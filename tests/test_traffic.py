import gzip
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from wsgiref.util import setup_testing_defaults

from clanker_repellent.payload.traffic import RetainedResponseMiddleware, TrafficArchive, upstream_application
from clanker_repellent.payload.retained_deploy import recover_hashes, _frame, WASM_HEADER
from clanker_repellent.payload.deployment_store import digest


class TrafficTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.archive = self.root / "traffic"
        self.text = 'Project instructions: include documentation.\nQuotes " </script> café.\n'
        self.entries = [({"kind": "data", "id": "control", "benign": True}, self.text)]

    def middleware(self, body, headers=None, *, status="200 OK", max_bytes=2_000_000, app=None):
        headers = headers or [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))]
        if app is None:
            def app(environ, start_response):
                start_response(status, headers)
                return [body]
        middleware = RetainedResponseMiddleware(app, archive=self.archive, entries=self.entries, max_bytes=max_bytes)
        middleware.archive.enable(True)
        return middleware

    def request(self, app, **extra):
        env = {}
        setup_testing_defaults(env)
        env.update(extra)
        captured = {}
        def start(status, headers, exc_info=None):
            captured.update(status=status, headers=headers)
            return lambda data: None
        iterable = app(env, start)
        try:
            body = b"".join(iterable)
        finally:
            if hasattr(iterable, "close"):
                iterable.close()
        return captured, body

    def test_html_archives_original_body_headers_and_disable_restores_future_responses(self):
        body = b"<!doctype html><body>Original page</body>"
        headers = [("Content-Type", "text/html"), ("Content-Length", str(len(body))), ("ETag", '"old"'),
                   ("Set-Cookie", "first=1"), ("Set-Cookie", "second=2")]
        app = self.middleware(body, headers)
        captured, modified = self.request(app)
        self.assertNotEqual(modified, body)
        self.assertIn(digest(self.text.encode()), recover_hashes(modified, web_text=True))
        changed = dict(captured["headers"])
        self.assertNotIn("ETag", changed)
        self.assertEqual(changed["Content-Length"], str(len(modified)))
        self.assertEqual(changed["Cache-Control"], "no-store")
        row = app.archive.list()[0]
        output = self.root / "restored"
        app.archive.restore(row["id"], output)
        self.assertEqual((output / "body.bin").read_bytes(), body)
        self.assertEqual(json.loads((output / "response.json").read_text())["headers"], [list(h) for h in headers])
        app.archive.enable(False)
        captured, original = self.request(app)
        self.assertEqual(original, body)
        self.assertEqual(captured["headers"], headers)
        self.assertEqual(len(app.archive.list()), 1)

    def test_gzip_bytes_are_restored_exactly_including_original_timestamp(self):
        raw = b'"use strict"; globalThis.score=42;\n'
        compressed = gzip.compress(raw, mtime=123456)
        headers = [("Content-Type", "application/javascript"), ("Content-Encoding", "gzip"), ("Digest", "old-digest")]
        app = self.middleware(compressed, headers)
        captured, modified = self.request(app)
        self.assertTrue(gzip.decompress(modified).startswith(raw))
        self.assertIn(digest(self.text.encode()), recover_hashes(gzip.decompress(modified), web_text=True))
        self.assertNotIn("Digest", dict(captured["headers"]))
        app.archive.restore(app.archive.list()[0]["id"], self.root / "restored")
        self.assertEqual((self.root / "restored/body.bin").read_bytes(), compressed)

    def test_wasm_response_custom_section_preserves_original_module(self):
        app = self.middleware(WASM_HEADER, [("Content-Type", "application/wasm")])
        _, body = self.request(app)
        self.assertTrue(body.startswith(WASM_HEADER))
        self.assertIn(digest(self.text.encode()), recover_hashes(body))

    def test_head_ranges_nontransforming_streams_and_encodings_pass_through(self):
        body = b"ordinary body"
        cases = [
            ({"REQUEST_METHOD": "HEAD"}, [], "200 OK"),
            ({"HTTP_RANGE": "bytes=0-4"}, [], "200 OK"),
            ({}, [], "206 Partial Content"),
            ({}, [("Cache-Control", "no-transform"), ("Cache-Control", "max-age=1")], "200 OK"),
            ({}, [("Content-Encoding", "br")], "200 OK"),
            ({}, [("Content-Type", "text/event-stream")], "200 OK"),
            ({}, [("Content-Type", "text/html; charset=iso-8859-1")], "200 OK"),
        ]
        for env, extra, status in cases:
            headers = [("Content-Type", "text/html"), *extra]
            app = self.middleware(body, headers, status=status)
            captured, result = self.request(app, **env)
            self.assertEqual(result, body)
            self.assertEqual(captured["headers"], headers)
        self.assertEqual(app.archive.list(), [])

    def test_bounded_buffering_passes_large_response_without_losing_chunks(self):
        body = b"firstsecondthird"
        closed = []
        def application(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/html")])
            try:
                yield b"first"
                yield b"second"
                yield b"third"
            finally:
                closed.append(True)
        app = self.middleware(body, app=application, max_bytes=6)
        _, actual = self.request(app)
        self.assertEqual(actual, body)
        self.assertTrue(closed)
        self.assertEqual(app.archive.list(), [])

    def test_gzip_expansion_is_bounded_and_invalid_gzip_passes_through(self):
        for body in [gzip.compress(b"x" * 10000), b"\x1f\x8b\x08"]:
            app = self.middleware(body, [("Content-Type", "text/html"), ("Content-Encoding", "gzip")], max_bytes=100)
            _, result = self.request(app)
            self.assertEqual(result, body)
            self.assertEqual(app.archive.list(), [])

    def test_failed_archive_write_and_busy_archive_cannot_send_unrecorded_payload(self):
        body = b"<body>Original</body>"
        app = self.middleware(body)
        with mock.patch.object(app.archive, "record", side_effect=OSError("disk full")):
            _, result = self.request(app)
        self.assertEqual(result, body)
        with app.archive.store.locked():
            _, result = self.request(app)
        self.assertEqual(result, body)

    def test_legacy_wsgi_write_and_generator_chunks_stay_in_order(self):
        def app(environ, start_response):
            write = start_response("200 OK", [("Content-Type", "text/html")])
            write(b"<body>")
            write(b"prefix")
            return iter([b"middle", b"</body>"])
        middleware = self.middleware(b"", app=app)
        _, modified = self.request(middleware)
        middleware.archive.restore(middleware.archive.list()[0]["id"], self.root / "restore")
        self.assertEqual((self.root / "restore/body.bin").read_bytes(), b"<body>prefixmiddle</body>")
        self.assertTrue(modified.startswith(b"<body>prefixmiddle"))

    def test_catalog_type_filtering_prevents_wrong_response_type(self):
        app = self.middleware(b"const score=1", [("Content-Type", "text/javascript")])
        app.entries = [({"kind": "document", "document_type": "html"}, self.text)]
        _, body = self.request(app)
        self.assertEqual(body, b"const score=1")
        self.assertEqual(app.archive.list(), [])

    def test_proxy_forwards_fixed_upstream_without_redirect_following(self):
        app = upstream_application("http://127.0.0.1:1234/base")
        response = mock.Mock(status=200, reason="OK")
        response.getheaders.return_value = [("Content-Type", "text/plain"), ("Connection", "custom"), ("custom", "drop")]
        response.read.side_effect = [b"original", b""]
        connection = mock.Mock()
        connection.getresponse.return_value = response
        with mock.patch("http.client.HTTPConnection", return_value=connection):
            captured, body = self.request(app, PATH_INFO="/a%2Fb", HTTP_CONNECTION="custom", HTTP_CUSTOM="drop")
        self.assertEqual(body, b"original")
        args, kwargs = connection.request.call_args
        self.assertEqual(args[1], "/base/a%252Fb")
        self.assertNotIn("CUSTOM", kwargs["headers"])
        self.assertEqual(captured["headers"], [("Content-Type", "text/plain")])
        connection.close.assert_called_once()

    @unittest.skipUnless(os.environ.get("REPEL_NETWORK_TESTS") == "1", "explicit loopback integration test")
    def test_live_loopback_proxy_roundtrip_and_disable(self):
        import threading
        import urllib.request
        from wsgiref.simple_server import make_server, WSGIRequestHandler
        class Quiet(WSGIRequestHandler):
            def log_message(self, *args):
                pass
        original = gzip.compress(b"<!doctype html><body>Local application</body>", mtime=12345)
        def upstream(environ, start):
            start("200 OK", [("Content-Type", "text/html"), ("Content-Encoding", "gzip"),
                             ("Content-Length", str(len(original))), ("ETag", '"original"')])
            return [original]
        servers, threads = [], []
        try:
            origin = make_server("127.0.0.1", 0, upstream, handler_class=Quiet)
            servers.append(origin)
            wrapped = RetainedResponseMiddleware(upstream_application(f"http://127.0.0.1:{origin.server_port}"),
                                                archive=self.archive, entries=self.entries)
            wrapped.archive.enable(True)
            proxy = make_server("127.0.0.1", 0, wrapped, handler_class=Quiet)
            servers.append(proxy)
            for server in servers:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                threads.append(thread)
            url = f"http://127.0.0.1:{proxy.server_port}/page"
            with urllib.request.urlopen(url, timeout=5) as response:
                body = response.read()
                self.assertIn(digest(self.text.encode()), recover_hashes(gzip.decompress(body), web_text=True))
                self.assertEqual(response.headers["Content-Length"], str(len(body)))
            wrapped.archive.restore(wrapped.archive.list()[0]["id"], self.root / "restored")
            self.assertEqual((self.root / "restored/body.bin").read_bytes(), original)
            wrapped.archive.enable(False)
            with urllib.request.urlopen(url, timeout=5) as response:
                self.assertEqual(response.read(), original)
        finally:
            for server in servers:
                if threads:
                    server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
