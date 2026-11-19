# AgentDevWorkSpace

通用 Agent 协作规范。具体规则见 [AGENTS.md](AGENTS.md)。

## 1. 安装与接入

需要 Git 和 Python 3.9+。安装程序默认写入用户主目录的 `.agent-dev-workspace/`，不需要管理员权限；安装与项目初始化分开。
macOS / Linux（bash / zsh）：

```sh
git clone https://github.com/LumenVestige/AgentDevWorkSpace.git
source AgentDevWorkSpace/setup.sh  # 安装完成后自动激活当前终端
cd <项目根目录>
agentdev init  # 自动初始化并检查环境，无需再执行 check
```

## 2. agentdev 命令

`adev` 是 `agentdev` 的等价短命令，支持相同的子命令、参数与退出码，例如 `adev init`、`adev --i`。已有安装重新执行 `source setup.sh` 后即可使用。

直接输入 `agentdev` 默认显示帮助，命令与别名统一如下（例如 `agentdev init` 与 `agentdev --i` 等价）：

| 命令 | 别名 | 行为 |
| --- | --- | --- |
| `agentdev help` | `agentdev --h` | 展示所有命令 |
| `agentdev init [目录]` | `agentdev --i [目录]` | 调用 deps.sh 安装共享依赖，再初始化工作区并检查环境；失败返回非零 |
| `agentdev update` | `agentdev --u` | 检查版本，强制覆盖安装目录改动并刷新当前工作区 |
| `agentdev version` | `agentdev --v` | 展示本地与远端版本；查询失败时明确报错 |
| `agentdev fix [目录]` | `agentdev --f [目录]` | 迁移历史 personal 至 workers，并适配旧 Note，不覆盖冲突文件 |
| `agentdev archive [目录]` | `agentdev --a [目录]` | 将较早的开发记录分组移入小写 archived 目录 |
| `agentdev check [目录]` | `agentdev --c [目录]` | 只读检查环境和历史 personal/Note；需迁移时提示 fix |

## 3. 安装目录

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

setup 只安装程序并准备共享 Python venv / pip，不执行 `deps.sh`，也不安装 json5 等 skill 依赖；依赖由 `agentdev init` 显式安装。重装 setup 不卸载已有依赖。

- **安装**：setup 在 macOS/Linux 配置用户 shell PATH，`AGENTDEV_HOME` 指定安装目录。`source setup.sh --no-path` 跳过持久 PATH 配置，仍激活当前会话，也可用完整路径调用 `bin/agentdev` 或 `bin/adev`。Git 源码须在 master 分支，保留受控文件的未提交改动和非忽略未跟踪文件，后续检查会提示。忽略文件不复制。
- **检查**：`agentdev check`、`agentdev version`、`agentdev update`（含 `--check`）和欢迎语均检查安装目录的暂存、未暂存、删除、未跟踪文件及分支、HEAD 与安装基准的差异，不计业务项目改动。远端查询失败仍提示本地风险。`check` 离线检查，安装有风险时返回非零，仍完成工作区和环境检查。未全局安装时只查工作区。
- **更新**：手动 `agentdev update`（或 `adev update`）同版本也可强制重装，丢弃安装目录的修改、删除和未跟踪文件，干净同版只刷新工作区。欢迎语和 hook 自动更新不覆盖风险安装。更新按 `install.json` 中的仓库下载 master、校验版本，失败保留原程序。项目配置、custom skills、个人约束、Note 和旧本地 venv 均保留。安装目录内执行 update 不会初始化为业务项目。
- **旧安装**：缺 `.git` 表示“无法检查”，可用 `agentdev update` 补齐，同版本且干净时只恢复元数据。发现改动后手动更新可覆盖，自动更新暂停。无 commit 的旧快照有新版时仍可升级，也可从 master 源码执行 setup.sh 重装。

## 4. 更新进度与通知

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

`--notify auto|system|none` 默认 `auto`，Claude、Codex 和普通 CLI 统一使用系统通知；`AGENTDEV_NOTIFY` 可设置默认方式，显式非 auto 参数优先。`AGENTDEV_CLIENT=claude|codex` 指明调用客户端，新注册的 hook 自动传递。`--status --watch` 输出普通文本，不擦除终端历史，完成后等待 10 秒退出；日志与最终状态均保留。

### 4.1 Claude Code / Codex：系统通知

两端均无需外置更新插件或客户端补丁。实际更新成功完成后只发送一条系统通知；开始和中间阶段不通知，失败、暂停、无需更新及只读检查也不通知。阶段细节和失败原因可在 CLI 状态查询及任务日志查看。

- macOS：已有的 `osascript`，固定 AppleScript + 参数传入，不拼接脚本。
- Linux：已有的 `notify-send`，请求 10000ms 超时；缺少通知工具/桌面环境、SSH 会话、通知服务不可用或发送超时均不影响更新，不自动安装依赖。
- 系统通知由 OS/桌面策略控制，**不能跨平台保证精确 10 秒消失**。

此前使用 `--plugin-dir …/plugins/claude-update` 的用户应移除该参数，直接运行 `claude`；通过官方插件管理器安装过旧插件的用户可在 `/plugin` 中卸载。更新不会修改全局 Claude 配置或宿主启动脚本。

示例输出（版本仅为测试夹具）：

```text
AgentDevWorkSpace · 下载源码
AgentDevWorkSpace · 安装依赖
AgentDevWorkSpace · 刷新工作区
AgentDevWorkSpace · 更新成功：0.3.0 → 0.4.0
更新日志：<安装根目录>/logs/update-<task_id>.log
```

## 5. 工作区初始化与检查

`agentdev init` 先显式执行安装源码中的 `scripts/lib/deps.sh`，将固定版本依赖安装到全局共享 `venv/`（使用安装级 pip 缓存），完整验证后才在当前目录创建 `agent-workspace/`，不要求工具位于项目内部。支持 Git 仓库根目录和非 Git 目录；在已有 Git 仓库的子目录执行时会提示切换到仓库根目录，避免创建嵌套工作区。Git 项目未配置 personal 时须设置 `git user.name`；非 Git 项目默认使用电脑用户名，不依赖 Git 用户配置。

- 依赖安装失败或超时返回非零，不继续创建或刷新工作区；`check` 和 `fix` 不触发依赖安装。`update` 保留原有依赖安装与环境验证，刷新工作区时也遵循 init 流程。
- `skills/common/` 每次从全局模板整体刷新；`skills/custom/` 保留，同名时优先。
- 按统一命名规则在 `agent-workspace/workers/<personal>/` 创建个人目录、`specs/constraints.md` 和 `notes/`，保留已有内容；不再自动迁移旧版平铺 Note，迁移须显式运行 `agentdev fix`。
- `config/config.json5` 不存在时从模板复制；`.agent/env/python-path` 和 `agentskill-path` 记录共享解释器及全局程序位置。
- 保留项目原有 `AGENTS.md` 内容，标记块只引用 `agent-workspace/AGENTS.md`，通用规则同步到该独立文件，不再追加规则全文；再次初始化会替换旧的受管明文块，并迁移未被用户修改的受管入口。用户自建符号链接和已修改的受管副本保持不变。链接 `CLAUDE.md` 和 `.claude/skills/`；链接不可用时复制，并保留复制后被用户修改的文件。
- 注册 Claude Code 和 Codex 的 Stop / SessionStart hook，保留其他 hook；由共享 Python 启动器选择 custom 优先的脚本。Codex 中仍需由用户信任项目及 hook。
- Git 项目安装提交标签校验 hook（已有其他 hook 时保留）；非 Git 项目跳过。SDD 快捷脚本直接使用本机 POSIX shell。
- `.gitignore` 忽略工作区配置、`.agent/` 和个人约束；工具生成的客户端配置和链接不纳入 Git。

`agentdev check` 不修复或写入文件；它检查当前目录是否存在有效工作区、安装路径和解释器是否可用、Python 3.9+/venv/pip/依赖版本、Note 配置格式以及必要 hook。环境缺项时列出问题并返回非零；发现历史 personal/Note 待迁移时仅显示一条汇总提醒，提示运行 `agentdev fix` 并返回非零，不逐条显示迁移路径，欢迎语中的检查同样适用。检测不会修改文件，暂不包含归档检测。`agentdev init` 已自动执行该检查，日常初始化无需再手动 check。更新后自动刷新当前工作区；其他项目可重新执行 `agentdev init` 同步模板。

在 AgentDevWorkSpace 自身的源码根目录中，`update` 刷新工作区时不会创建、追加或替换 `AGENTS.md` 和 `.gitignore`；skills、环境指针及 hook 仍正常同步，手动 `init` 也遵循相同保护。源码目录通过 Git remote URL 识别（任意 remote 指向主仓库即可，兼容 HTTPS、SSH/SCP 与 git 协议、可选 `.git` 后缀），不依赖目录名或源码文件布局，并排除带 `.agentdev-app` 标记的受管理安装；普通项目保持原有行为。此前已写入这两个文件的内容不会自动清理。

兼容旧版更新器与尚未刷新的 hook，`scripts/agentdev.py`、`scripts/run_skill.py` 仅保留薄转发入口，`scripts/setup.sh`、`scripts/deps.sh` 仅保留链接；实际实现均位于 `command/` 或 `lib/`，不会重新开放 app 的 setup 命令。

## 修复历史 personal 与 Note

```sh
agentdev fix                  # 修复当前工作区（adev fix 等价）
agentdev fix /path/to/project  # 修复指定工作区；也可用 --f / -fix
```

`fix` 独立于 `setup`、`init` 和 `update`，按顺序处理：

1. 将 `agent-workspace/<personal>/` 迁移到 `agent-workspace/workers/<personal>/`。处理配置用户及包含 specs、notes、feature、bugfix、change、research 的历史个人目录，跳过 skills、config、.agent、workers 和无关目录；迁移所有可识别用户，保留个人目录名称。
2. 识别各用户 notes 下两位/四位年份的有效日期前缀文件和主题目录，可带时分秒；去掉日期前缀，放进对应类型的 `YYYY-MM-DD/`，目录整体移动、附件和内容不变。
3. 按 `## Git 提交`（兼容 `Commits` / `提交记录`）节中的实际提交 hash 行分类：有提交记录进入 `git-commit-change`，没有则进入 `large-scale-file-change`。模板占位、诊断 SHA-256 或行内提及旧提交不算提交记录。
4. 纠正旧版 fix 错放在 `git-commit-change/YYYY-MM-DD/` 下的非提交记录；不扫描 archived 分组。

fix 适配所有可识别用户；archive 和个人约束加载仅针对当前配置用户。

目标目录已存在时逐项合并，不覆盖任何同名文件；确认内容相同的文件会删除旧副本，源目录搬空后删除，旧 Note 及其附件目录同样适用。个人目录迁移中的 Markdown 在比较前统一共享 skills 相对链接，避免仅链接层级不同造成假冲突。内容不同、文件与目录类型不符或涉及符号链接时保留源和目标；个人目录冲突返回非零，处理后可重试。迁移输出仅显示汇总，不逐条列出路径。

无历史数据时成功且不写文件。目录不存在、没有 `agent-workspace/` 或配置错误时返回非零，不初始化、安装或更新。旧 `scripts/lib/fix.py` / `fix.sh` 入口保留兼容。init/update 不隐式迁移个人目录或 Note；`check` 与欢迎语只读检测并提示 `agentdev fix`。

## 6. 开发记录分组归档

```sh
agentdev archive                 # adev archive 等价；也可用 --a / -archive
agentdev archive /path/to/project
```

仅整理当前 `agent-workspace/workers/<personal>/` 用户目录的 `feature`、`bugfix`、`change`、`research`、`notes/git-commit-change` 和
`notes/large-scale-file-change` 六个目录，不由 setup/init/update 自动触发。
每个目录的直接文件/子目录超过 N 时，保留按名称排序最新的 N 项，将较早的超出部分按名称顺序移入
该目录的小写 `archived/01/`、`archived/02/`…，每组最多 M 项；补满最后一个组后再增加编号。
Note 以日期目录为一项，不拆散日期或主题目录；隐藏项、符号链接和 `archived` 本身不参与数量统计。
同名目标不覆盖并提示保留源文件；不存在的目录不创建。归档保留条目内部结构与内容，不重写文档中的跨目录链接。
SDD 新编号/同名检查、布局检查和知识检索覆盖已归档需求；已归档 Note 仍参与提交记录识别。

在 `agent-workspace/config/config.json5` 中配置（均为正整数，缺失字段使用默认值）：

```json5
{ archive: { threshold: 50, group_size: 100 } }
```

## 7. 个人目录与统一配置

个人目录统一位于 `agent-workspace/workers/<personal>/`。配置路径为 `agent-workspace/config/config.json5`，例如：

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
- 仅修改 personal 配置时，后续 init、SDD、Note 和 layout 使用新名称，不自动重命名其他个人目录。历史层级迁移通过 `agentdev fix` 显式执行；新增需求时会补齐新目录的个人约束模板。
- init 会把旧 `notes.json5` 更名为 `config.json5`，保留内容和注释；两者并存时新文件优先，旧文件不覆盖或合并。
- 无论是否是 Git 仓库，init 都会正常创建或补充 `.gitignore`，保留已有条目。

### 个人开发约束

`agent-workspace/workers/<personal>/specs/constraints.md` 及同目录树内其他 Markdown 文件通过独立的
`SessionStart` hook 加载进 Agent 上下文，按当前配置选择用户，不读取其他用户或符号链接目标。
通用约束优先使用 `skills/custom/sdd/constraints.md`，没有时使用 common；通用约束优先于个人约束。
启动、恢复、clear 和 compact 后均加载，不因自定义欢迎语被绕过；配置或文件读取错误明确报告。
升级源码后需在目标项目执行 `agentdev init` 或更新工作区来同步 skill 和 hook；既有约束内容不会被覆盖。
每次开发任务仍需读取最新源文件，尤其是会话内修改约束后。hook 提供约束上下文，不对任意自然语言规则作自动语义验证；spec/plan 仍须逐项检查。

## 8. 宿主接入与欢迎语

Codex、Claude 仅通过官方提供的 hook 回调或外置插件接入。不得修改宿主启动脚本或 shell 启动配置，也不得用同名函数、别名或命令包装器接管宿主启动。

欢迎语由官方 SessionStart hook 输出，显示时机由客户端决定；不通过启动转发脚本保证输入首条消息前展示。hook 使用项目的 `agent-workspace/skills/custom/sdd/welcome.md`（不存在时使用 common），展示版本信息和 SDD 快捷命令。欢迎语同时运行只读 `check`，展示环境及历史数据迁移提示；发现待迁移项时提示 `agentdev fix`。更新成功完成后，两端统一发送系统通知。

## 9. 版本与发布

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

旧配置中的废弃版本地址在读取时映射为主仓库版本文件，`init` 会在保留其他设置和注释的同时替换实际配置值。`check` 保持只读。旧整数/小数版安装应先同步新源码并重新运行 setup 和 init，使所有入口使用三段版本；已有 personal 目录通过 `agentdev fix` 显式迁移到 workers/。

私有仓库可通过现有 `GITHUB_TOKEN` / `GH_TOKEN` 环境变量读取版本；令牌仅发送给对应主仓库的 GitHub API，不发送给自定义地址。`AGENTDEV_VERSION_URL` 可指定验证用文件/HTTP 地址。

## 10. 文件列表

`skills/` 是通用 skill 模板包，安装时复制到项目的 `agent-workspace/skills/common/`，Agent 和 hook 都使用工作区中的副本。

```
AGENTS.md                  规则
agentdev / adev             macOS/Linux 源码命令入口，默认展示帮助
setup.sh                   安装与 bash/zsh 当前会话激活入口
update.sh                  独立更新入口
scripts/command/app.py     CLI 参数解析与命令分发
scripts/command/           help / init / check / fix / archive / update / version 的实现
scripts/command/*.sh       init / check / update 的 shell 入口及 Codex 启动器
scripts/lib/fix.py, fix.sh  历史 personal / Note 迁移及兼容入口
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
skills/sdd/load_constraints.py  独立 SessionStart hook，加载当前用户 specs/**/*.md 和 custom 优先通用约束
skills/sdd/personal-constraints.md  个人约束模板（复制到 workers/<个人目录>/specs/constraints.md）
skills/sdd/new.sh               创建 workers/<个人目录>/<feature|bugfix|change|research>/NNN-<slug>/ 并复制该类型的模板
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

---

本文由 AgentWorkFlow 生成
