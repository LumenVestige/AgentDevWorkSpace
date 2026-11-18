"""独立 fix 命令及旧版 Note 迁移的隔离回归测试，不安装全局环境。"""
from pathlib import Path
import sys
import unittest

from support import ROOT, Sandbox, snapshot


class FixCommandTests(Sandbox):
    def invoke(self, *args, cwd=None, success=True):
        return self.run_command([sys.executable, '-B', ROOT / 'scripts/command/app.py', *args],
                                cwd=cwd, success=success)

    def legacy_note(self, root, name='26-11-17-10-20-30-topic.md', user='test-owner', content=b'# Note\r\n## Git \xe6\x8f\x90\xe4\xba\xa4\n```\nabcdef0 [fix] recorded\n```\n'):
        path = root / 'agent-workspace' / user / 'notes' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_migration_preserves_content_and_is_idempotent(self):
        root = self.make_project()
        source = self.legacy_note(root)
        target = source.parent / 'git-commit-change/2026-11-17/10-20-30-topic.md'
        result = self.invoke('fix', cwd=root)
        self.assertIn('已迁移 1 个', result.stdout)
        self.assertFalse(source.exists())
        self.assertEqual(target.read_bytes(), b'# Note\r\n## Git \xe6\x8f\x90\xe4\xba\xa4\n```\nabcdef0 [fix] recorded\n```\n')
        before = snapshot(root)
        self.assertIn('已迁移 0 个', self.invoke('fix', cwd=root).stdout)
        self.assertEqual(snapshot(root), before)
        self.assertFalse(Path(self.env['AGENTDEV_HOME']).exists())

    def test_explicit_directory_and_aliases(self):
        root = self.make_project(git=False)
        for alias in ('fix', '--f', '-fix'):
            with self.subTest(alias=alias):
                source = self.legacy_note(root)
                self.assertIn('已迁移 1 个', self.invoke(alias, root).stdout)
                target = source.parent / 'git-commit-change/2026-11-17/10-20-30-topic.md'
                self.assertEqual(target.read_bytes(), b'# Note\r\n## Git \xe6\x8f\x90\xe4\xba\xa4\n```\nabcdef0 [fix] recorded\n```\n')
                target.unlink()
        source = self.legacy_note(root)
        result = self.run_command([ROOT / 'adev', 'fix', root])
        self.assertIn('已迁移 1 个', result.stdout)
        self.assertFalse(source.exists())

    def test_conflicts_unrelated_notes_and_other_users_are_preserved(self):
        root = self.make_project()
        source = self.legacy_note(root)
        target = source.parent / 'git-commit-change/2026-11-17/10-20-30-topic.md'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'## Git \xe6\x8f\x90\xe4\xba\xa4\nabcdef0 [fix] existing target\n')
        self.legacy_note(root, name='README.md')
        self.legacy_note(root, user='other-user')
        self.legacy_note(root, name='undated-new-format.md')
        (source.parent / 'undated-directory').mkdir()
        before = snapshot(root)
        result = self.invoke('fix', root)
        self.assertIn('目标已存在跳过 1 个', result.stdout)
        self.assertEqual(snapshot(root), before)

    def test_missing_notes_is_successful_noop(self):
        root = self.make_project()
        before = snapshot(root)
        self.assertIn('已迁移 0 个', self.invoke('fix', root).stdout)
        self.assertEqual(snapshot(root), before)

    def test_legacy_personal_setting(self):
        root = self.make_project()
        (root / 'agent-workspace/config/config.json5').write_text('{peronsal: "Legacy Owner"}')
        source = self.legacy_note(root, user='legacy-owner')
        self.assertIn('已迁移 1 个', self.invoke('fix', root).stdout)
        self.assertFalse(source.exists())

    def test_default_personal_uses_git_user(self):
        root = self.make_project()
        (root / 'agent-workspace/config/config.json5').write_text('{personal: ""}')
        source = self.legacy_note(root, user='fixture-user')
        self.assertIn('已迁移 1 个', self.invoke('fix', root).stdout)
        self.assertFalse(source.exists())

    def test_invalid_directory_and_workspace_fail_without_writes(self):
        for root, message in ((self.base / 'missing', '项目目录不存在'),
                              (self.base, '不是 agent-workspace 工作区')):
            with self.subTest(root=root):
                before = snapshot(self.base)
                result = self.invoke('fix', root, success=False)
                self.assertIn(message, result.stderr)
                self.assertEqual(snapshot(self.base), before)

    def test_invalid_config_does_not_move_notes(self):
        root = self.make_project()
        self.legacy_note(root)
        (root / 'agent-workspace/config/config.json5').write_text('{broken')
        before = snapshot(root)
        self.invoke('fix', root, success=False)
        self.assertEqual(snapshot(root), before)

    def test_old_python_and_shell_entrypoints_still_work(self):
        root = self.make_project()
        for entry in ([sys.executable, ROOT / 'scripts/lib/fix.py'],
                      ['sh', ROOT / 'scripts/lib/fix.sh']):
            with self.subTest(entry=entry):
                source = self.legacy_note(root)
                result = self.run_command([*entry, root])
                self.assertIn('已迁移 1 个', result.stdout)
                self.assertFalse(source.exists())
                (source.parent / 'git-commit-change/2026-11-17/10-20-30-topic.md').unlink()

    def test_help_exposes_fix_and_directory_argument(self):
        self.assertIn('fix / --f', self.invoke('help').stdout)
        result = self.invoke('fix', '--help')
        self.assertIn('[directory]', result.stdout)
        self.assertIn('旧版 notes', result.stdout)


if __name__ == '__main__':
    unittest.main()
