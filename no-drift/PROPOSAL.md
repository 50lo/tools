# no-drift: Python implementation proposal

Status: proposal only; no implementation yet.

## Recommendation

Build a small, standard-library-only Python CLI that records explicit documentation-to-code bindings and reports when their targets change. Keep the useful workflow from [fiberplane/drift](https://github.com/fiberplane/drift): `link`, `check` (`lint` alias), `status`, `unlink`, and `refs`, plus an explicit review requirement before refreshing stale bindings.

Use **Python 3.12.8** for development and validation. On this computer, `mise ls` listed only Python 3.12.8; `mise exec python@3.12.8 -- python --version` confirmed it. Require Python 3.12 or newer initially and use no third-party packages. Python availability alone does not guarantee this version: machines with older system Python need an appropriate interpreter. Run with `python3 no_drift.py`, or install a symlink named `no-drift` to an executable script with a `#!/usr/bin/env python3` shebang.

This is a deliberately smaller implementation, not a drop-in replacement for upstream. It retains the binding/check/review workflow, Python syntax-aware fingerprints and Python declaration anchors. It initially omits syntax-aware parsing for other languages, Markdown sections and automatic Markdown link validation. If multi-language symbol anchors are essential, a dependency-free implementation will not provide equivalent functionality; use tree-sitter rather than inventing parsers.

## What upstream actually does

Inspected a temporary clone at `/private/tmp/fiberplane-drift.w4MJ13`, revision `fc90540acb1a3f15ab3c90b4c8c9bac16c7a6522`. Findings below describe that revision, not a promise about future upstream releases. The Zig application files under `src/` and `src/commands/` total about 4,050 lines, excluding the payload modules, tests, vendored parser code and language grammars. The idea is small; full feature parity is substantially larger.

1. `link` stores a doc path, target path with optional `#Symbol`, and fingerprint in a versioned TOML `drift.lock`. It fingerprints files on disk, including uncommitted changes.
2. `check` recomputes fingerprints and compares each binding independently. Missing files, missing symbols and absent signatures fail checking. Git history is unnecessary for the comparison.
3. For TypeScript/JavaScript, Python, Rust, Go, Zig and Java, it uses tree-sitter grammars and declaration queries. It hashes node types, structure and leaf text using XxHash3, excluding source positions and layout. Unsupported file types use raw bytes. This is the main cost of reproducing it faithfully. Comments are not explicitly discarded by its traversal; don't assume its normalization ignores comments.
4. Markdown targets can name a heading section, resolved through a Markdown parser. Whole Markdown files are actually hashed as bytes in `fingerprintDocumentSyntax`, despite broader wording about syntax fingerprints in the design document.
5. It also checks relative Markdown links. The check discovers tracked and non-ignored untracked `.md` files through `git ls-files`, including docs with no bindings, then adds explicitly bound docs. It skips discovery beneath nested lockfiles. Broken-link checking therefore has a wider reach than simply checking registered docs.
6. Refreshing an existing, changed signature requires review. A terminal can prompt; non-interactive callers must use `--doc-is-still-accurate`. Editing the doc alone does **not** satisfy this gate: an integration test explicitly covers that case.
7. Other features include origin-qualified cross-repo bindings, nested lockfile discovery, JSON output with a published schema, `--changed` path-prefix filtering, `--silent`, best-effort Git change attribution, parallel checking, and installer/release automation.

Two documentation/source mismatches matter:

- The README advertises automatically stamping inline `@./path#Symbol` references. The inspected link command handles an explicit target or refreshes existing bindings; I found no inline-reference extraction in source or tests. Do not treat that advertised behavior as verified functionality.
- The design document describes `.drift/config.yaml` and automatic Jujutsu selection. I found no config reader, and `detectVcs()` explicitly returns Git. Those are not requirements for our implementation.

A fresh signature means “the recorded target has not changed since someone acknowledged this binding.” Neither tool can determine whether the prose accurately describes the code, whether a doc is complete, or whether omitted dependencies affect a symbol. An agent can still acknowledge an inaccurate doc. The gate adds explicit accountability, not semantic verification.

## Proposed first version

### Commands and review workflow

```sh
no-drift link docs/auth.md src/auth.go
no-drift link docs/api.md 'src/client.py#Client.connect'
no-drift check
no-drift refs src/client.py
no-drift status

# After reviewing and, if necessary, editing the documentation:
no-drift link docs/auth.md -a

no-drift unlink docs/auth.md src/auth.go
```

- `link DOC TARGET`: create or refresh one binding. Doc and target must exist and be regular files. Initially restrict docs to `.md` files. New bindings need no acknowledgement. A changed existing target requires `--ack` (short form `-a`), meaning “I reviewed the documentation and acknowledge this refresh”; unchanged bindings are a no-op. No interactive prompt in version one.
- `link DOC`: refresh every existing binding for that doc. Resolve and validate all targets first; if any target fails or any stale binding lacks acknowledgement, leave the entire lockfile unchanged. No implicit discovery of references in prose.
- `check` / `lint`: report fresh and stale bindings grouped by doc, with actionable reasons. Missing/unreadable docs also fail. Never write the lockfile. With no lockfile or no bindings, print “no bindings checked” and exit 0; this explicitly provides no coverage.
- `status`: list recorded bindings without recomputing freshness.
- `unlink DOC TARGET`: remove exactly that binding; report a missing binding as an error. Allow removing bindings whose files no longer exist.
- `refs FILE`: return all docs bound to that file, including its Python symbols. `refs FILE#SYMBOL` matches that exact symbol. Return sorted unique paths, exit 0 even with no matches. Upstream currently matches exact targets only; broader file lookup is a small intentional improvement.
- `check --changed PATH`: select bindings whose target is exactly PATH or below that directory, respecting path-component boundaries. It is a filter supplied by the caller, not automatic Git diff detection. Check all bindings of each selected doc. Full checking remains the normal CI invocation.
- Exit 0 on successful commands/fresh checks, 1 on stale or unresolved check results, 2 on usage, malformed lockfile or command execution errors. Deterministic plain text initially; no upstream JSON schema compatibility.

### Repository and path rules

Use one `no-drift.lock` per repository, located at the Git root. Locate it by walking ancestors for a `.git` file or directory; this also supports Git worktrees without invoking Git. Stop there and ignore any lockfile above the repository. Outside Git, use the nearest ancestor `no-drift.lock`, or cwd for first creation. Do not recursively discover other scopes in version one.

CLI paths are relative to cwd; persisted paths are relative to the lockfile directory, using `/` separators. Do not use upstream's “cwd if it exists, otherwise root” fallback, which changes meaning when files disappear. Normalize paths consistently even for missing files so `unlink` and `refs` remain usable. Keep bindings within the selected root, including symlink resolution. Reject external/absolute persisted paths rather than introducing cross-repository behavior. Spaces and Unicode paths work; reserve `#` as the symbol separator and reject filenames containing it.

### Fingerprints

Use SHA-256 from `hashlib`, storing the full digest and an explicit fingerprint mode per binding.

| Target | Proposed fingerprint | Consequence |
| --- | --- | --- |
| Python file | `ast.parse`, then `ast.dump(..., annotate_fields=True, include_attributes=False)` | Formatting and comments ignored; docstrings and syntax changes count. |
| Python declaration | AST dump of the selected function, async function or class, including its decorators | Changes elsewhere in the file do not count; inherited/global dependencies require additional bindings. |
| All other files, including Markdown | Exact file bytes | Every byte change counts, including formatting, comments and line endings. |

Python anchors support top-level names such as `#connect` and qualified class members such as `#Client.connect`. Limit selection to module/class declaration bodies, reject ambiguous repeated names, and omit local functions and variable/type-alias anchors initially. Missing declarations and invalid Python syntax produce explicit failures; never silently replace a symbol anchor with a whole-file fingerprint. Unsupported languages with `#Symbol` are rejected at link time.

Store modes such as `bytes-sha256-v1` and `python-ast-sha256-v1`. Include the Python AST parser's minor version in AST bindings; reject mismatched parser versions with an actionable diagnostic rather than claiming compatibility. Develop with 3.12.8 and support other 3.12 patch releases; using 3.13+ can run byte bindings, but AST bindings created on 3.12 require deliberately rebuilding their baseline with that interpreter. This prevents Python grammar/AST changes from silently redefining old signatures. Parser changes are an explicit review event.

Do not strip whitespace or comments from Go/TypeScript using regex. That can alter strings or significant syntax and cause missed changes. Raw hashing is conservative and honest: in a Go-heavy repository it will be noisier than upstream and cannot provide Go symbol anchors.

### Lockfile

Use versioned JSON in `no-drift.lock`, distinct from upstream's TOML `drift.lock`. Both reading and writing then use Python's standard library; no TOML writer or custom parser is needed.

```json
{
  "version": 1,
  "bindings": [
    {
      "doc": "docs/auth.md",
      "target": "src/auth.go",
      "mode": "bytes-sha256-v1",
      "sig": "<64 lowercase hexadecimal characters>"
    }
  ]
}
```

The signature above is a placeholder, not a valid saved binding. Python AST entries additionally contain `python_minor: "3.12"`.

Validate schema version, required fields, field types, modes, digests and duplicate `(doc, target)` identities. Sort bindings by doc/target and use stable indented JSON with a trailing newline. Write a temporary file beside the lockfile and replace it with `os.replace` after all validations succeed. No daemon, database, write concurrency framework or legacy format migration. Users should serialize modifying commands; checks are read-only. Commit the lockfile alongside documentation and code.

Existing upstream signatures are incompatible: different parsers, normalization and hash algorithms. Do not import or restamp them automatically. Add selected bindings explicitly after reviewing their docs.

## Complexity to leave out

| Feature | Recommendation | What is lost |
| --- | --- | --- |
| Multi-language tree-sitter and queries | Omit initially | Non-Python files get byte hashes; no Go/TS/Rust/etc. symbol selection or formatting immunity. |
| Markdown heading anchors and broken-link checking | Omit initially | Bind whole docs instead; dead Markdown links aren't checked. A regex replacement would have misleading coverage. |
| Automatic inline bindings | Omit | Explicit CLI bindings remain the source of truth. |
| Cross-repo `origin` and nested scopes | Omit | One repository/root per invocation; no automatic cross-repo skipping. |
| Git blame and historical blob subprocesses | Omit | Reports explain the mismatch; use Git separately to investigate authorship. |
| Published JSON payload schema and silent-mode variants | Defer | Plain text plus exit status handles shell and CI use. |
| Parallelism and parser caches across runs | Omit | Sequential work with an in-memory per-run file/AST cache; optimize only if actual use is slow. |
| GitHub setup action, shell installer and release binaries | Omit | Run/copy one Python script and use ordinary CI commands. |
| Legacy lockfile upgrades, Jujutsu helpers and YAML config | Omit | No compatibility or configuration framework to maintain. |

If language-aware Go/TypeScript support becomes necessary, add tree-sitter and only the grammars actually used. Pin parser versions and record the fingerprint mode. That introduces package installation and native parser dependencies, so it should be a deliberate second step rather than part of this portable first version.

## Small implementation layout and validation

```text
no-drift/
  PROPOSAL.md           # this proposal
  README.md             # usage, installation and limitations
  no_drift.py           # CLI, lockfile I/O, fingerprints and command functions
  tests/
    test_no_drift.py    # standard-library unittest, temporary repositories/files
```

Aim for one straightforward script of roughly 400–600 lines plus behavioral tests, not a plugin architecture. This is a planning estimate; don't sacrifice clarity to a line limit. Use `argparse`, `pathlib`, `json`, `hashlib`, `ast`, `tempfile` and `os`. No packaging is needed for direct execution. A short README should explain the workflow to humans and coding agents; no installed skill is required.

Acceptance tests should demonstrate: fresh after linking; stale on an uncommitted target change; Python formatting/comments stay fresh; docstrings/code/decorators change fingerprints; another method does not stale a method anchor; missing/ambiguous symbols and invalid Python fail; missing docs/targets fail; stale relink requires explicit review even after doc edits; `--ack` and `-a` both acknowledge targeted and blanket refreshes; blanket refresh failure leaves lockfile bytes unchanged; duplicate/malformed state is rejected; subdirectory invocation and paths with spaces work; `unlink` works after deletion; file `refs` includes symbol bindings; changed-path filtering doesn't match unrelated prefixes; unknown parser versions/modes fail clearly; an empty check reports no coverage.

Run with `mise exec python@3.12.8 -- python -m unittest discover -s no-drift/tests`. Exercise the CLI in isolated temporary directories without modifying real repos. After implementation, manually run the documented link/change/check/review workflow on macOS and Linux. No external services or compiler are needed.

## Source references

All links below are pinned to the inspected revision:

- [README](https://github.com/fiberplane/drift/blob/fc90540acb1a3f15ab3c90b4c8c9bac16c7a6522/README.md): advertised workflow and inline references.
- [CLI reference](https://github.com/fiberplane/drift/blob/fc90540acb1a3f15ab3c90b4c8c9bac16c7a6522/docs/CLI.md): extra command flags and nested scopes.
- [Fingerprint implementation](https://github.com/fiberplane/drift/blob/fc90540acb1a3f15ab3c90b4c8c9bac16c7a6522/src/symbols.zig) and [dependencies](https://github.com/fiberplane/drift/blob/fc90540acb1a3f15ab3c90b4c8c9bac16c7a6522/build.zig.zon): parser languages, traversal and hashes.
- [Check implementation](https://github.com/fiberplane/drift/blob/fc90540acb1a3f15ab3c90b4c8c9bac16c7a6522/src/commands/lint.zig): doc discovery, target checking, filtering and concurrency.
- [Link implementation](https://github.com/fiberplane/drift/blob/fc90540acb1a3f15ab3c90b4c8c9bac16c7a6522/src/commands/link.zig) and [link tests](https://github.com/fiberplane/drift/blob/fc90540acb1a3f15ab3c90b4c8c9bac16c7a6522/test/integration/link_test.zig): review gate and all-doc refresh.
- [Markdown implementation](https://github.com/fiberplane/drift/blob/fc90540acb1a3f15ab3c90b4c8c9bac16c7a6522/src/markdown.zig), [VCS implementation](https://github.com/fiberplane/drift/blob/fc90540acb1a3f15ab3c90b4c8c9bac16c7a6522/src/vcs.zig) and [lockfile implementation](https://github.com/fiberplane/drift/blob/fc90540acb1a3f15ab3c90b4c8c9bac16c7a6522/src/lockfile.zig): verified details beyond the design document.

Upstream is MIT-licensed. Implement this proposal independently; retain upstream license notices if any source or substantial portions of documentation are copied.
