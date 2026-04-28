import json
import os
import sys
from common import ensure_diary_template

try:
    try:
        data = json.loads(sys.stdin.read())
        cwd = data.get('cwd', os.getcwd())
    except Exception:
        cwd = os.getcwd()

    out_path = ensure_diary_template(cwd, agent="claude-code")
    if out_path is None:
        sys.exit(0)

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

    sys.exit(0)

except Exception:
    sys.exit(0)
