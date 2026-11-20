"""Unix工作区初始化与只读检查；不在项目内安装依赖。"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

REPOSITORY = "https://github.com/LumenVestige/AgentDevWorkSpace.git"

MARK_BEGIN = "<!-- agentskill:begin 以下内容由 AgentDevWorkSpace 的 init.sh 追加，重新执行时会被替换，请勿修改 -->"
MARK_END = "<!-- agentskill:end -->"
SCRIPTS = {"Stop": ("notes/verify.py", "sdd/check_layout.py"), "SessionStart": ("sdd/welcome.py", "sdd/load_constraints.py")}
HOOK_PATHS = (".claude/settings.local.json", ".codex/hooks.json", ".agents/hooks.json")
AGY_GROUP = "agentdev-workspace"


def git(root, *args):
    env = dict(os.environ)
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    result = subprocess.run(["git", "-C", str(root), *args], env=env, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def slug(name):
    name = re.sub(r"[A-Z]", lambda match: match.group().lower(), name)
    return re.sub(r"[\x00-\x20\x7f!-/:-@\[-`{-~]+", "-", name).strip("-")


def requirements(source):
    match = re.search(r'^deps="([^"]+)"$', (source / "scripts/lib/deps.sh").read_text(encoding="utf-8"), re.M)
    if not match:
        raise RuntimeError("无法读取依赖清单 scripts/lib/deps.sh")
    return shlex.split(match.group(1))


def project_settings(project, py=None, source=None, migrate=False):
    env = project / "agent-workspace/.agent/env"
    if py is None:
        pointer = env / "python-path"
        legacy = env / "venv" / "bin/python"
        py = Path(pointer.read_text(encoding="utf-8").strip()) if pointer.is_file() else legacy if legacy.is_file() else Path(sys.executable)
    source = source or Path(__file__).resolve().parents[2]
    result = subprocess.run([str(py), "-B", str(source / "skills/_workspace_config.py"), str(project), *(["--migrate"] if migrate else [])],
                            capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "config.json5 配置格式错误")
    return json.loads(result.stdout)


def runtime_errors(py, source, check_dependencies=True):
    if not py.is_file():
        return [f"Python 解释器不存在：{py}"]
    deps = requirements(source) if check_dependencies else []
    code = ("import importlib.metadata as m,json,sys; "
            "print(json.dumps({'version':list(sys.version_info[:2]),'venv':sys.prefix!=sys.base_prefix,"
            "'packages':{s.split('==')[0]:m.version(s.split('==')[0]) for s in sys.argv[1:]}}))")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        result = subprocess.run([str(py), "-B", "-c", code, *deps], env=env, capture_output=True, text=True, timeout=20)
        if result.returncode:
            return ["Python 无法运行或缺少依赖，请重新执行 source setup.sh 和 agentdev init"]
        data = json.loads(result.stdout)
        errors = []
        if data["version"] < [3, 9]:
            errors.append("需要 Python 3.9+")
        if not data["venv"]:
            errors.append("解释器不在虚拟环境中")
        for spec in deps:
            name, expected = spec.split("==")
            if data["packages"].get(name) != expected:
                errors.append(f"依赖版本不匹配：{spec}")
        pip = subprocess.run([str(py), "-B", "-m", "pip", "--version"], env=env, capture_output=True, timeout=20)
        if pip.returncode:
            errors.append("pip 不可用")
        return errors
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return [f"环境检查失败：{error}"]


def install_dependencies(source, home):
    py = home / "venv/bin/python"
    # 缺包不能阻止 init 修复依赖，但必须先确认目标确实是可用的共享 venv。
    errors = runtime_errors(py, source, check_dependencies=False)
    if errors:
        raise RuntimeError("；".join(errors))
    print("正在安装工作区依赖（deps.sh）…", flush=True)
    env = {**os.environ, "PIP_CONFIG_FILE": os.devnull, "PIP_CACHE_DIR": str(home / "cache"),
           "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run(["sh", str(source / "scripts/lib/deps.sh"), str(py)],
                   env=env, check=True, timeout=120)


def write_if_changed(path, text):
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def append_lines(path, lines):
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = text.splitlines()
    for line in lines:
        if line not in existing:
            text = text.rstrip("\n") + ("\n" if text else "") + line + "\n"
            existing.append(line)
    write_if_changed(path, text)


def fingerprint(path):
    digest = hashlib.sha256()
    files = sorted(path.rglob("*")) if path.is_dir() else [path]
    for file in files:
        if file.is_file():
            digest.update(str(file.relative_to(path) if path.is_dir() else file.name).encode("utf-8"))
            digest.update(file.read_bytes())
    return digest.hexdigest()


def link_or_copy(target, source, managed):
    key = str(target)
    if target.exists() or target.is_symlink():
        if target.is_symlink():
            if key not in managed and "agent-workspace" not in str(target.readlink()):
                print(f"保留已有链接：{target}")
                return
            target.unlink()
        elif managed.get(key) == fingerprint(target):
            shutil.rmtree(target) if target.is_dir() else target.unlink()
        else:
            print(f"保留已有文件或目录：{target}")
            return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(os.path.relpath(source, target.parent), target_is_directory=source.is_dir())
        managed[key] = "symlink"
    except OSError:
        shutil.copytree(source, target) if source.is_dir() else shutil.copy2(source, target)
        managed[key] = fingerprint(target)


def sync_agent_rules(project, source, managed):
    """入口只保留文件引用；旧的受管明文块和未修改入口可迁移。"""
    agents = project / "AGENTS.md"
    rules = project / "agent-workspace/AGENTS.md"
    write_if_changed(rules, (source / "AGENTS.md").read_text(encoding="utf-8"))
    key = str(agents)
    generated = key in managed or not (agents.exists() or agents.is_symlink())
    text = ""
    if agents.is_symlink():
        if managed.get(key) != "symlink":
            print(f"保留已有链接：{agents}")
            return
        # 只替换受管理的入口，不写入旧链接的目标（可能是安装目录）。
        agents.unlink()
    elif agents.exists():
        if key in managed:
            if managed[key] != fingerprint(agents):
                print(f"保留已有文件或目录：{agents}")
                return
        else:
            text = agents.read_text(encoding="utf-8")
    text = re.sub(r"<!-- agentskill:begin[^\n]*-->.*?" + re.escape(MARK_END), "", text, flags=re.S).rstrip()
    reference = "请先阅读并遵守 [AgentDevWorkSpace 通用规则](agent-workspace/AGENTS.md)（路径相对于项目根目录）。"
    block = MARK_BEGIN + "\n\n" + reference + "\n" + MARK_END + "\n"
    write_if_changed(agents, (text + "\n\n" if text else "") + block)
    if generated:
        managed[key] = fingerprint(agents)


def load_json(path):
    value = json.loads(path.read_text(encoding="utf-8") or "{}") if path.exists() else {}
    if not isinstance(value, dict):
        raise ValueError(f"配置必须是 JSON 对象：{path}")
    if "hooks" in value:
        if not isinstance(value["hooks"], dict):
            raise ValueError(f"hooks 必须是对象：{path}")
        for entries in value["hooks"].values():
            if not isinstance(entries, list) or any(not isinstance(entry, dict) or not isinstance(entry.get("hooks", []), list) for entry in entries):
                raise ValueError(f"hook 事件格式错误：{path}")
            if any(not isinstance(hook, dict) or not isinstance(hook.get("command", ""), str) for entry in entries for hook in entry.get("hooks", [])):
                raise ValueError(f"hook 命令格式错误：{path}")
    return value


def hook_command(py, source, project, script, client=None):
    if client == "agy":
        event = next(event for event, scripts in SCRIPTS.items() if script in scripts)
        return shlex.join([str(py), "-B", str(source / "scripts/lib/agy_hook.py"),
                           "--agentdev", "--client", "agy", "--project", str(project),
                           "--event", event, script])
    args = [str(py), "-B", str(source / "scripts/lib/run_skill.py"), "--agentdev", "--project", str(project), script]
    if client:
        args[4:4] = ["--client", client]
    return shlex.join(args)


def own_hook(command):
    return "# agentskill" in command or (any(name in command for name in ("run_skill.py", "agy_hook.py"))
                                         and "--agentdev" in command)


def load_agy_hooks(path):
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError(f"agy hook 配置不能是符号链接：{path}")
    cfg = json.loads(path.read_text(encoding="utf-8") or "{}") if path.exists() else {}
    if not isinstance(cfg, dict):
        raise ValueError(f"agy hooks 必须是命名分组对象：{path}")
    for name, group in cfg.items():
        if name == "$schema":
            continue
        if not isinstance(group, dict):
            raise ValueError(f"agy hook 分组必须是对象：{path} {name}")
        if "enabled" in group and not isinstance(group["enabled"], bool):
            raise ValueError(f"agy hook enabled 必须是布尔值：{path} {name}")
        for event in (*SCRIPTS, "PreInvocation", "PostInvocation", "PreToolUse", "PostToolUse"):
            if event not in group:
                continue
            handlers = group[event]
            if not isinstance(handlers, list):
                raise ValueError(f"agy hook 事件必须是数组：{path} {event}")
            for handler in handlers:
                if not isinstance(handler, dict):
                    raise ValueError(f"agy hook handler 必须是对象：{path} {event}")
                commands = handler.get("hooks", []) if event in {"PreToolUse", "PostToolUse"} else [handler]
                if not isinstance(commands, list) or any(not isinstance(h, dict) or
                        not isinstance(h.get("command"), str) for h in commands):
                    raise ValueError(f"agy hook command 必须是字符串：{path} {event}")
    return cfg


def hook_commands(path, cfg, event):
    if path.parent.name == ".agents":
        return [h.get("command", "") for group in cfg.values()
                if isinstance(group, dict) and group.get("enabled", True)
                for h in group.get(event, [])]
    return [h.get("command", "") for entry in cfg.get("hooks", {}).get(event, [])
            for h in entry.get("hooks", [])]


def register_hooks(path, cfg, py, source, project):
    if path.parent.name == ".agents":
        group = cfg.setdefault(AGY_GROUP, {})
        for event, scripts in SCRIPTS.items():
            kept = [h for h in group.get(event, []) if not own_hook(h.get("command", ""))]
            group[event] = kept + [{"type": "command", "command": hook_command(py, source, project, script, "agy"),
                                    "timeout": 90} for script in scripts]
        write_if_changed(path, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
        return
    events = cfg.setdefault("hooks", {})
    for event, scripts in SCRIPTS.items():
        kept = []
        for entry in events.get(event, []):
            hooks = [hook for hook in entry.get("hooks", []) if not own_hook(hook.get("command", ""))]
            if hooks:
                kept.append({**entry, "hooks": hooks})
        for script in scripts:
            kept.append({**({"matcher": "startup|clear"} if event == "SessionStart" and script == "sdd/welcome.py" else {}),
                         "hooks": [{"type": "command", "command": hook_command(py, source, project, script, "claude" if path.parent.name == ".claude" else "codex")}]})
        events[event] = kept
    write_if_changed(path, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")


def repository_identity(url):
    """统一 URL 和 SCP 风格地址，仅比较主机与仓库路径。"""
    url = re.sub(r"^([^/:]+):(?=[^/])", r"ssh://\1/", url.strip())
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http", "ssh", "git"} or not parsed.hostname:
            return None
        return parsed.hostname.lower(), parsed.path.strip("/").lower().removesuffix(".git")
    except ValueError:
        return None


def is_source_repository(project):
    """通过 Git remote URL 识别主仓库，排除受管理安装。"""
    expected = repository_identity(REPOSITORY)
    return not (project / ".agentdev-app").exists() and any(
        repository_identity(line.partition(" ")[2]) == expected
        for line in git(project, "config", "--get-regexp", r"^remote\..*\.url$").splitlines()
    )


def refresh_common(source, ws):
    """使用模板源整体刷新 common，保留 custom 和工作区运行时配置。"""
    common = ws / "skills/common"
    with tempfile.TemporaryDirectory(prefix="skills-", dir=ws / ".agent/tmp") as temporary:
        staged = Path(temporary) / "common"
        shutil.copytree(source / "skills", staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        if common.is_symlink():
            common.unlink()
        elif common.exists():
            common.rename(Path(temporary) / "previous")
        staged.rename(common)
    return common


def initialize(source, home, project):
    project = project.absolute().resolve()
    if not project.is_dir():
        raise RuntimeError(f"项目目录不存在：{project}")
    if project == home or home in project.parents:
        raise RuntimeError("不能把全局安装目录初始化为工作区")
    git_root = git(project, "rev-parse", "--show-toplevel")
    if git_root and Path(git_root).resolve() != project:
        raise RuntimeError("请在 Git 仓库根目录执行 agentdev init，避免创建嵌套工作区")
    source_repository = is_source_repository(project)
    # Templates may come from a checkout; executable hooks always use app/.
    runtime_source = home / "app"
    py = home / "venv" / "bin/python"
    install_dependencies(source, home)
    errors = runtime_errors(py, source)
    if errors:
        raise RuntimeError("；".join(errors))
    user = project_settings(project, py, source)["personal"]
    configs = {project / relative: (load_agy_hooks if relative.startswith('.agents/') else load_json)(project / relative)
               for relative in HOOK_PATHS}
    ws = project / "agent-workspace"
    env = ws / ".agent/env"
    for path in (env, ws / ".agent/tmp", ws / ".agent/profiles", ws / ".agent/evals", ws / "skills/custom", ws / "config", ws / "workers" / user / "specs", ws / "workers" / user / "notes"):
        path.mkdir(parents=True, exist_ok=True)
    common = refresh_common(source, ws)
    if not any((ws / "skills/custom").iterdir()):
        (ws / "skills/custom/.gitkeep").touch()
    sdd = ws / "skills/custom/sdd" if (ws / "skills/custom/sdd").is_dir() else common / "sdd"
    constraint = ws / "workers" / user / "specs/constraints.md"
    if not constraint.exists():
        shutil.copy2(sdd / "personal-constraints.md", constraint)
    config = ws / "config/config.json5"
    if not config.exists():
        legacy = ws / "config/notes.json5"
        if legacy.exists():
            legacy.rename(config)
        else:
            shutil.copy2(common / "notes/config.json5", config)
    project_settings(project, py, source, migrate=True)
    write_if_changed(env / "agentskill-path", str(runtime_source) + "\n")
    write_if_changed(env / "python-path", str(py) + "\n")
    write_if_changed(env / "agentskill-version", (source / "publish/version").read_text(encoding="utf-8"))
    if not (env / "venv").exists() and not (env / "venv").is_symlink():
        (env / "venv").symlink_to(home / "venv", target_is_directory=True)
    if not (env / "note-base").exists():
        (env / "note-base").write_text(git(project, "rev-parse", "-q", "--verify", "HEAD") + "\n", encoding="utf-8")
    (env / "last-update").write_text(f"{int(time.time())}\n", encoding="utf-8")
    managed = load_json(env / "managed-links.json")
    agents = project / "AGENTS.md"
    # 主仓库自己的规则是模板源，不写入受管引用。
    if not source_repository:
        sync_agent_rules(project, source, managed)
    for name in ("CLAUDE.md", "GEMINI.md"):
        link_or_copy(project / name, agents, managed)
    for name in sorted({path.name for directory in (common, ws / "skills/custom") for path in directory.iterdir() if path.is_dir()}):
        target = ws / "skills/custom" / name
        if not target.is_dir():
            target = common / name
        for directory in (".claude/skills", ".agents/skills"):
            link_or_copy(project / directory / name, target, managed)
    write_if_changed(env / "managed-links.json", json.dumps(managed, indent=2, ensure_ascii=False) + "\n")
    if not source_repository:
        append_lines(project / ".gitignore", ["/agent-workspace/config/", "/agent-workspace/.agent/", "/agent-workspace/.agent/tmp/", "/agent-workspace/workers/*/specs/", "/agent-workspace/*/specs/"])
    if git_root:
        exclude = Path(git(project, "rev-parse", "--git-path", "info/exclude"))
        exclude = exclude if exclude.is_absolute() else project / exclude
        append_lines(exclude, ["/AGENTS.md", "/CLAUDE.md", "/GEMINI.md", "/.claude/skills/", "/.claude/settings.local.json", "/.codex/hooks.json",
                               "/.agents/skills/", "/.agents/hooks.json"])
        hook = Path(git(project, "rev-parse", "--git-path", "hooks/commit-msg"))
        hook = hook if hook.is_absolute() else project / hook
        if not hook.exists() or "# agentskill" in hook.read_text(encoding="utf-8", errors="replace"):
            write_if_changed(hook, '#!/bin/sh\n# agentskill\nf="$(git rev-parse --show-toplevel)/agent-workspace/skills/common/git-commit/commit-msg"\n[ -f "$f" ] || exit 0\nexec sh "$f" "$@"\n')
            hook.chmod(0o755)
        git(project, "config", "agentskill.python", str(py))
    for path, cfg in configs.items():
        register_hooks(path, cfg, py, runtime_source, project)
    print(f"已初始化：{project}（agent-workspace/workers/{user}，共享运行时 {py}）")
    print("Codex 首次使用项目 hook 时，请在客户端中信任本项目及相关 hook。")
    print("Antigravity CLI（agy）使用官方 .agents/hooks.json；可在 /hooks 中确认加载。")


def check_workspace(project):
    from .fix import migration_issues
    project = project.absolute().resolve()
    ws, errors = project / "agent-workspace", []
    user = None
    if not shutil.which("git"):
        errors.append("Git 不可用，请先安装 Git 并加入 PATH")
    for scripts in SCRIPTS.values():
        for script in scripts:
            if not any((ws / "skills" / kind / script).is_file() for kind in ("custom", "common")):
                errors.append(f"工作区缺少 skill 脚本：{script}")
    for relative in ("skills/common", "skills/common/_version.py", "skills/common/_workspace_config.py", "skills/custom", ".agent/env"):
        if not (ws / relative).exists():
            errors.append(f"工作区缺少：agent-workspace/{relative}")
    pointer = ws / ".agent/env/agentskill-path"
    interpreter = ws / ".agent/env/python-path"
    if pointer.is_file():
        source = Path(pointer.read_text(encoding="utf-8").strip())
        py = Path(interpreter.read_text(encoding="utf-8").strip()) if interpreter.is_file() else ws / ".agent/env/venv" / "bin/python"
        if (source / "scripts/lib/deps.sh").is_file():
            errors.extend(runtime_errors(py, source))
            if not errors:
                if not any((ws / "config" / name).is_file() for name in ("config.json5", "notes.json5")):
                    errors.append("缺少工作区配置 config.json5")
                else:
                    try:
                        user = project_settings(project, py, source)["personal"]
                    except ValueError as error:
                        errors.append(f"config.json5 配置格式错误：{error}")
        else:
            errors.append("AgentDevWorkSpace 安装路径不存在，请重新 agentdev init")
    else:
        errors.append("缺少 agentskill-path，请执行 agentdev init")
    for relative in HOOK_PATHS:
        path = project / relative
        try:
            cfg = (load_agy_hooks if path.parent.name == ".agents" else load_json)(path)
            for event, scripts in SCRIPTS.items():
                commands = [command.replace("\\", "/") for command in hook_commands(path, cfg, event)]
                for script in scripts:
                    if not any(script in command for command in commands):
                        errors.append(f"缺少 hook：{path.relative_to(project)} {event} {script}")
        except (OSError, ValueError) as error:
            errors.append(f"hook 配置错误：{error}")
    pending = migration_issues(project, user)
    if pending:
        errors.extend(pending)
        errors.append("请执行 agentdev fix 进行迁移；check 不会移动文件。")
    for error in errors:
        print(f"✗ {error}")
    if not errors:
        print(f"✓ 当前目录是 agent-workspace 工作区：{project}")
        print("✓ Python 3.9+、虚拟环境、pip、依赖和 hook 检查通过")
    return 1 if errors else 0
