#!/usr/bin/env python3
"""会话开始时（Claude Code / Codex 的 SessionStart hook，新对话或 /clear）展示 SDD 欢迎语。

输出 JSON：systemMessage 供客户端展示（首行是 AgentDevWorkSpace 的版本号）；additionalContext 交给 Agent，说明快捷命令的处理方式。
版本号取 agent-workspace/.agent/env/agentskill-path 指向的 AgentDevWorkSpace 中的 publish/version，读不到时不显示。
Codex CLI 输入前的欢迎语由 scripts/codex.sh 启动入口打印，不要求 Agent 在首次回复复述。
读不到 welcome.md 时不输出，不影响会话。
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent  # agent-workspace/skills/<common|custom>/sdd/

try:
    text = (HERE / "welcome.md").read_text(encoding="utf-8").strip()
except OSError:
    sys.exit(0)


def version():
    try:
        skill = Path((HERE.parents[2] / ".agent" / "env" / "agentskill-path").read_text(encoding="utf-8").strip())
        v = (skill / "publish" / "version").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return v if v.isdigit() else ""


if version():
    text = f"AgentDevWorkSpace 版本：{version()}\n\n{text}"

context = ("SDD 快捷命令：用户输入「创建feature:<名称>」「创建bugfix:<名称>」「创建change:<名称>」「创建research:<名称>」"
           "（或 new_feature / new_bugfix / new_change / new_research <名称>）时，按 sdd skill 执行对应的创建脚本，再进入 SDD 流程。")
print(json.dumps({
    "systemMessage": text,
    "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context},
}, ensure_ascii=False))
