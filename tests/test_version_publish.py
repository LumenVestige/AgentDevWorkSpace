"""三段版本、主仓库地址迁移和单仓库发布的离线行为验证。"""
import base64
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from support import ROOT, TMP, isolated_env
import _version as versions


class VersionRules(unittest.TestCase):
    def test_integer_tuple_comparison(self):
        for low, high in [('0.9.2','0.9.10'), ('0.9.99','0.10.0'), ('0.99.99','1.0.0')]:
            self.assertLess(versions.parse_version(low), versions.parse_version(high))
        self.assertEqual(versions.next_patch((0, 3, 9)), (0, 3, 10))

    def test_legacy_read_migration(self):
        for raw, expected in [('0.3', '0.3.0'), ('7', '7.0.0'), ('0.3.10', '0.3.10'), (' 1.0.2\n', '1.0.2')]:
            self.assertEqual(versions.format_version(versions.parse_version(raw, allow_legacy=True)), expected)
        for raw in ('0.3', '7', '01.2.3', '1.02.3', '-1.2.3', '1.2.3.4', 'v1.2.3', '1.0.0-beta', 'NaN', '1e2'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                versions.parse_version(raw)

    def response(self, body):
        value = Mock()
        value.__enter__ = Mock(return_value=value)
        value.__exit__ = Mock(return_value=False)
        value.read.return_value = body
        return value

    def test_retired_urls_never_requested(self):
        old_urls = [
            'https://raw.githubusercontent.com/LumenVestige/versions/main/AgentDevWorkSpace/version',
            'https://api.github.com/repos/LumenVestige/versions/contents/AgentDevWorkSpace/version?ref=main',
            'https://github.com/LumenVestige/versions/blob/main/AgentDevWorkSpace/version',
            versions.PAGE_URL,
        ]
        for address in old_urls:
            with patch.dict(os.environ, {'GITHUB_TOKEN':'', 'GH_TOKEN':''}), patch.object(versions.urllib.request, 'urlopen', return_value=self.response(b'0.3\n')) as request:
                self.assertEqual(versions.fetch_remote_version(address), (0, 3, 0))
                self.assertEqual(request.call_args.args[0].full_url, versions.API_URL)
                self.assertNotIn('/versions/', request.call_args.args[0].full_url)

    def test_main_file_api_fallback_and_base64(self):
        body = json.dumps({'content':base64.b64encode(b'0.3.1\n').decode()}).encode()
        with patch.dict(os.environ, {'GITHUB_TOKEN':'', 'GH_TOKEN':''}), patch.object(versions.urllib.request, 'urlopen', side_effect=[OSError('api unavailable'), self.response(b'0.3.1\n')]) as request:
            self.assertEqual(versions.fetch_remote_version(), (0, 3, 1))
            self.assertEqual(request.call_args_list[1].args[0].full_url, versions.RAW_URL)
        with patch.object(versions.urllib.request, 'urlopen', return_value=self.response(body)) as request:
            self.assertEqual(versions.fetch_remote_version(), (0, 3, 1))
            self.assertEqual(request.call_args.args[0].full_url, versions.API_URL)

    def test_private_api_token_is_scoped(self):
        with patch.dict(os.environ, {'GITHUB_TOKEN':'fixture-token'}), patch.object(versions.urllib.request, 'urlopen', return_value=self.response(b'0.3.1\n')) as request:
            versions.fetch_remote_version()
            self.assertEqual(request.call_args.args[0].full_url, versions.API_URL)
            self.assertEqual(request.call_args.args[0].get_header('Authorization'), 'Bearer fixture-token')
            versions.fetch_remote_version('http://127.0.0.1/custom-version')
            self.assertIsNone(request.call_args.args[0].get_header('Authorization'))

    def test_failures_are_errors(self):
        for body in (b'', b'not a version', b'0.1.2.3', b'{"message":"rate limited"}',
                     b'{"content":null}', b'{"content":"not-base64"}', b'\xff\xfe'):
            with patch.object(versions.urllib.request, 'urlopen', return_value=self.response(body)), self.assertRaises(RuntimeError):
                versions.fetch_remote_version('http://127.0.0.1/version')

    def test_network_failure_and_timeout_budget(self):
        with patch.object(versions.urllib.request, 'urlopen', side_effect=TimeoutError('fixture timeout')) as request:
            with self.assertRaisesRegex(RuntimeError, 'fixture timeout'):
                versions.fetch_remote_version(timeout=3)
            self.assertEqual(len(request.call_args_list), 2)
            for call in request.call_args_list:
                self.assertEqual(call.kwargs['timeout'], 3)

    def test_api_failure_never_sends_token_to_raw_fallback(self):
        with patch.dict(os.environ, {'GITHUB_TOKEN':'', 'GH_TOKEN':'fixture-gh-token'}), \
             patch.object(versions.urllib.request, 'urlopen', side_effect=[OSError('fixture'), self.response(b'1.2.3')]) as request:
            self.assertEqual(versions.fetch_remote_version(), (1, 2, 3))
            self.assertEqual(request.call_args_list[0].args[0].get_header('Authorization'), 'Bearer fixture-gh-token')
            self.assertIsNone(request.call_args_list[1].args[0].get_header('Authorization'))

    def test_format_rejects_invalid_tuple_components(self):
        for value in ((1, 2), (1, 2, 3, 4), (True, 2, 3), (1, -1, 3), (1, 2, 3.0)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                versions.format_version(value)

    def test_similar_hosts_and_unrelated_repositories_not_rewritten(self):
        for address in ('https://api.github.com.example.invalid/repos/LumenVestige/versions/file',
                        'https://github.com/another/versions/blob/main/file',
                        'http://127.0.0.1/publish/version'):
            with self.subTest(address=address):
                self.assertEqual(versions.normalize_url(address), address)

    def test_local_http_version_file(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != '/publish/version':
                    self.send_error(404)
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'0.9.10\n')
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            self.assertEqual(versions.fetch_remote_version(f'http://127.0.0.1:{server.server_port}/publish/version'), (0, 9, 10))
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


class Publishing(unittest.TestCase):
    def publish_case(self, old, expected=None, target=None, commit_fail=False, push_fail=False, stage_fail=False,
                     error=None, message='[update] fixture publish', dirty=False):
        with tempfile.TemporaryDirectory(prefix='publish-', dir=TMP) as temporary:
            base = Path(temporary)
            env = isolated_env(base)
            def git(*args, cwd=None):
                return subprocess.run(['git', *map(str, args)], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout.strip()
            remote, root = base / 'main.git', base / 'source'
            git('init', '-q', '--bare', '--initial-branch=master', remote)
            git('init', '-q', '-b', 'master', root)
            (root / 'publish').mkdir()
            (root / 'skills/git-commit').mkdir(parents=True)
            shutil.copy(ROOT / 'publish/publish.sh', root / 'publish/publish.sh')
            shutil.copy(ROOT / 'skills/git-commit/commit-msg', root / 'skills/git-commit/commit-msg')
            shutil.copy(ROOT / 'skills/_version.py', root / 'skills/_version.py')
            if old is not None:
                (root / 'publish/version').write_text(old + '\n')
            git('add', '.', cwd=root)
            git('commit', '-qm', '[update] fixture', cwd=root)
            git('remote', 'add', 'origin', remote, cwd=root)
            git('push', '-qu', 'origin', 'master', cwd=root)
            before = git('rev-parse', 'HEAD', cwd=root)
            if dirty:
                (root / 'new feature.txt').write_text('NEW FEATURE\n')
            if stage_fail:
                git('init', '-q', root / 'nested-empty-repo')
            if commit_fail:
                hook = root / '.git/hooks/pre-commit'
                hook.write_text('#!/bin/sh\nexit 1\n')
                hook.chmod(0o755)
            if push_fail:
                hook = remote / 'hooks/pre-receive'
                hook.write_text('#!/bin/sh\nexit 1\n')
                hook.chmod(0o755)
            result = subprocess.run(['sh', 'publish/publish.sh', message, *([target] if target else [])], cwd=root, env=env, capture_output=True, text=True, timeout=30)
            self.assertFalse((root / 'publish/versions').exists())
            remote_version = (git('--git-dir', remote, 'show', 'master:publish/version')
                              if git('--git-dir', remote, 'ls-tree', 'master', 'publish/version') else None)
            if error:
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error, result.stderr)
                self.assertEqual(remote_version, old)
                if push_fail:
                    self.assertEqual((root / 'publish/version').read_text().strip(), expected)
                    self.assertNotEqual(git('rev-parse', 'HEAD', cwd=root), before)
                else:
                    if old is None:
                        self.assertFalse((root / 'publish/version').exists())
                    else:
                        self.assertEqual((root / 'publish/version').read_text(), old + '\n')
                    self.assertEqual(git('rev-parse', 'HEAD', cwd=root), before)
            else:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(remote_version, expected)
                self.assertEqual((root / 'publish/version').read_text(), expected + '\n')
                self.assertFalse(git('status', '--porcelain', cwd=root))
                if dirty:
                    self.assertEqual(git('--git-dir', remote, 'show', 'master:new feature.txt'), 'NEW FEATURE')

    def test_default_patch(self):
        self.publish_case('0.3.0', '0.3.1')

    def test_missing_version_starts_at_first_patch(self):
        self.publish_case(None, '0.0.1')

    def test_commit_failure_restores_missing_version(self):
        self.publish_case(None, commit_fail=True, error='版本号已恢复')

    def test_patch_is_not_decimal(self):
        self.publish_case('0.3.9', '0.3.10')

    def test_legacy_local_version(self):
        self.publish_case('0.3', '0.3.1')

    def test_explicit_major(self):
        self.publish_case('0.3.0', '1.0.0', target='1.0.0')

    def test_explicit_minor(self):
        self.publish_case('0.3.0', '0.4.0', target='0.4.0')

    def test_explicit_two_parts_rejected(self):
        self.publish_case('0.3.0', target='0.4', error='大版本.小版本.补丁版本')

    def test_bad_local_version_rejected(self):
        self.publish_case('not-version', error='无效版本号')

    def test_commit_failure_restores_version(self):
        self.publish_case('0.3.0', commit_fail=True, error='版本号已恢复')

    def test_stage_failure_restores_version(self):
        self.publish_case('0.3.0', stage_fail=True, error='暂存失败，版本号已恢复')

    def test_push_failure_keeps_completed_commit(self):
        self.publish_case('0.3.0', '0.3.1', push_fail=True, error='推送失败')

    def test_invalid_commit_message_does_not_bump_version(self):
        self.publish_case('0.3.0', message='untagged message', error='提交信息必须')

    def test_publication_includes_pending_source_changes(self):
        self.publish_case('0.3.0', '0.3.1', dirty=True)

    def test_multiline_commit_message(self):
        self.publish_case('0.3.0', '0.3.1', message='[update] 多行提交\n\n说明正文保留换行。')

    def test_invalid_explicit_versions_never_modify_repository(self):
        for target in ('01.2.3', '-1.0.0', '1.0.0-beta', '1.2.3.4'):
            with self.subTest(target=target):
                self.publish_case('0.3.0', target=target, error='无效版本号')


if __name__ == '__main__':
    unittest.main(verbosity=2)
