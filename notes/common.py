"""notes 脚本共用：git 调用、项目根目录定位、配置读取与未记录提交扫描。"""
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

try:
    import json5
except ImportError:
    sys.exit(f"缺少依赖 json5：请执行 sh {HERE.parent}/scripts/deps.sh 安装到虚拟环境，并用 git config agentskill.python 指向的解释器运行")

# hook 环境会导出 GIT_DIR，影响 git -C 的结果。
for var in ("GIT_DIR", "GIT_WORK_TREE"):
    os.environ.pop(var, None)


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def resolve_root(skill_dir, candidate):
    """与 lib/root.sh 一致：候选目录须是 git 仓库根目录、AgentSkill 位于其下且不是 AgentSkill 自身；否则取包含 AgentSkill 的上层仓库。"""
    d = Path(candidate).resolve()
    if d != skill_dir and skill_dir.is_relative_to(d) and git("-C", str(d), "rev-parse", "--show-toplevel") == str(d):
        return d
    top = git("-C", str(skill_dir.parent), "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def project_root():
    """setup.sh 记录的根目录优先；未初始化时按执行目录推断；不在任何项目中时，用 AgentSkill 自身仓库。"""
    top = git("-C", str(HERE), "rev-parse", "--show-toplevel")
    if not top:
        sys.exit(f"{HERE} 不在 git 仓库中")
    skill_dir = Path(top).resolve()
    recorded = git("-C", str(skill_dir), "config", "agentskill.root")
    return Path(recorded) if recorded else resolve_root(skill_dir, Path.cwd()) or skill_dir


def notes_dir(root):
    return root / ".agents" / "notes"


def base_file(root):
    return root / ".agents" / "tmp" / "note-base"


def update_stamp_file(root):
    return root / ".agents" / "tmp" / "last-update"


def load_config(root):
    """读取 .agents/config/notes.json5，缺少的键用 AgentSkill 的默认配置 notes/config.json5 补齐。"""
    cfg = json5.loads((HERE / "config.json5").read_text(encoding="utf-8"))
    p = root / ".agents" / "config" / "notes.json5"
    if p.exists():
        try:
            user = json5.loads(p.read_text(encoding="utf-8") or "{}")
        except ValueError as e:
            sys.exit(f"配置文件格式错误：{p}：{e}")
        scan = {**cfg["scan"], **user.get("scan", {})}
        cfg.update(user)
        cfg["scan"] = scan
    return cfg


def recorded_hashes(notes):
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in notes.glob("*.md"))
    return set(re.findall(r"\b[0-9a-f]{7,40}\b", text))


def unrecorded_commits(root, cfg):
    """按扫描配置返回基线之后、hash 未出现在任何 Note 中的提交，元素为 (完整 hash, git log --oneline 行)，从新到旧。

    返回 None 表示基线不可用（首次执行或基线已失效），调用方应把基线重置为 HEAD。
    """
    scan = cfg["scan"]
    if not scan.get("commits", True):
        return []
    state = base_file(root)
    if not state.exists():
        return None
    if not git("-C", str(root), "rev-parse", "-q", "--verify", "HEAD"):
        return []
    # 基线为空表示 setup 时仓库还没有提交，从第一笔提交算起。
    base = state.read_text().strip()
    if base and not git("-C", str(root), "rev-parse", "-q", "--verify", f"{base}^{{commit}}"):
        return None
    args = ["-C", str(root), "log", "--format=%H%x09%h %s", f"{base}..HEAD" if base else "HEAD"]
    if not scan.get("include_merges", False):
        args.append("--no-merges")
    pathspec = list(scan.get("paths", [])) + [f":(exclude){p}" for p in scan.get("exclude_paths", [])]
    if pathspec:
        args += ["--", *pathspec]
    recorded = recorded_hashes(notes_dir(root))
    result = []
    for line in filter(None, git(*args).splitlines()):
        full, oneline = line.split("\t", 1)
        if not any(full.startswith(h) for h in recorded):
            result.append((full, oneline))
    return result


def reset_base(root):
    state = base_file(root)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(git("-C", str(root), "rev-parse", "-q", "--verify", "HEAD") + "\n")
