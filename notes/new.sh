#!/bin/sh
# 在项目根目录的 .agents/notes/ 下按模板创建 Note，在任意目录执行都可以。
set -e
usage="用法：$0 <proposed|implemented> <feature|fix|del|update> <topic-in-kebab-case>"
[ $# -eq 3 ] || { echo "$usage" >&2; exit 1; }
case $1 in proposed|implemented) ;; *) echo "$usage" >&2; exit 1 ;; esac
case $2 in feature|fix|del|update) ;; *) echo "$usage" >&2; exit 1 ;; esac
echo "$3" | grep -qE '^[a-z0-9]+(-[a-z0-9]+)*$' || { echo "topic 只能用小写字母、数字和 -：$3" >&2; exit 1; }
here=$(cd "$(dirname "$0")" && pwd)
. "$here/../lib/root.sh"
# setup.sh 记录的根目录优先；未初始化时按执行目录推断；不在任何项目中时，记录到 AgentSkill 自身仓库。
project_root=$(git -C "$skill_dir" config agentskill.root || resolve_root "$PWD" || true)
[ -n "$project_root" ] || project_root=$skill_dir
file="$project_root/.agents/notes/$1/$2/$(date +%F)-$3.md"
[ ! -e "$file" ] || { echo "已存在：$file" >&2; exit 1; }
mkdir -p "$(dirname "$file")"
cp "$here/template.md" "$file"
echo "$file"
