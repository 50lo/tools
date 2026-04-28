"""
reflect.py — Process unprocessed diary entries through a local agent CLI.

Usage:
  python reflect.py
  python reflect.py --agent claude
  python reflect.py --agent codex

Reads unprocessed diary entries from curator/diary/, calls a local agent CLI to extract
rule candidates and trauma patterns, writes rules to curator/playbook/,
appends trauma candidates to curator/traumas/pending.md, and marks diary
entries as processed.
"""

import argparse
import json
import os
import shutil
import sys
import secrets
import subprocess
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
    """Build the user message for the agent CLI call."""
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
# Agent CLI providers
# ---------------------------------------------------------------------------


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "debugging",
                            "testing",
                            "architecture",
                            "workflow",
                            "documentation",
                            "integration",
                            "git",
                            "security",
                            "performance",
                            "general",
                        ],
                    },
                    "type": {"type": "string", "enum": ["rule", "anti-pattern"]},
                    "text": {"type": "string"},
                    "context": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "evidence": {"type": "string"},
                },
                "required": ["title", "category", "type", "text", "context", "tags", "evidence"],
                "additionalProperties": False,
            },
        },
        "traumas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    "pattern": {"type": "string"},
                    "rationale": {"type": "string"},
                    "recovery": {"type": "string"},
                },
                "required": ["title", "severity", "pattern", "rationale", "recovery"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["rules", "traumas"],
    "additionalProperties": False,
}


def parse_args():
    parser = argparse.ArgumentParser(description="Extract Curator rules and trauma candidates.")
    parser.add_argument(
        "--agent",
        choices=("auto", "claude", "codex"),
        default=os.environ.get("CURATOR_REFLECT_AGENT", "auto"),
        help="Local agent CLI to use. Defaults to CURATOR_REFLECT_AGENT or auto.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model argument passed through to the selected agent CLI.",
    )
    return parser.parse_args()


def select_agent(agent):
    if agent != "auto":
        if not shutil.which(agent):
            raise RuntimeError(f"{agent!r} command not found on PATH")
        return agent

    for candidate in ("claude", "codex"):
        if shutil.which(candidate):
            return candidate
    raise RuntimeError("No supported agent CLI found. Install Claude Code or Codex CLI.")


def schema_path():
    path = CURATOR_DIR / ".cache" / "reflection-schema.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(OUTPUT_SCHEMA, indent=2))
    return path


def run_agent(command, prompt, timeout=300):
    result = subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=timeout,
        cwd=str(CURATOR_DIR),
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        raise RuntimeError(f"{command[0]} exited with status {result.returncode}{detail}")
    return result.stdout


def call_claude_cli(system_prompt, user_message, model):
    command = [
        "claude",
        "-p",
        "--no-session-persistence",
        "--max-turns",
        "1",
        "--permission-mode",
        "plan",
        "--tools",
        "",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(OUTPUT_SCHEMA),
        "--append-system-prompt",
        system_prompt,
    ]
    if model:
        command.extend(["--model", model])
    command.append(user_message)

    stdout = run_agent(command, prompt="")
    envelope = json.loads(stdout)
    if isinstance(envelope, dict):
        for key in ("result", "content", "text", "response"):
            value = envelope.get(key)
            if isinstance(value, str):
                return value
        if "rules" in envelope and "traumas" in envelope:
            return json.dumps(envelope)
    return stdout


def call_codex_cli(system_prompt, user_message, model):
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--output-schema",
        str(schema_path()),
        "--skip-git-repo-check",
    ]
    if model:
        command.extend(["--model", model])
    command.append(system_prompt + "\n\n" + user_message)

    return run_agent(command, prompt="")


def call_agent(agent, system_prompt, user_message, model):
    selected = select_agent(agent)
    if selected == "claude":
        return call_claude_cli(system_prompt, user_message, model)
    if selected == "codex":
        return call_codex_cli(system_prompt, user_message, model)
    raise ValueError(f"Unsupported agent: {selected}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    try:
        args = parse_args()

        # 1. Find unprocessed diary entries
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
        user_message = build_user_message(entries_text)

        # 4. Call local agent CLI
        try:
            raw_response = call_agent(args.agent, SYSTEM_PROMPT, user_message, args.model)
        except Exception as e:
            print(f"Error running {args.agent} agent: {e}", file=sys.stderr)
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
