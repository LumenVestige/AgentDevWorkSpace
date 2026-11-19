# 迁移后清理确认已保存的旧副本和空目录

时间：2026-11-19 19:54:40

## Outcome

修复 personal 和 Note 迁移将所有已有目标视为冲突的问题。目录逐项合并，目标已完整保存相同内容时删除源文件，搬空后删除源目录；个人目录中的共享 skills 链接按迁移后位置修正再比较。不同内容、文件与目录类型冲突、符号链接保留，输出仅显示汇总，不再逐条打印迁移路径。README 和 notes 模板文档同步说明，补丁版本发布为 0.3.22。

## Verification

- `tests/workspace/venv/bin/python -B -m unittest discover -s tests -p 'test_fix*.py'`：27 项通过，覆盖重复文件清理、目录合并、链接修正后比较、相同链接文本不同目标、真实内容冲突、符号链接、文件与目录同名冲突、只读检查及重复执行。
- `tests/workspace/venv/bin/python -B -m unittest discover -s tests -p 'test_notes.py'`：14 项通过，确认 Note 记录与旧迁移 API 兼容。
- `git diff --check`：通过。
- 新增清理和精简输出的回归断言在修改前失败，修改后通过。未对用户日志所属项目执行实际迁移。

## 文件改动

```
     2  README.md
    57  scripts/lib/fix.py
     2  skills/notes/SKILL.md
    31  tests/test_fix.py
    78  tests/test_fix_formats.py
```
