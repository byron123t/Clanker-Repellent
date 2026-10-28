import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from serve import FixtureApp


class PortableTemplateTests(unittest.TestCase):
    def setUp(self):
        self.app = FixtureApp("test-token")

    def request(self, path, *, token="test-token", method="GET", app=None):
        route, _, query = path.partition("?")
        captured = {}
        def start(status, headers):
            captured.update(status=status, headers=dict(headers))
        body = b"".join((app or self.app)({"PATH_INFO": route, "QUERY_STRING": query,
            "REQUEST_METHOD": method, "HTTP_AUTHORIZATION": "Bearer " + token}, start))
        return captured, body

    def test_static_assets_do_not_require_authentication(self):
        for path in ("/", "/app.js", "/style.css", "/favicon.svg"):
            meta, body = self.request(path, token="")
            self.assertEqual(meta["status"], "200 OK")
            self.assertTrue(body)
        self.assertEqual(self.request("/fixtures/objects.json")[0]["status"], "404 Not Found")
        self.assertEqual(self.request("/../serve.py")[0]["status"], "404 Not Found")

    def test_authentication_read_only_and_scenarios(self):
        self.assertEqual(self.request("/api/summary", token="wrong")[0]["status"], "401 Unauthorized")
        record = next(iter(self.app.journal["deployments"].values()))
        for path in ("/api/summary", f'/api/deployments/{record["id"]}', "/api/responses"):
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                self.assertEqual(self.request(path, method=method)[0]["status"], "405 Method Not Allowed")
        self.assertEqual(self.request("/api/summary", app=FixtureApp("test-token", "error"))[0]["status"], "503 Service Unavailable")
        empty = json.loads(self.request("/api/summary", app=FixtureApp("test-token", "empty"))[1])
        self.assertEqual(empty["deployments"], [])
        self.assertEqual(empty["response_count"], 0)

    def test_fixture_metrics_and_byte_edits_are_consistent(self):
        for record in self.app.journal["deployments"].values():
            files = [row for row in record["files"] if row["role"] == "placement"]
            self.assertEqual(len(files), record["metrics"]["placed_files"])
            for row in files:
                before, after = self.app.object(row["before_sha256"]), self.app.object(row["after_sha256"])
                edit = row["edits"][0]; inserted = self.app.object(edit["sha256"]); offset = edit["offset"]
                self.assertEqual(before[:offset] + inserted + before[offset:], after)
                self.assertEqual(len(inserted), row["inserted_bytes"])
                self.assertEqual(row["spans"][0]["start"], offset)
                self.assertEqual(row["spans"][0]["end"], offset + len(inserted))
            if record["metrics"]["eligible_files"] is None:
                self.assertIsNone(record["metrics"]["coverage_percent"])
        self.assertTrue(self.app.journal["summary"]["template"])
        self.assertNotIn("examples use consistent names", self.request("/api/summary")[1].decode())

    def test_previews_and_downloads_preserve_exact_objects(self):
        for record in self.app.journal["deployments"].values():
            for row in record["files"]:
                route = f'/api/deployments/{record["id"]}'
                for version in ("before", "after"):
                    meta, body = self.request(f'{route}/download?file={row["number"]}&version={version}')
                    self.assertEqual(meta["status"], "200 OK")
                    self.assertEqual(hashlib.sha256(body).hexdigest(), row[version + "_sha256"])
                if row["edits"]:
                    preview = json.loads(self.request(f'{route}/preview?file={row["number"]}')[1])
                    self.assertEqual(preview["sha256"], row["edits"][0]["sha256"])
        record = next(iter(self.app.journal["deployments"].values()))
        self.assertEqual(self.request(f'/api/deployments/{record["id"]}/preview?file=-1')[0]["status"], "404 Not Found")

    def test_binary_response_and_integrity_failure(self):
        for response in self.app.journal["responses"]:
            for version in ("before", "after"):
                route = f'/api/responses/{response["id"]}/download?version={version}'
                meta, body = self.request(route)
                self.assertEqual(meta["status"], "200 OK")
                self.assertEqual(hashlib.sha256(body).hexdigest(), response[version + "_sha256"])
        record = self.app.journal["responses"][-1]
        route = f'/api/responses/{record["id"]}/preview?version=before'
        self.assertEqual(json.loads(self.request(route)[1])["encoding"], "base64")
        self.app.objects[record["before_sha256"]] = "Y29ycnVwdA=="
        self.assertEqual(self.request(route)[0]["status"], "422 Unprocessable Content")


if __name__ == "__main__": unittest.main()
