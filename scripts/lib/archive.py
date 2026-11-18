"""显式分组归档当前用户的开发记录，不改动条目内容。"""
from pathlib import Path
import re

from lib.fix import safe_path
from lib.workspace import project_settings

KINDS = ('feature', 'bugfix', 'change', 'research', 'notes/git-commit-change', 'notes/large-scale-file-change')


def archive_directory(base, threshold, group_size):
    entries = sorted((p for p in base.iterdir() if p.name != 'archived' and not p.name.startswith('.')
                      and not p.is_symlink() and (p.is_file() or p.is_dir())), key=lambda p: p.name)
    pending = entries[:-threshold] if len(entries) > threshold else []
    if not pending:
        return 0, 0
    archived = base / 'archived'
    if not safe_path(archived, base) or (archived.exists() and not archived.is_dir()):
        print(f'跳过（归档路径不是安全目录）：{archived}')
        return 0, len(pending)
    batches = [p for p in archived.iterdir() if re.fullmatch(r'\d{2,}', p.name) and int(p.name) > 0] if archived.exists() else []
    number = max((int(p.name) for p in batches), default=1)
    # 不改动已有分组；只补满编号最大的组，后续从该编号继续。
    batch = archived / f'{number:02d}'
    moved = skipped = 0
    for entry in pending:
        if not safe_path(batch, base) or (batch.exists() and not batch.is_dir()):
            print(f'跳过（分组路径不是安全目录）：{batch}')
            skipped += 1
            continue
        if batch.exists() and len(list(batch.iterdir())) >= group_size:
            number += 1
            batch = archived / f'{number:02d}'
        target = batch / entry.name
        if not safe_path(target, base) or target.exists():
            print(f'跳过（目标已存在或为符号链接）：{entry} → {target}')
            skipped += 1
            continue
        batch.mkdir(parents=True, exist_ok=True)
        entry.rename(target)
        moved += 1
    return moved, skipped


def archive_workspace(project):
    project = Path(project).absolute().resolve()
    if not project.is_dir():
        raise RuntimeError(f'项目目录不存在：{project}')
    ws = project / 'agent-workspace'
    if not ws.is_dir():
        raise RuntimeError(f'不是 agent-workspace 工作区：{project}，请先执行 agentdev init')
    settings = project_settings(project)
    options = settings['config']['archive']
    moved = skipped = 0
    for kind in KINDS:
        base = ws / 'workers' / settings['personal'] / kind
        if not safe_path(base, project):
            print(f'跳过（工作目录为符号链接）：{base}')
            continue
        if base.is_dir():
            count, conflicts = archive_directory(base, options['threshold'], options['group_size'])
            moved += count
            skipped += conflicts
    print(f'Archive 完成：已归档 {moved} 个，跳过 {skipped} 个；保留最新 {options["threshold"]} 个，每组最多 {options["group_size"]} 个')
    return moved, skipped
