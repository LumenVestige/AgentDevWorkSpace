"""约束必须通过独立 SessionStart 上下文加载，而不是只在文档中提醒。"""
import json
import sys
from support import ROOT, Sandbox


class ConstraintLoading(Sandbox):
    def setUp(self):
        super().setUp()
        self.root = self.make_project()
        self.specs = self.root / 'agent-workspace/test-owner/specs'
        self.specs.mkdir(parents=True)
        (self.specs / 'constraints.md').write_text('P1: PERSONAL RULE\n')

    def load(self, success=True):
        return self.run_command([sys.executable, ROOT / 'scripts/lib/run_skill.py', '--project', self.root,
                                 'sdd/load_constraints.py'], cwd=self.root, success=success)

    def test_personal_and_common_are_added_to_context(self):
        out = json.loads(self.load().stdout)['hookSpecificOutput']
        self.assertEqual(out['hookEventName'], 'SessionStart')
        self.assertIn('P1: PERSONAL RULE', out['additionalContext'])
        self.assertIn('通用开发约束', out['additionalContext'])
        self.assertIn('agent-workspace/test-owner/specs/constraints.md', out['additionalContext'])

    def test_custom_common_priority_and_extra_markdown_and_user_isolation(self):
        custom = self.root / 'agent-workspace/skills/custom/sdd'
        custom.mkdir(parents=True)
        (custom / 'constraints.md').write_text('CUSTOM COMMON')
        (custom / 'welcome.py').write_text('print("CUSTOM WELCOME")')
        (self.specs / 'extra.md').write_text('EXTRA RULE')
        other = self.root / 'agent-workspace/other/specs'
        other.mkdir(parents=True)
        (other / 'constraints.md').write_text('OTHER PRIVATE RULE')
        text = self.load().stdout
        self.assertIn('CUSTOM COMMON', text)
        self.assertIn('EXTRA RULE', text)
        self.assertNotIn('OTHER PRIVATE RULE', text)
        self.assertNotIn('C1', text)

    def test_legacy_personal_and_rereads_modified_constraints(self):
        (self.root / 'agent-workspace/config/config.json5').write_text('{peronsal:"Test Owner"}')
        self.assertIn('PERSONAL RULE', self.load().stdout)
        (self.specs / 'constraints.md').write_text('CHANGED RULE')
        self.assertIn('CHANGED RULE', self.load().stdout)

    def test_invalid_config_or_unreadable_text_fails_visibly(self):
        (self.specs / 'constraints.md').write_bytes(b'\xff')
        self.assertIn('约束加载失败', self.load(success=False).stderr)
        (self.root / 'agent-workspace/config/config.json5').write_text('[]')
        self.assertIn('约束加载失败', self.load(success=False).stderr)

    def test_missing_personal_is_explicit_and_external_symlinks_not_loaded(self):
        (self.specs / 'constraints.md').unlink()
        target = self.base / 'external.md'
        target.write_text('EXTERNAL SECRET')
        (self.specs / 'linked.md').symlink_to(target)
        result = self.load()
        self.assertIn('未找到个人约束', result.stdout)
        self.assertNotIn('EXTERNAL SECRET', result.stdout)

    def test_hooks_registered_for_both_clients_and_all_session_start_causes(self):
        from lib.workspace import register_hooks
        for client in ('.claude/settings.local.json', '.codex/hooks.json'):
            path = self.root / client
            register_hooks(path, {}, sys.executable, ROOT, self.root)
            register_hooks(path, json.loads(path.read_text()), sys.executable, ROOT, self.root)
            events = json.loads(path.read_text())['hooks']['SessionStart']
            loaders = [e for e in events if any('sdd/load_constraints.py' in h['command'] for h in e['hooks'])]
            self.assertEqual(len(loaders), 1)
            self.assertNotIn('matcher', loaders[0])
            self.assertIn('--client ' + ('claude' if client.startswith('.claude') else 'codex'), loaders[0]['hooks'][0]['command'])
