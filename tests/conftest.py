import socket

import pytest


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    """Fail fast if a test accidentally attempts any external connection."""
    def forbidden(*args, **kwargs):
        raise AssertionError("External network calls are forbidden in offline tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
