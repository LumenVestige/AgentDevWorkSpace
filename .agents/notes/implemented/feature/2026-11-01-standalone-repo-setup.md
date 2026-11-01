# 独立仓库接入与项目根目录定位

## Outcome

AgentSkill 作为独立 git 仓库 clone 到项目内任意层级子目录使用，只影响当前项目，不修改全局 git 配置。在项目根目录执行 `sh <子目录>/setup.sh` 完成接入：

- 项目根目录按顺序取：`setup.sh` 参数 → 执行命令的目录 → 包含 AgentSkill 的上层 git 仓库；前两项须是 git 仓库根目录且 AgentSkill 位于其下（`lib/root.sh`）。
- 在项目根目录创建相对软链接 `AGENTS.md → <子目录>/AGENTS.md`、`CLAUDE.md → AGENTS.md`，已有同名文件不覆盖。
- 创建 `.agents/tmp/`（临时产物，不提交）和 `.agents/notes/`（Note，随代码提交）。
- 安装转发到 `git/hooks/commit-msg` 的 hook，校验 `[fix]` / `[feature]` / `[update]` 标签；不覆盖项目已有的同名 hook。
- AgentSkill 目录、软链接和 `.agents/tmp/` 写入项目的 `.git/info/exclude`。
- `notes/new.sh` 优先使用 `setup.sh` 记录的根目录，其次按执行目录推断；不在任何项目中时记录到 AgentSkill 自身仓库。

放弃的方案：git submodule 接入（项目要求独立仓库）；全局 `init.templateDir` 实现 clone 后自动初始化（会影响本机所有仓库，项目要求只作用于当前项目）。

## Verification

在临时目录中搭建项目验证：clone 到 `a/b/c/AgentSkill` 后执行 `setup.sh`，软链接与 `.agents/` 创建正确且项目 `git status` 干净；提交信息 `bad` 被拒绝、`[fix] ok` 通过；`setup.sh` 重复执行不产生重复的 exclude 条目；在嵌套仓库中以执行目录为准，执行目录不是仓库根时退回上层仓库，非项目目录中执行时报错退出；`new.sh` 在 setup 前后、项目子目录、AgentSkill 内部及 AgentSkill 单独使用时均写入正确位置。

未覆盖：macOS 与 Windows 环境；项目设置了 `core.hooksPath`（如 lefthook）时的 hook 安装位置。
