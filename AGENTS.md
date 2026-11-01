# AGENTS.md

## 工作方式

- 只做需求所需的最小改动，保留与任务无关的改动。
- 只跑覆盖本次改动的检查，汇报实际跑过的命令。
- 未经用户要求，不 commit、不 push、不做破坏性操作。

## .agents/ 目录

项目根目录下的 `.agents/` 已加入 `.gitignore`，不提交，只存放：

- `tmp/`：临时产物；`tmp/venv/` 是 `setup.sh` 创建的 Python 环境，依赖由 `deps.sh` 安装，AgentSkill 的 Python 脚本都用 `git config agentskill.python` 指向的解释器运行；
- `notes/`：Note 记录；
- `config/`：配置，`notes.json5` 见下文。

## Note

改变行为、架构、接口或数据格式的改动，写一条 Note：

- 路径：`.agents/notes/yyyy-mm-dd-HHMMSS-<topic>.md`，平铺在 `notes/` 下，时间取首次创建时刻（精确到秒），topic 用小写字母加 `-`，例如 `.agents/notes/2026-08-25-143005-local-cli-status-restart.md`。
- 内容：`## Outcome` 写改了什么、现在的行为；`## Verification` 写跑了哪些检查、哪些没覆盖。标题下的 `时间：` 和 Git 提交一节由 `create.py` 填写。
- 创建：`"$(git config agentskill.python)" "$(git config agentskill.path)/notes/create.py" <topic>`（在项目内任意目录执行）。自动填入当前时间和尚未记录到任何 Note 的提交；同一 topic 已有 Note 时不新建，刷新时间并把提交追加到原文件。
- 同一主题有后续改动时更新原文件：再次以同一 topic 运行 `create.py`，然后改写 Outcome / Verification。
- 校验：每轮对话结束前运行 `"$(git config agentskill.python)" "$(git config agentskill.path)/notes/verify.py"`（Claude Code 已通过 Stop hook 自动执行）。它只判断是否需要写 Note，并按上限删除最早的 Note；提示需要写时按上面的方式创建或更新。
- 配置：`.agents/config/notes.json5`（JSON5，每个字段都有注释）
  - `enabled`：是否开启 Note 校验；
  - `max_notes`：保留上限，默认 30；
  - `scan`：触发条件。`commits` 为 true 时存在未记录的提交即触发；`include_merges` 是否计入 merge 提交；`paths` / `exclude_paths` 只统计 / 不统计改动这些路径的提交（git pathspec）。

## Git 提交

每笔提交信息必须以标签开头：`[标签] 简述`

| 标签 | 用途 |
|---|---|
| `[fix]` | bug 修复 |
| `[feature]` | 新增业务功能 |
| `[del]` | 删除代码、功能或文件 |
| `[update]` | 代码逻辑更新；不属于以上三类时的兜底标签 |

一笔提交只做一件事；不同标签的改动混在一起时拆开提交。
