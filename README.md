# AgentSkill

通用 Agent 协作规范。具体规则见 [AGENTS.md](AGENTS.md)。

## 接入

在项目根目录执行：

```sh
git clone https://github.com/LumenVestige/AgentSkill.git <任意层级子目录>
sh <子目录>/setup.sh
```

项目根目录不是 git 仓库时，须显式传入根目录：`sh <子目录>/setup.sh <项目根目录>`。此时照常创建软链接、`.agents/`、
Python 环境和 Stop hook，跳过 `.git/info/exclude`、`commit-msg` hook 和项目的 `git config`（路径只记在 AgentSkill 仓库中）；
没有提交，Note 不会因提交触发。之后 `git init` 的话，重新执行一次 setup.sh 即可补上跳过的部分。

## setup.sh 介绍

- 在项目根目录创建相对软链接 `AGENTS.md → <子目录>/AGENTS.md` 和 `CLAUDE.md → AGENTS.md`（已有同名文件则跳过）；
- 创建 `.agents/tmp/`（临时产物）、`.agents/notes/`（Note 记录）和 `.agents/config/`；`notes.json5` 不存在时从 `notes/config.json5` 复制（Note 开关、上限、自动更新、扫描规则）；
- 在 `.agents/tmp/venv/` 创建 Python 3.9+ 虚拟环境，路径记入 `git config agentskill.python`，后续 Python 脚本都用它运行；
- 执行 `scripts/deps.sh`，用该虚拟环境的 pip 安装依赖（清单写在 deps.sh 中，已满足时跳过）；
- 执行 `scripts/check.sh`，检查虚拟环境与依赖是否安装成功，失败时中止；
- 把 `notes/verify.py` 注册为 Claude Code 的 Stop hook（写入 `.claude/settings.local.json`），每轮对话结束时检查未记录到 Note 的提交和 Note 上限；运行前若距上次更新超过 `auto_update_interval_hours`（默认 24 小时），先拉取 AgentSkill（`git pull --ff-only`，工作区有改动时跳过）并重新执行 setup.sh；
- 为当前项目安装 `commit-msg` hook，检查 `[fix]` / `[feature]` / `[del]` / `[update]` 标签；
- 把 `.agents/` 写入项目根目录的 `.gitignore`（已有则跳过）；AgentSkill 目录和两个软链接写入 `.git/info/exclude`。

## 文件列表

```
AGENTS.md                  规则
setup.sh                   → scripts/setup.sh 的软链接
scripts/setup.sh           项目初始化
scripts/deps.sh            Python 依赖清单，安装到虚拟环境（setup.sh 自动调用）
scripts/check.sh           检查虚拟环境与依赖（setup.sh 自动调用，也可单独执行）
lib/root.sh                确定项目根目录
git/hooks/commit-msg       提交标签校验
notes/create.py, template.md  创建 Note，自动填入时间与未记录的提交
notes/verify.py            每轮对话结束时按需自动更新，判断是否需要写 Note，按上限删除旧 Note
notes/config.json5         Note 默认配置（JSON5，带字段注释）
notes/common.py            notes 脚本共用：根目录定位、配置读取、未记录提交扫描
```
