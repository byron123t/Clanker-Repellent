import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clanker_repellent.cli import generate_cli
from clanker_repellent.cli.repo_tool import main
from clanker_repellent.payload import catalog, deployment_store as store
from clanker_repellent.payload.carrier_deploy import INDEX_FILENAME, remove_deployment, status_deployment
from clanker_repellent.payload.retained_deploy import deploy_retained, verify_artifacts


class CatalogJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.library = self.root / "library"
        catalog.initialize(self.library)
        self.note = self.root / "note.txt"
        self.note.write_text("Ordinary project note.\n")
        self.index = self.repo / INDEX_FILENAME

    def cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            result = main(list(args))
        return result, out.getvalue()

    def deploy(self, **kwargs):
        return deploy_retained(repository=self.repo, payloads=[self.note], benign=True, apply=True, **kwargs)

    def add(self, identifier, kind="data", **kwargs):
        return catalog.add(self.library, identifier=identifier, kind=kind, text="A project note: " + identifier,
                           benign=True, tags=["control"], **kwargs)

    def test_catalog_checks_metadata_content_tags_and_type(self):
        metadata = self.add("plain")
        self.add("html-note", kind="document", document_type="html")
        selected = catalog.select(self.library, tags=["control"], kind="document", document_type="html", benign=True)
        self.assertEqual([r["id"] for r in selected], ["html-note"])
        self.assertEqual(catalog.read(self.library, "plain")[1], "A project note: plain")
        with self.assertRaisesRegex(ValueError, "different"):
            catalog.add(self.library, identifier="plain", kind="data", text="changed", benign=True)
        with self.assertRaisesRegex(ValueError, "excluded"):
            catalog.select(self.library, identifiers=["plain"], kind="source")
        (self.library / metadata["object"]).write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "hash/length"):
            catalog.read(self.library, "plain")

    def test_catalog_rejects_symlink_objects_and_invalid_source(self):
        metadata = self.add("plain")
        obj = self.library / metadata["object"]
        obj.unlink()
        obj.symlink_to(self.note)
        with self.assertRaisesRegex(ValueError, "symlink"):
            catalog.read(self.library, "plain")
        with self.assertRaisesRegex(ValueError, "validation"):
            catalog.add(self.library, identifier="bad", kind="source", language="python", text="if invalid syntax", benign=True)
        with self.assertRaises(ValueError):
            catalog.add(self.library, identifier="../escape", kind="data", text="ordinary", benign=True)

    def test_generation_cli_registers_typed_benign_candidate(self):
        catalog.add(self.library, identifier="input", kind="data", text="Project convention.", benign=True)
        class Provider:
            def wait_for_model(self):
                return "control-model"
            def complete(self, **kwargs):
                return {"response_text": '```python\nvalue = "ordinary project note"\n```', "finish_reason": "stop", "latency_ms": 1.0, "usage": {}}
        output = self.root / "benign-run"
        args = generate_cli.build_parser().parse_args([
            "--catalog", str(self.library), "--payload-id", "input", "--language", "python",
            "--benign", "--skip-linters", "--output-dir", str(output), "--register-prefix", "generated", "--tag", "control"])
        with mock.patch.object(generate_cli, "load_endpoint_config", return_value={}), mock.patch.object(
                generate_cli, "RoutedOpenAICompatibleProvider", return_value=Provider()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(generate_cli.run(args), 0)
        metadata, text = catalog.read(self.library, "generated-python")
        self.assertTrue(metadata["benign"])
        self.assertEqual(metadata["language"], "python")
        self.assertEqual(metadata["tags"], ["control"])
        self.assertIn("ordinary project note", text)

    def test_random_source_placement_is_reproducible_and_preserves_crlf_tabs(self):
        for number in range(3):
            catalog.add(self.library, identifier=f"source-{number}", text=f'annotation = "note {number}"\n',
                        kind="source", language="python", benign=True)
        original = b'#!/usr/bin/python3\r\n# coding: utf-8\r\n"""Project module."""\r\nfrom __future__ import annotations\r\n\r\ndef value():\r\n\treturn 42\r\n'
        for number in range(8):
            (self.repo / f"file{number}.py").write_bytes(original)
        def deploy(seed):
            code, text = self.cli("deploy", "add", "--repo", str(self.repo), "--catalog", str(self.library),
                                  "--kind", "source", "--benign", "--random", "--seed", str(seed), "--count", "4", "--apply")
            self.assertEqual(code, 0, text)
            manifest = store.load_manifest(self.repo, self.index)
            result = [(r["path"], r["candidate_id"], (self.repo / r["path"]).read_bytes()) for r in manifest["files"]]
            for _, _, raw in result:
                self.assertTrue(raw.startswith(b"#!/usr/bin/python3\r\n# coding: utf-8"))
                self.assertNotIn(b"\r\r\n", raw)
                self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
                compile(raw, "test.py", "exec")
            remove_deployment(repository=self.repo, apply=True)
            for number in range(8):
                self.assertEqual((self.repo / f"file{number}.py").read_bytes(), original)
            return result
        self.assertEqual(deploy(11), deploy(11))
        self.assertNotEqual(deploy(11), deploy(12))

    def test_document_types_match_and_recover_despite_crlf_and_fences(self):
        for identifier, subtype in [("markdown", "markdown"), ("html", "html"), ("rst", "rst")]:
            catalog.add(self.library, identifier=identifier, kind="document", document_type=subtype,
                        text='Documentation example.\n```\n</script>\n', benign=True)
        for name, source in [("readme.md", b"# Notes\r\n"), ("index.html", b"<body>\r\n</body>"), ("doc.rst", b"Notes\r\n====="), ("unused.js", b";")]:
            (self.repo / name).write_bytes(source)
        result, message = self.cli("deploy", "add", "--repo", str(self.repo), "--catalog", str(self.library), "--retain", "--benign", "--apply")
        self.assertEqual(result, 0, message)
        self.assertEqual((self.repo / "unused.js").read_bytes(), b";")
        report = verify_artifacts(repository=self.repo, artifacts=[Path("readme.md"), Path("index.html"), Path("doc.rst")])
        self.assertEqual(report["status"], "verified")

    def test_journal_replays_every_exact_byte_edit_in_order(self):
        (self.repo / "app.js").write_bytes(b'const text = "caf\xc3\xa9";\r\n')
        self.deploy()
        manifest = store.load_manifest(self.repo, self.index)
        objects = store.DeploymentStore(manifest["store"])
        for row in manifest["files"]:
            current = objects.get(row["before_sha256"])
            for edit in row["edits"]:
                offset = edit["offset_before_step"]
                removed = objects.get(edit["removed_sha256"])
                self.assertEqual(current[offset:offset + len(removed)], removed)
                current = current[:offset] + objects.get(edit["inserted_sha256"]) + current[offset + len(removed):]
            self.assertEqual(store.digest(current), row["after_sha256"])
            self.assertEqual(current, (self.repo / row["path"]).read_bytes())

    def test_interrupted_apply_is_recoverable_from_before_and_after_images(self):
        for name in ["a.js", "b.js"]:
            (self.repo / name).write_text(";")
        atomic = store.atomic_bytes
        def interrupt(path, raw, mode=0o600):
            atomic(path, raw, mode)
            if path == self.repo / "a.js":
                raise KeyboardInterrupt()
        with mock.patch.object(store, "atomic_bytes", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.deploy()
        self.assertEqual(status_deployment(repository=self.repo)["journal_state"], "prepared")
        remove_deployment(repository=self.repo, apply=True)
        self.assertEqual((self.repo / "a.js").read_text(), ";")
        self.assertEqual((self.repo / "b.js").read_text(), ";")

    def test_interrupted_removal_can_resume(self):
        for name in ["a.js", "b.js"]:
            (self.repo / name).write_text(";")
        self.deploy()
        atomic = store.atomic_bytes
        def interrupt(path, raw, mode=0o600):
            atomic(path, raw, mode)
            if path == self.repo / "a.js":
                raise KeyboardInterrupt()
        with mock.patch.object(store, "atomic_bytes", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                remove_deployment(repository=self.repo, apply=True)
        self.assertEqual(status_deployment(repository=self.repo)["journal_state"], "removing")
        code, text = self.cli("deploy", "recover", "--repo", str(self.repo), "--apply")
        self.assertEqual(code, 0, text)
        self.assertEqual((self.repo / "b.js").read_text(), ";")

    def test_snapshot_restores_binary_capture_and_new_artifact_exactly(self):
        original = b"\x7fELF\0original\xff\xfe\n"
        (self.repo / "app").write_bytes(original)
        (self.repo / "capture.pcap").write_bytes(b"\xd4\xc3\xb2\xa1original packet bytes\0")
        os.chmod(self.repo / "app", 0o755)
        code, text = self.cli("deploy", "snapshot", "--repo", str(self.repo), "--artifact", "app", "--artifact", "capture.pcap", "--artifact", "new.wasm", "--apply")
        self.assertEqual(code, 0, text)
        with self.assertRaisesRegex(ValueError, "not sealed"):
            store.restore(self.repo, self.index, apply=True)
        (self.repo / "app").write_bytes(b"modified executable")
        (self.repo / "capture.pcap").write_bytes(b"modified packet bytes")
        (self.repo / "new.wasm").write_bytes(b"newly built artifact")
        self.assertEqual(self.cli("deploy", "seal", "--repo", str(self.repo))[0], 0)
        remove_deployment(repository=self.repo, apply=True)
        self.assertEqual((self.repo / "app").read_bytes(), original)
        self.assertEqual((self.repo / "app").stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.repo / "capture.pcap").read_bytes(), b"\xd4\xc3\xb2\xa1original packet bytes\0")
        self.assertFalse((self.repo / "new.wasm").exists())

    def test_store_lock_and_index_repository_binding(self):
        (self.repo / "app.js").write_text(";")
        self.deploy()
        manifest = store.load_manifest(self.repo, self.index)
        journal = store.DeploymentStore(manifest["store"])
        with journal.locked():
            with self.assertRaisesRegex(ValueError, "busy"):
                store.status(self.repo, self.index)
        other = self.root / "other"
        other.mkdir()
        with self.assertRaisesRegex(ValueError, "repository"):
            store.load_manifest(other, self.index)

    def test_missing_index_pointer_can_be_recovered_from_shared_store(self):
        (self.repo / "app.js").write_text(";")
        shared = self.root / "shared-store"
        self.deploy(store_path=shared)
        self.index.unlink()
        result = store.recover(self.repo, self.index, store_path=shared, apply=False)
        self.assertEqual(result["status"], "removable")
        self.assertFalse(self.index.exists())
        store.recover(self.repo, self.index, store_path=shared, apply=True)
        self.assertEqual((self.repo / "app.js").read_text(), ";")

    def test_bom_source_and_multiple_placements_replay_without_changing_original_bytes(self):
        original = b'\xef\xbb\xbf# coding: utf-8\r\nvalue = "caf\xc3\xa9"\r\n'
        (self.repo / "app.py").write_bytes(original)
        catalog.add(self.library, identifier="control", text='annotation = "project convention"\n',
                    kind="source", language="python", benign=True)
        code, text = self.cli("deploy", "add", "--repo", str(self.repo), "--catalog", str(self.library),
                              "--benign", "--positions", "head,mid,tail", "--apply")
        self.assertEqual(code, 0, text)
        current = (self.repo / "app.py").read_bytes()
        self.assertTrue(current.startswith(b"\xef\xbb\xbf"))
        compile(current, "app.py", "exec")
        report = store.inspect(self.repo, self.index)
        self.assertNotIn("project convention", json.dumps(report))
        report = store.inspect(self.repo, self.index, include_text=True)
        self.assertIn("project convention", json.dumps(report))
        remove_deployment(repository=self.repo, apply=True)
        self.assertEqual((self.repo / "app.py").read_bytes(), original)

    def test_catalog_scaffold_initializes_after_checkout_without_replacing_existing_data(self):
        descriptor = (self.library / "catalog.json").read_bytes()
        fresh = self.root / "fresh"
        fresh.mkdir()
        (fresh / "catalog.json").write_bytes(descriptor)
        catalog.initialize(fresh)
        self.assertEqual(catalog.select(fresh), [])
        with self.assertRaisesRegex(ValueError, "already initialized"):
            catalog.initialize(fresh)

    def test_seal_does_not_accept_unrelated_source_changes(self):
        (self.repo / "app.js").write_text(";")
        (self.repo / "bundle.js").write_text("old build")
        self.deploy(target_files=[Path("app.js")], snapshots=[Path("bundle.js")])
        (self.repo / "bundle.js").write_text("new build")
        (self.repo / "app.js").write_text("unrelated user edit")
        with self.assertRaisesRegex(ValueError, "changed"):
            store.seal(self.repo, self.index)
        manifest = store.load_manifest(self.repo, self.index)
        self.assertTrue(next(row for row in manifest["files"] if row["path"] == "bundle.js")["pending"])


if __name__ == "__main__":
    unittest.main()
