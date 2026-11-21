"""Shared fixtures: a real gaxis MCP server on loopback (transport + auth included)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

TOKEN = "gaxis-test-token-0123456789abcdef"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, proc: subprocess.Popen[str], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"server exited {proc.returncode}:\n{stderr}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError("gaxis MCP server did not start")


@pytest.fixture(scope="module")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Streamable HTTP endpoint with a bearer token, isolated data root."""
    port = free_port()
    home = tmp_path_factory.mktemp("gaxis-data")
    wrapper, state = fake_gbrain_binary(home)
    env = dict(os.environ) | {
        "GAXIS_MCP_TOKEN": TOKEN,
        "GAXIS_DATA_DIR": str(home),
        "GAXIS_GBRAIN_BIN": str(wrapper),
        "FAKE_GBRAIN_STATE": str(state),
    }
    env.pop("GAXIS_DEBUG", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "gaxis.mcp.server", "--transport", "http", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_port(port, proc)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()


def fake_gbrain_binary(directory: Path) -> tuple[Path, Path]:
    """Write an executable shim that runs tests/fake_gbrain.py; returns (shim, state)."""
    wrapper = directory / "gbrain"
    fake = Path(__file__).parent / "fake_gbrain.py"
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"\n')
    wrapper.chmod(0o755)
    return wrapper, directory / "kb-state.json"


@pytest.fixture(autouse=True)
def _isolate_real_knowledge_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a test write to the developer's real brain."""
    monkeypatch.setenv("GAXIS_KB_ENABLED", "false")


@pytest.fixture
def fake_kb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the knowledge base at tests/fake_gbrain.py (no real brain involved)."""
    wrapper, state = fake_gbrain_binary(tmp_path)
    monkeypatch.setenv("GAXIS_KB_ENABLED", "true")
    monkeypatch.setenv("GAXIS_GBRAIN_BIN", str(wrapper))
    monkeypatch.setenv("FAKE_GBRAIN_STATE", str(state))
    monkeypatch.setenv("GAXIS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GAXIS_CONFIG", raising=False)
    return state
