"""显示本地和远端版本。"""
from lib.repository import warn_installation
from lib.installer import ROOT, global_home, read_version, remote_version, version_text


def register(commands):
    parser = commands.add_parser("version", help="展示当前版本号与远端版本号")
    parser.set_defaults(handler=execute)


def execute(args):
    home = global_home()
    if (home / "install.json").is_file():
        warn_installation(home)
    source = home / "app" if (home / "install.json").is_file() else ROOT
    print(f"AgentDevWorkSpace 本地版本：{version_text(read_version(source))}")
    print(f"AgentDevWorkSpace 远端版本：{version_text(remote_version())}")
