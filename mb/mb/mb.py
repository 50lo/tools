import argparse
import datetime
import os
import pathlib
import sys
import fcntl

DATA_DIR = pathlib.Path.home() / ".local" / "state" / "mb"
DATA_FILE = DATA_DIR / "messages.txt"
LOCK_FILE = DATA_DIR / "messages.lock"
MAX_LINES = 100
LINES_TO_REMOVE = 10
MAX_MESSAGE_LENGTH = 1000

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def sanitize_message(message: str) -> str:
    # Replace newlines and carriage returns with spaces
    sanitized = message.replace('\n', ' ').replace('\r', ' ')
    # Truncate to MAX_MESSAGE_LENGTH
    return sanitized[:MAX_MESSAGE_LENGTH]

def post_message(message: str):
    ensure_data_dir()
    sanitized_message = sanitize_message(message)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"{timestamp} {sanitized_message}"

    # Use a lock file to prevent race conditions
    with open(LOCK_FILE, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        
        # Read existing lines
        lines = []
        if DATA_FILE.exists():
            with open(DATA_FILE, "r") as f:
                lines = f.readlines()
        
        # If file grows over 100 lines, remove first 10 lines before adding new message
        # The requirement says: "when files grows over 100 lines - mb removes first 10 lines before adding new message"
        # This implies if len(lines) + 1 > 100, we remove 10.
        if len(lines) >= MAX_LINES:
            # Rotating rewrites the whole file, so build it in a temp file and
            # rename it into place: a reader sees the old file or the new one,
            # never a truncated one.
            lines = lines[LINES_TO_REMOVE:]
            lines.append(formatted_message + "\n")
            tmp_file = DATA_FILE.with_suffix(".tmp")
            with open(tmp_file, "w") as f:
                f.writelines(lines)
            os.replace(tmp_file, DATA_FILE)
        else:
            # Common case: a plain append. One short write under the lock, so a
            # reader sees the whole line or none of it, and the file keeps its
            # identity so "tail -f" keeps following it.
            with open(DATA_FILE, "a") as f:
                f.write(formatted_message + "\n")

        # Release lock happens automatically when lock_f is closed

def get_messages(count: int):
    if not DATA_FILE.exists():
        return

    # "mb get -30" reaches us as -30, so treat the count as a magnitude.
    count = abs(count)
    if count == 0:
        return

    with open(DATA_FILE, "r") as f:
        lines = f.readlines()

    # Get the last N messages
    recent_messages = lines[-count:]
    for msg in recent_messages:
        print(msg.strip())

def main():
    parser = argparse.ArgumentParser(description="Message Board (mb) - A simple CLI tool to broadcast messages for humans and AI agents.")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Post command
    post_parser = subparsers.add_parser("post", help="Post a new message")
    post_parser.add_argument("message", type=str, help="The message to post")

    # Get command
    get_parser = subparsers.add_parser("get", help="Get recent messages")
    get_parser.add_argument("count", type=int, nargs='?', default=10, help="Number of messages to retrieve (default: 10)")

    args = parser.parse_args()

    if args.command == "post":
        post_message(args.message)
    elif args.command == "get":
        get_messages(args.count)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
