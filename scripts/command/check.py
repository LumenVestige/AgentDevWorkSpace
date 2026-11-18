"""只读工作区检查。"""
from pathlib import Path
from lib.installer import global_home
from lib.repository import warn_installation
from lib.workspace import check_workspace


def register(commands):
    parser = commands.add_parser("check", help="只读检查环境、hook 及历史 personal/Note 迁移，待迁移时提示 agentdev fix")
    parser.add_argument("directory", nargs="?", default=".")
    parser.set_defaults(handler=execute)


def execute(args):
    home = global_home()
    blocked = warn_installation(home) if (home / "install.json").is_file() else False
    result = check_workspace(Path(args.directory))
    return result or int(blocked)
