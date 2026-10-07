"""Existing-login transport does not extract credentials or widen reads."""
import io
import subprocess

import pytest

from devostasis.workscope.glab import GlabTransport
from devostasis.workscope.model import ScopeError


class Process:
    def __init__(self, output, timeout=False):
        self.stdout = io.BytesIO(output); self.timeout = timeout; self.killed = False
    def wait(self, timeout=None):
        if self.timeout and not self.killed:
            raise subprocess.TimeoutExpired("glab", timeout)
        return 0
    def kill(self):
        self.killed = True


def install(monkeypatch, output, timeout=False):
    from devostasis.workscope import glab
    proc, calls = Process(output, timeout), []
    def popen(args, **kwargs):
        calls.append((args, kwargs)); return proc
    monkeypatch.setattr(glab.subprocess, "Popen", popen)
    return proc, calls


def test_existing_glab_login_uses_only_host_bound_get_and_no_token_command(monkeypatch):
    _, calls = install(monkeypatch, b'HTTP/2.0 200 OK\r\nX-Next-Page: 2\r\n\r\n{"id":123}\n')
    bridge = GlabTransport("https://gitlab.example/api/v4")
    code, headers, body = bridge.request("GET", "https://gitlab.example/api/v4/projects/123", {}, None, 1)
    assert code == 200 and headers["x-next-page"] == "2" and b'"id":123' in body
    args = calls[0][0]
    assert args == ["glab", "api", "projects/123", "--hostname", "gitlab.example", "--method", "GET", "--include"]
    assert calls[0][1]["stderr"] == subprocess.DEVNULL


@pytest.mark.parametrize("method,url,body", [("POST", "https://gitlab.example/api/v4/projects/123", b"{}"),
    ("GET", "https://other.example/api/v4/projects/123", None),
    ("GET", "http://gitlab.example/api/v4/projects/123", None)])
def test_bridge_refuses_mutation_or_another_endpoint(monkeypatch, method, url, body):
    _, calls = install(monkeypatch, b'')
    with pytest.raises(ScopeError, match="same-endpoint GET"):
        GlabTransport("https://gitlab.example/api/v4").request(method, url, {}, body, 1)
    assert not calls


def test_bridge_auth_failure_is_closed_and_does_not_echo_diagnostics(monkeypatch):
    install(monkeypatch, b'not authenticated')
    with pytest.raises(ScopeError, match="GLAB_AUTH_OR_RESPONSE_UNAVAILABLE"):
        GlabTransport("https://gitlab.example/api/v4").request("GET", "https://gitlab.example/api/v4/projects/123", {}, None, 1)


def test_bridge_kills_slow_or_oversized_processes(monkeypatch):
    from devostasis.workscope.collect import MAX_RESPONSE
    for output, timeout, code in ((b'', True, "GLAB_TIME_CAP"),
                                 (b'x' * (MAX_RESPONSE + 65537), False, "RESPONSE_BYTE_CAP")):
        proc, _ = install(monkeypatch, output, timeout)
        with pytest.raises(ScopeError, match=code):
            GlabTransport("https://gitlab.example/api/v4").request("GET", "https://gitlab.example/api/v4/projects/123", {}, None, 1)
        assert proc.killed
