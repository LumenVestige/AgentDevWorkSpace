"""独立 fix 命令及旧版 Note 迁移的隔离回归测试，不安装全局环境。"""
from pathlib import Path
import sys
import unittest

from support import ROOT, Sandbox, snapshot


class FixCommandTests(Sandbox):
    def test_moves_all_legacy_workers_and_repairs_shared_constraint_links(self):
        root = self.make_project()
        for user in ('tony', 'sanyinchen'):
            folder = root / 'agent-workspace' / user / 'change/001-example'
            folder.mkdir(parents=True)
            (folder / 'spec.md').write_bytes(b'[constraints](../../../skills/common/sdd/constraints.md)\r\n')
            (folder / 'data.bin').write_bytes(b'\x00user-data')
        self.invoke('fix', root)
        for user in ('tony', 'sanyinchen'):
            self.assertFalse((root / 'agent-workspace' / user).exists())
            folder = root / 'agent-workspace/workers' / user / 'change/001-example'
            self.assertEqual((folder / 'data.bin').read_bytes(), b'\x00user-data')
            self.assertEqual((folder / 'spec.md').read_bytes(),
                             b'[constraints](../../../../skills/common/sdd/constraints.md)\r\n')
        before = snapshot(root)
        self.invoke('fix', root)
        self.assertEqual(snapshot(root), before)

    def test_worker_conflicts_keep_both_versions_and_move_nonconflicting_files(self):
        root = self.make_project()
        old = root / 'agent-workspace/test-owner/notes'
        new = root / 'agent-workspace/workers/test-owner/notes'
        old.mkdir(parents=True)
        new.mkdir(parents=True)
        (old / 'same.md').write_text('OLD')
        (new / 'same.md').write_text('NEW')
        (old / 'extra.md').write_text('EXTRA')
        result = self.invoke('fix', root, success=False)
        self.assertIn('冲突', result.stdout + result.stderr)
        self.assertEqual((old / 'same.md').read_text(), 'OLD')
        self.assertEqual((new / 'same.md').read_text(), 'NEW')
        self.assertEqual((new / 'extra.md').read_text(), 'EXTRA')
        self.assertNotIn('same.md', result.stdout + result.stderr)

    def test_duplicate_worker_files_are_removed_after_link_normalization(self):
        root = self.make_project()
        old = root / 'agent-workspace/test-owner/change/001-example'
        new = root / 'agent-workspace/workers/test-owner/change/001-example'
        old.mkdir(parents=True)
        new.mkdir(parents=True)
        (old / 'spec.md').write_bytes(b'[rules](../../../skills/common/sdd/constraints.md)\r\n')
        (new / 'spec.md').write_bytes(b'[rules](../../../../skills/common/sdd/constraints.md)\r\n')
        for folder in (old, new):
            (folder / 'data.bin').write_bytes(b'\x00\xff')
        before = snapshot(new)
        result = self.invoke('fix', root)
        self.assertIn('冲突 0 项', result.stdout)
        self.assertFalse((root / 'agent-workspace/test-owner').exists())
        self.assertEqual(snapshot(new), before)
        before = snapshot(root)
        self.invoke('fix', root)
        self.assertEqual(snapshot(root), before)

    def test_identical_link_text_with_different_targets_is_not_deleted(self):
        root = self.make_project()
        old = root / 'agent-workspace/test-owner/change/001-example/spec.md'
        new = root / 'agent-workspace/workers/test-owner/change/001-example/spec.md'
        for path in (old, new):
            path.parent.mkdir(parents=True)
            path.write_bytes(b'[rules](../../../skills/common/sdd/constraints.md)\r\n')
        before = snapshot(root)
        self.invoke('fix', root, success=False)
        self.assertEqual(snapshot(root), before)

    def test_workers_symlink_is_rejected_without_touching_its_target(self):
        root = self.make_project()
        self.legacy_note(root)
        outside = self.base / 'unrelated'
        outside.mkdir()
        (root / 'agent-workspace/workers').symlink_to(outside, target_is_directory=True)
        before = snapshot(root)
        self.invoke('fix', root, success=False)
        self.assertEqual(snapshot(root), before)
        self.assertEqual(list(outside.iterdir()), [])

    def test_check_reports_pending_personal_and_notes_migrations_read_only(self):
        root = self.make_project()
        self.legacy_note(root)
        current = root / 'agent-workspace/workers/other/notes'
        current.mkdir(parents=True)
        (current / '26-11-17-10-20-31-other.md').write_text('OTHER NOTE')
        before = snapshot(root)
        result = self.invoke('check', root, success=False)
        self.assertIn('agentdev fix', result.stdout)
        self.assertIn('personal', result.stdout)
        self.assertIn('Note', result.stdout)
        self.assertEqual(snapshot(root), before)
        self.invoke('fix', root)
        self.assertTrue((current / 'large-scale-file-change/2026-11-17/10-20-31-other.md').is_file())
        result = self.invoke('check', root, success=False)  # Fixture intentionally lacks hooks.
        self.assertNotIn('agentdev fix', result.stdout)

    def invoke(self, *args, cwd=None, success=True):
        return self.run_command([sys.executable, '-B', ROOT / 'scripts/command/app.py', *args],
                                cwd=cwd, success=success)

    def legacy_note(self, root, name='26-11-17-10-20-30-topic.md', user='test-owner', content=b'# Note\r\n'):
        path = root / 'agent-workspace' / user / 'notes' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def target_note(self, root):
        return root / 'agent-workspace/workers/test-owner/notes/large-scale-file-change/2026-11-17/10-20-30-topic.md'

    def test_migration_preserves_content_and_is_idempotent(self):
        root = self.make_project()
        source = self.legacy_note(root)
        target = self.target_note(root)
        result = self.invoke('fix', cwd=root)
        self.assertIn('已迁移 1 个', result.stdout)
        self.assertFalse(source.exists())
        self.assertEqual(target.read_bytes(), b'# Note\r\n')
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
                target = self.target_note(root)
                self.assertEqual(target.read_bytes(), b'# Note\r\n')
                target.unlink()
        source = self.legacy_note(root)
        result = self.run_command([ROOT / 'adev', 'fix', root])
        self.assertIn('已迁移 1 个', result.stdout)
        self.assertFalse(source.exists())

    def test_conflicts_and_unrelated_notes_are_preserved(self):
        root = self.make_project()
        source = self.legacy_note(root)
        target = self.target_note(root)
        target.parent.mkdir(parents=True)
        target.write_bytes(b'existing target')
        self.legacy_note(root, name='README.md')
        self.legacy_note(root, name='undated-new-format.md')
        (source.parent / 'undated-directory').mkdir()
        result = self.invoke('fix', root)
        self.assertIn('目标已存在跳过 1 个', result.stdout)
        notes = root / 'agent-workspace/workers/test-owner/notes'
        self.assertEqual((notes / source.name).read_bytes(), b'# Note\r\n')
        self.assertEqual(target.read_bytes(), b'existing target')
        self.assertTrue((notes / 'README.md').exists())
        self.assertTrue((notes / 'undated-new-format.md').exists())
        before = snapshot(root)
        self.invoke('fix', root)
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
                self.target_note(root).unlink()

    def test_help_exposes_fix_and_directory_argument(self):
        self.assertIn('fix / --f', self.invoke('help').stdout)
        result = self.invoke('fix', '--help')
        self.assertIn('[directory]', result.stdout)
        self.assertIn('旧版 notes', result.stdout)


if __name__ == '__main__':
    unittest.main()
