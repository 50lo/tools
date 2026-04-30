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
ALLOWED_STATUSES = ("active", "superseded")


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


def validate_iso8601(value: Any) -> bool:
    if not present_string(value):
        return False

    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False

    return True


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


def validate_agent_rules(data: Any, errors: List[str], warnings: List[str]) -> None:
    if not isinstance(data, dict):
        errors.append("agent_rules.yml must be a mapping/object")
        return

    if not validate_iso8601(data.get("updated")):
        errors.append("agent_rules.yml: updated must be an ISO-8601 timestamp string")

    if not present_string(data.get("purpose")):
        errors.append("agent_rules.yml: purpose must be a non-empty string")

    required_workflow = data.get("required_workflow")
    if not isinstance(required_workflow, list) or not required_workflow:
        errors.append("agent_rules.yml: required_workflow must be a non-empty array")
    elif not string_array(required_workflow):
        errors.append(
            "agent_rules.yml: required_workflow must be an array of non-empty strings"
        )

    precedence = data.get("precedence")
    if not isinstance(precedence, list) or not precedence:
        errors.append("agent_rules.yml: precedence must be a non-empty array")
    elif not string_array(precedence):
        errors.append("agent_rules.yml: precedence must be an array of non-empty strings")

    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("agent_rules.yml: rules must be a non-empty array")
        return

    priorities: Set[int] = set()
    ids: Set[str] = set()

    for index, rule in enumerate(rules):
        prefix = f"agent_rules.yml: rules[{index}]"

        if not isinstance(rule, dict):
            errors.append(f"{prefix} must be a mapping/object")
            continue

        priority = rule.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority <= 0:
            errors.append(f"{prefix}.priority must be a positive integer")
        elif priority in priorities:
            errors.append(f"{prefix}.priority duplicates {priority!r}")
        else:
            priorities.add(priority)

        rule_id = rule.get("id")
        if not valid_slug(rule_id):
            errors.append(f"{prefix}.id must be a lowercase kebab-case string")
        elif rule_id in ids:
            errors.append(f"{prefix}.id duplicates {rule_id!r}")
        else:
            ids.add(rule_id)

        applies_to = rule.get("applies_to")
        if not isinstance(applies_to, list) or not applies_to:
            errors.append(f"{prefix}.applies_to must be a non-empty array")
        elif not string_array(applies_to):
            errors.append(f"{prefix}.applies_to must be an array of non-empty strings")

        if not present_string(rule.get("rule")):
            errors.append(f"{prefix}.rule must be a non-empty string")

        prefer = rule.get("prefer")
        if not isinstance(prefer, list) or not prefer:
            errors.append(f"{prefix}.prefer must be a non-empty array")
        elif not string_array(prefer):
            errors.append(f"{prefix}.prefer must be an array of non-empty strings")

    quick_lookup = data.get("quick_lookup")
    if quick_lookup is None:
        return

    if not isinstance(quick_lookup, dict):
        errors.append("agent_rules.yml: quick_lookup must be a mapping/object")
        return

    if "log_focus" in quick_lookup:
        log_focus = quick_lookup.get("log_focus")
        if not isinstance(log_focus, list) or not log_focus:
            errors.append("agent_rules.yml: quick_lookup.log_focus must be a non-empty array")
        elif not string_array(log_focus):
            errors.append(
                "agent_rules.yml: quick_lookup.log_focus must be an array of non-empty strings"
            )

    if "optional_yq_examples" in quick_lookup:
        examples = quick_lookup.get("optional_yq_examples")
        if not isinstance(examples, list) or not examples:
            errors.append(
                "agent_rules.yml: quick_lookup.optional_yq_examples must be a non-empty array"
            )
        elif not string_array(examples):
            errors.append(
                "agent_rules.yml: quick_lookup.optional_yq_examples must be an array of non-empty strings"
            )

    known = {"updated", "purpose", "required_workflow", "precedence", "rules", "quick_lookup"}
    unknown = [str(key) for key in data if str(key) not in known]
    if unknown:
        warnings.append(f"agent_rules.yml has unknown fields: {', '.join(unknown)}")


def validate_decisions_log(data: Any, errors: List[str], warnings: List[str]) -> None:
    if not isinstance(data, dict):
        errors.append("decisions_log.yml must be a mapping/object")
        return

    if not validate_iso8601(data.get("updated")):
        errors.append("decisions_log.yml: updated must be an ISO-8601 timestamp string")

    usage = data.get("usage")
    if not isinstance(usage, list) or not usage:
        errors.append("decisions_log.yml: usage must be a non-empty array")
    elif not string_array(usage):
        errors.append("decisions_log.yml: usage must be an array of non-empty strings")

    entries = data.get("entries")
    if not isinstance(entries, list):
        errors.append("decisions_log.yml: entries must be an array")
        return

    ids: Set[str] = set()

    for index, entry in enumerate(entries):
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

        if not present_string(entry.get("source")):
            errors.append(f"{prefix}.source must be a non-empty string")

        if not present_string(entry.get("scope")):
            errors.append(f"{prefix}.scope must be a non-empty string")

        if not present_string(entry.get("summary")):
            errors.append(f"{prefix}.summary must be a non-empty string")

        if not present_string(entry.get("rationale")):
            errors.append(f"{prefix}.rationale must be a non-empty string")

        status = entry.get("status")
        if status not in ALLOWED_STATUSES:
            errors.append(
                f"{prefix}.status must be one of: {', '.join(ALLOWED_STATUSES)}"
            )

        known = {"id", "timestamp", "actor", "source", "scope", "summary", "rationale", "status"}
        unknown = [str(key) for key in entry if str(key) not in known]
        if unknown:
            warnings.append(f"{prefix} has unknown fields: {', '.join(unknown)}")

    known = {"updated", "usage", "entries"}
    unknown = [str(key) for key in data if str(key) not in known]
    if unknown:
        warnings.append(f"decisions_log.yml has unknown fields: {', '.join(unknown)}")


def usage(program_name: str) -> None:
    print(f"Usage: {program_name} [PROJECT_DIR]", file=sys.stderr)
    print(file=sys.stderr)
    print(
        "Validates PROJECT_DIR/agent_rules.yml and PROJECT_DIR/decisions_log.yml.",
        file=sys.stderr,
    )
    print("PROJECT_DIR defaults to the current directory.", file=sys.stderr)


def main(argv: List[str]) -> int:
    if len(argv) > 1 or "-h" in argv or "--help" in argv:
        usage(Path(sys.argv[0]).name)
        return 1 if len(argv) > 1 else 0

    project_dir = Path(argv[0] if argv else ".").expanduser().resolve()
    rules_path = project_dir / "agent_rules.yml"
    decisions_path = project_dir / "decisions_log.yml"

    errors: List[str] = []
    warnings: List[str] = []

    rules = load_yaml(rules_path, errors)
    decisions = load_yaml(decisions_path, errors)

    if rules is not None:
        validate_agent_rules(rules, errors, warnings)
    if decisions is not None:
        validate_decisions_log(decisions, errors, warnings)

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
