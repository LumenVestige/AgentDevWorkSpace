#!/usr/bin/env python3
"""AgentDevWorkSpace CLI 分发；安装请直接运行根 setup.sh。"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from command import help, init, check, update, version
from lib.installer import require_platform

ALIASES = {
    "-help": "help", "--h": "help", "--help": "help", "-h": "help",
    "-init": "init", "--i": "init", "-update": "update", "--u": "update",
    "-version": "version", "--v": "version", "--version": "version", "-v": "version",
    "-check": "check", "--c": "check",
}


def main(argv=None):
    require_platform()
    argv = list(sys.argv[1:] if argv is None else argv)
    argv = [ALIASES.get(argv[0], argv[0]), *argv[1:]] if argv else ["help"]
    parser = argparse.ArgumentParser(prog="agentdev", description="AgentDevWorkSpace 工作区管理",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.epilog = ("别名：help / --h；init / --i；update / --u；version / --v；check / --c。\n"
                     "adev 与 agentdev 等价；不传命令时展示帮助；工作区目录名为 agent-workspace/。")
    parser.set_defaults(root_parser=parser)
    commands = parser.add_subparsers(dest="command")
    for module in (help, init, check, update, version):
        module.register(commands)
    args = parser.parse_args(argv)
    if args.command in {"init", "update"} and not (args.command == "update" and args.status) and not shutil.which("git"):
        raise RuntimeError("需要先安装 Git，并将 git 加入 PATH")
    return args.handler(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"agentdev：{error}", file=sys.stderr)
        sys.exit(1)
