#!/bin/sh
# 用法：sh <AgentDevWorkSpace 路径>/scripts/lib/deps.sh [python 解释器]
# 依赖清单供跨平台全局安装器读取；此 POSIX 辅助入口也可手动安装到指定解释器。
# 默认优先使用全局共享 venv，其次读取当前项目的 python-path / agentskill.python。
set -e
unset GIT_DIR GIT_WORK_TREE

# 依赖清单：新增依赖直接加在这里，固定版本。
deps="json5==0.12.1"

# 旧 scripts/deps.sh 是指向本文件的链接，先解析后再定位源码根目录。
entry=$0
while [ -L "$entry" ]; do
  target=$(readlink "$entry")
  case "$target" in /*) entry=$target ;; *) entry="$(dirname "$entry")/$target" ;; esac
done
skill_dir=$(cd "$(dirname "$entry")/../.." && pwd -P)
py=${1:-}
if [ -z "$py" ] && [ -f "$skill_dir/.agentdev-app" ]; then
  py="$skill_dir/../venv/bin/python"
fi
if [ -z "$py" ] && [ -f agent-workspace/.agent/env/python-path ]; then
  py=$(cat agent-workspace/.agent/env/python-path)
fi
[ -n "$py" ] || py=$(git config agentskill.python 2>/dev/null || true)
if [ -z "$py" ] || ! "$py" -c '' 2>/dev/null; then
  echo "未找到虚拟环境的解释器，请先执行 setup.sh，或传入解释器路径" >&2
  exit 1
fi
# shellcheck disable=SC2086 # deps 按空格拆成多个包
"$py" -m pip install -q --disable-pip-version-check $deps || {
  echo "依赖安装失败：$py -m pip install $deps" >&2
  exit 1
}
