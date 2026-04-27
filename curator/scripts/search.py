"""
search.py — Search the playbook by keyword and score.

Usage: python search.py [--maturity MATURITY] [--category CATEGORY] [--limit N] [query words...]
"""

import sys
import re
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


def parse_args(argv):
    """Parse CLI args manually. Returns (maturity, category, limit, query_tokens)."""
    maturity_filter = None
    category_filter = None
    limit = 10
    query_words = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--maturity':
            i += 1
            if i < len(argv):
                maturity_filter = argv[i]
        elif arg == '--category':
            i += 1
            if i < len(argv):
                category_filter = argv[i]
        elif arg == '--limit':
            i += 1
            if i < len(argv):
                try:
                    limit = int(argv[i])
                except ValueError:
                    print(f'Error: --limit requires an integer, got {argv[i]!r}', file=sys.stderr)
                    sys.exit(1)
        else:
            query_words.append(arg)
        i += 1

    return maturity_filter, category_filter, limit, query_words


def tokenize(text):
    """Split text on whitespace and punctuation, lowercase."""
    return re.split(r'[\s\W]+', text.lower())


def main():
    maturity_filter, category_filter, limit, query_words = parse_args(sys.argv[1:])

    if not PLAYBOOK_DIR.exists():
        print(f'Error: playbook directory not found at {PLAYBOOK_DIR}', file=sys.stderr)
        sys.exit(1)

    query_tokens = tokenize(' '.join(query_words)) if query_words else []
    query_tokens = [t for t in query_tokens if t]

    results = []

    for filepath in sorted(PLAYBOOK_DIR.glob('*.md')):
        fm, body = parse_frontmatter(filepath)
        if not fm:
            continue

        if fm.get('maturity') == 'deprecated':
            continue

        if maturity_filter and fm.get('maturity') != maturity_filter:
            continue

        if category_filter and fm.get('category') != category_filter:
            continue

        title = str(fm.get('title', ''))
        category = str(fm.get('category', ''))
        tags = fm.get('tags', [])
        if isinstance(tags, list):
            tags_str = ' '.join(str(t) for t in tags)
        else:
            tags_str = str(tags)

        search_text = (title + ' ' + category + ' ' + tags_str + ' ' + body).lower()

        if query_tokens:
            keyword_score = sum(1 for t in query_tokens if t in search_text)
        else:
            keyword_score = 1

        effective_score = float(fm.get('effective_score', 0.5))
        combined_score = keyword_score * effective_score

        results.append((combined_score, effective_score, fm, filepath))

    results.sort(key=lambda x: x[0], reverse=True)
    results = results[:limit]

    if not results:
        print('No matching rules found.')
        return

    print(f'Found {len(results)} rule(s):')
    for combined_score, effective_score, fm, filepath in results:
        rule_id = fm.get('id', filepath.stem)
        maturity = fm.get('maturity', 'candidate')
        rule_type = fm.get('type', '')
        category = fm.get('category', '')
        title = fm.get('title', filepath.stem)

        if rule_type == 'anti-pattern':
            meta = f'{maturity}, anti-pattern, score={effective_score:.2f}'
        else:
            meta = f'{maturity}, score={effective_score:.2f}'

        line = f'[{rule_id}] ({meta}) {category} — {title}'

        if effective_score < 0.2:
            line += '  [low confidence]'

        print(line)


if __name__ == '__main__':
    main()
