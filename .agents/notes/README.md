# Notes

大改动（行为、架构、接口、数据格式）在同一笔提交里写一条记录。

## 路径

`.agents/notes/<状态>/<分类>/yyyy-mm-dd-<主题>.md`

- 状态：`proposed`（计划中）或 `implemented`（已完成）
- 分类：`feature` / `fix` / `update`，与提交标签一致
- 日期：首次写这条 Note 的日期；主题用英文小写，单词之间用 `-` 连接

例：`.agents/notes/implemented/feature/2026-08-25-local-cli-status-restart.md`

## 内容

```markdown
# <标题>

## Outcome
<改了什么、现在的行为>

## Verification
<跑了哪些检查，哪些没覆盖>
```

完成后把文件从 `proposed/` 移到 `implemented/`；同一主题有后续改动时更新原文件。
