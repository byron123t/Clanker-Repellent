import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from clanker_repellent.payload.hash_share import (
    HASH_SHARE_KIND,
    VERIFY_STATE_MISMATCH,
    VERIFY_STATE_VERIFIED,
    create_hash_share,
    verify_hash_share,
    write_hash_share,
)
from clanker_repellent.cli.repo_tool import main


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class HashShareTests(unittest.TestCase):
    def _fixture(self):
        root = Path(tempfile.mkdtemp())
        repository = root / "repo"
        repository.mkdir()
        clean_source = b"print('clean')\n"
        scattered_source = clean_source + b"# indexed change\n"
        created_source = b"# indexed carrier\n"
        (repository / "app.py").write_bytes(scattered_source)
        (repository / "carrier.py").write_bytes(created_source)
        index = {
            "schema_version": 5,
            "mode": "apply",
            "repository_root": str(repository.resolve()),
            "strategy": "replicated",
            "payload_sha256": _sha256(b"BENIGN_SENTINEL_PAYLOAD"),
            "payload_pool": [
                {"id": "benign-sentinel", "sha256": _sha256(b"BENIGN_SENTINEL_PAYLOAD")}
            ],
            "injections": [
                {
                    "path": "app.py",
                    "before_sha256": _sha256(clean_source),
                    "after_sha256": _sha256(scattered_source),
                },
                {
                    "path": "carrier.py",
                    "before_sha256": None,
                    "after_sha256": _sha256(created_source),
                },
            ],
        }
        return root, repository, index, clean_source

    def test_payload_present_share_round_trips_without_payload_text(self):
        root, repository, index, clean_source = self._fixture()
        try:
            share = create_hash_share(repository, index, expected_state="current")
            serialized = json.dumps(share)
            self.assertEqual(share["kind"], HASH_SHARE_KIND)
            self.assertEqual(share["expected_state"], "payload_present")
            self.assertNotIn("BENIGN_SENTINEL_PAYLOAD", serialized)
            self.assertNotIn("REPEL_BASE_URL", serialized)
            self.assertNotIn("API_KEY", serialized)

            share_path = root / ".repel-hashes.json"
            write_hash_share(share, share_path)
            result = verify_hash_share(repository, share_path)
            self.assertEqual(result["state"], VERIFY_STATE_VERIFIED)
            self.assertEqual(result["files_checked"], 2)

            (repository / "app.py").write_bytes(clean_source)
            result = verify_hash_share(repository, share_path)
            self.assertEqual(result["state"], VERIFY_STATE_MISMATCH)
            self.assertEqual(result["mismatches"][0]["path"], "app.py")
        finally:
            for path in sorted(root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()

    def test_clean_share_can_be_created_from_a_payloaded_index(self):
        root, repository, index, clean_source = self._fixture()
        try:
            (repository / "app.py").write_bytes(clean_source)
            (repository / "carrier.py").unlink()
            share = create_hash_share(repository, index, expected_state="clean")
            share_path = root / ".repel-hashes.json"
            write_hash_share(share, share_path)
            result = verify_hash_share(repository, share_path)
            self.assertEqual(result["expected_state"], "clean")
            self.assertEqual(result["state"], VERIFY_STATE_VERIFIED)
            self.assertFalse(share["file_hashes"][1]["present"])
        finally:
            for path in sorted(root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()

    def test_cli_share_and_verify_use_hash_only_artifact(self):
        root, repository, index, _ = self._fixture()
        try:
            index_path = root / "scatter-index.json"
            index_path.write_text(json.dumps(index), encoding="utf-8")
            share_path = root / ".repel-hashes.json"
            with contextlib.redirect_stdout(io.StringIO()) as output:
                shared = main(
                    [
                        "share",
                        "--repo",
                        str(repository),
                        "--index",
                        str(index_path),
                        "--output",
                        str(share_path),
                    ]
                )
            self.assertEqual(shared, 0)
            self.assertEqual(json.loads(output.getvalue())["file_count"], 2)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                verified = main(
                    [
                        "verify",
                        "--repo",
                        str(repository),
                        "--hashes",
                        str(share_path),
                    ]
                )
            self.assertEqual(verified, 0)
            self.assertEqual(json.loads(output.getvalue())["state"], VERIFY_STATE_VERIFIED)
        finally:
            for path in sorted(root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()


if __name__ == "__main__":
    unittest.main()
