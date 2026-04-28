import re
from datetime import date
from pathlib import Path


CURATOR_DIR = Path(__file__).parent.parent
TRAUMAS_DIR = CURATOR_DIR / "traumas" / "active"
DIARY_DIR = CURATOR_DIR / "diary"
TEMPLATE_PATH = CURATOR_DIR / "templates" / "diary-entry.md"


def parse_frontmatter(content):
    """Parse simple YAML frontmatter from a string."""
    if not content.startswith("---\n"):
        return {}
    try:
        end_idx = content.index("\n---\n", 4)
    except ValueError:
        return {}

    fm = {}
    for line in content[4:end_idx].split("\n"):
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            val = val[1:-1]
        fm[key] = val
    return fm


def trauma_matches(command):
    """Return active trauma entries whose regex matches the command."""
    if not command or not TRAUMAS_DIR.exists():
        return []

    matches = []
    for trauma_file in TRAUMAS_DIR.glob("*.md"):
        try:
            content = trauma_file.read_text()
        except Exception:
            continue

        fm = parse_frontmatter(content)
        pattern = fm.get("pattern")
        if not pattern:
            continue

        try:
            matched = re.search(pattern, command, re.IGNORECASE)
        except re.error:
            continue

        if not matched:
            continue

        matches.append(
            {
                "severity": fm.get("severity", "medium").lower(),
                "title": fm.get("title", trauma_file.stem),
                "pattern": pattern,
                "rationale": fm.get("rationale", ""),
                "recovery": fm.get("recovery", ""),
                "source_diary": fm.get("source_diary", ""),
            }
        )
    return matches


def format_trauma_message(match, blocked=False):
    label = "BLOCKED" if blocked else "WARNING"
    message = (
        f"[Curator Trauma Guard] {label}: {match['severity'].upper()}: {match['title']}\n"
        f"Matched pattern: {match['pattern']}\n"
        f"Rationale: {match['rationale']}"
    )
    if match.get("recovery"):
        message += f"\nRecovery: {match['recovery']}"
    if match.get("source_diary"):
        message += f"\nSource: {match['source_diary']}"
    return message


def project_slug_from_cwd(cwd):
    project_name = Path(cwd).name
    return re.sub(r"[^a-z0-9]+", "-", project_name.lower()).strip("-")


def ensure_diary_template(cwd, agent):
    """Create today's diary template if one does not already exist."""
    today = date.today().isoformat()
    existing = list(DIARY_DIR.glob(f"{today}-*.md"))
    if existing:
        return None

    if not TEMPLATE_PATH.exists():
        return None

    project_slug = project_slug_from_cwd(cwd)
    content = TEMPLATE_PATH.read_text()
    content = content.replace("diary-YYYY-MM-DD-project-name", f"diary-{today}-{project_slug}")
    content = content.replace("YYYY-MM-DD", today)
    content = content.replace("project-name", project_slug)
    content = content.replace("agent-name", agent)

    DIARY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DIARY_DIR / f"{today}-{project_slug}.md"
    out_path.write_text(content)
    return out_path
