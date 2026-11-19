"""实际遗留 Note 命名、分类及重跑迁移的回归。"""
import sys
from support import ROOT, Sandbox, snapshot


class LegacyFormats(Sandbox):
    def setUp(self):
        super().setUp()
        self.root = self.make_project()
        self.notes = self.root / 'agent-workspace/workers/test-owner/notes'
        self.notes.mkdir(parents=True)

    def write(self, name, text):
        path = self.notes / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text)
        return path

    def fix(self):
        return self.run_command([sys.executable, ROOT / 'scripts/command/app.py', 'fix', self.root])

    def test_date_only_files_and_directories_go_to_large_change(self):
        self.write('26-11-15-topic.md', b'# Analysis\r\n')
        self.write('26-11-15-evidence/summary.md', b'# Outcome\n')
        self.write('26-11-15-evidence/deep/raw.bin', b'\x00\xff')
        self.fix()
        day = self.notes / 'large-scale-file-change/2026-11-15'
        self.assertEqual((day / 'topic.md').read_bytes(), b'# Analysis\r\n')
        self.assertEqual((day / 'evidence/deep/raw.bin').read_bytes(), b'\x00\xff')
        self.assertFalse((self.notes / '26-11-15-evidence').exists())
        before = snapshot(self.root)
        self.fix()
        self.assertEqual(snapshot(self.root), before)

    def test_classify_actual_commits_not_template_or_evidence_hashes(self):
        for name, text in {
            '26-11-15-10-00-00-commit.md': b'## Git \xe6\x8f\x90\xe4\xba\xa4\n\n```\nabcdef0 [fix] real commit\n```\n',
            '26-11-15-10-00-01-empty.md': '## Git 提交\n本轮没有提交；旧 abcdef0 不是本轮记录。\n'.encode(),
            '26-11-15-10-00-02-sha.md': b'SHA-256: '+b'a'*64+b'\n',
            '2026-11-15-10-00-03-full-year.md': b'# Outcome\n',
        }.items():
            self.write(name, text)
        self.fix()
        self.assertTrue((self.notes / 'git-commit-change/2026-11-15/10-00-00-commit.md').is_file())
        for name in ('10-00-01-empty.md', '10-00-02-sha.md', '10-00-03-full-year.md'):
            self.assertTrue((self.notes / 'large-scale-file-change/2026-11-15' / name).is_file())

    def test_repair_previously_misclassified_files_and_preserve_conflicts(self):
        self.write('git-commit-change/2026-11-15/10-00-00-plain.md', b'# plain\r\n')
        old = self.write('git-commit-change/2026-11-15/10-00-01-conflict.md', b'# old')
        target = self.write('large-scale-file-change/2026-11-15/10-00-01-conflict.md', b'# existing')
        result = self.fix()
        self.assertFalse((old.parent / '10-00-00-plain.md').exists())
        self.assertEqual((target.parent / '10-00-00-plain.md').read_bytes(), b'# plain\r\n')
        self.assertEqual(old.read_bytes(), b'# old')
        self.assertEqual(target.read_bytes(), b'# existing')
        self.assertIn('目标已存在跳过 1 个', result.stdout)
        self.assertNotIn('conflict.md', result.stdout)

    def test_duplicate_notes_and_merged_directories_remove_old_sources(self):
        self.write('26-11-15-topic.md', b'# Outcome\r\n')
        target = self.write('large-scale-file-change/2026-11-15/topic.md', b'# Outcome\r\n')
        self.write('26-11-15-evidence/summary.md', b'# Outcome\n')
        self.write('26-11-15-evidence/deep/raw.bin', b'\x00\xff')
        self.write('26-11-15-evidence/extra.md', b'extra')
        self.write('large-scale-file-change/2026-11-15/evidence/summary.md', b'# Outcome\n')
        self.write('large-scale-file-change/2026-11-15/evidence/deep/raw.bin', b'\x00\xff')
        self.write('large-scale-file-change/2026-11-15/evidence/target-only.md', b'keep')
        result = self.fix()
        self.assertIn('已迁移 2 个', result.stdout)
        self.assertIn('跳过 0 个', result.stdout)
        self.assertNotIn('26-11-15-', result.stdout)
        self.assertFalse((self.notes / '26-11-15-topic.md').exists())
        self.assertFalse((self.notes / '26-11-15-evidence').exists())
        self.assertEqual(target.read_bytes(), b'# Outcome\r\n')
        self.assertEqual((target.parent / 'evidence/deep/raw.bin').read_bytes(), b'\x00\xff')
        self.assertEqual((target.parent / 'evidence/extra.md').read_bytes(), b'extra')
        self.assertEqual((target.parent / 'evidence/target-only.md').read_bytes(), b'keep')
        before = snapshot(self.root)
        self.fix()
        self.assertEqual(snapshot(self.root), before)
        result = self.run_command([sys.executable, ROOT / 'scripts/command/app.py', 'check', self.root], success=False)
        self.assertNotIn('待迁移', result.stdout)

    def test_partial_note_conflicts_preserve_differences_and_clean_duplicates(self):
        source = self.write('26-11-15-evidence/summary.md', b'# old')
        target = self.write('large-scale-file-change/2026-11-15/evidence/summary.md', b'# new')
        self.write('26-11-15-evidence/same.bin', b'\x00same')
        self.write('large-scale-file-change/2026-11-15/evidence/same.bin', b'\x00same')
        self.write('26-11-15-evidence/extra.bin', b'extra')
        result = self.fix()
        self.assertIn('跳过 1 个', result.stdout)
        self.assertNotIn('evidence', result.stdout)
        self.assertEqual(source.read_bytes(), b'# old')
        self.assertEqual(target.read_bytes(), b'# new')
        self.assertEqual(list(source.parent.iterdir()), [source])
        self.assertEqual((target.parent / 'extra.bin').read_bytes(), b'extra')

    def test_note_merge_preserves_symlinks_and_their_targets(self):
        for name in ('target-file', 'target-dir', 'dangling', 'source-link'):
            self.write(f'26-11-15-{name}/summary.md', b'# Outcome')
        external = self.base / 'outside'
        external.mkdir()
        (external / 'summary.md').write_bytes(b'# Outcome')
        day = self.notes / 'large-scale-file-change/2026-11-15'
        day.mkdir(parents=True)
        (day / 'target-file').mkdir()
        (day / 'target-file/summary.md').symlink_to(external / 'summary.md')
        (day / 'target-dir').symlink_to(external, target_is_directory=True)
        (day / 'dangling').symlink_to(external / 'missing', target_is_directory=True)
        self.write('large-scale-file-change/2026-11-15/source-link/summary.md', b'# Outcome')
        link = self.notes / '26-11-15-source-link/link.bin'
        link.symlink_to(external / 'summary.md')
        before = snapshot(external)
        result = self.fix()
        self.assertIn('跳过 4 个', result.stdout)
        for name in ('target-file', 'target-dir', 'dangling'):
            self.assertTrue((self.notes / f'26-11-15-{name}/summary.md').is_file())
        self.assertTrue(link.is_symlink())
        self.assertTrue((day / 'target-file/summary.md').is_symlink())
        self.assertTrue((day / 'target-dir').is_symlink())
        self.assertTrue((day / 'dangling').is_symlink())
        self.assertEqual(snapshot(external), before)

    def test_note_file_directory_collisions_are_not_deleted(self):
        self.write('26-11-15-file.md', b'# source file')
        self.write('large-scale-file-change/2026-11-15/file.md/summary.md', b'# target directory')
        self.write('26-11-15-directory/summary.md', b'# source directory')
        self.write('large-scale-file-change/2026-11-15/directory', b'# target file')
        before = snapshot(self.root)
        result = self.fix()
        self.assertIn('跳过 2 个', result.stdout)
        self.assertEqual(snapshot(self.root), before)

    def test_invalid_dates_unrelated_and_symlinks_remain_untouched(self):
        self.write('26-02-30-invalid.md', b'invalid')
        self.write('README.md', b'readme')
        external = self.base / 'outside'
        external.mkdir()
        (external / 'note.md').write_text('outside')
        (self.notes / '26-11-15-symlink').symlink_to(external, target_is_directory=True)
        (self.notes / 'large-scale-file-change').symlink_to(external, target_is_directory=True)
        self.write('26-11-15-topic.md', b'preserve')
        before = snapshot(self.base)
        self.fix()
        self.assertEqual(snapshot(self.base), before)

    def test_commit_topic_directory_and_dangerous_suffix(self):
        text = '## Git 提交\n- `abcdef0` [fix] recorded\n'.encode()
        self.write('26-11-15-committed/summary.md', text)
        self.write('26-11-15-committed/evidence/raw.bin', b'payload')
        self.write('26-11-15-../summary.md', b'keep unsafe suffix')
        self.fix()
        target = self.notes / 'git-commit-change/2026-11-15/committed'
        self.assertEqual((target / 'summary.md').read_bytes(), text)
        self.assertEqual((target / 'evidence/raw.bin').read_bytes(), b'payload')
        self.assertTrue((self.notes / '26-11-15-../summary.md').exists())

    def test_check_readonly_detection_matches_new_note_formats_and_wrong_types(self):
        self.write('26-11-15-no-time/summary.md', b'# Outcome')
        self.write('git-commit-change/2026-11-15/10-00-00-wrong.md', b'# Outcome')
        before = snapshot(self.root)
        result = self.run_command([sys.executable, ROOT / 'scripts/command/app.py', 'check', self.root], success=False)
        self.assertEqual(result.stdout.count('历史 personal / Note 待迁移'), 1)
        self.assertIn('agentdev fix', result.stdout)
        self.assertNotIn('26-11-15-no-time', result.stdout)
        self.assertNotIn('10-00-00-wrong.md', result.stdout)
        self.assertEqual(snapshot(self.root), before)
        self.fix()
        result = self.run_command([sys.executable, ROOT / 'scripts/command/app.py', 'check', self.root], success=False)
        self.assertNotIn('待迁移', result.stdout)

    def test_check_summarizes_many_legacy_notes_and_personal_directories(self):
        legacy = self.root / 'agent-workspace/legacy-owner/notes'
        legacy.mkdir(parents=True)
        for index in range(100):
            (legacy / f'26-11-15-10-00-00-topic-{index}.md').write_text('# Outcome')
        before = snapshot(self.root)
        result = self.run_command([sys.executable, ROOT / 'scripts/command/app.py', 'check', self.root], success=False)
        self.assertEqual(result.stdout.count('历史 personal / Note 待迁移'), 1)
        self.assertEqual(result.stdout.count('agentdev fix'), 1)
        self.assertNotIn('legacy-owner', result.stdout)
        self.assertNotIn('topic-', result.stdout)
        self.assertEqual(snapshot(self.root), before)
