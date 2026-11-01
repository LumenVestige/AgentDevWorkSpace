# AGENTS.md

## 工作方式

- 只做需求所需的最小改动，保留与任务无关的改动。
- 只跑覆盖本次改动的检查，汇报实际跑过的命令。
- 未经用户要求，不 commit、不 push、不做破坏性操作。

## .agents/ 目录

项目根目录下的 `.agents/` 只存放：

- `tmp/`：临时产物，不提交；
- `notes/`：Note 记录，随代码一起提交。

## Note

改变行为、架构、接口或数据格式的改动，在同一笔提交里写一条 Note：

- 路径：`.agents/notes/<proposed|implemented>/<feature|fix|update>/yyyy-mm-dd-<topic>.md`，日期取首次写的那天，topic 用小写字母加 `-`，例如 `.agents/notes/implemented/feature/2026-08-25-local-cli-status-restart.md`。
- 内容：`## Outcome` 写改了什么、现在的行为；`## Verification` 写跑了哪些检查、哪些没覆盖。
- 创建：`sh "$(git config agentskill.path)/notes/new.sh" implemented feature <topic>`（在项目内任意目录执行）。
- 完成后从 `proposed/` 移到 `implemented/`；同一主题有后续改动时更新原文件。

## Git 提交

每笔提交信息必须以标签开头：`[标签] 简述`

| 标签 | 用途 |
|---|---|
| `[fix]` | bug 修复 |
| `[feature]` | 新增业务功能 |
| `[update]` | 代码逻辑更新；不属于以上两类时的兜底标签 |

一笔提交只做一件事；fix 和 feature 混在一起时拆开提交。
