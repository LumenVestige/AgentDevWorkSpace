# AGENTS.md

## 工作方式

- 只做需求所需的最小改动，保留与任务无关的改动。
- 只跑覆盖本次改动的检查，汇报实际跑过的命令。
- 未经用户要求，不 commit、不 push、不做破坏性操作。

## .agents/ 目录

项目根目录下的 `.agents/` 已加入 `.gitignore`，不提交，只存放：

- `tmp/`：临时产物；`tmp/venv/` 是 `setup.sh` 创建的 Python 环境，AgentSkill 的 Python 脚本都用 `git config agentskill.python` 指向的解释器运行；
- `notes/`：Note 记录。

## Note

改变行为、架构、接口或数据格式的改动，写一条 Note：

- 路径：`.agents/notes/yyyy-mm-dd-HHMMSS-<topic>.md`，平铺在 `notes/` 下，时间取首次创建时刻（精确到秒），topic 用小写字母加 `-`，例如 `.agents/notes/2026-08-25-143005-local-cli-status-restart.md`。
- 内容：标题下的 `时间：` 是摘要的时间戳，创建时自动填入，更新 Note 时同步改为当前时间；`## Outcome` 写改了什么、现在的行为；`## Verification` 写跑了哪些检查、哪些没覆盖；涉及 git 提交时，`## Git 提交` 保留对应的 `git log --oneline` 日志，没有提交则删除该节。
- 创建：`"$(git config agentskill.python)" "$(git config agentskill.path)/notes/create.py" <topic>`（在项目内任意目录执行）。
- 同一主题有后续改动时更新原文件。

## Git 提交

每笔提交信息必须以标签开头：`[标签] 简述`

| 标签 | 用途 |
|---|---|
| `[fix]` | bug 修复 |
| `[feature]` | 新增业务功能 |
| `[del]` | 删除代码、功能或文件 |
| `[update]` | 代码逻辑更新；不属于以上三类时的兜底标签 |

一笔提交只做一件事；不同标签的改动混在一起时拆开提交。
