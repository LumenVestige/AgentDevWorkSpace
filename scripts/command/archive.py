"""按配置显式归档当前个人目录的开发记录。"""
from pathlib import Path
from lib.archive import archive_workspace


def register(commands):
    parser = commands.add_parser('archive', help='整理开发记录到 archived/NN 分组（默认保留 50 项，每组 100 项）')
    parser.add_argument('directory', nargs='?', default='.')
    parser.set_defaults(handler=execute)


def execute(args):
    archive_workspace(Path(args.directory))
    return 0
