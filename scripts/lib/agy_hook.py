"""Adapt shared skills to the official Antigravity 1.5.13 hook protocol."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True


def session_output(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("hookSpecificOutput", {}), dict):
        raise ValueError("共享 SessionStart hook 必须返回 JSON 对象")
    context = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
    visible = payload.get("systemMessage", "")
    if not isinstance(context, str) or not isinstance(visible, str):
        raise ValueError("共享 SessionStart 文本必须是字符串")
    # agy 1.5.13 scrubs renderInfo (internal_only); metadata maps panic in
    # ScrubInternalFields. Keep all workspace information in the public context
    # field. This version's TUI does not display these system messages.
    text = "\n\n".join(part for part in (visible, context) if part)
    return {"injectSteps": [{"systemMessage": {"systemMessage": text}}]} if text else {"injectSteps": []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agentdev", action="store_true")
    parser.add_argument("--client", choices=("agy",), default="agy")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--event", choices=("SessionStart", "Stop"), required=True)
    parser.add_argument("script")
    args = parser.parse_args()
    event = json.loads(sys.stdin.read() or "{}")
    if not isinstance(event, dict):
        raise ValueError("agy hook 输入必须是 JSON 对象")
    if args.event == "Stop" and event.get("fullyIdle") is False:
        print(json.dumps({"decision": "allow"}))
        return 0
    if args.event == "Stop":
        attempt = event.get("executionNum", 1)
        event["stop_hook_active"] = isinstance(attempt, int) and attempt > 1
    runner = Path(__file__).with_name("run_skill.py")
    result = subprocess.run([sys.executable, "-B", str(runner), "--agentdev", "--client", "agy",
                             "--project", str(args.project), args.script], cwd=args.project,
                            input=json.dumps(event), capture_output=True, text=True, timeout=60)
    if args.event == "Stop":
        output = ({"decision": "continue", "reason": result.stderr.strip() or result.stdout.strip()}
                  if result.returncode == 2 else {"decision": "allow"})
        if result.returncode not in (0, 2) and result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
    elif result.returncode:
        output = {"injectSteps": [{"errorMessage": {"userMessage": result.stderr.strip() or "AgentDevWorkSpace hook 执行失败"}}]}
    else:
        output = session_output(json.loads(result.stdout or "{}"))
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        print(f"AgentDevWorkSpace agy hook 失败：{error}", file=sys.stderr)
        sys.exit(1)
