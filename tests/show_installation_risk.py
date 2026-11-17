#!/usr/bin/env python3
"""Print real clean/dirty CLI and welcome output, without touching a real install.

Run after preparing test dependencies:
    tests/workspace/venv/bin/python -B tests/show_installation_risk.py
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

from support import ROOT, TMP, copy_source, isolated_env, snapshot
from lib.repository import stage_repository


def show(label, args, env, cwd, expected=0, welcome=False):
    result = subprocess.run(list(map(str, args)), env=env, cwd=cwd,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=20)
    print(f'\n=== {label} ===', flush=True)
    if welcome and result.returncode == 0:
        print(json.loads(result.stdout)['systemMessage'], flush=True)
    else:
        print(result.stdout.rstrip(), flush=True)
    print(f'退出码：{result.returncode}', flush=True)
    if result.returncode != expected:
        raise RuntimeError('演示结果与预期不一致')


def main():
    with tempfile.TemporaryDirectory(prefix='git-risk-demo-', dir=TMP) as temporary:
        base = Path(temporary)
        env = isolated_env(base, PYTHONUNBUFFERED='1')
        home = Path(env['AGENTDEV_HOME'])
        source = copy_source(base / 'source')
        for args in (['init', '-q', '-b', 'master'], ['add', '.'],
                     ['commit', '-qm', '[update] isolated demo fixture']):
            subprocess.run(['git', '-C', str(source), *args], env=env, check=True, capture_output=True)
        home.mkdir()
        app = home / 'app'
        with patch.dict(os.environ, env, clear=True):
            commit = stage_repository(source, app, str(source))
        (app / '.agentdev-app').touch()
        (home / 'install.json').write_text(json.dumps({'repository': str(source), 'commit': commit}))
        remote = base / 'remote-version'
        remote.write_text('0.3.0')
        project = base / 'project'
        workspace = project / 'agent-workspace'
        shutil.copytree(ROOT / 'skills', workspace / 'skills/common')
        state = workspace / '.agent/env'
        state.mkdir(parents=True)
        (state / 'python-path').write_text(sys.executable)
        (state / 'agentskill-path').write_text(str(app))
        config = workspace / 'config/config.json5'
        config.parent.mkdir()
        config.write_text(json.dumps({'personal': 'Demo', 'auto_update': True, 'update_url': remote.as_uri()}))
        cli = [sys.executable, '-B', app / 'scripts/command/app.py']
        welcome = [sys.executable, '-B', workspace / 'skills/common/sdd/welcome.py']
        show('安装目录：git branch', ['git', '-C', app, 'branch'], env, project)
        show('干净安装：agentdev version', [*cli, 'version'], env, project)
        show('干净安装：实际欢迎语', welcome, env, project, welcome=True)
        (app / 'README.md').write_text('MANUAL EDIT\n')
        (app / 'manual.txt').write_text('MANUAL FILE\n')
        remote.write_text('0.4.0')
        before = snapshot(app)
        show('手工改动后：agentdev update --check', [*cli, 'update', '--check'], env, project)
        show('手工改动后：实际欢迎语', welcome, env, project, welcome=True)
        show('手工改动后：agentdev update', [*cli, 'update'], env, project, expected=1)
        if snapshot(app) != before or (state / 'last-update').exists():
            raise RuntimeError('风险检测不应改写安装或启动自动更新')
        print('\n安装文件未被覆盖，未启动后台更新；隔离演示目录随后自动清理。', flush=True)


if __name__ == '__main__':
    main()
