"""
maintain.py — Weekly playbook maintenance.

Usage: python maintain.py [--dry-run]

Recomputes confidence_decay, effective_score, maturity for every rule.
Applies anti-pattern inversion when harmful_count >= 3 on a rule type.
"""

import sys
import os
import re
from datetime import date
from pathlib import Path

PLAYBOOK_DIR = Path(__file__).parent.parent / "playbook"


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


def compute_scores(fm):
    """Compute confidence_decay and effective_score from frontmatter fields."""
    lv_val = fm.get('last_validated') or fm.get('created', '')
    try:
        lv_date = date.fromisoformat(str(lv_val).strip())
    except (ValueError, TypeError):
        lv_date = date.today()

    days_since = (date.today() - lv_date).days
    confidence_decay = round(0.5 ** (days_since / 90.0), 4)

    helpful = int(fm.get('helpful_count', 0))
    harmful = int(fm.get('harmful_count', 0))
    if helpful + harmful == 0:
        feedback_ratio = 0.5
    else:
        feedback_ratio = max(0.0, min(1.0, helpful / (helpful + harmful * 4)))

    effective_score = round(confidence_decay * feedback_ratio, 4)
    return confidence_decay, effective_score


def compute_maturity(fm, effective_score):
    """Compute maturity level. Never un-deprecates."""
    helpful = int(fm.get('helpful_count', 0))
    harmful = int(fm.get('harmful_count', 0))

    if harmful >= helpful * 2 and helpful > 0:
        return 'deprecated'
    elif helpful >= 10 and effective_score >= 0.5:
        return 'proven'
    elif helpful >= 3 and effective_score >= 0.3:
        return 'established'
    else:
        return 'candidate'


def main():
    dry_run = '--dry-run' in sys.argv

    if not PLAYBOOK_DIR.exists():
        print(f"Error: playbook directory not found at {PLAYBOOK_DIR}", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(PLAYBOOK_DIR.glob('*.md'))
    processed = 0
    changes = []

    for filepath in md_files:
        fm, body = parse_frontmatter(filepath)
        if not fm:
            continue

        if fm.get('maturity') == 'deprecated':
            continue

        processed += 1

        old_maturity = fm.get('maturity', 'candidate')
        old_type = fm.get('type', '')
        old_score = float(fm.get('effective_score', 0.0))
        title = fm.get('title', filepath.stem)
        rule_id = fm.get('id', filepath.stem)

        confidence_decay, effective_score = compute_scores(fm)
        new_maturity = compute_maturity(fm, effective_score)

        fm['confidence_decay'] = confidence_decay
        fm['effective_score'] = effective_score
        fm['maturity'] = new_maturity

        # Anti-pattern inversion
        new_type = old_type
        if int(fm.get('harmful_count', 0)) >= 3 and fm.get('type') == 'rule':
            fm['type'] = 'anti-pattern'
            new_type = 'anti-pattern'
            if not str(fm.get('title', '')).startswith('AVOID: '):
                fm['title'] = 'AVOID: ' + str(fm.get('title', ''))
                title = fm['title']

        # Track changes
        file_changes = []
        if old_maturity != new_maturity:
            file_changes.append(f'maturity {old_maturity} → {new_maturity}')
        if old_type != new_type:
            file_changes.append(f'type {old_type} → {new_type}')
        if abs(effective_score - old_score) > 0.05:
            file_changes.append(f'score {old_score:.4f} → {effective_score:.4f}')

        if file_changes:
            changes.append(f'  {rule_id} ({title}): {", ".join(file_changes)}')
            if not dry_run:
                write_frontmatter(filepath, fm, body)

    prefix = '[DRY RUN] ' if dry_run else ''
    print(f'{prefix}Processed {processed} file(s).')
    if changes:
        for line in changes:
            print(f'{prefix}{line}')
    else:
        print(f'{prefix}No changes needed.')


if __name__ == '__main__':
    main()
