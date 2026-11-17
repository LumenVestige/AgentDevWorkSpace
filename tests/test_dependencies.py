"""setup 不安装 skill 依赖，init 通过 deps.sh 安装；仅使用本地隔离目录。"""
from pathlib import Path
import os
import subprocess
from unittest.mock import patch

from support import ROOT, Sandbox, copy_source, snapshot
from lib import workspace


class DependencyCommands(Sandbox):
    def setUp(self):
        super().setUp()
        self.source = copy_source(self.base / 'source')
        self.home = Path(self.env['AGENTDEV_HOME'])
        self.python = self.home / 'venv/bin/python'
        self.project = self.base / 'project with spaces'
        self.project.mkdir()
        self.log = self.base / 'deps.log'
        self.env['AGENTDEV_DEPS_TEST_LOG'] = str(self.log)
        # setup 的源码中植入只属于本用例的观测点，验证实际调用的确是 deps.sh。
        deps = self.source / 'scripts/lib/deps.sh'
        deps.write_text(deps.read_text().replace(
            'set -e\n', 'set -e\nprintf "%s\\n" "$1" >> "$AGENTDEV_DEPS_TEST_LOG"\n', 1))

    def setup(self, **kwargs):
        return self.run_command(['sh', self.source / 'setup.sh', '--no-path'], **kwargs)

    def cli(self, *args, **kwargs):
        return self.run_command([self.python, '-B', self.home / 'app/scripts/command/app.py', *args],
                                cwd=self.project, **kwargs)

    def has_json5(self):
        return self.run_command([self.python, '-c',
                                'import importlib.util; print(importlib.util.find_spec("json5") is not None)']).stdout.strip() == 'True'

    def test_setup_succeeds_without_dependency_wheels_or_deps_invocation(self):
        self.env['PIP_FIND_LINKS'] = str(self.base / 'no-wheels')
        self.setup()
        self.assertFalse(self.has_json5())
        self.assertFalse(self.log.exists())
        self.assertIn('init', self.cli('help').stdout)
        self.assertFalse((self.project / 'agent-workspace').exists())

    def test_init_runs_deps_then_initializes_and_check_remains_readonly(self):
        self.setup()
        self.assertFalse(self.has_json5())
        self.assertFalse(self.log.exists())
        result = self.cli('init')
        self.assertIn('检查通过', result.stdout)
        self.assertTrue(self.has_json5())
        self.assertEqual(self.log.read_text().splitlines(), [str(self.python)])
        pointer = self.project / 'agent-workspace/.agent/env/python-path'
        self.assertEqual(pointer.read_text().strip(), str(self.python))
        before = snapshot(self.project)
        self.cli('check')
        self.cli('fix')
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(self.log.read_text().splitlines(), [str(self.python)])
        self.cli('--i')
        self.assertEqual(self.log.read_text().splitlines(), [str(self.python)] * 2)
        self.setup()
        self.assertTrue(self.has_json5())
        self.assertEqual(self.log.read_text().splitlines(), [str(self.python)] * 2)
        before = snapshot(self.project)
        (self.home / 'app/scripts/lib/deps.sh').write_text('#!/bin/sh\necho "依赖安装失败" >&2\nexit 9\n')
        self.cli('init', success=False)
        self.assertEqual(snapshot(self.project), before)

    def test_failed_deps_do_not_initialize_workspace(self):
        self.setup()
        self.env['PIP_FIND_LINKS'] = str(self.base / 'no-wheels')
        result = self.cli('init', success=False)
        self.assertIn('依赖安装失败', result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), [str(self.python)])
        self.assertFalse((self.project / 'agent-workspace').exists())

    def test_invalid_project_is_rejected_before_installing_dependencies(self):
        self.setup()
        self.cli('init', self.base / 'missing', success=False)
        self.cli('init', self.home, success=False)
        self.assertFalse(self.log.exists())
        self.assertFalse(self.has_json5())


class DependencyFailures(Sandbox):
    def test_dependency_failure_stops_before_config_and_workspace_writes(self):
        project = self.base / 'project'
        project.mkdir()
        for error in (subprocess.CalledProcessError(1, ['deps.sh']),
                      subprocess.TimeoutExpired(['deps.sh'], 120)):
            with self.subTest(error=type(error).__name__), \
                    patch.dict(os.environ, self.env, clear=True), \
                    patch.object(workspace, 'install_dependencies', side_effect=error) as deps, \
                    patch.object(workspace, 'runtime_errors', return_value=[]), \
                    patch.object(workspace, 'project_settings') as config:
                with self.assertRaises(type(error)):
                    workspace.initialize(ROOT, self.base / 'installation', project)
                deps.assert_called_once()
                config.assert_not_called()
                self.assertFalse((project / 'agent-workspace').exists())

    def test_unusable_shared_runtime_does_not_attempt_install(self):
        with patch.object(workspace, 'runtime_errors', return_value=['pip 不可用']) as check, \
                patch.object(workspace.subprocess, 'run') as run:
            home = self.base / 'installation'
            with self.assertRaisesRegex(RuntimeError, 'pip 不可用'):
                workspace.install_dependencies(ROOT, home)
            check.assert_called_once_with(home / 'venv/bin/python', ROOT, check_dependencies=False)
            run.assert_not_called()
