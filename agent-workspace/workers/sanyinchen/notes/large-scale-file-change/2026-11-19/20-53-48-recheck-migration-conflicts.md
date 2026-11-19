# 复检迁移冲突并清理旧目录及空父目录

时间：2026-11-19 20:53:48

## Outcome

修复上一版先改写 Markdown 链接再比较、导致原始字节相同的文件被判冲突的问题：先比较原始内容，不同再比较共享 skills 链接修正后的内容，相同时删除历史副本。Note 分类后再次按最终路径合并并校验旧 personal 目录，仅汇总最终剩余冲突；清理搬空的旧个人目录和 Note 日期、类型父目录，保留当前 notes 根目录。真实差异和符号链接继续保留。README 和 notes 模板同步说明，补丁版本发布为 0.3.23。

## Verification

- `tests/workspace/venv/bin/python -B -m unittest discover -s tests -p 'test_fix*.py'`：最终 30 项通过，覆盖原始字节比较、迁移后冲突复检、真实冲突保留、空父目录清理及重复执行。
- `tests/workspace/venv/bin/python -B -m unittest discover -s tests -p 'test_notes.py'`：14 项通过。
- `git diff --check`：通过。
- 三项新增回归断言在修改前复现失败、修改后通过；后续增加最终路径真实冲突保留用例并完成相关测试。未访问或修改截图中 VirtualDevicePlatform 项目的文件。

## 文件改动

```
     2  README.md
    21  scripts/lib/fix.py
     2  skills/notes/SKILL.md
    37  tests/test_fix.py
    13  tests/test_fix_formats.py
```
