"""Behavioral CLI tests; all project state lives in disposable directories."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "no_drift.py"
SPEC = importlib.util.spec_from_file_location("no_drift", SCRIPT)
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="no-drift-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.put("docs/auth.md", "# Authentication\n")
        self.put("src/auth.go", "package auth\n")

    def put(self, path, text):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        return destination

    def run_cli(self, *args, code=0, cwd=None):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.root,
                                capture_output=True, text=True,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def lock_bytes(self):
        return (self.root / TOOL.LOCKFILE).read_bytes()

    def state(self):
        return json.loads(self.lock_bytes())

    def save_state(self, state):
        (self.root / TOOL.LOCKFILE).write_text(json.dumps(state), encoding="utf-8")

    def link(self, target="src/auth.go", doc="docs/auth.md"):
        return self.run_cli("link", doc, target)

    def test_byte_workflow_and_review_gate(self):
        self.link()
        self.assertIn("1 bindings checked", self.run_cli("check").stdout)
        self.assertIn("ok", self.run_cli("lint").stdout)
        original = self.lock_bytes()
        self.run_cli("link", "docs/auth.md")
        self.assertEqual(self.lock_bytes(), original)
        self.put("src/auth.go", "package auth\n// uncommitted change\n")
        self.assertIn("target changed", self.run_cli("check", code=1).stdout)
        self.put("docs/auth.md", "# Auth\nReviewed prose.\n")
        self.assertIn("--ack", self.run_cli("link", "docs/auth.md", code=2).stderr)
        self.assertEqual(self.lock_bytes(), original)
        self.run_cli("link", "docs/auth.md", "-a")
        self.run_cli("check")
        self.assertNotEqual(self.lock_bytes(), original)

    def test_both_ack_aliases_in_both_refresh_modes(self):
        self.link()
        for flag in ("--ack", "-a"):
            for targeted in (True, False):
                with self.subTest(flag=flag, targeted=targeted):
                    self.put("src/auth.go", (self.root / "src/auth.go").read_text() + "// edit\n")
                    args = ["link", "docs/auth.md"]
                    if targeted:
                        args.append("src/auth.go")
                    self.run_cli(*args, code=2)
                    self.run_cli(*args, flag)
                    self.run_cli("check")

    def test_python_file_ignores_layout_comments_but_tracks_docstrings(self):
        self.put("src/client.py", '"""Client."""\ndef connect(x):\n    return x + 1\n')
        self.link("src/client.py")
        self.put("src/client.py", '# comment\n"""Client."""\n\ndef connect( x ):\n\treturn (x+1)  # comment\n')
        self.run_cli("check")
        self.put("src/client.py", '"""New docs."""\ndef connect(x):\n    return x + 1\n')
        self.run_cli("check", code=1)

    def test_method_anchor_is_independent_and_includes_decorators(self):
        source = ('class Client:\n    @decorator\n    def connect(self):\n        return 1\n'
                  '    def other(self):\n        return 2\n')
        self.put("src/client.py", source)
        self.link("src/client.py#Client.connect")
        self.put("src/client.py", source.replace("return 2", "return 9"))
        self.run_cli("check")
        self.put("src/client.py", source.replace("@decorator", "@different"))
        self.run_cli("check", code=1)
        self.put("src/client.py", source.replace("return 1", "return 8"))
        self.run_cli("check", code=1)
        self.put("src/client.py", source.replace("def connect", "def renamed"))
        self.assertIn("symbol not found", self.run_cli("check", code=1).stdout)

    def test_top_level_async_class_and_nested_class_anchors(self):
        self.put("src/client.py", 'async def connect():\n    return 1\nclass Outer:\n    class Inner:\n        def run(self):\n            return 2\n')
        for symbol in ("connect", "Outer", "Outer.Inner.run"):
            self.link(f"src/client.py#{symbol}")
        self.run_cli("check")

    def test_python_invalid_missing_ambiguous_and_unsupported_symbols(self):
        cases = [
            ("def broken(:\n", "", "invalid Python"),
            ("def connect():\n    pass\n", "#missing", "symbol not found"),
            ("def connect():\n    pass\ndef connect():\n    pass\n", "#connect", "ambiguous symbol"),
            ("def outer():\n    def inner():\n        pass\n", "#outer.inner", "local function"),
            ("value = 1\n", "#value", "symbol not found"),
        ]
        for source, suffix, reason in cases:
            with self.subTest(reason=reason):
                self.put("src/client.py", source)
                self.assertIn(reason, self.run_cli("link", "docs/auth.md", "src/client.py" + suffix, code=2).stderr)
                self.assertFalse((self.root / TOOL.LOCKFILE).exists())
        self.assertIn("only for Python", self.run_cli("link", "docs/auth.md", "src/auth.go#Auth", code=2).stderr)

    def test_invalid_python_after_link_fails_check(self):
        self.put("src/client.py", "def connect():\n    pass\n")
        self.link("src/client.py#connect")
        self.put("src/client.py", "def connect(:\n")
        self.assertIn("invalid Python", self.run_cli("check", code=1).stdout)

    def test_python_source_encoding(self):
        path = self.put("src/client.py", "")
        path.write_bytes(b"# coding: latin-1\nmessage = 'caf\xe9'\n")
        self.link("src/client.py")
        self.run_cli("check")

    def test_deleted_doc_and_target_fail_and_can_be_unlinked(self):
        self.link()
        (self.root / "docs/auth.md").unlink()
        self.assertIn("docs/auth.md", self.run_cli("check", code=1).stdout)
        self.put("docs/auth.md", "# Auth\n")
        (self.root / "src/auth.go").unlink()
        self.assertIn("file not found", self.run_cli("check", code=1).stdout)
        self.assertEqual(self.run_cli("refs", "src/auth.go").stdout, "docs/auth.md\n")
        (self.root / "docs/auth.md").unlink()
        self.run_cli("unlink", "docs/auth.md", "src/auth.go")
        self.assertEqual(self.state()["bindings"], [])
        self.run_cli("unlink", "docs/auth.md", "src/auth.go", code=2)

    def test_blanket_failure_preserves_all_lock_bytes(self):
        self.put("src/other.go", "package other\n")
        self.link("src/other.go")
        self.link()
        before = self.lock_bytes()
        self.put("src/auth.go", "package changed\n")
        self.run_cli("link", "docs/auth.md", code=2)
        self.assertEqual(self.lock_bytes(), before)
        (self.root / "src/other.go").unlink()
        self.run_cli("link", "docs/auth.md", "-a", code=2)
        self.assertEqual(self.lock_bytes(), before)

    def test_refs_status_and_deterministic_order(self):
        self.put("docs/z.md", "# Z\n")
        self.put("docs/a.md", "# A\n")
        self.put("src/client.py", "def connect():\n    pass\n")
        self.link("src/client.py#connect", "docs/z.md")
        self.link("src/client.py", "docs/a.md")
        self.link("src/client.py#connect", "docs/a.md")
        self.assertEqual(self.run_cli("refs", "src/client.py").stdout, "docs/a.md\ndocs/z.md\n")
        self.assertEqual(self.run_cli("refs", "src/client.py#connect").stdout, "docs/a.md\ndocs/z.md\n")
        self.assertEqual(self.run_cli("refs", "src/client.py#other").stdout, "")
        self.assertEqual(self.run_cli("refs", "nonexistent.go").stdout, "")
        (self.root / "src/client.py").unlink()
        self.assertIn("src/client.py#connect", self.run_cli("status").stdout)
        bindings = self.state()["bindings"]
        self.assertEqual([(b["doc"], b["target"]) for b in bindings], sorted((b["doc"], b["target"]) for b in bindings))
        before = self.lock_bytes()
        self.run_cli("check", code=1)
        self.assertEqual(self.lock_bytes(), before)

    def test_changed_filter_checks_whole_doc_and_component_boundaries(self):
        self.put("docs/other.md", "# Other\n")
        self.put("src/other.go", "package other\n")
        self.put("src-old/a.go", "package old\n")
        self.link()
        self.link("src/other.go")
        self.link("src-old/a.go", "docs/other.md")
        self.put("src/other.go", "package new\n")
        self.put("src-old/a.go", "package new\n")
        checked = self.run_cli("check", "--changed", "src/auth.go", code=1).stdout
        self.assertIn("src/other.go", checked)
        self.assertNotIn("docs/other.md", checked)
        self.assertNotIn("docs/other.md", self.run_cli("check", "--changed", "src", code=1).stdout)
        self.assertIn("docs/other.md", self.run_cli("check", "--changed", ".", code=1).stdout)
        self.assertIn("no bindings checked", self.run_cli("check", "--changed", "src/o").stdout)

    def test_empty_and_bad_usage(self):
        self.assertEqual(self.run_cli("check").stdout, "no bindings checked\n")
        self.assertFalse((self.root / TOOL.LOCKFILE).exists())
        self.assertIn("no bindings", self.run_cli("status").stdout)
        self.run_cli("link", "docs/auth.md", code=2)
        self.run_cli(code=2)
        self.run_cli("unknown", code=2)
        self.run_cli("link", "docs/auth.md", "--doc-is-still-accurate", code=2)
        self.run_cli("link", "docs/auth.md", "missing.go", code=2)
        self.run_cli("link", "src/auth.go", "src/auth.go", code=2)
        self.run_cli("link", "docs/auth.md", "src/auth.go#", code=2)
        self.run_cli("link", "docs/auth.md", "", code=2)

    def test_git_root_subdirectories_spaces_unicode_and_worktree_marker(self):
        (self.root / ".git").write_text("gitdir: elsewhere\n")
        self.put("docs/café guide.md", "# Guide\n")
        self.put("src/my code.go", "package main\n")
        nested = self.root / "docs"
        self.run_cli("link", "café guide.md", "../src/my code.go", cwd=nested)
        self.assertTrue((self.root / TOOL.LOCKFILE).exists())
        self.assertFalse((nested / TOOL.LOCKFILE).exists())
        self.assertEqual(self.run_cli("refs", "../src/my code.go", cwd=nested).stdout, "docs/café guide.md\n")
        (self.root / "src/my code.go").unlink()
        self.run_cli("unlink", "café guide.md", "../src/my code.go", cwd=nested)

    def test_git_boundary_ignores_outer_and_nested_locks(self):
        self.save_state({"version": 1, "bindings": []})
        repo = self.root / "repo"
        (repo / ".git").mkdir(parents=True)
        self.put("repo/docs/auth.md", "# Auth\n")
        self.put("repo/src/auth.go", "package auth\n")
        self.put("repo/docs/no-drift.lock", "not JSON\n")
        self.run_cli("check", cwd=repo / "docs")
        self.run_cli("link", "auth.md", "../src/auth.go", cwd=repo / "docs")
        self.assertEqual(json.loads((repo / TOOL.LOCKFILE).read_text())["bindings"][0]["doc"], "docs/auth.md")
        self.assertEqual(self.state()["bindings"], [])

    def test_standalone_nearest_lock(self):
        self.link()
        self.run_cli("check", cwd=self.root / "docs")
        self.assertEqual(self.run_cli("refs", "../src/auth.go", cwd=self.root / "docs").stdout, "docs/auth.md\n")

    def test_outside_paths_and_symlinks(self):
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external) / "external.go"
            outside.write_text("package outside\n")
            self.run_cli("link", "docs/auth.md", str(outside), code=2)
            (self.root / "src/outside.go").symlink_to(outside)
            self.run_cli("link", "docs/auth.md", "src/outside.go", code=2)
            self.link()
            (self.root / "src/auth.go").unlink()
            (self.root / "src/auth.go").symlink_to(outside)
            self.assertIn("outside root", self.run_cli("check", code=1).stdout)

    def test_lockfile_schema_errors_leave_original_bytes(self):
        self.link()
        valid = self.state()
        mutations = [
            {**valid, "version": 2}, {**valid, "version": True},
            {**valid, "bindings": {}}, {**valid, "bindings": [None]},
            {**valid, "bindings": valid["bindings"] * 2},
        ]
        for field, value in [("mode", "unknown"), ("sig", "bad"), ("sig", 12),
                             ("doc", "../outside.md"), ("doc", "/absolute.md"),
                             ("doc", "./docs/auth.md"), ("doc", "docs/hash#name.md"),
                             ("target", "src/auth.go#Auth"), ("target", "../outside.go"),
                             ("mode", None), ("extra", "unsupported")]:
            binding = {**valid["bindings"][0], field: value}
            mutations.append({"version": 1, "bindings": [binding]})
        missing_sig = {k: v for k, v in valid["bindings"][0].items() if k != "sig"}
        mutations.append({"version": 1, "bindings": [missing_sig]})
        for bad in mutations:
            with self.subTest(state=bad):
                self.save_state(bad)
                before = self.lock_bytes()
                self.run_cli("check", code=2)
                self.run_cli("link", "docs/auth.md", "src/auth.go", "-a", code=2)
                self.assertEqual(self.lock_bytes(), before)
        (self.root / TOOL.LOCKFILE).write_text("not JSON\n")
        self.run_cli("check", code=2)

    def test_parser_mismatch_needs_review_even_with_same_digest(self):
        self.put("src/client.py", "def connect():\n    pass\n")
        self.link("src/client.py")
        state = self.state()
        state["bindings"][0]["python_minor"] = "3.99"
        self.save_state(state)
        before = self.lock_bytes()
        self.assertIn("parser mismatch", self.run_cli("check", code=1).stdout)
        self.run_cli("status")
        self.run_cli("link", "docs/auth.md", code=2)
        self.assertEqual(self.lock_bytes(), before)
        self.run_cli("link", "docs/auth.md", "--ack")
        self.assertEqual(self.state()["bindings"][0]["python_minor"], TOOL.PYTHON_MINOR)
        self.run_cli("check")

    def test_unreadable_target_is_stale(self):
        self.link()
        project = TOOL.Project(self.root)
        original_read = Path.read_bytes

        def fail_target(path):
            if path.name == "auth.go":
                raise PermissionError("denied")
            return original_read(path)

        with patch.object(Path, "read_bytes", fail_target), patch("builtins.print") as output:
            args = TOOL.parser().parse_args(["check"])
            self.assertEqual(TOOL.check(project, args), 1)
        self.assertTrue(any("cannot read" in str(call) for call in output.call_args_list))

    def test_atomic_replace_failure_preserves_original_and_removes_temp(self):
        self.link()
        before = self.lock_bytes()
        project = TOOL.Project(self.root)
        bindings = [{**project.bindings[0], "sig": "0" * 64}]
        with patch.object(TOOL.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                project.write(bindings)
        self.assertEqual(self.lock_bytes(), before)
        self.assertEqual(list(self.root.glob(".no-drift.lock.*")), [])


    def test_whole_markdown_bindings_remain_byte_based(self):
        source = "## Auth\nRules.\n## Other\nDetails.\n"
        self.put("docs/guide.md", source)
        self.link("docs/guide.md")
        self.link("docs/guide.md#Auth")
        self.assertEqual(self.state()["bindings"][0]["mode"], TOOL.BYTES_MODE)
        self.put("docs/guide.md", source.replace("Details.", "Changed details."))
        report = self.run_cli("check", code=1).stdout
        self.assertIn("STALE docs/guide.md (", report)
        self.assertIn("ok    docs/guide.md#auth", report)

    def test_markdown_section_tracks_subsections_but_not_neighbors(self):
        source = ('# Guide\nIntro.\n## Token Validation\nRules.\n'
                  '### Errors\nDetails.\n## Other\nUnrelated.\n')
        self.put("docs/guide.md", source)
        self.link("docs/guide.md#Token Validation")
        binding = self.state()["bindings"][0]
        self.assertEqual(binding["target"], "docs/guide.md#token-validation")
        self.assertEqual(binding["mode"], TOOL.HEADING_MODE)
        self.put("docs/guide.md", source.replace("Intro.", "New intro.").replace("Unrelated.", "New neighbor."))
        self.run_cli("check")
        self.put("docs/guide.md", source.replace("Details.", "Changed subsection."))
        self.run_cli("check", code=1)
        before = self.lock_bytes()
        self.run_cli("link", "docs/auth.md", "docs/guide.md#token-validation", code=2)
        self.assertEqual(self.lock_bytes(), before)
        self.run_cli("link", "docs/auth.md", "docs/guide.md#token-validation", "-a")
        self.run_cli("check")
        self.assertEqual(self.run_cli("refs", "docs/guide.md#Token Validation").stdout, "docs/auth.md\n")
        (self.root / "docs/guide.md").unlink()
        self.run_cli("unlink", "docs/auth.md", "docs/guide.md#Token Validation")

    def test_markdown_heading_ambiguity_and_missing_heading_do_not_write(self):
        self.put("docs/guide.md", "# Guide\n## Auth\nBody.\n")
        self.link("docs/guide.md#Auth")
        before = self.lock_bytes()
        for text, reason in [("# Guide\n", "heading not found"),
                             ("## Auth\nOne.\n### AUTH\nTwo.\n", "ambiguous heading")]:
            with self.subTest(reason=reason):
                self.put("docs/guide.md", text)
                self.assertIn(reason, self.run_cli("check", code=1).stdout)
                self.assertIn(reason, self.run_cli("link", "docs/auth.md", "-a", code=2).stderr)
                self.assertEqual(self.lock_bytes(), before)
        # Different titles with the same normalized fragment are ambiguous too.
        self.put("docs/guide.md", "## Token Validation\nOne.\n## Token-validation\nTwo.\n")
        self.run_cli("link", "docs/auth.md", "docs/guide.md#token-validation", code=2)
        self.assertEqual(self.lock_bytes(), before)

    def test_markdown_fences_hide_headings_but_section_hash_includes_code(self):
        source = ('## Auth\nRules.\n````markdown\n## Auth\n```\n# Example\n'
                  '~~~~\n````\n~~~python\n## Auth\n~~~\n## Other\nElsewhere.\n')
        self.put("docs/guide.md", source)
        self.link("docs/guide.md#Auth")
        self.run_cli("check")
        self.run_cli("link", "docs/auth.md", "docs/guide.md#Example", code=2)
        self.put("docs/guide.md", source.replace("# Example", "# Changed example"))
        self.run_cli("check", code=1)
        # A fence closed with trailing text is not a closing fence.
        self.put("docs/guide.md", "## Auth\n```\n``` extra\n## Auth\n")
        self.run_cli("link", "docs/auth.md", "docs/guide.md#Auth", "-a")
        self.run_cli("check")

    def test_markdown_unicode_crlf_offsets_and_closing_hashes(self):
        source = "# Préface\r\nRésumé.\r\n  ## Café Guide ###\r\nBody.\r\n# End\r\n"
        path = self.put("docs/guide.md", "")
        path.write_bytes(source.encode("utf-8"))
        self.link("docs/guide.md#Café Guide")
        self.assertEqual(self.state()["bindings"][0]["target"], "docs/guide.md#café-guide")
        path.write_bytes(source.replace("Résumé.", "More préface text.").encode("utf-8"))
        self.run_cli("check")
        path.write_bytes(source.replace("Body.", "Body changed.").encode("utf-8"))
        self.run_cli("check", code=1)

    def test_markdown_limited_heading_syntax_and_encoding(self):
        self.put("docs/guide.md", "Auth\n====\n    # Indented\n> # Quoted\n#NoSpace\n")
        for name in ("Auth", "Indented", "Quoted", "NoSpace", "!!!"):
            self.run_cli("link", "docs/auth.md", f"docs/guide.md#{name}", code=2)
        (self.root / "docs/guide.md").write_bytes(b"# Auth\n\xff\n")
        self.assertIn("UTF-8", self.run_cli("link", "docs/auth.md", "docs/guide.md#Auth", code=2).stderr)
        self.assertFalse((self.root / TOOL.LOCKFILE).exists())

    def test_inline_discovery_deduplicates_doc_relative_files_symbols_and_headings(self):
        (self.root / ".git").mkdir()
        self.put("src/client.py", "class Client:\n    def connect(self):\n        return 1\n")
        self.put("docs/guide.md", "## Token Validation\nRules.\n")
        self.put("docs/auth.md", 'Uses @./../src/auth.go, `@./../src/client.py#Client.connect`.\n'
                 'See (@./guide.md#token-validation).\nAgain @./../src/auth.go!\n')
        self.run_cli("link", "auth.md", cwd=self.root / "docs")
        targets = [b["target"] for b in self.state()["bindings"]]
        self.assertEqual(targets, ["docs/guide.md#token-validation", "src/auth.go", "src/client.py#Client.connect"])
        before = self.lock_bytes()
        self.run_cli("link", "docs/auth.md")
        self.assertEqual(self.lock_bytes(), before)
        self.run_cli("check")
        self.assertEqual(self.run_cli("refs", "src/client.py").stdout, "docs/auth.md\n")
        self.put("src/auth.go", "package changed\n")
        self.run_cli("check", "--changed", "src/auth.go", code=1)
        self.run_cli("link", "docs/auth.md", code=2)
        self.assertEqual(self.lock_bytes(), before)
        self.run_cli("link", "docs/auth.md", "--ack")
        self.run_cli("check")

    def test_inline_fenced_indented_escaped_and_email_examples_are_ignored(self):
        self.put("docs/auth.md", 'Use @./../src/auth.go.\n'
                 '````markdown\n@./missing.py\n```\n@./still-hidden.py\n````\n'
                 '~~~ example\n@./also-missing.py\n~~~\n'
                 '    @./indented.py\n\t@./tabbed.py\n'
                 r'Escaped \@./escaped.py and email@./email.py' + '\n')
        self.run_cli("link", "docs/auth.md")
        self.assertEqual([b["target"] for b in self.state()["bindings"]], ["src/auth.go"])
        self.run_cli("check")

    def test_inline_discovery_and_explicit_bindings_are_atomic_and_retained(self):
        self.link()
        self.put("src/new.py", "def run():\n    pass\n")
        self.put("docs/auth.md", "Use @./../src/new.py#run and @./missing.py.\n")
        before = self.lock_bytes()
        self.run_cli("link", "docs/auth.md", "-a", code=2)
        self.assertEqual(self.lock_bytes(), before)
        self.put("docs/auth.md", "Use @./../src/new.py#run.\n")
        # Targeted link intentionally doesn't discover other inline references.
        self.run_cli("link", "docs/auth.md", "src/auth.go")
        self.assertEqual(self.lock_bytes(), before)
        self.run_cli("link", "docs/auth.md")
        self.assertEqual(len(self.state()["bindings"]), 2)
        self.put("docs/auth.md", "No inline references remain.\n")
        self.run_cli("link", "docs/auth.md")
        self.assertEqual(len(self.state()["bindings"]), 2)
        self.run_cli("unlink", "docs/auth.md", "src/new.py#run")
        self.assertEqual(len(self.state()["bindings"]), 1)

    def test_inline_new_references_do_not_bypass_existing_review_gate(self):
        self.link()
        self.put("src/new.py", "def run():\n    pass\n")
        self.put("docs/auth.md", "Use @./../src/new.py#run.\n")
        self.put("src/auth.go", "package changed\n")
        before = self.lock_bytes()
        self.run_cli("link", "docs/auth.md", code=2)
        self.assertEqual(self.lock_bytes(), before)
        self.run_cli("link", "docs/auth.md", "-a")
        self.assertEqual(len(self.state()["bindings"]), 2)
        self.run_cli("check")

    def test_inline_reference_cannot_escape_root(self):
        self.link()
        before = self.lock_bytes()
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external) / "outside.py"
            outside.write_text("pass\n")
            (self.root / "docs/outside.py").symlink_to(outside)
            self.put("docs/auth.md", "Use @./outside.py.\n")
            self.assertIn("outside root", self.run_cli("link", "docs/auth.md", "-a", code=2).stderr)
            self.assertEqual(self.lock_bytes(), before)

    def test_markdown_binding_mode_and_fragment_validation(self):
        self.put("docs/guide.md", "# Auth\nBody.\n")
        self.link("docs/guide.md#Auth")
        valid = self.state()
        for field, value in (("mode", TOOL.BYTES_MODE), ("target", "docs/guide.md#Auth"),
                             ("target", "src/auth.go#auth")):
            with self.subTest(field=field, value=value):
                self.save_state({"version": 1, "bindings": [{**valid["bindings"][0], field: value}]})
                self.run_cli("check", code=2)


if __name__ == "__main__":
    unittest.main()
