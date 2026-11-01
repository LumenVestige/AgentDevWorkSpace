"""notes 脚本共用：git 调用与项目根目录定位。"""
import os
import subprocess
import sys
from pathlib import Path

# hook 环境会导出 GIT_DIR，影响 git -C 的结果。
for var in ("GIT_DIR", "GIT_WORK_TREE"):
    os.environ.pop(var, None)

HERE = Path(__file__).resolve().parent


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
