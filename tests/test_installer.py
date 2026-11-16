"""Installation protections, rollback and shell profile preservation."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock, patch

from support import Sandbox, ROOT, copy_source, snapshot
import agentdev


class Installer(Sandbox):
    def setUp(self):
        super().setUp()
        self.source = copy_source(self.base / "source")
        self.home = self.base / "install"

    def test_default_global_directory(self):
        with patch.dict(os.environ, self.env, clear=True):
            os.environ.pop("AGENTDEV_HOME")
            with patch.object(Path, "home", return_value=self.base):
                self.assertEqual(agentdev.global_home(), self.base / ".agent-dev-workspace")

    def test_unmanaged_directory_preserved(self):
        self.home.mkdir()
        (self.home / "user.txt").write_text("KEEP")
        before = snapshot(self.home)
        with self.assertRaisesRegex(RuntimeError, "拒绝覆盖"):
            agentdev.install(self.source, self.home, no_path=True, repo="fixture")
        self.assertEqual(before, snapshot(self.home))

    def test_source_cannot_be_install_destination(self):
        before = snapshot(self.source)
        with self.assertRaisesRegex(RuntimeError, "不能覆盖"):
            agentdev.install(self.source, self.source, no_path=True, repo="fixture")
        self.assertEqual(before, snapshot(self.source))

    def test_symlink_install_destination_rejected(self):
        destination = self.base / "destination"
        destination.mkdir()
        self.home.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "符号链接"):
            with agentdev.installation_lock(self.home):
                self.fail("unsafe install lock entered")
        self.assertEqual(list(destination.iterdir()), [])

    def test_lock_released_when_install_raises(self):
        with self.assertRaises(ValueError):
            with agentdev.installation_lock(self.home):
                raise ValueError("fixture")
        self.assertFalse((self.home / ".install.lock").exists())

    def managed_install(self):
        self.home.mkdir()
        copy_source(self.home / "app", "0.2.0")
        (self.home / "install.json").write_text(json.dumps({"repository":"fixture", "path_configured":False}))
        py = agentdev.python_exe(self.home)
        py.parent.mkdir(parents=True)
        py.symlink_to(sys.executable)

    def test_failed_activation_write_restores_previous_app(self):
        self.managed_install()
        before = snapshot(self.home / "app")
        state = (self.home / "install.json").read_bytes()
        with patch.dict(os.environ, self.env, clear=True), \
             patch.object(agentdev.subprocess, "run", return_value=Mock(returncode=0)), \
             patch.object(agentdev, "runtime_errors", return_value=[]), \
             patch.object(agentdev, "write_launchers", side_effect=OSError("fixture disk failure")):
            with self.assertRaises(OSError):
                agentdev.install(self.source, self.home, no_path=True, repo="fixture")
        self.assertEqual(before, snapshot(self.home / "app"))
        self.assertEqual((self.home / "install.json").read_bytes(), state)
        self.assertFalse((self.home / "app.previous").exists())

    def test_failed_dependency_install_keeps_existing_app(self):
        self.managed_install()
        before = snapshot(self.home / "app")
        with patch.object(agentdev.subprocess, "run", side_effect=[Mock(returncode=0), subprocess.CalledProcessError(1, "pip")]):
            with self.assertRaises(subprocess.CalledProcessError):
                agentdev.install(self.source, self.home, no_path=True, repo="fixture")
        self.assertEqual(before, snapshot(self.home / "app"))

    def test_update_requires_published_source_version(self):
        self.managed_install()
        remote = self.base / "remote"
        copy_source(remote, "0.2.1")
        self.git("init", "-q", "-b", "master", remote)
        self.git("add", ".", cwd=remote)
        self.git("commit", "-qm", "[update] older checkout", cwd=remote)
        (self.home / "install.json").write_text(json.dumps({"repository":str(remote), "path_configured":False}))
        before = snapshot(self.home / "app")
        with patch.dict(os.environ, self.env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "尚未包含公布的版本"):
                agentdev.update(self.home, remote=(0, 3, 0))
        self.assertEqual(before, snapshot(self.home / "app"))

    def test_bash_profiles_keep_user_content_and_replace_managed_block(self):
        for name in (".bashrc", ".profile", ".bash_profile"):
            (self.base / name).write_text("# KEEP USER CONTENT\n")
        with patch.dict(os.environ, self.env, clear=True), patch.object(Path, "home", return_value=self.base):
            os.environ["SHELL"] = "/bin/bash"
            agentdev.configure_path(self.home)
            new_home = self.base / "new prefix's folder"
            agentdev.configure_path(new_home)
        for name in (".bashrc", ".profile", ".bash_profile"):
            text = (self.base / name).read_text()
            self.assertIn("# KEEP USER CONTENT", text)
            self.assertEqual(text.count("# >>> agentdev PATH >>>"), 1)
            self.assertNotIn(str(self.home / "env"), text)
            profile_env = self.env.copy()
            # Syntax verification never sources a real profile.
            result = subprocess.run(["bash", "-n", str(self.base / name)], env=profile_env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_uninstalled_commands_fail_clearly(self):
        for command in ("init", "update"):
            with self.subTest(command=command):
                result = self.run_command([str(ROOT / "agentdev"), command], success=False)
                self.assertIn("尚未全局安装", result.stderr)
        result = self.run_command([str(ROOT / "agentdev"), "check"], success=False)
        self.assertIn("缺少 agentskill-path", result.stdout)
