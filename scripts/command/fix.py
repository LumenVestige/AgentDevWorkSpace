"""显式修复旧版工作区，独立于初始化和更新。"""
from pathlib import Path
from lib.fix import fix_notes


def register(commands):
    description = "修复当前工作区：迁移旧版 notes 目录（不覆盖已有文件）"
    parser = commands.add_parser("fix", help=description, description=description)
    parser.add_argument("directory", nargs="?", default=".")
    parser.set_defaults(handler=execute)


def execute(args):
    fix_notes(Path(args.directory))
    return 0
