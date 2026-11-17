"""旧版 Note 迁移辅助入口，不暴露为 app 命令。"""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.workspace import fix_notes

if __name__ == "__main__":
    fix_notes(Path(sys.argv[1] if len(sys.argv) > 1 else ".").absolute())
