# Curator Memory System

## Before Starting A Task

Before any non-trivial task (> ~15 min), use Curator context:

```bash
python curator/scripts/search.py "<brief description of what you're about to do>"
```

Read the output. Let matching rules inform your approach. If no rules match, proceed normally.

## During A Session

If a rule from the playbook was directly useful, note its ID, using the format `r-XXXXXX`.
If a rule was wrong, misleading, or caused a problem, note its ID and mark it harmful at the end of the session.

## Ending A Significant Session

After any session involving real decisions, debugging, or more than about 30 minutes of work, write a diary entry at:

```text
curator/diary/YYYY-MM-DD-project-slug.md
```

Use the template at `curator/templates/diary-entry.md`.

The `## Failures` section is critical. If any command or action caused data loss, required a rollback, broke something, or wasted significant time, document the exact command or action, what broke, the impact, and how it was recovered. Leave it empty only if nothing failed.

## After A Session

If you noted helpful or harmful rules:

```bash
python curator/scripts/feedback.py <rule-id> helpful
python curator/scripts/feedback.py <rule-id> harmful
```

## Boundaries

Curator does not replace reading the codebase and understanding the current state.
Playbook rules are probabilistic guidance, not hard constraints.
When a rule conflicts with the specific context of a task, use judgment and record the outcome in the diary.
