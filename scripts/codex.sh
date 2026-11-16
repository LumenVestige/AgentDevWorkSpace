#!/bin/sh
# Codex 的交互启动入口：输入首条消息前打印 AgentDevWorkSpace 的本地和远端版本号及欢迎语，再以保留终端内容的模式启动原生 CLI。
# 版本行由 notes skill 的 `update.py --welcome` 生成：当场请求远端版本，本地落后时立即在后台更新（不等待）；
# Codex 未信任项目时项目级 SessionStart hook 不会加载，这里保证展示欢迎语时也会检查。update.py 不可用时只显示本地版本。
# shell 函数可转发到本脚本；本脚本不安装全局命令，也不更改原生 CLI。
set -e

launch_dir=$PWD
interactive=1
# 只检查参数，不修改最终转发的 "$@"；有值选项的值不能误判成子命令。
parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -h|--help|-V|--version)
        interactive=; return ;;
      -C|--cd)
        [ "$#" -ge 2 ] || { interactive=; return; }
        launch_dir=$2; shift 2 ;;
      --cd=*) launch_dir=${1#--cd=}; shift ;;
      -C?*) launch_dir=${1#-C}; shift ;;
      -c|--config|-m|--model|-p|--profile|-s|--sandbox|-a|--ask-for-approval|-i|--image|--enable|--disable|--remote|--remote-auth-token-env|--local-provider|--add-dir)
        [ "$#" -ge 2 ] || { interactive=; return; }
        shift 2 ;;
      --) return ;;
      -*) shift ;;
      agents|exec|e|review|login|logout|mcp|plugin|app-server|remote-control|app|completion|update|doctor|sandbox|debug|apply|a|resume|queue|archive|delete|migrate-rollouts|migrate-nfs-db|unarchive|fork|cloud|exec-server|features|help)
        interactive=; return ;;
      *) return ;;
    esac
  done
}
parse_args "$@"

if [ -n "$interactive" ] && [ -t 1 ] && [ -d "$launch_dir" ]; then
  launch_root=$(CDPATH= cd "$launch_dir" && pwd -P)
  # 从子目录启动也能找到工作区；非 git 项目同样按父目录查找。
  while [ ! -d "$launch_root/agent-workspace" ] && [ "$launch_root" != / ]; do
    launch_root=$(dirname "$launch_root")
  done
  welcome="$launch_root/agent-workspace/skills/custom/sdd/welcome.md"
  [ -f "$welcome" ] || welcome="$launch_root/agent-workspace/skills/common/sdd/welcome.md"
  if [ -r "$welcome" ] && [ -s "$welcome" ]; then
    ws=$launch_root/agent-workspace
    py="$ws/.agent/env/venv/bin/python"
    if [ -r "$ws/.agent/env/python-path" ]; then
      py=$(cat "$ws/.agent/env/python-path")
    fi
    updater="$ws/skills/custom/notes/update.py"
    [ -f "$updater" ] || updater="$ws/skills/common/notes/update.py"
    line=
    if [ -f "$updater" ] && [ -x "$py" ]; then
      line=$("$py" "$updater" --welcome </dev/null 2>/dev/null) || line=
    fi
    if [ -z "$line" ]; then
      skill=$(cat "$ws/.agent/env/agentskill-path" 2>/dev/null || :)
      version=$(cat "$skill/publish/version" 2>/dev/null || :)
      version=$(printf '%s\n' "$version" | LC_ALL=C awk -F. 'NF >= 1 && NF <= 3 { for (i=1; i<=NF; i++) if ($i !~ /^(0|[1-9][0-9]*)$/) exit; print $1 "." (NF>1?$2:0) "." (NF>2?$3:0) }')
      [ -z "$version" ] || line="AgentDevWorkSpace 版本：本地 $version"
    fi
    renderer="$ws/skills/custom/sdd/render_welcome.py"
    [ -f "$renderer" ] || renderer="$ws/skills/common/sdd/render_welcome.py"
    if [ -f "$renderer" ] && [ -x "$py" ] &&
        "$py" "$renderer" --file "$welcome" --version-line "$line" 2>/dev/null; then
      :
    else
      printf '\n'
      [ -z "$line" ] || printf '%s\n\n' "$line"
      cat "$welcome"
      printf '\n\n'
    fi
    exec codex --no-alt-screen "$@"
  fi
fi
exec codex "$@"
