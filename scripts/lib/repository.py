"""Independent master installations and read-only checks of the installed worktree."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def git(root, *args, timeout=5):
    # Hooks may export an index/worktree from the caller's project. Never inspect it.
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
                'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_NAMESPACE'):
        env.pop(key, None)
    return subprocess.run(['git', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=' + os.devnull,
                           '-C', str(root), *map(str, args)], env=env, check=True,
                          capture_output=True, timeout=timeout).stdout.decode('utf-8', errors='surrogateescape')


def stage_repository(source, staged, repository):
    """Clone only master, then retain source edits without inventing a clean commit.

    Return None for legacy non-Git snapshots; the installer keeps their old layout.
    """
    if not (source / '.git').exists():
        return None
    if Path(git(source, 'rev-parse', '--show-toplevel').strip()).resolve() != source.resolve():
        raise RuntimeError('安装来源必须是 Git 仓库根目录')
    if git(source, 'symbolic-ref', '--short', 'HEAD').strip() != 'master':
        raise RuntimeError('安装来源必须在 master 分支；请切换后再执行 setup.sh')
    # --no-local avoids shared objects/alternates and also supports linked worktrees.
    git(source, 'clone', '--no-local', '--depth', '1', '--single-branch', '--branch', 'master',
        '--no-tags', source, staged, timeout=120)
    git(staged, 'remote', 'set-url', 'origin', repository)
    mirror_worktree(source, staged)
    exclude = staged / '.git/info/exclude'
    with exclude.open('a', encoding='utf-8') as file:
        file.write('\n/.agentdev-app\n__pycache__/\n*.py[cod]\n')
    return git(staged, 'rev-parse', 'HEAD').strip()


def mirror_worktree(source, staged):
    """Copy Git-visible files, preserving symlinks and deletions, not private ignores."""
    names = set(git(source, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0')) - {''}
    # Start with only .git: copying a subset over the checkout would leave deleted files,
    # and traversing a checkout directory replaced by a symlink could escape the target.
    for path in staged.iterdir():
        if path.name == '.git':
            continue
        if path.is_symlink() or path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
    for name in sorted(names):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or '.git' in relative.parts:
            raise RuntimeError('源码包含不安全的 Git 路径')
        src, dst = source / relative, staged / relative
        symlink_parent = any((source / parent).is_symlink() for parent in reversed(relative.parents) if parent != Path('.'))
        if symlink_parent or not (src.is_symlink() or src.is_file()):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            dst.symlink_to(os.readlink(src))
        else:
            shutil.copy2(src, dst)


def installation_risk(home):
    """Return (visible warning, block replacement); absence of a legacy Git is unknown."""
    app = home / 'app'
    prefix = f'风险提示：安装目录 {app} '
    try:
        metadata = json.loads((home / 'install.json').read_text(encoding='utf-8'))
        baseline = metadata.get('commit')
        if (app / '.git').is_symlink() or not (app / '.git').is_dir():
            return prefix + '缺少独立 .git，无法检查本地改动；请备份并从 master 源码运行 setup.sh 重装。', bool(baseline)
        if Path(git(app, 'rev-parse', '--show-toplevel').strip()).resolve() != app.resolve():
            raise RuntimeError('安装目录不是独立仓库根目录')
        issues = []
        branch = git(app, 'symbolic-ref', '--short', 'HEAD').strip()
        if branch != 'master':
            issues.append('当前分支不是 master')
        head = git(app, 'rev-parse', 'HEAD').strip()
        if baseline and head != baseline:
            issues.append('HEAD 与安装基准不同，可能存在手工提交或 reset')
        status = git(app, '-c', 'core.quotePath=true', 'status', '--porcelain=v1', '--untracked-files=all').strip()
        if status:
            issues.append('存在异常改动：' + '; '.join(status.splitlines()[:5]))
        if issues:
            return prefix + '；'.join(issues) + '。更新可能丢失这些改动。', True
        if not baseline:
            return prefix + '缺少安装 commit 基准，无法检查本地提交偏移；请从 master 源码运行 setup.sh 重装。', False
        return '', False
    except (OSError, ValueError, AttributeError, RuntimeError, subprocess.SubprocessError):
        return prefix + '无法检查 Git 状态，可能缺少 Git 或仓库已损坏；请先备份并检查。', True


def warn_installation(home):
    warning, blocked = installation_risk(home)
    if warning:
        print(warning, file=sys.stderr)
    return blocked
