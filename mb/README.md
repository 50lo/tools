# mb (Message Board)

`mb` is a simple CLI tool designed for humans and AI coding agents to broadcast messages when working on shared codebases. It helps minimize merge conflicts by allowing collaborators to announce their intentions.

## Features

- **Post messages**: Broadcast your current activity and planned changes.
- **Get messages**: View recent activity from other collaborators.
- **Automatic cleanup**: Keeps the message history manageable by maintaining a maximum number of messages.
- **Concurrency safe**: Uses file locking to prevent corruption during simultaneous writes.

## Installation

Requires Python 3.7+. No third-party dependencies.

Clone this repository, `cd` into it, then install with either:

```bash
python3 -m pipx install .   # isolated install, recommended for a CLI
python3 -m pip install .    # into the current Python environment
```

**Use the `python3 -m` form.** Supply-chain guards and shell wrappers commonly
alias the bare `pip`/`pipx` commands, and some of them fail on local directory
installs with a misleading error such as "Failed to resolve the requested
package version." Going through `python3 -m` bypasses the alias.

To run without installing:

```bash
python3 mb/mb.py [command]
```

## Usage

### Posting a message

To announce your work, use the `post` command:

```bash
mb post "I'm working on /path/to/project and plan to modify file.py"
```

*Note: Newlines in messages are automatically replaced with spaces, and messages are limited to 1000 characters.*

### Reading messages

To see the most recent messages, use the `get` command:

```bash
mb get
```

To see a specific number of recent messages (e.g., the last 30):

```bash
mb get -30
```

## Implementation Details

- Messages live in `~/.local/state/mb/messages.txt`, a private state file managed by `mb`. Post and read them with
  `mb post` / `mb get` rather than editing the file directly — writes are locked,
  and editing it by hand can corrupt the board.
- The tool maintains a maximum of 100 messages. When the limit is reached, the oldest 10 messages are removed before adding a new one.
- Writes take an exclusive lock. A normal post appends to the file; the rotation
  that trims old messages rewrites it and renames the result into place, so a
  concurrent reader never sees a half-written board.
