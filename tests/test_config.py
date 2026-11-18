"""JSON5 merging, safe personal names, and backwards-compatible migrations."""
import json
import os
from unittest.mock import patch

from support import Sandbox, snapshot
import _workspace_config as config
import _version as version


class Configuration(Sandbox):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, self.env, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.root = self.make_project(git=False)
        self.path = self.root / "agent-workspace/config/config.json5"

    def test_partial_nested_settings_preserve_defaults(self):
        self.path.write_text('{scan:{large_change:{files:7}}, personal:"My Owner"}')
        result = config.load_config(self.root)
        self.assertEqual(result["scan"]["large_change"]["files"], 7)
        self.assertEqual(result["scan"]["large_change"]["lines"], 1000)
        self.assertTrue(result["scan"]["commits"])
        self.assertEqual(config.personal_name(self.root), "my-owner")

    def test_empty_configuration_uses_defaults(self):
        for text in ("", "{}", "// comments\n{}"):
            with self.subTest(text=text):
                self.path.write_text(text)
                self.assertEqual(config.load_config(self.root)["max_notes"], 100)

    def test_non_object_or_malformed_nested_settings_rejected(self):
        for text in ("[]", "null", "5", "{scan:[]}", "{scan:null}",
                     "{scan:{large_change:[]}}", "{unclosed:"):
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaises(ValueError):
                    config.load_config(self.root)

    def test_personal_and_typo_alias_precedence(self):
        for data, expected in (({"personal":"Owner", "peronsal":"Alias"}, "owner"),
                               ({"personal":"", "peronsal":"Alias"}, "alias"),
                               ({"peronsal":"Alias"}, "alias")):
            with self.subTest(data=data):
                self.assertEqual(config.personal_name(self.root, data), expected)

    def test_unsafe_or_reserved_names_rejected(self):
        for name in ("..", ".", "../escape", "a/b", "a\\b", "a\x00b", "skills", "Skills", "workers", "Workers", "config", ".agent", "!!!"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                config.personal_name(self.root, {"personal":name})

    def test_wrong_personal_types_rejected_even_when_alias_unused(self):
        for data in ({"personal":5}, {"personal":None}, {"peronsal":False},
                     {"personal":"Owner", "peronsal":[]}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                config.personal_name(self.root, data)

    def test_non_git_username_does_not_inherit_parent_git_identity(self):
        with patch.object(config.getpass, "getuser", return_value="Computer Owner"):
            self.assertEqual(config.personal_name(self.root, {}), "computer-owner")

    def test_git_root_uses_git_identity_but_nested_dir_uses_username(self):
        self.git("init", "-q", self.root)
        self.assertEqual(config.personal_name(self.root, {}), "fixture-user")
        child = self.root / "child"
        child.mkdir()
        with patch.object(config.getpass, "getuser", return_value="Computer Owner"):
            self.assertEqual(config.personal_name(child, {}), "computer-owner")

    def test_git_without_identity_requires_personal(self):
        self.git("init", "-q", self.root)
        with patch.dict(os.environ, {"GIT_CONFIG_VALUE_0":""}):
            with self.assertRaises(ValueError):
                config.personal_name(self.root, {})
            self.assertEqual(config.personal_name(self.root, {"personal":"Explicit"}), "explicit")

    def test_unicode_and_unix_device_names(self):
        for raw, expected in (("Tony Chen!", "tony-chen"), (" 张三 开发 ", "张三-开发"),
                              ("CON", "con"), ("aux", "aux"), ("O'Reilly & Team", "o-reilly-team")):
            with self.subTest(raw=raw):
                self.assertEqual(config.personal_name(self.root, {"personal":raw}), expected)

    def test_current_config_wins_over_legacy(self):
        legacy = self.path.with_name("notes.json5")
        legacy.write_text('{personal:"Legacy"}')
        self.path.write_text('{personal:"Current"}')
        before = snapshot(self.root)
        self.assertEqual(config.personal_name(self.root), "current")
        self.assertEqual(before, snapshot(self.root))
        self.path.unlink()
        self.assertEqual(config.personal_name(self.root), "legacy")

    def test_migration_only_replaces_effective_url_preserving_comments(self):
        old = "https://raw.githubusercontent.com/LumenVestige/versions/main/AgentDevWorkSpace/version"
        for key in ("update_url", "'update_url'", '"update_url"'):
            with self.subTest(key=key):
                comment = f'// update_url: "{old}" historical comment\n'
                self.path.write_text(comment + "{" + key + ":" + json.dumps(old) + ',personal:"Keep", max_notes:3}\n')
                self.assertTrue(config.migrate_version_source(self.root))
                self.assertTrue(self.path.read_text().startswith(comment))
                self.assertEqual(config.load_config(self.root)["personal"], "Keep")
                self.assertEqual(config.load_config(self.root)["max_notes"], 3)
                self.assertEqual(config.load_config(self.root)["update_url"], version.DEFAULT_URL)
                before = self.path.read_bytes()
                self.assertFalse(config.migrate_version_source(self.root))
                self.assertEqual(self.path.read_bytes(), before)

    def test_custom_version_source_not_rewritten(self):
        self.path.write_text('{update_url:"http://127.0.0.1/version",personal:"Keep"}')
        before = self.path.read_bytes()
        self.assertFalse(config.migrate_version_source(self.root))
        self.assertEqual(config.load_config(self.root)["update_url"], "http://127.0.0.1/version")
        self.assertEqual(self.path.read_bytes(), before)

    def test_config_cli_errors_without_traceback(self):
        self.path.write_text("[]")
        from support import ROOT
        import sys
        result = self.run_command([sys.executable, ROOT / "skills/_workspace_config.py", self.root], success=False)
        self.assertIn("工作区配置错误", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
