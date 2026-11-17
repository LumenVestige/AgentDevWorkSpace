"""Installed master worktree and read-only risk detection (local Git only)."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

from support import Sandbox, copy_source, snapshot
from lib.repository import stage_repository, installation_risk


class InstalledRepository(Sandbox):
    def setUp(self):
        super().setUp()
        self.source = copy_source(self.base / 'source')
        (self.source / '.gitignore').write_text('private/\n__pycache__/\n*.pyc\n')
        (self.source / 'extra').mkdir()
        (self.source / 'extra/tracked.txt').write_text('FULL TREE')
        self.git('init', '-q', '-b', 'master', self.source)
        self.git('add', '.', cwd=self.source)
        self.git('commit', '-qm', '[update] fixture', cwd=self.source)
        self.commit = self.git('rev-parse', 'HEAD', cwd=self.source)
        self.git('branch', 'feature', cwd=self.source)
        self.home = self.base / 'global 安装'
        self.home.mkdir()
        self.app = self.home / 'app'
        stage_repository(self.source, self.app, str(self.source))
        (self.app / '.agentdev-app').touch()
        self.metadata = {'repository': str(self.source), 'path_configured': False, 'commit': self.commit}
        (self.home / 'install.json').write_text(json.dumps(self.metadata))
        (self.base / 'remote-version').write_text('0.3.0')

    def cli(self, *args, success=True):
        return self.run_command([sys.executable, self.app / 'scripts/command/app.py', *args], success=success)

    def test_master_only_independent_and_clean(self):
        self.assertEqual(self.git('branch', '--format=%(refname:short)', cwd=self.app), 'master')
        self.assertEqual(self.git('config', '--get-all', 'remote.origin.fetch', cwd=self.app),
                         '+refs/heads/master:refs/remotes/origin/master')
        self.assertFalse((self.app / '.git/objects/info/alternates').exists())
        self.assertTrue((self.app / 'extra/tracked.txt').is_file())
        shutil.rmtree(self.source)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=self.app), self.commit)
        self.assertEqual(installation_risk(self.home), ('', False))
        self.assertEqual(self.git('status', '--porcelain', cwd=self.app), '')

    def test_runtime_files_do_not_warn(self):
        cache = self.app / 'scripts/lib/__pycache__'
        cache.mkdir()
        (cache / 'example.pyc').write_bytes(b'cache')
        self.assertEqual(installation_risk(self.home), ('', False))

    def test_modified_staged_deleted_and_untracked_files_warn(self):
        for kind in ('modified', 'staged', 'deleted', 'untracked'):
            with self.subTest(kind=kind):
                path = self.app / ('manual.txt' if kind == 'untracked' else 'README.md')
                if kind == 'deleted':
                    path.unlink()
                else:
                    path.write_text('MANUAL EDIT')
                if kind == 'staged':
                    self.git('add', 'README.md', cwd=self.app)
                before = snapshot(self.app)
                index = (self.app / '.git/index').read_bytes()
                text, blocked = installation_risk(self.home)
                self.assertTrue(blocked)
                self.assertIn('风险', text)
                self.assertIn(path.name, text)
                self.assertIn('异常改动', text)
                self.assertIn('执行[agentdev update]进行强制覆盖更新。', text)
                self.assertNotIn('更新可能丢失这些改动', text)
                self.assertNotIn('未提交改动', text)
                self.assertNotIn('git status', text)
                self.assertEqual(snapshot(self.app), before)
                self.assertEqual((self.app / '.git/index').read_bytes(), index)
                self.git('reset', '--hard', '-q', 'HEAD', cwd=self.app)
                if kind == 'untracked':
                    path.unlink()

    def test_manual_commit_and_branch_switch_warn(self):
        self.git('checkout', '-qb', 'manual', cwd=self.app)
        self.assertIn('master', installation_risk(self.home)[0])
        self.git('checkout', '-q', 'master', cwd=self.app)
        self.commit_file(self.app, 'manual.txt', 'local commit')
        text, blocked = installation_risk(self.home)
        self.assertTrue(blocked)
        self.assertIn('HEAD', text)

    def test_missing_or_corrupt_git_is_not_reported_clean(self):
        shutil.rmtree(self.app / '.git')
        text, blocked = installation_risk(self.home)
        self.assertTrue(blocked)
        self.assertIn('.git', text)
        (self.app / '.git').mkdir()
        self.assertTrue(installation_risk(self.home)[1])

    def test_old_snapshot_warns_but_can_migrate(self):
        shutil.rmtree(self.app / '.git')
        self.metadata.pop('commit')
        (self.home / 'install.json').write_text(json.dumps(self.metadata))
        text, blocked = installation_risk(self.home)
        self.assertIn('无法检查', text)
        self.assertFalse(blocked)

    def test_git_failure_warns(self):
        with patch('lib.repository.git', side_effect=OSError('fixture git missing')):
            text, blocked = installation_risk(self.home)
        self.assertTrue(blocked)
        self.assertIn('无法检查', text)

    def test_cli_version_and_update_check_warn_without_mutation(self):
        (self.app / 'README.md').write_text('MANUAL EDIT')
        before = snapshot(self.app)
        for args in (('version',), ('update', '--check')):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertIn('风险', result.stderr)
                self.assertIn('README.md', result.stderr)
                self.assertIn('0.3.0', result.stdout)
                self.assertEqual(snapshot(self.app), before)

    def test_remote_failure_does_not_hide_local_risk(self):
        (self.app / 'manual.txt').write_text('MANUAL EDIT')
        (self.base / 'remote-version').write_text('invalid')
        result = self.cli('version', success=False)
        self.assertIn('风险', result.stderr)
        self.assertIn('manual.txt', result.stderr)

    def test_automatic_update_does_not_overwrite_local_changes(self):
        (self.app / 'README.md').write_text('KEEP')
        (self.base / 'remote-version').write_text('0.4.0')
        result = self.cli('update', '--project', self.base, success=False)
        self.assertIn('风险', result.stderr)
        self.assertIn('暂停', result.stderr)
        self.assertEqual((self.app / 'README.md').read_text(), 'KEEP')
        self.assertFalse((self.home / 'app.previous').exists())
        self.assertFalse((self.home / '.install.lock').exists())

    def test_manual_same_version_update_overwrites_all_uncommitted_changes(self):
        (self.app / 'README.md').write_text('DISCARD UNSTAGED')
        (self.app / 'extra/tracked.txt').write_text('DISCARD STAGED')
        self.git('add', 'extra/tracked.txt', cwd=self.app)
        (self.app / 'AGENTS.md').unlink()
        (self.app / 'manual.txt').write_text('DISCARD UNTRACKED')
        result = self.cli('update')
        self.assertIn('已更新到 0.3.0', result.stdout)
        self.assertIn('执行[agentdev update]进行强制覆盖更新。', result.stderr)
        self.assertEqual((self.app / 'README.md').read_bytes(), (self.source / 'README.md').read_bytes())
        self.assertEqual((self.app / 'extra/tracked.txt').read_text(), 'FULL TREE')
        self.assertTrue((self.app / 'AGENTS.md').is_file())
        self.assertFalse((self.app / 'manual.txt').exists())
        self.assertEqual(installation_risk(self.home), ('', False))
        self.assertEqual(json.loads((self.home / 'update-status.json').read_text())['result'], 'success')
        self.assertFalse((self.home / 'app.previous').exists())

    def test_manual_new_version_update_overwrites_local_changes(self):
        (self.app / 'README.md').write_text('DISCARD')
        self.commit_file(self.source, 'publish/version', '0.4.0\n')
        (self.base / 'remote-version').write_text('0.4.0')
        result = self.cli('update')
        self.assertIn('已更新到 0.4.0', result.stdout)
        self.assertEqual(installation_risk(self.home), ('', False))
        self.assertEqual((self.app / 'README.md').read_bytes(), (self.source / 'README.md').read_bytes())

    def test_manual_force_validates_version_before_replacement(self):
        (self.app / 'README.md').write_text('KEEP')
        (self.base / 'remote-version').write_text('0.4.0')
        before = snapshot(self.app)
        result = self.cli('update', success=False)
        self.assertIn('远端源码尚未包含公布的版本', result.stderr)
        self.assertEqual(snapshot(self.app), before)
        self.assertEqual(json.loads((self.home / 'update-status.json').read_text())['result'], 'failed')

    def test_manual_same_version_force_rejects_older_checkout(self):
        (self.app / 'README.md').write_text('KEEP')
        self.commit_file(self.source, 'publish/version', '0.2.0\n')
        before = snapshot(self.app)
        self.cli('update', success=False)
        self.assertEqual(snapshot(self.app), before)
        self.assertEqual(json.loads((self.home / 'update-status.json').read_text())['result'], 'failed')

    def test_manual_same_version_update_overwrites_changes_after_git_repair(self):
        shutil.rmtree(self.app / '.git')
        (self.app / 'README.md').write_text('DISCARD')
        result = self.cli('update')
        self.assertIn('.git 已补齐', result.stdout)
        self.assertIn('已更新到 0.3.0', result.stdout)
        self.assertEqual((self.app / 'README.md').read_bytes(), (self.source / 'README.md').read_bytes())
        self.assertEqual(installation_risk(self.home), ('', False))

    def test_check_reports_installation_changes_without_mutation(self):
        self.run_command(['sh', self.source / 'setup.sh', '--no-path'])
        project = self.base / 'check-project'
        project.mkdir()
        self.cli('init', project)
        before = snapshot(self.home)
        result = self.cli('check', project)
        self.assertNotIn('风险提示', result.stderr)
        self.assertIn('检查通过', result.stdout)
        self.assertEqual(snapshot(self.home), before)
        # check must not depend on remote version availability.
        (self.base / 'remote-version').write_text('invalid')
        for kind in ('modified', 'staged', 'deleted', 'untracked'):
            with self.subTest(kind=kind):
                path = self.app / ('manual.txt' if kind == 'untracked' else 'README.md')
                if kind == 'deleted':
                    path.unlink()
                else:
                    path.write_text('KEEP')
                if kind == 'staged':
                    self.git('add', 'README.md', cwd=self.app)
                before = snapshot(self.home)
                index = (self.app / '.git/index').read_bytes()
                result = self.cli('check', project, success=False)
                self.assertIn(path.name, result.stderr)
                self.assertIn('执行[agentdev update]进行强制覆盖更新。', result.stderr)
                self.assertIn('检查通过', result.stdout)
                self.assertEqual(snapshot(self.home), before)
                self.assertEqual((self.app / '.git/index').read_bytes(), index)
                self.git('reset', '--hard', '-q', 'HEAD', cwd=self.app)
                if kind == 'untracked':
                    path.unlink()

    def test_check_reports_risk_even_if_workspace_is_invalid(self):
        (self.app / 'README.md').write_text('KEEP')
        before = snapshot(self.home)
        result = self.cli('check', self.base / 'missing-project', success=False)
        self.assertIn('README.md', result.stderr)
        self.assertIn('工作区缺少', result.stdout)
        self.assertEqual(snapshot(self.home), before)

    def test_check_missing_git_is_read_only(self):
        shutil.rmtree(self.app / '.git')
        before = snapshot(self.home)
        result = self.cli('check', self.base / 'missing-project', success=False)
        self.assertIn('缺少独立 .git', result.stderr)
        self.assertFalse((self.app / '.git').exists())
        self.assertEqual(snapshot(self.home), before)

    def test_stage_preserves_dirty_source_without_private_files_or_source_writes(self):
        (self.source / 'README.md').write_text('DIRTY SOURCE')
        (self.source / 'AGENTS.md').unlink()
        (self.source / 'new.txt').write_text('UNTRACKED')
        (self.source / 'private').mkdir()
        (self.source / 'private/secret').write_text('DO NOT COPY')
        before = snapshot(self.source)
        index = (self.source / '.git/index').read_bytes()
        target = self.home / 'new-app'
        stage_repository(self.source, target, 'fixture-origin')
        self.assertEqual((target / 'README.md').read_text(), 'DIRTY SOURCE')
        self.assertFalse((target / 'AGENTS.md').exists())
        self.assertTrue((target / 'new.txt').is_file())
        self.assertFalse((target / 'private').exists())
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=target), self.commit)
        self.assertEqual(self.git('config', 'remote.origin.url', cwd=target), 'fixture-origin')
        self.assertEqual(snapshot(self.source), before)
        self.assertEqual((self.source / '.git/index').read_bytes(), index)

    def test_install_keeps_git_and_records_baseline(self):
        result = self.run_command(['sh', self.source / 'setup.sh', '--no-path'])
        self.assertIn('已安装', result.stdout)
        metadata = json.loads((self.home / 'install.json').read_text())
        self.assertEqual(metadata['commit'], self.commit)
        self.assertEqual(installation_risk(self.home), ('', False))
        self.assertEqual(self.git('branch', '--format=%(refname:short)', cwd=self.app), 'master')

    def test_welcome_surfaces_risk_and_does_not_spawn_update(self):
        project = self.make_project(git=False)
        state = project / 'agent-workspace/.agent/env'
        (state / 'agentskill-path').write_text(str(self.app))
        (self.app / 'README.md').write_text('MANUAL EDIT')
        (self.base / 'remote-version').write_text('0.4.0')
        config = project / 'agent-workspace/config/config.json5'
        config.write_text(json.dumps({'personal': 'Test Owner', 'auto_update': True,
                                     'update_url': (self.base / 'remote-version').as_uri()}))
        result = self.skill(project, 'notes/update.py', '--welcome')
        self.assertIn('风险', result.stdout)
        self.assertIn('README.md', result.stdout)
        self.assertIn('暂停', result.stdout)
        self.assertNotIn('正在后台更新', result.stdout)
        self.assertFalse((state / 'last-update').exists())

    def test_symlink_changes_are_copied_without_following_targets(self):
        outside = self.base / 'outside'
        outside.mkdir()
        marker = outside / 'marker'
        marker.write_text('KEEP')
        shutil.rmtree(self.source / 'extra')
        (self.source / 'extra').symlink_to(outside, target_is_directory=True)
        target = self.home / 'symlink-app'
        stage_repository(self.source, target, 'fixture')
        self.assertTrue((target / 'extra').is_symlink())
        self.assertEqual(marker.read_text(), 'KEEP')
        self.assertFalse((target / 'marker').exists())

    def test_linked_worktree_becomes_independent_master_repository(self):
        linked = self.base / 'linked'
        self.git('worktree', 'add', '--force', linked, 'master', cwd=self.source)
        target = self.home / 'linked-app'
        stage_repository(linked, target, 'fixture')
        self.assertTrue((target / '.git').is_dir())
        self.git('worktree', 'remove', linked, cwd=self.source)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=target), self.commit)

    def test_non_master_source_is_rejected_without_switching_it(self):
        self.git('checkout', '-q', 'feature', cwd=self.source)
        with self.assertRaisesRegex(RuntimeError, 'master'):
            stage_repository(self.source, self.home / 'rejected', 'fixture')
        self.assertEqual(self.git('branch', '--show-current', cwd=self.source), 'feature')

    def test_caller_git_overrides_do_not_redirect_checks(self):
        from lib.repository import git
        with patch.dict('os.environ', {'GIT_DIR': str(self.source / '.git'),
                                       'GIT_INDEX_FILE': str(self.source / '.git/index')}):
            self.assertEqual(Path(git(self.app, 'rev-parse', '--show-toplevel').strip()), self.app)
        (self.app / 'manual.txt').write_text('DIRTY')
        self.assertTrue(installation_risk(self.home)[1])

    def test_welcome_json_preserves_risk_line(self):
        project = self.make_project(git=False)
        (project / 'agent-workspace/.agent/env/agentskill-path').write_text(str(self.app))
        (self.app / 'manual.txt').write_text('MANUAL EDIT')
        config = project / 'agent-workspace/config/config.json5'
        config.write_text(json.dumps({'personal': 'Test Owner', 'auto_update': False,
                                     'update_url': (self.base / 'remote-version').as_uri()}))
        result = self.skill(project, 'sdd/welcome.py')
        message = json.loads(result.stdout)['systemMessage']
        self.assertIn('风险提示', message)
        self.assertIn('manual.txt', message)
        self.assertIn('⚠', message)

    def test_legacy_snapshot_upgrades_to_clean_git_installation(self):
        shutil.rmtree(self.app / '.git')
        self.metadata.pop('commit')
        (self.home / 'install.json').write_text(json.dumps(self.metadata))
        (self.source / 'publish/version').write_text('0.4.0\n')
        self.git('add', 'publish/version', cwd=self.source)
        self.git('commit', '-qm', '[update] fixture upgrade', cwd=self.source)
        (self.base / 'remote-version').write_text('0.4.0')
        self.run_command([sys.executable, '-m', 'venv', self.home / 'venv'])
        result = self.cli('update')
        self.assertIn('已更新到 0.4.0', result.stdout)
        self.assertIn('无法检查', result.stderr)
        self.assertEqual(installation_risk(self.home), ('', False))
        self.assertEqual(self.git('branch', '--show-current', cwd=self.app), 'master')

    def test_git_timeout_warns_instead_of_reporting_clean(self):
        with patch('lib.repository.git', side_effect=subprocess.TimeoutExpired('git', 5)):
            text, blocked = installation_risk(self.home)
        self.assertTrue(blocked)
        self.assertIn('无法检查', text)

    def test_update_from_app_does_not_initialize_installation_as_a_project(self):
        workspace = self.app / 'agent-workspace'
        workspace.mkdir()
        (workspace / 'tracked.txt').write_text('SHIPPED WORKSPACE')
        self.git('add', 'agent-workspace', cwd=self.app)
        self.git('commit', '-qm', '[update] fixture workspace', cwd=self.app)
        self.metadata['commit'] = self.git('rev-parse', 'HEAD', cwd=self.app)
        (self.home / 'install.json').write_text(json.dumps(self.metadata))
        before = snapshot(self.app)
        self.run_command([sys.executable, self.app / 'scripts/command/app.py', 'update'], cwd=self.app)
        self.assertEqual(snapshot(self.app), before)
        self.assertEqual(installation_risk(self.home), ('', False))

    def test_same_version_update_repairs_missing_git_without_overwriting_source(self):
        shutil.rmtree(self.app / '.git')
        self.metadata.pop('commit')
        (self.home / 'install.json').write_text(json.dumps(self.metadata))
        before = snapshot(self.app)
        result = self.cli('update')
        self.assertIn('.git 已补齐', result.stdout)
        self.assertEqual(snapshot(self.app), before)
        self.assertEqual(installation_risk(self.home), ('', False))
        self.assertEqual(self.git('branch', '--format=%(refname:short)', cwd=self.app), 'master')
        self.assertFalse((self.app / '.git/objects/info/alternates').exists())
        self.assertEqual(self.git('config', 'remote.origin.url', cwd=self.app), str(self.source))
        status = json.loads((self.home / 'update-status.json').read_text())
        self.assertEqual(status['result'], 'success')
        self.assertEqual(status['from_version'], status['to_version'])
        task_id = status['task_id']
        self.cli('update')
        self.assertEqual(json.loads((self.home / 'update-status.json').read_text())['task_id'], task_id)
        shutil.rmtree(self.source)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=self.app), self.commit)

    def test_git_repair_uses_recorded_commit_not_newer_master(self):
        shutil.rmtree(self.app / '.git')
        before = snapshot(self.app)
        self.commit_file(self.source, 'publish/version', '0.4.0\n')
        result = self.cli('update')  # published version still 0.3.0
        self.assertIn('.git 已补齐', result.stdout)
        self.assertEqual(snapshot(self.app), before)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=self.app), self.commit)
        self.assertEqual(installation_risk(self.home), ('', False))

    def test_git_repair_preserves_and_reports_abnormal_changes(self):
        (self.app / 'README.md').write_text('KEEP MANUAL EDIT')
        (self.app / 'AGENTS.md').unlink()
        (self.app / 'manual.txt').write_text('KEEP UNTRACKED')
        for recorded in (True, False):
            with self.subTest(recorded_commit=recorded):
                shutil.rmtree(self.app / '.git')
                if not recorded:
                    self.metadata.pop('commit')
                    (self.home / 'install.json').write_text(json.dumps(self.metadata))
                before = snapshot(self.app)
                result = self.cli('update', '--project', self.base, success=False)
                self.assertIn('.git 已补齐', result.stdout)
                self.assertIn('异常改动', result.stderr)
                for name in ('README.md', 'AGENTS.md', 'manual.txt'):
                    self.assertIn(name, result.stderr)
                self.assertEqual(snapshot(self.app), before)
                self.assertTrue(installation_risk(self.home)[1])
                self.assertEqual(json.loads((self.home / 'update-status.json').read_text())['result'], 'blocked')
                self.assertFalse((self.home / 'app.previous').exists())
                self.assertFalse((self.home / '.install.lock').exists())

    def test_missing_git_version_and_check_remain_read_only(self):
        shutil.rmtree(self.app / '.git')
        before = snapshot(self.home)
        for args in (('version',), ('update', '--check')):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertIn('agentdev update', result.stderr)
                self.assertIn('缺少独立 .git', result.stderr)
                self.assertFalse((self.app / '.git').exists())
                self.assertEqual(snapshot(self.home), before)

    def test_git_repair_refuses_unmatched_or_unavailable_baselines(self):
        shutil.rmtree(self.app / '.git')
        self.commit_file(self.source, 'publish/version', '0.4.0\n')
        # No baseline, wrong version, unknown SHA, wrong-version SHA, invalid SHA.
        for baseline in (None, 'f' * 40, self.git('rev-parse', 'HEAD', cwd=self.source), '--unsafe'):
            with self.subTest(baseline=baseline):
                self.metadata.pop('commit', None)
                if baseline is not None:
                    self.metadata['commit'] = baseline
                (self.home / 'install.json').write_text(json.dumps(self.metadata))
                before = snapshot(self.app)
                metadata_before = (self.home / 'install.json').read_bytes()
                self.cli('update', success=False)
                self.assertFalse((self.app / '.git').exists())
                self.assertEqual(snapshot(self.app), before)
                self.assertEqual((self.home / 'install.json').read_bytes(), metadata_before)
                self.assertEqual(json.loads((self.home / 'update-status.json').read_text())['result'], 'failed')
                self.assertFalse(list(self.home.glob('repair-git-*')))

    def test_git_repair_download_failure_preserves_installation(self):
        shutil.rmtree(self.app / '.git')
        self.metadata['repository'] = str(self.base / 'does-not-exist')
        (self.home / 'install.json').write_text(json.dumps(self.metadata))
        before = snapshot(self.app)
        self.cli('update', success=False)
        self.assertEqual(snapshot(self.app), before)
        self.assertFalse((self.app / '.git').exists())
        self.assertEqual(json.loads((self.home / 'install.json').read_text()), self.metadata)
        self.assertEqual(json.loads((self.home / 'update-status.json').read_text())['result'], 'failed')

    def test_git_repair_rolls_back_if_metadata_cannot_be_written(self):
        from lib.installer import repair_repository
        shutil.rmtree(self.app / '.git')
        before = snapshot(self.home)
        with patch('lib.update_status.atomic_json', side_effect=OSError('fixture write failure')):
            with self.assertRaisesRegex(OSError, 'fixture write failure'):
                repair_repository(self.home, self.source)
        self.assertFalse((self.app / '.git').exists())
        self.assertEqual(snapshot(self.home), before)
        self.assertFalse(list(self.home.glob('repair-git-*')))

    def test_git_repair_does_not_replace_existing_git(self):
        from lib.installer import repair_repository
        # Valid, corrupt directory, Git file and dangling symlink are never repair candidates.
        for kind in ('valid', 'directory', 'file', 'symlink'):
            with self.subTest(kind=kind):
                path = self.app / '.git'
                if kind != 'valid':
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    if kind == 'directory':
                        path.mkdir()
                    elif kind == 'file':
                        path.write_text('gitdir: nonexistent\n')
                    else:
                        path.symlink_to(self.base / 'nonexistent')
                before = snapshot(self.app)
                with self.assertRaisesRegex(RuntimeError, '不替换已有 Git'):
                    repair_repository(self.home, self.source)
                self.assertEqual(snapshot(self.app), before)
                if kind != 'valid':
                    self.metadata.pop('commit', None)
                    (self.home / 'install.json').write_text(json.dumps(self.metadata))
                    self.assertTrue(installation_risk(self.home)[1])
                    (self.base / 'remote-version').write_text('0.4.0')
                    self.cli('update', '--project', self.base, success=False)
                    self.assertEqual(snapshot(self.app), before)
                    self.assertFalse((self.home / 'app.previous').exists())

    def test_missing_git_with_recorded_baseline_can_upgrade_after_repair(self):
        shutil.rmtree(self.app / '.git')
        self.commit_file(self.source, 'publish/version', '0.4.0\n')
        (self.base / 'remote-version').write_text('0.4.0')
        self.run_command([sys.executable, '-m', 'venv', self.home / 'venv'])
        result = self.cli('update')
        self.assertIn('.git 已补齐', result.stdout)
        self.assertIn('已更新到 0.4.0', result.stdout)
        self.assertEqual(installation_risk(self.home), ('', False))
        self.assertEqual((self.app / 'publish/version').read_text(), '0.4.0\n')

    def test_missing_git_abnormal_changes_block_newer_version_upgrade(self):
        shutil.rmtree(self.app / '.git')
        self.commit_file(self.source, 'publish/version', '0.4.0\n')
        (self.base / 'remote-version').write_text('0.4.0')
        (self.app / 'README.md').write_text('KEEP')
        before = snapshot(self.app)
        result = self.cli('update', '--project', self.base, success=False)
        self.assertIn('异常改动', result.stderr)
        self.assertEqual(snapshot(self.app), before)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=self.app), self.commit)
        self.assertEqual(json.loads((self.home / 'update-status.json').read_text())['result'], 'blocked')
