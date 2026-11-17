"""只读工作区检查。"""
from pathlib import Path
from lib.workspace import check_workspace


def register(commands):
    parser = commands.add_parser("check", help="检查当前工作区与 Python / pip / json5 / hook")
    parser.add_argument("directory", nargs="?", default=".")
    parser.set_defaults(handler=execute)


def execute(args):
    return check_workspace(Path(args.directory))
