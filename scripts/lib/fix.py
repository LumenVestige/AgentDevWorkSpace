"""显式修复旧版工作区数据；保留直接运行的兼容入口。"""
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.workspace import project_settings


def fix_notes(project):
    project = project.absolute().resolve()
    if not project.is_dir():
        raise RuntimeError(f"项目目录不存在：{project}")
    if not (project / "agent-workspace").is_dir():
        raise RuntimeError(f"不是 agent-workspace 工作区：{project}，请先执行 agentdev init")
    user = project_settings(project)["personal"]
    notes = project / "agent-workspace" / user / "notes"
    pattern = re.compile(r"^(\d{2}-\d{2}-\d{2})-(\d{2}-\d{2}-\d{2}-.+\.md)$")
    migrated = skipped = 0
    for file in sorted(notes.glob("*.md")):
        match = pattern.fullmatch(file.name)
        if not match or not file.is_file():
            continue
        target = notes / "git-commit-change" / ("20" + match[1]) / match[2]
        if target.exists() or target.is_symlink():
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        file.rename(target)
        migrated += 1
    print(f"Note 迁移完成：已迁移 {migrated} 个，目标已存在跳过 {skipped} 个（保留原文件）")


if __name__ == "__main__":
    try:
        fix_notes(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"fix：{error}", file=sys.stderr)
        sys.exit(1)
