"""
reflect.py — Process unprocessed diary entries through Claude API for rule/trauma extraction.

Usage: python reflect.py

Reads unprocessed diary entries from curator/diary/, calls Claude to extract
rule candidates and trauma patterns, writes rules to curator/playbook/,
appends trauma candidates to curator/traumas/pending.md, and marks diary
entries as processed.
"""

import json
import os
import sys
import secrets
from datetime import date
from pathlib import Path

CURATOR_DIR = Path(__file__).parent.parent
DIARY_DIR = CURATOR_DIR / "diary"
PLAYBOOK_DIR = CURATOR_DIR / "playbook"
PENDING_PATH = CURATOR_DIR / "traumas" / "pending.md"


# ---------------------------------------------------------------------------
# Frontmatter utilities
# ---------------------------------------------------------------------------

def parse_frontmatter(filepath):
    """Parse YAML frontmatter from a markdown file. Returns (dict, body_str)."""
    content = Path(filepath).read_text()
    if not content.startswith('---\n'):
        return {}, content
    try:
        end_idx = content.index('\n---\n', 4)
    except ValueError:
        return {}, content
    fm_text = content[4:end_idx]
    body = content[end_idx + 5:]
    fm = {}
    for line in fm_text.split('\n'):
        if ':' not in line or line.startswith('#'):
            continue
        key, _, val = line.partition(':')
        key = key.strip()
        val = val.strip()
        if val.startswith('[') and val.endswith(']'):
            inner = val[1:-1].strip()
            fm[key] = [x.strip().strip('"\'') for x in inner.split(',')] if inner else []
        elif val.startswith('"') and val.endswith('"'):
            fm[key] = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            fm[key] = val[1:-1]
        elif val.lower() == 'true':
            fm[key] = True
        elif val.lower() == 'false':
            fm[key] = False
        else:
            try:
                fm[key] = int(val)
            except ValueError:
                try:
                    fm[key] = float(val)
                except ValueError:
                    fm[key] = val
    return fm, body


def write_frontmatter(filepath, fm, body):
    """Write frontmatter dict + body back to a markdown file."""
    lines = ['---']
    for key, val in fm.items():
        if isinstance(val, list):
            if not val:
                lines.append(f'{key}: []')
            else:
                lines.append(f'{key}: [{", ".join(str(v) for v in val)}]')
        elif isinstance(val, bool):
            lines.append(f'{key}: {"true" if val else "false"}')
        elif isinstance(val, (int, float)):
            lines.append(f'{key}: {val}')
        elif isinstance(val, str):
            if any(c in val for c in ':#{}[]|>&*!,'):
                escaped = val.replace('"', '\\"')
                lines.append(f'{key}: "{escaped}"')
            else:
                lines.append(f'{key}: {val}')
        else:
            lines.append(f'{key}: {val}')
    lines.append('---')
    Path(filepath).write_text('\n'.join(lines) + '\n' + body)


# ---------------------------------------------------------------------------
# Rule ID generation
# ---------------------------------------------------------------------------

def new_rule_id():
    return 'r-' + secrets.token_hex(3)  # 6 hex chars


# ---------------------------------------------------------------------------
# Rule file writer
# ---------------------------------------------------------------------------

def write_rule_file(rule_id, rule, today, sources):
    """Write a rule candidate file to PLAYBOOK_DIR."""
    title = rule.get('title', 'Untitled Rule')
    category = rule.get('category', 'general')
    rule_type = rule.get('type', 'rule')
    text = rule.get('text', '')
    context = rule.get('context', '')
    evidence = rule.get('evidence', '')
    tags = rule.get('tags', [])

    sources_str = ', '.join(str(s) for s in sources) if sources else ''
    tags_str = ', '.join(str(t) for t in tags) if tags else ''

    def quote_if_needed(s):
        return f'"{s}"' if any(c in s for c in ':#{}[]|>&*!,') else s

    fm_lines = [
        '---',
        f'id: {rule_id}',
        f'title: {quote_if_needed(title)}',
        f'category: {category}',
        f'type: {rule_type}',
        f'maturity: candidate',
        f'helpful_count: 0',
        f'harmful_count: 0',
        f'effective_score: 0.5',
        f'confidence_decay: 1.0',
        f'last_validated: {today}',
        f'created: {today}',
        f'tags: [{tags_str}]',
        f'sources: [{sources_str}]',
        '---',
    ]

    body_lines = [
        '',
        text,
        '',
        '## Context',
        '',
        context,
        '',
        '## Evidence',
        '',
        evidence,
    ]

    content = '\n'.join(fm_lines) + '\n' + '\n'.join(body_lines) + '\n'
    rule_path = PLAYBOOK_DIR / f"{rule_id}.md"
    rule_path.write_text(content)


# ---------------------------------------------------------------------------
# Prompt construction helpers
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a coding knowledge extractor. You analyze coding session diary entries and extract two types of patterns:

1. RULES: Actionable practices that should be followed in future coding sessions.
2. TRAUMAS: Specific commands or actions that caused harm and should be blocked or warned against.

Be conservative and specific. Only extract patterns with clear evidence in the diary. Do not invent or generalize beyond what is documented."""


def build_entries_text(unprocessed):
    """Concatenate all diary entries with session headers."""
    parts = []
    for path, fm, body in unprocessed:
        session_id = fm.get(
            'session_id',
            f"diary-{fm.get('date', 'unknown')}-{fm.get('project', 'unknown')}"
        )
        diary_date = fm.get('date', 'unknown')
        project = fm.get('project', 'unknown')
        header = f"--- Session: {session_id} ({diary_date}, project: {project}) ---"
        parts.append(header)
        parts.append(body.strip())
        parts.append('')
    return '\n'.join(parts)


def build_user_message(entries_text):
    """Build the user message for the Claude API call."""
    return f"""Analyze the following coding session diary entries and extract rules and trauma patterns.

{entries_text}

---

Return JSON in exactly this format (no markdown, no commentary outside the JSON):
{{
  "rules": [
    {{
      "title": "Short imperative title (max 60 chars)",
      "category": "one of: debugging|testing|architecture|workflow|documentation|integration|git|security|performance|general",
      "type": "rule or anti-pattern",
      "text": "One clear actionable sentence.",
      "context": "When this applies. 1-2 sentences.",
      "tags": ["tag1", "tag2"],
      "evidence": "Brief note from the session supporting this rule."
    }}
  ],
  "traumas": [
    {{
      "title": "Short title describing the dangerous pattern",
      "severity": "low|medium|high|critical",
      "pattern": "Python regex that matches the dangerous command",
      "rationale": "What went wrong in 1-2 sentences.",
      "recovery": "How to recover or prevent in 1-2 sentences."
    }}
  ]
}}

Extraction rules:
- type "anti-pattern" for practices to avoid; "rule" for practices to follow
- Be specific and actionable
- Only extract 3-7 rules total across all sessions — quality over quantity
- ONLY extract traumas from ## Failures sections — never invent danger patterns
- Severity: low=wasted time, medium=required rollback, high=data loss/broke CI, critical=production incident
- If no failures are documented, return empty traumas array
- Pattern must be a valid Python regex matching the specific dangerous command"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    try:
        # 1. Check ANTHROPIC_API_KEY
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
            print("Set it with: export ANTHROPIC_API_KEY=your-key-here", file=sys.stderr)
            sys.exit(1)

        # 2. Find unprocessed diary entries
        unprocessed = []
        for path in sorted(DIARY_DIR.glob('*.md')):
            fm, body = parse_frontmatter(path)
            if fm and fm.get('processed') == False:
                unprocessed.append((path, fm, body))

        if not unprocessed:
            print("No unprocessed diary entries found.")
            return

        print(f"Processing {len(unprocessed)} diary entry/entries...")

        # 3. Build prompt
        entries_text = build_entries_text(unprocessed)

        # 4. Call Claude API
        try:
            import anthropic
        except ImportError:
            print("Error: anthropic package not installed.", file=sys.stderr)
            print("Install it with: pip install anthropic", file=sys.stderr)
            sys.exit(1)

        client = anthropic.Anthropic(api_key=api_key)

        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_message(entries_text)}]
            )
            raw_response = response.content[0].text
        except Exception as e:
            print(f"Error calling Claude API: {e}", file=sys.stderr)
            print("Diary entries have NOT been marked as processed.", file=sys.stderr)
            sys.exit(1)

        # 5. Parse JSON response
        try:
            text = raw_response.strip()
            if text.startswith('```'):
                text = text.split('\n', 1)[1]
                text = text.rsplit('```', 1)[0]
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raw_path = CURATOR_DIR / "traumas" / "pending-raw.txt"
            raw_path.write_text(raw_response)
            print(f"Warning: Could not parse JSON response. Raw response saved to {raw_path}", file=sys.stderr)
            print(f"JSON error: {e}", file=sys.stderr)
            print("Diary entries have NOT been marked as processed.", file=sys.stderr)
            sys.exit(1)

        rules = data.get('rules', [])
        traumas = data.get('traumas', [])

        # 6. Write rule candidates
        today = date.today().isoformat()
        rules_written = []
        sources = [
            fm.get('session_id', f"diary-{fm.get('date', 'unknown')}-{fm.get('project', 'unknown')}")
            for _, fm, _ in unprocessed
        ]
        for rule in rules:
            rule_id = new_rule_id()
            write_rule_file(rule_id, rule, today, sources)
            rules_written.append(rule_id)
            print(f"  Created rule: {rule_id} — {rule.get('title', '')}")

        # 7. Append trauma candidates
        if traumas:
            PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(PENDING_PATH, 'a') as f:
                for trauma in traumas:
                    session_id = unprocessed[0][1].get('session_id', 'unknown') if unprocessed else 'unknown'
                    trauma_id = secrets.token_hex(3)
                    f.write(f"\n## T-pending-{trauma_id}: {trauma.get('title', 'Unnamed')}\n\n")
                    f.write(f"**Extracted from:** {session_id}\n")
                    f.write(f"**Severity:** {trauma.get('severity', 'medium')}\n")
                    f.write(f"**Pattern:** `{trauma.get('pattern', '')}`\n\n")
                    f.write(f"**Rationale:** {trauma.get('rationale', '')}\n")
                    f.write(f"**Recovery:** {trauma.get('recovery', '')}\n\n")
                    f.write("---\n")
            print(f"  Appended {len(traumas)} trauma candidate(s) to traumas/pending.md")

        # 8. Mark diary entries as processed
        for path, fm, body in unprocessed:
            fm['processed'] = True
            write_frontmatter(path, fm, body)

        # 9. Summary
        print(f"\nReflection complete:")
        print(f"  {len(unprocessed)} diary entry/entries processed")
        print(f"  {len(rules_written)} rule(s) created in playbook/")
        print(f"  {len(traumas)} trauma candidate(s) added to traumas/pending.md")
        if traumas:
            print(f"  Review traumas/pending.md and promote valid entries to traumas/active/")

    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
