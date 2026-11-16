"""Welcome rendering regressions without running hooks or checking remote versions."""
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/sdd"))
from render_welcome import ANSI, cells, render_table, render_version, render_welcome


class WelcomeRenderingTests(unittest.TestCase):
    def test_version_is_immediately_followed_by_sdd_and_table(self):
        text = (ROOT / "skills/sdd/welcome.md").read_text()
        rows = [cells(line) for line in text.splitlines() if line.startswith("|")]
        rows.pop(1)
        for version in ("", "AgentDevWorkSpace 版本：本地 0.3.8，远端 0.3.8（已是最新）",
                        "AgentDevWorkSpace 版本：本地 0.3.8，远端 未知（获取远端版本失败）"):
            for columns in (40, 80, 120):
                for color in (False, True):
                    with self.subTest(version=version, columns=columns, color=color):
                        output = render_welcome(text, version, color, columns)
                        lines = ANSI.sub("", output).splitlines()
                        self.assertEqual(lines[0], "🚀 AgentDevWorkSpace")
                        index = 1
                        if version:
                            self.assertEqual(lines[index], render_version(version, False))
                            index += 1
                        self.assertEqual(lines[index], "SDD · Spec-Driven Development")
                        self.assertTrue(lines[index + 1].startswith("┌"))
                        self.assertIn(render_table(rows, columns, color), output)

    def test_body_paragraph_spacing_is_preserved(self):
        text = "# Title\n## Heading\n\nFirst paragraph.\n\nSecond paragraph."
        self.assertEqual(render_welcome(text),
                         "Title\nHeading\n\nFirst paragraph.\n\nSecond paragraph.")


if __name__ == "__main__":
    unittest.main()
