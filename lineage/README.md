# lineage

`lineage` automatically attaches coding-session transcripts (your conversation with AI coding agent) to commits using `git notes`, so you can trace generated code back to its prompt/session history without changing commit messages.

## What it does

- Installs `post-commit` and `post-rewrite` hooks in a target repository.
- Runs an **extractor script to that you need to implement** after each commit.
- Validates extractor output as JSON.
- Stores that JSON as a note under a dedicated notes ref (default: `refs/notes/lineage`).
- Preserves notes across rewritten history (for example, amend and rebase).

The default extractor is a stub. To make lineage work you'll need to implement extractor script that works for your specific setup. It should be capable of finding logs for the right coding session, remove all sensitive information from logs, and print result to stdout.

## Installation

From this project directory:

```bash
./install.sh /path/to/target/repo
```

Optional flags:

```bash
./install.sh /path/to/target/repo \
  --extractor /absolute/path/to/your/extractor.sh \
  --notes-ref refs/notes/lineage \
  --force
```

`--force` rotates conflicting hook backups if both `<hook>` and `<hook>.pre-lineage` already exist.

## How hooks behave

- `post-commit`: captures session JSON and writes/updates a note for `HEAD`, except while rewrite operations are in progress (`rebase`, `cherry-pick`, `revert`).
- `post-rewrite`: copies existing lineage notes from rewritten commits to new commit IDs, and falls back to fresh capture if no old note exists.

Hook failures do not block git operations; they are logged to:

```text
.git/lineage/lineage.log
```

## Repo-local configuration keys

`install` writes these keys into the target repo's local git config:

- `lineage.extractorPath`: script path used to extract sanitized transcript JSON.
- `lineage.notesRef`: notes ref where lineage notes are stored.
- `lineage.installedBy`: source installation path for this tool.
- `notes.displayRef` includes the lineage notes ref.

`lineage` intentionally removes its notes ref from `notes.rewriteRef` (if present) to avoid duplicate/merged note payloads during `--amend` rewrites; rewrite preservation is handled by the `post-rewrite` hook.

## Common commands

Show lineage note for latest commit:

```bash
git notes --ref refs/notes/lineage show HEAD
```

Show commits with lineage notes:

```bash
git log --show-notes=refs/notes/lineage
```

Attach manually (without hooks):

```bash
/absolute/path/to/lineage/bin/lineage attach HEAD --event manual
```

## Sharing notes with remotes

Notes are not always pushed by default. Push/fetch explicitly:

```bash
git push origin refs/notes/lineage
git fetch origin refs/notes/lineage:refs/notes/lineage
```

## Security model

- `lineage` assumes your extractor script already removes sensitive data.
- `lineage` only validates that extractor output is syntactically valid JSON.
- Note content is stored as-is from extractor output.
