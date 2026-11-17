#!/usr/bin/env python3
"""Print real isolated update/risk output; do not notify or change a real installation."""
import json
import sys

from support import ROOT
from test_update_status import SharedUpdateIntegration


def main():
    case = SharedUpdateIntegration(methodName='test_real_upgrade_has_shared_log_and_clean_installed_git')
    try:
        case.setUp()
        def show(title, result):
            print(f'\n=== {title} ===')
            text = (result.stdout + result.stderr).replace(str(case.base), '<隔离目录>')
            print(text.rstrip())
            print(f'退出码：{result.returncode}')
        show('真实本地 Git 升级（不联网，不发系统通知）',
             case.run_command([sys.executable, case.entry, 'update']))
        value = json.loads((case.home / 'update-status.json').read_text())
        print('共享状态摘要：' + json.dumps({key: value[key] for key in (
            'schema_version', 'task_id', 'stage', 'from_version', 'to_version', 'result')}, ensure_ascii=False))
        print(f"完成结果展示窗口：{value['expires_at'] - value['finished_at']:.0f} 秒")
        show('CLI 状态查询', case.run_command([sys.executable, case.entry, 'update', '--status']))
        (case.source / 'publish/version').write_text('0.5.0\n')
        case.git('add', 'publish/version', cwd=case.source)
        case.git('commit', '-qm', '[update] next fixture', cwd=case.source)
        (case.base / 'remote-version').write_text('0.5.0')
        (case.home / 'app/README.md').write_text('UNEXPECTED MANUAL EDIT\n')
        show('异常改动阻止覆盖', case.run_command([sys.executable, case.entry, 'update'], success=False))
        show('被暂停任务的共享状态', case.run_command([sys.executable, case.entry, 'update', '--status']))
        print('\n=== Claude 插件 API 替身输出（非真实 UI 验收） ===')
        print(case.run_command(['node', ROOT / 'tests/test_claude_plugin.mjs']).stdout.rstrip())
    finally:
        case.doCleanups()


if __name__ == '__main__':
    main()
