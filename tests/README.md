# 自动化测试

在仓库根目录执行（macOS / Linux，Python 3.9+、Git、bash，以及可创建 venv 的 Python/pip）：

```sh
python3 tests/run.py
```

入口从 `scripts/lib/deps.sh` 读取固定依赖，下载 wheel 到 `tests/workspace/wheels/`，在 `tests/workspace/venv/` 安装后，用标准库 `unittest` 发现并运行全部测试。无需先执行全局安装或初始化当前仓库。

已有 wheel 时可完全离线运行：

```sh
python3 tests/run.py --offline
# 或使用已准备好的 wheel 目录（包含 json5==0.12.1）
python3 tests/run.py --offline --wheel-dir /path/to/wheels
```

只运行一个模块：

```sh
python3 tests/run.py --offline --pattern test_config.py
```

准备依赖后，也可直接使用 unittest：

```sh
AGENTDEV_TEST_WHEELS="$PWD/tests/workspace/wheels" \
  tests/workspace/venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

缺依赖、初始化失败、断言失败都会返回非零退出码。默认运行全部 250 个测试方法，数据驱动的方法通过 `subTest` 覆盖多个输入。zsh 激活测试在主机没有 zsh 时显示 skip；bash 激活、fish 配置生成仍会执行。

## 覆盖范围

| 测试文件 | 方法数 | 验证的行为 |
| --- | ---: | --- |
| `test_agentdev.py` | 5 | adev 别名、参数与退出码转发、shell 激活（不再重载 setup 环境）、重装后入口 |
| `test_update_status.py` | 21 | 原子 JSON/完整字段/失败清理、通知路由/macOS 参数/Linux 超时/无桌面与 SSH 降级、真实 Git 升级、并发两项目一组通知且各自刷新、自动 hook 共用状态、只读查询/到期退出、失败及风险终态 |
| `test_claude_plugin.py` | 2 | 插件清单与模块路径；通过 Node.js 执行官方 Mod API 替身验证后台轮询、完成 10 秒清除、新任务计时器隔离、损坏文件降级和会话清理（23 项 JS 断言，不是真实客户端 UI 验收） |
| `test_repository.py` | 31 | 真实 master 独立安装、完整树与 dirty 源保留、忽略私有文件、暂存/未暂存/删除/未跟踪、HEAD/分支、Git 异常/超时、旧快照迁移、worktree/symlink、CLI 与欢迎语风险、阻止覆盖及只读性；同版本补齐 .git、原 commit 恢复、异常保留阻断、错误基准拒绝、下载/元数据失败回滚、现有 Git 不替换、恢复后继续升级 |
| `test_layout.py` | 7 | 移除 setup 及别名、帮助命令列表、command/lib 分层、旧 Python 入口转发 |
| `test_version.py` | 10 | 每个接口独立 5 秒超时、API 限流与 HTTP/网络错误回退、响应内容校验 |
| `test_workspace.py` | 16 | 源码工作区保护、AGENTS 文件引用与旧规则迁移、受管文件保留和刷新 |
| `test_cli.py` | 40 | 默认帮助、所有命令和别名；通过 setup.sh 真实隔离安装/重装；Git/非 Git 初始化后自动 check；check 只读；非法 hook 在写入前拒绝；公共 skill 刷新、自定义与个人文件保留；实际 commit hook；解释器指针；bash/zsh source 激活；旧入口清理；真实本地 master 更新和工作区刷新 |
| `test_config.py` | 14 | JSON5/注释、嵌套默认值合并、配置格式拒绝、新旧配置优先级、personal/peronsal、Git/电脑用户名、Unicode、安全目录名、保留注释迁移版本源、自定义版本源保持原样 |
| `test_installer.py` | 10 | 默认全局路径、拒绝覆盖非托管目录与源码、符号链接保护、锁释放、依赖/激活写入失败回滚、公布版本与源码不一致、bash 用户配置保留、未安装状态的错误 |
| `test_notes.py` | 13 | 提交扫描与 Note 记录闭环、其他人的记录、Note 自身提交排除、路径过滤、基线恢复、关闭开关、大改动文件/行阈值和撤销后重新增长、二进制忽略、无损合并与再次合并、文件碰撞保护、旧 Note 迁移 |
| `test_skills.py` | 17 | 四类 SDD 独立编号/模板、重名拒绝、编号空洞、custom 优先、目录布局/Stop hook 防循环/非 Git/旧提交；hook 调用与路径拒绝；知识检索字面匹配/多关键词/分类文档/Note/约束/Git 历史；提交标签及自动生成信息 |
| `test_update.py` | 16 | 实际欢迎语的新版/相同/旧版/错误版本源；旧格式归一化；后台更新间隔、时钟回拨、关闭开关、锁竞争与失效锁、单次查询、失败日志、ready 重试与清理 |
| `test_version_publish.py` | 27 | 三段整数比较、补丁递增、旧格式读取、非法版本拒绝、旧 URL 映射、API/raw 回退、Base64、超时和 token 作用域；真实本地 bare 仓库发布、缺版本文件、显式版本、待提交文件、多行信息，以及暂存/提交/推送失败后的状态 |
| `test_welcome.py` | 21 | 彩色/纯文本表格、40/60/80/120 列与 Unicode 对齐、旧自定义文案、实际伪终端启动、NO_COLOR/TERM、参数转发、非交互绕过、hook JSON、custom 优先、缺解释器/渲染器/更新器的降级 |

## 隔离与维护

- 安装目录、profile、pip 缓存、源码副本、Git 远端和 HTTP 服务都由夹具创建；不安装到真实用户目录，不改真实 shell 配置，不向 GitHub 推送。
- `AGENTDEV_NOTIFY=none` 默认禁止真实系统通知；通知用例使用 mock 或隔离的假 osascript/notify-send，不向真实桌面发消息。插件行为测试需要已有 Node.js，未安装时明确 skip，不自动安装。
- `AGENTDEV_HOME` 指向测试目录；Git 忽略系统/用户配置，剔除调用者的 Git 覆盖、Python/PIP 覆盖和 GitHub token。普通测试不访问外部版本源；只有运行器首次准备依赖需要网络。
- 源码夹具固定为 `0.3.0`，升级项目版本不会改变断言。用例不依赖个人 SDD 文档、历史运行产物或开发者用户名。
- `tests/workspace/` 已被 `.gitignore` 忽略；每个用例自动清理数据，venv、wheel 和手动保存的日志留在此目录供复用。不要提交这些运行产物。
- 在新平台上执行同一入口验证平台行为。当前运行平台与实际覆盖结果以本轮测试报告为准；未安装的可选 shell 会显示 skip。

## 查看欢迎语与风险提示的实际输出

依赖准备好后执行（不访问真实安装、不联网更新）：

```sh
tests/workspace/venv/bin/python -B tests/show_installation_risk.py
```

脚本在隔离目录创建真实 master 仓库，依次打印 `git branch`、干净版本检查、完整欢迎语、手工改动后的 `update --check`、完整风险欢迎语及被暂停的 `update`。不是只输出测试 OK；退出码和风险文件名也会展示，结束后清理隔离目录。示例版本固定为 0.3.0/0.4.0，不表示本仓库当前发布版本。

## 查看更新进度与 Claude 插件提示输出

```sh
tests/workspace/venv/bin/python -B tests/show_update_status.py
```

真实本地 Git/隔离安装打印下载、依赖、安装切换、完成、状态查询、异常改动暂停及退出码；随后执行 Claude API 替身并打印实际渲染文本与 10 秒后清除值。测试版本固定为 0.3.0/0.4.0/0.5.0，不代表当前发布版本。不会联网升级或发送真实桌面通知。该脚本需要已有 Node.js，不安装任何全局依赖。
