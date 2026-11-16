#!/bin/sh
# 用法：sh <AgentDevWorkSpace 路径>/setup.sh [项目根目录]（根目录的 setup.sh 是指向本文件的软链接）
# 接入 AgentDevWorkSpace：先执行 scripts/init.sh 初始化项目文件（AGENTS.md / CLAUDE.md 软链接、工作区 agent-workspace/
#（含 skills 副本）、.claude/skills 软链接、.gitignore）和 scripts/fix.sh（升级兼容），再安装运行环境：提交校验 hook、Python 虚拟环境与依赖、Stop hook。可重复执行。
# 项目根目录优先取参数，其次取执行命令的目录，最后取包含 AgentDevWorkSpace 的上层 git 仓库。
# 非 git 工程须显式传入项目根目录：照常初始化，跳过 .git/info/exclude 和 commit-msg hook。
set -e
# 通过根目录软链接执行时 $0 是软链接本身，先解析到 scripts/setup.sh 再定位同目录的 root.sh。
self=$(readlink -f "$0" 2>/dev/null) || self=$0
. "$(cd "$(dirname "$self")" && pwd)/root.sh"
project_root=$(find_project_root "$1") || exit 1
if [ "$project_root" = "$skill_dir" ]; then skill_rel=.; else skill_rel=${skill_dir#"$project_root"/}; fi
cd "$project_root"
git_env

# 项目文件的初始化都在 init.sh 中。AgentDevWorkSpace 初始化自身时不接受显式根目录，在 AgentDevWorkSpace 目录内不带参数执行。
# init.sh 之后执行 fix.sh，把旧版本留下的工作区文件改成新版本的格式（升级兼容）。
if [ "$project_root" = "$skill_dir" ]; then
  sh "$skill_dir/scripts/init.sh"
  sh "$skill_dir/scripts/fix.sh"
else
  sh "$skill_dir/scripts/init.sh" "$project_root"
  sh "$skill_dir/scripts/fix.sh" "$project_root"
fi

# hook 只转发到工作区 git-commit skill 中的脚本（agent-workspace/skills/common/，init.sh 每次覆盖）；不覆盖项目已有的其他 hook。
if [ -n "$is_git" ]; then
  hooks=$(git rev-parse --git-path hooks)
  mkdir -p "$hooks"
  for name in commit-msg; do
    target="$hooks/$name"
    if [ -e "$target" ] && ! grep -q '# agentskill' "$target"; then
      echo "跳过：$target 已存在，请手动接入 agent-workspace/skills/common/git-commit/$name" >&2
      continue
    fi
    cat > "$target" <<HOOK
#!/bin/sh
# agentskill
f="\$(git rev-parse --show-toplevel)/agent-workspace/skills/common/git-commit/$name"
[ -x "\$f" ] || exit 0
exec "\$f" "\$@"
HOOK
    chmod +x "$target"
  done
fi

# AgentDevWorkSpace 的 Python 脚本统一用 agent-workspace/.agent/env/venv 中的解释器。已有且 pip 可用时跳过；
# venv 内含绝对路径，项目移动后无法运行；缺少 pip 时 deps.sh 无法安装依赖：两种情况都重建。
venv=agent-workspace/.agent/env/venv
py="$project_root/$venv/bin/python"
if ! "$py" -m pip --version >/dev/null 2>&1; then
  command -v python3 >/dev/null || { echo "未找到 python3，请先安装 Python 3.9+" >&2; exit 1; }
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || { echo "需要 Python 3.9+，当前：$(python3 -V)" >&2; exit 1; }
  rm -rf "$venv"
  python3 -m venv "$venv" || { echo "创建 $venv 失败；Debian/Ubuntu 请先安装 python3-venv" >&2; rm -rf "$venv"; exit 1; }
fi

# 用该虚拟环境的 pip 安装依赖（清单在 deps.sh 中）；已满足时跳过。
sh "$skill_dir/scripts/deps.sh" "$py"
# 检查虚拟环境与依赖是否安装成功，失败时中止。
sh "$skill_dir/scripts/check.sh" "$py"

# 自动更新（notes skill 的 update.py）上次版本检查的时间戳：刚初始化完，从现在开始计时。
date +%s > agent-workspace/.agent/env/last-update

# 注册 Claude Code（.claude/settings.local.json）和 Codex（.codex/hooks.json）的 hook，两者的事件结构相同，共用同一条命令：
# - Stop：每轮对话结束时执行 notes skill 的 verify.py 和 sdd skill 的 check_layout.py（需求目录中新增的文件是否已归类），
#   退出码 2 + stderr 表示阻止结束并把 stderr 交回 Agent；
# - SessionStart（startup、clear，即新对话和 /clear）：执行 sdd skill 的 welcome.py，展示 SDD 快捷命令的欢迎语；
#   执行 notes skill 的 update.py，在后台检查 AgentDevWorkSpace 的版本，有新版本时拉取，LLM 任务结束后再执行 setup.sh。
# 执行工作区中的脚本，custom/ 中有同名 skill 的该脚本时优先。都是项目本地配置，不提交；同一事件已注册时不重复添加。
# git 工程按仓库根目录定位，项目移动后仍有效；非 git 工程命令中直接写项目根目录的绝对路径。
ignore /.claude/settings.local.json
ignore /.codex/hooks.json
AGENTSKILL_GIT="$is_git" AGENTSKILL_ROOT="$project_root" "$py" - <<'PY'
import json
import os
import re
import sys
from pathlib import Path

MARK = "# agentskill"


def command(skill, script):
    """用工作区 venv 执行 skill 中的脚本：优先 custom/<skill>/，没有时用 common/<skill>/；脚本不存在时什么都不做。"""
    if os.environ["AGENTSKILL_GIT"]:
        r, prefix = '"$r"', "r=$(git rev-parse --show-toplevel 2>/dev/null) && "
    else:
        r, prefix = f'"{os.environ["AGENTSKILL_ROOT"]}"', ""
    ws = f"{r}/agent-workspace"
    return (f'{prefix}f={ws}/skills/custom/{skill}/{script}; [ -f "$f" ] || f={ws}/skills/common/{skill}/{script}; '
            f'[ -f "$f" ] && exec {ws}/.agent/env/venv/bin/python "$f"; exit 0  {MARK}')


def register(path, event, hook, script, matcher=None):
    """把 hook 写进配置文件的 event 下；该事件已有执行同一脚本（<skill>/<脚本>）的带标记命令时不重复添加，
    同一事件可以注册多个不同脚本的 hook。"""
    cfg = json.loads(path.read_text() or "{}") if path.exists() else {}
    entries = cfg.setdefault("hooks", {}).setdefault(event, [])
    if any(MARK in c and f"/{script}" in c for e in entries for c in (h.get("command", "") for h in e.get("hooks", []))):
        return
    entries.append({**({"matcher": matcher} if matcher else {}), "hooks": [hook]})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")


verify = command("notes", "verify.py")
layout = command("sdd", "check_layout.py")
welcome = command("sdd", "welcome.py")
updater = command("notes", "update.py")
claude, codex = Path(".claude/settings.local.json"), Path(".codex/hooks.json")
register(claude, "Stop", {"type": "command", "command": verify}, "notes/verify.py")
register(codex, "Stop", {"type": "command", "command": verify, "statusMessage": "检查 Note"}, "notes/verify.py")
register(claude, "Stop", {"type": "command", "command": layout}, "sdd/check_layout.py")
register(codex, "Stop", {"type": "command", "command": layout, "statusMessage": "检查需求目录归类"}, "sdd/check_layout.py")
register(claude, "SessionStart", {"type": "command", "command": welcome}, "sdd/welcome.py", matcher="startup|clear")
register(codex, "SessionStart", {"type": "command", "command": welcome}, "sdd/welcome.py", matcher="startup|clear")
register(claude, "SessionStart", {"type": "command", "command": updater}, "notes/update.py", matcher="startup|clear")
register(codex, "SessionStart", {"type": "command", "command": updater}, "notes/update.py", matcher="startup|clear")

# Codex 的项目级 hook 只在项目被信任时加载，这里只提示，不改动用户的全局配置。
# Codex 对 hook 本身还有一道信任（按命令的哈希），首次启动时在界面中确认，不在这里代替用户决定。
codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
root = os.environ["AGENTSKILL_ROOT"]
try:
    text = (codex_home / "config.toml").read_text(encoding="utf-8")
except OSError:
    text = ""
quoted = re.escape(root)
section = re.search(rf'^\[projects\.(?:"{quoted}"|\'{quoted}\')\]\s*$(.*?)(?=^\[|\Z)', text, re.M | re.S)
if not (section and re.search(r'^\s*trust_level\s*=\s*"trusted"', section.group(1), re.M)):
    print(f'提示：Codex 的项目级 hook 需要先信任本项目，否则 .codex/hooks.json 不会加载。'
          f'可在 Codex 中信任本项目，或在 {codex_home / "config.toml"} 中加入：\n'
          f'[projects."{root}"]\ntrust_level = "trusted"', file=sys.stderr)
PY

# deps.sh / check.sh 单独执行时，默认从 AgentDevWorkSpace 仓库的 git config 取解释器。
# 工作区中的脚本不依赖 git config：按自身位置找到项目，按 agent-workspace/.agent/env/agentskill-path 找到 AgentDevWorkSpace。
git -C "$skill_dir" config agentskill.python "$py"
if [ -n "$is_git" ]; then
  echo "已初始化：${project_root}（AgentDevWorkSpace 位于 ${skill_rel}）"
else
  echo "已初始化（非 git 工程）：${project_root}（AgentDevWorkSpace 位于 ${skill_rel}），已跳过 .git/info/exclude 和 commit-msg hook"
fi
