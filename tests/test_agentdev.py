"""Focused command-alias and installer regression tests; no real global installation."""
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


class CommandAliasTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="adev test ' ")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "installation"
        py = agentdev.python_exe(self.home)
        py.parent.mkdir(parents=True)
        py.symlink_to(sys.executable)
        entry = self.home / "app/scripts/agentdev.py"
        entry.parent.mkdir(parents=True)
        entry.write_text(
            'import json, os, sys\n'
            'from pathlib import Path\n'
            'if os.environ.get("ADEV_REFRESH_ENV"):\n'
            '    (Path(__file__).parents[2] / "env").write_text("export ADEV_REFRESHED=1\\n")\n'
            'print(json.dumps(sys.argv[1:]))\n'
            'sys.exit(int(os.environ.get("ADEV_EXIT_CODE", "0")))\n'
        )
        agentdev.write_launchers(self.home)
        self.env = {**os.environ, "HOME": self.temporary.name,
                    "ZDOTDIR": self.temporary.name, "AGENTDEV_HOME": str(self.home),
                    "PYTHONDONTWRITEBYTECODE": "1"}
        for name in ("BASH_ENV", "ENV", "ADEV_REFRESH_ENV", "ADEV_EXIT_CODE", "ADEV_REFRESHED"):
            self.env.pop(name, None)

    def run_command(self, args, **env):
        return subprocess.run([str(arg) for arg in args], env={**self.env, **env},
                              capture_output=True, text=True, cwd=self.temporary.name)

    def shells(self):
        for name, flags in (("sh", []), ("bash", ["--noprofile", "--norc"]), ("zsh", ["-f"])):
            if shutil.which(name):
                yield name, flags

    def test_source_alias_matches_original_help_and_errors(self):
        for args in ([], ["help"], ["--h"], ["init", "--help"], ["not-a-command"]):
            with self.subTest(args=args):
                original = self.run_command([ROOT / "agentdev", *args])
                alias = self.run_command([ROOT / "adev", *args])
                self.assertEqual((alias.returncode, alias.stdout, alias.stderr),
                                 (original.returncode, original.stdout, original.stderr))
                self.assertEqual(alias.returncode, 2 if args == ["not-a-command"] else 0)
                if alias.returncode == 0:
                    self.assertIn("usage: agentdev", alias.stdout)

    def test_installed_launchers_preserve_arguments_and_exit_status(self):
        args = ["check", "path with spaces", "single'quote", "", "--i"]
        for name in ("agentdev", "adev"):
            for code in (0, 23):
                with self.subTest(name=name, code=code):
                    result = self.run_command([self.home / "bin" / name, *args], ADEV_EXIT_CODE=str(code))
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual(json.loads(result.stdout), args)

    def test_posix_activation_preserves_arguments_errors_and_path(self):
        for shell, flags in self.shells():
            for code in (0, 23):
                with self.subTest(shell=shell, code=code):
                    result = self.run_command(
                        [shell, *flags, "-c", '. "$1"; . "$1"; adev check "path with spaces" ""',
                         "test", self.home / "env"], ADEV_EXIT_CODE=str(code))
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual(json.loads(result.stdout), ["check", "path with spaces", ""])
            with self.subTest(shell=shell, path=True):
                result = self.run_command(
                    [shell, *flags, "-c", '. "$1"; . "$1"; printf "%s" "$PATH"',
                     "test", self.home / "env"])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.split(":").count(str(self.home / "bin")), 1)

    def test_adev_setup_reactivates_only_after_success(self):
        for shell, flags in self.shells():
            for command in ("setup", "-setup", "--s"):
                for code in (0, 23):
                    with self.subTest(shell=shell, command=command, code=code):
                        agentdev.write_launchers(self.home)
                        result = self.run_command(
                            [shell, *flags, "-c",
                             '. "$1"; adev "$2" --no-path; code=$?; '
                             'printf "%s:%s\\n" "$code" "${ADEV_REFRESHED-unset}"; exit "$code"',
                             "test", self.home / "env", command],
                            ADEV_REFRESH_ENV="1", ADEV_EXIT_CODE=str(code))
                        self.assertEqual(result.returncode, code, result.stderr)
                        self.assertEqual(result.stdout.splitlines()[-1],
                                         "0:1" if code == 0 else "23:unset")

    def test_install_and_reinstall_copy_alias(self):
        # Preserve the fake interpreter while exercising real staging/copy/launcher logic.
        (self.home / "install.json").write_text("{}")
        with mock.patch.object(agentdev, "run"), \
                mock.patch.object(agentdev.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
                mock.patch.object(agentdev, "runtime_errors", return_value=[]), \
                mock.patch.object(agentdev, "configure_path") as configure_path, \
                contextlib.redirect_stdout(io.StringIO()):
            for _ in range(2):
                agentdev.install(ROOT, self.home, no_path=True, repo="test-repository")
                self.assertEqual((self.home / "app/adev").read_text(), (ROOT / "agentdev").read_text())
                self.assertTrue(os.access(self.home / "bin/adev", os.X_OK))
            configure_path.assert_not_called()
        for entry in (self.home / "bin/adev", self.home / "app/adev"):
            result = self.run_command([entry, "--h"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("adev 与 agentdev 等价", result.stdout)


if __name__ == "__main__":
    unittest.main()
