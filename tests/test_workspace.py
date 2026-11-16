"""Source-repository update protections, isolated from real installations and profiles."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import agentdev
import workspace

class SourceWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="agentdev-source-update-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / "installation"
        self.source = self.home / "app"
        self.source.mkdir(parents=True)
        for name in ("scripts", "skills", "publish"):
            shutil.copytree(ROOT / name, self.source / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copy2(ROOT / "AGENTS.md", self.source / "AGENTS.md")
        (self.source / ".agentdev-app").touch()
        (self.home / "install.json").write_text(json.dumps({"repository": "test-repository"}))
        self.version = agentdev.read_version(self.source)
        for patcher in (
            mock.patch.dict(os.environ, {"HOME": str(self.base), "GIT_CONFIG_NOSYSTEM": "1",
                                         "GIT_CONFIG_GLOBAL": os.devnull}),
            mock.patch.object(workspace, "runtime_errors", return_value=[]),
            mock.patch.object(workspace, "project_settings", return_value={"personal": "tester"}),
            mock.patch.object(workspace, "fix_notes"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            patcher.__enter__()
            self.addCleanup(patcher.__exit__, None, None, None)

    def project(self, name="renamed-checkout", source=True):
        project = self.base / name
        project.mkdir()
        subprocess.run(["git", "-c", "init.templateDir=", "init", "-q", str(project)], check=True)
        (project / "agent-workspace").mkdir()
        if source:
            self.remote(project, "add", "origin", agentdev.REPOSITORY)
        (project / "AGENTS.md").write_bytes(b"# Local rules\r\nKeep these exact bytes.")
        (project / ".gitignore").write_bytes(b"# Local ignores\r\n/keep-me")
        return project

    def remote(self, project, *args):
        subprocess.run(["git", "-C", str(project), "remote", *args], check=True)

    def snapshot(self, project):
        return {name: ((project / name).read_bytes(), (project / name).lstat().st_mtime_ns,
                       (project / name).is_symlink()) for name in ("AGENTS.md", ".gitignore")}

    def update(self, project, remote, current_directory=False):
        def run(args, **kwargs):
            if args[:2] == ["git", "clone"]:
                checkout = Path(args[-1])
                shutil.copytree(self.source, checkout)
                (checkout / "publish/version").write_text(agentdev.version_text(remote) + "\n")
            else:
                self.assertEqual(args[1:3], [self.source / "scripts/agentdev.py", "init"])
                self.assertEqual(Path(args[-1]), project)
                workspace.initialize(self.source, self.home, Path(args[-1]))

        def install(checkout, home, **kwargs):
            self.assertEqual(home, self.home)
            shutil.copytree(checkout, self.source, dirs_exist_ok=True)

        with mock.patch.object(agentdev, "run", side_effect=run), \
                mock.patch.object(agentdev, "install", side_effect=install), \
                mock.patch.object(agentdev.Path, "cwd", return_value=project):
            agentdev.update(self.home, project=None if current_directory else str(project), remote=remote)

    def assert_workspace_refreshed(self, project):
        ws = project / "agent-workspace"
        self.assertEqual((ws / "skills/common/sdd/welcome.md").read_bytes(),
                         (self.source / "skills/sdd/welcome.md").read_bytes())
        self.assertEqual((ws / ".agent/env/agentskill-version").read_text(),
                         (self.source / "publish/version").read_text())
        for path in (project / ".claude/settings.local.json", project / ".codex/hooks.json"):
            self.assertIn("Stop", json.loads(path.read_text())["hooks"])

    def test_update_preserves_source_files_with_or_without_new_version(self):
        project = self.project()
        before = self.snapshot(project)
        versions = (self.version, (*self.version[:2], self.version[2] + 1))
        for index, remote in enumerate(versions):
            with self.subTest(remote=remote):
                self.update(project, remote, current_directory=index == 0)
                self.assertEqual(self.snapshot(project), before)
                self.assert_workspace_refreshed(project)

    def test_update_regular_project_still_updates_managed_files(self):
        project = self.project("AgentDevWorkSpace", source=False)
        self.update(project, self.version)
        self.assertIn(workspace.MARK_BEGIN, (project / "AGENTS.md").read_text())
        self.assertIn("/agent-workspace/*/specs/", (project / ".gitignore").read_text())
        self.assert_workspace_refreshed(project)

    def test_init_preserves_source_symlinks_and_their_targets(self):
        project = self.project()
        for name in ("AGENTS.md", ".gitignore"):
            path = project / name
            target = self.base / (name + ".target")
            path.rename(target)
            path.symlink_to(target)
        env = project / "agent-workspace/.agent/env"
        env.mkdir(parents=True)
        (env / "managed-links.json").write_text(json.dumps({str(project / "AGENTS.md"): "symlink"}))
        before = self.snapshot(project)
        workspace.initialize(self.source, self.home, project)
        self.assertEqual(self.snapshot(project), before)
        self.assert_workspace_refreshed(project)

    def test_source_detection_supports_renamed_and_linked_directories(self):
        project = self.project("arbitrary-checkout-name")
        alias = self.base / "checkout-link"
        alias.symlink_to(project, target_is_directory=True)
        self.assertTrue(workspace.is_source_repository(project))
        self.assertTrue(workspace.is_source_repository(alias))
        self.assertFalse(workspace.is_source_repository(self.project("AgentDevWorkSpace", source=False)))

    def test_source_detection_excludes_managed_installations(self):
        project = self.project()
        (project / ".agentdev-app").touch()
        with mock.patch.object(workspace, "git") as git:
            self.assertFalse(workspace.is_source_repository(project))
            git.assert_not_called()

    def test_source_detection_normalizes_remote_urls(self):
        project = self.project()
        urls = (
            "https://github.com/LumenVestige/AgentDevWorkSpace.git",
            "https://github.com/LumenVestige/AgentDevWorkSpace/",
            "git@github.com:LumenVestige/AgentDevWorkSpace.git",
            "git@github.com:LumenVestige/AgentDevWorkSpace",
            "ssh://git@github.com/LumenVestige/AgentDevWorkSpace.git",
            "ssh://git@github.com:22/LumenVestige/AgentDevWorkSpace.git/",
            "git://github.com/LumenVestige/AgentDevWorkSpace.git",
            "https://GITHUB.COM/lumenvestige/AGENTDEVWORKSPACE.GIT",
        )
        for url in urls:
            with self.subTest(url=url):
                self.remote(project, "set-url", "origin", url)
                self.assertTrue(workspace.is_source_repository(project))

    def test_source_detection_checks_remotes_other_than_origin(self):
        project = self.project()
        self.remote(project, "set-url", "origin", "https://github.com/someone/AgentDevWorkSpace.git")
        self.assertFalse(workspace.is_source_repository(project))
        self.remote(project, "add", "upstream", agentdev.REPOSITORY)
        self.assertTrue(workspace.is_source_repository(project))
        self.remote(project, "remove", "origin")
        self.assertTrue(workspace.is_source_repository(project))

    def test_source_detection_rejects_unrelated_and_invalid_remotes(self):
        project = self.project()
        urls = (
            "https://github.com/other/AgentDevWorkSpace.git",
            "https://example.com/LumenVestige/AgentDevWorkSpace.git",
            "https://github.com.evil.example/LumenVestige/AgentDevWorkSpace.git",
            "https://github.com/LumenVestige/AgentDevWorkSpace-extra.git",
            "https://github.com/LumenVestige/AgentDevWorkSpace/subdirectory",
            "file://github.com/LumenVestige/AgentDevWorkSpace.git",
            "/tmp/LumenVestige/AgentDevWorkSpace.git",
            "https://[invalid",
        )
        for url in urls:
            with self.subTest(url=url):
                self.remote(project, "set-url", "origin", url)
                self.assertFalse(workspace.is_source_repository(project))
        self.remote(project, "remove", "origin")
        self.assertFalse(workspace.is_source_repository(project))
        self.assertFalse(workspace.is_source_repository(self.base))

    def test_init_does_not_create_missing_source_files(self):
        project = self.project()
        for name in ("AGENTS.md", ".gitignore"):
            (project / name).unlink()
        workspace.initialize(self.source, self.home, project)
        for name in ("AGENTS.md", ".gitignore"):
            self.assertFalse((project / name).exists())
            self.assertFalse((project / name).is_symlink())
        self.assert_workspace_refreshed(project)


if __name__ == "__main__":
    unittest.main()
