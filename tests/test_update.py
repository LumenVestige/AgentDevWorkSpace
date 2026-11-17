"""Welcome/version integration and controlled background-update state machines."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import types
from unittest.mock import Mock, patch

from support import ROOT, Sandbox, copy_source, snapshot


class WelcomeVersions(Sandbox):
    def setUp(self):
        super().setUp()
        self.root = self.make_project(git=False)
        self.source = copy_source(self.base / "source", "0.3.0")
        (self.root / "agent-workspace/.agent/env/agentskill-path").write_text(str(self.source))
        self.remote = self.base / "remote-version"
        self.config = self.root / "agent-workspace/config/config.json5"
        self.config.write_text(json.dumps({"personal":"Test Owner", "auto_update":False,
                                           "update_url":self.remote.as_uri()}))

    def test_equal_older_and_newer_remote_versions(self):
        for remote, expected in (("0.3.0", "本地 0.3.0，远端 0.3.0（已是最新）"),
                                 ("0.2.99", "已是最新"),
                                 ("0.3.1", "发现远端版本更新，由本地0.3.0版本更新到0.3.1版本"),
                                 ("0.10.0", "由本地0.3.0版本更新到0.10.0版本")):
            with self.subTest(remote=remote):
                self.remote.write_text(remote)
                text = self.skill(self.root, "notes/update.py", "--welcome").stdout
                self.assertIn(expected, text)
                if remote in ("0.3.1", "0.10.0"):
                    self.assertIn("自动更新已关闭", text)
        self.assertFalse((self.root / "agent-workspace/.agent/env/update.lock").exists())

    def test_missing_or_malformed_remote_is_reported_without_traceback(self):
        for content in (None, "NaN"):
            with self.subTest(content=content):
                if content is not None:
                    self.remote.write_text(content)
                result = self.skill(self.root, "notes/update.py", "--welcome")
                self.assertIn("远端 未知", result.stdout)
                self.assertIn("获取远端版本失败", result.stdout)
                self.assertNotIn("Traceback", result.stderr)

    def test_legacy_local_is_normalized(self):
        (self.source / "publish/version").write_text("0.3")
        self.remote.write_text("0.3")
        self.assertIn("本地 0.3.0，远端 0.3.0", self.skill(self.root, "notes/update.py", "--welcome").stdout)

    def test_noarg_old_hook_is_noop(self):
        before = snapshot(self.root)
        self.assertEqual(self.skill(self.root, "notes/update.py").stdout, "")
        self.assertEqual(snapshot(self.root), before)


class BackgroundUpdate(Sandbox):
    def setUp(self):
        super().setUp()
        self.root = self.base / "project"
        self.root.mkdir()
        self.state = self.root / "env"
        self.state.mkdir()
        self.source = copy_source(self.base / "source")
        common = types.ModuleType("common")
        common.ENV = self.state
        common.project_root = lambda: self.root
        common.python_path = lambda root: Path(sys.executable)
        common.skill_dir = lambda: self.source
        common.update_stamp_file = lambda root: self.state / "last-update"
        common.load_config = lambda root: {"auto_update":True,"auto_update_interval_hours":24}
        spec = importlib.util.spec_from_file_location("test_background_updater", ROOT / "skills/notes/update.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"common":common}):
            spec.loader.exec_module(self.module)
        self.config = common.load_config(self.root)

    def test_due_missing_corrupt_expired_future_and_recent_stamps(self):
        stamp = self.state / "last-update"
        self.assertTrue(self.module.due(self.root, self.config))
        for value, expected in (("invalid",True), ("0",True), (str(time.time()+3600),True),
                                (str(time.time()),False)):
            with self.subTest(value=value):
                stamp.write_text(value)
                self.assertEqual(self.module.due(self.root, self.config), expected)

    def test_disabled_and_recent_checks_do_not_spawn(self):
        with patch.object(self.module, "spawn") as spawn:
            self.assertFalse(self.module.trigger(self.root, {**self.config,"auto_update":False}, now=True))
            (self.state / "last-update").write_text(str(time.time()))
            self.assertFalse(self.module.trigger(self.root, self.config))
        spawn.assert_not_called()

    def test_supplied_remote_spawns_once_without_second_fetch(self):
        with patch.object(self.module, "spawn") as spawn, patch.object(self.module, "fetch_remote") as fetch:
            self.assertTrue(self.module.trigger(self.root, self.config, now=True, remote=(0, 3, 10)))
            spawn.assert_called_once_with("--run", "--remote", "0.3.10")
            fetch.assert_not_called()
            self.assertTrue((self.state / "last-update").is_file())

    def test_spawn_failure_is_logged_without_breaking_hook(self):
        with patch.object(self.module, "spawn", side_effect=OSError("fixture cannot spawn")):
            self.assertFalse(self.module.trigger(self.root, self.config, now=True))
        self.assertIn("fixture cannot spawn", self.module.LOG.read_text())

    def test_live_lock_prevents_duplicate_updates(self):
        self.module.LOCK.write_text(str(os.getpid()))
        self.assertFalse(self.module.acquire())
        with patch.object(self.module, "spawn") as spawn:
            self.assertFalse(self.module.trigger(self.root, self.config, now=True))
            spawn.assert_not_called()

    def test_corrupt_and_dead_locks_can_be_reclaimed(self):
        for text in ("invalid", "999999999"):
            with self.subTest(text=text):
                self.module.LOCK.write_text(text)
                self.assertTrue(self.module.acquire())
                self.assertEqual(self.module.LOCK.read_text().strip(), str(os.getpid()))
                self.module.release()
                self.assertFalse(self.module.LOCK.exists())

    def test_release_never_deletes_another_owners_lock(self):
        self.module.LOCK.write_text("999999999")
        self.module.release()
        self.assertEqual(self.module.LOCK.read_text(), "999999999")

    def test_failed_update_keeps_ready_and_success_clears_it(self):
        (self.source / ".agentdev-app").touch()
        with patch.object(self.module.subprocess, "run", return_value=Mock(returncode=1)) as run:
            self.module.check(self.root, self.config, remote=(0, 3, 10))
            self.assertEqual(self.module.READY.read_text().strip(), "0.3.10")
            args = run.call_args.args[0]
            self.assertIn("--project", args)
            self.assertEqual(args[-1], "0.3.10")
            self.assertEqual(run.call_args.kwargs["env"]["AGENTDEV_HOME"], str(self.source.parent))
        with patch.object(self.module.subprocess, "run", return_value=Mock(returncode=0)):
            self.module.check(self.root, self.config, remote=(0, 3, 10))
        self.assertFalse(self.module.READY.exists())

    def test_remote_lookup_failure_is_delegated_to_shared_cli_task(self):
        cfg = {**self.config, 'update_url': (self.base / 'missing-version').as_uri()}
        with patch.object(self.module, 'fetch_remote') as fetch, \
                patch.object(self.module.subprocess, 'run', return_value=Mock(returncode=1)) as run:
            self.module.check(self.root, cfg)
        fetch.assert_not_called()
        self.assertNotIn('--remote', run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs['env']['AGENTDEV_VERSION_URL'], cfg['update_url'])
        self.assertEqual(self.module.READY.read_text().strip(), 'retry')

    def test_successful_init_retry_clears_ready(self):
        self.module.READY.write_text("0.3.1")
        with patch.object(self.module.subprocess, "run", return_value=Mock(returncode=1)):
            self.module.setup(self.root)
        self.assertTrue(self.module.READY.exists())
        with patch.object(self.module.subprocess, "run", return_value=Mock(returncode=0)):
            self.module.setup(self.root)
        self.assertFalse(self.module.READY.exists())

    def test_main_retries_ready_before_check_and_always_releases_lock(self):
        self.module.READY.write_text("0.3.1")
        calls = []
        with patch.object(sys, "argv", ["update.py", "--run", "--remote", "0.3.1"]), \
             patch.object(self.module.os, "nice"), \
             patch.object(self.module, "setup", side_effect=lambda root: calls.append("init")), \
             patch.object(self.module, "check", side_effect=lambda *args: calls.append("check")):
            self.assertEqual(self.module.main(), 0)
        self.assertEqual(calls, ["init", "check"])
        self.assertFalse(self.module.LOCK.exists())

    def test_invalid_background_arguments_rejected(self):
        for args in (["--run","--remote","NaN"], ["--unknown"], ["--run","unexpected"]):
            with self.subTest(args=args), patch.object(sys,"argv",["update.py",*args]):
                with self.assertRaises(SystemExit):
                    self.module.main()
