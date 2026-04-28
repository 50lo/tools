import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "hooks"))

from common import ensure_diary_template  # noqa: E402


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
        cwd = data.get("cwd", os.getcwd())
    except Exception:
        cwd = os.getcwd()

    out_path = ensure_diary_template(cwd, agent="claude-code")
    if out_path is None:
        return 0

    print(
        json.dumps(
            {
                "systemMessage": (
                    f"[Curator] Diary template ready: {out_path}\n"
                    "Fill it in after significant work, especially the ## Failures section."
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
