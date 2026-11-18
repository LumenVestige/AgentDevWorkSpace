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
        self.assertIn('conflict.md', result.stdout)

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
        self.assertIn('26-11-15-no-time', result.stdout)
        self.assertIn('10-00-00-wrong.md', result.stdout)
        self.assertEqual(snapshot(self.root), before)
        self.fix()
        result = self.run_command([sys.executable, ROOT / 'scripts/command/app.py', 'check', self.root], success=False)
        self.assertNotIn('历史 Note 待迁移', result.stdout)
