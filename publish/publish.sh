#!/bin/sh
# 用法：sh publish/publish.sh "<提交信息>" [MAJOR.MINOR.PATCH]
# 发布主仓库：默认补丁号 +1；指定版本时使用该三段版本。只提交并推送当前仓库。
# 提交失败恢复版本文件；推送失败保留已完成的提交并返回非零，便于重试。
set -e
unset GIT_DIR GIT_WORK_TREE
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ] || [ -z "$1" ]; then
  echo "用法：sh $0 \"<提交信息>\" [MAJOR.MINOR.PATCH]" >&2
  exit 1
fi
msg=$1
target_version=${2:-}
root=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
lfile="$root/publish/version"
work=$(mktemp -d) || exit 1
trap 'rm -rf "$work"' EXIT
printf '%s\n' "$msg" > "$work/message"
sh "$root/skills/git-commit/commit-msg" "$work/message"
py="$root/agent-workspace/.agent/env/venv/bin/python"
[ ! -f "$root/agent-workspace/.agent/env/python-path" ] || py=$(cat "$root/agent-workspace/.agent/env/python-path")
[ -x "$py" ] || py=python3
pair=$("$py" - "$root" "$target_version" <<'PYVERSION'
from pathlib import Path
import sys
root = Path(sys.argv[1])
sys.path.insert(0, str(root / 'skills'))
from _version import read_version_file, parse_version, next_patch, format_version
try:
    file = root / 'publish/version'
    old = read_version_file(file) if file.is_file() else (0, 0, 0)
    new = parse_version(sys.argv[2]) if sys.argv[2] else next_patch(old)
    print(format_version(old), format_version(new))
except (OSError, ValueError) as error:
    sys.exit(str(error))
PYVERSION
) || exit 1
old=${pair% *}
new=${pair#* }
existed=
if [ -f "$lfile" ]; then existed=1; cp "$lfile" "$work/previous-version"; fi
mkdir -p "$(dirname "$lfile")"
printf '%s\n' "$new" > "$lfile"
restore() {
  if [ -n "$existed" ]; then
    cp "$work/previous-version" "$lfile"
    git -C "$root" add publish/version
  else
    git -C "$root" rm -q --cached --ignore-unmatch publish/version
    rm -f "$lfile"
  fi
}
if ! git -C "$root" add -A; then
  restore
  echo "暂存失败，版本号已恢复为 ${old}" >&2
  exit 1
fi
if ! git -C "$root" commit -q -m "$msg"; then
  restore
  echo "提交失败，版本号已恢复为 $old" >&2
  exit 1
fi
hash=$(git -C "$root" rev-parse --short HEAD)
git -C "$root" push -q origin HEAD || {
  echo "推送失败（已提交 ${hash}），请重试 git push origin HEAD" >&2
  exit 1
}
echo "已发布：AgentDevWorkSpace ${hash}，version ${old} → ${new}"
