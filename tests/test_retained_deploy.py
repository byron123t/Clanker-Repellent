import contextlib
import gzip
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clanker_repellent.cli.repo_tool import main
from clanker_repellent.payload import carrier_deploy as lifecycle
from clanker_repellent.payload import retained_deploy as retained
from clanker_repellent.payload import deployment_store as journal


class RetainedDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.payload = self.base / "note.txt"
        self.text = 'Project note: preserve examples.\nQuotes " and \\\\; café 🎲 </script> ??/\n'
        self.payload.write_text(self.text, encoding="utf-8")

    def deploy(self, **kwargs):
        return retained.deploy_retained(repository=self.repo, payloads=[self.payload], benign=True, **kwargs)

    def backup_path(self, name):
        manifest = journal.load_manifest(self.repo, self.repo / lifecycle.INDEX_FILENAME)
        row = next(row for row in manifest["files"] if row["path"] == name)
        key = row["before_sha256"]
        return Path(manifest["store"]) / "objects" / key[:2] / key

    def test_preview_apply_verify_remove_without_content_in_index(self):
        originals = {"app.js": b'"use strict";\nlet score = 42;\n',
                     "index.html": b'<!doctype html><body><canvas></canvas></body>',
                     "game.wasm": retained.WASM_HEADER}
        for name, raw in originals.items():
            (self.repo / name).write_bytes(raw)
        os.chmod(self.repo / "app.js", 0o755)
        preview = self.deploy()
        self.assertEqual(preview["files_changed"], 3)
        self.assertFalse((self.repo / lifecycle.INDEX_FILENAME).exists())
        self.assertEqual((self.repo / "app.js").read_bytes(), originals["app.js"])
        applied = self.deploy(apply=True)
        self.assertNotIn("Project note", json.dumps(applied))
        self.assertTrue(applied["benign"])
        result = retained.verify_artifacts(repository=self.repo, artifacts=list(map(Path, originals)))
        self.assertEqual(result["status"], "verified")
        self.assertEqual(lifecycle.status_deployment(repository=self.repo)["status"], "clean")
        lifecycle.remove_deployment(repository=self.repo, apply=True)
        for name, raw in originals.items():
            self.assertEqual((self.repo / name).read_bytes(), raw)
        self.assertEqual((self.repo / "app.js").stat().st_mode & 0o777, 0o755)

    @unittest.skipUnless(shutil.which("cc") and shutil.which("strip"), "C compiler and strip required")
    def test_native_text_survives_optimization_lto_and_symbol_stripping(self):
        host = self.repo / "main.c"
        host.write_text("#include <stdio.h>\nint main(void) { puts(\"ordinary app\"); return 0; }\n")
        self.deploy(apply=True)
        binary = self.repo / "app"
        flags = ["-O3", "-flto", "-Wall", "-Wextra", "-Werror", "-ffunction-sections", "-fdata-sections"]
        flags += ["-Wl,-dead_strip"] if sys.platform == "darwin" else ["-Wl,--gc-sections"]
        built = subprocess.run([shutil.which("cc"), *flags, str(host), "-o", str(binary)], capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        subprocess.run(["strip", str(binary)], check=True, capture_output=True)
        output = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
        self.assertEqual(output.stdout, "ordinary app\n")
        self.assertIn(self.text.encode(), binary.read_bytes())
        self.assertEqual(retained.verify_artifacts(repository=self.repo, artifacts=[binary])["status"], "verified")

    @unittest.skipUnless(shutil.which("c++"), "C++ compiler required")
    def test_cpp_multiple_translation_units_link_without_collisions(self):
        (self.repo / "main.cpp").write_text("int helper(); int main() { return helper(); }\n")
        (self.repo / "helper.cpp").write_text("int helper() { return 0; }\n")
        self.deploy(apply=True)
        binary = self.repo / "app"
        result = subprocess.run(["c++", "-O2", "-Wall", "-Wextra", "-Werror", str(self.repo / "main.cpp"),
                                 str(self.repo / "helper.cpp"), "-o", str(binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(retained.verify_artifacts(repository=self.repo, artifacts=[binary])["status"], "verified")

    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_javascript_execution_keeps_host_behavior_and_note_is_data(self):
        target = self.repo / "app.cjs"
        target.write_text('"use strict"; globalThis.score = 42;\n')
        self.deploy(apply=True)
        check = '''require(process.argv[1]);
const key = Object.getOwnPropertyNames(globalThis).find(k => k.startsWith('repel:'));
process.stdout.write(JSON.stringify({score: globalThis.score, record: globalThis[key]}));'''
        result = subprocess.run(["node", "-e", check, str(target)], check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["score"], 42)
        self.assertIn(self.text, data["record"])

    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_wasm_module_still_instantiates_and_exposes_custom_section(self):
        target = self.repo / "game.wasm"
        # A real function export: (func (export "answer") (result i32) i32.const 42).
        target.write_bytes(retained.WASM_HEADER + bytes.fromhex(
            "0105016000017f 03020100 070a0106616e737765720000 0a06010400412a0b"))
        self.deploy(apply=True)
        check = '''const fs = require('fs');
const m = new WebAssembly.Module(fs.readFileSync(process.argv[1]));
if (new WebAssembly.Instance(m).exports.answer() !== 42) throw Error('host changed');
const notes = WebAssembly.Module.customSections(m, 'repel.notes.v1');
process.stdout.write(Buffer.from(notes[0]));'''
        result = subprocess.run(["node", "-e", check, str(target)], check=True, capture_output=True)
        self.assertIn(self.text.encode(), result.stdout)

    def test_html_data_does_not_break_out_and_ignores_fake_closing_tags(self):
        original = '<!doctype html><body><script>const tag = "</body>";</script><!-- </body> --></body>'
        target = self.repo / "index.html"
        target.write_text(original)
        self.deploy(apply=True)
        source = target.read_text()
        self.assertTrue(source.startswith(original[:-7]))
        self.assertEqual(source.count("</script>"), 2)
        self.assertIn('type="application/json"', source)
        self.assertEqual(retained.verify_artifacts(repository=self.repo, artifacts=[target])["status"], "verified")

    def test_verifier_decodes_minifier_quotes_escapes_and_gzip(self):
        target = self.repo / "app.js"
        target.write_text(";")
        self.deploy(apply=True)
        frame = retained._frame(self.text).decode()
        # Single quotes, hex escapes, Unicode escapes and surrogate pairs are common
        # minifier output; verification must not evaluate the bundle to decode them.
        literal = json.dumps(frame, ensure_ascii=True)[1:-1].replace("'", "\\'")
        literal = literal.replace('\\"', '"').replace("REPEL", "\\x52EPEL")
        compressed = self.repo / "bundle.js.gz"
        compressed.write_bytes(gzip.compress(("globalThis.note='" + literal + "'").encode()))
        self.assertEqual(retained.verify_artifacts(repository=self.repo, artifacts=[compressed])["status"], "verified")

    def test_verification_fails_if_only_hash_remains_or_content_is_corrupt(self):
        target = self.repo / "app.js"
        target.write_text(";")
        manifest = self.deploy(apply=True)
        for raw in [manifest["contents"][0]["sha256"].encode(), retained._frame(self.text).replace(b"Project", b"project")]:
            (self.repo / "build.bin").write_bytes(raw)
            self.assertEqual(retained.verify_artifacts(repository=self.repo, artifacts=[Path("build.bin")])["status"], "missing")

    def test_verifier_does_not_lose_records_after_quotes_in_js_regex_or_comments(self):
        target = self.repo / "app.js"
        target.write_text('const regex = /["\']/g; /* a lone " */\n')
        self.deploy(apply=True)
        self.assertEqual(retained.verify_artifacts(repository=self.repo, artifacts=[target])["status"], "verified")

    def test_truncated_gzip_reports_a_cli_error(self):
        (self.repo / "app.js").write_text(";")
        self.deploy(apply=True)
        (self.repo / "app.js.gz").write_bytes(b"\x1f\x8b\x08")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["deploy", "verify", "--repo", str(self.repo), "--artifact", "app.js.gz"])
        self.assertEqual(code, 2)
        self.assertIn("invalid gzip artifact", output.getvalue())

    def test_changed_backup_is_rejected_before_any_file_is_restored(self):
        for name in ["a.js", "b.js"]:
            (self.repo / name).write_text(";")
        self.deploy(apply=True)
        before = (self.repo / "a.js").read_bytes()
        backup = self.backup_path("b.js")
        backup.write_bytes(b"tampered")
        with self.assertRaisesRegex(lifecycle.DeploymentError, "hash changed"):
            lifecycle.remove_deployment(repository=self.repo, apply=True)
        self.assertEqual((self.repo / "a.js").read_bytes(), before)

    def test_apply_rolls_back_if_index_write_fails(self):
        for name in ["a.js", "b.js"]:
            (self.repo / name).write_text(";")
        write = journal.atomic_bytes
        def fail_index(path, data, mode=0o600):
            if path.name == lifecycle.INDEX_FILENAME:
                raise OSError("disk full")
            return write(path, data, mode)
        with mock.patch.object(journal, "atomic_bytes", side_effect=fail_index):
            with self.assertRaises(OSError):
                self.deploy(apply=True)
        for name in ["a.js", "b.js"]:
            self.assertEqual((self.repo / name).read_text(), ";")
        self.assertFalse((self.repo / (lifecycle.INDEX_FILENAME + ".preimage")).exists())

    def test_symlinks_and_path_traversal_cannot_be_targeted(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "app.js").write_text(";")
        (self.repo / "link").symlink_to(outside, target_is_directory=True)
        for value in [Path("link/app.js"), Path("../outside/app.js")]:
            with self.assertRaises(lifecycle.DeploymentError):
                self.deploy(target_files=[value], apply=True)
        self.assertEqual((outside / "app.js").read_text(), ";")

    def test_discovery_excludes_generated_dependency_and_operational_directories(self):
        # Do not create/read the operational directories prohibited by AGENTS.md.
        self.assertIn("payloads", retained.EXCLUDED_DIRECTORIES)
        self.assertIn("results", retained.EXCLUDED_DIRECTORIES)
        for name in ["dist", "node_modules", ".repel-carrier-index.json.preimage"]:
            (self.repo / name).mkdir()
            (self.repo / name / "skip.js").write_text(";")
        (self.repo / "app.js").write_text(";")
        (self.repo / "types.d.ts").write_text("declare const score: number;\n")
        result = self.deploy()
        self.assertEqual([row["path"] for row in result["files"]], ["app.js"])
        result = self.deploy(target_files=[Path("dist/skip.js")])
        self.assertEqual(result["files_changed"], 1)

    def test_multiple_payloads_and_benign_generation_snippets_are_retained_as_data(self):
        (self.repo / "app.js").write_text(";")
        other = self.base / "other.txt"
        other.write_text("Another ordinary project note.\n")
        report = retained.deploy_retained(repository=self.repo, payloads=[self.payload, other], benign=True, apply=True)
        self.assertEqual(len(report["contents"]), 2)
        self.assertEqual(retained.verify_artifacts(repository=self.repo, artifacts=[Path("app.js")])["status"], "verified")
        lifecycle.remove_deployment(repository=self.repo, apply=True)
        run = self.base / "benign-run"
        run.mkdir()
        snippet = 'const note = "Project documentation";\n'
        (run / "generated.js").write_text(snippet)
        manifest = {"kind": "repel_source_generation", "settings": {"mode": "benign"}, "candidates": [{
            "language": "javascript", "candidate_id": "control", "status": "passed", "accepted": True,
            "candidate": {"relative_path": "generated.js", "sha256": retained._sha256_bytes(snippet.encode())}}]}
        (run / "manifest.json").write_text(json.dumps(manifest))
        retained.deploy_retained(repository=self.repo, run_dir=run, benign=True, apply=True)
        self.assertEqual(retained.verify_artifacts(repository=self.repo, artifacts=[Path("app.js")])["status"], "verified")

    def test_benign_mode_rejects_unreviewed_generation_run(self):
        (self.repo / "app.js").write_text(";")
        run = self.base / "run"
        run.mkdir()
        (run / "manifest.json").write_text(json.dumps({"kind": "repel_source_generation", "settings": {"mode": "standard"}}))
        with self.assertRaisesRegex(lifecycle.DeploymentError, "requires a benign generation run"):
            retained.deploy_retained(repository=self.repo, run_dir=run, benign=True, apply=True)

    def test_changed_target_and_symlinked_backup_are_rejected(self):
        target = self.repo / "app.js"
        target.write_text(";")
        self.deploy(apply=True)
        after = target.read_bytes()
        target.write_bytes(after + b"\n;")
        with self.assertRaisesRegex(lifecycle.DeploymentError, "refusing approximate removal"):
            lifecycle.remove_deployment(repository=self.repo, apply=True)
        target.write_bytes(after)
        backup = self.backup_path("app.js")
        backup.unlink()
        backup.symlink_to(target)
        with self.assertRaisesRegex(lifecycle.DeploymentError, "symlink"):
            lifecycle.remove_deployment(repository=self.repo, apply=True)

    def test_malformed_wasm_prevents_all_writes(self):
        (self.repo / "a.js").write_text(";")
        target = self.repo / "b.wasm"
        for body in [b"bad", retained.WASM_HEADER + b"\0\xff", retained.WASM_HEADER + b"\0\x05x",
                     retained.WASM_HEADER + b"\0\x01\x02"]:
            target.write_bytes(body)
            with self.assertRaises(lifecycle.DeploymentError):
                self.deploy(apply=True)
            self.assertEqual((self.repo / "a.js").read_text(), ";")

    def test_cli_retained_mode_and_nonzero_verification_exit(self):
        (self.repo / "app.js").write_text(";")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["deploy", "add", "--repo", str(self.repo), "--retain", "--benign",
                         "--payload", str(self.payload), "--file", "app.js", "--apply"])
        self.assertEqual(code, 0, output.getvalue())
        self.assertTrue(json.loads(output.getvalue())["benign"])
        (self.repo / "empty.js").write_text(";")
        for artifact, expected in [("app.js", 0), ("empty.js", 3)]:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["deploy", "verify", "--repo", str(self.repo), "--artifact", artifact]), expected)


if __name__ == "__main__":
    unittest.main()
