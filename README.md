# AgentDevWorkSpace

通用 Agent 协作规范。具体规则见 [AGENTS.md](AGENTS.md)。

## 安装与接入

需要 Git 和 Python 3.9+。安装程序默认写入用户主目录的 `.agent-dev-workspace/`，不需要管理员权限；安装与项目初始化分开。

macOS / Linux（bash / zsh）：

```sh
git clone https://github.com/LumenVestige/AgentDevWorkSpace.git
source AgentDevWorkSpace/setup.sh  # 安装完成后自动激活当前终端
cd <项目根目录>
agentdev init  # 自动初始化并检查环境，无需再执行 check
```

fish 中先运行 `sh AgentDevWorkSpace/setup.sh`，再执行安装器输出的 `source .../env.fish` 激活命令。普通 `sh setup.sh` 无法修改父终端 PATH，会输出本 shell 的激活命令；source 入口在当前会话自动生效。`--no-path` 只跳过持久 PATH 配置，显式 source 仍激活当前会话。

当前仅支持 macOS 和 Linux。可在源码目录直接运行 `./agentdev` 或 `./adev`；setup 只负责全局安装，项目接入用 `agentdev init`，完成后自动检查环境。

## agentdev 命令

`adev` 是 `agentdev` 的等价短命令，支持相同的子命令、参数与退出码，例如 `adev init`、`adev --i`。已有安装重新执行 `agentdev setup` 后即可使用。

直接输入 `agentdev` 默认显示帮助，命令与别名统一如下（例如 `agentdev init` 与 `agentdev --i` 等价）：

| 命令 | 别名 | 行为 |
| --- | --- | --- |
| `agentdev help` | `agentdev --h` | 展示所有命令 |
| `agentdev setup` | `agentdev --s` | 全局安装或重新安装程序及共享依赖 |
| `agentdev init [目录]` | `agentdev --i [目录]` | 初始化工作区，完成后自动检查环境；失败返回非零 |
| `agentdev update` | `agentdev --u` | 检查版本，有新版时更新全局程序和当前工作区 |
| `agentdev version` | `agentdev --v` | 展示本地与远端版本；查询失败时明确报错 |
| `agentdev check [目录]` | `agentdev --c [目录]` | 单独只读检查工作区和环境，不修复文件 |

旧单横线形式作为兼容别名保留，帮助和示例使用上表规范。

`agentdev update --check` 仅查询版本，不安装。`update.sh` 是独立更新入口，版本和源码都取主仓库 master 分支。未安装、Git/Python 缺失、版本查询或更新失败时返回非零，不显示成功。

## 全局目录

```text
~/.agent-dev-workspace/
├── app/             受管理的程序和 skill 模板（含 publish/version）
├── venv/            共享 Python 环境，使用 bin/python
├── bin/             agentdev / adev 命令入口
├── env              bash/zsh/sh 激活文件（另有 env.fish）
└── install.json     更新使用的源仓库与 PATH 配置状态
```

setup 在 macOS/Linux 注册当前用户的 shell PATH（zsh 的 `.zshrc`，bash 的 `.bashrc`/登录配置，fish 的 config.fish）；不写系统目录或安装系统级依赖。可用 `agentdev setup --no-path` 跳过 PATH 修改，之后通过完整路径调用 `bin/agentdev` 或 `bin/adev` 。`AGENTDEV_HOME` 可指定安装目录；测试使用仓库内隔离目录，不修改真实主目录。

setup 可从当前源码安装，包含尚未提交的源码改动；更新根据 `install.json` 记录的 Git 仓库和远端版本，下载到临时目录，验证版本后替换 `app/`，失败保留原程序和可重试状态。安装与更新使用全局互斥锁。保留项目的配置、custom skills、个人约束和 Note；旧项目本地 venv 不删除。

## 工作区初始化与检查

`agentdev init` 在当前目录创建 `agent-workspace/`，不要求工具位于项目内部。支持 Git 仓库根目录和非 Git 目录；在已有 Git 仓库的子目录执行时会提示切换到仓库根目录，避免创建嵌套工作区。Git 项目未配置 personal 时须设置 `git user.name`；非 Git 项目默认使用电脑用户名，不依赖 Git 用户配置。

- `skills/common/` 每次从全局模板整体刷新；`skills/custom/` 保留，同名时优先。
- 按统一命名规则创建个人目录、`specs/constraints.md` 和 `notes/`，保留已有内容；旧版平铺 Note 迁移到按类型、日期归档的目录，目标已有时不覆盖。
- `config/config.json5` 不存在时从模板复制；`.agent/env/python-path` 和 `agentskill-path` 记录共享解释器及全局程序位置。
- 保留项目原有 `AGENTS.md` 内容，标记块只引用 `agent-workspace/AGENTS.md`，通用规则同步到该独立文件，不再追加规则全文；再次初始化会替换旧的受管明文块，并迁移未被用户修改的受管入口。用户自建符号链接和已修改的受管副本保持不变。链接 `CLAUDE.md` 和 `.claude/skills/`；链接不可用时复制，并保留复制后被用户修改的文件。
- 注册 Claude Code 和 Codex 的 Stop / SessionStart hook，保留其他 hook；由共享 Python 启动器选择 custom 优先的脚本。Codex 中仍需由用户信任项目及 hook。
- Git 项目安装提交标签校验 hook（已有其他 hook 时保留）；非 Git 项目跳过。SDD 快捷脚本直接使用本机 POSIX shell。
- `.gitignore` 忽略工作区配置、`.agent/` 和个人约束；工具生成的客户端配置和链接不纳入 Git。

`agentdev check` 不修复或写入文件；它检查当前目录是否存在有效工作区、安装路径和解释器是否可用、Python 3.9+/venv/pip/依赖版本、Note 配置格式以及必要 hook。缺项会列出并返回非零。`agentdev init` 已自动执行该检查，日常初始化无需再手动 check。更新后自动刷新当前工作区；其他项目可重新执行 `agentdev init` 同步模板。

在 AgentDevWorkSpace 自身的源码根目录中，`update` 刷新工作区时不会创建、追加或替换 `AGENTS.md` 和 `.gitignore`；skills、环境指针及 hook 仍正常同步，手动 `init` 也遵循相同保护。源码目录通过 Git remote URL 识别（任意 remote 指向主仓库即可，兼容 HTTPS、SSH/SCP 与 git 协议、可选 `.git` 后缀），不依赖目录名或源码文件布局，并排除带 `.agentdev-app` 标记的受管理安装；普通项目保持原有行为。此前已写入这两个文件的内容不会自动清理。

## 个人目录与统一配置

配置路径为 `agent-workspace/config/config.json5`，例如：

```json5
{
  personal: "alice", // 可修改个人目录名；留空使用默认规则
  enabled: true,
  auto_update: true,
}
```

- `personal` 非空时优先，兼容拼写 `peronsal`；两者都填写时以 `personal` 为准。
- 默认 Git 仓库根目录取 `git user.name`，非 Git 目录取当前电脑用户名，统一转小写并把空格、标点换成 `-`。
- 禁止路径、空目录名、工作区保留目录名。
- 修改后，后续 init、SDD、Note 和 layout 使用新名称；旧个人目录及其数据不迁移、不合并、不删除。新增需求时会补齐新目录的个人约束模板。
- init 会把旧 `notes.json5` 更名为 `config.json5`，保留内容和注释；两者并存时新文件优先，旧文件不覆盖或合并。
- 无论是否是 Git 仓库，init 都会正常创建或补充 `.gitignore`，保留已有条目。

## Codex CLI 启动欢迎语

要在输入任何消息前看到欢迎语，在已接入项目中用以下入口启动（支持原有 CLI 参数）：

```sh
sh <AgentDevWorkSpace 路径>/scripts/codex.sh
```

入口先查询并打印 AgentDevWorkSpace 的版本信息或更新提示，以及项目 `agent-workspace/skills/custom/sdd/welcome.md`（不存在时使用 common）；发现新版本时在后台更新（notes skill 的 `update.py --welcome`），
再用 `--no-alt-screen` 启动原生 Codex，保留终端中的欢迎语；不发送初始消息、不调用模型。
欢迎语使用带 emoji 的三列表格展示快捷命令、用途和示例，中文列自动对齐，窄终端自动换行；交互终端带彩色标题和版本状态，设置 `NO_COLOR=1` 或 `TERM=dumb` 可关闭颜色。SessionStart hook 输出无 ANSI 的纯文本表格，缺少渲染器或 Python 时启动入口保留文本显示。
`--help`、`--version`、`exec` 等子命令、恢复会话及重定向输出直接转发，不打印欢迎语。
支持从项目子目录启动和 `-C/--cd` 指定项目。此入口只处理进程启动，CLI 内部 `/clear` 仍由 hook 处理。

如果希望仍直接输入 `codex`，可在自己的 zsh 配置中添加转发函数，把下面路径改为实际绝对路径：

```sh
function codex {
  sh '/绝对路径/AgentDevWorkSpace/scripts/codex.sh' "$@"
}
```

setup 只注册 agentdev 所需的 PATH，不会添加 codex 转发函数；移除该函数即可恢复原生命令。

## 版本与发布

唯一版本源是[主仓库 master 分支的 publish/version](https://github.com/LumenVestige/AgentDevWorkSpace/blob/master/publish/version)。CLI `version` / `update`、欢迎语和自动更新使用同一解析与读取逻辑，优先通过同文件的 GitHub contents API 获取，失败时回退到原始文件地址，不依赖外部版本仓库。

版本固定为 `大版本.小版本.补丁版本`（MAJOR.MINOR.PATCH），例如 `0.3.0`，按三个整数比较：`0.9.10 > 0.9.2`、`0.10.0 > 0.9.99`。不使用浮点数；不接受负数、前导零、额外段数、预发布标识或 v 前缀。迁移期间兼容读取旧的 `0.3` / `7`，分别显示为 `0.3.0` / `7.0.0`；新发布参数必须严格三段。

```sh
# 未指定版本：补丁号 +1，例如 0.3.0 → 0.3.1
sh publish/publish.sh "[update] <改动说明>"
# 指定小版本或大版本
sh publish/publish.sh "[update] 发布版本 0.4.0" 0.4.0
sh publish/publish.sh "[update] 发布版本 1.0.0" 1.0.0
```

发布只修改本仓库的 `publish/version`，按标签规则提交全部未忽略的改动，再推送本仓库当前分支。提交失败恢复版本文件；推送失败保留已完成的提交并明确返回错误。没有第二仓库的 clone、pull、版本对齐、提交或 push。

旧配置中的废弃版本地址在读取时映射为主仓库版本文件，`init` 会在保留其他设置和注释的同时替换实际配置值。`check` 保持只读。旧整数/小数版安装应先同步新源码并重新运行 setup 和 init，使所有入口使用三段版本；已有 personal 目录仍不迁移。

私有仓库可通过现有 `GITHUB_TOKEN` / `GH_TOKEN` 环境变量读取版本；令牌仅发送给对应主仓库的 GitHub API，不发送给自定义地址。`AGENTDEV_VERSION_URL` 可指定验证用文件/HTTP 地址。

## 文件列表

`skills/` 是通用 skill 模板包，安装时复制到项目的 `agent-workspace/skills/common/`，Agent 和 hook 都使用工作区中的副本。

```
AGENTS.md                  规则
agentdev / adev             macOS/Linux 源码命令入口，默认展示帮助
setup.sh                   安装与 bash/zsh 当前会话激活入口
update.sh                  独立更新入口
scripts/agentdev.py         命令解析、全局安装、更新、版本与 PATH 注册
scripts/workspace.py        工作区初始化、只读检查及平台链接/复制
scripts/run_skill.py        跨平台 hook 分发
scripts/setup.sh           全局安装 / 重新安装及 bash/zsh source 激活
scripts/init.sh            agentdev init 的 POSIX 兼容入口，初始化项目和工作区
scripts/deps.sh            共享依赖清单与 POSIX 手动安装入口
scripts/check.sh           agentdev check 的 POSIX 入口，工作区与环境只读检查
scripts/fix.sh             旧 Note 迁移的 POSIX 兼容入口（init 自动迁移）
scripts/codex.sh           Codex CLI 启动入口：输入首条消息前打印欢迎语
scripts/root.sh            保留的旧版 shell 路径辅助；新入口使用跨平台核心
publish/publish.sh         发布：默认补丁 +1，支持指定三段版本，只提交并推送主仓库
publish/version            唯一版本文件（MAJOR.MINOR.PATCH）
skills/git-commit/SKILL.md      git-commit skill：提交信息规则
skills/git-commit/commit-msg    提交标签校验（commit-msg hook）
skills/sdd/SKILL.md             sdd skill：SDD 流程、需求目录与编号规则
skills/sdd/constraints.md       通用开发约束规范
skills/sdd/personal-constraints.md  个人约束模板（复制到 <个人目录>/specs/constraints.md）
skills/sdd/new.sh               创建 <个人目录>/<feature|bugfix|change|research>/NNN-<slug>/ 并复制该类型的模板
skills/sdd/new_feature.sh, new_bugfix.sh, new_change.sh, new_research.sh  快捷命令「创建feature/bugfix/change/research:<名称>」对应的入口
skills/sdd/welcome.md, welcome.py  SessionStart hook：新对话时展示 SDD 快捷命令
skills/sdd/render_welcome.py       欢迎语表格与终端配色，供 hook 和 CLI 入口共用
skills/sdd/check_layout.py      Stop hook：检查需求目录中新增的文件是否已归类（根目录白名单 + NN-<主题>/ 子目录）
skills/sdd/templates/<类型>/    SDD 模板：spec.md、plan.md、tasks.md，按 feature / bugfix / change / research 分开
skills/knowledge/SKILL.md       knowledge skill：开发知识库里有什么（SDD 产物、Note、约束、提交），如何检索和追溯
skills/knowledge/search.sh      按关键词检索所有人的 feature / bugfix / change / research、Note、约束和提交信息
skills/notes/SKILL.md           notes skill：Note 的路径、内容、创建、校验与配置
skills/notes/create.py, template.md  创建 Note（git-commit-change / large-scale-file-change），自动填入时间、未记录的提交或未提交的改动
skills/notes/verify.py          Claude Code / Codex 的 Stop hook：判断是否需要写 Note，按上限合并同一天的旧 Note，任务结束时触发自动更新
skills/notes/update.py          自动更新触发器，委托独立 update 核心更新全局程序及当前工作区
skills/notes/config.json5       工作区默认配置模板（复制为 config/config.json5，含 personal 与 Note 设置）
skills/_workspace_config.py     统一配置读取、personal/peronsal 和旧版本地址迁移
skills/_version.py              三段版本解析、比较、主仓库文件查询与旧格式读取
skills/notes/common.py          notes 脚本共用：根目录定位、个人目录、Note 类型与目录、配置读取、未记录提交与工作区改动扫描
```
