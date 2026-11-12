# 供 setup.sh、init.sh source，不单独执行。设置 skill_dir（AgentSkill 仓库目录），
# 提供 resolve_root、resolve_plain_root、find_project_root、git_env、ignore。
# hook 环境会导出指向 AgentSkill 自身的 GIT_DIR，先清除，避免对项目执行 git 命令时用错仓库。
unset GIT_DIR GIT_WORK_TREE
skill_dir=$(cd "$(dirname "$0")" && git rev-parse --show-toplevel) || exit 1
skill_dir=$(cd "$skill_dir" && pwd -P)

# 输出项目根目录。按参数顺序取第一个满足条件的目录：是 git 仓库根目录、AgentSkill 位于其下、且不是 AgentSkill 自身。
# 都不满足时，退回到包含 AgentSkill 的上层 git 仓库。
resolve_root() {
  for d in "$@"; do
    [ -n "$d" ] && [ -d "$d" ] || continue
    d=$(cd "$d" && pwd -P)
    case "$d/" in "$skill_dir"/*) continue ;; esac
    case "$skill_dir/" in "$d"/*) ;; *) continue ;; esac
    [ "$(git -C "$d" rev-parse --show-toplevel 2>/dev/null)" = "$d" ] && { echo "$d"; return 0; }
  done
  git -C "$skill_dir/.." rev-parse --show-toplevel 2>/dev/null
}

# 非 git 工程：显式传入的目录不在任何 git 仓库中、AgentSkill 位于其下且不是 AgentSkill 自身时，输出该目录。
# 只接受显式参数，不从执行目录推断，避免把 $HOME 之类的上层目录误当成项目根目录。
resolve_plain_root() {
  d=$1
  [ -n "$d" ] && [ -d "$d" ] || return 1
  d=$(cd "$d" && pwd -P)
  case "$d/" in "$skill_dir"/*) return 1 ;; esac
  case "$skill_dir/" in "$d"/*) ;; *) return 1 ;; esac
  git -C "$d" rev-parse --git-dir >/dev/null 2>&1 && return 1
  echo "$d"
}

# 输出项目根目录：优先取参数，其次取执行命令的目录，最后取包含 AgentSkill 的上层 git 仓库；非 git 工程须显式传入。
# 不在任何项目中、且不带参数在 AgentSkill 目录内执行时，输出 AgentSkill 自身（单独使用或开发 AgentSkill）。
find_project_root() {
  r=$(resolve_root "$1" "$PWD") || r=
  [ -n "$r" ] || r=$(resolve_plain_root "$1") || r=
  if [ -z "$r" ] && [ -z "$1" ]; then
    case "$(pwd -P)/" in "$skill_dir"/*) r=$skill_dir ;; esac
  fi
  if [ -z "$r" ]; then
    echo "未找到项目根目录：请在项目根目录（git 仓库）执行，或传入项目根目录（非 git 工程须传入）" >&2
    return 1
  fi
  echo "$r"
}

# 在项目根目录调用：设置 is_git，git 工程还设置 exclude（.git/info/exclude 的路径）。
git_env() {
  if git rev-parse --git-dir >/dev/null 2>&1; then
    is_git=1
    exclude=$(git rev-parse --git-path info/exclude)
    mkdir -p "$(dirname "$exclude")"
  else
    is_git=
  fi
}

# 把路径写入 .git/info/exclude，已有时跳过；非 git 工程什么都不做。须先调用 git_env。
ignore() {
  [ -n "$is_git" ] || return 0
  grep -qxF "$1" "$exclude" 2>/dev/null || echo "$1" >> "$exclude"
}
