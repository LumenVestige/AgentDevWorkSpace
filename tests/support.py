"""Shared, project-local fixtures. No real profiles, credentials or remote writes."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "tests/workspace"
TMP = WORK / "cases"
WHEELS = Path(os.environ.get("AGENTDEV_TEST_WHEELS", WORK / "wheels"))
TMP.mkdir(parents=True, exist_ok=True)
sys.dont_write_bytecode = True
for directory in ("scripts", "skills"):
    sys.path.insert(0, str(ROOT / directory))


def isolated_env(base, **extra):
    env = dict(os.environ)
    # Never use the caller's credentials, Git overrides or Python package paths.
    for key in list(env):
        if key.startswith(("GIT_", "PIP_", "PYTHON")) or key in {
            "GH_TOKEN", "GITHUB_TOKEN", "AGENTDEV_HOME", "AGENTDEV_VERSION_URL", "BASH_ENV", "ENV", "ZDOTDIR"
        }:
            env.pop(key)
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CEILING_DIRECTORIES": str(base), "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "3",
        "GIT_CONFIG_KEY_0": "user.name", "GIT_CONFIG_VALUE_0": "Fixture User",
        "GIT_CONFIG_KEY_1": "commit.gpgSign", "GIT_CONFIG_VALUE_1": "false",
        "GIT_CONFIG_KEY_2": "init.defaultBranch", "GIT_CONFIG_VALUE_2": "master",
        "GIT_AUTHOR_NAME": "Fixture User", "GIT_COMMITTER_NAME": "Fixture User",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "PIP_NO_INDEX": "1", "PIP_FIND_LINKS": str(WHEELS),
        "PIP_CONFIG_FILE": os.devnull, "PIP_CACHE_DIR": str(base / "pip-cache"),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "AGENTDEV_HOME": str(base / "global 安装"),
        "AGENTDEV_VERSION_URL": (base / "remote-version").as_uri(),
        "ZDOTDIR": str(base / "shell-config"),
    })
    env.update(extra)
    return env


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file() and not path.is_symlink()
            and ".git" not in path.relative_to(root).parts}


def copy_source(target, version="0.3.0"):
    """Pin fixture versions so a future release never changes test expectations."""
    target.mkdir()
    for name in ("scripts", "skills"):
        shutil.copytree(ROOT / name, target / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("AGENTS.md", "README.md", "agentdev", "adev", "setup.sh", "update.sh"):
        shutil.copy2(ROOT / name, target / name, follow_symlinks=False)
    (target / "publish").mkdir()
    shutil.copy2(ROOT / "publish/publish.sh", target / "publish/publish.sh")
    (target / "publish/version").write_text(version + "\n", encoding="utf-8")
    return target


class Sandbox(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="case-", dir=TMP)
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.env = isolated_env(self.base)

    def run_command(self, args, *, cwd=None, success=True, input=None):
        result = subprocess.run(list(map(str, args)), cwd=cwd or self.base, env=self.env,
                                input=input, capture_output=True, text=True, timeout=60)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def git(self, *args, cwd=None):
        return self.run_command(["git", *args], cwd=cwd).stdout.strip()

    def make_project(self, *, git=True, personal="Test Owner"):
        root = self.base / "项目 with spaces"
        root.mkdir()
        if git:
            self.git("init", "-q", "-b", "master", root)
        common = root / "agent-workspace/skills/common"
        shutil.copytree(ROOT / "skills", common)
        env = root / "agent-workspace/.agent/env"
        env.mkdir(parents=True)
        (env / "python-path").write_text(sys.executable)
        (env / "agentskill-path").write_text(str(ROOT))
        (env / "note-base").write_text("")
        config = root / "agent-workspace/config/config.json5"
        config.parent.mkdir()
        config.write_text('{personal: "' + personal + '", auto_update:false}', encoding="utf-8")
        (root / ".gitignore").write_text("/agent-workspace/.agent/\n/agent-workspace/config/\n")
        return root

    def skill(self, root, script, *args, success=True, input="{}"):
        return self.run_command([sys.executable, "-B", root / "agent-workspace/skills/common" / script, *args],
                                cwd=root, success=success, input=input)

    def commit_file(self, root, name, content, message="[update] fixture"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.git("add", "--", name, cwd=root)
        self.git("commit", "-qm", message, cwd=root)
        return self.git("rev-parse", "HEAD", cwd=root)
