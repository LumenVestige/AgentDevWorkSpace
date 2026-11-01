#!/usr/bin/env python3
"""每轮对话结束时执行：判断是否需要触发 Note，并按上限删除旧 Note。Note 的内容由 create.py 填充。

用法："$(git config agentskill.python)" verify.py
作为 Claude Code Stop hook 时从 stdin 读取事件 JSON；需要写 Note 时以退出码 2 把提示交回 Agent。

配置：.agents/config/notes.json5（JSON5，字段含义见其中的注释；缺少的键取 notes/config.json5 的默认值）
- enabled：false 时不触发 Note、不删除。
- max_notes：Note 超过该数量时按文件名中的时间删除最早的。
- scan：触发条件。commits 为 true 时，基线之后存在未记录到任何 Note 的提交即触发；
  include_merges 是否计入 merge 提交；paths / exclude_paths 只统计 / 不统计改动这些路径的提交（git pathspec）。

全部提交都已记录时，基线（.agents/tmp/note-base）前移到 HEAD，此后删除旧 Note 不会让这些提交重新触发。
"""
import json
import select
import sys

from common import load_config, notes_dir, project_root, reset_base, unrecorded_commits

BLOCK = 2  # Claude Code Stop hook：退出码 2 阻止结束，stderr 交给 Agent 继续处理


def hook_input():
    """Stop hook 会立即写入事件 JSON；手动执行时 stdin 可能是终端或一直不关闭的管道，等不到数据就跳过，避免卡住。"""
    try:
        if sys.stdin is None or sys.stdin.isatty() or not select.select([sys.stdin], [], [], 1)[0]:
            return {}
        return json.loads(sys.stdin.read() or "{}")
    except (OSError, ValueError):
        return {}


def prune(notes, limit):
    existing = sorted(notes.glob("*.md"))
    for old in existing[: max(0, len(existing) - limit)]:
        old.unlink()
        print(f"Note 超过 {limit} 条，已删除最早的：{old.name}", file=sys.stderr)


def main():
    event = hook_input()
    root = project_root()
    cfg = load_config(root)
    if not cfg["enabled"]:
        return 0
    notes = notes_dir(root)
    notes.mkdir(parents=True, exist_ok=True)

    pending = unrecorded_commits(root, cfg)
    if not pending:
        # 全部已记录，或基线不可用（首次执行、rebase 等）：基线前移到 HEAD。
        reset_base(root)
    prune(notes, int(cfg["max_notes"]))
    if not pending:
        return 0
    print(f"有 {len(pending)} 笔提交尚未记录到 Note，请按 AGENTS.md 写 Note：\n"
          '"$(git config agentskill.python)" "$(git config agentskill.path)/notes/create.py" <topic>', file=sys.stderr)
    # Stop hook 已经因本脚本续跑过一轮时不再阻止，避免循环。
    return 0 if event.get("stop_hook_active") else BLOCK


if __name__ == "__main__":
    sys.exit(main())
