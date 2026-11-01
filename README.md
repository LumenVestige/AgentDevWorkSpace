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
- 为当前项目安装 `commit-msg` hook，检查 `[fix]` / `[feature]` / `[del]` / `[update]` 标签；
- 把 AgentSkill 目录、两个软链接和 `.agents/tmp/` 写入项目的 `.git/info/exclude`，不污染项目仓库。

可重复执行。

## 文件

```
AGENTS.md                  规则
setup.sh                   项目初始化
lib/root.sh                确定项目根目录
git/hooks/commit-msg       提交标签校验
notes/new.sh, template.md  创建 Note
```
