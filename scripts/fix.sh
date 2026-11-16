#!/bin/sh
# 用法：sh <AgentDevWorkSpace 路径>/scripts/fix.sh [项目根目录]
# 处理 AgentDevWorkSpace 升级引入的兼容问题：把旧版本留下的工作区文件改成新版本的格式。setup.sh 在 init.sh 之后自动调用，也可单独执行。
# 每项修复都可重复执行：已是新格式的不再处理，目标已存在时跳过并提示，不覆盖、不删除内容。项目根目录的确定方式同 setup.sh。
# 新增兼容逻辑时，在下面加一个 fix_<名称> 函数，并加到文件末尾的执行列表中。
set -e
. "$(cd "$(dirname "$0")" && pwd)/root.sh"
project_root=$(find_project_root "$1") || exit 1
cd "$project_root"

# 个人目录名，与 init.sh 一致：git user.name 的 ASCII 字母转小写，空白、标点和控制字符换成 -，合并连续的 -，去掉首尾的 -。
user_dir=$(git config user.name 2>/dev/null | LC_ALL=C tr '[:upper:]' '[:lower:]' |
  LC_ALL=C sed -e 's/[[:space:][:punct:][:cntrl:]]/-/g' -e 's/--*/-/g' -e 's/^-//' -e 's/-$//')
[ -n "$user_dir" ] || { echo "fix：未配置 git user.name，跳过" >&2; exit 0; }

# Note 按类型、按天归档（notes skill）：旧版本平铺在 notes/ 下的 yy-MM-dd-HH-mm-ss-<topic>.md
# 移到 notes/git-commit-change/<20yy-MM-dd>/HH-mm-ss-<topic>.md（旧 Note 都因提交触发）。只处理当前用户的个人目录。
fix_flat_notes() {
  notes=agent-workspace/$user_dir/notes
  n=0
  for f in "$notes"/*.md; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    case "$name" in
      [0-9][0-9]-[01][0-9]-[0-3][0-9]-[0-2][0-9]-[0-5][0-9]-[0-5][0-9]-?*.md) ;;
      *) echo "fix：$f 不是旧版本的 Note 文件名，未处理" >&2; continue ;;
    esac
    dir=$notes/git-commit-change/20$(printf '%s' "$name" | cut -c1-8)
    target=$dir/$(printf '%s' "$name" | cut -c10-)
    if [ -e "$target" ]; then
      echo "fix：$target 已存在，未移动 $f" >&2
      continue
    fi
    mkdir -p "$dir"
    mv "$f" "$target"
    n=$((n + 1))
  done
  [ "$n" -eq 0 ] || echo "fix：已把 $n 条旧 Note 归类到 $notes/git-commit-change/<YYYY-MM-DD>/"
}

fix_flat_notes
