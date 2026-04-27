import json
import os
import re
import sys
from datetime import date
from pathlib import Path

CURATOR_DIR = Path(__file__).parent.parent
DIARY_DIR = CURATOR_DIR / "diary"
TEMPLATE_PATH = CURATOR_DIR / "templates" / "diary-entry.md"

try:
    try:
        data = json.loads(sys.stdin.read())
        cwd = data.get('cwd', os.getcwd())
    except Exception:
        cwd = os.getcwd()

    project_name = Path(cwd).name
    project_slug = re.sub(r'[^a-z0-9]+', '-', project_name.lower()).strip('-')

    today = date.today().isoformat()

    existing = list(DIARY_DIR.glob(f"{today}-*.md"))
    if existing:
        sys.exit(0)

    if not TEMPLATE_PATH.exists():
        sys.exit(0)

    content = TEMPLATE_PATH.read_text()

    # Replace slug reference first to avoid double-replacement
    content = content.replace(
        f"diary-YYYY-MM-DD-project-name",
        f"diary-{today}-{project_slug}"
    )
    content = content.replace("YYYY-MM-DD", today)
    content = content.replace("project-name", project_slug)

    DIARY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DIARY_DIR / f"{today}-{project_slug}.md"
    out_path.write_text(content)

    print(f"\n[Curator] Diary template ready: curator/diary/{today}-{project_slug}.md")
    print("Fill in the diary entry to help Curator learn from this session.")
    print("Pay special attention to the ## Failures section if anything went wrong.")

    sys.exit(0)

except Exception:
    sys.exit(0)
