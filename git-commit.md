# Git 提交规则

每笔提交信息必须以标签开头：`[标签] 简述`

| 标签 | 用途 |
|---|---|
| `[fix]` | bug 修复 |
| `[feature]` | 新增业务功能 |
| `[update]` | 代码逻辑更新；不属于以上两类时的兜底标签 |

```
[fix] 修复会话重置后标题未清空
[feature] 侧边菜单支持折叠
[update] 重构文件加载逻辑
```

- 一笔提交只做一件事；fix 和 feature 混在一起时拆开提交。
- 启用校验：`git config core.hooksPath .githooks`，不符合格式的提交会被 `.githooks/commit-msg` 拒绝。
