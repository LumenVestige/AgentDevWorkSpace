"""初始化当前工作区并检查。"""
from pathlib import Path
from lib.installer import global_home, installed
from lib.workspace import initialize, check_workspace


def register(commands):
    parser = commands.add_parser("init", help="初始化当前目录的 agent-workspace/")
    parser.add_argument("directory", nargs="?", default=".")
    parser.set_defaults(handler=execute)


def execute(args):
    home = global_home()
    project = Path(args.directory)
    initialize(installed(home), home, project)
    return check_workspace(project)
