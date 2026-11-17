"""显示 CLI 帮助。"""


def register(commands):
    parser = commands.add_parser("help", help="展示各个命令")
    parser.set_defaults(handler=execute)


def execute(args):
    args.root_parser.print_help()
