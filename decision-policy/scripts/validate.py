#!/usr/bin/env python3

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Set

try:
    import yaml
except ImportError:  # pragma: no cover - depends on the user's environment.
    yaml = None


ALLOWED_ACTORS = ("user", "agent")
ALLOWED_BASIS = (
    "explicit_user_instruction",
    "derived_from_principles",
    "repo_pattern",
    "agent_judgment",
)
ALLOWED_STATUSES = ("active", "superseded")
ALLOWED_PRECEDENCE = (
    "explicit_user_instruction",
    "current_prd_or_issue",
    "agent_principles",
    "decisions_log_precedents",
    "existing_repo_conventions",
    "agent_judgment",
    "agent_judgement",
)


def present_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_array(value: Any) -> bool:
    return isinstance(value, list) and all(present_string(item) for item in value)


def valid_slug(value: Any) -> bool:
    if not present_string(value):
        return False

    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
    return (
        value[0] in set("abcdefghijklmnopqrstuvwxyz0123456789")
        and all(char in allowed for char in value)
    )


def load_yaml(path: Path, errors: List[str]) -> Optional[Any]:
    if not path.is_file():
        errors.append(f"Missing required file: {path}")
        return None

    if yaml is None:
        errors.append(
            "PyYAML is required to parse YAML. Install it with: python3 -m pip install PyYAML"
        )
        return None

    try:
        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file)
    except yaml.YAMLError as error:
        errors.append(f"Invalid YAML in {path}: {error}")
        return None


def validate_principles(
    data: Any, errors: List[str], warnings: List[str]
) -> None:
    if not isinstance(data, dict):
        errors.append("agent_principles.yml must be a mapping/object")
        return

    if "version" not in data:
        errors.append("agent_principles.yml: version is required")
    if not present_string(data.get("updated")):
        errors.append("agent_principles.yml: updated must be a non-empty string")

    priorities = data.get("priorities")
    if not isinstance(priorities, list) or not priorities:
        errors.append("agent_principles.yml: priorities must be a non-empty array")
        return

    ids: Set[Any] = set()
    ranks: Set[Any] = set()

    for index, priority in enumerate(priorities):
        prefix = f"agent_principles.yml: priorities[{index}]"

        if not isinstance(priority, dict):
            errors.append(f"{prefix} must be a mapping/object")
            continue

        priority_id = priority.get("id")
        rank = priority.get("rank")

        if not valid_slug(priority_id):
            errors.append(f"{prefix}.id must be a lowercase kebab-case string")
        if priority_id in ids:
            errors.append(f"{prefix}.id duplicates {priority_id!r}")
        elif priority_id is not None:
            ids.add(priority_id)

        if not isinstance(rank, int) or isinstance(rank, bool) or rank <= 0:
            errors.append(f"{prefix}.rank must be a positive integer")
        if rank in ranks:
            errors.append(f"{prefix}.rank duplicates {rank!r}")
        elif rank is not None:
            ranks.add(rank)

        if not present_string(priority.get("statement")):
            errors.append(f"{prefix}.statement must be a non-empty string")

        if "prefer" in priority and not string_array(priority.get("prefer")):
            errors.append(f"{prefix}.prefer must be an array of non-empty strings")

        if "ask_user_when" in priority:
            warnings.append(
                f"{prefix}.ask_user_when is deprecated; use top-level "
                "autonomy.ask_user_only_when only for project-wide fallback boundaries"
            )
            if not string_array(priority.get("ask_user_when")):
                errors.append(
                    f"{prefix}.ask_user_when must be an array of non-empty strings"
                )

    precedence = data.get("precedence")
    if precedence:
        if not string_array(precedence):
            errors.append(
                "agent_principles.yml: precedence must be an array of non-empty strings"
            )
        else:
            unknown = [
                value for value in precedence if value not in ALLOWED_PRECEDENCE
            ]
            if unknown:
                warnings.append(
                    "agent_principles.yml: unknown precedence values: "
                    + ", ".join(unknown)
                )

    autonomy = data.get("autonomy")
    if not autonomy:
        return

    if not isinstance(autonomy, dict):
        errors.append("agent_principles.yml: autonomy must be a mapping/object")
        return

    if "default" in autonomy and not present_string(autonomy.get("default")):
        errors.append(
            "agent_principles.yml: autonomy.default must be a non-empty string"
        )

    if "ask_user_only_when" in autonomy and not string_array(
        autonomy.get("ask_user_only_when")
    ):
        errors.append(
            "agent_principles.yml: autonomy.ask_user_only_when must be an array of "
            "non-empty strings"
        )


def validate_iso8601(value: Any) -> bool:
    if not present_string(value):
        return False

    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False

    return True


def validate_decisions(data: Any, errors: List[str], warnings: List[str]) -> None:
    if not isinstance(data, list):
        errors.append("decisions_log.yml must be an array; use [] for an empty log")
        return

    ids: Set[str] = set()

    for index, entry in enumerate(data):
        prefix = f"decisions_log.yml: entries[{index}]"

        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be a mapping/object")
            continue

        entry_id = entry.get("id")
        if not present_string(entry_id):
            errors.append(f"{prefix}.id must be a non-empty string")
        elif entry_id in ids:
            errors.append(f"{prefix}.id duplicates {entry_id!r}")
        else:
            ids.add(entry_id)

        if not validate_iso8601(entry.get("timestamp")):
            errors.append(f"{prefix}.timestamp must be an ISO-8601 timestamp string")

        actor = entry.get("actor")
        if actor not in ALLOWED_ACTORS:
            errors.append(
                f"{prefix}.actor must be one of: {', '.join(ALLOWED_ACTORS)}"
            )

        basis = entry.get("basis")
        if basis not in ALLOWED_BASIS:
            errors.append(
                f"{prefix}.basis must be one of: {', '.join(ALLOWED_BASIS)}"
            )

        status = entry.get("status")
        if status not in ALLOWED_STATUSES:
            errors.append(
                f"{prefix}.status must be one of: {', '.join(ALLOWED_STATUSES)}"
            )

        if not present_string(entry.get("decision")):
            errors.append(f"{prefix}.decision must be a non-empty string")
        if not present_string(entry.get("rationale")):
            errors.append(f"{prefix}.rationale must be a non-empty string")

        if "principles" in entry and not string_array(entry.get("principles")):
            errors.append(f"{prefix}.principles must be an array of non-empty strings")

        known = {
            "id",
            "timestamp",
            "actor",
            "basis",
            "principles",
            "decision",
            "rationale",
            "status",
            "supersedes",
            "superseded_by",
        }
        unknown = [str(key) for key in entry if str(key) not in known]
        if unknown:
            warnings.append(f"{prefix} has unknown fields: {', '.join(unknown)}")


def usage(program_name: str) -> None:
    print(f"Usage: {program_name} [PROJECT_DIR]", file=sys.stderr)
    print(file=sys.stderr)
    print(
        "Validates PROJECT_DIR/agent_principles.yml and PROJECT_DIR/decisions_log.yml.",
        file=sys.stderr,
    )
    print("PROJECT_DIR defaults to the current directory.", file=sys.stderr)


def main(argv: List[str]) -> int:
    if len(argv) > 1 or "-h" in argv or "--help" in argv:
        usage(Path(sys.argv[0]).name)
        return 1 if len(argv) > 1 else 0

    project_dir = Path(argv[0] if argv else ".").expanduser().resolve()
    principles_path = project_dir / "agent_principles.yml"
    decisions_path = project_dir / "decisions_log.yml"

    errors: List[str] = []
    warnings: List[str] = []

    principles = load_yaml(principles_path, errors)
    decisions = load_yaml(decisions_path, errors)

    if principles is not None:
        validate_principles(principles, errors, warnings)
    if decisions is not None:
        validate_decisions(decisions, errors, warnings)

    for warning in warnings:
        print(f"WARN: {warning}", file=sys.stderr)

    if not errors:
        print("Decision policy files are valid.")
        return 0

    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
