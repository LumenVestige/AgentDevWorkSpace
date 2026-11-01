#!/bin/sh
# 用法：sh <AgentSkill 路径>/setup.sh [项目根目录]（根目录的 setup.sh 是指向本文件的软链接）
# 在项目根目录初始化：AGENTS.md / CLAUDE.md 软链接、.agents/、提交校验 hook。可重复执行。
# 项目根目录优先取参数，其次取执行命令的目录，最后取包含 AgentSkill 的上层 git 仓库。
set -e
# 通过根目录软链接执行时 $0 是软链接本身，先解析到 scripts/setup.sh 再定位 lib/。
self=$(readlink -f "$0" 2>/dev/null) || self=$0
. "$(cd "$(dirname "$self")/.." && pwd)/lib/root.sh"
project_root=$(resolve_root "$1" "$PWD") || true
# 不在任何项目中、且在 AgentSkill 目录内执行时，初始化 AgentSkill 自身（单独使用或开发 AgentSkill）。
if [ -z "$project_root" ] && [ -z "$1" ]; then
  case "$(pwd -P)/" in "$skill_dir"/*) project_root=$skill_dir ;; esac
fi
if [ -z "$project_root" ]; then
  echo "未找到项目根目录：请在项目根目录（git 仓库）执行，或传入项目根目录" >&2
  exit 1
fi
if [ "$project_root" = "$skill_dir" ]; then skill_rel=.; else skill_rel=${skill_dir#"$project_root"/}; fi
cd "$project_root"

exclude=$(git rev-parse --git-path info/exclude)
mkdir -p "$(dirname "$exclude")"
ignore() { grep -qxF "$1" "$exclude" 2>/dev/null || echo "$1" >> "$exclude"; }

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

# AgentSkill 的 Python 脚本统一用 .agents/tmp/venv 中的解释器。已有且可用时跳过；
# venv 内含绝对路径，项目移动后无法运行，此时重建。
venv=.agents/tmp/venv
py="$project_root/$venv/bin/python"
if ! "$py" -c '' 2>/dev/null; then
  command -v python3 >/dev/null || { echo "未找到 python3，请先安装 Python 3.9+" >&2; exit 1; }
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || { echo "需要 Python 3.9+，当前：$(python3 -V)" >&2; exit 1; }
  rm -rf "$venv"
  python3 -m venv "$venv" || { echo "创建 $venv 失败；Debian/Ubuntu 请先安装 python3-venv" >&2; rm -rf "$venv"; exit 1; }
fi

# 用该虚拟环境的 pip 安装依赖（清单在 deps.sh 中）；已满足时跳过。
sh "$skill_dir/scripts/deps.sh" "$py"

# verify.py 的提交基线：只检查接入之后的提交。仓库还没有提交时写空，表示从第一笔提交算起。
[ -e .agents/tmp/note-base ] || { git rev-parse -q --verify HEAD || :; } > .agents/tmp/note-base

# 每轮对话结束时执行 verify.py：注册为 Claude Code 的 Stop hook（项目本地配置，不提交）；已注册时不重复添加。
ignore /.claude/settings.local.json
"$py" - <<'PY'
import json
from pathlib import Path
p = Path(".claude/settings.local.json")
cfg = json.loads(p.read_text() or "{}") if p.exists() else {}
cmd = ('p=$(git config agentskill.path) && [ -f "$p/notes/verify.py" ] && '
       'exec "$(git config agentskill.python)" "$p/notes/verify.py"; exit 0  # agentskill')
stop = cfg.setdefault("hooks", {}).setdefault("Stop", [])
if not any("# agentskill" in h.get("command", "") for e in stop for h in e.get("hooks", [])):
    stop.append({"hooks": [{"type": "command", "command": cmd}]})
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
PY

# 项目和 AgentSkill 各记一份，在两者的任意目录中都能通过 git config 找到脚本和解释器。
git config agentskill.path "$skill_dir"
git config agentskill.python "$py"
git -C "$skill_dir" config agentskill.path "$skill_dir"
git -C "$skill_dir" config agentskill.python "$py"
git -C "$skill_dir" config agentskill.root "$project_root"
echo "已初始化：$project_root（AgentSkill 位于 $skill_rel）"
