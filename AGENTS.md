# AGENTS.md

<项目名>：<一句话定位>。

## 工作方式

- 只做需求所需的最小改动，保留与任务无关的改动。
- 只跑覆盖本次改动的检查，汇报实际跑过的命令。
- 未经用户要求，不 commit、不 push、不做破坏性操作。

## 大改动写 Note

改变行为、架构、接口或数据格式的改动，按 [.agents/notes/](.agents/notes/README.md) 的格式写一条简短记录。

## Git 提交

每笔提交必须带标签，规则见 [git-commit.md](git-commit.md)。
