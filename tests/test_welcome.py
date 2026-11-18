"""离线检查共享渲染、hook JSON 和真实伪终端入口，不查询网络。"""
from pathlib import Path
import importlib.util
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from support import ROOT, TMP, isolated_env
spec = importlib.util.spec_from_file_location('renderer', ROOT / 'skills/sdd/render_welcome.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
SOURCE = (ROOT / 'skills/sdd/welcome.md').read_text()
VERSION = 'AgentDevWorkSpace 版本：本地 0.3.0，远端 0.3.0（已是最新）'


class Rendering(unittest.TestCase):
    def test_content(self):
        text = renderer.render_welcome(SOURCE, VERSION)
        for value in ('🚀 AgentDevWorkSpace', '📦 本地 0.3.0', '✅ 已是最新', '创建feature:<名称>',
                      '创建bugfix:<名称>', '创建change:<名称>', '创建research:<名称>',
                      '创建research:虚拟设备性能方案对比', '创建change:升级 json5', '┌', '└'):
            self.assertIn(value, text)
        self.assertNotIn('\x1b', text)
        self.assertNotIn('\n\n\n', text)

    def test_alignment_and_wrapping(self):
        for columns in (40, 60, 80, 120):
            for color in (False, True):
                text = renderer.render_welcome(SOURCE, VERSION, color=color, columns=columns)
                table = [line for line in text.splitlines() if renderer.ANSI.sub('', line).startswith(('│', '┌', '├', '└'))]
                widths = {renderer.display_width(line) for line in table}
                self.assertEqual(len(widths), 1, (columns, widths))
                self.assertLessEqual(max(widths), columns)
        self.assertEqual(renderer.wrap_cell('升级 json5', 7), ['升级', 'json5'])
        self.assertEqual(renderer.display_width('中文✨'), 6)

    def test_color_content_identical(self):
        plain = renderer.render_welcome(SOURCE, VERSION)
        colored = renderer.render_welcome(SOURCE, VERSION, color=True)
        self.assertEqual(renderer.ANSI.sub('', colored), plain)
        self.assertIn('\x1b[1;36m', colored)
        self.assertIn('\x1b[32m已是最新', colored)

    def test_update_and_failure_colors(self):
        update = renderer.render_version('发现远端版本更新，由本地0.3.0版本更新到0.3.1版本', True)
        self.assertIn('\x1b[33m', update)
        self.assertIn('由本地0.3.0版本更新到0.3.1版本', update)
        failed = renderer.render_version('AgentDevWorkSpace 版本：本地 0.3.0，远端 未知（获取远端版本失败）', True)
        self.assertIn('\x1b[31m', failed)

    def test_legacy_custom_text(self):
        text = renderer.render_welcome('自定义欢迎语\n旧格式保持可读', VERSION)
        self.assertIn('自定义欢迎语\n旧格式保持可读', text)


class Entrypoints(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TMP)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ws = self.root / 'agent-workspace'
        self.sdd = self.ws / 'skills/common/sdd'
        self.notes = self.ws / 'skills/common/notes'
        env_dir = self.ws / '.agent/env'
        for path in (self.sdd, self.notes, env_dir / 'venv/bin', self.root / 'publish', self.root / 'bin'):
            path.mkdir(parents=True)
        shutil.copy(ROOT / 'skills/_version.py', self.ws / 'skills/common/_version.py')
        for name in ('welcome.md', 'welcome.py', 'render_welcome.py'):
            shutil.copy(ROOT / 'skills/sdd' / name, self.sdd / name)
        (env_dir / 'venv/bin/python').symlink_to(sys.executable)
        (env_dir / 'agentskill-path').write_text(str(self.root))
        (self.root / 'publish/version').write_text('0.3.0\n')
        self.calls = self.root / 'version-calls'
        (self.notes / 'update.py').write_text(f'from pathlib import Path\nwith Path({str(self.calls)!r}).open("a") as f: f.write("1")\nprint({VERSION!r})\n')
        codex = self.root / 'bin/codex'
        codex.write_text(f'#!{sys.executable}\nimport json, sys\nprint("CODEX_ARGS=" + json.dumps(sys.argv[1:]))\n')
        codex.chmod(0o755)
        self.env = {**isolated_env(self.root), 'PATH': f"{self.root / 'bin'}:{os.environ['PATH']}", 'TERM': 'xterm-256color', 'COLUMNS': '80'}
        self.env.pop('NO_COLOR', None)

    def cli(self, args=(), tty=True, extra=None):
        command = ['sh', str(ROOT / 'scripts/command/codex.sh'), *args]
        env = {**self.env, **(extra or {})}
        if not tty:
            return subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True, check=True, timeout=10).stdout
        master, slave = pty.openpty()
        process = subprocess.Popen(command, cwd=self.root, env=env, stdout=slave, stderr=slave)
        try:
            blocks = []
            deadline = time.monotonic() + 10
            while True:
                if select.select([master], [], [], 0.1)[0]:
                    blocks.append(os.read(master, 65536))
                if process.poll() is not None and not select.select([master], [], [], 0)[0]:
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError('terminal fixture timed out')
            text = b''.join(blocks).decode().replace('\r\n', '\n')
            self.assertEqual(process.returncode, 0, text)
            return text
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(slave)
            os.close(master)

    def hook(self):
        result = subprocess.run([sys.executable, '-B', str(self.sdd / 'welcome.py')], cwd=self.root, env=self.env,
                                capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_color_terminal_and_single_query(self):
        text = self.cli(['--model', 'example-model', '示例消息'])
        self.assertIn('\x1b[1;36m', text)
        self.assertIn('┌', text)
        args = json.loads(text.split('CODEX_ARGS=', 1)[1].strip())
        self.assertEqual(args, ['--no-alt-screen', '--model', 'example-model', '示例消息'])
        self.assertEqual(self.calls.read_text(), '1')

    def test_no_color(self):
        for value in ('1', ''):
            text = self.cli(extra={'NO_COLOR': value})
            self.assertNotIn('\x1b', text)
            self.assertIn('┌', text)

    def test_dumb_terminal(self):
        text = self.cli(extra={'TERM': 'dumb'})
        self.assertNotIn('\x1b', text)
        self.assertIn('创建research:<名称>', text)

    def test_redirected_output_skips_welcome(self):
        text = self.cli(['--model', 'example-model'], tty=False)
        self.assertNotIn('AgentDevWorkSpace', text)
        self.assertEqual(json.loads(text.split('CODEX_ARGS=')[1]), ['--model', 'example-model'])
        self.assertFalse(self.calls.exists())

    def test_noninteractive_commands(self):
        for args in (['--help'], ['exec', 'message'], ['resume']):
            text = self.cli(args)
            self.assertNotIn('AgentDevWorkSpace', text)
            self.assertEqual(json.loads(text.split('CODEX_ARGS=')[1]), args)
        self.assertFalse(self.calls.exists())

    def test_custom_welcome_priority(self):
        custom = self.ws / 'skills/custom/sdd'
        custom.mkdir(parents=True)
        (custom / 'welcome.md').write_text('我的自定义欢迎语\n原有内容')
        text = self.cli()
        self.assertIn('我的自定义欢迎语\n原有内容', text)
        self.assertNotIn('Spec-Driven Development', text)

    def test_custom_renderer_priority(self):
        custom = self.ws / 'skills/custom/sdd'
        custom.mkdir(parents=True)
        (custom / 'render_welcome.py').write_text('print("CUSTOM_RENDERER")\n')
        self.assertIn('CUSTOM_RENDERER', self.cli())

    def test_renderer_missing_fallback(self):
        (self.sdd / 'render_welcome.py').unlink()
        text = self.cli()
        self.assertIn(VERSION, text)
        self.assertIn('| 快捷命令 | 用途 | 示例 |', text)
        self.assertIn('CODEX_ARGS=', text)
        self.assertIn(VERSION, self.hook()['systemMessage'])

    def test_python_missing_fallback(self):
        (self.ws / '.agent/env/venv/bin/python').unlink()
        text = self.cli()
        self.assertIn('AgentDevWorkSpace 版本：本地 0.3.0', text)
        self.assertIn('| 快捷命令 | 用途 | 示例 |', text)

    def test_renderer_failure_fallback(self):
        custom = self.ws / 'skills/custom/sdd'
        custom.mkdir(parents=True)
        (custom / 'render_welcome.py').write_text('raise RuntimeError("fixture")\n')
        text = self.cli()
        self.assertIn('| 快捷命令 | 用途 | 示例 |', text)
        self.assertIn('CODEX_ARGS=', text)
        self.assertNotIn('Traceback', text)

    def test_updater_missing_fallback(self):
        (self.notes / 'update.py').unlink()
        text = self.cli()
        self.assertIn('本地 0.3.0', text)
        self.assertIn('┌', text)

    def test_hook_json_plain_table(self):
        data = self.hook()
        self.assertIn('┌', data['systemMessage'])
        self.assertIn('📦 本地 0.3.0', data['systemMessage'])
        self.assertNotIn('\x1b', data['systemMessage'])
        self.assertEqual(data['hookSpecificOutput']['hookEventName'], 'SessionStart')
        self.assertIn('new_research', data['hookSpecificOutput']['additionalContext'])
        self.assertEqual(self.calls.read_text(), '1')

    def test_hook_runs_check_and_shows_migration_advice_without_fixing(self):
        command = self.root / 'scripts/command/app.py'
        command.parent.mkdir(parents=True)
        command.write_text('import sys\n'
                           f'assert sys.argv[1:] == ["check", {str(self.root)!r}]\n'
                           'print("历史 personal / Note 待迁移，请执行 agentdev fix 进行迁移")\n'
                           'sys.exit(1)\n')
        data = self.hook()
        self.assertIn('agentdev fix', data['systemMessage'])
        self.assertIn('┌', data['systemMessage'])
        self.assertIn('new_research', data['hookSpecificOutput']['additionalContext'])

    def test_hook_displays_successful_environment_check(self):
        command = self.root / 'scripts/command/app.py'
        command.parent.mkdir(parents=True)
        command.write_text('print("✓ 环境检查通过，无需迁移")\n')
        self.assertIn('环境检查通过，无需迁移', self.hook()['systemMessage'])

    def test_custom_updater(self):
        custom = self.ws / 'skills/custom/notes'
        custom.mkdir(parents=True)
        (custom / 'update.py').write_text('print("发现远端版本更新，由本地0.3.0版本更新到0.3.1版本")\n')
        self.assertIn('由本地0.3.0版本更新到0.3.1版本', self.cli())
        self.assertIn('由本地0.3.0版本更新到0.3.1版本', self.hook()['systemMessage'])
        self.assertFalse(self.calls.exists())

    def test_narrow_terminal(self):
        text = self.cli(extra={'COLUMNS': '60'})
        lines = [renderer.ANSI.sub('', line) for line in text.splitlines()]
        table = [line for line in lines if line.startswith(('│', '┌', '├', '└'))]
        self.assertEqual(len({renderer.display_width(line) for line in table}), 1)
        self.assertLessEqual(max(map(renderer.display_width, table)), 60)
        self.assertIn('json5', text)


class WelcomeRenderingTests(unittest.TestCase):
    def test_version_is_immediately_followed_by_sdd_and_table(self):
        text = (ROOT / "skills/sdd/welcome.md").read_text()
        rows = [renderer.cells(line) for line in text.splitlines() if line.startswith("|")]
        rows.pop(1)
        for version in ("", "AgentDevWorkSpace 版本：本地 0.3.8，远端 0.3.8（已是最新）",
                        "AgentDevWorkSpace 版本：本地 0.3.8，远端 未知（获取远端版本失败）"):
            for columns in (40, 80, 120):
                for color in (False, True):
                    with self.subTest(version=version, columns=columns, color=color):
                        output = renderer.render_welcome(text, version, color, columns)
                        lines = renderer.ANSI.sub("", output).splitlines()
                        self.assertEqual(lines[0], "🚀 AgentDevWorkSpace")
                        index = 1
                        if version:
                            self.assertEqual(lines[index], renderer.render_version(version, False))
                            index += 1
                        self.assertEqual(lines[index], "SDD · Spec-Driven Development")
                        self.assertTrue(lines[index + 1].startswith("┌"))
                        self.assertIn(renderer.render_table(rows, columns, color), output)

    def test_body_paragraph_spacing_is_preserved(self):
        text = "# Title\n## Heading\n\nFirst paragraph.\n\nSecond paragraph."
        self.assertEqual(renderer.render_welcome(text),
                         "Title\nHeading\n\nFirst paragraph.\n\nSecond paragraph.")


if __name__ == '__main__':
    unittest.main(verbosity=2)
