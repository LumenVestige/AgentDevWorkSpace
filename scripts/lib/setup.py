#!/usr/bin/env python3
"""根 setup.sh 的安装实现，不是 agentdev 子命令。"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.installer import ROOT, global_home, install, installation_lock, require_platform


def main():
    require_platform()
    parser = argparse.ArgumentParser(prog="setup.sh", description="安装或重新安装 AgentDevWorkSpace")
    parser.add_argument("--no-path", action="store_true", help="不修改持久 PATH；source 仍激活当前会话")
    args = parser.parse_args()
    if not shutil.which("git"):
        raise RuntimeError("需要先安装 Git，并将 git 加入 PATH")
    home = global_home()
    with installation_lock(home):
        install(ROOT, home, args.no_path)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"setup.sh：{error}", file=sys.stderr)
        sys.exit(1)
