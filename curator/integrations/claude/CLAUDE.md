# Curator Memory System

## Before starting a task

Before any non-trivial task (> ~15 min), run:

```bash
python curator/scripts/search.py "<brief description of what you're about to do>"
```

Read the output. Let matching rules inform your approach. If no rules match, proceed normally.

## During a session — tracking rule usage

If a rule from the playbook was directly useful, note its ID (format: `r-XXXXXX`).
If a rule was wrong, misleading, or caused a problem, note its ID and that it was harmful.
Record feedback at the end of the session.

## Ending a significant session — write diary

After any session that's non-trivial (anything involving real decisions, debugging, or > 30 minutes of work), write a diary entry at:

```text
curator/diary/YYYY-MM-DD-project-slug.md
```

Use the template at `curator/templates/diary-entry.md`. Replace all placeholders.

**Critical instruction about the `## Failures` section:** If any command or action during this session caused data loss, required a rollback, broke something, or wasted significant time, document it here with the exact command or action, what broke, impact, and how it was recovered. This section is the primary source for trauma pattern extraction. An empty `## Failures` section means nothing went wrong; only leave it empty if that's true.

## After a session — record feedback

If you noted helpful or harmful rules during the session:

```bash
python curator/scripts/feedback.py <rule-id> helpful
python curator/scripts/feedback.py <rule-id> harmful
```

## What Curator does not replace

- Reading the actual codebase and understanding the current state.
- Playbook rules are probabilistic guides, not hard constraints.
- When a rule conflicts with the specific context of a task, use judgment and record the outcome in the diary so the rule's confidence updates accordingly.
