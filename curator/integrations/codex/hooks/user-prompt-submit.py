import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SEARCH = ROOT / "scripts" / "search.py"


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0

    prompt = data.get("prompt", "").strip()
    if not prompt or not SEARCH.exists():
        return 0

    try:
        result = subprocess.run(
            [sys.executable, str(SEARCH), prompt],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except Exception:
        return 0

    output = result.stdout.strip()
    if not output:
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        "Curator playbook search results for this prompt:\n\n" + output
                    ),
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
