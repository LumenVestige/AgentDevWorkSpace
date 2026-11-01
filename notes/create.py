#!/usr/bin/env python3
"""在项目根目录的 .agents/notes/ 下按模板创建 Note，在任意目录执行都可以。

用法："$(git config agentskill.python)" create.py <topic-in-kebab-case>
文件名：.agents/notes/yyyy-mm-dd-HHMMSS-<topic>.md，平铺在 notes/ 下。
"""
import datetime
import re
import sys

from common import HERE, notes_dir, project_root


def main():
    if len(sys.argv) != 2:
        sys.exit(f"用法：{sys.argv[0]} <topic-in-kebab-case>")
    topic = sys.argv[1]
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", topic):
        sys.exit(f"topic 只能用小写字母、数字和 -：{topic}")

    notes = notes_dir(project_root())
    now = datetime.datetime.now()
    file = notes / f"{now:%Y-%m-%d-%H%M%S}-{topic}.md"
    if file.exists():
        sys.exit(f"已存在：{file}")
    notes.mkdir(parents=True, exist_ok=True)
    text = (HERE / "template.md").read_text(encoding="utf-8")
    file.write_text(text.replace("<时间戳>", f"{now:%Y-%m-%d %H:%M:%S}", 1), encoding="utf-8")
    print(file)


if __name__ == "__main__":
    main()
