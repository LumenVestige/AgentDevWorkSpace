"""CLI layout and removed installation command regressions."""
import sys

from support import ROOT, Sandbox


class CommandLayout(Sandbox):
    def test_setup_is_not_a_command_or_alias(self):
        for entry in ("agentdev", "adev"):
            for command in ("setup", "-setup", "--s"):
                with self.subTest(entry=entry, command=command):
                    result = self.run_command([ROOT / entry, command], success=False)
                    self.assertEqual(result.returncode, 2)
        self.assertFalse((self.base / "global 安装").exists())

    def test_help_only_lists_supported_commands(self):
        text = self.run_command([ROOT / "agentdev", "help"]).stdout
        for name in ("help", "init", "check", "update", "version"):
            self.assertIn(name, text)
        self.assertNotIn("setup", text)
        self.assertNotIn("--s", text)

    def test_command_and_library_implementations_are_separate(self):
        for name in ("app", "help", "init", "check", "update", "version"):
            self.assertTrue((ROOT / "scripts/command" / (name + ".py")).is_file(), name)
        for name in ("installer.py", "workspace.py", "setup.py", "bootstrap.sh", "deps.sh", "run_skill.py"):
            self.assertTrue((ROOT / "scripts/lib" / name).is_file(), name)
        self.assertTrue((ROOT / "setup.sh").is_file())

    def test_legacy_python_entry_forwards_to_new_cli(self):
        text = self.run_command([sys.executable, ROOT / "scripts/agentdev.py", "help"]).stdout
        self.assertIn("init", text)
        self.assertNotIn("setup", text)

    def test_shell_entrypoints_dispatch_to_supported_commands(self):
        for name in ("init", "check", "update"):
            with self.subTest(command=name):
                text = self.run_command(["sh", ROOT / "scripts/command" / (name + ".sh"), "--help"]).stdout
                self.assertIn("agentdev " + name, text)
        self.assertIn("agentdev update", self.run_command(["sh", ROOT / "update.sh", "--help"]).stdout)

    def test_legacy_hook_entry_forwards_to_shared_dispatcher(self):
        project = self.make_project()
        marker = project / "agent-workspace/skills/custom/sdd"
        marker.mkdir(parents=True)
        (marker / "welcome.py").write_text('print("LEGACY_HOOK_OK")\n')
        result = self.run_command([sys.executable, ROOT / "scripts/run_skill.py", "--project", project,
                                   "sdd/welcome.py"], cwd=project)
        self.assertEqual(result.stdout.strip(), "LEGACY_HOOK_OK")

    def test_legacy_dependency_manifest_is_readable(self):
        self.assertEqual((ROOT / "scripts/deps.sh").read_text(), (ROOT / "scripts/lib/deps.sh").read_text())
        self.assertEqual((ROOT / "scripts/setup.sh").resolve(), ROOT / "setup.sh")
