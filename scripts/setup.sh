#!/bin/sh
# 用法：sh <AgentSkill 路径>/setup.sh [项目根目录]（根目录的 setup.sh 是指向本文件的软链接）
# 在项目根目录初始化：AGENTS.md / CLAUDE.md 软链接、.agents/、提交校验 hook。可重复执行。
# 项目根目录优先取参数，其次取执行命令的目录，最后取包含 AgentSkill 的上层 git 仓库。
# 非 git 工程须显式传入项目根目录：照常初始化，跳过 .git/info/exclude、commit-msg hook 和项目的 git config。
set -e
# 通过根目录软链接执行时 $0 是软链接本身，先解析到 scripts/setup.sh 再定位 lib/。
self=$(readlink -f "$0" 2>/dev/null) || self=$0
. "$(cd "$(dirname "$self")/.." && pwd)/lib/root.sh"
project_root=$(resolve_root "$1" "$PWD") || true
[ -n "$project_root" ] || project_root=$(resolve_plain_root "$1") || true
# 不在任何项目中、且在 AgentSkill 目录内执行时，初始化 AgentSkill 自身（单独使用或开发 AgentSkill）。
if [ -z "$project_root" ] && [ -z "$1" ]; then
  case "$(pwd -P)/" in "$skill_dir"/*) project_root=$skill_dir ;; esac
fi
if [ -z "$project_root" ]; then
  echo "未找到项目根目录：请在项目根目录（git 仓库）执行，或传入项目根目录（非 git 工程须传入）" >&2
  exit 1
fi
if [ "$project_root" = "$skill_dir" ]; then skill_rel=.; else skill_rel=${skill_dir#"$project_root"/}; fi
cd "$project_root"

# 非 git 工程：没有 .git/info/exclude、hooks 和项目 git config，相关步骤跳过。
if git rev-parse --git-dir >/dev/null 2>&1; then is_git=1; else is_git=; fi

if [ -n "$is_git" ]; then
  exclude=$(git rev-parse --git-path info/exclude)
  mkdir -p "$(dirname "$exclude")"
  ignore() { grep -qxF "$1" "$exclude" 2>/dev/null || echo "$1" >> "$exclude"; }
else
  ignore() { :; }
fi

# AgentSkill 是独立仓库，不纳入项目版本管理。
[ "$skill_rel" = . ] || ignore "/$skill_rel/"

# 用相对路径链接，项目移动或换机器后仍有效；项目已有同名文件时不覆盖。
if [ ! -e AGENTS.md ] && [ ! -L AGENTS.md ]; then
  ln -s "$skill_rel/AGENTS.md" AGENTS.md && ignore /AGENTS.md
fi
if [ ! -e CLAUDE.md ] && [ ! -L CLAUDE.md ]; then
  ln -s AGENTS.md CLAUDE.md && ignore /CLAUDE.md
fi

mkdir -p .agents/tmp .agents/notes .agents/config

# Note 配置：开关、上限、触发 Note 的扫描规则。已有时不覆盖；缺少的键由脚本取 notes/config.json5 的默认值。
[ -e .agents/config/notes.json5 ] || cp "$skill_dir/notes/config.json5" .agents/config/notes.json5

# .agents/ 写入项目根目录的 .gitignore。已有任一等价写法（.agents、.agents/、/.agents、/.agents/）时不重复添加；
# 文件末尾缺少换行时先补一个，避免与最后一行拼接。
if ! grep -qxE '/?\.agents/?' .gitignore 2>/dev/null; then
  [ ! -s .gitignore ] || [ -z "$(tail -c1 .gitignore)" ] || echo >> .gitignore
  echo /.agents/ >> .gitignore
fi

# hook 只转发到 AgentSkill 中的脚本，AgentSkill 更新后自动生效；不覆盖项目已有的其他 hook。
if [ -n "$is_git" ]; then
  hooks=$(git rev-parse --git-path hooks)
  mkdir -p "$hooks"
  for name in commit-msg; do
    target="$hooks/$name"
    if [ -e "$target" ] && ! grep -q '# agentskill' "$target"; then
      echo "跳过：$target 已存在，请手动接入 $skill_rel/git/hooks/$name" >&2
      continue
    fi
    cat > "$target" <<HOOK
#!/bin/sh
# agentskill
f="\$(git rev-parse --show-toplevel)/$skill_rel/git/hooks/$name"
[ -x "\$f" ] || exit 0
exec "\$f" "\$@"
HOOK
    chmod +x "$target"
  done
fi

# AgentSkill 的 Python 脚本统一用 .agents/tmp/venv 中的解释器。已有且 pip 可用时跳过；
# venv 内含绝对路径，项目移动后无法运行；缺少 pip 时 deps.sh 无法安装依赖：两种情况都重建。
venv=.agents/tmp/venv
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

# verify.py 的提交基线：只检查接入之后的提交。仓库还没有提交时写空，表示从第一笔提交算起。
[ -e .agents/tmp/note-base ] || { git rev-parse -q --verify HEAD 2>/dev/null || :; } > .agents/tmp/note-base

# verify.py 自动更新的时间戳：刚初始化完，从现在开始计时。
date +%s > .agents/tmp/last-update

# 每轮对话结束时执行 verify.py：注册为 Claude Code（.claude/settings.local.json）和 Codex（.codex/hooks.json）
# 的 Stop hook。两者的事件结构相同，退出码 2 + stderr 都表示阻止结束并把 stderr 交回 Agent，共用同一条命令。
# 都是项目本地配置，不提交；已注册时不重复添加。
# 非 git 工程没有项目 git config，命令中直接写解释器和脚本的绝对路径。
ignore /.claude/settings.local.json
ignore /.codex/hooks.json
AGENTSKILL_GIT="$is_git" AGENTSKILL_PY="$py" AGENTSKILL_DIR="$skill_dir" AGENTSKILL_ROOT="$project_root" "$py" - <<'PY'
import json
import os
import re
import sys
from pathlib import Path

MARK = "# agentskill"
if os.environ["AGENTSKILL_GIT"]:
    cmd = ('p=$(git config agentskill.path) && [ -f "$p/notes/verify.py" ] && '
           f'exec "$(git config agentskill.python)" "$p/notes/verify.py"; exit 0  {MARK}')
else:
    verify = Path(os.environ["AGENTSKILL_DIR"]) / "notes" / "verify.py"
    cmd = f'[ -f "{verify}" ] && exec "{os.environ["AGENTSKILL_PY"]}" "{verify}"; exit 0  {MARK}'


def register(path, hook):
    """把 Stop hook 写进配置文件；已有带标记的命令时不重复添加。"""
    cfg = json.loads(path.read_text() or "{}") if path.exists() else {}
    stop = cfg.setdefault("hooks", {}).setdefault("Stop", [])
    if any(MARK in h.get("command", "") for e in stop for h in e.get("hooks", [])):
        return
    stop.append({"hooks": [hook]})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")


register(Path(".claude/settings.local.json"), {"type": "command", "command": cmd})
register(Path(".codex/hooks.json"), {"type": "command", "command": cmd, "statusMessage": "检查 Note"})

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

# 项目和 AgentSkill 各记一份，在两者的任意目录中都能通过 git config 找到脚本和解释器。
# 非 git 工程只记在 AgentSkill 仓库中，notes 脚本通过 agentskill.root 找到项目。
if [ -n "$is_git" ]; then
  git config agentskill.path "$skill_dir"
  git config agentskill.python "$py"
fi
git -C "$skill_dir" config agentskill.path "$skill_dir"
git -C "$skill_dir" config agentskill.python "$py"
git -C "$skill_dir" config agentskill.root "$project_root"
if [ -n "$is_git" ]; then
  echo "已初始化：${project_root}（AgentSkill 位于 ${skill_rel}）"
else
  echo "已初始化（非 git 工程）：${project_root}（AgentSkill 位于 ${skill_rel}），已跳过 .git/info/exclude、commit-msg hook 和项目 git config"
fi
