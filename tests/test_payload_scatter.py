import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import llmddos.payload_scatter as payload_scatter

from llmddos.payload_scatter import (
    FILE_POSITIONS,
    END_MARKER,
    HUB_CARRIER,
    INSTRUCTION_FILES,
    MARKER,
    POINTER_MARKER,
    STRATEGY_FRAGMENTED,
    STRATEGY_HUB_SPOKE,
    _append_block,
    _comment_block,
    _hub_carrier,
    _pointer_block,
    _split_payload_lines,
    _shebang_comment_prefix,
    _split_payload,
    eligible_file_count,
    instruction_layout_directory,
    normalize_file_positions,
    normalize_instruction_files,
    remove_scattered_payload,
    scatter_payload,
    write_scatter_manifest,
)


class PayloadScatterTests(unittest.TestCase):
    def _repository(self, root: Path) -> None:
        (root / "src").mkdir()
        (root / "src/app.py").write_text("print('ok')\n", encoding="utf-8")
        (root / "src/view.ts").write_text("export const ok = true;\n", encoding="utf-8")
        (root / "src/query.sql").write_text("select 1;\n", encoding="utf-8")
        (root / "src/ignored.json").write_text("{}\n", encoding="utf-8")
        (root / "vendor").mkdir()
        (root / "vendor/third_party.py").write_text("pass\n", encoding="utf-8")

    def test_dry_run_is_deterministic_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._repository(root)

            first = scatter_payload(
                root, "line one\nline two", condition_id="candidate", count=2, seed=17
            )
            second = scatter_payload(
                root, "line one\nline two", condition_id="candidate", count=2, seed=17
            )

            self.assertEqual(first["injections"], second["injections"])
            self.assertEqual(first["mode"], "dry-run")
            self.assertNotIn("line one", str(first))
            self.assertFalse(
                any(MARKER in path.read_text(encoding="utf-8") for path in root.rglob("*.*"))
            )
            self.assertEqual(eligible_file_count(root), 3)

    def test_default_selects_every_eligible_source_header_and_document(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
            (root / "api.h").write_text("#define API 1\n", encoding="utf-8")
            (root / "README.md").write_text("# Read me\n", encoding="utf-8")
            (root / "GUIDE.markdown").write_text("# Guide\n", encoding="utf-8")
            (root / "NOTES.txt").write_text("Notes\n", encoding="utf-8")
            (root / "REFERENCE.rst").write_text("Reference\n", encoding="utf-8")
            (root / "MANUAL.adoc").write_text("= Manual\n", encoding="utf-8")
            (root / "ignored.json").write_text("{}\n", encoding="utf-8")

            manifest = scatter_payload(
                root,
                "payload",
                condition_id="all",
                seed=7,
                apply=True,
            )

            selected = {row["path"] for row in manifest["injections"]}
            self.assertEqual(manifest["selection_mode"], "all_eligible")
            self.assertIsNone(manifest["requested_injections"])
            self.assertEqual(manifest["source_files_selected"], 7)
            self.assertEqual(manifest["eligible_files"], 7)
            self.assertEqual(
                selected,
                {
                    "app.c",
                    "api.h",
                    "README.md",
                    "GUIDE.markdown",
                    "NOTES.txt",
                    "REFERENCE.rst",
                    "MANUAL.adoc",
                },
            )
            self.assertIn("payload", (root / "README.md").read_text(encoding="utf-8"))
            self.assertIn("payload", (root / "NOTES.txt").read_text(encoding="utf-8"))
            self.assertIn(".. payload", (root / "REFERENCE.rst").read_text(encoding="utf-8"))
            self.assertIn("// payload", (root / "MANUAL.adoc").read_text(encoding="utf-8"))
            self.assertNotIn("payload", (root / "ignored.json").read_text(encoding="utf-8"))

    def test_mainstream_languages_build_files_and_test_sources_are_eligible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = {
                "src/app.py": "print('python')\n",
                "spec/app_spec.rb": "puts 'ruby'\n",
                "web/index.html": "<main>html</main>\n",
                "web/styles.css": "main { color: black; }\n",
                "web/app.js": "console.log('js');\n",
                "web/component.ts": "export const value: number = 1;\n",
                "web/view.tsx": "export const View = () => <main />;\n",
                "Sources/App/main.swift": "print(\"swift\")\n",
                "src/Main.java": "class Main {}\n",
                "scripts/check.bash": "#!/usr/bin/env bash\ntrue\n",
                "src/lib.rs": "pub fn value() -> u8 { 1 }\n",
                "src/main.c": "int main(void) { return 0; }\n",
                "include/api.hpp": "#pragma once\n",
                "cmd/main.go": "package main\n",
                "src/Program.cs": "class Program {}\n",
                "src/Main.kt": "fun main() = Unit\n",
                "public/index.php": "<?php echo 'php';\n",
                "config/settings.yaml": "enabled: true\n",
                "Cargo.toml": "[package]\nname = \"fixture\"\n",
                "Makefile": "all:\n\t@true\n",
                "CMakeLists.txt": "project(fixture C)\n",
                "Dockerfile": "FROM scratch\n",
                "runner": "#!/usr/bin/env python3.12\nprint('runner')\n",
            }
            for relative_path, content in fixtures.items():
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            (root / "data.json").write_text("{}\n", encoding="utf-8")
            (root / "README").write_text("extensionless prose\n", encoding="utf-8")

            manifest = scatter_payload(
                root,
                "language coverage",
                condition_id="languages",
                seed=11,
                apply=True,
            )

            records = {row["path"]: row for row in manifest["injections"]}
            self.assertEqual(manifest["eligible_files"], len(fixtures))
            self.assertEqual(set(records), set(fixtures))
            self.assertEqual(records["web/index.html"]["comment_prefix"], "<!--")
            self.assertEqual(records["web/styles.css"]["comment_prefix"], "/*")
            self.assertEqual(records["Makefile"]["comment_prefix"], "#")
            self.assertEqual(records["CMakeLists.txt"]["comment_prefix"], "#")
            self.assertEqual(records["Dockerfile"]["comment_prefix"], "#")
            self.assertEqual(records["runner"]["comment_prefix"], "#")
            self.assertIn(
                "<!-- language coverage -->",
                (root / "web/index.html").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "/* language coverage */",
                (root / "web/styles.css").read_text(encoding="utf-8"),
            )
            self.assertNotIn(MARKER, (root / "data.json").read_text(encoding="utf-8"))
            self.assertNotIn(MARKER, (root / "README").read_text(encoding="utf-8"))

    def test_documentation_files_support_fragmented_and_hub_spoke_modes(self):
        for strategy, expected in (
            (STRATEGY_FRAGMENTED, "documentation payload"),
            (STRATEGY_HUB_SPOKE, HUB_CARRIER),
        ):
            with self.subTest(strategy=strategy), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "README.md").write_text("# Read me\n", encoding="utf-8")

                manifest = scatter_payload(
                    root,
                    "documentation payload",
                    condition_id="docs",
                    seed=8,
                    strategy=strategy,
                    apply=True,
                )

                content = (root / "README.md").read_text(encoding="utf-8")
                self.assertIn(expected, content)
                self.assertEqual(manifest["source_files_selected"], 1)

    def test_seeded_payload_pool_rotates_multiple_full_replicas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(3):
                (root / f"file_{index}.py").write_text("pass\n", encoding="utf-8")
            pool = [
                {"id": "alpha", "payload": "alpha payload"},
                {"id": "beta", "payload": "beta payload"},
                {"id": "gamma", "payload": "gamma payload"},
            ]

            manifest = scatter_payload(
                root,
                pool[0]["payload"],
                condition_id="alpha",
                payload_pool=pool,
                seed=16,
                apply=True,
            )

            self.assertEqual(manifest["payload_pool_size"], 3)
            self.assertEqual(
                {record["payload_id"] for record in manifest["injections"]},
                {"alpha", "beta", "gamma"},
            )
            for record in manifest["injections"]:
                content = (root / record["path"]).read_text(encoding="utf-8")
                self.assertIn(f"# {record['payload_id']} payload", content)

    def test_hub_spoke_line_chunks_multiple_payloads_outside_source_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("pass\n", encoding="utf-8")
            pool = [
                {"id": "alpha", "payload": "a1\na2\na3\na4\na5"},
                {"id": "beta", "payload": "b1\nb2\nb3\nb4\nb5"},
            ]

            manifest = scatter_payload(
                root,
                pool[0]["payload"],
                condition_id="alpha",
                payload_pool=pool,
                seed=17,
                strategy=STRATEGY_HUB_SPOKE,
                hub_chunk_lines=2,
                instruction_files=["agents"],
                apply=True,
            )

            source = (root / "app.py").read_text(encoding="utf-8")
            instruction = (root / "AGENTS.md").read_text(encoding="utf-8")
            carrier = (root / HUB_CARRIER).read_text(encoding="utf-8")
            carrier_record = next(
                record for record in manifest["injections"] if record["role"] == "carrier"
            )
            instruction_record = next(
                record
                for record in manifest["injections"]
                if record["role"] == "instruction"
            )
            self.assertIn(HUB_CARRIER, source)
            self.assertNotIn("a1", source)
            self.assertNotIn("b1", source)
            self.assertIn(HUB_CARRIER, instruction)
            self.assertNotIn("a1", instruction)
            self.assertIn("a1", carrier)
            self.assertIn("b1", carrier)
            self.assertEqual(set(instruction_record["payload_ids"]), {"alpha", "beta"})
            self.assertEqual(carrier_record["line_chunk_count"], 6)
            self.assertEqual(
                {item["payload_id"] for item in carrier_record["placements"]},
                {"alpha", "beta"},
            )

    def test_paired_comment_closing_delimiter_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root / "app.py"
            html = root / "index.html"
            python.write_text("pass\n", encoding="utf-8")
            html.write_text("<main></main>\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsafe closing delimiter"):
                scatter_payload(
                    root,
                    "unsafe --> payload",
                    condition_id="delimiter",
                    seed=12,
                    apply=True,
                )

            self.assertNotIn(MARKER, python.read_text(encoding="utf-8"))
            self.assertNotIn(MARKER, html.read_text(encoding="utf-8"))

    def test_fragmented_adds_full_replica_and_inline_chunk_to_each_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(6):
                (root / f"file_{index}.py").write_text("pass\n", encoding="utf-8")

            manifest = scatter_payload(
                root,
                "abc",
                condition_id="short-fragments",
                seed=9,
                strategy=STRATEGY_FRAGMENTED,
                apply=True,
            )

            records = manifest["injections"]
            self.assertEqual(manifest["source_files_selected"], 6)
            self.assertEqual({row["role"] for row in records}, {"replica_with_inline_chunks"})
            self.assertEqual({row["inline_chunk_count"] for row in records}, {1})
            for row in records:
                content = (root / row["path"]).read_text(encoding="utf-8")
                self.assertEqual(content.count("# abc"), 2)
                self.assertEqual(
                    [item["kind"] for item in row["placements"]],
                    ["inline_chunk", "full_replica"],
                )

    def test_default_rejects_repository_without_eligible_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.json").write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "no eligible"):
                scatter_payload(
                    root,
                    "payload",
                    condition_id="empty",
                    seed=1,
                )

    def test_apply_uses_language_comments_without_visible_wrapper_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._repository(root)

            manifest = scatter_payload(
                root,
                "phase one\nphase two",
                condition_id="candidate",
                count=3,
                seed=4,
                apply=True,
            )

            self.assertEqual(len(manifest["injections"]), 3)
            for injection in manifest["injections"]:
                content = (root / injection["path"]).read_text(encoding="utf-8")
                self.assertIn(f"{injection['comment_prefix']} phase one", content)
                self.assertNotIn(MARKER, content)
                self.assertNotIn(END_MARKER, content)
                self.assertNotIn("sha256=", content)

    def test_rejects_unsupported_extension_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._repository(root)
            with self.assertRaisesRegex(ValueError, "unsupported extensions"):
                scatter_payload(
                    root,
                    "payload",
                    condition_id="candidate",
                    count=1,
                    seed=1,
                    extensions=["json"],
                )

    def test_eligibility_filter_covers_every_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "eligible.PY").write_text("pass\n", encoding="utf-8")
            (root / "unsupported.txt").write_text("text\n", encoding="utf-8")
            (root / "large.py").write_text("x" * 65, encoding="utf-8")
            (root / "nul.py").write_bytes(b"x\x00y")
            (root / "invalid.py").write_bytes(b"\xff\xfe")
            (root / "marked.py").write_text(MARKER, encoding="utf-8")
            (root / "pointer.py").write_text(POINTER_MARKER, encoding="utf-8")
            (root / "unreadable.py").write_text("pass\n", encoding="utf-8")
            (root / "target").mkdir()
            (root / "target/ignored.py").write_text("pass\n", encoding="utf-8")
            (root / "linked.py").symlink_to(root / "eligible.PY")
            (root / "linked-directory").symlink_to(root / "target", target_is_directory=True)

            original_read_bytes = Path.read_bytes

            def selective_read(path):
                if path.name == "unreadable.py":
                    raise OSError("simulated unreadable file")
                return original_read_bytes(path)

            with mock.patch.object(Path, "read_bytes", selective_read):
                self.assertEqual(
                    eligible_file_count(
                        root,
                        max_file_bytes=64,
                        extensions=[".py"],
                    ),
                    1,
                )
            self.assertEqual(eligible_file_count(root, extensions=[]), 0)

    def test_rejects_invalid_roots_and_scatter_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing"
            (root / "app.py").write_text("pass\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "not a directory"):
                eligible_file_count(missing)
            with self.assertRaisesRegex(ValueError, "not a directory"):
                scatter_payload(
                    missing, "payload", condition_id="candidate", count=1, seed=1
                )

            invalid_calls = [
                (
                    "non-empty string",
                    dict(payload="", condition_id="candidate", count=1),
                ),
                (
                    "non-empty string",
                    dict(payload=None, condition_id="candidate", count=1),
                ),
                (
                    "NUL bytes",
                    dict(payload="bad\x00payload", condition_id="candidate", count=1),
                ),
                (
                    "condition_id",
                    dict(payload="payload", condition_id=" ", count=1),
                ),
                (
                    "count must",
                    dict(payload="payload", condition_id="candidate", count=0),
                ),
            ]
            for message, arguments in invalid_calls:
                with self.subTest(message=message, arguments=arguments):
                    with self.assertRaisesRegex(ValueError, message):
                        scatter_payload(root, seed=1, **arguments)
            with self.assertRaisesRegex(ValueError, "max_file_bytes"):
                scatter_payload(
                    root,
                    "payload",
                    condition_id="candidate",
                    count=1,
                    seed=1,
                    max_file_bytes=0,
                )
            with self.assertRaisesRegex(ValueError, "found only"):
                scatter_payload(
                    root,
                    "payload",
                    condition_id="candidate",
                    count=2,
                    seed=1,
                )
            with self.assertRaisesRegex(ValueError, "strategy must"):
                scatter_payload(
                    root,
                    "payload",
                    condition_id="candidate",
                    count=1,
                    seed=1,
                    strategy="unknown",
                )
            with self.assertRaisesRegex(ValueError, "inline_source_lines"):
                scatter_payload(
                    root,
                    "payload",
                    condition_id="candidate",
                    seed=1,
                    inline_source_lines=0,
                )
            with self.assertRaisesRegex(ValueError, "hub_chunk_lines"):
                scatter_payload(
                    root,
                    "payload",
                    condition_id="candidate",
                    seed=1,
                    hub_chunk_lines=0,
                )
            invalid_pools = [
                ("at least one", []),
                ("exactly id and payload", [{"id": "a", "payload": "x", "extra": "y"}]),
                ("ids must", [{"id": 1, "payload": "x"}]),
                ("ids must", [{"id": " ", "payload": "x"}]),
                ("duplicate", [{"id": "a", "payload": "x"}, {"id": "a", "payload": "y"}]),
                ("NUL-free", [{"id": "a", "payload": 1}]),
                ("NUL-free", [{"id": "a", "payload": ""}]),
                ("NUL-free", [{"id": "a", "payload": "x\x00y"}]),
            ]
            for message, pool in invalid_pools:
                with self.subTest(pool=pool), self.assertRaisesRegex(ValueError, message):
                    scatter_payload(
                        root,
                        "payload",
                        condition_id="candidate",
                        seed=1,
                        payload_pool=pool,
                    )

    def test_text_helpers_preserve_newlines_and_validate_fragmentation(self):
        payload_hash = "a" * 64

        self.assertEqual(_append_block(b"", "block\n"), b"block\n")
        self.assertEqual(_append_block(b"line\n", "block\n"), b"line\nblock\n")
        self.assertEqual(_append_block(b"line", "block\n"), b"line\nblock\n")
        self.assertEqual(
            _append_block(b"line\r\n", "block\r\n"), b"line\r\nblock\r\n"
        )
        commented = _comment_block(
            "first\r\n\rsecond", "#", payload_hash, "\r\n", metadata="part=1/1"
        )
        self.assertIn("# first\r\n#\r\n# second", commented)
        self.assertNotIn("part=1/1", commented)
        self.assertNotIn(MARKER, commented)
        paired = _comment_block(
            "first\n\nsecond", "<!--", payload_hash, "\n"
        )
        self.assertIn("<!-- first -->\n<!---->\n<!-- second -->", paired)
        self.assertNotIn(MARKER, paired)
        self.assertTrue(
            _pointer_block("<!--", payload_hash, "\n", metadata="position=head")
            .rstrip()
            .endswith("-->")
        )
        with self.assertRaisesRegex(ValueError, "unsafe closing delimiter"):
            _comment_block("unsafe */ payload", "/*", payload_hash, "\n")
        self.assertEqual(
            _shebang_comment_prefix(b"#!/usr/bin/env node\n"), "//"
        )
        self.assertEqual(
            _shebang_comment_prefix(b"#!/usr/bin/python3.12\n"), "#"
        )
        self.assertIsNone(_shebang_comment_prefix(b"plain text\n"))
        self.assertIsNone(_shebang_comment_prefix(b"#!/usr/bin/env unknown\n"))
        self.assertEqual(_split_payload("abcdef", 3), ["ab", "cd", "ef"])
        self.assertEqual(
            _split_payload_lines("a\nb\nc", 2), ["a\n", "b\nc"]
        )
        with self.assertRaisesRegex(ValueError, "at least 4"):
            _split_payload("abc", 4)

        def malformed_range(stop):
            return [0, 0, 2] if stop == 3 else [0, 1]

        with mock.patch.object(
            payload_scatter, "range", side_effect=malformed_range, create=True
        ):
            with self.assertRaisesRegex(RuntimeError, "preserve the exact text"):
                _split_payload("abcd", 2)

        with mock.patch.object(
            payload_scatter,
            "range",
            side_effect=([0, 0, 2], [0, 1]),
            create=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "line fragmentation"):
                _split_payload_lines("a\nb", 2)

        without_newline = _hub_carrier("payload", payload_hash).decode("utf-8")
        with_newline = _hub_carrier("payload\n", payload_hash).decode("utf-8")
        self.assertEqual(without_newline, with_newline)
        self.assertEqual(with_newline, "payload\n")

    def test_head_mid_tail_places_three_labeled_blocks_per_source_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                "first = 1\nsecond = 2\nthird = 3\nfourth = 4\n",
                encoding="utf-8",
            )

            manifest = scatter_payload(
                root,
                "position payload",
                condition_id="positions",
                count=1,
                seed=5,
                apply=True,
                file_positions=FILE_POSITIONS,
            )

            content = (root / "app.py").read_text(encoding="utf-8")
            self.assertEqual(content.count("# position payload"), 3)
            self.assertNotIn(MARKER, content)
            self.assertNotIn("position=", content)
            placement_index = manifest["injections"][0]["placements"]
            self.assertEqual(
                [placement["position"] for placement in placement_index],
                list(FILE_POSITIONS),
            )
            self.assertEqual(
                [placement["start_byte"] for placement in placement_index],
                sorted(placement["start_byte"] for placement in placement_index),
            )
            self.assertEqual(manifest["file_positions"], list(FILE_POSITIONS))
            self.assertEqual(manifest["placements_per_source_file"], 3)
            self.assertEqual(manifest["placements_written"], 3)
            self.assertEqual(manifest["injections"][0]["placement_count"], 3)

    def test_instruction_file_flag_creates_all_carriers_at_all_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("pass\n", encoding="utf-8")
            (root / "AGENTS.md").write_bytes(b"first\r\nsecond\r\n")
            self.assertEqual(eligible_file_count(root), 2)
            self.assertEqual(
                eligible_file_count(root, instruction_files=INSTRUCTION_FILES), 1
            )

            manifest = scatter_payload(
                root,
                "instruction payload",
                condition_id="instructions",
                count=1,
                seed=6,
                apply=True,
                file_positions=FILE_POSITIONS,
                instruction_files=["claude", "AGENTS.md", "memory"],
            )

            self.assertEqual(manifest["instruction_files"], list(INSTRUCTION_FILES))
            self.assertEqual(manifest["placements_written"], 12)
            instruction_records = [
                row for row in manifest["injections"] if row["role"] == "instruction"
            ]
            self.assertEqual(len(instruction_records), 3)
            self.assertEqual(manifest["source_files_selected"], 1)
            self.assertEqual(
                len({row["path"] for row in manifest["injections"]}),
                len(manifest["injections"]),
            )
            self.assertEqual(
                eligible_file_count(root, instruction_files=INSTRUCTION_FILES), 1
            )
            for filename in INSTRUCTION_FILES:
                raw = (root / filename).read_bytes()
                self.assertEqual(raw.count(MARKER.encode("utf-8")), 0)
                self.assertEqual(raw.count(b"instruction payload"), 3)
            agents_record = next(
                row for row in instruction_records if row["path"] == "AGENTS.md"
            )
            claude_record = next(
                row for row in instruction_records if row["path"] == "CLAUDE.md"
            )
            self.assertIsNotNone(agents_record["before_sha256"])
            self.assertIsNone(claude_record["before_sha256"])
            self.assertIn(b"\r\n", (root / "AGENTS.md").read_bytes())

    def test_instruction_file_dry_run_does_not_create_carrier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("pass\n", encoding="utf-8")

            manifest = scatter_payload(
                root,
                "payload",
                condition_id="instructions",
                count=1,
                seed=6,
                instruction_files=["claude"],
            )

            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertEqual(manifest["files_changed"], 2)

    def test_position_and_instruction_file_options_are_strict(self):
        self.assertEqual(normalize_file_positions(None), ("tail",))
        self.assertEqual(normalize_instruction_files(None), ())
        self.assertEqual(
            instruction_layout_directory(None), "without_instruction_files"
        )
        self.assertEqual(
            instruction_layout_directory(["claude"]), "with_instruction_files"
        )
        with self.assertRaisesRegex(ValueError, "at least one"):
            normalize_file_positions([])
        with self.assertRaisesRegex(ValueError, "unsupported file positions"):
            normalize_file_positions(["quarter"])
        with self.assertRaisesRegex(ValueError, "duplicates"):
            normalize_file_positions(["head", "HEAD"])
        with self.assertRaisesRegex(ValueError, "unsupported instruction file"):
            normalize_instruction_files(["OTHER.md"])
        with self.assertRaisesRegex(ValueError, "duplicates"):
            normalize_instruction_files(["claude", "CLAUDE.md"])

    def test_instruction_file_rejects_unsafe_existing_targets(self):
        cases = {
            "directory": lambda path: path.mkdir(),
            "oversized": lambda path: path.write_bytes(b"x" * 65),
            "nul": lambda path: path.write_bytes(b"x\x00y"),
            "non-utf8": lambda path: path.write_bytes(b"\xff\xfe"),
            "marked": lambda path: path.write_text(MARKER, encoding="utf-8"),
            "pointer": lambda path: path.write_text(POINTER_MARKER, encoding="utf-8"),
        }
        expected = {
            "directory": "not readable",
            "oversized": "not eligible",
            "nul": "not eligible",
            "non-utf8": "must be UTF-8",
            "marked": "already marked",
            "pointer": "already marked",
        }
        for label, create_target in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "app.py").write_text("pass\n", encoding="utf-8")
                target = root / "CLAUDE.md"
                create_target(target)
                with self.assertRaisesRegex(ValueError, expected[label]):
                    scatter_payload(
                        root,
                        "payload",
                        condition_id="instructions",
                        count=1,
                        seed=6,
                        max_file_bytes=64,
                        instruction_files=["claude"],
                    )
                self.assertEqual(
                    (root / "app.py").read_text(encoding="utf-8"), "pass\n"
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("pass\n", encoding="utf-8")
            (root / "CLAUDE.md").symlink_to(root / "missing")
            with self.assertRaisesRegex(ValueError, "cannot be a symlink"):
                scatter_payload(
                    root,
                    "payload",
                    condition_id="instructions",
                    count=1,
                    seed=6,
                    instruction_files=["claude"],
                )

    def test_fragmented_inline_chunk_count_scales_with_source_length(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "short.py").write_text("pass\n", encoding="utf-8")
            (root / "long.py").write_text("value = 1\n" * 100, encoding="utf-8")
            payload = "".join(f"payload line {index}\n" for index in range(10))

            manifest = scatter_payload(
                root,
                payload,
                condition_id="candidate",
                seed=9,
                strategy=STRATEGY_FRAGMENTED,
                inline_source_lines=20,
                apply=True,
            )

            self.assertEqual(manifest["strategy"], STRATEGY_FRAGMENTED)
            by_path = {item["path"]: item for item in manifest["injections"]}
            self.assertEqual(by_path["short.py"]["inline_chunk_count"], 1)
            self.assertEqual(by_path["long.py"]["inline_chunk_count"], 5)
            for record in manifest["injections"]:
                content = (root / record["path"]).read_text(encoding="utf-8")
                for line in payload.splitlines():
                    self.assertEqual(content.count(f"# {line}"), 2)

    def test_fragmented_empty_file_and_instruction_file_receive_inline_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "empty.py").write_bytes(b"")
            (root / "AGENTS.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
            payload = "line one\nline two\nline three"

            manifest = scatter_payload(
                root,
                payload,
                condition_id="fragmented-instructions",
                count=1,
                seed=18,
                strategy=STRATEGY_FRAGMENTED,
                inline_source_lines=1,
                instruction_files=["agents"],
                apply=True,
            )

            by_path = {record["path"]: record for record in manifest["injections"]}
            self.assertEqual(by_path["empty.py"]["inline_chunk_count"], 1)
            self.assertEqual(
                sum(
                    item["kind"] == "inline_chunk"
                    for item in by_path["AGENTS.md"]["placements"]
                ),
                3,
            )

    def test_fragmented_instruction_delimiter_is_prevalidated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "app.py"
            source.write_text("pass\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "instruction file"):
                scatter_payload(
                    root,
                    "unsafe --> payload",
                    condition_id="unsafe-instruction",
                    count=1,
                    seed=19,
                    strategy=STRATEGY_FRAGMENTED,
                    instruction_files=["agents"],
                    apply=True,
                )
            self.assertEqual(source.read_text(encoding="utf-8"), "pass\n")

    def test_hub_spoke_strategy_creates_carrier_and_source_pointers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._repository(root)
            payload = "complete inert evaluation payload"

            manifest = scatter_payload(
                root,
                payload,
                condition_id="candidate",
                count=2,
                seed=11,
                strategy=STRATEGY_HUB_SPOKE,
                apply=True,
            )

            roles = [item["role"] for item in manifest["injections"]]
            self.assertEqual(roles.count("pointer"), 2)
            self.assertEqual(roles.count("carrier"), 1)
            self.assertIn(payload, (root / HUB_CARRIER).read_text(encoding="utf-8"))
            for record in manifest["injections"]:
                if record["role"] == "pointer":
                    content = (root / record["path"]).read_text(encoding="utf-8")
                    self.assertIn(HUB_CARRIER, content)
                    self.assertNotIn(POINTER_MARKER, content)

    def test_hub_spoke_dry_run_and_existing_carrier_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._repository(root)
            payload = "payload ending in newline\n"

            manifest = scatter_payload(
                root,
                payload,
                condition_id="candidate",
                count=1,
                seed=3,
                strategy=STRATEGY_HUB_SPOKE,
            )

            self.assertEqual(manifest["mode"], "dry-run")
            self.assertEqual(manifest["files_changed"], 2)
            self.assertFalse((root / HUB_CARRIER).exists())

            (root / HUB_CARRIER).write_text("occupied\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                scatter_payload(
                    root,
                    payload,
                    condition_id="candidate",
                    count=1,
                    seed=3,
                    strategy=STRATEGY_HUB_SPOKE,
                )
            (root / HUB_CARRIER).unlink()
            (root / HUB_CARRIER).symlink_to(root / "missing-carrier")
            with self.assertRaisesRegex(ValueError, "already exists"):
                scatter_payload(
                    root,
                    payload,
                    condition_id="candidate",
                    count=1,
                    seed=3,
                    strategy=STRATEGY_HUB_SPOKE,
                )

    def test_external_index_removes_payload_and_restores_original_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "app.py"
            source.write_text("first = 1\nsecond = 2\n", encoding="utf-8")
            original = source.read_bytes()
            manifest = scatter_payload(
                root,
                "indexed payload",
                condition_id="indexed",
                count=1,
                seed=13,
                apply=True,
                file_positions=FILE_POSITIONS,
                instruction_files=["claude"],
            )

            self.assertNotIn("indexed payload", str(manifest))
            for record in manifest["injections"]:
                for placement in record["placements"]:
                    self.assertIn("start_byte", placement)
                    self.assertIn("end_byte", placement)
                    self.assertIn("inserted_sha256", placement)
            legacy_index = copy.deepcopy(manifest)
            legacy_index["schema_version"] = 4
            self.assertEqual(
                remove_scattered_payload(root, legacy_index)["mode"], "dry-run"
            )
            preview = remove_scattered_payload(root, manifest)
            self.assertEqual(preview["mode"], "dry-run")
            self.assertIn(b"indexed payload", source.read_bytes())

            removed = remove_scattered_payload(root, manifest, apply=True)

            self.assertEqual(source.read_bytes(), original)
            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertEqual(removed["files_restored"], 1)
            self.assertEqual(removed["created_files_removed"], 1)

    def test_external_index_refuses_modified_repository_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.py"
            second = root / "b.py"
            first.write_text("a = 1\n", encoding="utf-8")
            second.write_text("b = 2\n", encoding="utf-8")
            manifest = scatter_payload(
                root,
                "payload",
                condition_id="indexed",
                seed=14,
                apply=True,
            )
            first_after_scatter = first.read_bytes()
            second.write_bytes(second.read_bytes() + b"# agent edit\n")

            with self.assertRaisesRegex(ValueError, "changed after scattering"):
                remove_scattered_payload(root, manifest, apply=True)

            self.assertEqual(first.read_bytes(), first_after_scatter)

    def test_external_index_rejects_malformed_or_unsafe_metadata(self):
        def indexed_fixture(root):
            source = root / "app.py"
            source.write_text("value = 1\n", encoding="utf-8")
            return scatter_payload(
                root,
                "payload",
                condition_id="indexed",
                count=1,
                seed=15,
                apply=True,
            )

        mutations = {
            "schema_version": lambda index, root: index.update(schema_version=3),
            "mode": lambda index, root: index.update(mode="dry-run"),
            "injections_type": lambda index, root: index.update(injections={}),
            "injections_empty": lambda index, root: index.update(injections=[]),
            "record_type": lambda index, root: index["injections"].__setitem__(0, None),
            "path_empty": lambda index, root: index["injections"][0].update(path=""),
            "path_absolute": lambda index, root: index["injections"][0].update(path="/tmp/x"),
            "path_traversal": lambda index, root: index["injections"][0].update(path="../x"),
            "path_duplicate": lambda index, root: index["injections"].append(
                copy.deepcopy(index["injections"][0])
            ),
            "path_missing": lambda index, root: index["injections"][0].update(path="missing.py"),
            "placements_type": lambda index, root: index["injections"][0].update(placements={}),
            "placements_empty": lambda index, root: index["injections"][0].update(placements=[]),
            "placement_type": lambda index, root: index["injections"][0].update(placements=[None]),
            "start_type": lambda index, root: index["injections"][0]["placements"][0].update(start_byte="0"),
            "end_type": lambda index, root: index["injections"][0]["placements"][0].update(end_byte="1"),
            "start_negative": lambda index, root: index["injections"][0]["placements"][0].update(start_byte=-1),
            "end_before_start": lambda index, root: index["injections"][0]["placements"][0].update(end_byte=0),
            "end_too_large": lambda index, root: index["injections"][0]["placements"][0].update(end_byte=10_000),
            "length_mismatch": lambda index, root: index["injections"][0]["placements"][0].update(inserted_bytes=1),
            "inserted_hash": lambda index, root: index["injections"][0]["placements"][0].update(inserted_sha256="0" * 64),
            "before_hash": lambda index, root: index["injections"][0].update(before_sha256="0" * 64),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = indexed_fixture(root)
                broken = copy.deepcopy(manifest)
                mutate(broken, root)
                with self.assertRaises(ValueError):
                    remove_scattered_payload(root, broken)

        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            with self.assertRaisesRegex(ValueError, "not a directory"):
                remove_scattered_payload(missing, {})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "must be an object"):
                remove_scattered_payload(root, [])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = indexed_fixture(root)
            source = root / "app.py"
            source.unlink()
            source.symlink_to(root / "missing")
            with self.assertRaisesRegex(ValueError, "missing or unsafe"):
                remove_scattered_payload(root, manifest)

    def test_manifest_writer_creates_parent_and_emits_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested/scatter.json"
            manifest = {"schema_version": 2, "strategy": "replicated"}

            write_scatter_manifest(manifest, path)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), manifest)
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))


if __name__ == "__main__":
    unittest.main()
