import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preview import PreviewApp


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.app = PreviewApp("test-token")

    def request(self, url, *, token="test-token", method="GET", app=None):
        path, _, query = url.partition("?")
        meta = {}
        def start(status, headers):
            meta.update(status=status, headers=dict(headers))
        raw = b"".join((app or self.app)({"REQUEST_METHOD": method, "PATH_INFO": path,
            "QUERY_STRING": query, "HTTP_AUTHORIZATION": "Bearer " + token}, start))
        return meta, raw

    def test_authentication_and_read_only_access(self):
        self.assertEqual(self.request("/api/summary", token="wrong")[0]["status"], "401 Unauthorized")
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertEqual(self.request("/api/summary", method=method)[0]["status"], "405 Method Not Allowed")
        self.assertEqual(self.request("/api/unknown")[0]["status"], "404 Not Found")

    def test_only_frontend_assets_are_public(self):
        for url in ("/", "/app.js", "/style.css", "/favicon.svg"):
            meta, raw = self.request(url, token="")
            self.assertEqual(meta["status"], "200 OK")
            self.assertTrue(raw)
            self.assertIn("script-src 'self'", meta["headers"]["Content-Security-Policy"])
        for url in ("/../preview.py", "/fixtures/responses.json", "/preview.py"):
            self.assertEqual(self.request(url)[0]["status"], "404 Not Found")

    def test_populated_empty_and_error_states(self):
        summary = json.loads(self.request("/api/summary")[1])
        self.assertTrue(summary["template"])
        self.assertEqual(len(summary["deployments"]), 7)
        empty = json.loads(self.request("/api/summary", app=PreviewApp("test-token", "empty"))[1])
        self.assertEqual(empty["deployments"], [])
        self.assertEqual(empty["response_count"], 0)
        self.assertEqual(self.request("/api/summary", app=PreviewApp("test-token", "error"))[0]["status"], "503 Service Unavailable")

    def test_query_order_aliases_and_exact_download(self):
        summary = json.loads(self.request("/api/summary")[1])
        route = "/api/deployments/" + summary["deployments"][0]["id"]
        urls = [route + "/preview?file=0&step=0&version=before",
                route + "/preview?version=before&step=0&file=0",
                route + "/preview?file=0&version=before"]
        previews = [self.request(url) for url in urls]
        self.assertTrue(all(meta["status"] == "200 OK" for meta, _ in previews))
        self.assertTrue(all(raw == previews[0][1] for _, raw in previews))
        preview = json.loads(previews[0][1])
        meta, body = self.request(route + "/download?file=0&step=0&version=before")
        self.assertEqual(hashlib.sha256(body).hexdigest(), preview["sha256"])
        self.assertEqual(len(body), preview["bytes"])
        self.assertIn("attachment", meta["headers"]["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()
