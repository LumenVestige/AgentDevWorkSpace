"""Note scanning, creation, threshold accounting and lossless merging."""
import json
import os
from unittest.mock import patch

from support import Sandbox, snapshot
from lib.fix import fix_notes


class Notes(Sandbox):
    def setUp(self):
        super().setUp()
        self.root = self.make_project()
        self.config = self.root / "agent-workspace/config/config.json5"
        self.notes = self.root / "agent-workspace/test-owner/notes"
        self.state = self.root / "agent-workspace/.agent/env"

    def configure(self, **settings):
        self.config.write_text(json.dumps({"personal":"Test Owner", "auto_update":False, **settings}))

    def verify(self, *, success=True, active=False):
        return self.skill(self.root, "notes/verify.py", success=success,
                          input=json.dumps({"stop_hook_active":active}))

    def test_pending_commit_recorded_then_baseline_advanced(self):
        commit = self.commit_file(self.root, "src/main.txt", "NEW\n")
        result = self.verify(success=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("1 笔提交", result.stderr)
        result = self.skill(self.root, "notes/create.py", "record-commit")
        from pathlib import Path
        path = Path(result.stdout.strip())
        self.assertIn(commit[:7], path.read_text())
        self.assertIn("## Git 提交", path.read_text())
        self.assertNotIn("## 文件改动", path.read_text())
        self.verify()
        self.assertEqual((self.state / "note-base").read_text().strip(), commit)

    def test_pending_commit_reports_without_repeated_hook_block(self):
        self.commit_file(self.root, "main.txt", "NEW")
        self.verify(success=False)
        self.assertIn("尚未记录", self.verify(active=True).stderr)

    def test_commit_recorded_by_another_person_is_recognized(self):
        commit = self.commit_file(self.root, "main.txt", "NEW")
        path = self.root / "agent-workspace/another/notes/git-commit-change/2026-01-01/00-00-00-record.md"
        path.parent.mkdir(parents=True)
        path.write_text("# Record\n\n" + commit[:9])
        self.verify()

    def test_note_only_commit_does_not_request_another_note(self):
        commit = self.commit_file(self.root, "main.txt", "BASE")
        (self.state / "note-base").write_text(commit)
        self.commit_file(self.root, "agent-workspace/test-owner/notes/git-commit-change/2026-01-01/00-00-00-note.md", "# Record")
        self.verify()

    def test_scan_path_filters_apply_to_commits(self):
        commit = self.commit_file(self.root, "seed.txt", "BASE")
        (self.state / "note-base").write_text(commit)
        self.configure(scan={"paths":["src"], "exclude_paths":["src/ignored.txt"]})
        self.commit_file(self.root, "docs/info.md", "IGNORE")
        self.commit_file(self.root, "src/ignored.txt", "IGNORE")
        included = self.commit_file(self.root, "src/main.txt", "INCLUDE")
        result = self.skill(self.root, "notes/create.py", "filtered")
        from pathlib import Path
        text = Path(result.stdout.strip()).read_text()
        self.assertIn(included[:7], text)
        self.assertEqual(result.stderr.strip(), "已填入 1 笔未记录的提交")
        self.verify()

    def test_first_scan_and_invalid_baseline_recover(self):
        commit = self.commit_file(self.root, "main.txt", "BASE")
        for stale in (None, "ffffffffffffffffffffffffffffffffffffffff"):
            with self.subTest(stale=stale):
                state = self.state / "note-base"
                state.unlink(missing_ok=True)
                if stale:
                    state.write_text(stale)
                self.verify()
                self.assertEqual(state.read_text().strip(), commit)

    def test_disabled_notes_leave_user_data_alone(self):
        self.commit_file(self.root, "main.txt", "NEW")
        self.configure(enabled=False, max_notes=1)
        day = self.notes / "git-commit-change/2026-01-01"
        day.mkdir(parents=True)
        for i in range(3):
            (day / f"00-00-0{i}-test.md").write_text(f"# Keep {i}")
        before = snapshot(self.notes)
        self.verify()
        self.assertEqual(before, snapshot(self.notes))

    def test_large_changes_recorded_once_and_retrigger_after_growth(self):
        self.configure(scan={"commits":False, "paths":["src"], "large_change":{"files":1,"lines":0}})
        self.verify()  # Establish snapshot; initialization is not a new change.
        (self.root / "src").mkdir()
        (self.root / "src/new.txt").write_text("NEW\n")
        result = self.verify(success=False)
        self.assertIn("新增 1 个文件", result.stderr)
        result = self.skill(self.root, "notes/create.py", "--type", "large-scale-file-change", "large-batch")
        from pathlib import Path
        text = Path(result.stdout.strip()).read_text()
        self.assertIn("src/new.txt", text)
        self.assertNotIn("## Git 提交", text)
        self.verify()
        (self.root / "src/new.txt").unlink()
        self.verify()  # Shrink snapshot after undoing.
        (self.root / "src/new.txt").write_text("NEW AGAIN\n")
        self.assertIn("大规模", self.verify(success=False).stderr)

    def test_large_change_line_threshold_excludes_binary_and_ignored_paths(self):
        self.configure(scan={"commits":False,"paths":["src"],"exclude_paths":["src/ignored.txt"],
                             "large_change":{"files":0,"lines":3}})
        self.verify()
        src = self.root / "src"
        src.mkdir()
        (src / "image.bin").write_bytes(b"\x00" + b"\n" * 20)
        (src / "ignored.txt").write_text("IGNORED\n" * 20)
        self.verify()
        (src / "main.txt").write_text("a\nb\nc")
        self.assertIn("3 行", self.verify(success=False).stderr)

    def test_merge_preserves_hashes_code_fences_sources_and_other_people(self):
        self.configure(max_notes=2, scan={"commits":False,"large_change":{"enabled":False}})
        day = self.notes / "git-commit-change/2026-01-01"
        day.mkdir(parents=True)
        other = self.root / "agent-workspace/other/notes/git-commit-change/2026-01-01"
        other.mkdir(parents=True)
        for i in range(4):
            text = f"# Title {i}\n\n## Body\n\nHash deadbeef{i}\n```sh\n# shell comment\n```\n"
            (day / f"00-00-0{i}-note.md").write_text(text)
            (other / f"00-00-0{i}-other.md").write_text("KEEP OTHER")
        before_other = snapshot(other)
        self.verify()
        self.assertEqual(len(list(day.glob("*.md"))), 2)
        merged = next(day.glob("*-merged.md")).read_text()
        for i in range(3):
            self.assertIn(f"deadbeef{i}", merged)
            self.assertIn(f"<!-- source: 00-00-0{i}-note.md -->", merged)
            self.assertIn(f"## Title {i}", merged)
        self.assertIn("```sh\n# shell comment\n```", merged)
        self.assertEqual(before_other, snapshot(other))
        # A later merge flattens existing source records without dropping them.
        (day / "00-00-04-next.md").write_text("# Next\n\nNew payload")
        self.verify()
        merged = next(day.glob("*-merged.md")).read_text()
        self.assertIn("deadbeef0", merged)
        self.assertEqual(merged.count("<!-- source: 00-00-00-note.md -->"), 1)

    def test_invalid_topic_and_type_create_no_note(self):
        for arguments in (("Invalid Name",), ("../escape",), ("--type","unknown","topic")):
            with self.subTest(arguments=arguments):
                self.skill(self.root, "notes/create.py", *arguments, success=False)
        self.assertFalse(self.notes.exists())

    def test_repeated_topic_never_overwrites_existing_note(self):
        # Collision at the current timestamp must preserve the already written note.
        from pathlib import Path
        first = self.skill(self.root, "notes/create.py", "repeat")
        path = Path(first.stdout.strip())
        path.write_text("USER DATA")
        # The clock is not frozen: either a new second gives a distinct path, or collision is rejected.
        import subprocess
        import sys
        result = subprocess.run([sys.executable, "-B", self.root / "agent-workspace/skills/common/notes/create.py", "repeat"],
                                cwd=self.root, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(path.read_text(), "USER DATA")
        if result.returncode:
            self.assertIn("Note 已存在", result.stderr)
        else:
            self.assertNotEqual(result.stdout.strip(), str(path))
            self.assertTrue(Path(result.stdout.strip()).is_file())

    def test_legacy_note_migration_preserves_collisions(self):
        self.notes.mkdir(parents=True)
        old = self.notes / "26-01-02-03-04-05-legacy.md"
        old.write_text("LEGACY")
        collision = self.notes / "26-01-02-03-04-06-same.md"
        collision.write_text("OLD MUST REMAIN")
        target = self.notes / "large-scale-file-change/2026-01-02/03-04-06-same.md"
        target.parent.mkdir(parents=True)
        target.write_text("NEW MUST REMAIN")
        with patch.dict(os.environ, self.env, clear=True):
            fix_notes(self.root)
            fix_notes(self.root)
        self.assertFalse(old.exists())
        self.assertEqual((target.parent / "03-04-05-legacy.md").read_text(), "LEGACY")
        self.assertEqual(collision.read_text(), "OLD MUST REMAIN")
        self.assertEqual(target.read_text(), "NEW MUST REMAIN")
