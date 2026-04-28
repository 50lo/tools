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

    print(f"\n[Curator] Diary template ready: {out_path}")
    print("Fill in the diary entry to help Curator learn from this session.")
    print("Pay special attention to the ## Failures section if anything went wrong.")

    sys.exit(0)

except Exception:
    sys.exit(0)
