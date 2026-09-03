import unittest
from unittest.mock import MagicMock, patch

from clanker_repellent.inference.tunnel import (
    build_interactive_ssh_command,
    build_ssh_command,
    managed_ssh_tunnel,
)


class TunnelTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "target": "user@example.test",
            "startup_timeout_seconds": 2.0,
            "forwards": [
                {
                    "local_port": 18473,
                    "remote_host": "127.0.0.1",
                    "remote_port": 18473,
                },
                {
                    "local_port": 18474,
                    "remote_host": "127.0.0.1",
                    "remote_port": 18474,
                },
            ],
        }

    def test_command_has_fixed_safe_options_and_loopback_binds(self):
        command = build_ssh_command(self.config, self.config["forwards"])

        self.assertEqual(command[:2], ["ssh", "-N"])
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertIn("ExitOnForwardFailure=yes", command)
        self.assertIn("127.0.0.1:18473:127.0.0.1:18473", command)
        self.assertEqual(command[-1], "user@example.test")

    def test_interactive_command_prompts_via_ssh_and_uses_control_master(self):
        command = build_interactive_ssh_command(
            self.config, self.config["forwards"], "/tmp/test-control"
        )

        self.assertIn("-f", command)
        self.assertIn("-M", command)
        self.assertIn("/tmp/test-control", command)
        self.assertNotIn("BatchMode=yes", command)
        self.assertIn("StrictHostKeyChecking=yes", command)

    @patch("clanker_repellent.inference.tunnel._interactive_ssh_tunnel")
    @patch("clanker_repellent.inference.tunnel._port_is_open", return_value=False)
    def test_interactive_auth_uses_interactive_manager(self, _open, interactive):
        interactive.return_value.__enter__.return_value = {
            "status": "started",
            "authentication": "interactive",
        }

        with managed_ssh_tunnel(self.config, interactive_auth=True) as state:
            self.assertEqual(state["authentication"], "interactive")

        interactive.assert_called_once()

    @patch("clanker_repellent.inference.tunnel.subprocess.Popen")
    @patch("clanker_repellent.inference.tunnel._port_is_open", return_value=True)
    def test_reuses_existing_tunnel_without_spawning(self, _open, popen):
        with managed_ssh_tunnel(self.config) as state:
            self.assertEqual(state["status"], "reused")

        popen.assert_not_called()

    @patch("clanker_repellent.inference.tunnel._wait_for_ports")
    @patch("clanker_repellent.inference.tunnel.subprocess.Popen")
    @patch("clanker_repellent.inference.tunnel._port_is_open", return_value=False)
    def test_starts_and_stops_only_managed_process(self, _open, popen, wait_for_ports):
        process = MagicMock()
        process.poll.return_value = None
        popen.return_value = process

        with managed_ssh_tunnel(self.config) as state:
            self.assertEqual(state["status"], "started")

        wait_for_ports.assert_called_once()
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)


if __name__ == "__main__":
    unittest.main()
