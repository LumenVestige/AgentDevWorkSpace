#!/usr/bin/env python3
"""每轮对话结束时执行：检查是否需要写 Note、Note 是否超出上限。

用法："$(git config agentskill.python)" verify.py
作为 Claude Code Stop hook 时从 stdin 读取事件 JSON；需要写 Note 时以退出码 2 把原因交回 Agent。

规则：
1. 触发 Note：基线之后存在提交，且提交的 hash 没有出现在任何 Note 中（`## Git 提交` 保留的 git log --oneline）。
   全部提交都已记录时，基线前移到 HEAD，此后删除旧 Note 不会让这些提交重新变成未记录。
2. 上限删除：Note 超过 MAX_NOTES 条时，按文件名中的时间删除最早的 Note。
"""
import json
import re
import select
import sys

from common import git, notes_dir, project_root

MAX_NOTES = 30
BLOCK = 2  # Claude Code Stop hook：退出码 2 阻止结束，stderr 交给 Agent 继续处理


def hook_input():
    """Stop hook 会立即写入事件 JSON；手动执行时 stdin 可能是终端或一直不关闭的管道，等不到数据就跳过，避免卡住。"""
    try:
        if sys.stdin is None or sys.stdin.isatty() or not select.select([sys.stdin], [], [], 1)[0]:
            return {}
        return json.loads(sys.stdin.read() or "{}")
    except (OSError, ValueError):
        return {}


def prune(notes):
    existing = sorted(notes.glob("*.md"))
    for old in existing[: max(0, len(existing) - MAX_NOTES)]:
        old.unlink()
        print(f"Note 超过 {MAX_NOTES} 条，已删除最早的：{old.name}", file=sys.stderr)


def unrecorded_commits(root, notes):
    """返回尚未记录到 Note 的提交（git log --oneline 行）；全部已记录时前移基线。"""
    state = root / ".agents" / "tmp" / "note-base"
    head = git("-C", str(root), "rev-parse", "-q", "--verify", "HEAD")
    if not state.exists():
        # 首次执行：以当前 HEAD 为基线，不追溯历史提交。
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(head + "\n")
        return []
    if not head:
        return []
    # 基线为空表示仓库在 setup 时还没有提交，从第一笔提交算起。
    base = state.read_text().strip()
    if base and not git("-C", str(root), "rev-parse", "-q", "--verify", f"{base}^{{commit}}"):
        # 基线已不存在（rebase、reset 等）：重置为 HEAD。
        state.write_text(head + "\n")
        return []
    rng = f"{base}..HEAD" if base else "HEAD"
    commits = git("-C", str(root), "log", "--no-merges", "--format=%H%x09%h %s", rng).splitlines()
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in notes.glob("*.md"))
    recorded = set(re.findall(r"\b[0-9a-f]{7,40}\b", text))
    missing = []
    for line in commits:
        full, oneline = line.split("\t", 1)
        if not any(full.startswith(h) for h in recorded):
            missing.append(oneline)
    if not missing:
        state.write_text(head + "\n")
    return missing


def main():
    event = hook_input()
    root = project_root()
    notes = notes_dir(root)
    notes.mkdir(parents=True, exist_ok=True)

    missing = unrecorded_commits(root, notes)
    prune(notes)
    if not missing:
        return 0
    print("以下提交尚未记录到 Note：\n" + "\n".join(missing) +
          "\n请按 AGENTS.md 写入或更新 Note，并在 `## Git 提交` 中保留这些提交的 git log --oneline。", file=sys.stderr)
    # Stop hook 已经因本脚本续跑过一轮时不再阻止，避免循环。
    return 0 if event.get("stop_hook_active") else BLOCK


if __name__ == "__main__":
    sys.exit(main())
