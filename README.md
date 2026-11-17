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

`adev` 是 `agentdev` 的等价短命令，支持相同的子命令、参数与退出码，例如 `adev init`、`adev --i`。已有安装重新执行 `source setup.sh` 后即可使用。

直接输入 `agentdev` 默认显示帮助，命令与别名统一如下（例如 `agentdev init` 与 `agentdev --i` 等价）：

| 命令 | 别名 | 行为 |
| --- | --- | --- |
| `agentdev help` | `agentdev --h` | 展示所有命令 |
| `agentdev init [目录]` | `agentdev --i [目录]` | 初始化工作区，完成后自动检查环境；失败返回非零 |
| `agentdev update` | `agentdev --u` | 检查版本，强制覆盖安装目录改动并刷新当前工作区 |
| `agentdev version` | `agentdev --v` | 展示本地与远端版本；查询失败时明确报错 |
| `agentdev check [目录]` | `agentdev --c [目录]` | 只读检查安装目录改动、工作区和环境，不修复文件 |

上表命令的旧单横线形式作为兼容别名保留。安装不属于 app 命令：`setup`、`-setup`、`--s` 已移除，请直接运行或 source 根目录的 `setup.sh`；帮助和示例使用上表规范。

`agentdev update --check` 查询版本并只读检查安装仓库，不安装。`update.sh` 是独立更新入口，版本和源码都取主仓库 master 分支。未安装、Git/Python 缺失、版本查询或更新失败时返回非零，不显示成功。

## 全局目录

```text
~/.agent-dev-workspace/
├── app/             受管理的 master Git 工作树（含独立 .git、源码与 publish/version）
├── venv/            共享 Python 环境，使用 bin/python
├── bin/             agentdev / adev 命令入口
├── env              bash/zsh/sh 激活文件（另有 env.fish）
├── install.json     源仓库、PATH 配置及安装基准 commit
├── update-status.json  手动/自动更新共享状态，原子写入，不随 app 替换
├── logs/            每任务 update-<task_id>.log，保留子进程输出
└── .update.lock     安装级内核更新锁（文件保留，进程退出自动释放锁）
```

setup 在 macOS/Linux 注册当前用户的 shell PATH（zsh 的 `.zshrc`，bash 的 `.bashrc`/登录配置，fish 的 config.fish）；不写系统目录或安装系统级依赖。可用 `source setup.sh --no-path` 跳过 PATH 修改，之后通过完整路径调用 `bin/agentdev` 或 `bin/adev` 。`AGENTDEV_HOME` 可指定安装目录；测试使用仓库内隔离目录，不修改真实主目录。

setup 从 Git 源码安装时要求当前分支为 master。安装目录保留完整 Git 工作树与独立 `.git`，仅克隆 master（浅克隆、无其他分支或标签），不依赖原源码/更新临时目录的对象。源码中尚未提交的受控文件改动和非忽略未跟踪文件会保留，不会伪造提交；被忽略的私有配置、环境不复制。使用带本地改动的源码安装，之后也会收到安装目录改动提示。

`agentdev check`、`agentdev version`、`agentdev update`（含 `--check`）和欢迎语版本检查同时检测安装目录的已暂存/未暂存/删除/未跟踪文件，并将分支及 HEAD 与安装基准比较。异常会展示“异常改动”风险提示和文件名，以及“执行[agentdev update]进行强制覆盖更新。”；即使远端版本查询失败，本地风险也会展示。`check` 不查询远端，发现安装风险时返回非零，仍完成工作区和环境检查；尚未全局安装时只检查工作区。标记文件与 Python 字节码不会导致正常安装误报，当前业务项目的改动不计入安装风险。

手动执行 `agentdev update`（或 `adev update`）允许强制覆盖安装目录改动：同版本发现改动时也会从 master 下载、校验并重新安装，丢弃安装目录的修改、删除和未跟踪文件；干净的同版本安装仍只刷新工作区。自动更新继续保留风险保护，欢迎语发现风险时不启动后台覆盖，hook 的内部 `--project` 调用也不会覆盖风险安装。

旧安装或归档源码没有 `.git` 时明确提示“无法检查”，不是“目录干净”；同版本先补齐独立的 master `.git`，安装干净时仅恢复元数据。有安装 commit 时恢复原基准；没有 commit 时要求 master 与安装版本一致，否则拒绝附加错误基准。补齐后发现异常改动，手动更新继续覆盖安装，自动更新暂停。元数据修复本身不替换已有 `.git`，手动强制重新安装可整体替换风险安装。无 commit 的旧快照在真正有新版时仍兼容原来的完整升级迁移，也可从 master 源码执行 setup.sh 重装。

更新仍根据 `install.json` 记录的 Git 仓库和远端版本，临时克隆 master、验证版本后替换 `app/`，失败保留原程序和可重试状态。安装与更新使用全局互斥锁。保留项目的配置、custom skills、个人约束和 Note；旧项目本地 venv 不删除。在安装目录本身执行 update 不会把它初始化为业务项目。

## 更新进度与通知

手动 `agentdev update` 与欢迎语/Stop hook 的后台更新使用同一个安装级任务：

- 状态写在 `${AGENTDEV_HOME:-~/.agent-dev-workspace}/update-status.json`，不放进 `app/`；采用同目录临时文件、flush/fsync 和原子替换，读取方不会看到半份 JSON。
- `schema_version=1`；记录 `task_id`、`pid`、`client`、`stage`、`started_at/updated_at/finished_at/expires_at`（Unix 秒）、`from_version/to_version`、`result`、`error/failed_stage`、`project` 与 `log_path`。结果为 `running/success/failed/blocked`。
- 真实阶段包括安装目录检查、下载源码、安装依赖、运行环境验证、准备/切换安装、刷新工作区。CLI 输出阶段；Git/pip/init 的子进程输出保存在独立任务日志中。
- 多项目同时触发会等待安装级锁；首个任务升级后，其他项目重新读取版本，仅刷新各自工作区，不重复下载、不生成另一组成功通知，也不覆盖刚完成的状态。
- `--check` 不创建任务；无新版、无需补齐 `.git` 且无需强制覆盖时也不创建任务，不覆盖之前的状态。同版本补齐 `.git` 或强制覆盖复用相同的进度、日志及通知机制。自动更新风险阻止、版本获取失败、下载/安装/刷新失败有终态；安装回滚保留。

查询与控制：

```sh
agentdev update --status          # 查看最近任务及日志，不安装、不查远端
agentdev update --status --watch  # 持续查看；结束结果保留至完成后 10 秒再退出
agentdev update --notify none     # 本次不发系统通知
```

`--notify auto|system|none` 默认 `auto`；`AGENTDEV_NOTIFY` 可设置默认方式，显式非 auto 参数优先。`AGENTDEV_CLIENT=claude|codex` 指明调用客户端，新注册的 hook 自动传递。`--status --watch` 输出普通文本，不擦除终端历史；10 秒清除指 Claude 插件的临时提示，日志与最终状态均保留。

### Claude Code：外置插件

提供 [`plugins/claude-update/`](plugins/claude-update/README.md) Mod 插件，通过官方 `session.start`、`clock.every/after`、`ui.status` 每秒刷新输入框下方的状态，不需要先发送聊天消息，不改原有状态栏设置。成功、失败、暂停按**任务完成时间 + 10 秒**清除，新的任务不会被旧计时器清除。需要支持 Mod 的 Claude Code（官方教程要求 v2.1.287+）；组织策略或安全模式可能禁用插件。

```sh
claude --plugin-dir "${AGENTDEV_HOME:-$HOME/.agent-dev-workspace}/app/plugins/claude-update"
```

这是手动加载示例，setup/init 不写全局 Claude 配置，也不自动安装插件。未加载时仍可使用 CLI 查询。自定义安装路径通过环境变量或项目内受管理安装指针发现。

### Codex：系统通知

Codex 不需要插件或客户端补丁。实际更新任务只发送开始与最终结果两条通知，避免按阶段刷屏；阶段细节可在 CLI/任务日志查看。

- macOS：已有的 `osascript`，固定 AppleScript + 参数传入，不拼接脚本。
- Linux：已有的 `notify-send`，请求 10000ms 超时；缺少通知工具/桌面环境、SSH 会话、通知服务不可用或发送超时均不影响更新，不自动安装依赖。
- 系统通知由 OS/桌面策略控制，**不能跨平台保证精确 10 秒消失**；Claude 插件按本程序时间控制清除。

示例输出（版本仅为测试夹具）：

```text
AgentDevWorkSpace · 下载源码
AgentDevWorkSpace · 安装依赖
AgentDevWorkSpace · 刷新工作区
AgentDevWorkSpace · 更新成功：0.3.0 → 0.4.0
更新日志：<安装根目录>/logs/update-<task_id>.log
```

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

兼容旧版更新器与尚未刷新的 hook，`scripts/agentdev.py`、`scripts/run_skill.py` 仅保留薄转发入口，`scripts/setup.sh`、`scripts/deps.sh` 仅保留链接；实际实现均位于 `command/` 或 `lib/`，不会重新开放 app 的 setup 命令。

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

## 宿主接入与欢迎语

Codex、Claude 仅通过官方提供的 hook 回调或外置插件接入。不得修改宿主启动脚本或 shell 启动配置，也不得用同名函数、别名或命令包装器接管宿主启动。

欢迎语由官方 SessionStart hook 输出，显示时机由客户端决定；不通过启动转发脚本保证输入首条消息前展示。hook 使用项目的 `agent-workspace/skills/custom/sdd/welcome.md`（不存在时使用 common），展示版本信息和 SDD 快捷命令。Claude 的更新进度可通过前述外置插件展示。

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
scripts/command/app.py     CLI 参数解析与命令分发
scripts/command/           help / init / check / update / version 的实现
scripts/command/*.sh       init / check / update 的 shell 入口及 Codex 启动器
scripts/lib/installer.py   全局安装、运行时、PATH 与安装锁
scripts/lib/repository.py  独立 master 工作树安装与 Git 改动风险检查
scripts/lib/setup.py       仅供根 setup.sh 调用的安装实现
scripts/lib/workspace.py   工作区初始化、只读检查及链接/复制
scripts/lib/run_skill.py   hook 分发
scripts/lib/deps.sh        共享依赖清单与手动依赖安装辅助入口
scripts/lib/               bootstrap、旧 Note 迁移、shell 路径辅助
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
