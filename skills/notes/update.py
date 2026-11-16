#!/usr/bin/env python3
"""AgentDevWorkSpace 自动更新：按版本号判断是否需要更新，需要时立即在后台进程中拉取并执行 setup.sh，调用方不等待。

触发：
- 展示欢迎语：sdd skill 的 welcome.py（SessionStart hook）和 Codex 启动入口 scripts/codex.sh 执行 `update.py --welcome`：
  当场请求远端版本（WELCOME_TIMEOUT 秒内），向 stdout 输出一行「AgentDevWorkSpace 版本：本地 X，远端 Y（状态）」供欢迎语展示；
  本地低于远端（或上次 setup.sh 失败待重试）时立即启动后台进程更新，并把已取得的远端版本传给它，不重复请求；
- 每轮结束：verify.py（Stop hook）调用 trigger()，距上次检查（agent-workspace/.agent/env/last-update）超过 auto_update_interval_hours 才检查。
远端版本：先请求 update_url（默认 GitHub API 的 contents 接口，发布后立即可见），它是 GitHub API 地址时失败再回退到 raw 地址
（raw.githubusercontent.com 有约 5 分钟 CDN 缓存，发布后短时间内可能仍是旧值）。
后台进程（--run [--remote N]）：
- 与 AgentDevWorkSpace 的 publish/version 比较；低于远端时 git pull --ff-only（AgentDevWorkSpace 工作区有改动时跳过），拉取到新版本后立即执行 setup.sh；
- 执行 setup.sh 前写入 update-ready，成功后删除；失败时保留，下次触发时先补执行 setup.sh（此时本地版本已与远端一致，不会再因版本触发）。
后台进程降低优先级（nice），同一时间只运行一个（update.lock），输出写入 update.log；失败只记日志，下次触发时再试。
不带参数执行时什么都不做：旧版本 setup.sh 注册的 SessionStart hook 仍会调用它，检查已改由欢迎语触发，避免重复请求。
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
WELCOME_TIMEOUT = 3  # 秒，欢迎语当场请求远端版本的超时，避免拖慢会话开始
RAW_URL = "https://raw.githubusercontent.com/LumenVestige/versions/main/AgentDevWorkSpace/version"
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


def spawn(*args):
    """启动脱离调用方的后台进程：新会话、不继承终端和输出管道，调用方立即返回。"""
    ENV.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as err:
        subprocess.Popen([str(ENV / "venv" / "bin" / "python"), os.path.abspath(__file__), *args],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
                         start_new_session=True, close_fds=True)


def due(root, cfg):
    """时间戳缺失、损坏或晚于当前时间（时钟回拨）时都视为到期。"""
    try:
        last = float(update_stamp_file(root).read_text().strip())
    except (OSError, ValueError):
        return True
    return not 0 <= time.time() - last < float(cfg["auto_update_interval_hours"]) * 3600


def trigger(root, cfg, now=False, remote=None):
    """now 为 True 或检查到期时写入检查时间并启动后台进程；remote 为已取得的远端版本，后台进程不再请求。
    启动了后台进程时返回 True。任何异常都不影响调用方。"""
    try:
        if not cfg.get("auto_update", True) or running():
            return False
        if not (now or due(root, cfg)):
            return False
        stamp = update_stamp_file(root)
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(f"{int(time.time())}\n")
        spawn("--run", *(["--remote", str(remote)] if remote is not None else []))
        return True
    except Exception as e:  # noqa: BLE001  hook 中不能因更新失败而报错
        log(f"触发更新失败：{e!r}")
        return False


def read_int(text):
    text = (text or "").strip()
    return int(text) if text.isdigit() else None


def local_version(skill):
    try:
        return read_int((skill / "publish" / "version").read_text(encoding="utf-8")) or 0
    except OSError:
        return 0


def fetch_remote(cfg, timeout):
    """远端版本号；先请求 update_url，它是 GitHub API 地址时失败再回退到 raw 地址。都失败时返回 None 并记日志。"""
    urls = [cfg["update_url"]]
    if urls[0].startswith("https://api.github.com/"):
        urls.append(RAW_URL)
    per = max(1.0, timeout / len(urls))
    for url in urls:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.raw", "User-Agent": "AgentDevWorkSpace-update"})
        try:
            with urllib.request.urlopen(req, timeout=per) as r:
                v = read_int(r.read(64).decode("utf-8", "ignore"))
        except Exception as e:  # noqa: BLE001
            log(f"获取远端版本失败：{url}：{e!r}")
            continue
        if v is not None:
            return v
        log(f"远端版本不是整数：{url}")
    return None


def check(root, cfg, remote=None):
    skill = skill_dir()
    if not skill:
        log(f"找不到 AgentDevWorkSpace（{ENV / 'agentskill-path'}），跳过：请重新执行 AgentDevWorkSpace 的 setup.sh")
        return
    if remote is None:
        remote = fetch_remote(cfg, FETCH_TIMEOUT * 2)
    if remote is None:
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


def welcome(root):
    """欢迎语中的版本行：当场请求远端版本；本地落后或有待重试的 setup.sh 时立即启动后台更新。"""
    cfg = load_config(root)
    skill = skill_dir()
    local = local_version(skill) if skill else None
    remote = fetch_remote(cfg, WELCOME_TIMEOUT)
    if running():
        state = "正在后台更新"
    elif local is None:
        state = "找不到 AgentDevWorkSpace，请重新执行 setup.sh"
    elif remote is None:
        state = "获取远端版本失败，后台重试" if trigger(root, cfg, now=True) else "获取远端版本失败"
    elif local < remote or READY.exists():
        if not cfg.get("auto_update", True):
            state = "有新版本，自动更新已关闭"
        else:
            state = "正在后台更新" if trigger(root, cfg, now=True, remote=remote) else "有新版本，启动更新失败"
    else:
        state = "已是最新"
    print(f"AgentDevWorkSpace 版本：本地 {local if local is not None else '未知'}，"
          f"远端 {remote if remote is not None else '未知'}（{state}）")


def main():
    root = project_root()
    args = sys.argv[1:]
    if not args:  # 旧版本注册的 SessionStart hook：检查已改由欢迎语触发
        return 0
    if args == ["--welcome"]:
        welcome(root)
        return 0
    if args[:1] != ["--run"] or not (len(args) == 1 or (len(args) == 3 and args[1] == "--remote" and args[2].isdigit())):
        sys.exit(f"用法：{sys.argv[0]} --welcome | --run [--remote <版本号>]")
    remote = int(args[2]) if len(args) == 3 else None
    os.nice(NICE)
    if not acquire():
        return 0
    try:
        if READY.exists():  # 上次拉取后 setup.sh 失败，先补执行
            log("补执行上次失败的 setup.sh")
            setup(root)
        check(root, load_config(root), remote)
    except Exception as e:  # noqa: BLE001
        log(f"更新异常：{e!r}")
    finally:
        release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
