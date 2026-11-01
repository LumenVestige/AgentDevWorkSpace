#!/usr/bin/env python3
"""在项目根目录的 .agents/notes/ 下创建 Note，并填入能从脚本获取的内容，在任意目录执行都可以。

用法："$(git config agentskill.python)" create.py <topic-in-kebab-case>
文件名：.agents/notes/yyyy-mm-dd-HHMMSS-<topic>.md，平铺在 notes/ 下。

自动填充：
- `时间：` 摘要时间戳，取当前时间；
- `## Git 提交`：尚未记录到任何 Note 的提交（git log --oneline，扫描范围同 verify.py）；没有时删除该节。
同一 topic 已有 Note 时不新建：刷新时间戳，把未记录的提交追加到原文件的 `## Git 提交`。
`## Outcome` / `## Verification` 由 Agent 填写。
"""
import datetime
import re
import sys

from common import HERE, load_config, notes_dir, project_root, unrecorded_commits

SECTION = re.compile(r"^## Git 提交[ \t]*\n(?:(?!^## ).*\n?)*", re.M)
TIME = re.compile(r"^时间：.*$", re.M)


def commit_block(lines):
    return "## Git 提交\n\n```\n" + "".join(f"{l}\n" for l in lines) + "```\n"


def fill_commits(text, lines):
    """把提交写入 `## Git 提交` 节：原有代码块中的行保留在新行之后；没有任何提交时删除该节。"""
    m = SECTION.search(text)
    old = re.findall(r"^[0-9a-f]{7,40} .*$", m.group(0), re.M) if m else []
    merged = lines + [l for l in old if l not in lines]
    block = commit_block(merged) if merged else ""
    if m:
        text = text[:m.start()] + block + text[m.end():]
    elif block:
        text = text.rstrip("\n") + "\n\n" + block
    return text.rstrip("\n") + "\n"


def main():
    if len(sys.argv) != 2:
        sys.exit(f"用法：{sys.argv[0]} <topic-in-kebab-case>")
    topic = sys.argv[1]
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", topic):
        sys.exit(f"topic 只能用小写字母、数字和 -：{topic}")

    root = project_root()
    notes = notes_dir(root)
    notes.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now()
    stamp = f"时间：{now:%Y-%m-%d %H:%M:%S}"
    commits = [oneline for _, oneline in (unrecorded_commits(root, load_config(root)) or [])]

    same = sorted(notes.glob(f"????-??-??-??????-{topic}.md"))
    if same:
        file = same[-1]
        text = file.read_text(encoding="utf-8")
        text = TIME.sub(stamp, text, count=1) if TIME.search(text) else text
    else:
        file = notes / f"{now:%Y-%m-%d-%H%M%S}-{topic}.md"
        text = TIME.sub(stamp, (HERE / "template.md").read_text(encoding="utf-8"), count=1)
    file.write_text(fill_commits(text, commits), encoding="utf-8")
    print(file)
    if commits:
        print(f"已填入 {len(commits)} 笔未记录的提交", file=sys.stderr)


if __name__ == "__main__":
    main()
