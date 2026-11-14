# AgentDevWorkSpace

通用 Agent 协作规范。具体规则见 [AGENTS.md](AGENTS.md)。

## 接入

在项目根目录执行：

```sh
git clone https://github.com/LumenVestige/AgentDevWorkSpace.git <任意层级子目录>
sh <子目录>/setup.sh
```

项目根目录不是 git 仓库时，须显式传入根目录：`sh <子目录>/setup.sh <项目根目录>`。此时照常创建软链接、`agent-workspace/`、
Python 环境和 Stop hook，跳过 `.git/info/exclude` 和 `commit-msg` hook；
没有提交，Note 不会因提交触发。之后 `git init` 的话，重新执行一次 setup.sh 即可补上跳过的部分。

## setup.sh 介绍

setup.sh 先执行 `scripts/init.sh` 初始化项目文件，再安装运行环境。

init.sh（也可单独执行：`sh <子目录>/scripts/init.sh [项目根目录]`，只初始化项目文件）：

- 在项目根目录创建相对软链接 `AGENTS.md → <子目录>/AGENTS.md` 和 `CLAUDE.md → AGENTS.md`（已有同名文件则跳过）；
- 按 `git config user.name` 生成个人目录名（转小写，空格和标点换成 `-`；未配置、或与 `skills` / `config` 重名时报错退出），创建工作区 `agent-workspace/`：
  - `skills/common/`：把 AgentDevWorkSpace 的 `skills/`（通用 skill 模板包）整体复制过来，每次执行都覆盖；`skills/custom/`：项目自己的 skill，从不改动，与 common 同名时优先；两者随项目提交；
  - `<个人目录>/specs/constraints.md`（个人约束，从 sdd skill 的 `personal-constraints.md` 复制，已有则不覆盖，不提交）和 `<个人目录>/notes/`（Note 记录，随项目提交）；`<个人目录>/feature|bugfix|change/` 由 sdd skill 的创建脚本按需生成；
  - `config/`：`notes.json5` 不存在时从 notes skill 的 `config.json5` 复制（Note 开关、上限、自动更新、扫描规则）；
  - `.agent/env/`（Python 虚拟环境、Note 提交基线 `note-base`、AgentDevWorkSpace 路径 `agentskill-path` 等）、`.agent/profiles/`、`.agent/evals/`；
- 把工作区的每个 skill 软链接到 `.claude/skills/<名称>`（Claude Code 加载；同名时指向 custom），已有同名的非软链接时跳过；
- 把 `/agent-workspace/config/`、`/agent-workspace/.agent/` 和 `/agent-workspace/*/specs/`（所有个人目录的 specs/）写入项目根目录的 `.gitignore`（已有则跳过）；AgentDevWorkSpace 目录、`AGENTS.md` / `CLAUDE.md` 软链接和 `.claude/skills/` 下的 skill 链接写入 `.git/info/exclude`。

之后 setup.sh 继续：

- 在 `agent-workspace/.agent/env/venv/` 创建 Python 3.9+ 虚拟环境，skill 中的 Python 脚本都用它运行（路径也记入 AgentDevWorkSpace 仓库的 `git config agentskill.python`，供 deps.sh / check.sh 单独执行时使用）；
- 执行 `scripts/deps.sh`，用该虚拟环境的 pip 安装依赖（清单写在 deps.sh 中，已满足时跳过）；
- 执行 `scripts/check.sh`，检查虚拟环境与依赖是否安装成功，失败时中止；
- 把工作区的 `agent-workspace/skills/common/notes/verify.py` 注册为 Claude Code 的 Stop hook（写入 `.claude/settings.local.json`）和 Codex 的 Stop hook（写入 `.codex/hooks.json`）；每轮对话结束时检查未记录到 Note 的提交和 Note 上限；运行前若距上次更新超过 `auto_update_interval_hours`（默认 24 小时），先拉取 AgentDevWorkSpace（`git pull --ff-only`，工作区有改动时跳过）并重新执行 setup.sh（同时用新的模板包覆盖 `skills/common/`）。Codex 的项目级 hook 只在项目被信任时加载，未信任时 setup.sh 会提示在 `~/.codex/config.toml` 中加入 `[projects."<项目根目录>"]` 和 `trust_level = "trusted"`；此外 Codex 对 hook 本身还有一道信任，首次启动（以及 hook 命令变更后）会要求确认，选择信任后才会执行；
- 把工作区 sdd skill 的 `check_layout.py` 也注册为 Claude Code 和 Codex 的 Stop hook：当前用户个人目录的需求目录中新增的文件不在根目录白名单（`spec.md`、`plan.md`、`tasks.md`、`summary.md`）内、也不在 `NN-<主题>/` 子目录中时，阻止结束并列出清单（同一轮只阻止一次）；已提交的旧文件不追溯，手动加 `--all` 检查全部；同一事件下各脚本的 hook 分别去重，重复执行 setup 不会重复添加；
- 把工作区 sdd skill 的 `welcome.py` 注册为 Claude Code 和 Codex 的 SessionStart hook（matcher `startup|clear`）：新对话和 `/clear` 时向用户展示 SDD 快捷命令（`welcome.md`）；
- 为当前项目安装 `commit-msg` hook（转发到 `agent-workspace/skills/common/git-commit/commit-msg`），检查 `[fix]` / `[feature]` / `[del]` / `[update]` 标签。

## 文件列表

`skills/` 是通用 skill 模板包，安装时复制到项目的 `agent-workspace/skills/common/`，Agent 和 hook 都使用工作区中的副本。

```
AGENTS.md                  规则
setup.sh                   → scripts/setup.sh 的软链接
scripts/setup.sh           接入：调用 init.sh，再安装运行环境
scripts/init.sh            初始化项目文件和工作区，复制 skills（setup.sh 自动调用，也可单独执行）
scripts/deps.sh            Python 依赖清单，安装到虚拟环境（setup.sh 自动调用）
scripts/check.sh           检查虚拟环境与依赖（setup.sh 自动调用，也可单独执行）
scripts/root.sh            确定项目根目录，.git/info/exclude 写入（setup.sh、init.sh 共用）
skills/git-commit/SKILL.md      git-commit skill：提交信息规则
skills/git-commit/commit-msg    提交标签校验（commit-msg hook）
skills/sdd/SKILL.md             sdd skill：SDD 流程、需求目录与编号规则
skills/sdd/constraints.md       通用开发约束规范
skills/sdd/personal-constraints.md  个人约束模板（复制到 <个人目录>/specs/constraints.md）
skills/sdd/new.sh               创建 <个人目录>/<feature|bugfix|change>/NNN-<slug>/ 并复制该类型的模板
skills/sdd/new_feature.sh, new_bugfix.sh, new_change.sh  快捷命令「创建feature/bugfix/change:<名称>」对应的入口
skills/sdd/welcome.md, welcome.py  SessionStart hook：新对话时展示 SDD 快捷命令
skills/sdd/check_layout.py      Stop hook：检查需求目录中新增的文件是否已归类（根目录白名单 + NN-<主题>/ 子目录）
skills/sdd/templates/<类型>/    SDD 模板：spec.md、plan.md、tasks.md，按 feature / bugfix / change 分开
skills/knowledge/SKILL.md       knowledge skill：开发知识库里有什么（SDD 产物、Note、约束、提交），如何检索和追溯
skills/knowledge/search.sh      按关键词检索所有人的 feature / bugfix / change、Note、约束和提交信息
skills/notes/SKILL.md           notes skill：Note 的路径、内容、创建、校验与配置
skills/notes/create.py, template.md  创建 Note，自动填入时间与未记录的提交
skills/notes/verify.py          Claude Code / Codex 的 Stop hook：按需自动更新，判断是否需要写 Note，按上限删除旧 Note
skills/notes/config.json5       Note 默认配置（JSON5，带字段注释）
skills/notes/common.py          notes 脚本共用：根目录定位、个人目录、配置读取、未记录提交扫描
```
