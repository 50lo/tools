# Curator — Markdown-first procedural memory for coding agents

Curator is a personal, file-based memory system for coding agents. It gives Claude Code persistent knowledge across sessions: what patterns work, what to avoid, and what commands have caused harm in the past. All data lives in plain Markdown files with YAML frontmatter — no database, no server, no dependencies beyond Python and the Anthropic SDK.

Built around three ideas from cognitive science adapted for agents:

- **Working memory (diary):** Structured session summaries written after each coding session.
- **Procedural memory (playbook):** Distilled rules and anti-patterns with confidence scores that decay over time.
- **Trauma Guard:** A blocklist of dangerous command patterns, extracted from documented failures and enforced by a Claude Code `PreToolUse` hook.


## Directory layout

```
curator/
  README.md                   # this file — read when you need a refresher
  CLAUDE.md                   # snippet to include in project CLAUDE.md files

  playbook/                   # one .md file per rule or anti-pattern
  diary/                      # one .md file per coding session

  traumas/
    active/                   # one .md file per active trauma (enforced by pre-tool-use hook)
    pending.md                # trauma candidates from reflection — review before promoting

  scripts/
    maintain.py               # weekly: recompute scores, update maturity, invert anti-patterns
    feedback.py               # mark a rule helpful or harmful after a session
    reflect.py                # LLM reflection: extract rules + traumas from new diary entries
    search.py                 # search playbook by keyword and score

  templates/
    diary-entry.md            # blank diary template
    rule.md                   # blank rule template (for manual rule creation)

  hooks/
    pre-tool-use.py           # Trauma Guard: blocks/warns on dangerous commands
    stop.py                   # post-session: creates diary template if none written today
```


## Data models

### Rule (`playbook/r-XXXXXX.md`)

```yaml
---
id: r-8f3a2c
title: Short rule title
category: testing       # debugging|testing|architecture|workflow|documentation
                        # |integration|git|security|performance|general
type: rule              # rule | anti-pattern
maturity: candidate     # candidate | established | proven | deprecated
helpful_count: 0
harmful_count: 0
effective_score: 0.5    # computed by maintain.py — do not edit manually
confidence_decay: 1.0   # computed by maintain.py — do not edit manually
last_validated: 2026-04-23
created: 2026-04-23
tags: [python, testing]
sources: []             # diary session_ids that support this rule
---

Rule text: one clear, actionable sentence.

## Context

When this rule applies and what preconditions trigger it.

## Evidence

Notes from specific sessions where this rule proved correct or incorrect.
```

### Diary entry (`diary/YYYY-MM-DD-project-slug.md`)

```yaml
---
date: 2026-04-23
project: my-project
agent: claude-code
session_id: diary-2026-04-23-my-project
processed: false        # set to true by reflect.py after extraction
---
```

Body uses fixed sections (see `templates/diary-entry.md`). The `## Failures` section is the most important — it drives trauma pattern extraction.

### Trauma (`traumas/active/T001-title.md`)

```yaml
---
id: T001
title: Force push to main
severity: critical      # low | medium | high | critical
pattern: "git push.*--force.*(main|master)"   # Python regex matched against Bash commands
rationale: Rewrites shared history and causes data loss for other developers.
recovery: Use --force-with-lease as a last resort. Coordinate with team first.
created: 2026-04-23
source_diary: diary-2026-04-23-my-project
---
```

`rationale` and `recovery` live in frontmatter so the Trauma Guard hook can include them in its output. The body is optional — add prose notes there if useful for human review.


## Confidence math

```
# Time-based decay — 90-day half-life
confidence_decay = 0.5 ^ (days_since_last_validated / 90)

# Feedback ratio — 4× asymmetry for harmful marks
if helpful_count + harmful_count == 0:
    feedback_ratio = 0.5
else:
    feedback_ratio = helpful_count / (helpful_count + harmful_count × 4)
    feedback_ratio = clamp(0.0, 1.0)

# Combined score
effective_score = confidence_decay × feedback_ratio
```

**Intuition:** One harmful mark cancels four helpful marks. A rule not revalidated for 90 days loses half its weight. Both factors decay independently — a rule can be universally praised but become low-confidence if nobody uses it for months.


## Maturity thresholds

Enforced automatically by `maintain.py`:

| Maturity | Condition |
|---|---|
| `candidate` | helpful_count < 3 |
| `established` | helpful_count ≥ 3 AND effective_score ≥ 0.3 |
| `proven` | helpful_count ≥ 10 AND effective_score ≥ 0.5 |
| `deprecated` | harmful_count ≥ helpful_count × 2 (auto) OR set manually |

**Anti-pattern inversion:** when `harmful_count` reaches 3 and `type` is `rule`, `maintain.py` automatically sets `type: anti-pattern` and prepends `AVOID:` to the title. Edit the resulting text to make the warning more specific.


## Trauma Guard severity

The `pre-tool-use.py` hook behavior depends on severity:

| Severity | Behavior |
|---|---|
| `critical` / `high` | Blocks the command. Claude sees the warning and cannot proceed. |
| `medium` / `low` | Warns but allows. Claude sees the warning and can override with judgment. |


## Workflows

### Session start — load context

Before starting any non-trivial task, run:

```bash
python curator/scripts/search.py "your task description"
```

Returns matching rules sorted by score. Read them before proceeding. Claude Code does this automatically if the `CLAUDE.md` snippet is in your project.

### Session end — write diary

After any session that's non-trivial (> ~30 min or involving real decisions), write a diary entry. Claude Code's stop hook creates a template automatically at `curator/diary/YYYY-MM-DD-project.md`. Fill it in — or ask Claude to fill it in at the start of the next session using `transcript_path` from the hook.

The `## Failures` section is the most important part. If any command caused data loss, required a rollback, broke something, or wasted significant time — document the exact command, what broke, and how it was recovered. This is the primary sensor for trauma pattern extraction.

### Reflection — extract rules and traumas

Run after accumulating a few diary entries (weekly or on demand):

```bash
python curator/scripts/reflect.py
```

Reads all diary entries with `processed: false`, calls the Claude API, and outputs:
- Rule candidates written to `playbook/` with `maturity: candidate`
- Trauma candidates appended to `traumas/pending.md`
- Processed diary entries marked `processed: true`

**Requires** `ANTHROPIC_API_KEY` in your environment.

### Review pending traumas (manual)

Open `traumas/pending.md` after reflection. For each entry:
1. Verify the pattern accurately describes a real danger you experienced
2. Edit the Python regex if it's too broad or too narrow
3. Create `traumas/active/T00N-short-title.md` using the format in the Data models section
4. Delete the entry from `pending.md`

False positives (e.g., the LLM hallucinated a failure that didn't happen) — just delete them.

### Feedback — mark rules helpful or harmful

After a session where a specific rule guided a decision:

```bash
python curator/scripts/feedback.py r-8f3a2c helpful
python curator/scripts/feedback.py r-8f3a2c harmful
```

Updates counts, recomputes `effective_score`, updates `last_validated`.

### Maintenance — weekly decay pass

```bash
python curator/scripts/maintain.py
```

Recomputes `confidence_decay` and `effective_score` for all rules. Promotes maturity where thresholds are met. Inverts rules with `harmful_count ≥ 3` to anti-patterns. Deprecates rules where `harmful_count ≥ helpful_count × 2`. Prints a summary of changes.

Run with `--dry-run` to preview without writing.

### Review candidates (manual)

After reflection, look at new rules:

```bash
python curator/scripts/search.py --maturity candidate
```

Edit rule text to be more specific or actionable. Mark helpful/harmful as you use them. Delete rules that don't belong.

### Onboard known patterns (manual)

When starting fresh, don't wait for the system to discover patterns you already know. Manually create a few rules in `playbook/` using `templates/rule.md`. Set `maturity: established` or `proven` for things you're confident about. Set `helpful_count` to reflect your experience level.


## Claude Code integration

### 1. Install hooks

Add to your project's `.claude/settings.json` (or global `~/.claude/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python /absolute/path/to/curator/hooks/pre-tool-use.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python /absolute/path/to/curator/hooks/stop.py"
          }
        ]
      }
    ]
  }
}
```

Use absolute paths — hooks run from varying working directories.

### 2. Include CLAUDE.md in your project

Copy the contents of `curator/CLAUDE.md` into your project's `CLAUDE.md` (or the global `~/.claude/CLAUDE.md`). Update the path to match where `curator/` lives relative to your project root.


## Manual workflows (cannot be automated)

**Promoting traumas.** `reflect.py` cannot verify that an extracted pattern is genuinely dangerous or that the regex is correct. Always review `pending.md` before promoting to `active/`. A too-broad regex blocks legitimate commands.

**Retiring rules.** Set `maturity: deprecated` manually when a rule no longer applies (framework change, changed workflow, etc.). `maintain.py` skips deprecated rules.

**Tuning inverted anti-patterns.** When `maintain.py` auto-inverts a rule, the title gets a mechanical `AVOID:` prefix. Edit it to explain the specific failure mode and recovery path.

**Seeding with known knowledge.** The system only learns from sessions you record. Seed the playbook manually with patterns you already know — otherwise it starts cold and takes many sessions to become useful.

**Resolving rule conflicts.** If two rules give contradictory guidance, `maintain.py` won't detect this — it works per-file. Review the playbook periodically and either merge or deprecate conflicting rules.


## How retrieval works (and when to upgrade)

During a session, `search.py` surfaces relevant rules by scoring each playbook file:

```
combined_score = keyword_match_count × effective_score
```

`keyword_match_count` is the number of query tokens (words) found anywhere in the rule's title, category, tags, and body. Results are sorted by combined score and truncated to `--limit` (default 10).

This works well for a small playbook. The failure mode is vocabulary mismatch: a rule titled "use `-x` for fail-fast test execution" won't surface for the query "debugging slow test suite" because the keywords don't overlap, even though the rule is directly relevant.

**Upgrade path: qmd.** Once the playbook grows past ~50–100 rules and you notice relevant rules being missed, swap in [qmd](https://github.com/tobias-theobald/qmd) — an all-local CLI that runs BM25 + vector search (via node-llama-cpp / GGUF models) over markdown files. The playbook files work as-is; qmd indexes the same directory `search.py` already reads.

```bash
# Install qmd (requires Node.js)
npm install -g qmd

# Use in place of search.py
qmd search "debugging slow test suite" --path curator/playbook
```

Post-processing to weight results by `effective_score` would require a small wrapper script, but plain qmd output is already useful as a drop-in. At that point `search.py` can stay as a fallback for machines without Node.js.

For most playbooks under a few hundred rules, `search.py` is sufficient and has no extra dependencies.


## Dependencies

```bash
pip install anthropic   # for reflect.py only — all other scripts use stdlib
```

Python 3.8+ required (uses `pathlib`, `datetime.date.fromisoformat`).
