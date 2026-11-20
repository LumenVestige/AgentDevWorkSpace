"""Antigravity 1.5.13 hook contract; local subprocesses, no model requests."""
import json
import subprocess
import sys

from support import ROOT, Sandbox, snapshot
from lib import workspace


class AgyHooks(Sandbox):
    def setUp(self):
        super().setUp()
        self.root = self.make_project()
        self.path = self.root / '.agents/hooks.json'

    def register(self, cfg=None):
        workspace.register_hooks(self.path, cfg or {}, sys.executable, ROOT, self.root)
        return json.loads(self.path.read_text())

    def command(self, event, script):
        cfg = self.register()
        return next(hook['command'] for hook in cfg['agentdev-workspace'][event]
                    if script in hook['command'])

    def invoke(self, event, script, payload=None):
        return subprocess.run(self.command(event, script), shell=True, cwd=self.root, env=self.env,
                              input=json.dumps(payload or {}), capture_output=True, text=True, timeout=15)

    def custom(self, script, source):
        path = self.root / 'agent-workspace/skills/custom' / script
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)

    def test_named_flat_handlers_preserve_user_config_and_are_idempotent(self):
        foreign = {'enabled': True, 'Stop': [{'type': 'command', 'command': 'echo USER'}]}
        cfg = self.register({'user-hook': foreign})
        self.assertEqual(cfg['user-hook'], foreign)
        self.assertNotIn('hooks', cfg)
        for event, scripts in workspace.SCRIPTS.items():
            handlers = cfg['agentdev-workspace'][event]
            self.assertEqual(len(handlers), len(scripts))
            for hook in handlers:
                self.assertNotIn('matcher', hook)
                self.assertNotIn('hooks', hook)
                self.assertIn('--client agy', hook['command'])
                self.assertGreaterEqual(hook['timeout'], 60)
        cfg['agentdev-workspace']['enabled'] = False
        cfg['agentdev-workspace']['Stop'].append({'command': 'echo CUSTOM'})
        result = self.register(cfg)
        self.assertFalse(result['agentdev-workspace']['enabled'])
        self.assertIn({'command': 'echo CUSTOM'}, result['agentdev-workspace']['Stop'])
        self.assertEqual(result, self.register(result))

    def test_welcome_context_uses_public_fields_without_sending_a_user_message(self):
        self.custom('sdd/welcome.py', 'import json, os\n'
                    'assert os.environ["AGENTDEV_CLIENT"] == "agy"\n'
                    'print(json.dumps({"systemMessage":"CUSTOM WELCOME",'
                    '"hookSpecificOutput":{"additionalContext":"SDD COMMANDS"}}))\n')
        result = self.invoke('SessionStart', 'sdd/welcome.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        steps = json.loads(result.stdout)['injectSteps']
        self.assertTrue(steps)
        self.assertFalse(any('userMessage' in step for step in steps))
        message = steps[0]['systemMessage']
        self.assertIn('SDD COMMANDS', message['systemMessage'])
        self.assertIn('CUSTOM WELCOME', message['systemMessage'])
        self.assertNotIn('renderInfo', message)  # internal_only: scrubbed by agy
        self.assertNotIn('metadata', message)

    def test_constraint_context_reuses_current_user_and_custom_common(self):
        specs = self.root / 'agent-workspace/workers/test-owner/specs'
        specs.mkdir(parents=True)
        (specs / 'constraints.md').write_text('PERSONAL RULE')
        self.custom('sdd/constraints.md', 'CUSTOM COMMON RULE')
        result = self.invoke('SessionStart', 'sdd/load_constraints.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        context = data['injectSteps'][0]['systemMessage']
        self.assertIn('PERSONAL RULE', context['systemMessage'])
        self.assertIn('CUSTOM COMMON RULE', context['systemMessage'])
        self.assertNotIn('renderInfo', context)

    def test_real_shared_welcome_includes_check_and_does_not_migrate(self):
        self.custom('notes/update.py', 'print("AgentDevWorkSpace 版本：本地 0.3.24，远端 0.3.24（已是最新）")\n')
        legacy = self.root / 'agent-workspace/legacy-owner/notes'
        legacy.mkdir(parents=True)
        (legacy / '26-11-20-00-00-00-old.md').write_text('OLD NOTE')
        self.register()
        before = snapshot(self.root)
        result = self.invoke('SessionStart', 'sdd/welcome.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        text = json.loads(result.stdout)['injectSteps'][0]['systemMessage']['systemMessage']
        for expected in ('AgentDevWorkSpace', '0.3.24', '创建feature:<名称>', 'agentdev fix'):
            self.assertIn(expected, text)
        self.assertEqual(snapshot(self.root), before)

    def test_stop_block_is_valid_json_with_exit_zero_and_no_repeated_loop(self):
        self.custom('notes/verify.py', 'import json, sys\n'
                    'event=json.load(sys.stdin)\n'
                    'print("WRITE A NOTE", file=sys.stderr)\n'
                    'sys.exit(0 if event.get("stop_hook_active") else 2)\n')
        result = self.invoke('Stop', 'notes/verify.py', {'fullyIdle': True, 'executionNum': 1})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'decision': 'continue', 'reason': 'WRITE A NOTE'})
        result = self.invoke('Stop', 'notes/verify.py', {'fullyIdle': True, 'executionNum': 2})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['decision'], 'allow')

    def test_stop_does_not_run_while_background_work_is_active(self):
        self.custom('notes/verify.py', 'raise RuntimeError("MUST NOT RUN")\n')
        result = self.invoke('Stop', 'notes/verify.py', {'fullyIdle': False})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'decision': 'allow'})
        self.assertNotIn('MUST NOT RUN', result.stderr)

    def test_session_hook_failure_is_visible_in_agy_format(self):
        self.custom('sdd/welcome.py', 'import sys\nprint("BROKEN HOOK",file=sys.stderr)\nsys.exit(1)\n')
        result = self.invoke('SessionStart', 'sdd/welcome.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        step = json.loads(result.stdout)['injectSteps'][0]
        self.assertIn('BROKEN HOOK', step['errorMessage']['userMessage'])

    def test_missing_skill_reports_refresh_instead_of_silent_empty_output(self):
        (self.root / 'agent-workspace/skills/common/sdd/welcome.py').unlink()
        result = self.invoke('SessionStart', 'sdd/welcome.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        text = json.loads(result.stdout)['injectSteps'][0]['errorMessage']['userMessage']
        self.assertIn('agentdev init', text)

    def test_check_reports_missing_agy_hook_read_only(self):
        for file in ('.claude/settings.local.json', '.codex/hooks.json', '.agents/hooks.json'):
            workspace.register_hooks(self.root / file, {}, sys.executable, ROOT, self.root)
        self.path.write_text('{}')
        before = snapshot(self.root)
        result = self.run_command([sys.executable, ROOT / 'scripts/command/app.py', 'check', self.root],
                                  success=False)
        self.assertIn('.agents/hooks.json', result.stdout)
        self.assertEqual(snapshot(self.root), before)

    def test_disabled_group_is_preserved_but_check_does_not_treat_it_as_active(self):
        cfg = self.register()
        cfg['agentdev-workspace']['enabled'] = False
        cfg = self.register(cfg)
        self.assertEqual(workspace.hook_commands(self.path, cfg, 'SessionStart'), [])
