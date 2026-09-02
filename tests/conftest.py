import socket
import threading

import pytest


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    """Fail fast if a test accidentally attempts any external connection."""
    original_connect = socket.socket.connect
    original_socketpair = socket.socketpair
    local = threading.local()

    def forbidden(*args, **kwargs):
        raise AssertionError("External network calls are forbidden in offline tests")

    def guarded_connect(sock, address):
        if getattr(local, "creating_socketpair", False):
            return original_connect(sock, address)
        return forbidden()

    def local_socketpair(*args, **kwargs):
        # Windows implements asyncio's private wakeup pipe with a loopback
        # socketpair. Allow only that construction, not arbitrary connections.
        local.creating_socketpair = True
        try:
            return original_socketpair(*args, **kwargs)
        finally:
            local.creating_socketpair = False

    monkeypatch.setattr(socket, "socketpair", local_socketpair)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
