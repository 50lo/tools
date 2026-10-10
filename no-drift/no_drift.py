#!/usr/bin/env python3
"""Record reviewed documentation-to-code bindings and check for changes."""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile

LOCKFILE = "no-drift.lock"
BYTES_MODE = "bytes-sha256-v1"
AST_MODE = "python-ast-sha256-v1"
HEADING_MODE = "markdown-section-sha256-v1"
PYTHON_MINOR = f"{sys.version_info.major}.{sys.version_info.minor}"
DECLARATIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class ToolError(Exception):
    """An actionable command or target-resolution failure."""


def resolve(path):
    try:
        return path.resolve()
    except (OSError, RuntimeError) as exc:
        raise ToolError(f"cannot resolve {path}: {exc}") from exc


def find_root(cwd):
    ancestors = (cwd, *cwd.parents)
    # A repository boundary takes priority over any nearer standalone lockfile.
    for directory in ancestors:
        git = directory / ".git"
        if git.is_file() or git.is_dir():
            return directory
    for directory in ancestors:
        lock = directory / LOCKFILE
        if lock.exists() or lock.is_symlink():
            return directory
    return cwd


def split_target(target):
    path, separator, symbol = target.partition("#")
    if not path or (separator and not symbol):
        raise ToolError(f"invalid target: {target!r}")
    if separator and PurePosixPath(path).suffix == ".md":
        symbol = heading_slug(symbol)
        if not symbol:
            raise ToolError("Markdown heading fragment must not be empty after normalization")
    elif separator and not all(part.isidentifier() for part in symbol.split(".")):
        raise ToolError(f"invalid Python symbol: {symbol!r}")
    return path, symbol if separator else None


def heading_slug(text):
    text = re.sub(r"[^\w\s-]", "", text.casefold())
    return re.sub(r"[\s-]+", "-", text).strip("-")


def markdown_lines(content):
    """Yield byte offsets and lines outside ordinary backtick/tilde fences."""
    offset = 0
    fence = None
    for raw in content.splitlines(keepends=True):
        try:
            line = raw.decode("utf-8").rstrip("\r\n")
        except UnicodeError as exc:
            raise ToolError("Markdown must be UTF-8") from exc
        if offset == 0:
            line = line.removeprefix("\ufeff")
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if (match and match[1][0] == fence[0] and len(match[1]) >= fence[1]
                    and not match[2].strip()):
                fence = None
        elif match and (match[1][0] != "`" or "`" not in match[2]):
            fence = (match[1][0], len(match[1]))
        else:
            yield offset, line
        offset += len(raw)


def heading_section(content, fragment):
    headings = []
    for offset, line in markdown_lines(content):
        match = re.fullmatch(r" {0,3}(#{1,6})(?:[ \t]+(.*)|[ \t]*)", line)
        if match:
            text = re.sub(r"[ \t]+#+[ \t]*$", "", match[2] or "").strip()
            headings.append((offset, len(match[1]), heading_slug(text)))
    matches = [index for index, heading in enumerate(headings) if heading[2] == fragment]
    if not matches:
        raise ToolError(f"heading not found: #{fragment}")
    if len(matches) != 1:
        raise ToolError(f"ambiguous heading: #{fragment}")
    index = matches[0]
    start, level, _ = headings[index]
    end = next((offset for offset, depth, _ in headings[index + 1:] if depth <= level), len(content))
    return content[start:end]


def inline_references(content):
    """Recognize explicit @./ tokens in prose or inline code, not fenced examples."""
    pattern = re.compile(r"(?<![\w@\\])@(\./[^\s`<>\[\](){},;:!?\"']+)")
    for _, line in markdown_lines(content):
        if line.startswith(("    ", "\t")):
            continue
        for match in pattern.finditer(line):
            yield match[1].rstrip(".")


def stored_path(path):
    """Validate the portable, canonical spelling used in the lockfile."""
    if not isinstance(path, str) or not path or "#" in path or "\x00" in path:
        raise ToolError(f"invalid stored path: {path!r}")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or parsed.as_posix() != path or path == ".":
        raise ToolError(f"stored path must be relative and normalized: {path!r}")


def validate_bindings(data):
    if not isinstance(data, dict) or set(data) != {"version", "bindings"}:
        raise ToolError("lockfile must contain version and bindings")
    if type(data["version"]) is not int or data["version"] != 1:
        raise ToolError("unsupported lockfile version (expected 1)")
    if not isinstance(data["bindings"], list):
        raise ToolError("lockfile bindings must be a list")
    seen = set()
    for binding in data["bindings"]:
        if not isinstance(binding, dict):
            raise ToolError("each binding must be an object")
        mode = binding.get("mode")
        if mode not in (BYTES_MODE, AST_MODE, HEADING_MODE):
            raise ToolError(f"unsupported fingerprint mode: {mode!r}")
        fields = {"doc", "target", "mode", "sig"}
        if mode == AST_MODE:
            fields.add("python_minor")
        if set(binding) != fields or not all(isinstance(v, str) for v in binding.values()):
            raise ToolError("binding has missing, unknown or non-string fields")
        stored_path(binding["doc"])
        if PurePosixPath(binding["doc"]).suffix != ".md":
            raise ToolError("binding doc must be a .md file")
        path, symbol = split_target(binding["target"])
        stored_path(path)
        python = PurePosixPath(path).suffix == ".py"
        heading = PurePosixPath(path).suffix == ".md" and symbol is not None
        expected_mode = AST_MODE if python else HEADING_MODE if heading else BYTES_MODE
        if mode != expected_mode or (symbol and not (python or heading)):
            raise ToolError("fingerprint mode does not match target type")
        if heading and binding["target"] != f"{path}#{symbol}":
            raise ToolError("stored Markdown heading fragment must be normalized")
        if not re.fullmatch(r"[0-9a-f]{64}", binding["sig"]):
            raise ToolError("binding sig must be 64 lowercase hexadecimal characters")
        if mode == AST_MODE and not re.fullmatch(r"3\.[0-9]+", binding["python_minor"]):
            raise ToolError("invalid python_minor in AST binding")
        identity = (binding["doc"], binding["target"])
        if identity in seen:
            raise ToolError(f"duplicate binding: {identity[0]} -> {identity[1]}")
        seen.add(identity)
    return sorted(data["bindings"], key=lambda b: (b["doc"], b["target"]))


class Project:
    def __init__(self, cwd):
        self.cwd = resolve(cwd)
        self.root = find_root(self.cwd)
        self.lock = self.root / LOCKFILE
        self.contents = {}
        self.trees = {}
        self.bindings = self.load()

    def contained(self, path):
        absolute = resolve(path)
        if not absolute.is_relative_to(self.root):
            raise ToolError(f"path is outside root {self.root}: {path}")
        return absolute

    def input_path(self, raw, allow_root=False, base=None):
        if not raw or "#" in raw or "\x00" in raw:
            raise ToolError(f"invalid path: {raw!r}")
        absolute = self.contained((base or self.cwd) / raw)
        relative = absolute.relative_to(self.root).as_posix()
        if relative == "." and not allow_root:
            raise ToolError("expected a file path, not the project root")
        return relative

    def input_target(self, raw, base=None):
        path, symbol = split_target(raw)
        path = self.input_path(path, base=base)
        return f"{path}#{symbol}" if symbol else path

    def load(self):
        self.contained(self.lock)
        try:
            source = self.lock.read_text(encoding="utf-8")
        except FileNotFoundError:
            if self.lock.is_symlink():
                raise ToolError("lockfile is a broken symlink")
            return []
        try:
            return validate_bindings(json.loads(source))
        except (ValueError, UnicodeError) as exc:
            raise ToolError(f"invalid {LOCKFILE}: {exc}") from exc

    def read(self, relative):
        if relative not in self.contents:
            path = self.contained(self.root / relative)
            if not path.is_file():
                raise ToolError(f"file not found or not a regular file: {relative}")
            try:
                self.contents[relative] = path.read_bytes()
            except OSError as exc:
                raise ToolError(f"cannot read {relative}: {exc}") from exc
        return self.contents[relative]

    def fingerprint(self, target):
        path, symbol = split_target(target)
        content = self.read(path)
        result = {"mode": BYTES_MODE}
        if PurePosixPath(path).suffix == ".py":
            if path not in self.trees:
                try:
                    # Passing bytes honors Python's source encoding declaration.
                    self.trees[path] = ast.parse(content, filename=path)
                except (SyntaxError, ValueError) as exc:
                    raise ToolError(f"invalid Python in {path}: {exc}") from exc
            node = self.trees[path]
            if symbol:
                parts = symbol.split(".")
                for index, name in enumerate(parts):
                    matches = [n for n in node.body if isinstance(n, DECLARATIONS) and n.name == name]
                    if not matches:
                        raise ToolError(f"symbol not found: {target}")
                    if len(matches) != 1:
                        raise ToolError(f"ambiguous symbol: {target}")
                    node = matches[0]
                    if index < len(parts) - 1 and not isinstance(node, ast.ClassDef):
                        raise ToolError(f"local function anchors are unsupported: {target}")
            content = ast.dump(node, annotate_fields=True, include_attributes=False).encode("utf-8")
            result = {"mode": AST_MODE, "python_minor": PYTHON_MINOR}
        elif symbol and PurePosixPath(path).suffix == ".md":
            content = heading_section(content, symbol)
            result = {"mode": HEADING_MODE}
        elif symbol:
            raise ToolError("symbol anchors are supported only for Python declarations or Markdown headings")
        result["sig"] = hashlib.sha256(content).hexdigest()
        return result

    def write(self, bindings):
        data = {"version": 1, "bindings": sorted(bindings, key=lambda b: (b["doc"], b["target"]))}
        validate_bindings(data)
        self.contained(self.lock)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root,
                                             prefix=f".{LOCKFILE}.", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            os.replace(temporary, self.lock)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def link(project, args):
    doc = project.input_path(args.doc)
    if PurePosixPath(doc).suffix != ".md":
        raise ToolError("doc must be a .md file")
    content = project.read(doc)
    target = project.input_target(args.target) if args.target is not None else None
    existing = {b["target"]: b for b in project.bindings if b["doc"] == doc}
    if target is not None:
        targets = {target}
    else:
        base = project.root / PurePosixPath(doc).parent
        targets = set(existing)
        targets.update(project.input_target(raw, base=base) for raw in inline_references(content))
        if not targets:
            raise ToolError(f"no bindings or inline references found for {doc}")
    selected = [existing.get(t, {"doc": doc, "target": t}) for t in sorted(targets)]
    updated = []
    for old in selected:
        current = project.fingerprint(old["target"])
        previous = {k: v for k, v in old.items() if k not in ("doc", "target")}
        if previous and previous != current and not args.ack:
            raise ToolError(f"target changed: {old['target']}; review {doc}, then relink with --ack (-a)")
        updated.append({"doc": doc, "target": old["target"], **current})
    identities = {(b["doc"], b["target"]) for b in updated}
    bindings = [b for b in project.bindings if (b["doc"], b["target"]) not in identities] + updated
    if sorted(bindings, key=lambda b: (b["doc"], b["target"])) == project.bindings:
        print(f"unchanged: {doc}")
    else:
        project.write(bindings)
        for binding in updated:
            print(f"linked {doc} -> {binding['target']}")
    return 0


def check(project, args):
    selected = project.bindings
    if args.changed is not None:
        prefix = project.input_path(args.changed, allow_root=True)
        docs = {b["doc"] for b in selected
                if prefix == "." or split_target(b["target"])[0] == prefix
                or split_target(b["target"])[0].startswith(prefix + "/")}
        selected = [b for b in selected if b["doc"] in docs]
    if not selected:
        print("no bindings checked")
        return 0
    failed_docs = set()
    last_doc = None
    for binding in selected:
        doc = binding["doc"]
        if doc != last_doc:
            print(doc)
            last_doc = doc
        try:
            project.read(doc)
            if binding["mode"] == AST_MODE and binding["python_minor"] != PYTHON_MINOR:
                raise ToolError(f"Python parser mismatch: baseline {binding['python_minor']}, running {PYTHON_MINOR}; "
                                "use the baseline interpreter or review and relink with --ack (-a)")
            current = project.fingerprint(binding["target"])
            if binding["sig"] != current["sig"]:
                raise ToolError("target changed since last review")
        except ToolError as exc:
            failed_docs.add(doc)
            print(f"  STALE {binding['target']} ({exc})")
        else:
            print(f"  ok    {binding['target']}")
    total = len({b["doc"] for b in selected})
    print(f"{len(failed_docs)} docs stale, {total - len(failed_docs)} docs ok; {len(selected)} bindings checked")
    return 1 if failed_docs else 0


def status(project, args):
    if not project.bindings:
        print("no bindings recorded")
    last_doc = None
    for binding in project.bindings:
        if binding["doc"] != last_doc:
            print(binding["doc"])
            last_doc = binding["doc"]
        print(f"  {binding['target']} ({binding['mode']})")
    return 0


def unlink(project, args):
    doc = project.input_path(args.doc)
    target = project.input_target(args.target)
    remaining = [b for b in project.bindings if (b["doc"], b["target"]) != (doc, target)]
    if len(remaining) == len(project.bindings):
        raise ToolError(f"binding not found: {doc} -> {target}")
    project.write(remaining)
    print(f"removed {doc} -> {target}")
    return 0


def refs(project, args):
    target = project.input_target(args.target)
    path, symbol = split_target(target)
    docs = {b["doc"] for b in project.bindings
            if b["target"] == target or (symbol is None and split_target(b["target"])[0] == path)}
    for doc in sorted(docs):
        print(doc)
    return 0


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    link_cli = commands.add_parser("link", help="add bindings, discover inline references, or refresh reviewed bindings")
    link_cli.add_argument("doc")
    link_cli.add_argument("target", nargs="?")
    link_cli.add_argument("-a", "--ack", action="store_true",
                          help="I reviewed the documentation and acknowledge this refresh")
    link_cli.set_defaults(run=link)
    check_cli = commands.add_parser("check", aliases=["lint"], help="check recorded bindings for drift")
    check_cli.add_argument("--changed", metavar="PATH", help="check docs bound to this file or directory")
    check_cli.set_defaults(run=check)
    status_cli = commands.add_parser("status", help="list bindings without checking freshness")
    status_cli.set_defaults(run=status)
    unlink_cli = commands.add_parser("unlink", help="remove an exact binding")
    unlink_cli.add_argument("doc")
    unlink_cli.add_argument("target")
    unlink_cli.set_defaults(run=unlink)
    refs_cli = commands.add_parser("refs", help="list docs bound to a file or exact symbol")
    refs_cli.add_argument("target")
    refs_cli.set_defaults(run=refs)
    return cli


def main(argv=None):
    if sys.version_info < (3, 12):
        print("error: no-drift requires Python 3.12 or newer", file=sys.stderr)
        return 2
    args = parser().parse_args(argv)
    try:
        return args.run(Project(Path.cwd()), args)
    except (ToolError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
