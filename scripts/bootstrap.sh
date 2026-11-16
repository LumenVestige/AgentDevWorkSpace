#!/bin/sh
# macOS/Linux 入口：安装前使用 python3，安装后优先使用共享 venv。
set -e
agentdev_scripts=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
agentdev_python=python3
if [ -f "$agentdev_scripts/../.agentdev-app" ] && [ -x "$agentdev_scripts/../../venv/bin/python" ]; then
  agentdev_python="$agentdev_scripts/../../venv/bin/python"
fi
command -v "$agentdev_python" >/dev/null 2>&1 || { echo '需要 Python 3.9+（支持 macOS / Linux）' >&2; exit 1; }
exec "$agentdev_python" -B "$agentdev_scripts/agentdev.py" "$@"
