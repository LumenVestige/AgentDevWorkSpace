#!/usr/bin/env python3
"""macOS/Linux 安装器与 CLI 共用的运行时、版本、锁及 PATH 支持。"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
from .workspace import REPOSITORY, requirements, runtime_errors
from .repository import stage_repository, missing_repository, git

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills"))
from _version import parse_version, format_version, read_version_file, fetch_remote_version


def global_home():
    if os.environ.get("AGENTDEV_HOME"):
        return Path(os.environ["AGENTDEV_HOME"]).expanduser().absolute()
    if ROOT.name == "app" and (ROOT.parent / "install.json").is_file():
        return ROOT.parent
    return Path.home() / ".agent-dev-workspace"


def python_exe(home):
    return home / "venv/bin/python"


def version(text):
    return parse_version(text, allow_legacy=True)


def version_text(value):
    return format_version(value)


def read_version(source):
    return read_version_file(source / "publish/version")


def remote_version():
    return fetch_remote_version(os.environ.get("AGENTDEV_VERSION_URL"))


def run(args, **kwargs):
    env = {**os.environ, **kwargs.pop("env", {}), "PYTHONDONTWRITEBYTECODE": "1", "GIT_TERMINAL_PROMPT": "0"}
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return subprocess.run([str(arg) for arg in args], env=env, check=True, **kwargs)


def installed(home):
    entries = ("command/app.py", "agentdev.py")  # 后者只用于识别旧版安装。
    if not (home / "install.json").is_file() or not any(
            (home / "app/scripts" / entry).is_file() for entry in entries):
        raise RuntimeError("尚未全局安装，请先运行 source setup.sh")
    return home / "app"


def metadata(home):
    return json.loads((home / "install.json").read_text(encoding="utf-8"))


def repository(source, home):
    if (home / "install.json").is_file() and source == home / "app":
        return metadata(home)["repository"]
    result = subprocess.run(["git", "-C", str(source), "config", "--get", "remote.origin.url"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else REPOSITORY


def write_launchers(home):
    directory = home / "bin"
    directory.mkdir(exist_ok=True)
    py, entry = str(python_exe(home)), str(home / "app/scripts/command/app.py")
    for name in ("agentdev", "adev"):
        unix = directory / name
        unix.write_text(f'#!/bin/sh\nexec {shlex.quote(py)} {shlex.quote(entry)} "$@"\n', encoding="utf-8")
        unix.chmod(0o755)
    command = f'{shlex.quote(py)} -B {shlex.quote(entry)}'
    (home / "env").write_text(
        f'case ":$PATH:" in *{shlex.quote(":" + str(directory) + ":")}*) ;; *) export PATH={shlex.quote(str(directory))}:"$PATH" ;; esac\n'
        'agentdev() {\n'
        f'  {command} "$@"\n'
        '}\n'
        'adev() { agentdev "$@"; }\n', encoding="utf-8")
    fish_quote = lambda text: "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"
    (home / "env.fish").write_text(
        f'if not contains -- {fish_quote(str(directory))} $PATH\n'
        f'    set -gx PATH {fish_quote(str(directory))} $PATH\nend\n', encoding="utf-8")
    # 只清理旧安装器生成的遗留入口，不再提供这些平台入口。
    for relative in ("bin/agentdev.cmd", "bin/agentdev.ps1", "env.cmd", "env.ps1"):
        legacy = home / relative
        if legacy.is_file() or legacy.is_symlink():
            legacy.unlink()


@contextmanager
def installation_lock(home):
    if home.is_symlink():
        raise RuntimeError("安装目录不能是符号链接")
    home.mkdir(parents=True, exist_ok=True)
    lock = home / ".install.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RuntimeError(f"另一个安装或更新正在进行；若进程已退出，请检查锁文件：{lock}") from None
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)


def configure_path(home):
    shell = Path(os.environ.get("SHELL", "")).name
    names = [".zshrc"] if shell == "zsh" else [".bashrc", ".profile"] if shell == "bash" else [".profile"]
    if shell == "bash" and (Path.home() / ".bash_profile").exists():
        names.append(".bash_profile")
    start, end = "# >>> agentdev PATH >>>", "# <<< agentdev PATH <<<"
    block = f'{start}\n. {shlex.quote(str(home / "env"))}\n{end}'
    if shell == "fish":
        config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        names = [config_home / "fish/config.fish"]
        fish_path = str(home / "env.fish").replace("\\", "\\\\").replace("'", "\\'")
        block = f"{start}\nsource '{fish_path}'\n{end}"
    for name in names:
        profile = Path.home() / name
        text = profile.read_text(encoding="utf-8") if profile.exists() else ""
        text = re.sub(re.escape(start) + r".*?" + re.escape(end), "", text, flags=re.S).rstrip()
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text((text + "\n\n" if text else "") + block + "\n", encoding="utf-8")


def repair_repository(home, checkout):
    """Restore only Git metadata, never checkout/reset the installed worktree."""
    from .update_status import atomic_json

    if not missing_repository(home):
        raise RuntimeError("仅允许补齐缺失的 .git，不替换已有 Git 元数据")
    saved = metadata(home)
    baseline = saved.get("commit")
    if baseline and (not isinstance(baseline, str) or not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", baseline)):
        raise RuntimeError("安装 commit 基准无效，无法补齐 .git")
    with tempfile.TemporaryDirectory(prefix="repair-git-", dir=home) as temporary:
        staged = Path(temporary) / "repository"
        stage_repository(checkout, staged, saved["repository"])
        if baseline and git(staged, "rev-parse", "HEAD").strip() != baseline:
            # The downloaded master may be newer; compare against the installed commit,
            # not today's files. All destructive Git operations stay in temporary storage.
            git(staged, "fetch", "--depth", "1", "--no-tags", "origin", baseline, timeout=120)
            git(staged, "reset", "--hard", baseline)
        if read_version(staged) != read_version(home / "app"):
            raise RuntimeError("Git 基准版本与安装版本不一致，无法安全补齐 .git；现有源码未覆盖")
        commit = git(staged, "rev-parse", "HEAD").strip()
        if not missing_repository(home):
            raise RuntimeError("安装目录的 .git 已变化，本次不替换")
        target = home / "app/.git"
        os.replace(staged / ".git", target)
        try:
            atomic_json(home / "install.json", dict(saved, commit=commit))
        except BaseException:
            # No pre-existing Git was touched; rollback only the metadata we just added.
            os.replace(target, staged / ".git")
            raise
    return commit


def install(source, home, no_path=False, repo=None, progress=None):
    source, home = source.resolve(), home.absolute()
    read_version(source)
    if home == source:
        raise RuntimeError("安装目录不能覆盖源码目录或其父目录")
    if home.is_symlink():
        raise RuntimeError("安装目录不能是符号链接")
    contents = {path.name for path in home.iterdir()} if home.exists() else set()
    if contents - {".install.lock"} and not any((home / name).exists() for name in ("install.json", ".installing")):
        raise RuntimeError(f"目录已有其他内容，拒绝覆盖：{home}")
    repo = repo or repository(source, home)
    home.mkdir(parents=True, exist_ok=True)
    (home / ".installing").touch()
    py = python_exe(home)
    runner = progress.run if progress else run
    if progress:
        progress.stage("dependencies")
    try:
        usable = py.is_file() and subprocess.run([str(py), "-B", "-m", "pip", "--version"], capture_output=True).returncode == 0
    except OSError:
        usable = False
    if not usable:
        runner([sys.executable, "-m", "venv", home / "venv"], timeout=120)
    env = {**os.environ, "PIP_CONFIG_FILE": os.devnull, "PIP_CACHE_DIR": str(home / "cache"), "PYTHONDONTWRITEBYTECODE": "1"}
    runner([str(py), "-m", "pip", "install", "--disable-pip-version-check", *requirements(source)], env=env, timeout=120)
    if progress:
        progress.stage("validating")
    errors = runtime_errors(py, source)
    if errors:
        raise RuntimeError("；".join(errors))
    previous = home / "app.previous"
    if previous.exists():
        raise RuntimeError(f"上次安装备份尚在，请先恢复或检查：{previous}")
    if progress:
        progress.stage("staging")
    with tempfile.TemporaryDirectory(prefix="install-", dir=home) as temporary:
        staged = Path(temporary) / "app"
        commit = stage_repository(source, staged, repo)
        if commit is None:  # Compatibility with archives and old installed snapshots.
            staged.mkdir()
            for name in ("scripts", "skills"):
                shutil.copytree(source / name, staged / name, symlinks=name == "scripts",
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if (source / "plugins").is_dir():
                shutil.copytree(source / "plugins", staged / "plugins")
            (staged / "publish").mkdir()
            (staged / "publish/version").write_text(version_text(read_version(source)) + "\n", encoding="utf-8")
            for name in ("AGENTS.md", "README.md", "agentdev", "adev", "setup.sh"):
                shutil.copy2(source / name, staged / name)
        (staged / ".agentdev-app").touch()
        if progress:
            progress.stage("activating")
        if (home / "app").exists():
            (home / "app").rename(previous)
        try:
            staged.rename(home / "app")
            write_launchers(home)
            if not no_path:
                configure_path(home)
            (home / "install.json").write_text(json.dumps({"repository": repo, "path_configured": not no_path, **({"commit": commit} if commit else {})}, indent=2) + "\n", encoding="utf-8")
        except Exception:
            shutil.rmtree(home / "app", ignore_errors=True)
            if previous.exists():
                previous.rename(home / "app")
            raise
    if previous.exists():
        shutil.rmtree(previous)
    (home / ".installing").unlink(missing_ok=True)
    print(f"已安装 AgentDevWorkSpace {version_text(read_version(home / 'app'))}：{home}")
    if no_path:
        print(f"未修改持久 PATH；请通过完整路径调用 {home / 'bin/agentdev'}")
    else:
        if Path(os.environ.get("SHELL", "")).name == "fish":
            print(f"当前 fish 激活：source {shlex.quote(str(home / 'env.fish'))}")
        else:
            print(f"当前终端激活：. {shlex.quote(str(home / 'env'))}；也可直接 source setup.sh 安装并激活。")



def require_platform():
    if os.name != "posix":
        raise RuntimeError("仅支持 macOS 和 Linux")
    if sys.version_info < (3, 9):
        raise RuntimeError("需要 Python 3.9+")
