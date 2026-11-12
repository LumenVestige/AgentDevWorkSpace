#!/bin/sh
# 用法：sh <AgentDevWorkSpace 路径>/scripts/init.sh [项目根目录]
# 初始化项目文件：AGENTS.md / CLAUDE.md 软链接，以及工作区 agent-workspace/（skills、个人目录、config、.agent）、
# .claude/skills 软链接、Note 配置与基线、.gitignore。setup.sh 会先调用本脚本；单独执行时只初始化项目文件，不安装运行环境。
# 除 agent-workspace/skills/common/ 每次覆盖外，已有的文件不覆盖，可重复执行。项目根目录的确定方式同 setup.sh。
set -e
. "$(cd "$(dirname "$0")" && pwd)/root.sh"
project_root=$(find_project_root "$1") || exit 1
if [ "$project_root" = "$skill_dir" ]; then skill_rel=.; else skill_rel=${skill_dir#"$project_root"/}; fi
cd "$project_root"
git_env

# 个人目录名取 git user.name：ASCII 字母转小写，空白、标点和控制字符换成 -，合并连续的 -，去掉首尾的 -；
# 中文等非 ASCII 字符原样保留。例如 "Tony Chen" → tony-chen。先检查，取不到时不做任何改动。
user_name=$(git config user.name || :)
user_dir=$(printf '%s' "$user_name" | LC_ALL=C tr '[:upper:]' '[:lower:]' |
  LC_ALL=C sed -e 's/[[:space:][:punct:][:cntrl:]]/-/g' -e 's/--*/-/g' -e 's/^-//' -e 's/-$//')
if [ -z "$user_dir" ]; then
  echo "未配置 git user.name（或其中没有可用字符），无法创建个人目录：请先执行 git config --global user.name <名字>" >&2
  exit 1
fi
# 个人目录与工作区的 skills/、config/ 同级，不能重名。
case "$user_dir" in skills|config)
  echo "git user.name 生成的个人目录名 ${user_dir} 与 agent-workspace/${user_dir}/ 冲突，请修改 git config user.name" >&2
  exit 1 ;;
esac

# AgentDevWorkSpace 是独立仓库，不纳入项目版本管理。
[ "$skill_rel" = . ] || ignore "/$skill_rel/"

# 项目没有 AGENTS.md 时用相对路径链接到 AgentDevWorkSpace 的 AGENTS.md，项目移动或换机器后仍有效。
# 项目已有自己的 AGENTS.md（普通文件）时不覆盖，把 AgentDevWorkSpace 的 AGENTS.md 追加到末尾，两者的规则都生效：
# 追加的内容放在标记之间，再次执行时替换标记之间的内容（随 AgentDevWorkSpace 更新），不重复追加。
# AgentDevWorkSpace 初始化自身时 AGENTS.md 就是 AgentDevWorkSpace 的，不处理。
agents_begin='<!-- agentskill:begin 以下内容由 AgentDevWorkSpace 的 init.sh 追加，重新执行时会被替换，请勿修改 -->'
agents_end='<!-- agentskill:end -->'
if [ ! -e AGENTS.md ] && [ ! -L AGENTS.md ]; then
  ln -s "$skill_rel/AGENTS.md" AGENTS.md && ignore /AGENTS.md
elif [ "$skill_rel" != . ] && [ -f AGENTS.md ] && [ ! -L AGENTS.md ]; then
  # 去掉已有的标记块和末尾空行，再追加最新内容；内容不变时不改写文件。
  # 开始标记按行首的 "<!-- agentskill:begin" 识别，标记中的说明文字改动后仍能找到旧的标记块。
  awk -v e="$agents_end" '
    index($0, "<!-- agentskill:begin") == 1 { skip = 1; next }
    $0 == e { skip = 0; next }
    skip { next }
    /^[[:space:]]*$/ { blank = blank $0 "\n"; next }
    { printf "%s", blank; blank = ""; print }
  ' AGENTS.md > AGENTS.md.agentskill
  {
    [ ! -s AGENTS.md.agentskill ] || echo
    echo "$agents_begin"
    echo
    cat "$skill_dir/AGENTS.md"
    echo
    echo "$agents_end"
  } >> AGENTS.md.agentskill
  cmp -s AGENTS.md.agentskill AGENTS.md || cat AGENTS.md.agentskill > AGENTS.md
  rm -f AGENTS.md.agentskill
elif [ -L AGENTS.md ] && [ "$(readlink AGENTS.md)" != "$skill_rel/AGENTS.md" ]; then
  echo "跳过：AGENTS.md 是指向 $(readlink AGENTS.md) 的软链接，请手动把 $skill_rel/AGENTS.md 的内容加入项目规则" >&2
fi
if [ ! -e CLAUDE.md ] && [ ! -L CLAUDE.md ]; then
  ln -s AGENTS.md CLAUDE.md && ignore /CLAUDE.md
fi

# 工作区 agent-workspace/：
# - skills/common/：AgentDevWorkSpace 的 skills/ 是通用 skill 模板包，每次执行都整体覆盖到这里，不要在 common/ 中修改；
#   skills/custom/：项目自己的 skill，从不改动；与 common/ 同名时优先加载 custom/ 中的。两者都随项目提交。
# - <个人目录>/：specs/ 是个人的自定义约束（constraints.md，从 sdd skill 的 personal-constraints.md 复制，已有时不覆盖），
#   写入 .gitignore，不提交；feature/、bugfix/、change/ 由 sdd skill 的 new_*.sh 按需创建；notes/ 存放 Note。
#   个人目录除 specs/ 外随项目提交。
# - config/：配置（notes.json5）；.agent/：env/（Python 虚拟环境、脚本状态、AgentDevWorkSpace 路径）、profiles/、evals/。
#   都是本机使用，写入 .gitignore，不提交。
ws=agent-workspace
sk="$ws/skills"
mine="$ws/$user_dir"
env_dir="$ws/.agent/env"
mkdir -p "$sk/custom" "$ws/config" "$env_dir" "$ws/.agent/profiles" "$ws/.agent/evals" \
  "$mine/specs" "$mine/notes"

# 先复制到临时目录再替换，复制失败时保留原来的 common/。模板包中的 __pycache__ 不复制。
rm -rf "$sk/common.tmp"
cp -R "$skill_dir/skills" "$sk/common.tmp"
find "$sk/common.tmp" -name __pycache__ -type d -prune -exec rm -rf {} +
rm -rf "$sk/common"
mv "$sk/common.tmp" "$sk/common"

# 空目录无法提交，custom/ 为空时放一个 .gitkeep。
[ -n "$(ls -A "$sk/custom")" ] || : > "$sk/custom/.gitkeep"

# 取实际加载的 skill 目录：custom/ 中有同名 skill 时用 custom/，否则用 common/。
skill_path() {
  if [ -d "$sk/custom/$1" ]; then echo "$sk/custom/$1"; else echo "$sk/common/$1"; fi
}
[ -e "$mine/specs/constraints.md" ] || cp "$(skill_path sdd)/personal-constraints.md" "$mine/specs/constraints.md"

# common/ 和 custom/ 中的每个 skill 链接到 .claude/skills/<名称>（Claude Code 按需加载），同名时指向 custom/。
# 用相对路径链接；已是软链接时更新指向，已有同名的普通文件或目录时不覆盖。.claude/ 可能随项目提交，链接写入 exclude。
mkdir -p .claude/skills
for s in "$sk"/common/*/ "$sk"/custom/*/; do
  [ -d "$s" ] || continue
  name=$(basename "$s")
  link=.claude/skills/$name
  if [ -L "$link" ] || [ ! -e "$link" ]; then
    rm -f "$link"
    ln -s "../../$(skill_path "$name")" "$link"
  else
    echo "跳过：$link 已存在且不是软链接，请手动接入 $(skill_path "$name")" >&2
  fi
  ignore "/$link"
done

# 工作区中的脚本通过这个文件找到 AgentDevWorkSpace（自动更新时拉取并重新执行 setup.sh）。
printf '%s\n' "$skill_dir" > "$env_dir/agentskill-path"

# Note 配置：开关、上限、触发 Note 的扫描规则。已有时不覆盖；缺少的键由脚本取 notes skill 中 config.json5 的默认值。
[ -e "$ws/config/notes.json5" ] || cp "$sk/common/notes/config.json5" "$ws/config/notes.json5"

# verify.py 的提交基线：只检查接入之后的提交。仓库还没有提交时写空，表示从第一笔提交算起。
[ -e "$env_dir/note-base" ] || { git rev-parse -q --verify HEAD 2>/dev/null || :; } > "$env_dir/note-base"

# config/、.agent/ 和所有个人目录的 specs/（/agent-workspace/*/specs/）写入项目根目录的 .gitignore，已有时跳过；文件末尾缺少换行时先补一个，避免与最后一行拼接。
for line in "/$ws/config/" "/$ws/.agent/" "/$ws/*/specs/"; do
  grep -qxF "$line" .gitignore 2>/dev/null && continue
  [ ! -s .gitignore ] || [ -z "$(tail -c1 .gitignore)" ] || echo >> .gitignore
  echo "$line" >> .gitignore
done

echo "已初始化项目文件：${project_root}（个人目录 ${mine}）"
