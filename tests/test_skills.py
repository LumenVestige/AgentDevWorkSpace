"""Real SDD creation/layout hooks, knowledge searches and commit-message hooks."""
import shutil
import sys

from support import ROOT, Sandbox, snapshot


class SDD(Sandbox):
    def setUp(self):
        super().setUp()
        self.root = self.make_project()
        self.common = self.root / "agent-workspace/skills/common"

    def create(self, kind, name, success=True):
        return self.run_command(["sh", self.common / f"sdd/new_{kind}.sh", name],
                                cwd=self.root, success=success)

    def test_four_types_number_independently_and_fill_templates(self):
        for kind in ("feature", "bugfix", "change", "research"):
            with self.subTest(kind=kind):
                result = self.create(kind, "用户 Login & Upgrade")
                path = self.root / result.stdout.strip()
                self.assertEqual(path.name, "001-用户-login-upgrade")
                self.assertEqual(path.parent.name, kind)
                self.assertEqual({p.name for p in path.iterdir()}, {"spec.md", "plan.md", "tasks.md"})
                spec = (path / "spec.md").read_text()
                self.assertIn("用户 Login & Upgrade", spec)
                self.assertIn("001", spec)
                self.assertNotIn("<git user.name>", spec)
                self.assertNotIn("<需求名称>", spec)
                self.assertIn("002-second", self.create(kind, "Second").stdout)
        self.assertIn("已全部归类", self.skill(self.root, "sdd/check_layout.py", "--all").stdout)

    def test_duplicate_or_empty_names_do_not_change_existing_spec(self):
        result = self.create("change", "First")
        path = self.root / result.stdout.strip()
        (path / "spec.md").write_text("USER SPEC")
        before = snapshot(path)
        self.assertIn("已存在", self.create("change", "First", success=False).stderr)
        self.assertEqual(before, snapshot(path))
        for name in ("", "!!!"):
            with self.subTest(name=name):
                self.create("change", name, success=False)
        self.assertEqual(len(list(path.parent.iterdir())), 1)

    def test_next_number_uses_maximum_with_gaps(self):
        path = self.root / "agent-workspace/test-owner/feature/009-existing"
        path.mkdir(parents=True)
        self.assertIn("/010-next", self.create("feature", "Next").stdout)

    def test_custom_templates_and_constraints_take_priority(self):
        custom = self.root / "agent-workspace/skills/custom/sdd"
        shutil.copytree(self.common / "sdd", custom)
        template = custom / "templates/change/spec.md"
        template.write_text(template.read_text() + "\nCUSTOM TEMPLATE\n")
        (custom / "personal-constraints.md").write_text("CUSTOM CONSTRAINTS")
        path = self.root / self.create("change", "Custom").stdout.strip()
        self.assertIn("CUSTOM TEMPLATE", (path / "spec.md").read_text())
        self.assertIn("skills/custom/sdd/constraints.md", (path / "spec.md").read_text())
        self.assertEqual((path.parents[1] / "specs/constraints.md").read_text(), "CUSTOM CONSTRAINTS")

    def test_layout_all_blocks_unclassified_file(self):
        path = self.root / self.create("bugfix", "Broken").stdout.strip()
        (path / "evidence.log").write_text("unclassified")
        result = self.skill(self.root, "sdd/check_layout.py", "--all", success=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("evidence.log", result.stderr)
        evidence = path / "01-evidence"
        evidence.mkdir()
        (path / "evidence.log").rename(evidence / "evidence.log")
        self.skill(self.root, "sdd/check_layout.py", "--all")

    def test_layout_stop_blocks_once_then_reports_without_looping(self):
        path = self.root / self.create("feature", "Hook").stdout.strip()
        (path / "loose.md").write_text("evidence")
        result = self.skill(self.root, "sdd/check_layout.py", success=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("loose.md", result.stderr)
        result = self.skill(self.root, "sdd/check_layout.py", input='{"stop_hook_active":true}')
        self.assertIn("loose.md", result.stderr)

    def test_layout_stop_ignores_committed_old_files(self):
        path = self.root / self.create("feature", "Old layout").stdout.strip()
        self.commit_file(self.root, str(path.relative_to(self.root) / "old.log"), "OLD")
        self.skill(self.root, "sdd/check_layout.py")
        self.skill(self.root, "sdd/check_layout.py", "--all", success=False)

    def test_layout_non_git_checks_all_files(self):
        # Reuse the generated workspace without a Git repository.
        shutil.rmtree(self.root / ".git")
        path = self.root / self.create("research", "Plain").stdout.strip()
        (path / "raw.txt").write_text("RAW")
        self.assertEqual(self.skill(self.root, "sdd/check_layout.py", success=False).returncode, 2)

    def test_layout_accepts_classified_deep_paths_and_junk(self):
        path = self.root / self.create("change", "Classified").stdout.strip()
        for relative in ("summary.md", ".DS_Store", "01-evidence/deep/anywhere/file.txt", "02-results/output.json"):
            file = path / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("DATA")
        self.skill(self.root, "sdd/check_layout.py", "--all")

    def test_hook_runner_custom_priority_and_project_discovery(self):
        for flavor in ("common", "custom"):
            target = self.root / "agent-workspace/skills" / flavor / "fixture/run.py"
            target.parent.mkdir(parents=True)
            target.write_text(f'import os\nprint({flavor!r}, os.getcwd())\n')
        child = self.root / "nested dir"
        child.mkdir()
        result = self.run_command([sys.executable, ROOT / "scripts/run_skill.py", "--project", self.base,
                                   "fixture/run.py"], cwd=child)
        self.assertEqual(result.stdout.strip(), f"custom {self.root}")
        (self.root / "agent-workspace/skills/custom/fixture/run.py").unlink()
        result = self.run_command([sys.executable, ROOT / "scripts/run_skill.py", "--project", self.root,
                                   "fixture/run.py"], cwd=child)
        self.assertEqual(result.stdout.strip(), f"common {self.root}")

    def test_hook_runner_rejects_parent_traversal(self):
        for script in ("../secret.py", "sdd/../../secret.py", "script.py"):
            with self.subTest(script=script):
                result = self.run_command([sys.executable, ROOT / "scripts/run_skill.py", "--project", self.root,
                                           script], success=False)
                self.assertIn("skill 脚本路径", result.stderr)


class Knowledge(Sandbox):
    def setUp(self):
        super().setUp()
        self.root = self.make_project()
        self.script = self.root / "agent-workspace/skills/common/knowledge/search.sh"
        self.req = self.root / "agent-workspace/alice/research/001-storage"
        (self.req / "01-results").mkdir(parents=True)
        (self.req / "spec.md").write_text("# Storage\n类型：research | 编号：001 | 负责人：Alice\n")

    def search(self, *words, success=True):
        return self.run_command(["sh", self.script, *words], cwd=self.root, success=success)

    def test_search_classified_documents_and_requirement_metadata(self):
        (self.req / "01-results/findings.md").write_text("Storage latency benchmark\n")
        output = self.search("STORAGE", "latency").stdout
        self.assertIn("01-results/findings.md", output)
        self.assertIn("负责人：Alice", output)
        self.assertNotIn("- agent-workspace/alice/research/001-storage/spec.md", output)

    def test_keywords_are_literal_and_all_required(self):
        (self.req / "plan.md").write_text("literal a.*b [x] --flag\n")
        self.assertIn("plan.md", self.search("a.*b", "[x]", "--flag").stdout)
        self.assertIn("未找到", self.search("a.+b").stdout)
        self.assertIn("未找到", self.search("literal", "absent").stdout)

    def test_notes_constraints_and_git_history(self):
        self.commit_file(self.root, "src.txt", "payload", "[update] uniquehistory benchmark")
        self.assertIn("Git 提交", self.search("UNIQUEHISTORY", "benchmark").stdout)
        for relative in ("alice/notes/git-commit-change/2026-01-01/00-00-00-test.md", "alice/specs/constraints.md"):
            path = self.root / "agent-workspace" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("unique content phrase")
        output = self.search("unique content phrase").stdout
        self.assertIn("Note", output)
        self.assertIn("约束", output)

    def test_missing_keywords_fail_with_usage(self):
        self.assertIn("用法", self.search(success=False).stderr)


class CommitMessageHook(Sandbox):
    def test_allowed_tags_and_generated_messages(self):
        path = self.base / "message"
        for title in ("[fix] 修复", "[feature] 登录", "[research] 调研", "[del] 删除", "[update] 更新",
                      "Merge branch 'topic'", "Revert \"old\"", "fixup! previous", "squash! previous"):
            with self.subTest(title=title):
                path.write_text(title + "\n\nBODY\n")
                self.run_command(["sh", ROOT / "skills/git-commit/commit-msg", path])

    def test_missing_or_invalid_tag_is_rejected(self):
        path = self.base / "message"
        for title in ("", "update thing", "[fix]", "[feat] feature", "[fix] ", "prefix [fix] thing"):
            with self.subTest(title=title):
                path.write_text(title + "\n")
                result = self.run_command(["sh", ROOT / "skills/git-commit/commit-msg", path], success=False)
                self.assertIn("提交信息必须", result.stderr)
