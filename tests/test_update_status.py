"""Shared update tasks, atomic state, notification routing and concurrent upgrades."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import patch

from support import ROOT, Sandbox, copy_source
from lib import update_status as status
from lib.repository import stage_repository, installation_risk
from command import update as command


class UpdateState(Sandbox):
    def setUp(self):
        super().setUp()
        self.home = self.base / 'installation'
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, self.env).start()

    def task(self, **kwargs):
        return status.UpdateTask(self.home, '0.3.0', '0.4.0', **kwargs)

    def test_complete_schema_and_completion_expiry(self):
        with contextlib.redirect_stdout(io.StringIO()):
            task = self.task()
            task.stage('downloading')
            task.finish('success')
        value = status.read_status(self.home)
        for key in ('task_id', 'pid', 'stage', 'started_at', 'finished_at', 'from_version',
                    'to_version', 'result', 'log_path', 'expires_at'):
            self.assertIn(key, value)
        self.assertEqual(value['result'], 'success')
        self.assertAlmostEqual(value['expires_at'] - value['finished_at'], 10)
        self.assertGreaterEqual(value['finished_at'], value['started_at'])
        self.assertTrue(Path(value['log_path']).is_file())
        self.assertNotIn('/app/', value['log_path'])
        self.assertIn('下载源码', Path(value['log_path']).read_text())

    def test_atomic_replace_does_not_expose_partial_json(self):
        path = self.home / 'update-status.json'
        status.atomic_json(path, {'sequence': 0, 'payload': 'x' * 10000})
        errors = []
        stop = threading.Event()
        def reader():
            while not stop.is_set():
                try:
                    value = json.loads(path.read_text())
                    self.assertEqual(len(value['payload']), 10000)
                except Exception as error:
                    errors.append(error)
        thread = threading.Thread(target=reader)
        thread.start()
        try:
            for i in range(30):
                status.atomic_json(path, {'sequence': i, 'payload': 'x' * 10000})
        finally:
            stop.set()
            thread.join()
        self.assertFalse(errors)
        self.assertEqual(list(self.home.glob('.update-status.json-*')), [])

    def test_failed_atomic_replace_keeps_previous_and_removes_temp(self):
        path = self.home / 'update-status.json'
        status.atomic_json(path, {'old': True})
        with patch.object(status.os, 'replace', side_effect=OSError('fixture')):
            with self.assertRaises(OSError):
                status.atomic_json(path, {'new': True})
        self.assertEqual(json.loads(path.read_text()), {'old': True})
        self.assertEqual(list(self.home.glob('.update-status.json-*')), [])

    def test_missing_invalid_and_unknown_schema_are_ignored(self):
        self.assertIsNone(status.read_status(self.home))
        self.home.mkdir()
        for text in ('{', '[]', '{"schema_version":2}', '{"schema_version":1,"result":"invalid"}',
                     '{"schema_version":1,"result":[]}', '{"schema_version":1,"result":"success"}'):
            (self.home / 'update-status.json').write_text(text)
            self.assertIsNone(status.read_status(self.home))

    def test_only_success_notifies_once_after_completion_for_all_clients(self):
        with patch.dict(os.environ, {'AGENTDEV_NOTIFY': 'system'}), \
                patch.object(status, 'desktop_notify', return_value=True) as notify:
            for client in ('claude', 'codex', 'cli'):
                with self.subTest(client=client), patch.dict(os.environ, {'AGENTDEV_CLIENT': client}):
                    notify.reset_mock()
                    task = self.task()
                    task.stage('downloading')
                    task.stage('dependencies')
                    notify.assert_not_called()
                    task.finish('success')
                    task.finish('success')
                    notify.assert_called_once()
                    self.assertIn('更新成功', notify.call_args.args[1])
                    self.assertEqual(status.read_status(self.home)['result'], 'success')

    def test_failed_and_blocked_tasks_do_not_notify(self):
        with patch.dict(os.environ, {'AGENTDEV_NOTIFY': 'system'}), \
                patch.object(status, 'desktop_notify') as notify:
            for result in ('failed', 'blocked'):
                with self.subTest(result=result):
                    task = self.task()
                    task.finish(result, '下载失败或异常改动')
                    task.finish('success')
                    self.assertEqual(status.read_status(self.home)['result'], result)
                    self.assertIn('下载失败或异常改动', status.read_status(self.home)['error'])
            notify.assert_not_called()

    def test_command_failures_do_not_leak_credential_arguments_to_state_or_toast(self):
        with patch.dict(os.environ, {'AGENTDEV_NOTIFY': 'system'}), \
                patch.object(status, 'desktop_notify') as notify:
            task = self.task()
            task.stage('downloading')
            task.finish('failed', subprocess.CalledProcessError(128, ['git', 'clone', 'https://secret-token@example.invalid/repo']))
        self.assertNotIn('secret-token', task.path.read_text())
        self.assertNotIn('secret-token', str(notify.call_args))
        notify.assert_not_called()
        self.assertIn('退出码 128', status.read_status(self.home)['error'])

    def test_auto_routes_all_clients_to_system_and_preserves_overrides(self):
        with patch.dict(os.environ, {}, clear=True):
            for env in ({'AGENTDEV_CLIENT':'claude'}, {'AGENTDEV_CLIENT':'codex', 'CLAUDECODE':'1'},
                        {'CLAUDECODE':'1'}, {}):
                with patch.dict(os.environ, env, clear=True):
                    self.assertEqual(status.notification_mode(), 'system')
            self.assertEqual(status.notification_mode('none'), 'none')
            with patch.dict(os.environ, {'AGENTDEV_NOTIFY': 'none'}):
                self.assertEqual(status.notification_mode(), 'none')
                self.assertEqual(status.notification_mode('system'), 'system')
            with patch.dict(os.environ, {'AGENTDEV_NOTIFY': 'invalid'}):
                self.assertEqual(status.notification_mode(), 'system')

    def test_disabled_notifications_remain_silent_on_success(self):
        with patch.object(status, 'desktop_notify') as notify:
            task = self.task(notify='none')
            task.finish('success')
            notify.assert_not_called()

    def test_mac_uses_fixed_script_and_argv_not_string_interpolation(self):
        text = '失败 " & do shell script "not-a-command'
        with patch.dict(os.environ, {}, clear=True), patch.object(status.sys, 'platform', 'darwin'), \
                patch.object(status.shutil, 'which', return_value='/fixture/osascript'), \
                patch.object(status.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertTrue(status.desktop_notify('AgentDevWorkSpace', text))
        args = run.call_args.args[0]
        self.assertEqual(args[-1], text)
        self.assertNotIn(text, args[2])
        self.assertEqual(run.call_args.kwargs['timeout'], 5)
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_linux_requests_ten_seconds_and_passes_arguments(self):
        with patch.dict(os.environ, {'WAYLAND_DISPLAY':'fixture'}, clear=True), \
                patch.object(status.sys, 'platform', 'linux'), \
                patch.object(status.shutil, 'which', return_value='/fixture/notify-send'), \
                patch.object(status.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertTrue(status.desktop_notify('AgentDevWorkSpace', '更新成功'))
            self.assertIn('--expire-time=10000', run.call_args.args[0])
            self.assertEqual(run.call_args.args[0][-2:], ['AgentDevWorkSpace', '更新成功'])

    def test_missing_tools_headless_ssh_and_failures_do_not_raise(self):
        for env in ({}, {'DISPLAY':'fixture', 'SSH_CONNECTION':'ssh'}):
            with patch.dict(os.environ, env, clear=True), patch.object(status.sys, 'platform', 'linux'), \
                    patch.object(status.shutil, 'which', return_value=None), \
                    patch.object(status.subprocess, 'run') as run:
                self.assertFalse(status.desktop_notify('title', 'body'))
                run.assert_not_called()
        for error in (OSError('missing'), subprocess.TimeoutExpired('notify-send', 5)):
            with patch.dict(os.environ, {'DISPLAY':'fixture'}, clear=True), \
                    patch.object(status.sys, 'platform', 'linux'), \
                    patch.object(status.shutil, 'which', return_value='fixture'), \
                    patch.object(status.subprocess, 'run', side_effect=error):
                self.assertFalse(status.desktop_notify('title', 'body'))

    def test_task_subprocess_output_is_saved_in_log(self):
        task = self.task()
        task.run([sys.executable, '-c', 'import sys; print("fixture stdout"); print("fixture stderr",file=sys.stderr)'])
        log = Path(task.value['log_path']).read_text()
        self.assertIn('fixture stdout', log)
        self.assertIn('fixture stderr', log)

    def test_status_command_is_read_only_and_check_does_not_write_task(self):
        task = self.task()
        task.finish('blocked', '异常改动')
        before = task.path.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            status.show_status(self.home)
        self.assertIn('更新已暂停', out.getvalue())
        self.assertIn(task.value['task_id'], out.getvalue())
        self.assertEqual(task.path.read_bytes(), before)
        with patch.object(command, 'installed', return_value=self.home / 'app'), \
                patch.object(command, 'warn_installation', return_value=False), \
                patch.object(command, 'read_version', return_value=(0,3,0)), \
                patch.dict(os.environ, {'AGENTDEV_NOTIFY': 'system'}), \
                patch.object(status, 'desktop_notify') as notify:
            command.update(self.home, check_only=True, remote=(0,4,0))
            notify.assert_not_called()
        self.assertEqual(task.path.read_bytes(), before)

    def test_watch_ends_at_writer_expiry_without_deleting_state(self):
        task = self.task()
        task.finish('success')
        value = status.read_status(self.home)
        before = task.path.read_bytes()
        with patch.object(status.time, 'time', return_value=value['expires_at']), \
                patch.object(status.time, 'sleep') as sleep, contextlib.redirect_stdout(io.StringIO()) as out:
            status.show_status(self.home, watch=True)
        sleep.assert_not_called()
        self.assertIn('更新成功', out.getvalue())
        self.assertEqual(task.path.read_bytes(), before)

    def test_existing_success_is_not_overwritten_by_noop(self):
        task = self.task()
        task.finish('success')
        before = task.path.read_bytes()
        with patch.object(command, 'installed', return_value=self.home / 'app'), \
                patch.object(command, 'warn_installation', return_value=False), \
                patch.object(command, 'read_version', return_value=(0,4,0)), \
                patch.object(command, 'refresh') as refresh, \
                patch.dict(os.environ, {'AGENTDEV_NOTIFY': 'system'}), \
                patch.object(status, 'desktop_notify') as notify:
            command.update(self.home, remote=(0,4,0))
            notify.assert_not_called()
        refresh.assert_called_once()
        self.assertEqual(task.path.read_bytes(), before)

    def test_version_download_and_install_failures_are_terminal(self):
        for name in ('version', 'download', 'install'):
            with self.subTest(name=name), \
                    patch.object(command, 'installed', return_value=self.home / 'app'), \
                    patch.object(command, 'warn_installation', return_value=False), \
                    patch.object(command, 'read_version', return_value=(0,3,0)), \
                    patch.object(command, 'remote_version', side_effect=RuntimeError('fixture version')) if name == 'version' else contextlib.nullcontext(), \
                    patch.object(command, 'metadata', return_value={'repository':'fixture'}), \
                    patch.object(status.UpdateTask, 'run', side_effect=RuntimeError('fixture download') if name == 'download' else None), \
                    patch.object(command, 'install', side_effect=RuntimeError('fixture install')):
                # A checkout must claim the remote version before installer failure.
                if name == 'install':
                    command.read_version.side_effect = [(0,3,0), (0,4,0)]
                with self.assertRaises(RuntimeError):
                    command.update(self.home, remote=None if name == 'version' else (0,4,0))
                self.assertEqual(status.read_status(self.home)['result'], 'failed')
                self.assertIn('fixture', status.read_status(self.home)['error'])

    def test_blocked_task_does_not_announce_download_or_install(self):
        with patch.object(command, 'installed', return_value=self.home / 'app'), \
                patch.object(command, 'warn_installation', return_value=True), \
                patch.object(command, 'read_version', return_value=(0,3,0)), \
                patch.object(command, 'install') as install:
            with self.assertRaisesRegex(RuntimeError, '暂停'):
                command.update(self.home, remote=(0,4,0))
        install.assert_not_called()
        self.assertEqual(status.read_status(self.home)['result'], 'blocked')

    def test_kernel_lock_releases_after_process_exit_and_timeout_preserves_state(self):
        self.home.mkdir()
        code = ('from pathlib import Path; from lib.update_status import update_lock; import time; '
                f'h=Path({str(self.home)!r}); '
                '\nwith update_lock(h):\n print("locked",flush=True); time.sleep(60)')
        process = subprocess.Popen([sys.executable, '-B', '-c', code], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, cwd=ROOT,
                                   env={**self.env, 'PYTHONPATH':str(ROOT / 'scripts')})
        try:
            self.assertEqual(process.stdout.readline().strip(), 'locked')
            with self.assertRaisesRegex(RuntimeError, '等待现有更新超时'):
                with status.update_lock(self.home, timeout=0.1):
                    self.fail('must not acquire')
            self.assertFalse((self.home / 'update-status.json').exists())
        finally:
            process.terminate()
            process.communicate(timeout=10)
        with status.update_lock(self.home, timeout=0):
            pass


class SharedUpdateIntegration(Sandbox):
    def setUp(self):
        super().setUp()
        self.source = copy_source(self.base / 'source')
        self.git('init', '-q', '-b', 'master', self.source)
        self.git('add', '.', cwd=self.source)
        self.git('commit', '-qm', '[update] original fixture', cwd=self.source)
        self.git('remote', 'add', 'origin', self.source, cwd=self.source)
        self.home = Path(self.env['AGENTDEV_HOME'])
        self.run_command(['sh', self.source / 'setup.sh', '--no-path'])
        (self.source / 'publish/version').write_text('0.4.0\n')
        self.git('add', 'publish/version', cwd=self.source)
        self.git('commit', '-qm', '[update] upgraded fixture', cwd=self.source)
        (self.base / 'remote-version').write_text('0.4.0')
        self.entry = ROOT / 'scripts/command/app.py'

    def test_real_upgrade_has_shared_log_and_clean_installed_git(self):
        project = self.make_project(git=False)
        result = self.run_command([sys.executable, self.entry, 'update', '--project', project])
        value = status.read_status(self.home)
        self.assertEqual(value['result'], 'success')
        self.assertEqual(value['from_version'], '0.3.0')
        self.assertEqual(value['to_version'], '0.4.0')
        self.assertIn('下载源码', result.stdout)
        self.assertIn('安装依赖', result.stdout)
        self.assertIn('刷新工作区', result.stdout)
        self.assertIn('Requirement', Path(value['log_path']).read_text())
        self.assertFalse((self.home / 'app/plugins/claude-update').exists())
        self.assertEqual(installation_risk(self.home), ('', False))
        query = self.run_command([sys.executable, self.entry, 'update', '--status'])
        self.assertIn(value['task_id'], query.stdout)
        self.env['PATH'] = ''
        without_git = self.run_command([sys.executable, self.entry, 'update', '--status'])
        self.assertIn(value['task_id'], without_git.stdout)

    def test_activation_failure_rolls_back_app_but_keeps_failed_task(self):
        with patch.dict(os.environ, self.env), \
                patch('lib.installer.write_launchers', side_effect=RuntimeError('fixture activation failure')):
            with self.assertRaisesRegex(RuntimeError, 'activation failure'):
                command.update(self.home, remote=(0,4,0), notify='none')
        value = status.read_status(self.home)
        self.assertEqual(value['result'], 'failed')
        self.assertEqual(value['failed_stage'], 'activating')
        self.assertEqual((self.home / 'app/publish/version').read_text().strip(), '0.3.0')
        self.assertFalse((self.home / 'app.previous').exists())
        self.assertTrue(Path(value['log_path']).is_file())
        self.assertEqual(installation_risk(self.home), ('', False))

    def test_concurrent_projects_reuse_task_and_refresh_both(self):
        # Hold the outer lock until both processes start; neither can touch status.
        projects = []
        for name in ('project-one', 'project-two'):
            root = self.base / name
            (root / 'agent-workspace').mkdir(parents=True)
            projects.append(root)
        notifications = self.base / 'notifications.log'
        fakebin = self.base / 'fake-notifications'
        fakebin.mkdir()
        for name in ('notify-send', 'osascript'):
            script = fakebin / name
            # macOS passes a multiline AppleScript argument; count invocations, not argument lines.
            script.write_text("#!/bin/sh\nprintf 'notification\\n' >> \"$AGENTDEV_TEST_NOTIFICATIONS\"\n")
            script.chmod(0o755)
        self.env.update(AGENTDEV_NOTIFY='system', DISPLAY='fixture',
                        PATH=str(fakebin) + os.pathsep + self.env.get('PATH', ''),
                        SSH_CONNECTION='', SSH_TTY='', AGENTDEV_TEST_NOTIFICATIONS=str(notifications))
        processes = []
        try:
            with status.update_lock(self.home):
                for project in projects:
                    processes.append(subprocess.Popen([sys.executable, '-B', str(self.entry), 'update', '--project', str(project)],
                                                      cwd=self.base, env=self.env, stdout=subprocess.PIPE,
                                                      stderr=subprocess.PIPE, text=True))
                time.sleep(0.5)
                self.assertFalse((self.home / 'update-status.json').exists())
            outputs = []
            for process in processes:
                out, err = process.communicate(timeout=120)
                self.assertEqual(process.returncode, 0, out + err)
                outputs.append(out)
            self.assertEqual(sum('已更新到 0.4.0' in out for out in outputs), 1)
            self.assertEqual(len(list((self.home / 'logs').glob('update-*.log'))), 1)
            self.assertEqual(len(notifications.read_text().splitlines()), 1)
            for project in projects:
                self.assertTrue((project / 'agent-workspace/.agent/env/agentskill-path').is_file())
            self.assertEqual(status.read_status(self.home)['result'], 'success')
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_auto_hook_writes_same_installation_state(self):
        project = self.make_project(git=False)
        self.run_command([sys.executable, self.entry, 'init', project])
        updater = project / 'agent-workspace/skills/common/notes/update.py'
        self.run_command([sys.executable, updater, '--run', '--remote', '0.4.0'], cwd=project)
        self.assertEqual(status.read_status(self.home)['result'], 'success')
        self.assertFalse((project / 'agent-workspace/.agent/env/update-status.json').exists())
        for directory, client in (('.claude', 'claude'), ('.codex', 'codex')):
            file = 'settings.local.json' if client == 'claude' else 'hooks.json'
            self.assertIn('--client ' + client, (project / directory / file).read_text())
