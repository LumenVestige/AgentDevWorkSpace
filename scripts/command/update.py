"""版本检查、更新全局程序及刷新当前工作区。"""
import argparse
from pathlib import Path
import tempfile

from lib.repository import warn_installation, missing_repository
from lib.installer import (global_home, installed, installation_lock, read_version, remote_version,
                           version, version_text, metadata, run, install, python_exe, repair_repository)
from lib.update_status import UpdateTask, update_lock, show_status


def refresh(home, project, runner=None):
    runner = runner or run
    project = Path(project).absolute() if project else Path.cwd()
    if not project.resolve().is_relative_to((home / "app").resolve()) and (project / "agent-workspace").is_dir():
        runner([python_exe(home), home / "app/scripts/command/app.py", "init", project], timeout=120)


def update(home, check_only=False, project=None, remote=None, notify="auto", force=False):
    source = installed(home)
    blocked = warn_installation(home)
    local = read_version(source)
    try:
        remote = remote if remote is not None else remote_version()
    except Exception as error:
        if not check_only:
            UpdateTask(home, version_text(local), None, notify, project).finish("failed", error)
        raise
    print(f"AgentDevWorkSpace 版本：本地 {version_text(local)}，远端 {version_text(remote)}")
    if check_only:
        print("发现远端版本更新" if remote > local else "已是最新")
        return
    # Legacy upgrades without a commit still use full-install migration; there is
    # no trustworthy old commit to recover from a newer master.
    repair = missing_repository(home) and (remote <= local or bool(metadata(home).get("commit")))
    replace = remote > local or (force and blocked and not repair)
    if not replace and not repair:
        print("已是最新")
        refresh(home, project)
        return
    task = UpdateTask(home, version_text(local), version_text(remote), notify, project)
    try:
        if blocked and not repair and not force:
            error = "安装目录存在风险，已暂停更新；请先备份并处理本地改动"
            task.finish("blocked", error)
            raise RuntimeError(error)
        task.stage("downloading")
        with tempfile.TemporaryDirectory(prefix="update-", dir=home) as temporary:
            checkout = Path(temporary) / "source"
            repo = metadata(home)["repository"]
            task.run(["git", "clone", "--depth", "1", "--single-branch", "--no-tags", "--branch", "master", repo, checkout], timeout=120)
            if (replace or force) and read_version(checkout) < max(local, remote):
                raise RuntimeError("远端源码尚未包含公布的版本，本次不更新，请稍后重试")
            if repair:
                task.stage("staging")
                repair_repository(home, checkout)
                print(".git 已补齐（master）；现有源码未覆盖", flush=True)
                task.log(".git 已补齐（master）；现有源码未覆盖")
                blocked = warn_installation(home)
                if blocked and not force:
                    error = "已补齐 .git，但安装目录存在异常改动，已暂停覆盖式更新"
                    task.finish("blocked", error)
                    raise RuntimeError(error)
                replace = remote > local or (force and blocked)
            if replace:
                install(checkout, home, no_path=not metadata(home).get("path_configured", False), repo=repo, progress=task)
        task.stage("refreshing")
        refresh(home, project, task.run)
        task.value["to_version"] = version_text(read_version(home / "app"))
        task.finish("success")
        print(f"已更新到 {task.value['to_version']}" if replace else "已是最新；Git 元数据已修复")
    except BaseException as error:
        task.finish("failed", error)
        raise


def register(commands):
    parser = commands.add_parser("update", help="检查更新，强制覆盖安装目录改动并刷新当前工作区")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只检查，不安装更新")
    mode.add_argument("--status", action="store_true", help="查看安装级更新状态和日志路径")
    parser.add_argument("--watch", action="store_true", help="配合 --status 持续查看，完成 10 秒后退出")
    parser.add_argument("--notify", choices=("auto", "system", "none"), default="auto", help="通知方式；auto 统一使用系统通知，仅更新成功完成时发送")
    parser.add_argument("--project", help=argparse.SUPPRESS)
    parser.add_argument("--remote", type=version, help=argparse.SUPPRESS)
    parser.set_defaults(handler=execute)


def execute(args):
    if args.watch and not args.status:
        raise ValueError("--watch 必须配合 --status 使用")
    home = global_home()
    installed(home)
    if args.status:
        return show_status(home, args.watch)
    if args.check:
        return update(home, True, args.project, args.remote, args.notify)
    # 等待锁后重新读取 app/版本；等待者只刷新自己的项目，不再创建同一升级的任务。
    with update_lock(home):
        with installation_lock(home):
            # --project is the internal hook entry; automatic updates retain risk protection.
            update(home, False, args.project, args.remote, args.notify, force=not args.project)
