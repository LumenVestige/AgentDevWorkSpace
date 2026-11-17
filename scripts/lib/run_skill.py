"""跨平台 hook 分发；从工作区加载 custom 优先的 skill。"""
import argparse
import os
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser()
parser.add_argument("--agentdev", action="store_true")
parser.add_argument("--client", choices=("claude", "codex"))
parser.add_argument("--project", type=Path, required=True)
parser.add_argument("script")
args = parser.parse_args()
if args.client:
    os.environ["AGENTDEV_CLIENT"] = args.client
parts = Path(args.script).parts
if len(parts) != 2 or any(part in {".", ".."} for part in parts):
    parser.error("skill 脚本路径必须是 <skill>/<script.py>")
root = next((path for path in (Path.cwd(), *Path.cwd().parents) if (path / "agent-workspace").is_dir()), args.project)
workspace = root / "agent-workspace"
script = workspace / "skills/custom" / args.script
if not script.is_file():
    script = workspace / "skills/common" / args.script
if script.is_file():
    os.chdir(root)
    sys.path.insert(0, str(script.parent))
    sys.argv = [str(script)]
    runpy.run_path(str(script), run_name="__main__")
