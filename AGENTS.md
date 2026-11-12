# AGENTS.md

## 工作方式

- 只做需求所需的最小改动，保留与任务无关的改动。
- 只跑覆盖本次改动的检查，汇报实际跑过的命令。
- 未经用户要求，不 commit、不 push、不做破坏性操作。

## agent-workspace/ 目录

项目根目录下的 `agent-workspace/` 是 Agent 工作区，由 `scripts/init.sh` 创建，AgentDevWorkSpace 的文件都放在这里：

- `skills/`：Agent 加载的 skill，随项目提交；
  - `common/`：从 AgentDevWorkSpace 的 `skills/`（通用 skill 模板包）复制，每次执行 setup 都整体覆盖，不要在这里修改；
  - `custom/`：项目自己的 skill，setup 从不改动；与 `common/` 同名时优先加载 `custom/` 中的，定制通用 skill 时先把它从 `common/` 复制过来再改；
- `<个人目录>/`：每人一个，目录名由 `git config user.name` 生成（转小写，空格和标点换成 `-`，例如 `Tony Chen` → `tony-chen`），随项目提交；
  - `specs/`：个人的自定义约束 `constraints.md`，补充通用开发约束（见 `sdd` skill）；
  - `feature/`、`bugfix/`、`change/`：每个新功能、bug 修复、变更一个目录 `NNN-<slug>/`，内含 `spec.md`、`plan.md`、`tasks.md`（见 `sdd` skill）；
  - `notes/`：Note 记录（见 `notes` skill）；只改动各人 `notes/` 的提交不会触发新的 Note；
- `config/`：配置，`notes.json5` 见 `notes` skill；不提交；
- `.agent/`：本机使用，不提交；
  - `env/`：`venv/` 是 `setup.sh` 创建的 Python 环境，依赖由 `deps.sh` 安装，skill 中的 Python 脚本都用它运行；另有 Note 校验的状态文件和 AgentDevWorkSpace 的路径；
  - `profiles/`、`evals/`：预留。

## Skills

SDD 流程、Note、Git 提交规则和开发知识库检索封装成 skill，在 `agent-workspace/skills/common/` 下；`init.sh` 把每个 skill 链接到 `.claude/skills/`（Claude Code 按需加载，同名时指向 `custom/`）。用到时读取对应的 `SKILL.md`（`custom/` 中有同名 skill 时读 `custom/` 中的）：

- `sdd`（`agent-workspace/skills/common/sdd/SKILL.md`）：用户输入「创建feature:<名称>」「创建bugfix:<名称>」「创建change:<名称>」（或 new_feature / new_bugfix / new_change <名称>）时，按它创建对应的目录；新功能和跨模块的改动，必须先读通用开发约束和个人约束，再按它写 spec / plan / tasks，plan 中逐条做约束检查后才能实现。
- `notes`（`agent-workspace/skills/common/notes/SKILL.md`）：改变行为、架构、接口或数据格式的改动，必须写一条 Note；Stop hook 提示有提交尚未记录到 Note 时，按它创建。
- `knowledge`（`agent-workspace/skills/common/knowledge/SKILL.md`）：搜索或回顾历史开发痕迹（以前做过什么、某个需求或 bug 的方案、为什么这样设计、某笔提交的来龙去脉）时，按它检索，用检索到的文档作为依据回答。
- `git-commit`（`agent-workspace/skills/common/git-commit/SKILL.md`）：每笔提交信息必须以 `[fix]` / `[feature]` / `[del]` / `[update]` 标签开头；提交前按它编写提交信息。
