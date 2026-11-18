"""archive 命令的隔离验收，默认值、分组、安全性及 SDD 历史兼容。"""
import json
import sys
from support import ROOT, Sandbox, snapshot

KINDS = ('feature', 'bugfix', 'change', 'research', 'notes/git-commit-change', 'notes/large-scale-file-change')


class ArchiveCommand(Sandbox):
    def setUp(self):
        super().setUp()
        self.root = self.make_project()
        self.personal = self.root / 'agent-workspace/workers/test-owner'
        self.config = self.root / 'agent-workspace/config/config.json5'

    def configure(self, **archive):
        self.config.write_text(json.dumps({'personal': 'Test Owner', 'archive': archive}))

    def entries(self, kind='feature', count=5):
        base = self.personal / kind
        base.mkdir(parents=True, exist_ok=True)
        for n in range(1, count + 1):
            path = base / f'{n:03d}-topic'
            if n % 2:
                path.mkdir(exist_ok=True)
                (path / 'spec.md').write_text(f'DATA {n}')
            else:
                path.write_text(f'DATA {n}')
        return base

    def archive(self, *args, success=True):
        return self.run_command([sys.executable, ROOT / 'scripts/command/app.py', 'archive', *args], cwd=self.root, success=success)

    def test_all_six_types_keep_newest_and_group_oldest(self):
        self.configure(threshold=2, group_size=2)
        for kind in KINDS:
            self.entries(kind)
        out = self.archive().stdout
        self.assertIn('18', out)
        for kind in KINDS:
            base = self.personal / kind
            self.assertEqual(sorted(p.name for p in base.iterdir()), ['004-topic', '005-topic', 'archived'])
            self.assertEqual(sorted(p.name for p in (base / 'archived/01').iterdir()), ['001-topic', '002-topic'])
            self.assertEqual((base / 'archived/01/001-topic/spec.md').read_text(), 'DATA 1')
            self.assertEqual((base / 'archived/02/003-topic/spec.md').read_text(), 'DATA 3')
        before = snapshot(self.root)
        self.archive()
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse((self.base / 'global 安装').exists())

    def test_default_threshold_and_group_size_and_boundary(self):
        base = self.entries(count=50)
        self.archive()
        self.assertFalse((base / 'archived').exists())
        self.entries(count=151)
        self.archive(self.root)
        self.assertEqual(len(list((base / 'archived/01').iterdir())), 100)
        self.assertEqual(len(list((base / 'archived/02').iterdir())), 1)
        self.assertEqual(len(list(base.iterdir())), 51)

    def test_partial_settings_and_refill_last_batch(self):
        self.configure(threshold=1)
        base = self.entries(count=3)
        self.archive()
        self.entries(count=5)
        # Remove recreated already-archived entries; add only genuine new entries.
        import shutil
        shutil.rmtree(base / '001-topic')
        (base / '002-topic').unlink()
        self.archive()
        self.assertEqual(len(list((base / 'archived/01').iterdir())), 4)
        self.assertFalse((base / 'archived/02').exists())

    def test_conflict_other_users_and_symlink_paths_are_preserved(self):
        self.configure(threshold=1, group_size=3)
        base = self.entries(count=3)
        target = base / 'archived/01/001-topic'
        target.parent.mkdir(parents=True)
        target.write_text('existing')
        other = self.root / 'agent-workspace/workers/other/feature'
        other.mkdir(parents=True)
        (other / '001-private').write_text('private')
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / '001-external').write_text('external')
        (self.personal / 'bugfix').symlink_to(outside, target_is_directory=True)
        result = self.archive()
        self.assertIn('跳过', result.stdout)
        self.assertEqual(target.read_text(), 'existing')
        self.assertTrue((base / '001-topic').is_dir())
        self.assertEqual((outside / '001-external').read_text(), 'external')
        self.assertTrue((other / '001-private').exists())

    def test_unsafe_archive_target_does_not_write_outside(self):
        self.configure(threshold=1)
        base = self.entries(count=3)
        outside = self.base / 'outside'
        outside.mkdir()
        (base / 'archived').symlink_to(outside, target_is_directory=True)
        before = snapshot(self.base)
        self.archive()
        self.assertEqual(snapshot(self.base), before)

    def test_invalid_settings_fail_before_moves(self):
        self.entries()
        for value in (None, [], {'threshold': 0}, {'threshold': True}, {'group_size': -1}, {'group_size': 1.5}):
            with self.subTest(value=value):
                self.config.write_text(json.dumps({'personal': 'Test Owner', 'archive': value}))
                before = snapshot(self.root)
                self.assertIn('archive', self.archive(success=False).stderr)
                self.assertEqual(snapshot(self.root), before)

    def test_missing_workspace_fails_and_empty_workspace_noops(self):
        self.assertIn('不是 agent-workspace', self.archive(self.base, success=False).stderr)
        before = snapshot(self.root)
        self.archive()
        self.assertEqual(snapshot(self.root), before)

    def test_aliases_help_and_legacy_personal(self):
        self.assertIn('archive', self.run_command([ROOT / 'adev', 'help']).stdout)
        self.config.write_text('{peronsal:"Test Owner",archive:{threshold:1,group_size:2}}')
        base = self.entries(count=3)
        self.run_command([ROOT / 'adev', '--a', self.root])
        self.assertTrue((base / 'archived/01/001-topic').exists())
        self.run_command([sys.executable, ROOT / 'scripts/command/app.py', '-archive', self.root])

    def test_archived_numbering_duplicate_detection_layout_and_search(self):
        self.configure(threshold=1, group_size=100)
        base = self.personal / 'feature'
        for number, slug in ((8, 'old'), (9, 'latest')):
            req = base / f'{number:03d}-{slug}'
            req.mkdir(parents=True)
            (req / 'spec.md').write_text(f'# Search unique-history\n类型：feature | 编号：{number:03d}\n')
        self.archive()
        script = self.root / 'agent-workspace/skills/common/sdd/new.sh'
        result = self.run_command(['sh', script, 'feature', 'new'], cwd=self.root)
        self.assertTrue(result.stdout.strip().endswith('010-new'))
        duplicate = self.run_command(['sh', script, 'feature', 'old'], cwd=self.root, success=False)
        self.assertIn('archived/01/008-old', duplicate.stderr)
        moved = base / 'archived/01/008-old'
        (moved / 'loose.log').write_text('not classified')
        result = self.skill(self.root, 'sdd/check_layout.py', '--all', success=False)
        self.assertIn('archived/01/008-old', result.stderr)
        self.assertIn('loose.log', result.stderr)
        (moved / 'loose.log').unlink()
        self.skill(self.root, 'sdd/check_layout.py', '--all')
        output = self.run_command(['sh', self.root / 'agent-workspace/skills/common/knowledge/search.sh', 'unique-history'], cwd=self.root).stdout
        self.assertIn('archived/01/008-old/spec.md', output)
        self.assertIn('编号：008', output)

    def test_archived_notes_still_record_hashes_and_are_searchable(self):
        self.configure(threshold=1, group_size=2)
        base = self.personal / 'notes/git-commit-change'
        for day in ('2026-11-16', '2026-11-17'):
            folder = base / day
            folder.mkdir(parents=True)
            (folder / '00-00-00-note.md').write_text('## Git 提交\nabcdef0 [fix] archived-note-evidence\n')
        self.archive()
        output = self.run_command(['sh', self.root / 'agent-workspace/skills/common/knowledge/search.sh', 'archived-note-evidence'], cwd=self.root).stdout
        self.assertIn('archived/01/2026-11-16/00-00-00-note.md', output)
        result = self.run_command([sys.executable, '-B', '-c',
            'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); '
            'from common import recorded_hashes; print(recorded_hashes(Path(sys.argv[2])))',
            self.root / 'agent-workspace/skills/common/notes', self.root])
        self.assertIn('abcdef0', result.stdout)

    def test_archived_highest_number_not_reused_when_active_requirements_removed(self):
        path = self.personal / 'change/archived/01/099-history'
        path.mkdir(parents=True)
        script = self.root / 'agent-workspace/skills/common/sdd/new.sh'
        result = self.run_command(['sh', script, 'change', 'next'], cwd=self.root)
        self.assertTrue(result.stdout.strip().endswith('100-next'))

    def test_archive_file_and_batch_symlinks_do_not_modify_sources(self):
        self.configure(threshold=1, group_size=1)
        base = self.entries(count=3)
        outside = self.base / 'outside'
        outside.mkdir()
        (base / 'archived').mkdir()
        (base / 'archived/01').symlink_to(outside, target_is_directory=True)
        (base / '999-link').symlink_to(outside, target_is_directory=True)
        before = snapshot(self.base)
        self.archive()
        self.assertEqual(snapshot(self.base), before)

    def test_archive_does_not_implicitly_migrate_legacy_workers(self):
        self.configure(threshold=1)
        self.entries(count=3)
        legacy = self.root / 'agent-workspace/test-owner/feature'
        legacy.mkdir(parents=True)
        (legacy / '001-old').write_text('legacy')
        self.archive()
        self.assertEqual((legacy / '001-old').read_text(), 'legacy')
        self.assertFalse((legacy / 'archived').exists())
