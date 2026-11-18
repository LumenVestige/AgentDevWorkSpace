"""显式迁移旧版 Note，并纠正旧 fix 产生的非提交 Note 误分类。"""
from datetime import date
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.workspace import project_settings

LEGACY = re.compile(r"^(?P<date>(?:\d{4}|\d{2})-\d{2}-\d{2})-(?P<name>.+)$")
GIT_SECTION = re.compile(r"^#{1,6}[ \t]+(?:Git[ \t]*提交|Commits?|提交记录)[ \t]*\n(.*?)(?=^#{1,6}[ \t]|\Z)", re.M | re.S | re.I)
COMMIT_LINE = re.compile(r"^[ \t]*(?:[-*][ \t]+)?`?[0-9a-f]{7,40}`?(?:[ \t]+|$)", re.M | re.I)
COMMIT_TYPE = 'git-commit-change'
LARGE_TYPE = 'large-scale-file-change'


def safe_path(path, root):
    """检查路径自身和到边界的各级目录，不沿符号链接读写。"""
    return path.is_relative_to(root) and all(not p.is_symlink() for p in (*reversed(path.parents), path) if p == root or root in p.parents)


def has_commits(entry):
    # 目录的说明文档负责分类；不把 evidence/ 中的源码 hash 当作提交记录。
    files = sorted(entry.glob('*.md')) if entry.is_dir() else [entry]
    for file in files:
        if file.is_symlink() or not file.is_file():
            continue
        text = file.read_text(encoding='utf-8-sig')
        if any(COMMIT_LINE.search(section[1]) for section in GIT_SECTION.finditer(text)):
            return True
    return False


def fix_notes_directory(notes):
    """只触及指定 notes 目录；亦供已授权的旧工作区定点修复。"""
    migrated = skipped = 0
    if not notes.is_symlink() and notes.is_dir():
        moves = []
        for entry in sorted(notes.iterdir()):
            match = LEGACY.fullmatch(entry.name)
            if not match or match['name'] in {'.', '..'} or not safe_path(entry, notes) or not (entry.is_dir() or entry.suffix.lower() == '.md'):
                continue
            try:
                day = date.fromisoformat(('20' if len(match['date']) == 8 else '') + match['date'])
            except ValueError:
                continue
            kind = COMMIT_TYPE if has_commits(entry) else LARGE_TYPE
            moves.append((entry, notes / kind / str(day) / match['name']))
        # 早期 fix 全部写入 Git 类型；只纠正标准日期层，不扫描 archived 或附件。
        planned_targets = {target for _, target in moves}
        git_notes = notes / COMMIT_TYPE
        if safe_path(git_notes, notes) and git_notes.is_dir():
            for day in sorted(git_notes.iterdir()):
                if not safe_path(day, notes) or not day.is_dir():
                    continue
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day.name):
                    continue
                try:
                    date.fromisoformat(day.name)
                except ValueError:
                    continue
                for entry in sorted(day.iterdir()):
                    if entry not in planned_targets and safe_path(entry, notes) and (entry.is_dir() or entry.suffix.lower() == '.md') and not has_commits(entry):
                        moves.append((entry, notes / LARGE_TYPE / day.name / entry.name))
        for source, target in moves:
            if not safe_path(target, notes) or target.exists():
                print(f'跳过（目标已存在或路径为符号链接，保留原文件）：{source.relative_to(notes)} → {target.relative_to(notes)}')
                skipped += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
            migrated += 1
    print(f'Note 迁移完成：已迁移 {migrated} 个，目标已存在跳过 {skipped} 个（保留原文件）')
    return migrated, skipped


def fix_notes(project):
    project = project.absolute().resolve()
    if not project.is_dir():
        raise RuntimeError(f'项目目录不存在：{project}')
    if not (project / 'agent-workspace').is_dir():
        raise RuntimeError(f'不是 agent-workspace 工作区：{project}，请先执行 agentdev init')
    user = project_settings(project)['personal']
    notes = project / 'agent-workspace' / user / 'notes'
    if not safe_path(notes, project):
        raise ValueError(f'拒绝迁移符号链接工作区：{notes}')
    return fix_notes_directory(notes)


if __name__ == '__main__':
    try:
        fix_notes(Path(sys.argv[1] if len(sys.argv) > 1 else '.'))
    except (OSError, RuntimeError, ValueError) as error:
        print(f'fix：{error}', file=sys.stderr)
        sys.exit(1)
