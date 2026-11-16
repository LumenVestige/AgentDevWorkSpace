#!/usr/bin/env python3
"""AgentDevWorkSpace 的 macOS/Linux 安装、更新和命令入口（Python 3.9+）。"""
import argparse
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
from workspace import initialize, check_workspace, fix_notes, requirements, runtime_errors

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills"))
from _version import parse_version, format_version, read_version_file, fetch_remote_version
REPOSITORY = "https://github.com/LumenVestige/AgentDevWorkSpace.git"
ALIASES = {
    "-help": "help", "--h": "help", "--help": "help", "-h": "help",
    "-setup": "setup", "--s": "setup", "-init": "init", "--i": "init",
    "-update": "update", "--u": "update", "-version": "version", "--v": "version",
    "--version": "version", "-v": "version", "-check": "check", "--c": "check",
}


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
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "GIT_TERMINAL_PROMPT": "0"}
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return subprocess.run([str(arg) for arg in args], env=env, check=True, **kwargs)


def installed(home):
    if not (home / "install.json").is_file() or not (home / "app/scripts/agentdev.py").is_file():
        raise RuntimeError("尚未全局安装，请先执行 agentdev setup（或运行 source setup.sh）")
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
    py, entry = str(python_exe(home)), str(home / "app/scripts/agentdev.py")
    for name in ("agentdev", "adev"):
        unix = directory / name
        unix.write_text(f'#!/bin/sh\nexec {shlex.quote(py)} {shlex.quote(entry)} "$@"\n', encoding="utf-8")
        unix.chmod(0o755)
    env_file = shlex.quote(str(home / "env"))
    command = f'{shlex.quote(py)} -B {shlex.quote(entry)}'
    (home / "env").write_text(
        f'case ":$PATH:" in *{shlex.quote(":" + str(directory) + ":")}*) ;; *) export PATH={shlex.quote(str(directory))}:"$PATH" ;; esac\n'
        'agentdev() {\n'
        f'  if {command} "$@"; then\n'
        f'    case "${{1-}}" in setup|-setup|--s) . {env_file} ;; esac\n'
        '  else\n    return $?\n  fi\n}\n'
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


def install(source, home, no_path=False, repo=None):
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
    try:
        usable = py.is_file() and subprocess.run([str(py), "-B", "-m", "pip", "--version"], capture_output=True).returncode == 0
    except OSError:
        usable = False
    if not usable:
        run([sys.executable, "-m", "venv", home / "venv"])
    env = {**os.environ, "PIP_CONFIG_FILE": os.devnull, "PIP_CACHE_DIR": str(home / "cache"), "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check", *requirements(source)], env=env, check=True)
    errors = runtime_errors(py, source)
    if errors:
        raise RuntimeError("；".join(errors))
    previous = home / "app.previous"
    if previous.exists():
        raise RuntimeError(f"上次安装备份尚在，请先恢复或检查：{previous}")
    with tempfile.TemporaryDirectory(prefix="install-", dir=home) as temporary:
        staged = Path(temporary) / "app"
        staged.mkdir()
        (staged / ".agentdev-app").touch()
        for name in ("scripts", "skills"):
            shutil.copytree(source / name, staged / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (staged / "publish").mkdir()
        (staged / "publish/version").write_text(version_text(read_version(source)) + "\n", encoding="utf-8")
        for name in ("AGENTS.md", "README.md", "agentdev", "adev", "setup.sh", "install.fish"):
            shutil.copy2(source / name, staged / name)
        if (home / "app").exists():
            (home / "app").rename(previous)
        try:
            staged.rename(home / "app")
            write_launchers(home)
            if not no_path:
                configure_path(home)
            (home / "install.json").write_text(json.dumps({"repository": repo, "path_configured": not no_path}, indent=2) + "\n", encoding="utf-8")
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


def update(home, check_only=False, project=None, remote=None):
    source = installed(home)
    local = read_version(source)
    remote = remote if remote is not None else remote_version()
    print(f"AgentDevWorkSpace 版本：本地 {version_text(local)}，远端 {version_text(remote)}")
    if check_only:
        print("发现远端版本更新" if remote > local else "已是最新")
        return
    if remote > local:
        with tempfile.TemporaryDirectory(prefix="update-", dir=home) as temporary:
            checkout = Path(temporary) / "source"
            repo = metadata(home)["repository"]
            run(["git", "clone", "--depth", "1", "--branch", "master", repo, checkout], timeout=120)
            if read_version(checkout) < remote:
                raise RuntimeError("远端源码尚未包含公布的版本，本次不更新，请稍后重试")
            install(checkout, home, no_path=not metadata(home).get("path_configured", False), repo=repo)
        print(f"已更新到 {version_text(read_version(home / 'app'))}")
    else:
        print("已是最新")
    project = Path(project).absolute() if project else Path.cwd()
    if (project / "agent-workspace").is_dir():
        run([python_exe(home), home / "app/scripts/agentdev.py", "init", project])


def main(argv=None):
    if os.name != "posix":
        raise RuntimeError("仅支持 macOS 和 Linux")
    if sys.version_info < (3, 9):
        raise RuntimeError("需要 Python 3.9+")
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["_fix"]:
        fix_notes(Path(argv[1] if len(argv) > 1 else ".").absolute())
        return 0
    argv = [ALIASES.get(argv[0], argv[0]), *argv[1:]] if argv else ["help"]
    parser = argparse.ArgumentParser(prog="agentdev", description="AgentDevWorkSpace 全局安装与工作区管理")
    parser.epilog = ("别名：help / --h；setup / --s；init / --i；update / --u；version / --v；check / --c。"
                     "adev 与 agentdev 等价；不传命令时展示帮助；工作区目录名为 agent-workspace/。")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("help", help="展示各个命令")
    setup = commands.add_parser("setup", help="全局安装 / 重新安装")
    setup.add_argument("--no-path", action="store_true", help="不修改持久 PATH 或 shell 配置；source 入口仍激活当前会话")
    init = commands.add_parser("init", help="初始化当前目录的 agent-workspace/")
    init.add_argument("directory", nargs="?", default=".")
    check = commands.add_parser("check", help="检查当前工作区与 Python / pip / json5 / hook")
    check.add_argument("directory", nargs="?", default=".")
    updater = commands.add_parser("update", help="检查更新，有新版本时更新安装和当前工作区")
    updater.add_argument("--check", action="store_true", help="只检查，不安装更新")
    updater.add_argument("--project", help=argparse.SUPPRESS)
    updater.add_argument("--remote", type=version, help=argparse.SUPPRESS)
    commands.add_parser("version", help="展示当前版本号与远端版本号")
    args = parser.parse_args(argv)
    if args.command == "help":
        parser.print_help()
        return 0
    if args.command in {"setup", "init", "update"} and not shutil.which("git"):
        raise RuntimeError("需要先安装 Git，并将 git 加入 PATH")
    home = global_home()
    if args.command == "setup":
        with installation_lock(home):
            install(ROOT, home, args.no_path)
    elif args.command == "init":
        initialize(installed(home), home, Path(args.directory))
        return check_workspace(Path(args.directory))
    elif args.command == "check":
        return check_workspace(Path(args.directory))
    elif args.command == "update":
        installed(home)
        if args.check:
            update(home, True, args.project, args.remote)
        else:
            with installation_lock(home):
                update(home, False, args.project, args.remote)
    elif args.command == "version":
        source = home / "app" if (home / "install.json").is_file() else ROOT
        print(f"AgentDevWorkSpace 本地版本：{version_text(read_version(source))}")
        print(f"AgentDevWorkSpace 远端版本：{version_text(remote_version())}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"agentdev：{error}", file=sys.stderr)
        sys.exit(1)
