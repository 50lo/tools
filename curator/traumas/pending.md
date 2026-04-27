# Trauma Candidates — Pending Review

Extracted by `scripts/reflect.py` from diary entries. These are **not yet active** — the Trauma Guard hook does not check this file. Review each entry, edit if needed, and promote valid ones to `traumas/active/`.

## How to promote a trauma

1. Verify the pattern matches exactly what went wrong (test the regex if unsure)
2. Edit the regex if it's too broad or too narrow — a bad pattern blocks legitimate commands
3. Create `traumas/active/T00N-short-title.md`:

```
---
id: T001
title: Force push to main
severity: critical
pattern: "git push.*--force.*(main|master)"
rationale: What went wrong, in one sentence.
recovery: How to recover or prevent, in one sentence.
created: YYYY-MM-DD
source_diary: diary-YYYY-MM-DD-project
---
```

Note: `rationale` and `recovery` must be in frontmatter (not body) — the Trauma Guard hook reads them from there to include in its warning output.

4. Delete the entry from this file after promoting
5. Delete false positives — if the LLM extracted a pattern that doesn't reflect a real failure, just remove it

---

<!-- Extracted trauma candidates appear below this line -->
