"""只读工作区检查。"""
from pathlib import Path
from lib.installer import global_home
from lib.repository import warn_installation
from lib.workspace import check_workspace


def register(commands):
    parser = commands.add_parser("check", help="只读检查安装目录改动、当前工作区与 Python / pip / json5 / hook")
    parser.add_argument("directory", nargs="?", default=".")
    parser.set_defaults(handler=execute)


def execute(args):
    home = global_home()
    blocked = warn_installation(home) if (home / "install.json").is_file() else False
    result = check_workspace(Path(args.directory))
    return result or int(blocked)
