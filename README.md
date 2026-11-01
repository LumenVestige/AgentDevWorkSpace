# AgentSkill

通用 Agent 协作规范。作为独立 git 仓库 clone 到项目内的任意子目录使用，只影响当前项目。规则见 [AGENTS.md](AGENTS.md)。

## 接入

在项目根目录执行：

```sh
git clone <AgentSkill 仓库地址> <任意层级子目录>
sh <子目录>/setup.sh
```

## 项目根目录的确定顺序

1. `setup.sh` 的参数；
2. 执行命令时所在的目录；
3. 包含 AgentSkill 的上层 git 仓库。

前两项只有在满足以下条件时才会被采用：该目录是 git 仓库的根目录，且 AgentSkill 位于该目录之下。

## setup.sh 介绍

- 在项目根目录创建相对软链接 `AGENTS.md → <子目录>/AGENTS.md` 和 `CLAUDE.md → AGENTS.md`（已有同名文件则跳过）；
- 创建 `.agents/tmp/`（临时产物）、`.agents/notes/`（Note 记录）和 `.agents/config/`；`notes.json5` 不存在时从 `notes/config.json5` 复制（Note 开关、上限、扫描规则）；
- 在 `.agents/tmp/venv/` 创建 Python 3.9+ 虚拟环境，路径记入 `git config agentskill.python`，后续 Python 脚本都用它运行；
- 执行 `scripts/deps.sh`，用该虚拟环境的 pip 安装依赖（清单写在 deps.sh 中，已满足时跳过）；
- 执行 `scripts/check.sh`，检查虚拟环境与依赖是否安装成功，失败时中止；
- 把 `notes/verify.py` 注册为 Claude Code 的 Stop hook（写入 `.claude/settings.local.json`），每轮对话结束时检查未记录到 Note 的提交和 Note 上限；
- 为当前项目安装 `commit-msg` hook，检查 `[fix]` / `[feature]` / `[del]` / `[update]` 标签；
- 把 `.agents/` 写入项目根目录的 `.gitignore`（已有则跳过）；AgentSkill 目录和两个软链接写入 `.git/info/exclude`。

可重复执行。

## 文件

```
AGENTS.md                  规则
setup.sh                   → scripts/setup.sh 的软链接
scripts/setup.sh           项目初始化
scripts/deps.sh            Python 依赖清单，安装到虚拟环境（setup.sh 自动调用）
scripts/check.sh           检查虚拟环境与依赖（setup.sh 自动调用，也可单独执行）
lib/root.sh                确定项目根目录
git/hooks/commit-msg       提交标签校验
notes/create.py, template.md  创建或更新 Note，自动填入时间与未记录的提交
notes/verify.py            每轮对话结束时判断是否需要写 Note，按上限删除旧 Note
notes/config.json5         Note 默认配置（JSON5，带字段注释）
notes/common.py            notes 脚本共用：根目录定位、配置读取、未记录提交扫描
```
