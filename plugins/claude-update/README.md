# AgentDevWorkSpace Claude 更新提示插件

独立 Claude Code Mod 插件：不替换客户端、不改用户原有 `statusLine`，在输入框下方显示本插件的更新状态。

## 加载

需要支持 Mod 的 Claude Code；官方入门文档要求 **v2.1.287+**。安全模式、`--bare`、`disableAllHooks` 或组织策略可能禁用 Mod。

源码中试用：

```sh
claude --plugin-dir /绝对路径/AgentDevWorkSpace/plugins/claude-update
```

已安装 AgentDevWorkSpace：

```sh
claude --plugin-dir "${AGENTDEV_HOME:-$HOME/.agent-dev-workspace}/app/plugins/claude-update"
```

以上是用户主动执行的加载命令；AgentDevWorkSpace 不自动安装全局插件，不覆盖全局 Claude 配置。可在 `/plugin` 中确认插件是否加载。项目仍需 `agentdev init` 注册自动更新 hook；此插件只读展示，不额外触发升级。

## 行为

- `session.start` 启动定时器，每秒读取安装根目录的 `update-status.json`，无需发送消息，空闲时也刷新。
- 依次识别 `AGENTDEV_HOME`、当前项目/祖先的受管理安装指针、默认 `$HOME/.agent-dev-workspace`；自定义路径建议显式导出 `AGENTDEV_HOME`。
- 显示检查、下载、依赖、验证、安装切换与工作区刷新阶段；不伪造百分比。
- 成功、失败、暂停按写入端 `finished_at + 10` 秒清除，只清除本插件自己的状态。最终 JSON/日志不删除；旧结果不会在新会话重新展示。
- 新任务出现会取消旧任务清理计时器；结束会话取消轮询和清理计时器。
- 丢失或损坏的状态文件不会中断 Claude。此插件不写更新状态、不获取网络、不运行更新命令。
- 插件会给会话子进程设置 `AGENTDEV_CLIENT=claude`。新注册的 Claude/Codex hook 同时显式携带 `--client`，避免同项目跨客户端时误判。

## 验证边界

`tests/test_claude_plugin.mjs` 用官方 API 形状的替身验证轮询、显示、过期、路径发现与会话清理；它不是 Claude UI 的实机验收。真实客户端可选运行 `claude plugin validate <插件目录>`，由用户在自己的客户端环境执行。

参考官方接口：

- https://code.claude.com/docs/en/plugins/mods/create
- https://code.claude.com/docs/en/plugins/mods/api
- https://github.com/anthropics/claude-code/blob/main/mods/types/claude-code.d.ts
