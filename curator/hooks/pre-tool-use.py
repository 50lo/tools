import json
import re
import sys
from pathlib import Path

TRAUMAS_DIR = Path(__file__).parent.parent / "traumas" / "active"


def parse_frontmatter(content):
    """Parse frontmatter from string (not file). Returns dict."""
    if not content.startswith('---\n'):
        return {}
    try:
        end_idx = content.index('\n---\n', 4)
    except ValueError:
        return {}
    fm = {}
    for line in content[4:end_idx].split('\n'):
        if ':' not in line:
            continue
        key, _, val = line.partition(':')
        key = key.strip()
        val = val.strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            val = val[1:-1]
        fm[key] = val
    return fm


try:
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    if data.get('tool_name') != 'Bash':
        sys.exit(0)

    command = data.get('tool_input', {}).get('command', '')
    if not command:
        sys.exit(0)

    if not TRAUMAS_DIR.exists():
        sys.exit(0)

    warnings = []

    for trauma_file in TRAUMAS_DIR.glob('*.md'):
        try:
            content = trauma_file.read_text()
        except Exception:
            continue

        fm = parse_frontmatter(content)
        pattern = fm.get('pattern')
        if not pattern:
            continue

        try:
            match = re.search(pattern, command, re.IGNORECASE)
        except re.error:
            continue

        if not match:
            continue

        severity = fm.get('severity', 'medium').lower()
        title = fm.get('title', trauma_file.stem)
        rationale = fm.get('rationale', '')
        recovery = fm.get('recovery', '')
        source_diary = fm.get('source_diary', '')

        if severity in ('critical', 'high'):
            msg = (
                f"[Curator Trauma Guard] BLOCKED — {severity.upper()}: {title}\n"
                f"Matched pattern: {pattern}\n"
                f"Rationale: {rationale}\n"
                f"Recovery: {recovery}"
            )
            if source_diary:
                msg += f"\nSource: {source_diary}"
            print(msg)
            sys.exit(1)
        else:
            warnings.append(
                f"[Curator Trauma Guard] WARNING — {severity.upper()}: {title}\n"
                f"Matched pattern: {pattern}\n"
                f"Rationale: {rationale}"
            )

    for w in warnings:
        print(w)

    sys.exit(0)

except Exception:
    sys.exit(0)
