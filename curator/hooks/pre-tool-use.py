import json
import sys
from common import format_trauma_message, trauma_matches


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

    warnings = []

    for match in trauma_matches(command):
        if match["severity"] in ('critical', 'high'):
            print(format_trauma_message(match, blocked=True), file=sys.stderr)
            sys.exit(2)
        else:
            warnings.append(format_trauma_message(match, blocked=False))

    for w in warnings:
        print(w, file=sys.stderr)

    sys.exit(0)

except Exception:
    sys.exit(0)
