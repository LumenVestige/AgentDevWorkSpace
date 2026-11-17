#!/bin/sh
# 选择共享运行时，执行调用方指定的内部入口；不提供任何 app 子命令。
set -e
agentdev_root=$(CDPATH= cd "$(dirname "$0")/../.." && pwd -P)
agentdev_entry=$1
shift
agentdev_python=python3
if [ -f "$agentdev_root/.agentdev-app" ] && [ -x "$agentdev_root/../venv/bin/python" ]; then
  agentdev_python="$agentdev_root/../venv/bin/python"
fi
command -v "$agentdev_python" >/dev/null 2>&1 || { echo '需要 Python 3.9+（支持 macOS / Linux）' >&2; exit 1; }
exec "$agentdev_python" -B "$agentdev_entry" "$@"
