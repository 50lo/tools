# no-drift

Bind Markdown documentation to code and flag targets that have changed since their last review. A small Python tool inspired by [fiberplane/drift](https://github.com/fiberplane/drift), with no third-party dependencies.

Requires **Python 3.12 or newer**, on macOS or Linux. Developed and tested with Python 3.12.8. Checking fingerprints uses files on disk, including uncommitted changes; it needs no Git history or Git executable.

## Run or install

From this tools repository:

```sh
python3 no-drift/no_drift.py --help
```

For use in other repositories, run the script by its absolute path, or put a symlink on your PATH. From the tools repository root:

```sh
mkdir -p "$HOME/.local/bin"
ln -s "$PWD/no-drift/no_drift.py" "$HOME/.local/bin/no-drift"
```

Ensure `~/.local/bin` is on PATH and `python3` selects a supported interpreter. No pip install, virtual environment, parser download or package build is needed. With mise, use `mise exec python@3.12.8 -- python /path/to/tools/no-drift/no_drift.py ...` to select the development interpreter explicitly.

## Workflow

In the repository whose documentation you want to track:

```sh
# Add a file binding or a Python declaration binding.
no-drift link docs/auth.md src/auth.go
no-drift link docs/api.md 'src/client.py#Client.connect'

no-drift check
no-drift status
no-drift refs src/client.py

# Review the documentation after the bound code changes, edit it if needed,
# then acknowledge and refresh every binding for that doc.
no-drift link docs/auth.md -a

# Or acknowledge and refresh just one binding.
no-drift link docs/api.md 'src/client.py#Client.connect' --ack

no-drift unlink docs/auth.md src/auth.go
```

`--ack` and `-a` mean “I reviewed the documentation and acknowledge this refresh.” New bindings need no acknowledgement. Refreshing a stale binding requires it even if you edited the doc. Unchanged refreshes do nothing. There are no interactive prompts.

`link DOC` refreshes all existing bindings for that doc. If any target cannot be resolved, or a stale binding lacks acknowledgement, the whole lockfile remains unchanged. `link DOC TARGET` changes only that binding.

`check` (also available as `lint`) reports each binding as `ok` or `STALE`. Missing or unreadable docs/targets, invalid Python, missing/ambiguous declarations, and Python parser mismatches fail checking. Editing a doc does not clear a stale target; you must review and refresh its bindings. `status` lists recorded bindings without checking them.

`refs FILE` includes docs bound to the whole file and any of its symbols. `refs FILE#SYMBOL` matches only that exact declaration. Results are sorted and deduplicated. `unlink` removes exactly one binding and works after the doc or target has been deleted.

### Scope and exit codes

```sh
no-drift check --changed src/auth.go
no-drift check --changed src
```

`--changed` is a caller-supplied file/directory filter, not automatic Git diff detection. It selects docs with targets at that path or beneath it, then checks **all bindings of each selected doc**. `src` does not match `src-old`. Run a full `no-drift check` for the normal CI gate.

- **0:** successful command or fresh check. An empty check prints `no bindings checked`; it provides no coverage. `refs` also exits 0 if no docs match.
- **1:** a check has stale or unresolved bindings.
- **2:** usage, malformed lockfile, failed link/unlink or other command execution error.

## Fingerprints and limitations

| Target | What changes its fingerprint |
| --- | --- |
| Python file | AST changes, including docstrings. Formatting and comments are ignored. |
| Python function, async function or class | Changes to that declaration's AST, including decorators and docstrings. |
| Any other file, including Markdown | Any byte change, including formatting, comments and line endings. |

Python declarations can use top-level names (`#connect`), class members (`#Client.connect`) or nested classes (`#Outer.Inner.run`). Only declarations directly inside a module or class are selected; local functions, assignments and type aliases are unsupported. Repeated matching names are ambiguous and fail rather than choosing one. Non-Python symbol anchors are rejected.

A declaration anchor does not track changes to its imports, globals, parent classes or other dependencies. Add separate file/declaration bindings where those matter. A fresh fingerprint only confirms that a target matches its reviewed baseline; the tool cannot verify whether the prose is accurate or complete.

Python AST bindings record the interpreter's minor version. A binding created on 3.12 can be checked with another 3.12 patch release; checking it with 3.13 or later reports a parser mismatch. Use the baseline interpreter, or review and relink with `-a` using the new interpreter. Byte bindings have no parser-version constraint.

There is no multi-language syntax normalization, Markdown heading selection, broken-link validation, inline-reference discovery, cross-repo origin handling, nested scopes, Git blame, JSON report or background service. This tool uses its own JSON lockfile; it cannot read upstream's TOML `drift.lock` or reuse upstream signatures.

## Paths and lockfile

Within Git, `no-drift.lock` lives at the nearest Git root (a `.git` file or directory identifies it, including worktrees). A lockfile outside that repository or in a nested directory is ignored. Outside Git, use the nearest ancestor lockfile, or create one in cwd when first linking.

CLI paths are relative to **cwd**, including when called from a subdirectory; there is no root-relative fallback. Paths within the lockfile are normalized relative to its directory. Absolute CLI paths are accepted if they resolve within the root. Paths and symlinks that resolve outside the root are rejected. Spaces and Unicode work; `#` is reserved for symbols and cannot be part of a filename.

The versioned JSON stores one unique `(doc, target)` binding with its fingerprint mode and SHA-256 digest. Python entries also store `python_minor`. Bindings are sorted for readable diffs. Malformed or unsupported state is rejected instead of overwritten. Writes replace the lockfile atomically after validation; modifying commands must be serialized. `check`, `status` and `refs` never write it.

Commit the lockfile alongside code and documentation. Bindings are explicit: an unbound doc or dependency is not checked.

## Structure and tests

- `no_drift.py`: CLI parsing, root/path handling, lockfile I/O, fingerprints and command functions. File bytes and parsed Python trees are cached for each invocation.
- `tests/test_no_drift.py`: standard-library unittest suite with disposable directories and subprocess CLI checks, plus injected read/write failures.
- `PROPOSAL.md`: original scope and upstream investigation.

From the tools repository root:

```sh
mise exec python@3.12.8 -- python -m unittest discover -s no-drift/tests -v
# Or with a supported Python already on PATH:
python3 -m unittest discover -s no-drift/tests -v
```
