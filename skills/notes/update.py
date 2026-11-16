#!/usr/bin/env python3
"""AgentDevWorkSpace 自动更新：按版本号判断是否需要更新，需要时立即在后台进程中拉取并执行 setup.sh，hook 不等待。

触发（hook 只启动后台进程，立即返回，不向 stdout 输出）：
- 会话开始：与欢迎语同一时机，Claude Code / Codex 的 SessionStart hook（startup、clear）执行本脚本，每次都检查；
- 每轮结束：verify.py（Stop hook）调用 trigger()，距上次检查（agent-workspace/.agent/env/last-update）超过 auto_update_interval_hours 才检查。
后台进程（--run）：
- 请求 update_url（versions 库中 AgentDevWorkSpace/version 的原始内容），与 AgentDevWorkSpace 的 publish/version 比较；
  低于远端时 git pull --ff-only（AgentDevWorkSpace 工作区有改动时跳过），拉取到新版本后立即执行 setup.sh；
- 执行 setup.sh 前写入 update-ready，成功后删除；失败时保留，下次触发时先补执行 setup.sh（此时本地版本已与远端一致，不会再因版本触发）。
后台进程降低优先级（nice），同一时间只运行一个（update.lock），输出写入 update.log；失败只记日志，下次触发时再试。
配置：agent-workspace/config/notes.json5 的 auto_update（开关）、auto_update_interval_hours、update_url。
"""
import datetime
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.dont_write_bytecode = True  # 不在工作区副本中生成 __pycache__

from common import ENV, git, load_config, project_root, skill_dir, update_stamp_file

READY = ENV / "update-ready"
LOCK = ENV / "update.lock"
LOG = ENV / "update.log"
LOG_LIMIT = 200_000  # 字节，超过时只保留后半部分
FETCH_TIMEOUT = 10  # 秒
PULL_TIMEOUT = 120  # 秒
NICE = 10


def log(msg):
    try:
        if LOG.exists() and LOG.stat().st_size > LOG_LIMIT:
            LOG.write_bytes(LOG.read_bytes()[-LOG_LIMIT // 2:])
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} [{os.getpid()}] {msg}\n")
    except OSError:
        pass


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def running():
    """已有更新进程在运行时返回 True。"""
    try:
        return alive(int(LOCK.read_text().strip()))
    except (OSError, ValueError):
        return False


def acquire():
    """取得互斥锁；已有存活的更新进程时返回 False。进程退出后遗留的锁视为失效。"""
    for _ in range(2):
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if running():
                return False
            LOCK.unlink(missing_ok=True)
            continue
        os.write(fd, f"{os.getpid()}\n".encode())
        os.close(fd)
        return True
    return False


def release():
    try:
        if LOCK.read_text().strip() == str(os.getpid()):
            LOCK.unlink()
    except OSError:
        pass


def spawn(mode):
    """启动脱离 hook 的后台进程：新会话、不继承终端，hook 立即返回。"""
    ENV.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as err:
        subprocess.Popen([str(ENV / "venv" / "bin" / "python"), os.path.abspath(__file__), mode],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
                         start_new_session=True, close_fds=True)


def due(root, cfg):
    """时间戳缺失、损坏或晚于当前时间（时钟回拨）时都视为到期。"""
    try:
        last = float(update_stamp_file(root).read_text().strip())
    except (OSError, ValueError):
        return True
    return not 0 <= time.time() - last < float(cfg["auto_update_interval_hours"]) * 3600


def trigger(root, cfg, session_start=False):
    """hook 调用：会话开始或检查到期时写入检查时间并启动后台进程。任何异常都不影响 hook。"""
    try:
        if not cfg.get("auto_update", True) or running():
            return
        if session_start or due(root, cfg):
            stamp = update_stamp_file(root)
            stamp.parent.mkdir(parents=True, exist_ok=True)
            stamp.write_text(f"{int(time.time())}\n")
            spawn("--run")
    except Exception as e:  # noqa: BLE001  hook 中不能因更新失败而报错
        log(f"触发更新失败：{e!r}")


def read_int(text):
    text = (text or "").strip()
    return int(text) if text.isdigit() else None


def local_version(skill):
    try:
        return read_int((skill / "publish" / "version").read_text(encoding="utf-8")) or 0
    except OSError:
        return 0


def check(root, cfg):
    skill = skill_dir()
    if not skill:
        log(f"找不到 AgentDevWorkSpace（{ENV / 'agentskill-path'}），跳过：请重新执行 AgentDevWorkSpace 的 setup.sh")
        return
    url = cfg["update_url"]
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as r:
            remote = read_int(r.read(64).decode("utf-8", "ignore"))
    except Exception as e:  # noqa: BLE001
        log(f"获取远端版本失败：{url}：{e!r}")
        return
    if remote is None:
        log(f"远端版本不是整数：{url}")
        return
    local = local_version(skill)
    if local >= remote:
        log(f"已是最新：本地 {local}，远端 {remote}")
        return
    log(f"发现新版本：本地 {local}，远端 {remote}，拉取 {skill}")
    if git("-C", str(skill), "status", "--porcelain", "--untracked-files=no"):
        log("AgentDevWorkSpace 工作区有改动，跳过拉取")
        return
    # 输出写临时文件而不是管道：超时只杀 git，ssh 等子进程若还持有管道，subprocess.run 会一直等下去。
    with tempfile.TemporaryFile("w+", encoding="utf-8") as out:
        try:
            r = subprocess.run(["git", "-C", str(skill), "pull", "--ff-only"], stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                               timeout=PULL_TIMEOUT, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        except subprocess.TimeoutExpired:
            log(f"拉取超时（{PULL_TIMEOUT} 秒）")
            return
        out.seek(0)
        if r.returncode:
            log(f"拉取失败：\n{out.read()}")
            return
    now = local_version(skill)
    if now <= local:
        log(f"拉取后版本仍为 {now}，未更新")
        return
    log(f"已拉取版本 {now}，执行 setup.sh")
    READY.write_text(f"{now}\n")
    setup(root)


def setup(root):
    """执行 setup.sh；成功后删除 update-ready，失败时保留，下次触发时重试。"""
    skill = skill_dir()
    if not skill:
        log("找不到 AgentDevWorkSpace，无法执行 setup.sh")
        return
    # AgentDevWorkSpace 初始化自身时 setup.sh 不接受显式根目录，靠执行目录判断。
    args = [] if root.resolve() == skill.resolve() else [str(root)]
    with LOG.open("a", encoding="utf-8") as out:
        r = subprocess.run(["sh", str(skill / "scripts" / "setup.sh"), *args], cwd=root,
                           stdin=subprocess.DEVNULL, stdout=out, stderr=out)
    if r.returncode:
        log(f"setup.sh 失败（退出码 {r.returncode}），下次触发时重试")
        return
    READY.unlink(missing_ok=True)
    log(f"已更新到版本 {local_version(skill)}")


def main():
    root = project_root()
    if len(sys.argv) == 1:  # SessionStart hook
        trigger(root, load_config(root), session_start=True)
        return 0
    if sys.argv[1:] != ["--run"]:
        sys.exit(f"用法：{sys.argv[0]} [--run]")
    os.nice(NICE)
    if not acquire():
        return 0
    try:
        if READY.exists():  # 上次拉取后 setup.sh 失败，先补执行
            log("补执行上次失败的 setup.sh")
            setup(root)
        check(root, load_config(root))
    except Exception as e:  # noqa: BLE001
        log(f"更新异常：{e!r}")
    finally:
        release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
