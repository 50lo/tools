# git-copy

A lightweight custom Git command for copying files or folders from another branch into your current working tree — without switching branches. This is especially useful when you want to grab a specific script, config, or directory from a feature branch.

---

## Installation

Run the installer from the project root:

```bash
./install
```

The installer copies the `git-copy` script to `~/bin/git-copy`. Make sure the
`~/bin` directory exists and is on your `PATH` (create it with `mkdir -p ~/bin`
and add `export PATH="$HOME/bin:$PATH"` to your shell profile if needed). After
installation you can verify things are wired up correctly with:

```bash
git copy --help
```

---

## Usage

```bash
git copy [--force] <branch> <source> [destination]
```

If `destination` is omitted, the file or folder is copied to the same path name in your current branch.

**Examples:**

Copy a single file:
```bash
git copy feature/new-cleanup src/scripts/cleanup.sh
```

Copy an entire folder:
```bash
git copy feature/tooling-updates src/utils
```

Copy and rename a file in one step:
```bash
git copy feature/new-cleanup src/scripts/cleanup.sh scripts/cleanup.sh
```

---

## Features

- Works with both files and folders
- Confirms before overwriting existing files (use `--force` to skip the prompt)
- Uses `git archive` internally for folders (fast and clean)
- Fully shell-based — no dependencies
- Safe: validates branches and paths before copying

---

## How it works

Internally, `git-copy` uses:

- `git show <branch>:<path>` for files  
- `git archive <branch> <folder>` for folders

So your working tree is updated without checking out another branch or touching your index.

---

## Example workflow

Let’s say you fixed a script on another branch and want it in your current one:

```bash
git copy tasks/fix-cleanup-script src/scripts/cleanup.sh
git add src/scripts/cleanup.sh
git commit -m "Update cleanup script from fix-cleanup-script branch"
```

---

## Uninstall

To remove:
```bash
rm -f ~/bin/git-copy
```

---

## Tech Stack

`git-copy` command implemented as a simple shell script. It only requires `bash` to run.
