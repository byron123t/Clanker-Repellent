import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clanker_repellent.dashboard.app import DashboardApp
from clanker_repellent.dashboard.reader import JournalReader, placement_spans
from clanker_repellent.payload.retained_deploy import deploy_retained
from clanker_repellent.payload import deployment_store as journal
from clanker_repellent.payload.carrier_deploy import INDEX_FILENAME, Carrier, deploy_carriers, remove_deployment
from clanker_repellent.payload.traffic import TrafficArchive
from clanker_repellent.cli.repo_tool import main


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "demo-project"
        self.repo.mkdir()
        for number in range(5):
            (self.repo / f"file{number}.js").write_text(f"const score = {number};\n")
        self.note = self.root / "control.txt"
        self.note.write_text('Ordinary documentation: <script>window.example = 1;</script>\n')
        result = deploy_retained(repository=self.repo, payloads=[self.note], benign=True,
                                 randomize=True, seed=42, count=2, apply=True)
        self.store, self.identity = Path(result["store"]), result["deployment_id"]
        self.reader = JournalReader(self.store)
        self.app = DashboardApp(self.store, "test-token")

    def request(self, path, *, auth=True, method="GET"):
        path, _, query = path.partition("?")
        env = {"PATH_INFO": path, "QUERY_STRING": query, "REQUEST_METHOD": method}
        if auth:
            env["HTTP_AUTHORIZATION"] = "Bearer test-token"
        captured = {}
        def start(status, headers):
            captured.update(status=status, headers=dict(headers))
        result = self.app(env, start)
        try:
            body = b"".join(result)
        finally:
            if hasattr(result, "close"):
                result.close()
        return captured, body

    def test_coverage_uses_presampling_compatible_denominator(self):
        detail = self.reader.deployment(self.identity)
        self.assertEqual(detail["metrics"]["coverage_percent"], 40.0)
        self.assertEqual(detail["metrics"]["eligible_files"], 5)
        self.assertEqual(detail["metrics"]["placed_files"], 2)
        self.assertEqual(len(detail["eligible_paths"]), 5)
        self.assertEqual(detail["selection"]["seed"], 42)
        self.assertIsNotNone(detail["created_at"])
        self.assertGreater(detail["metrics"]["density_percent"], 0)

    def test_explicit_target_scope_and_snapshot_artifacts_do_not_inflate_coverage(self):
        remove_deployment(repository=self.repo, apply=True)
        (self.repo / "app.bin").write_bytes(b"original binary\0")
        result = deploy_retained(repository=self.repo, payloads=[self.note], benign=True,
                                 target_files=[Path("file0.js")], snapshots=[Path("app.bin")], apply=True)
        detail = self.reader.deployment(result["deployment_id"])
        self.assertEqual(detail["metrics"]["eligible_files"], 1)
        self.assertEqual(detail["metrics"]["placed_files"], 1)
        self.assertEqual(detail["metrics"]["coverage_percent"], 100.0)
        self.assertEqual(detail["metrics"]["scope"], "explicit targets")
        self.assertEqual(detail["metrics"]["artifacts"], 1)

    def test_snapshot_only_record_does_not_claim_coverage(self):
        remove_deployment(repository=self.repo, apply=True)
        manifest = {"kind": "repel_carrier_deployment", "repository_root": str(self.repo), "files": []}
        journal.apply_plan(self.repo, self.repo / INDEX_FILENAME, manifest, {}, snapshots=[Path("file0.js")])
        detail = self.reader.deployment(manifest["deployment_id"])
        self.assertEqual(detail["mode"], "snapshot")
        self.assertIsNone(detail["metrics"]["coverage_percent"])
        self.assertEqual(detail["metrics"]["inserted_bytes"], 0)

    def test_source_coverage_counts_only_language_compatible_files_and_all_insertions(self):
        remove_deployment(repository=self.repo, apply=True)
        for number in range(3):
            (self.repo / f"module{number}.py").write_text("value = 42\n")
        snippet = 'note = "ordinary control"\n'
        carrier = Carrier("python-control", "python", snippet, journal.digest(snippet.encode()), "control.py")
        result = deploy_carriers(repository=self.repo, carriers=[carrier], randomize=True, seed=9,
                                 count=1, positions=["head", "mid", "tail"], apply=True)
        detail = self.reader.deployment(result["deployment_id"])
        self.assertEqual(detail["metrics"]["eligible_files"], 3)
        self.assertEqual(detail["metrics"]["coverage_percent"], 33.3)
        self.assertEqual(detail["metrics"]["placements"], 3)
        self.assertTrue(all(p.endswith(".py") for p in detail["eligible_paths"]))

    def test_old_journal_has_unknown_denominator_without_fabricated_coverage(self):
        store = journal.DeploymentStore(self.store)
        with store.locked() as db:
            manifest, state = store.read(db, self.identity, self.repo, self.repo / INDEX_FILENAME)
            manifest.pop("coverage")
            store.write(db, self.identity, manifest, state)
        detail = self.reader.deployment(self.identity)
        self.assertIsNone(detail["metrics"]["coverage_percent"])
        self.assertEqual(detail["metrics"]["placed_files"], 2)

    def test_summary_never_returns_snippet_or_original_text(self):
        header, body = self.request("/api/summary")
        self.assertEqual(header["status"], "200 OK")
        self.assertNotIn(b"Ordinary documentation", body)
        self.assertNotIn(b"window.example", body)
        self.assertNotIn(b"const score", body)
        self.assertEqual(header["headers"]["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", header["headers"])
        self.assertEqual(json.loads(body)["deployments"][0]["id"], self.identity)
        self.assertEqual(json.loads(body)["deployments"][0]["types"], ["javascript_global_data"])

    def test_typescript_retention_is_identified_in_summary_and_file_view(self):
        remove_deployment(repository=self.repo, apply=True)
        (self.repo / "entry.ts").write_text("export const value: number = 42;\n")
        result = deploy_retained(repository=self.repo, payloads=[self.note], benign=True,
                                 target_files=[Path("entry.ts")], apply=True)
        detail = self.reader.deployment(result["deployment_id"])
        self.assertEqual(detail["types"], ["typescript"])
        self.assertEqual(detail["files"][0]["kind"], "typescript")

    def test_authenticated_explicit_preview_and_download_are_exact(self):
        route = f"/api/deployments/{self.identity}"
        header, body = self.request(route + "/preview?file=0&step=0&version=insertion")
        self.assertEqual(header["status"], "200 OK")
        snippet = json.loads(body)
        self.assertIn("Ordinary documentation", snippet["text"])
        self.assertFalse(snippet["truncated"])
        manifest = journal.load_manifest(self.repo, self.repo / INDEX_FILENAME)
        expected = journal.DeploymentStore(self.store).get(manifest["files"][0]["before_sha256"])
        header, original = self.request(route + "/download?file=0&version=before")
        self.assertEqual(original, expected)
        self.assertEqual(header["headers"]["Content-Type"], "application/octet-stream")
        self.assertTrue(header["headers"]["Content-Disposition"].startswith("attachment;"))

    def test_authentication_invalid_routes_and_writes_are_rejected(self):
        for route in ["/api/summary", f"/api/deployments/{self.identity}/download?file=0&version=before"]:
            self.assertEqual(self.request(route, auth=False)[0]["status"], "401 Unauthorized")
        self.assertEqual(self.request("/api/summary", method="POST")[0]["status"], "405 Method Not Allowed")
        self.assertEqual(self.request("/../../pyproject.toml")[0]["status"], "404 Not Found")
        self.assertEqual(self.request(f"/api/deployments/{self.identity}/preview?file=-1")[0]["status"], "404 Not Found")
        self.assertEqual(self.request(f"/api/deployments/{self.identity}/preview?file=invalid")[0]["status"], "422 Unprocessable Content")

    def test_checksum_failure_withholds_object_content(self):
        manifest = journal.load_manifest(self.repo, self.repo / INDEX_FILENAME)
        key = manifest["files"][0]["edits"][0]["inserted_sha256"]
        (self.store / "objects" / key[:2] / key).write_bytes(b"corrupt secret content")
        header, body = self.request(f"/api/deployments/{self.identity}/preview?file=0")
        self.assertEqual(header["status"], "422 Unprocessable Content")
        self.assertNotIn(b"secret content", body)

    def test_summary_withholds_corrupt_manifest_and_keeps_other_records_visible(self):
        with journal.DeploymentStore(self.store).locked() as db:
            db.execute("UPDATE deployments SET manifest='{}' WHERE id=?", (self.identity,))
        result = self.reader.summary()
        self.assertEqual(result["deployments"], [])
        self.assertEqual(len(result["errors"]), 1)

    def test_dashboard_does_not_modify_journal_or_scan_live_targets(self):
        db = self.store / "journal.sqlite3"
        before, mtime = db.read_bytes(), db.stat().st_mtime_ns
        with mock.patch.object(journal.DeploymentStore, "locked", side_effect=AssertionError("write lock used")):
            self.reader.summary()
            self.reader.deployment(self.identity)
            self.request(f"/api/deployments/{self.identity}/preview?file=0&version=before")
        self.assertEqual(db.read_bytes(), before)
        self.assertEqual(db.stat().st_mtime_ns, mtime)
        for path in self.repo.glob("*.js"):
            path.unlink()
        self.assertEqual(self.reader.deployment(self.identity)["metrics"]["coverage_percent"], 40.0)

    def test_restored_deployment_stays_inspectable_and_is_labeled_historical(self):
        remove_deployment(repository=self.repo, apply=True)
        detail = self.reader.deployment(self.identity)
        self.assertEqual(detail["state"], "restored")
        self.assertEqual(detail["metrics"]["coverage_percent"], 40.0)
        self.assertEqual(self.request(f"/api/deployments/{self.identity}/preview?file=0")[0]["status"], "200 OK")

    def test_binary_preview_and_multibyte_truncation_are_explicit(self):
        store = journal.DeploymentStore(self.store)
        binary = b"\0\xff\xfe\x01"
        preview = self.reader.preview(store.put(binary))
        self.assertEqual(preview["encoding"], "base64")
        self.assertEqual(base64.b64decode(preview["text"]), binary)
        preview = self.reader.preview(store.put("abc🎲def".encode()), limit=5)
        self.assertEqual(preview["encoding"], "utf-8")
        self.assertEqual(preview["text"], "abc")
        self.assertTrue(preview["truncated"])

    def test_response_archive_hides_headers_and_downloads_original_entity(self):
        archive = TrafficArchive(self.store)
        identity = archive.record(b"original body", b"modified body", status="200 OK",
                                  headers_before=[("Set-Cookie", "secret=1"), ("Content-Type", "text/plain")],
                                  headers_after=[], request={"method": "GET", "path": "/example"})
        _, raw = self.request("/api/responses")
        self.assertNotIn(b"secret=1", raw)
        self.assertNotIn(b"original body", raw)
        self.assertEqual(self.request(f"/api/responses/{identity}/download?version=before")[1], b"original body")

    def test_final_byte_spans_handle_later_insertions_and_removals(self):
        row = {"bytes_before": 10, "bytes_after": 16, "edits": [
            {"offset_before_step": 5, "removed_bytes": 0, "inserted_bytes": 5},
            {"offset_before_step": 7, "removed_bytes": 1, "inserted_bytes": 2}]}
        spans = placement_spans(row)
        self.assertEqual([(s["start"], s["end"], s["step"]) for s in spans], [(5, 7, 0), (7, 9, 1), (9, 11, 0)])
        self.assertEqual(sum(s["end"] - s["start"] for s in spans), 6)

    def test_dashboard_command_help_and_assets(self):
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit):
            main(["dashboard", "--help"])
        self.assertIn("--store", out.getvalue())
        self.assertIn("--demo", out.getvalue())
        self.assertIn("--assets", out.getvalue())
        for path in ["/", "/app.js", "/style.css", "/favicon.svg"]:
            self.assertEqual(self.request(path, auth=False)[0]["status"], "200 OK")

    def test_isolated_frontend_override_keeps_real_journal_api(self):
        assets = self.root / "candidate-web"
        assets.mkdir()
        for name in ("index.html", "app.js", "style.css", "favicon.svg"):
            (assets / name).write_text("isolated candidate " + name)
        self.app = DashboardApp(self.store, "test-token", assets=assets)
        self.assertEqual(self.request("/", auth=False)[1], b"isolated candidate index.html")
        self.assertEqual(json.loads(self.request("/api/summary")[1])["deployments"][0]["id"], self.identity)
        self.assertEqual(self.request("/../journal.sqlite3")[0]["status"], "404 Not Found")
        (assets / "app.js").unlink()
        with self.assertRaises(ValueError): DashboardApp(self.store, "test-token", assets=assets)


if __name__ == "__main__":
    unittest.main()
