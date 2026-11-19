# 合并历史迁移检查提示，避免逐条输出路径

时间：2026-11-19 19:46:38

## Outcome

只读 check（含欢迎语和 init 复用的检查）将历史 personal / Note 待迁移项合并为一条提醒，继续提示运行 agentdev fix 并返回非零。保留环境错误和不安全目录提示，迁移候选规则与 fix 行为不变。README 同步说明，补丁版本发布为 0.3.21。

## Verification

- `tests/workspace/venv/bin/python -B -m unittest discover -s tests -p 'test_fix*.py'`：21 项通过，覆盖大量旧 Note 汇总、迁移后提醒消失、检查只读性以及迁移兼容性。
- `tests/workspace/venv/bin/python -B -m unittest discover -s tests -p 'test_welcome.py'`：23 项通过，覆盖欢迎语 check 和 hook 输出。
- `git diff --check`：通过。
- 新增回归断言在修改前失败，修改后通过；最初使用系统 Python 时因缺少 json5 失败，切换仓库现有测试虚拟环境后完成验证。

## 文件改动

```
     2  README.md
     7  scripts/lib/fix.py
    21  tests/test_fix_formats.py
```
