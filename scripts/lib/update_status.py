"""安装级更新状态、日志与 best-effort 桌面通知；运行文件不进入 app 工作树。"""
from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

STAGES = {
    "checking": "检查安装目录", "downloading": "下载源码", "dependencies": "安装依赖",
    "validating": "验证运行环境", "staging": "准备安装文件", "activating": "切换安装",
    "refreshing": "刷新工作区", "finished": "更新完成",
}
RESULTS = {"running": "更新中", "success": "更新成功", "failed": "更新失败", "blocked": "更新已暂停"}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def read_status(home):
    try:
        value = json.loads((Path(home) / "update-status.json").read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            return None
        if not isinstance(value.get("result"), str) or value["result"] not in RESULTS:
            return None
        if any(not isinstance(value.get(key), str) for key in ("task_id", "stage", "log_path")):
            return None
        if value["result"] != "running":
            if any(not isinstance(value.get(key), (int, float)) or not math.isfinite(value[key])
                   for key in ("finished_at", "expires_at")):
                return None
        return value
    except (OSError, ValueError):
        return None


def notification_mode(requested="auto"):
    mode = requested if requested != "auto" else os.environ.get("AGENTDEV_NOTIFY", "auto")
    if mode not in {"auto", "system", "none"}:
        mode = "auto"
    if mode != "auto":
        return mode
    client = os.environ.get("AGENTDEV_CLIENT", "").lower()
    return "none" if client == "claude" or (not client and os.environ.get("CLAUDECODE")) else "system"


def desktop_notify(title, text):
    """不使用 shell，也不拼接 AppleScript 内容；缺少桌面或通知服务时静默降级。"""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return False
    if sys.platform == "darwin" and shutil.which("osascript"):
        script = 'on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run'
        command = ["osascript", "-e", script, "--", title, text]
    elif sys.platform.startswith("linux") and shutil.which("notify-send") and any(
            os.environ.get(name) for name in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS")):
        command = ["notify-send", "--app-name=AgentDevWorkSpace", "--expire-time=10000", "--", title, text]
    else:
        return False
    try:
        return subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@contextmanager
def update_lock(home, timeout=300):
    """内核持有锁，进程异常退出也会释放；等待者不创建任务或覆盖活跃状态。"""
    home = Path(home)
    if home.is_symlink():
        raise RuntimeError("安装目录不能是符号链接")
    home.mkdir(parents=True, exist_ok=True)
    with (home / ".update.lock").open("a+") as stream:
        started, announced = time.monotonic(), False
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not announced:
                    print("AgentDevWorkSpace：已有更新任务，等待完成后复用结果", flush=True)
                    announced = True
                if time.monotonic() - started >= timeout:
                    raise RuntimeError("等待现有更新超时；可用 agentdev update --status 查看状态")
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def error_text(error, stage):
    # Command exceptions may contain credential-bearing repository URLs in argv.
    # Keep command/output details in the local log, never in status or toasts.
    if isinstance(error, subprocess.CalledProcessError):
        return f"{STAGES.get(stage, stage)}失败（退出码 {error.returncode}，详见日志）"
    if isinstance(error, subprocess.TimeoutExpired):
        return f"{STAGES.get(stage, stage)}超时（{error.timeout} 秒，详见日志）"
    if isinstance(error, KeyboardInterrupt):
        return "用户中断更新"
    return str(error) or type(error).__name__


class UpdateTask:
    def __init__(self, home, local, target, notify="auto", project=None):
        self.home = Path(home)
        self.path = self.home / "update-status.json"
        self.mode = notification_mode(notify)
        task_id = uuid.uuid4().hex
        now = time.time()
        self.value = {
            "schema_version": 1, "task_id": task_id, "pid": os.getpid(),
            "client": os.environ.get("AGENTDEV_CLIENT", "cli"), "stage": "checking",
            "started_at": now, "updated_at": now, "finished_at": None, "expires_at": None,
            "from_version": local, "to_version": target, "result": "running", "error": None,
            "project": str(project) if project else None,
            "log_path": str((self.home / "logs" / f"update-{task_id}.log").absolute()),
        }
        Path(self.value["log_path"]).parent.mkdir(parents=True, exist_ok=True)
        self.started_notification = False
        self.stage("checking")

    def log(self, text):
        with Path(self.value["log_path"]).open("a", encoding="utf-8") as stream:
            stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")

    def stage(self, stage):
        self.value.update(stage=stage, updated_at=time.time())
        atomic_json(self.path, self.value)
        message = f"AgentDevWorkSpace · {STAGES.get(stage, stage)}"
        self.log(message)
        print(message, flush=True)

    def announce(self):
        if self.started_notification:
            return
        self.started_notification = True
        if self.mode == "system":
            desktop_notify("AgentDevWorkSpace", f"开始更新：{self.value['from_version']} → {self.value['to_version']}")

    def run(self, args, **kwargs):
        # 子进程完整输出写入安装级日志；终端只展示阶段，不往客户端界面刷屏。
        from .installer import run
        with Path(self.value["log_path"]).open("a", encoding="utf-8") as stream:
            return run(args, stdout=stream, stderr=subprocess.STDOUT, **kwargs)

    def finish(self, result, error=None):
        if self.value["result"] != "running":
            return
        now = time.time()
        error = error_text(error, self.value["stage"]) if error is not None else None
        self.value.update(result=result, failed_stage=self.value["stage"] if error else None,
                          stage="finished", error=str(error) if error else None,
                          updated_at=now, finished_at=now, expires_at=now + 10)
        atomic_json(self.path, self.value)
        text = f"{RESULTS[result]}：{self.value['from_version']} → {self.value['to_version'] or '未知'}"
        if error:
            text += f"；{error}"
        self.log(text)
        print(f"AgentDevWorkSpace · {text}\n更新日志：{self.value['log_path']}", flush=True)
        if self.mode == "system":
            desktop_notify("AgentDevWorkSpace", text[:240])


def status_text(value):
    if not value:
        return "暂无更新任务状态"
    text = f"AgentDevWorkSpace · {RESULTS[value['result']]}"
    if value["result"] == "running":
        text += f" · {STAGES.get(value.get('stage'), value.get('stage', '未知阶段'))}"
    if value.get("error"):
        text += f" · {value['error']}"
    return text


def show_status(home, watch=False):
    last = None
    while True:
        value = read_status(home)
        text = status_text(value)
        identity = (value.get("task_id") if value else None, text)
        if identity != last:
            print(text, flush=True)
            if value:
                print(f"任务：{value['task_id']}\n日志：{value['log_path']}", flush=True)
            last = identity
        if not watch or not value:
            return
        if value.get("result") != "running" and time.time() >= value.get("expires_at", 0):
            return
        time.sleep(0.2)
