"""Lifecycle management for bounded, loopback-only SSH port forwarding."""

from __future__ import annotations

import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List


def _port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def build_ssh_command(ssh_config: Dict[str, Any], forwards: Iterable[Dict[str, Any]]) -> List[str]:
    command = [
        "ssh",
        "-N",
        "-o",
        "BatchMode=yes",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
    ]
    for forward in forwards:
        command.extend(
            [
                "-L",
                "127.0.0.1:{local_port}:{remote_host}:{remote_port}".format(**forward),
            ]
        )
    command.append(ssh_config["target"])
    return command


def build_interactive_ssh_command(
    ssh_config: Dict[str, Any],
    forwards: Iterable[Dict[str, Any]],
    control_path: str,
) -> List[str]:
    """Build a foreground-authenticated master that backgrounds after login."""

    command = [
        "ssh",
        "-N",
        "-f",
        "-M",
        "-S",
        control_path,
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
    ]
    for forward in forwards:
        command.extend(
            [
                "-L",
                "127.0.0.1:{local_port}:{remote_host}:{remote_port}".format(**forward),
            ]
        )
    command.append(ssh_config["target"])
    return command


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _wait_for_ports(
    process: subprocess.Popen, ports: Iterable[int], timeout_seconds: float
) -> None:
    deadline = time.monotonic() + timeout_seconds
    ports = list(ports)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr is not None else ""
            raise RuntimeError(f"SSH tunnel exited before becoming ready: {stderr.strip()[:500]}")
        if all(_port_is_open(port) for port in ports):
            return
        time.sleep(0.1)
    raise TimeoutError(f"SSH tunnel did not open local ports {ports} within {timeout_seconds}s")


def _wait_for_open_ports(ports: Iterable[int], timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    ports = list(ports)
    while time.monotonic() < deadline:
        if all(_port_is_open(port) for port in ports):
            return
        time.sleep(0.1)
    raise TimeoutError(f"SSH tunnel did not open local ports {ports} within {timeout_seconds}s")


def _close_control_master(control_path: str, target: str) -> None:
    try:
        subprocess.run(
            ["ssh", "-S", control_path, "-O", "exit", target],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


@contextmanager
def _interactive_ssh_tunnel(
    ssh_config: Dict[str, Any],
    missing: List[Dict[str, Any]],
    reused: List[Dict[str, Any]],
) -> Iterator[Dict[str, Any]]:
    """Authenticate on the controlling terminal without reading the credential in Python."""

    with tempfile.TemporaryDirectory(prefix="llmddos-ssh-", dir="/tmp") as temp_dir:
        control_path = str(Path(temp_dir) / "control")
        command = build_interactive_ssh_command(ssh_config, missing, control_path)
        try:
            completed = subprocess.run(command, check=False)
        except OSError as exc:
            raise RuntimeError(f"Could not start SSH: {exc}") from exc
        if completed.returncode != 0:
            raise RuntimeError(
                f"SSH authentication or tunnel setup failed with exit code {completed.returncode}"
            )
        try:
            _wait_for_open_ports(
                [forward["local_port"] for forward in missing],
                ssh_config["startup_timeout_seconds"],
            )
            yield {
                "status": "started",
                "authentication": "interactive",
                "started_ports": [item["local_port"] for item in missing],
                "reused_ports": [item["local_port"] for item in reused],
            }
        finally:
            _close_control_master(control_path, ssh_config["target"])


@contextmanager
def managed_ssh_tunnel(
    ssh_config: Dict[str, Any], interactive_auth: bool = False
) -> Iterator[Dict[str, Any]]:
    """Reuse open forwards, start missing ones, and stop only the process started here."""

    forwards = ssh_config["forwards"]
    reused = [forward for forward in forwards if _port_is_open(forward["local_port"])]
    missing = [forward for forward in forwards if forward not in reused]
    if not missing:
        yield {"status": "reused", "reused_ports": [item["local_port"] for item in reused]}
        return

    if interactive_auth:
        with _interactive_ssh_tunnel(ssh_config, missing, reused) as state:
            yield state
        return

    command = build_ssh_command(ssh_config, missing)
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_ports(
            process,
            [forward["local_port"] for forward in missing],
            ssh_config["startup_timeout_seconds"],
        )
        yield {
            "status": "started",
            "started_ports": [item["local_port"] for item in missing],
            "reused_ports": [item["local_port"] for item in reused],
        }
    finally:
        _stop_process(process)
