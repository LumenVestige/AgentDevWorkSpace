"""显式迁移历史 personal/Note；只读检测供 check 与欢迎语复用。"""
import os
from datetime import date
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RESERVED = {"skills", "config", ".agent", "workers"}
PERSONAL_CONTENT = {"specs", "notes", "feature", "bugfix", "change", "research"}
NOTE_NAME = re.compile(r"^(\d{2}-\d{2}-\d{2})-(\d{2}-\d{2}-\d{2}-.+\.md)$")
SHARED_LINK = re.compile(rb"\]\(((?:\.\./)+skills/(?:common|custom)/[^)\s]+)\)")


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


def legacy_workers(ws, user=None):
    if ws.is_symlink() or not ws.is_dir():
        return []
    return [p for p in sorted(ws.iterdir())
            if p.name not in RESERVED and not p.name.startswith(".") and not p.is_symlink() and p.is_dir()
            and (p.name == user or any(not (p / name).is_symlink() and (p / name).is_dir()
                                       for name in PERSONAL_CONTENT))]


def personal_dirs(ws, user=None):
    folders = legacy_workers(ws, user)
    workers = ws / "workers"
    if not workers.is_symlink() and workers.is_dir():
        folders += [p for p in sorted(workers.iterdir()) if not p.is_symlink() and p.is_dir()]
    return folders


def legacy_notes(ws, user=None):
    for personal in personal_dirs(ws, user):
        for source, _ in note_moves(personal / "notes"):
            yield source


def migration_issues(project, user=None):
    """只返回迁移提醒，不逐条列出路径；与 fix 使用同样的候选规则。"""
    ws = project / "agent-workspace"
    if ws.is_symlink():
        return ["agent-workspace 是符号链接，不能安全检查迁移数据"]
    issues = ["历史 personal / Note 待迁移"] if legacy_workers(ws, user) else []
    workers = ws / "workers"
    if workers.is_symlink() or (workers.exists() and not workers.is_dir()):
        issues.append("workers 必须是普通目录，不能安全迁移至符号链接或文件")
        return issues
    if not issues and next(legacy_notes(ws, user), None) is not None:
        issues.append("历史 personal / Note 待迁移")
    return issues


def validate(project):
    project = project.absolute().resolve()
    if not project.is_dir():
        raise RuntimeError(f"项目目录不存在：{project}")
    ws = project / "agent-workspace"
    if ws.is_symlink():
        raise RuntimeError("agent-workspace 不能是符号链接")
    if not ws.is_dir():
        raise RuntimeError(f"不是 agent-workspace 工作区：{project}，请先执行 agentdev init")
    workers = ws / "workers"
    if workers.is_symlink() or (workers.exists() and not workers.is_dir()):
        raise RuntimeError("workers 必须是普通目录，不能是符号链接或文件")
    return project


def repair_links(source, destination, ws):
    """仅修正已移动 Markdown 中指向共享 skills 的相对链接，保留其他字节。"""
    files = [destination] if destination.is_file() else (
        Path(folder) / name for folder, _, names in os.walk(destination, followlinks=False)
        for name in names)
    for file in files:
        if file.is_symlink() or file.suffix != ".md":
            continue
        old = source if destination.is_file() else source / file.relative_to(destination)
        data = file.read_bytes()
        def replace(match):
            target = Path(os.path.normpath(old.parent / os.fsdecode(match[1])))
            try:
                target.relative_to(ws / "skills")
            except ValueError:
                return match[0]
            return b"](" + os.fsencode(os.path.relpath(target, file.parent)) + b")"
        changed = SHARED_LINK.sub(replace, data)
        if changed != data:
            file.write_bytes(changed)


def move_tree(source, destination, ws, conflicts):
    if destination.is_symlink():
        conflicts.append(str(source.relative_to(ws)))
    elif not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        if not destination.is_symlink():
            repair_links(source, destination, ws)
    elif not source.is_symlink() and source.is_dir() and destination.is_dir():
        for child in sorted(source.iterdir()):
            move_tree(child, destination / child.name, ws, conflicts)
        if not any(source.iterdir()):
            source.rmdir()
    else:
        conflicts.append(str(source.relative_to(ws)))


def note_moves(notes):
    if notes.is_symlink() or not notes.is_dir():
        return []
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
    return moves


def fix_notes_directory(notes, *, verbose=True):
    """只触及指定 notes，保留定点修复 API。"""
    migrated = skipped = 0
    moves = note_moves(notes)
    for source, target in moves:
        if not safe_path(target, notes) or target.exists():
            print(f'跳过（目标已存在或路径为符号链接，保留原文件）：{source.relative_to(notes)} → {target.relative_to(notes)}')
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        migrated += 1
    if verbose:
        print(f'Note 迁移完成：已迁移 {migrated} 个，目标已存在跳过 {skipped} 个（保留原文件）')
    return migrated, skipped


def fix_notes(project, *, user=None):
    from lib.workspace import project_settings
    project = validate(project)
    user = user if user is not None else project_settings(project)["personal"]
    migrated = skipped = 0
    for personal in personal_dirs(project / "agent-workspace", user):
        count, conflicts = fix_notes_directory(personal / "notes", verbose=False)
        migrated += count
        skipped += conflicts
    print(f"Note 迁移完成：已迁移 {migrated} 个，目标已存在跳过 {skipped} 个（保留原文件）")
    return migrated, skipped


def fix_workspace(project):
    from lib.workspace import project_settings
    project = validate(project)
    user = project_settings(project)["personal"]  # 配置无效时在任何写入之前退出。
    ws = project / "agent-workspace"
    conflicts = []
    candidates = legacy_workers(ws, user)
    for source in candidates:
        move_tree(source, ws / "workers" / source.name, ws, conflicts)
    print(f"personal 迁移：处理 {len(candidates)} 个旧目录，冲突 {len(conflicts)} 项")
    for path in conflicts:
        print(f"冲突保留源文件和目标文件：agent-workspace/{path}")
    fix_notes(project, user=user)
    if conflicts:
        raise RuntimeError("个人目录迁移存在冲突；请处理以上文件后重试 agentdev fix")


if __name__ == "__main__":
    try:
        fix_workspace(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"fix：{error}", file=sys.stderr)
        sys.exit(1)
