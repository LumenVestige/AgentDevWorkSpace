"""Validate the external Claude plugin using a documented-API test double."""
import json
import shutil
import unittest

from support import ROOT, Sandbox


class ClaudePlugin(Sandbox):
    def test_manifest_and_hook_module_paths(self):
        root = ROOT / 'plugins/claude-update'
        manifest = json.loads((root / '.claude-plugin/plugin.json').read_text())
        hooks = json.loads((root / 'hooks/hooks.json').read_text())
        self.assertEqual(manifest['name'], 'agentdev-update')
        self.assertEqual(hooks['modules'], ['./register.js'])
        self.assertTrue((root / 'hooks' / hooks['modules'][0]).is_file())

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for Claude Mod contract tests')
    def test_background_polling_expiry_and_session_cleanup(self):
        result = self.run_command(['node', ROOT / 'tests/test_claude_plugin.mjs'])
        self.assertIn('assertions passed', result.stdout)
        self.assertIn('完成 10 秒后：undefined', result.stdout)
