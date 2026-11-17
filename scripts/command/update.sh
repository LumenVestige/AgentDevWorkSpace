#!/bin/sh
# agentdev 的跨平台核心位于 scripts/command/app.py；本文件保留 POSIX 入口。
set -e
agentdev_entry=$0
while [ -L "$agentdev_entry" ]; do
  agentdev_target=$(readlink "$agentdev_entry")
  case "$agentdev_target" in /*) agentdev_entry=$agentdev_target ;; *) agentdev_entry="$(dirname "$agentdev_entry")/$agentdev_target" ;; esac
done
agentdev_directory=$(CDPATH= cd "$(dirname "$agentdev_entry")" && pwd -P)
agentdev_directory=$(CDPATH= cd "$agentdev_directory/.." && pwd -P)
exec sh "$agentdev_directory/lib/bootstrap.sh" "$agentdev_directory/command/app.py" update "$@"
