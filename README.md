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
- 创建 `.agents/tmp/`（临时产物）和 `.agents/notes/`（Note 记录）；
- 在 `.agents/tmp/venv/` 创建 Python 3.9+ 虚拟环境，路径记入 `git config agentskill.python`，后续 Python 脚本都用它运行；
- 把 `notes/verify.py` 注册为 Claude Code 的 Stop hook（写入 `.claude/settings.local.json`），每轮对话结束时检查未记录到 Note 的提交和 Note 上限；
- 为当前项目安装 `commit-msg` hook，检查 `[fix]` / `[feature]` / `[del]` / `[update]` 标签；
- 把 `.agents/` 写入项目根目录的 `.gitignore`（已有则跳过）；AgentSkill 目录和两个软链接写入 `.git/info/exclude`。

可重复执行。

## 文件

```
AGENTS.md                  规则
setup.sh                   项目初始化
lib/root.sh                确定项目根目录
git/hooks/commit-msg       提交标签校验
notes/create.py, template.md  创建 Note
notes/verify.py            每轮对话结束时检查是否需要写 Note、删除超出 30 条的旧 Note
notes/common.py            notes 脚本共用的根目录定位
```
