"""全局 CLI 离线集成检查；安装、profile、远端均位于仓库内临时目录。"""
from pathlib import Path
import getpass
import importlib.util
import json
import os
import shutil
import shlex
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from support import ROOT, TMP, WHEELS, isolated_env, snapshot, copy_source
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'skills'))
import _workspace_config as naming
import _version as semver
from lib import installer as agentdev
from lib import workspace


class GlobalCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='case-', dir=TMP)
        cls.base = Path(cls.temporary.name)
        cls.home = cls.base / 'global 安装'
        cls.remote_version = cls.base / 'remote-version'
        cls.remote_version.write_text('0.3\n')
        cls.env = isolated_env(cls.base, GIT_ALLOW_PROTOCOL='file')
        cls.source = copy_source(cls.base / 'fixture source')
        # Same-version update can now repair Git: use a real local master, never GitHub.
        for args in (['init', '-q', '-b', 'master'], ['add', '.'],
                     ['commit', '-qm', '[update] isolated CLI fixture'],
                     ['remote', 'add', 'origin', str(cls.source)]):
            subprocess.run(['git', '-C', str(cls.source), *args], env=cls.env, check=True,
                           capture_output=True)
        result = subprocess.run(['sh', str(cls.source / 'setup.sh'), '--no-path'],
                                cwd=cls.base, env=cls.env, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.py = agentdev.python_exe(cls.home)
        cls.entry = cls.home / 'app/scripts/command/app.py'

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.env = dict(type(self).env)

    def invoke(self, *args, cwd=None, success=True):
        result = subprocess.run([str(self.py), '-B', str(self.entry), *map(str, args)], cwd=cwd or self.base,
                                env=self.env, capture_output=True, text=True, timeout=120)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def project(self, name, git_repo=True):
        root = self.base / name
        root.mkdir()
        if git_repo:
            subprocess.run(['git', 'init', '-q', str(root)], env=self.env, check=True)
        return root

    def test_default_help_and_aliases(self):
        for args in ((), ('-help',), ('--h',), ('--help',), ('-h',), ('help',)):
            text = self.invoke(*args).stdout
            for command in ('init', 'update', 'check', 'version'):
                self.assertIn(command, text)

    def test_installed_commands_reject_setup_and_aliases_without_writes(self):
        before = snapshot(self.home)
        for name in ('agentdev', 'adev'):
            for command in ('setup', '-setup', '--s'):
                with self.subTest(name=name, command=command):
                    result = subprocess.run([str(self.home / 'bin' / name), command], cwd=self.base,
                                            env=self.env, capture_output=True, text=True, timeout=20)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(snapshot(self.home), before)
        self.assertIn('scripts/command/app.py', (self.home / 'bin/agentdev').read_text())

    def test_version_aliases(self):
        for alias in ('version', '-version', '--v', '--version', '-v'):
            result = self.invoke(alias)
            self.assertIn('本地版本：0.3.0', result.stdout)
            self.assertIn('远端版本：0.3.0', result.stdout)

    def test_launchers(self):
        text = subprocess.run([str(self.home / 'bin/agentdev'), '--h'], env=self.env, capture_output=True, text=True, check=True).stdout
        self.assertNotIn('setup', text)
        self.assertFalse((self.home / 'bin/agentdev.cmd').exists())
        self.assertFalse((self.home / 'bin/agentdev.ps1').exists())
        self.assertTrue((self.home / 'app/skills/sdd/render_welcome.py').is_file())
        self.assertTrue((self.home / 'env').is_file())

    def test_git_init_check_and_preserve(self):
        root = self.project('git 项目')
        (root / 'AGENTS.md').write_text('# Project rules\nKeep this.\n')
        (root / '.claude').mkdir()
        (root / '.claude/settings.local.json').write_text(json.dumps({'keep': True, 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo foreign'}]}]}}))
        self.invoke('--i', cwd=root)
        custom = root / 'agent-workspace/skills/custom/sdd'
        custom.mkdir()
        shutil.copy(self.home / 'app/skills/sdd/personal-constraints.md', custom / 'personal-constraints.md')
        (custom / 'welcome.md').write_text('CUSTOM')
        constraint = root / 'agent-workspace/workers/fixture-user/specs/constraints.md'
        constraint.write_text('PERSONAL')
        self.invoke('init', cwd=root)
        self.assertIn('Keep this.', (root / 'AGENTS.md').read_text())
        self.assertEqual((root / 'AGENTS.md').read_text().count('<!-- agentskill:begin'), 1)
        self.assertEqual(constraint.read_text(), 'PERSONAL')
        self.assertEqual((custom / 'welcome.md').read_text(), 'CUSTOM')
        cfg = json.loads((root / '.claude/settings.local.json').read_text())
        self.assertTrue(cfg['keep'])
        self.assertIn('foreign', json.dumps(cfg))
        self.assertEqual(len(cfg['hooks']['Stop']), 3)
        before = snapshot(root)
        self.assertIn('检查通过', self.invoke('check', cwd=root).stdout)
        self.assertEqual(before, snapshot(root))

    def test_plain_directory(self):
        root = self.project('plain project', git_repo=False)
        self.invoke('-init', cwd=root)
        self.assertIn('检查通过', self.invoke('check', cwd=root).stdout)
        self.assertFalse((root / '.git').exists())

    def test_missing_workspace(self):
        root = self.project('not initialized', git_repo=False)
        before = snapshot(root)
        self.invoke('check', cwd=root, success=False)
        self.assertEqual(before, snapshot(root))

    def test_missing_skill_detected(self):
        root = self.project('missing skill')
        self.invoke('init', cwd=root)
        (root / 'agent-workspace/skills/common/notes/verify.py').unlink()
        self.assertIn('缺少 skill', self.invoke('check', cwd=root, success=False).stdout)

    def test_bad_configuration(self):
        root = self.project('bad config')
        self.invoke('init', cwd=root)
        config = root / 'agent-workspace/config/config.json5'
        config.write_text('not json5 {')
        self.assertIn('配置格式错误', self.invoke('check', cwd=root, success=False).stdout)

    def test_hook_execution(self):
        root = self.project('hook execution')
        self.invoke('init', cwd=root)
        custom = root / 'agent-workspace/skills/custom/sdd'
        custom.mkdir()
        (custom / 'welcome.py').write_text('import json\nprint(json.dumps({"systemMessage":"CUSTOM_HOOK"}))\n')
        cfg = json.loads((root / '.codex/hooks.json').read_text())
        command = cfg['hooks']['SessionStart'][0]['hooks'][0]['command']
        result = subprocess.run(command, shell=True, cwd=root, env=self.env, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['systemMessage'], 'CUSTOM_HOOK')

    def test_agy_hooks_and_skills_use_official_project_configuration(self):
        root = self.project('agy hook execution')
        hooks = root / '.agents/hooks.json'
        hooks.parent.mkdir()
        foreign = {'Stop': [{'command': 'echo USER_HOOK'}]}
        stale = workspace.hook_command(self.py, self.source, root, 'sdd/welcome.py', 'agy')
        hooks.write_text(json.dumps({'user-hook': foreign, 'agentdev-workspace': {
            'SessionStart': [{'command': stale}]}}))
        result = subprocess.run([str(self.py), '-B', str(self.source / 'scripts/command/app.py'), 'init'],
                                cwd=root, env=self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((root / '.agents/skills/sdd/SKILL.md').is_file())
        self.assertEqual((root / 'GEMINI.md').readlink(), Path('AGENTS.md'))
        custom = root / 'agent-workspace/skills/custom/sdd'
        custom.mkdir()
        (custom / 'welcome.py').write_text('import json\nprint(json.dumps({"systemMessage":"AGY WELCOME"}))\n')
        cfg = json.loads(hooks.read_text())
        self.assertEqual(cfg['user-hook'], foreign)
        for handlers in cfg['agentdev-workspace'].values():
            for handler in handlers:
                args = shlex.split(handler['command'])
                self.assertEqual(args[0], str(self.py))
                self.assertEqual(args[2], str(self.home / 'app/scripts/lib/agy_hook.py'))
                self.assertEqual(args[args.index('--project') + 1], str(root))
        command = next(h['command'] for h in cfg['agentdev-workspace']['SessionStart'] if 'welcome.py' in h['command'])
        result = subprocess.run(command, shell=True, cwd=root, env=self.env, input='{}',
                                capture_output=True, text=True, check=True)
        step = json.loads(result.stdout)['injectSteps'][0]['systemMessage']
        self.assertIn('AGY WELCOME', step['systemMessage'])
        self.assertNotIn('renderInfo', step)
        before = hooks.read_bytes()
        self.invoke('init', cwd=root)
        self.assertEqual(hooks.read_bytes(), before)

    def test_invalid_agy_config_is_rejected_before_workspace_writes(self):
        for i, value in enumerate(('[]', '{"group":{"SessionStart":{}}}',
                                   '{"group":{"Stop":[{"command":5}]}}')):
            root = self.project(f'invalid agy hooks {i}')
            path = root / '.agents/hooks.json'
            path.parent.mkdir()
            path.write_text(value)
            before = snapshot(root)
            self.invoke('init', cwd=root, success=False)
            self.assertEqual(snapshot(root), before)

    def test_invalid_cli_and_nonzero_errors(self):
        self.invoke('unknown-command', success=False)
        self.invoke('init', self.base / 'missing', success=False)
        self.invoke('--u', '--remote', 'NaN', success=False)

    def test_init_rejects_git_subdirectories_and_install_prefix(self):
        root = self.project('nested init')
        child = root / 'child'
        child.mkdir()
        self.assertIn('仓库根目录', self.invoke('init', cwd=child, success=False).stderr)
        self.assertFalse((child / 'agent-workspace').exists())
        self.assertIn('全局安装目录', self.invoke('init', self.home, success=False).stderr)
        self.assertFalse((self.home / 'agent-workspace').exists())

    def test_hook_configuration_validated_before_workspace_writes(self):
        for index, invalid in enumerate(('[]', '{"hooks":[]}', '{"hooks":{"Stop":{}}}',
                                         '{"hooks":{"Stop":[{"hooks":[{"command":5}]}]}}')):
            with self.subTest(invalid=invalid):
                root = self.project(f'invalid hooks {index}')
                path = root / '.codex/hooks.json'
                path.parent.mkdir()
                path.write_text(invalid)
                before = snapshot(root)
                self.invoke('init', cwd=root, success=False)
                self.assertEqual(before, snapshot(root))
                self.assertFalse((root / 'agent-workspace').exists())

    def test_missing_python_pointer_fails_readonly_check(self):
        root = self.project('missing runtime')
        self.invoke('init', cwd=root)
        (root / 'agent-workspace/.agent/env/python-path').write_text(str(self.base / 'missing python'))
        before = snapshot(root)
        self.assertIn('解释器不存在', self.invoke('--c', cwd=root, success=False).stdout)
        self.assertEqual(before, snapshot(root))

    def test_managed_commit_hook_runs_and_foreign_hook_is_preserved(self):
        root = self.project('commit hook')
        self.invoke('init', cwd=root)
        (root / 'main.txt').write_text('PAYLOAD')
        subprocess.run(['git', '-C', str(root), 'add', 'main.txt'], env=self.env, check=True)
        result = subprocess.run(['git', '-C', str(root), 'commit', '-qm', 'invalid message'],
                                env=self.env, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('提交信息必须', result.stderr)
        subprocess.run(['git', '-C', str(root), 'commit', '-qm', '[update] valid message'], env=self.env, check=True)
        foreign = self.project('foreign commit hook')
        hook = foreign / '.git/hooks/commit-msg'
        content = '#!/bin/sh\n# foreign hook\nexit 0\n'
        hook.write_text(content)
        hook.chmod(0o755)
        self.invoke('init', cwd=foreign)
        self.assertEqual(hook.read_text(), content)

    def test_init_and_check_aliases(self):
        for index, alias in enumerate(('init', '--i', '-init')):
            with self.subTest(alias=alias):
                root = self.project(f'alias init {index}', git_repo=False)
                self.assertIn('检查通过', self.invoke(alias, cwd=root).stdout)
                for check in ('check', '--c', '-check'):
                    self.assertIn('检查通过', self.invoke(check, cwd=root).stdout)

    def test_check_only_never_initializes_workspace(self):
        root = self.project('update check only', git_repo=False)
        self.assertIn('已是最新', self.invoke('update', '--check', cwd=root).stdout)
        self.assertFalse((root / 'agent-workspace').exists())

    def test_reinstall(self):
        self.run_install_for_update()
        self.run_install_for_update()
        self.assertTrue((self.home / 'app/scripts/lib/run_skill.py').is_file())
        self.assertFalse((self.home / '.install.lock').exists())

    def test_python_pointer_and_real_updater(self):
        root = self.project('shared interpreter')
        self.invoke('init', cwd=root)
        env = root / 'agent-workspace/.agent/env'
        if (env / 'venv').is_symlink():
            (env / 'venv').unlink()
        config = root / 'agent-workspace/config/config.json5'
        config.write_text(json.dumps({'auto_update': False, 'update_url': self.remote_version.as_uri()}))
        welcome = root / 'agent-workspace/skills/common/sdd/welcome.py'
        result = subprocess.run([str(self.py), '-B', str(welcome)], cwd=root, env=self.env, capture_output=True, text=True, check=True)
        self.assertIn('本地 0.3.0', json.loads(result.stdout)['systemMessage'])
        updater = root / 'agent-workspace/skills/common/notes/update.py'
        subprocess.run([str(self.py), '-B', str(updater), '--run', '--remote', '0.3'], cwd=root, env=self.env, check=True, timeout=60)
        self.assertIn('已是最新', (env / 'update.log').read_text())
        self.assertFalse((env / 'update.lock').exists())
        self.assertFalse((env / 'update-ready').exists())

    def test_update_failure_preserves_install(self):
        state = self.home / 'install.json'
        previous = state.read_text()
        data = json.loads(previous)
        data['repository'] = str(self.base / 'missing remote')
        before = snapshot(self.home / 'app')
        state.write_text(json.dumps(data))
        try:
            self.invoke('update', '--remote', '0.4', success=False)
            self.assertEqual(before, snapshot(self.home / 'app'))
            self.assertFalse((self.home / '.install.lock').exists())
        finally:
            state.write_text(previous)

    def test_version_remote_failure(self):
        previous = self.env['AGENTDEV_VERSION_URL']
        self.env['AGENTDEV_VERSION_URL'] = (self.base / 'missing-version').as_uri()
        try:
            result = self.invoke('--v', success=False)
            self.assertIn('本地版本：0.3.0', result.stdout)
            self.assertIn('读取主仓库 publish/version 失败', result.stderr)
        finally:
            self.env['AGENTDEV_VERSION_URL'] = previous

    def test_check_only_update(self):
        before = snapshot(self.home / 'app')
        self.remote_version.write_text('0.4.0\n')
        try:
            self.assertIn('发现远端版本更新', self.invoke('-update', '--check').stdout)
            result = subprocess.run(['sh', str(ROOT / 'update.sh'), '--check'], cwd=self.base, env=self.env, capture_output=True, text=True, check=True)
            self.assertIn('发现远端版本更新', result.stdout)
            self.assertEqual(before, snapshot(self.home / 'app'))
        finally:
            self.remote_version.write_text('0.3\n')

    def test_real_local_update(self):
        self.home = self.base / 'update-install'
        self.env = {**self.env, 'AGENTDEV_HOME': str(self.home)}
        self.run_install_for_update()
        self.py = agentdev.python_exe(self.home)
        self.entry = self.home / 'app/scripts/command/app.py'
        source = self.base / 'remote-source'
        shutil.copytree(self.home / 'app', source)
        (source / 'publish/version').write_text('0.4.0\n')
        subprocess.run(['git', 'init', '-q', '-b', 'master', str(source)], env=self.env, check=True)
        subprocess.run(['git', '-C', str(source), 'add', '.'], env=self.env, check=True)
        subprocess.run(['git', '-C', str(source), '-c', 'commit.gpgSign=false', 'commit', '-qm', '[update] fixture 0.4'], env=self.env, check=True)
        state = json.loads((self.home / 'install.json').read_text())
        state['repository'] = str(source)
        (self.home / 'install.json').write_text(json.dumps(state))
        root = self.project('update project')
        self.invoke('init', cwd=root)
        self.remote_version = self.base / 'new-remote-version'
        self.env['AGENTDEV_VERSION_URL'] = self.remote_version.as_uri()
        self.remote_version.write_text('0.4.0\n')
        text = self.invoke('--u', cwd=root).stdout
        self.assertIn('已更新到 0.4', text)
        self.assertEqual((self.home / 'app/publish/version').read_text().strip(), '0.4.0')
        self.assertEqual((root / 'agent-workspace/.agent/env/agentskill-version').read_text().strip(), '0.4.0')
        self.assertIn('检查通过', self.invoke('check', cwd=root).stdout)

    def run_install_for_update(self):
        result = subprocess.run(['sh', str(self.source / 'setup.sh'), '--no-path'], cwd=self.base,
                                env=self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def test_init_auto_checks(self):
        root = self.project('auto check')
        result = self.invoke('init', cwd=root)
        self.assertIn('检查通过', result.stdout)
        self.assertIn('检查通过', self.invoke('--c', cwd=root).stdout)
        self.assertTrue((root / 'agent-workspace/config/config.json5').exists())
        self.assertFalse((root / 'agent-workspace/config/notes.json5').exists())

    def test_non_git_system_name_and_gitignore(self):
        root = self.project('system user', git_repo=False)
        self.invoke('--i', cwd=root)
        expected = naming.slug(getpass.getuser())
        self.assertTrue((root / 'agent-workspace/workers' / expected / 'specs/constraints.md').is_file())
        self.assertTrue((root / '.gitignore').is_file())
        self.assertIn('/agent-workspace/config/', (root / '.gitignore').read_text())
        self.assertFalse((root / '.git').exists())

    def test_legacy_config_rename_and_no_personal_move(self):
        root = self.project('legacy names')
        config_dir = root / 'agent-workspace/config'
        config_dir.mkdir(parents=True)
        legacy_text = '// keep comment\n{personal: "Old Name", auto_update: false}\n'
        (config_dir / 'notes.json5').write_text(legacy_text)
        self.invoke('init', cwd=root)
        self.assertEqual((config_dir / 'config.json5').read_text(), legacy_text)
        self.assertFalse((config_dir / 'notes.json5').exists())
        old = root / 'agent-workspace/workers/old-name'
        (old / 'notes/keep.md').write_text('USER DATA')
        before = snapshot(old)
        (config_dir / 'config.json5').write_text('{personal:"New Name", auto_update:false}')
        self.invoke('init', cwd=root)
        self.assertEqual(before, snapshot(old))
        self.assertTrue((root / 'agent-workspace/workers/new-name/specs/constraints.md').exists())
        common = root / 'agent-workspace/skills/common'
        result = subprocess.run(['sh', str(common / 'sdd/new_change.sh'), 'Configured Owner'], cwd=root, env=self.env, capture_output=True, text=True, check=True)
        self.assertIn('new-name/change/001-configured-owner', result.stdout)
        result = subprocess.run([str(self.py), '-B', str(common / 'notes/create.py'), 'configured-name'], cwd=root, env=self.env, capture_output=True, text=True, check=True)
        self.assertIn('/new-name/notes/', result.stdout)
        result = subprocess.run([str(self.py), '-B', str(common / 'sdd/check_layout.py'), '--all'], cwd=root, env=self.env, capture_output=True, text=True, check=True)
        self.assertIn('已全部归类', result.stdout)
        self.assertEqual(before, snapshot(old))

    def test_peronsal_alias_and_new_config_priority(self):
        root = self.project('alias personal', git_repo=False)
        config_dir = root / 'agent-workspace/config'
        config_dir.mkdir(parents=True)
        (config_dir / 'config.json5').write_text('{peronsal:"Alias Name",auto_update:false}')
        (config_dir / 'notes.json5').write_text('{personal:"Legacy Ignored"}')
        self.invoke('init', cwd=root)
        self.assertTrue((root / 'agent-workspace/workers/alias-name').is_dir())
        self.assertFalse((root / 'agent-workspace/workers/legacy-ignored').exists())
        self.assertEqual((config_dir / 'notes.json5').read_text(), '{personal:"Legacy Ignored"}')
        (config_dir / 'config.json5').write_text('{personal:"Canonical",peronsal:"Alias Name"}')
        self.invoke('init', cwd=root)
        self.assertTrue((root / 'agent-workspace/workers/canonical').is_dir())
        self.assertTrue((root / 'agent-workspace/workers/alias-name').is_dir())

    def test_invalid_personal(self):
        root = self.project('invalid personal')
        config_dir = root / 'agent-workspace/config'
        config_dir.mkdir(parents=True)
        for name in ('../outside', 'skills', '.', '..', '.agent', 'a/b', 0):
            (config_dir / 'config.json5').write_text(json.dumps({'personal':name}))
            result = self.invoke('init', cwd=root, success=False)
            self.assertIn('personal', result.stderr)
        self.assertFalse((root / 'agent-workspace/.agent').exists())

    def test_source_bash_activation(self):
        command = 'source "$1" --no-path && command -v agentdev && agentdev --h && source "$AGENTDEV_HOME/env" && echo "ACTIVE_PATH=$PATH"'
        result = subprocess.run(['bash', '--noprofile', '--norc', '-c', command, 'fixture', str(self.source / 'setup.sh')], cwd=self.base, env=self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('当前终端生效', result.stdout)
        self.assertIn('version', result.stdout)
        value = result.stdout.split('ACTIVE_PATH=',1)[1].strip()
        self.assertEqual(value.split(os.pathsep).count(str(self.home / 'bin')), 1)

    def test_source_zsh_activation(self):
        zsh = shutil.which('zsh')
        if not zsh:
            self.skipTest('zsh unavailable on host')
        result = subprocess.run([zsh, '-f', '-c', 'source "$1" --no-path && whence agentdev && agentdev --h', 'fixture', str(self.source / 'setup.sh')], cwd=self.base, env=self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('当前终端生效', result.stdout)
        self.assertIn('version', result.stdout)

    def test_source_installed_custom_prefix(self):
        environment = dict(self.env)
        environment.pop('AGENTDEV_HOME')
        result = subprocess.run(['bash', '--noprofile', '--norc', '-c', 'source "$1" --no-path && agentdev --h', 'fixture', str(self.home / 'app/setup.sh')], cwd=self.base, env=environment, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('当前终端生效', result.stdout)


    def test_custom_skills_follow_shared_config(self):
        root = self.project('custom shared config')
        self.invoke('init', cwd=root)
        common = root / 'agent-workspace/skills/common'
        custom = root / 'agent-workspace/skills/custom'
        shutil.copytree(common / 'notes', custom / 'notes')
        shutil.copytree(common / 'sdd', custom / 'sdd')
        (root / 'agent-workspace/config/config.json5').write_text('{personal:"Custom Owner",auto_update:false}')
        result = subprocess.run([str(self.py), '-B', str(custom / 'notes/create.py'), 'custom-shared'], cwd=root, env=self.env, capture_output=True, text=True, check=True)
        self.assertIn('/custom-owner/notes/', result.stdout)
        result = subprocess.run(['sh', str(custom / 'sdd/new_feature.sh'), 'Custom Task'], cwd=root, env=self.env, capture_output=True, text=True, check=True)
        self.assertIn('custom-owner/feature/001-custom-task', result.stdout)
        result = subprocess.run([str(self.py), '-B', str(custom / 'sdd/check_layout.py'), '--all'], cwd=root, env=self.env, capture_output=True, text=True, check=True)
        self.assertIn('已全部归类', result.stdout)

    def test_custom_note_defaults_do_not_change_personal(self):
        root = self.project('note defaults naming')
        self.invoke('init', cwd=root)
        common = root / 'agent-workspace/skills/common'
        custom_notes = root / 'agent-workspace/skills/custom/notes'
        shutil.copytree(common / 'notes', custom_notes)
        defaults = (custom_notes / 'config.json5').read_text().replace('personal: ""', 'personal: "Must Not Override"')
        (custom_notes / 'config.json5').write_text(defaults)
        (root / 'agent-workspace/config/config.json5').write_text('{auto_update:false}')
        result = subprocess.run([str(self.py), '-B', str(custom_notes / 'create.py'), 'shared-default-name'], cwd=root, env=self.env, capture_output=True, text=True, check=True)
        self.assertIn('/fixture-user/notes/', result.stdout)
        self.assertFalse((root / 'agent-workspace/workers/must-not-override').exists())

    def test_retired_url_is_migrated_without_losing_comments(self):
        root = self.project('old remote config')
        self.invoke('init', cwd=root)
        config = root / 'agent-workspace/config/config.json5'
        retired = 'https://api.github.com/repos/LumenVestige/versions/contents/AgentDevWorkSpace/version?ref=main'
        comment = '// update_url: "' + retired + '" (historical comment)'
        text = comment + '\n{update_url:"' + retired + '",personal:"Keep Name",auto_update:false}\n'
        config.write_text(text)
        self.invoke('check', cwd=root)
        self.assertEqual(config.read_text(), text)
        self.invoke('init', cwd=root)
        self.assertIn(comment, config.read_text())
        with patch.dict(os.environ, self.env):
            cfg = naming.load_config(root)
        self.assertEqual(cfg['update_url'], semver.DEFAULT_URL)
        self.assertTrue((root / 'agent-workspace/workers/keep-name').is_dir())

    def test_installer_removes_legacy_launchers(self):
        for relative in ('bin/agentdev.cmd','bin/agentdev.ps1','env.cmd','env.ps1'):
            path = self.home / relative
            path.write_text('old managed launcher')
        self.run_install_for_update()
        for relative in ('bin/agentdev.cmd','bin/agentdev.ps1','env.cmd','env.ps1'):
            self.assertFalse((self.home / relative).exists())


class PlatformHelpers(unittest.TestCase):
    def test_fish_profile_and_activation_files(self):
        with tempfile.TemporaryDirectory(dir=TMP) as temp:
            base = Path(temp)
            agentdev.write_launchers(base)
            with patch.object(Path, 'home', return_value=base), patch.dict(os.environ, {'SHELL':'/usr/bin/fish','XDG_CONFIG_HOME':str(base / '.config')}):
                agentdev.configure_path(base)
                agentdev.configure_path(base)
            profile = (base / '.config/fish/config.fish').read_text()
            self.assertEqual(profile.count('# >>> agentdev PATH >>>'), 1)
            self.assertIn('env.fish', profile)
            self.assertIn('contains --', (base / 'env.fish').read_text())
            self.assertFalse((base / 'env.ps1').exists())
            self.assertFalse((base / 'env.cmd').exists())


    def test_detached_background_process_options(self):
        with tempfile.TemporaryDirectory(dir=TMP) as temp:
            env = Path(temp)
            common = types.ModuleType('common')
            common.ENV = env
            for name in ('load_config', 'project_root', 'python_path', 'skill_dir', 'update_stamp_file'):
                setattr(common, name, Mock(return_value=env))
            spec = importlib.util.spec_from_file_location('updater_fixture', ROOT / 'skills/notes/update.py')
            module = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {'common': common}):
                spec.loader.exec_module(module)
            with patch.object(module.subprocess, 'Popen') as popen:
                module.spawn('--run')
                self.assertTrue(popen.call_args.kwargs['start_new_session'])

    def test_no_symlink_permission(self):
        with tempfile.TemporaryDirectory(dir=TMP) as temp:
            base = Path(temp)
            source, target = base / 'source', base / 'target'
            source.mkdir()
            (source / 'file').write_text('one')
            managed = {}
            with patch.object(Path, 'symlink_to', side_effect=PermissionError('link fixture')):
                workspace.link_or_copy(target, source, managed)
                self.assertEqual((target / 'file').read_text(), 'one')
                (source / 'file').write_text('two')
                workspace.link_or_copy(target, source, managed)
                self.assertEqual((target / 'file').read_text(), 'two')
                (target / 'file').write_text('user custom')
                workspace.link_or_copy(target, source, managed)
                self.assertEqual((target / 'file').read_text(), 'user custom')

    def test_profile_idempotence_without_real_home(self):
        with tempfile.TemporaryDirectory(dir=TMP) as temp:
            base = Path(temp)
            with patch.object(Path, 'home', return_value=base), patch.dict(os.environ, {'SHELL': '/bin/zsh'}):
                agentdev.configure_path(base / 'global')
                agentdev.configure_path(base / 'global')
            self.assertEqual((base / '.zshrc').read_text().count('# >>> agentdev PATH >>>'), 1)

    def test_install_lock(self):
        with tempfile.TemporaryDirectory(dir=TMP) as temp:
            home = Path(temp)
            with agentdev.installation_lock(home):
                with self.assertRaises(RuntimeError):
                    with agentdev.installation_lock(home):
                        pass
            self.assertFalse((home / '.install.lock').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
