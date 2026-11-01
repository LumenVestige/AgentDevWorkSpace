# 供其他脚本 source。设置 skill_dir（AgentSkill 仓库目录），提供 resolve_root。
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
