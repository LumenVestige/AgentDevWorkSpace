# AgentSkill

通用 Agent 协作规范。具体规则见 [AGENTS.md](AGENTS.md)。

## 接入

在项目根目录执行：

```sh
git clone https://github.com/LumenVestige/AgentSkill.git <任意层级子目录>
sh <子目录>/setup.sh
```

## setup.sh 介绍

- 在项目根目录创建相对软链接 `AGENTS.md → <子目录>/AGENTS.md` 和 `CLAUDE.md → AGENTS.md`（已有同名文件则跳过）；
- 创建 `.agents/tmp/`（临时产物）和 `.agents/notes/`（Note 记录）；
- 为当前项目安装 `commit-msg` hook，检查 `[fix]` / `[feature]` / `[del]` / `[update]` 标签；
- 把 `.agents/` 写入项目根目录的 `.gitignore`（已有则跳过）；AgentSkill 目录和两个软链接写入 `.git/info/exclude`。

## 文件列表

```
AGENTS.md                  规则
setup.sh                   项目初始化
lib/root.sh                确定项目根目录
git/hooks/commit-msg       提交标签校验
notes/new.sh, template.md  创建 Note
```
