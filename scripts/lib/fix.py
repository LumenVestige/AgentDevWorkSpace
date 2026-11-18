"""显式迁移历史 personal/Note；只读检测供 check 与欢迎语复用。"""
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RESERVED = {"skills", "config", ".agent", "workers"}
PERSONAL_CONTENT = {"specs", "notes", "feature", "bugfix", "change", "research"}
NOTE_NAME = re.compile(r"^(\d{2}-\d{2}-\d{2})-(\d{2}-\d{2}-\d{2}-.+\.md)$")
SHARED_LINK = re.compile(rb"\]\(((?:\.\./)+skills/(?:common|custom)/[^)\s]+)\)")


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
        notes = personal / "notes"
        if notes.is_symlink():
            continue
        for file in sorted(notes.glob("*.md")):
            if not file.is_symlink() and file.is_file() and NOTE_NAME.fullmatch(file.name):
                yield file


def migration_issues(project, user=None):
    """不创建目录、不运行迁移；与 fix 使用同样的候选规则。"""
    ws = project / "agent-workspace"
    if ws.is_symlink():
        return ["agent-workspace 是符号链接，不能安全检查迁移数据"]
    issues = [f"历史 personal 目录待迁移：{p.relative_to(project)}" for p in legacy_workers(ws, user)]
    workers = ws / "workers"
    if workers.is_symlink() or (workers.exists() and not workers.is_dir()):
        issues.append("workers 必须是普通目录，不能安全迁移至符号链接或文件")
        return issues
    issues += [f"历史 Note 待迁移：{p.relative_to(project)}" for p in legacy_notes(ws, user)]
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


def fix_notes(project, *, user=None):
    from lib.workspace import project_settings
    project = validate(project)
    user = user if user is not None else project_settings(project)["personal"]
    ws = project / "agent-workspace"
    migrated = skipped = 0
    for file in legacy_notes(ws, user):
        match = NOTE_NAME.fullmatch(file.name)
        target = file.parent / "git-commit-change" / ("20" + match[1]) / match[2]
        if any(p.is_symlink() for p in (target.parent.parent, target.parent)):
            raise RuntimeError(f"Note 迁移目标不能包含符号链接：{target}")
        if target.exists() or target.is_symlink():
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        file.rename(target)
        migrated += 1
    print(f"Note 迁移完成：已迁移 {migrated} 个，目标已存在跳过 {skipped} 个（保留原文件）")


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
