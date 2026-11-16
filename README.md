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

setup.sh 先执行 `scripts/init.sh` 初始化项目文件、`scripts/fix.sh` 处理升级兼容，再安装运行环境。

init.sh（也可单独执行：`sh <子目录>/scripts/init.sh [项目根目录]`，只初始化项目文件）：

- 在项目根目录创建相对软链接 `AGENTS.md → <子目录>/AGENTS.md` 和 `CLAUDE.md → AGENTS.md`（已有同名文件则跳过）；
- 按 `git config user.name` 生成个人目录名（转小写，空格和标点换成 `-`；未配置、或与 `skills` / `config` 重名时报错退出），创建工作区 `agent-workspace/`：
  - `skills/common/`：把 AgentDevWorkSpace 的 `skills/`（通用 skill 模板包）整体复制过来，每次执行都覆盖；`skills/custom/`：项目自己的 skill，从不改动，与 common 同名时优先；两者随项目提交；
  - `<个人目录>/specs/constraints.md`（个人约束，从 sdd skill 的 `personal-constraints.md` 复制，已有则不覆盖，不提交）和 `<个人目录>/notes/`（Note 记录，随项目提交）；`<个人目录>/feature|bugfix|change|research/` 由 sdd skill 的创建脚本按需生成；
  - `config/`：`notes.json5` 不存在时从 notes skill 的 `config.json5` 复制（Note 开关、上限、自动更新、扫描规则）；
  - `.agent/env/`（Python 虚拟环境、Note 提交基线 `note-base`、AgentDevWorkSpace 路径 `agentskill-path` 等）、`.agent/tmp/`（Agent 的临时文件，按任务建子目录）、`.agent/profiles/`、`.agent/evals/`；
- 把工作区的每个 skill 软链接到 `.claude/skills/<名称>`（Claude Code 加载；同名时指向 custom），已有同名的非软链接时跳过；
- 把 `/agent-workspace/config/`、`/agent-workspace/.agent/`、`/agent-workspace/.agent/tmp/` 和 `/agent-workspace/*/specs/`（所有个人目录的 specs/）写入项目根目录的 `.gitignore`（已有则跳过）；AgentDevWorkSpace 目录、`AGENTS.md` / `CLAUDE.md` 软链接和 `.claude/skills/` 下的 skill 链接写入 `.git/info/exclude`。

之后 setup.sh 执行 `scripts/fix.sh [项目根目录]`（也可单独执行），处理升级引入的兼容问题，可重复执行、不覆盖已有文件：

- 把当前用户 `notes/` 下旧版本平铺的 `yy-MM-dd-HH-mm-ss-<topic>.md` 移到 `notes/git-commit-change/<YYYY-MM-DD>/HH-mm-ss-<topic>.md`。

之后 setup.sh 继续：

- 在 `agent-workspace/.agent/env/venv/` 创建 Python 3.9+ 虚拟环境，skill 中的 Python 脚本都用它运行（路径也记入 AgentDevWorkSpace 仓库的 `git config agentskill.python`，供 deps.sh / check.sh 单独执行时使用）；
- 执行 `scripts/deps.sh`，用该虚拟环境的 pip 安装依赖（清单写在 deps.sh 中，已满足时跳过）；
- 执行 `scripts/check.sh`，检查虚拟环境与依赖是否安装成功，失败时中止；
- 把工作区的 `agent-workspace/skills/common/notes/verify.py` 注册为 Claude Code 的 Stop hook（写入 `.claude/settings.local.json`）和 Codex 的 Stop hook（写入 `.codex/hooks.json`）；每轮对话结束时检查未记录到 Note 的提交、工作区的大规模改动，并把超过上限的同一天 Note 合并；不阻止结束时，若距上次版本检查超过 `auto_update_interval_hours`（默认 24 小时），触发自动更新（见下一条）。Codex 的项目级 hook 只在项目被信任时加载，未信任时 setup.sh 会提示在 `~/.codex/config.toml` 中加入 `[projects."<项目根目录>"]` 和 `trust_level = "trusted"`；此外 Codex 对 hook 本身还有一道信任，首次启动（以及 hook 命令变更后）会要求确认，选择信任后才会执行；
- 把工作区 notes skill 的 `update.py` 注册为 Claude Code 和 Codex 的 SessionStart hook（matcher `startup|clear`）：每次会话开始在后台比较本地 `publish/version` 与 versions 库的 `AgentDevWorkSpace/version`，低于远端时拉取 AgentDevWorkSpace（`git pull --ff-only`，工作区有改动时跳过），并在当前 LLM 任务结束后（下一次 Stop 或 SessionStart）于后台执行 setup.sh（同时用新的模板包覆盖 `skills/common/`）；不阻塞、不打断正在执行的任务，日志在 `agent-workspace/.agent/env/update.log`；
- 把工作区 sdd skill 的 `welcome.py` 注册为 Claude Code 和 Codex 的 SessionStart hook（matcher `startup|clear`）：输出 SDD 快捷命令（`welcome.md`）及交给 Agent 的命令处理规则；hook 的显示时机取决于客户端。Codex CLI 启动即展示的接入方式见下节；
- 为当前项目安装 `commit-msg` hook（转发到 `agent-workspace/skills/common/git-commit/commit-msg`），检查 `[fix]` / `[feature]` / `[del]` / `[update]` 标签。

## Codex CLI 启动欢迎语

要在输入任何消息前看到欢迎语，在已接入项目中用以下入口启动（支持原有 CLI 参数）：

```sh
sh <AgentDevWorkSpace 路径>/scripts/codex.sh
```

入口先打印项目 `agent-workspace/skills/custom/sdd/welcome.md`（不存在时使用 common），
再用 `--no-alt-screen` 启动原生 Codex，保留终端中的欢迎语；不发送初始消息、不调用模型。
`--help`、`--version`、`exec` 等子命令、恢复会话及重定向输出直接转发，不打印欢迎语。
支持从项目子目录启动和 `-C/--cd` 指定项目。此入口只处理进程启动，CLI 内部 `/clear` 仍由 hook 处理。

如果希望仍直接输入 `codex`，可在自己的 zsh 配置中添加转发函数，把下面路径改为实际绝对路径：

```sh
function codex {
  sh '/绝对路径/AgentDevWorkSpace/scripts/codex.sh' "$@"
}
```

setup 不会自动修改全局 shell 配置；移除该函数即可恢复原生命令。

## 发布

维护 AgentDevWorkSpace 时，用发布脚本提交并推送：

```sh
sh publish/publish.sh "[update] <改动说明>"
```

- 提交信息须符合 git-commit skill 的标签规则，提交前预先校验；
- versions 库位于 `publish/versions/`（已写入 `.gitignore`），不存在时自动 clone `git@github.com:LumenVestige/versions.git`，已存在时先 `pull --ff-only`；
- 版本号（一个整数）同时记在本库的 `publish/version` 和 versions 库的 `AgentDevWorkSpace/version`，两者须一致，不一致时报错（通常是本地不是最新，先 `git pull`）；
- 两处版本号都加 1，提交 AgentDevWorkSpace 的全部改动（`git add -A`；没有其他改动时只提交版本号），再提交 versions 库（提交信息相同，正文附 AgentDevWorkSpace 的提交 hash），最后两个库都推送当前分支；
- AgentDevWorkSpace 提交失败时两处版本号恢复原值；推送失败时提示哪个库需要手动推送，已完成的提交不自动撤销。

## 文件列表

`skills/` 是通用 skill 模板包，安装时复制到项目的 `agent-workspace/skills/common/`，Agent 和 hook 都使用工作区中的副本。

```
AGENTS.md                  规则
setup.sh                   → scripts/setup.sh 的软链接
scripts/setup.sh           接入：调用 init.sh、fix.sh，再安装运行环境
scripts/init.sh            初始化项目文件和工作区，复制 skills（setup.sh 自动调用，也可单独执行）
scripts/deps.sh            Python 依赖清单，安装到虚拟环境（setup.sh 自动调用）
scripts/check.sh           检查虚拟环境与依赖（setup.sh 自动调用，也可单独执行）
scripts/fix.sh             升级兼容：把旧版本的工作区文件改成新格式（setup.sh 自动调用，也可单独执行）
scripts/codex.sh           Codex CLI 启动入口：输入首条消息前打印欢迎语
scripts/root.sh            确定项目根目录，.git/info/exclude 写入（setup.sh、init.sh 共用）
publish/publish.sh         发布：版本号加 1，提交并推送 AgentDevWorkSpace 和 versions 库（publish/versions/）
publish/version            AgentDevWorkSpace 当前版本号，与 versions 库的 AgentDevWorkSpace/version 一致
skills/git-commit/SKILL.md      git-commit skill：提交信息规则
skills/git-commit/commit-msg    提交标签校验（commit-msg hook）
skills/sdd/SKILL.md             sdd skill：SDD 流程、需求目录与编号规则
skills/sdd/constraints.md       通用开发约束规范
skills/sdd/personal-constraints.md  个人约束模板（复制到 <个人目录>/specs/constraints.md）
skills/sdd/new.sh               创建 <个人目录>/<feature|bugfix|change|research>/NNN-<slug>/ 并复制该类型的模板
skills/sdd/new_feature.sh, new_bugfix.sh, new_change.sh, new_research.sh  快捷命令「创建feature/bugfix/change/research:<名称>」对应的入口
skills/sdd/welcome.md, welcome.py  SessionStart hook：新对话时展示 SDD 快捷命令
skills/sdd/check_layout.py      Stop hook：检查需求目录中新增的文件是否已归类（根目录白名单 + NN-<主题>/ 子目录）
skills/sdd/templates/<类型>/    SDD 模板：spec.md、plan.md、tasks.md，按 feature / bugfix / change / research 分开
skills/knowledge/SKILL.md       knowledge skill：开发知识库里有什么（SDD 产物、Note、约束、提交），如何检索和追溯
skills/knowledge/search.sh      按关键词检索所有人的 feature / bugfix / change / research、Note、约束和提交信息
skills/notes/SKILL.md           notes skill：Note 的路径、内容、创建、校验与配置
skills/notes/create.py, template.md  创建 Note（git-commit-change / large-scale-file-change），自动填入时间、未记录的提交或未提交的改动
skills/notes/verify.py          Claude Code / Codex 的 Stop hook：判断是否需要写 Note，按上限合并同一天的旧 Note，任务结束时触发自动更新
skills/notes/update.py          自动更新：SessionStart hook 和 verify.py 触发，后台按版本号检查、拉取 AgentDevWorkSpace，任务结束后执行 setup.sh
skills/notes/config.json5       Note 默认配置（JSON5，带字段注释）
skills/notes/common.py          notes 脚本共用：根目录定位、个人目录、Note 类型与目录、配置读取、未记录提交与工作区改动扫描
```
