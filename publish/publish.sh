#!/bin/sh
# 用法：sh publish/publish.sh "<提交信息>"
# 发布 AgentDevWorkSpace：提交前把版本号加 1，再提交并推送 AgentDevWorkSpace 和 versions 两个库。
# - 版本号是一个非负整数，同时记在本库的 publish/version 和 versions 库的 AgentDevWorkSpace/version，两者须一致：
#   不一致时报错退出（通常是本地 AgentDevWorkSpace 不是最新，先 git pull）；某一处不存在或为空时取另一处的值，都没有时视为 0；
# - versions 库位于 publish/versions/（已写入 .gitignore），不存在时自动 clone，已存在时先 pull --ff-only 取最新版本；
#   地址默认 git@github.com:LumenVestige/versions.git，可用环境变量 PUBLISH_VERSIONS_REPO 覆盖；
# - 提交信息须符合 git-commit skill 的标签规则（[fix] / [feature] / [research] / [del] / [update]），提交前预先校验；
# - AgentDevWorkSpace 提交全部改动（git add -A，遵守 .gitignore）；versions 库提交 version 文件，提交信息相同，正文附 AgentDevWorkSpace 的提交 hash；
# - AgentDevWorkSpace 提交失败时两处版本号恢复原值；已完成的提交不自动撤销，推送失败时提示手动推送。
set -e
unset GIT_DIR GIT_WORK_TREE

if [ $# -ne 1 ] || [ -z "$1" ]; then
  echo "用法：sh $0 \"<提交信息>\"" >&2
  exit 1
fi
msg=$1
root=$(cd "$(dirname "$0")/.." && pwd -P)
versions=${root}/publish/versions
repo=${PUBLISH_VERSIONS_REPO:-git@github.com:LumenVestige/versions.git}
vfile=${versions}/AgentDevWorkSpace/version
lfile=${root}/publish/version

# 预先校验提交信息，与 commit-msg hook 同一规则，避免改了 version 后才被拒绝。
tmp=$(mktemp) || exit 1
trap 'rm -f "$tmp"' EXIT
printf '%s\n' "$msg" > "$tmp"
sh "${root}/skills/git-commit/commit-msg" "$tmp"

if [ -z "$(git -C "${root}" status --porcelain)" ]; then
  echo "AgentDevWorkSpace 没有可提交的改动" >&2
  exit 1
fi

if [ -d "${versions}/.git" ]; then
  git -C "${versions}" pull -q --ff-only || { echo "拉取 versions 库失败：${versions}" >&2; exit 1; }
elif [ -e "${versions}" ]; then
  echo "${versions} 已存在但不是 git 仓库，请先处理" >&2
  exit 1
else
  git clone -q "${repo}" "${versions}" || { echo "拉取 versions 库失败：${repo}" >&2; exit 1; }
fi

# 读取版本号文件：输出去掉空白后的内容；不存在时输出空；不是非负整数时报错退出。
read_version() {
  [ -f "$1" ] || return 0
  v=$(tr -d '[:space:]' < "$1")
  case "$v" in *[!0-9]*) echo "$1 的内容不是非负整数：$v" >&2; return 1 ;; esac
  echo "$v"
}
local_v=$(read_version "${lfile}")
remote_v=$(read_version "${vfile}")
if [ -n "${local_v}" ] && [ -n "${remote_v}" ] && [ "${local_v}" -ne "${remote_v}" ]; then
  echo "版本号不一致：publish/version 为 ${local_v}，versions 库为 ${remote_v}；请先 git pull 更新 AgentDevWorkSpace，或手动对齐两者" >&2
  exit 1
fi
old=${remote_v:-${local_v:-0}}
new=$(( old + 1 ))

# 写入两处版本号；AgentDevWorkSpace 提交失败时恢复原样（原本不存在的文件删除）。
lexisted=; [ -f "${lfile}" ] && lexisted=1 && lold=$(cat "${lfile}")
vexisted=; [ -f "${vfile}" ] && vexisted=1 && vold=$(cat "${vfile}")
mkdir -p "$(dirname "${vfile}")"
printf '%s\n' "${new}" > "${lfile}"
printf '%s\n' "${new}" > "${vfile}"
restore() {
  if [ -n "${vexisted}" ]; then printf '%s\n' "${vold}" > "${vfile}"; else rm -f "${vfile}"; fi
  if [ -n "${lexisted}" ]; then
    printf '%s\n' "${lold}" > "${lfile}"
    git -C "${root}" add publish/version
  else
    git -C "${root}" rm -q --cached --ignore-unmatch publish/version
    rm -f "${lfile}"
  fi
}

git -C "${root}" add -A
if ! git -C "${root}" commit -q -m "$msg"; then
  restore
  echo "AgentDevWorkSpace 提交失败，版本号已恢复为 ${old}" >&2
  exit 1
fi
hash=$(git -C "${root}" rev-parse --short HEAD)

git -C "${versions}" add AgentDevWorkSpace/version
git -C "${versions}" commit -q -m "$msg" -m "AgentDevWorkSpace: ${hash}（version ${new}）" ||
  { echo "versions 库提交失败；AgentDevWorkSpace 已提交 ${hash}，请手动处理 ${versions}" >&2; exit 1; }
vhash=$(git -C "${versions}" rev-parse --short HEAD)

git -C "${root}" push -q origin HEAD ||
  { echo "AgentDevWorkSpace 推送失败（已提交 ${hash}），versions 库也未推送（已提交 ${vhash}），请手动推送两个库" >&2; exit 1; }
git -C "${versions}" push -q origin HEAD ||
  { echo "versions 库推送失败（已提交 ${vhash}），请手动推送：git -C ${versions} push origin HEAD" >&2; exit 1; }

echo "已发布：AgentDevWorkSpace ${hash}，version ${old:-0} → ${new}（versions ${vhash}）"
