"""Test-wide guards: no test may reach the network (CI has none, and real calls would leak keys/quota)."""

import socket

import pytest


@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    """Fail any test that opens a non-local socket, unless it is marked ``integration``."""
    if request.node.get_closest_marker("integration"):
        return
    real_connect = socket.socket.connect

    def guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if self.family == socket.AF_UNIX or host in ("127.0.0.1", "::1", "localhost"):
            return real_connect(self, address, *args, **kwargs)
        raise RuntimeError(f"network access attempted in a test: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
