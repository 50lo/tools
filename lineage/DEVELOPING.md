# DEVELOPING

This document describes internals, failure handling, and extension points for `lineage`.

## Project layout

- `bin/lineage`: main CLI and hook harness.
- `scripts/extract-session-stub.sh`: default extractor stub that returns JSON.
- `install.sh`: convenience wrapper for `lineage install`.

## CLI commands

- `lineage install`: installs hook wrappers and config into a target repo.
- `lineage hook post-commit`: called by git hook after each commit.
- `lineage hook post-rewrite`: called by git hook after amend/rebase/cherry-pick rewrites.
- `lineage attach`: manual note attachment for a specific commit.

## Hook installation strategy

Installer resolves hooks directory from:

1. `core.hooksPath` if configured
2. otherwise `<git-dir>/hooks`

For each managed hook (`post-commit`, `post-rewrite`):

- If existing hook is not lineage-managed, move it to `<hook>.pre-lineage`.
- If conflict exists with an existing `.pre-lineage` backup, installation fails unless `--force` is used.
- Wrapper executes legacy hook first (if present), then lineage hook logic.
- Wrapper always exits success to avoid blocking git workflows after commit/rewrite completion.
- Installer removes lineage's notes ref from `notes.rewriteRef` (if present) to avoid duplicate note merge behavior during amend/rebase.

## Note attachment flow

`post-commit` flow:

1. Resolve `HEAD`.
2. Skip capture if rewrite is in progress (`rebase-merge`, `rebase-apply`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`).
3. Resolve extractor path (`lineage.extractorPath`, fallback to stub).
4. Call extractor with context in env vars:
   - `LINEAGE_REPO_ROOT`
   - `LINEAGE_COMMIT`
   - `LINEAGE_EVENT`
5. Validate output as JSON (`jq`, `python3`, `python`, then basic fallback).
6. Write note to `lineage.notesRef` (default `refs/notes/lineage`) with `git notes add -f`.

`post-rewrite` flow:

1. Read old/new commit pairs from stdin.
2. Copy lineage note from old commit to new commit when new note does not already exist.
3. If old commit has no lineage note, generate one for the new commit via extractor fallback.
4. Log summary metrics (processed/copied/generated/skipped/failed).

Rewrite preservation is intentionally implemented in hook logic instead of `notes.rewriteRef` to avoid combining old and new payloads when both notes already exist.

## Failure modes considered

- Missing or non-executable extractor script: log warning/error, skip note write.
- Extractor non-zero exit: warning + repo log, no note write.
- Empty extractor output: warning + repo log.
- Invalid JSON output: warning + repo log.
- Lock contention (`.git/lineage.lock`) during note attachment: bounded retries, then skip with warning.
- Existing hook conflicts on install: explicit error unless `--force`.
- Notes ref misconfiguration: fallback to default and warning.
- Existing identical note content: no-op update.
- Rebase/cherry-pick note churn: prevented by skipping `post-commit` capture during rewrites and preserving lineage in `post-rewrite`.

All runtime diagnostics are appended to `.git/lineage/lineage.log` when possible.

## Updating the extractor

Point target repo to your real extractor:

```bash
git -C /path/to/repo config --local lineage.extractorPath /absolute/path/to/extractor.sh
```

Extractor contract:

- Input: environment variables listed above.
- Output: JSON on stdout.
- Exit code: non-zero on failure.

`lineage` stores stdout JSON as the note payload without additional transformation.

## Manual smoke test

From a repo where hooks are installed:

```bash
git commit --allow-empty -m "smoke: commit"
git notes --ref refs/notes/lineage show HEAD

git commit --amend -m "smoke: amend"
git notes --ref refs/notes/lineage show HEAD

git checkout -b lineage-smoke-base
git commit --allow-empty -m "base"
git checkout -b lineage-smoke-feature HEAD~1
git commit --allow-empty -m "feature"
git rebase lineage-smoke-base
git notes --ref refs/notes/lineage show HEAD
```

If needed, inspect log:

```bash
cat .git/lineage/lineage.log
```
