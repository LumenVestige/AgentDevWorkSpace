#!/bin/sh
# 用法：sh <AgentSkill 路径>/setup.sh [项目根目录]
# 在项目根目录初始化：AGENTS.md / CLAUDE.md 软链接、.agents/、提交校验 hook。可重复执行。
# 项目根目录优先取参数，其次取执行命令的目录，最后取包含 AgentSkill 的上层 git 仓库。
set -e
. "$(cd "$(dirname "$0")" && pwd)/lib/root.sh"
project_root=$(resolve_root "$1" "$PWD") || true
if [ -z "$project_root" ]; then
  echo "未找到项目根目录：请在项目根目录（git 仓库）执行，或传入项目根目录" >&2
  exit 1
fi
skill_rel=${skill_dir#"$project_root"/}
cd "$project_root"

exclude=$(git rev-parse --git-path info/exclude)
mkdir -p "$(dirname "$exclude")"
ignore() { grep -qxF "$1" "$exclude" 2>/dev/null || echo "$1" >> "$exclude"; }

# AgentSkill 是独立仓库，不纳入项目版本管理。
ignore "/$skill_rel/"

# 用相对路径链接，项目移动或换机器后仍有效；项目已有同名文件时不覆盖。
if [ ! -e AGENTS.md ] && [ ! -L AGENTS.md ]; then
  ln -s "$skill_rel/AGENTS.md" AGENTS.md && ignore /AGENTS.md
fi
if [ ! -e CLAUDE.md ] && [ ! -L CLAUDE.md ]; then
  ln -s AGENTS.md CLAUDE.md && ignore /CLAUDE.md
fi

mkdir -p .agents/tmp .agents/notes

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

# 项目和 AgentSkill 各记一份，在两者的任意目录中都能通过 git config agentskill.path 找到脚本。
git config agentskill.path "$skill_dir"
git -C "$skill_dir" config agentskill.path "$skill_dir"
git -C "$skill_dir" config agentskill.root "$project_root"
echo "已初始化：$project_root（AgentSkill 位于 $skill_rel）"
