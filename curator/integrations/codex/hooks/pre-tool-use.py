import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "hooks"))

from common import format_trauma_message, trauma_matches  # noqa: E402


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0

    if data.get("tool_name") != "Bash":
        return 0

    command = data.get("tool_input", {}).get("command", "")
    if not command:
        return 0

    warnings = []
    for match in trauma_matches(command):
        if match["severity"] in ("critical", "high"):
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": format_trauma_message(match, blocked=True),
                        }
                    }
                )
            )
            return 0
        warnings.append(format_trauma_message(match, blocked=False))

    if warnings:
        print(json.dumps({"systemMessage": "\n\n".join(warnings)}))

    return 0


if __name__ == "__main__":
    sys.exit(main())
