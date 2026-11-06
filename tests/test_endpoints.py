import json
import tempfile
import unittest
from pathlib import Path

from clanker_repellent.inference.endpoints import is_allowed_base_url, load_endpoint_config


def config():
    return {
        "ssh": {
            "target": "user@example.test",
            "forwards": [
                {
                    "local_port": 18473,
                    "remote_host": "127.0.0.1",
                    "remote_port": 18473,
                }
            ],
        },
        "models": {
            "model-a": {
                "base_url": "http://127.0.0.1:18473/v1",
            }
        },
    }


class EndpointConfigTests(unittest.TestCase):
    def test_explicit_endpoint_keeps_generation_defaults_without_forwarding_credentials_or_ssh(self):
        original=config()
        original['generation']={'languages':['json'],'max_tokens':2048}
        original.pop('models')
        original['endpoint']={'base_url':'${UNSET_OLD_SERVER}', 'api_key_env':'UNSET_OLD_KEY', 'timeout_seconds':240}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json'
            path.write_text(json.dumps(original))
            loaded=load_endpoint_config(path,environ={},endpoint_override='http://127.0.0.1:18473/v1')
        self.assertNotIn('ssh',loaded)
        self.assertNotIn('api_key_env',loaded['models']['server'])
        self.assertEqual(loaded['models']['server']['base_url'],'http://127.0.0.1:18473/v1')
        self.assertEqual(loaded['generation'],original['generation'])
        self.assertEqual(loaded['models']['server']['timeout_seconds'],240)

    def test_explicit_endpoint_rejects_remote_http_credentials_and_url_query(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json'
            path.write_text(json.dumps(config()))
            for url in ['http://example.test:1234/v1','https://user:password@example.test/v1',
                        'http://127.0.0.1:1234/v1?key=secret','https://example.test/v1#fragment']:
                with self.subTest(url=url),self.assertRaises(ValueError):
                    load_endpoint_config(path,endpoint_override=url)

    def test_checked_in_routed_config_contains_only_environment_references(self):
        root = Path(__file__).resolve().parents[1]
        raw = (root / "configs/abliterated-local.json").read_text(encoding="utf-8")
        remote = (root / "configs/abliterated-remote.json").read_text(encoding="utf-8")
        example = (root / ".env.example").read_text(encoding="utf-8")

        self.assertIn("${GUARDRAIL_SSH_TARGET}", raw)
        self.assertEqual(raw.count("${REPEL_BASE_URL}"), 1)
        self.assertEqual(raw.count("${REPEL_LOCAL_PORT}"), 1)
        self.assertNotIn("glm-4.7", raw)
        self.assertNotIn("qwen3", raw.casefold())
        self.assertNotIn("http://", raw)
        self.assertNotRegex(raw, r"\b18\d{3}\b")
        self.assertNotRegex(raw, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        self.assertIn("REPEL_LOCAL_PORT=<local-port>", example)
        self.assertIn("REPEL_REMOTE_PORT=<remote-port>", example)
        self.assertIn(
            "REPEL_BASE_URL=<loopback-openai-base-url>", example
        )
        self.assertIn("${GUARDRAIL_BASE_URL}", remote)
        self.assertIn('"api_key_env": "GUARDRAIL_API_KEY"', remote)
        self.assertNotIn('"api_key"', remote)

    def test_loads_credential_free_direct_config(self):
        root = Path(__file__).resolve().parents[1]
        loaded = load_endpoint_config(
            root / "configs/abliterated-remote.json",
            environ={"GUARDRAIL_BASE_URL": "https://models.example/v1"},
        )

        self.assertEqual(loaded["_discovery_route"], "server")
        self.assertEqual(
            loaded["models"]["server"]["base_url"], "https://models.example/v1"
        )
        self.assertEqual(
            loaded["models"]["server"]["api_key_env"], "GUARDRAIL_API_KEY"
        )

    def test_url_policy_allows_https_and_explicit_loopback_only(self):
        self.assertTrue(is_allowed_base_url("https://models.example/v1"))
        self.assertTrue(is_allowed_base_url("http://127.0.0.1:18473/v1"))
        self.assertTrue(is_allowed_base_url("http://localhost:8000/v1"))
        self.assertFalse(is_allowed_base_url("http://models.example/v1"))
        self.assertFalse(is_allowed_base_url("http://127.0.0.1.evil.test:8000/v1"))
        self.assertFalse(is_allowed_base_url("http://127.0.0.1/v1"))

    def test_loads_credential_free_routed_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "endpoints.json"
            path.write_text(json.dumps(config()), encoding="utf-8")

            loaded = load_endpoint_config(path)

            self.assertEqual(loaded["ssh"]["startup_timeout_seconds"], 15.0)
            self.assertEqual(loaded["models"]["model-a"]["timeout_seconds"], 120.0)
            self.assertEqual(
                loaded["models"]["model-a"]["health_timeout_seconds"], 120.0
            )
            self.assertEqual(loaded["models"]["model-a"]["minimum_max_tokens"], 1)
            self.assertEqual(loaded["models"]["model-a"]["tool_mode"], "native")

    def test_normalizes_one_server_discovered_endpoint(self):
        value = config()
        value["endpoint"] = value.pop("models")["model-a"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "endpoints.json"
            path.write_text(json.dumps(value), encoding="utf-8")

            loaded = load_endpoint_config(path)

            self.assertEqual(loaded["_discovery_route"], "server")
            self.assertEqual(
                loaded["models"]["server"]["base_url"],
                "http://127.0.0.1:18473/v1",
            )

    def test_rejects_unforwarded_loopback_port(self):
        value = config()
        value["models"]["model-a"]["base_url"] = "http://127.0.0.1:19999/v1"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "endpoints.json"
            path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "not SSH-forwarded"):
                load_endpoint_config(path)

    def test_rejects_embedded_credentials(self):
        value = config()
        value["models"]["model-a"]["api_key"] = "do-not-store-this"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "endpoints.json"
            path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "credentials cannot be stored"):
                load_endpoint_config(path)

    def test_expands_endpoint_environment_references_and_numeric_ports(self):
        value = {
            "ssh": {
                "target": "${TEST_SSH_TARGET}",
                "forwards": [
                    {
                        "local_port": "${TEST_PORT}",
                        "remote_host": "${TEST_REMOTE_HOST}",
                        "remote_port": "${TEST_PORT}",
                    }
                ],
            },
            "models": {"model-a": {"base_url": "${TEST_BASE_URL}"}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "endpoints.json"
            path.write_text(json.dumps(value), encoding="utf-8")

            loaded = load_endpoint_config(
                path,
                environ={
                    "TEST_SSH_TARGET": "user@example.test",
                    "TEST_PORT": "19001",
                    "TEST_REMOTE_HOST": "127.0.0.1",
                    "TEST_BASE_URL": "http://127.0.0.1:19001/v1",
                },
            )

            self.assertEqual(loaded["ssh"]["forwards"][0]["local_port"], 19001)
            self.assertEqual(
                loaded["models"]["model-a"]["base_url"],
                "http://127.0.0.1:19001/v1",
            )

    def test_rejects_missing_or_malformed_environment_reference(self):
        value = config()
        value["ssh"]["target"] = "${MISSING_TARGET}"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "endpoints.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "MISSING_TARGET is not set"):
                load_endpoint_config(path, environ={})

            value["ssh"]["target"] = "${BROKEN"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid environment reference"):
                load_endpoint_config(path, environ={})


if __name__ == "__main__":
    unittest.main()
