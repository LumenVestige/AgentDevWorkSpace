#!/bin/sh
# 用法：sh <AgentDevWorkSpace 路径>/scripts/deps.sh [python 解释器]
# 用指定虚拟环境的 pip 安装 AgentDevWorkSpace Python 脚本的依赖。解释器默认取 git config agentskill.python（setup.sh 写入，即 agent-workspace/.agent/env/venv）。
# setup.sh 每次执行都会调用；依赖已满足时 pip 直接跳过。
set -e
unset GIT_DIR GIT_WORK_TREE

# 依赖清单：新增依赖直接加在这里，固定版本。
deps="json5==0.12.1"

skill_dir=$(cd "$(dirname "$0")/.." && pwd -P)
py=${1:-$(git -C "$skill_dir" config agentskill.python || true)}
if [ -z "$py" ] || ! "$py" -c '' 2>/dev/null; then
  echo "未找到虚拟环境的解释器，请先执行 setup.sh，或传入解释器路径" >&2
  exit 1
fi
# shellcheck disable=SC2086 # deps 按空格拆成多个包
"$py" -m pip install -q --disable-pip-version-check $deps || {
  echo "依赖安装失败：$py -m pip install $deps" >&2
  exit 1
}
