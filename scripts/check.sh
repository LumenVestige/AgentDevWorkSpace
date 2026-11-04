#!/bin/sh
# 用法：sh <AgentSkill 路径>/scripts/check.sh [python 解释器]
# 检查虚拟环境与依赖是否安装成功：解释器可用、Python 3.9+、位于虚拟环境中、pip 可用、deps.sh 中的依赖已安装且版本一致。
# setup.sh 安装依赖后自动执行；任一项失败时退出码为 1。
unset GIT_DIR GIT_WORK_TREE
skill_dir=$(cd "$(dirname "$0")/.." && pwd -P)
py=${1:-$(git -C "$skill_dir" config agentskill.python)}
failed=0
ok() { echo "  ✓ $1"; }
bad() { echo "  ✗ $1" >&2; failed=1; }

echo "检查虚拟环境与依赖："
if [ -n "$py" ] && "$py" -c '' 2>/dev/null; then
  ok "解释器：$py"
else
  bad "解释器不可用：${py:-未配置 agentskill.python}，请执行 setup.sh"
  exit 1
fi
"$py" -c 'import sys; sys.exit(sys.version_info < (3, 9))' && ok "版本：$("$py" -V 2>&1)" || bad "需要 Python 3.9+，当前：$("$py" -V 2>&1)"
"$py" -c 'import sys; sys.exit(sys.prefix == sys.base_prefix)' && ok "虚拟环境：$("$py" -c 'import sys; print(sys.prefix)')" || bad "$py 不在虚拟环境中"
"$py" -m pip --version >/dev/null 2>&1 && ok "pip：$("$py" -m pip --version | cut -d' ' -f1-2)" || bad "pip 不可用"

# 依赖清单取自 deps.sh，避免两处维护。
deps=$(sed -n 's/^deps="\(.*\)"$/\1/p' "$skill_dir/scripts/deps.sh")
[ -n "$deps" ] || bad "未能从 deps.sh 读取依赖清单"
for spec in $deps; do
  name=${spec%%==*}
  want=${spec#*==}
  [ "$want" = "$spec" ] && want=
  have=$("$py" -c "import importlib.metadata as m, sys; print(m.version(sys.argv[1]))" "$name" 2>/dev/null)
  if [ -z "$have" ]; then
    bad "依赖未安装：${spec}，请执行 sh $skill_dir/scripts/deps.sh"
  elif [ -n "$want" ] && [ "$have" != "$want" ]; then
    bad "依赖版本不一致：$name 需要 ${want}，当前 ${have}，请执行 sh $skill_dir/scripts/deps.sh"
  else
    ok "依赖：$name $have"
  fi
done

[ "$failed" = 0 ] && echo "检查通过" || echo "检查未通过" >&2
exit "$failed"
