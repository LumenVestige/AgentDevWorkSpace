#!/bin/sh
# bash/zsh: source setup.sh 在当前会话安装并激活；普通 sh 执行只输出激活提示。
_agentdev_setup() {
  local agentdev_entry agentdev_target agentdev_directory agentdev_sourced agentdev_install_home
  agentdev_entry=${BASH_SOURCE:-$0}
  agentdev_sourced=0
  if [ -n "${BASH_VERSION-}" ] && [ "$agentdev_entry" != "$0" ]; then
    agentdev_sourced=1
  elif [ -n "${ZSH_VERSION-}" ]; then
    eval 'agentdev_entry=${(%):-%x}'
    case "${ZSH_EVAL_CONTEXT-}" in *:file*) agentdev_sourced=1 ;; esac
  fi
  while [ -L "$agentdev_entry" ]; do
    agentdev_target=$(readlink "$agentdev_entry")
    case "$agentdev_target" in /*) agentdev_entry=$agentdev_target ;; *) agentdev_entry="$(dirname "$agentdev_entry")/$agentdev_target" ;; esac
  done
  agentdev_directory=$(CDPATH= cd "$(dirname "$agentdev_entry")" && pwd -P)
  [ -f "$agentdev_directory/bootstrap.sh" ] || agentdev_directory="$agentdev_directory/scripts"
  if sh "$agentdev_directory/bootstrap.sh" setup "$@"; then
    if [ "$agentdev_sourced" = 1 ]; then
      agentdev_install_home=${AGENTDEV_HOME:-}
      if [ -z "$agentdev_install_home" ] && [ -f "$agentdev_directory/../.agentdev-app" ]; then
        agentdev_install_home=$(CDPATH= cd "$agentdev_directory/../.." && pwd -P)
      fi
      agentdev_install_home=${agentdev_install_home:-$HOME/.agent-dev-workspace}
      . "$agentdev_install_home/env" || return
      printf '%s\n' 'agentdev 已在当前终端生效。'
    fi
  else
    return $?
  fi
}
_agentdev_setup "$@"
