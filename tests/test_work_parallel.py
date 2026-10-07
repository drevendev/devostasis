"""Shared quotas and scheduling-independent canonical collection evidence."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading
import time

import pytest

from devostasis.canonical import canonical_bytes
from devostasis.workscope.collect import Client, collect
from devostasis.workscope.model import ScopeError
from test_workscope_adapters import Routes, gitlab_routes, issue_routes
from test_workscope import AT, HEAD, BASE, config


@pytest.mark.parametrize("endpoint", ["https://:password@host/api/v4", "https://user:password@host/api/v4", "https://user@host/api/v4", "https://:@host/api/v4"])
def test_userinfo_is_refused_before_any_request(endpoint):
    with pytest.raises(ScopeError, match="HTTPS"):
        Client("gitlab", endpoint)


def test_parallel_requests_cannot_overdraw_shared_quota_or_ignore_deadline():
    class Slow(Routes):
        def request(self, *args):
            time.sleep(0.01)
            return super().request(*args)
    transport = Slow({"/api/v4/test": (200, {}, {})})
    client = Client("gitlab", "https://gitlab.example/api/v4", transport=transport, max_requests=5, workers=8)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: client.obj("/test"), range(30)))
    assert client.requests == len(transport.calls) == 5
    assert sum(obj is not None for obj, error in results) == 5
    client.deadline = time.monotonic() - 1
    assert client.obj("/test")[1] == "REQUEST_OR_TIME_CAP" and len(transport.calls) == 5


def multi_routes():
    routes = gitlab_routes(); root = "/api/v4/projects/123"; first = deepcopy(routes[root + "/merge_requests/1"][2])
    second = deepcopy(first); second.update(id=100, iid=2)
    routes[root + "/merge_requests"] = (200, {"x-next-page": ""}, [second, first])
    for name, reply in list(routes.items()):
        if "/merge_requests/1" in name:
            routes[name.replace("/merge_requests/1", "/merge_requests/2")] = deepcopy(reply)
    routes[root + "/merge_requests/2"] = (200, {}, second)
    return routes


def test_concurrent_change_reads_keep_exact_evidence_and_reuse_train_inventory():
    class Overlap(Routes):
        def __init__(self, routes):
            super().__init__(routes); self.lock = threading.Lock(); self.active = self.peak = 0
        def request(self, *args):
            with self.lock:
                self.active += 1; self.peak = max(self.peak, self.active)
            time.sleep(0.005)
            try:
                return super().request(*args)
            finally:
                with self.lock: self.active -= 1
    sequential = Routes(multi_routes()); concurrent = Overlap(multi_routes())
    a = collect(Client("gitlab", "https://gitlab.example/api/v4", transport=sequential, workers=1), "123", config(), AT)
    b = collect(Client("gitlab", "https://gitlab.example/api/v4", transport=concurrent, workers=4), "123", config(), AT)
    assert canonical_bytes(a) == canonical_bytes(b) and concurrent.peak > 1
    assert sum("/merge_trains?" in c[1] for c in concurrent.calls) == 1
    assert all(c["reviews"]["status"] == "UNAVAILABLE" for c in b["changes"]["items"])


def test_capped_parallel_collection_keeps_returned_records_and_explicit_gaps():
    client = Client("gitlab", "https://gitlab.example/api/v4", transport=Routes(multi_routes()), workers=4, max_requests=9)
    inv = collect(client, "123", config(), AT)
    assert client.requests == 9 and inv["changes"]["status"] != "COMPLETE"
    assert inv["changes"]["reasons"]


def test_transport_failure_retains_bounded_source_recovery_path():
    class Failed:
        def request(self, *args):
            raise ScopeError("GLAB_AUTH_OR_RESPONSE_UNAVAILABLE")
    client = Client("gitlab", "https://gitlab.example/api/v4", transport=Failed())
    assert client.obj("/projects/123/merge_requests/7")[0] is None
    assert client.receipts == [{"path": "/projects/123/merge_requests/7", "status": "UNAVAILABLE",
                               "body_digest": None, "reason": "GLAB_AUTH_OR_RESPONSE_UNAVAILABLE"}]
    assert client.telemetry[0]["bytes"] == 0 and client.requests == 1


@pytest.mark.parametrize("provider", ["github", "gitlab"])
@pytest.mark.parametrize("phase", ["initial", "final"])
def test_wrong_native_change_identity_never_satisfies_selected_collection(provider, phase):
    routes, endpoint, locator, root = issue_routes(provider)
    key = "number" if provider == "github" else "iid"
    detail = (gitlab_routes()[root + "/merge_requests/1"][2] if provider == "gitlab" else
              {"number": 1, "title": "Change", "state": "open", "head": {"sha": HEAD}, "base": {"sha": BASE},
               "user": {"login": "owner"}, "updated_at": AT, "changed_files": 0})
    route = root + ("/pulls/1" if provider == "github" else "/merge_requests/1")
    counter = 0
    def reply(_):
        nonlocal counter
        counter += 1
        return 200, {}, {**detail, key: 9} if phase == "initial" or counter > 1 else detail
    routes[route] = reply
    inv = collect(Client(provider, endpoint, transport=Routes(routes)), locator, config(), AT, change_refs=["1"])
    assert inv["changes"]["status"] == "UNAVAILABLE" and not inv["changes"]["items"]
    assert "CHANGE_IDENTITY_MISMATCH" in inv["changes"]["reasons"]
    assert counter == (1 if phase == "initial" else 2)


@pytest.mark.parametrize("provider", ["github", "gitlab"])
def test_wrong_native_issue_identity_never_satisfies_registered_criterion(provider):
    routes, endpoint, locator, root = issue_routes(provider)
    routes[root + "/issues/2"][2]["number" if provider == "github" else "iid"] = 9
    inv = collect(Client(provider, endpoint, transport=Routes(routes)), locator, config(), AT, change_refs=[])
    assert inv["issues"]["status"] == "UNAVAILABLE" and not inv["issues"]["items"]
