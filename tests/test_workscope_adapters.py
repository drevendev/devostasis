"""Provider capability, transport and consumer invalidation regression cases."""
from copy import deepcopy
import json
from urllib.parse import urlsplit
from urllib.request import Request

import pytest

from devostasis.canonical import canonical_bytes, digest
from devostasis.cli import main
from devostasis.workscope.bundle import build, publish, verify
from devostasis.workscope.cli import recheck
from devostasis.workscope.collect import Client, HTTPTransport, SafeRedirect, collect
from devostasis.workscope.evidence import empty_evidence
from devostasis.workscope.model import ScopeError, identity, inventory, policy
from devostasis.workscope.planner import project
from test_workscope import AT, SHA, HEAD, BASE, config, inv, item


class Routes:
    def __init__(self, routes):
        self.routes, self.calls = routes, []
    def request(self, method, url, headers, data, timeout):
        self.calls.append((method, url, headers, data))
        value = self.routes.get(urlsplit(url).path, (404, {}, {}))
        if callable(value):
            value = value(self.calls)
        return value[0], value[1], canonical_bytes(value[2])


def gitlab_routes():
    root = "/api/v4/projects/123"; mr = root + "/merge_requests/1"
    detail = {"id": 99, "iid": 1, "title": "Feature", "state": "opened", "author": {"username": "owner"},
              "assignees": [], "sha": HEAD, "diff_refs": {"base_sha": BASE}, "updated_at": AT,
              "draft": False, "has_conflicts": False, "changes_count": "1"}
    return {root: (200, {}, {"id": 123, "default_branch": "main"}),
            root + "/repository/commits/main": (200, {}, {"id": SHA}),
            root + "/merge_requests": (200, {"x-next-page": ""}, [detail]), mr: (200, {}, detail),
            mr + "/approvals": (200, {}, {"approved": True, "approved_by": [{"user": {"username": "reviewer"}, "approved_at": AT}]}),
            mr + "/discussions": (200, {"x-next-page": ""}, [{"id": "d1", "notes": [{"resolvable": True, "resolved": False}]}]),
            mr + "/diffs": (200, {"x-next-page": ""}, [{"new_path": "src/app.py", "old_path": "src/app.py"}]),
            mr + "/pipelines": (200, {"x-next-page": ""}, [{"id": 101, "sha": HEAD}]),
            root + "/pipelines/101/jobs": (200, {"x-next-page": ""}, [{"id": 102, "name": "tests", "status": "manual", "created_at": AT}]),
            root + "/merge_trains": (200, {"x-next-page": ""}, []),
            root + "/issues/2": (200, {}, {"iid": 2, "title": "Feature", "state": "opened", "assignees": [], "updated_at": AT})}


def issue_routes(provider):
    if provider == "gitlab":
        return gitlab_routes(), "https://gitlab.example/api/v4", "123", "/api/v4/projects/123"
    root = "/repos/acme/widget"
    return {root: (200, {}, {"id": 123, "full_name": "acme/widget", "default_branch": "main"}),
            root + "/commits/main": (200, {}, {"sha": SHA}),
            root + "/issues/2": (200, {}, {"number": 2, "title": "Feature", "state": "open",
                                           "assignees": [], "updated_at": AT})}, "https://api.github.com", "acme/widget", root


@pytest.mark.parametrize("provider", ["github", "gitlab"])
@pytest.mark.parametrize("state", [None, "", "unexpected", False, 0, [], {}])
def test_work_unknown_issue_state_cannot_complete_a_criterion(provider, state):
    routes, endpoint, locator, root = issue_routes(provider)
    routes[root + "/issues/2"][2]["state"] = state
    p = config()
    selected = item(project(inv(), p, empty_evidence()), "implement_issue")
    i = collect(Client(provider, endpoint, transport=Routes(routes)), locator, p, AT, selected=selected)
    assert i["issues"]["status"] == "UNAVAILABLE" and not i["issues"]["items"]
    scope = project(i, p, empty_evidence())
    assert item(scope, "implement_issue")["eligibility"] == "UNKNOWN"
    assert any(task["source"] == "recovery:issue:2" for task in scope["items"])
    assert not any(exclusion["reason"] == "CRITERION_DONE" for exclusion in scope["excluded"])


@pytest.mark.parametrize("provider", ["github", "gitlab"])
@pytest.mark.parametrize("missing", ["2", "3"])
def test_work_mixed_issue_availability_preserves_partial_scope_in_either_order(provider, missing):
    routes, endpoint, locator, root = issue_routes(provider)
    valid = deepcopy(routes[root + "/issues/2"][2])
    valid["number" if provider == "github" else "iid"] = 3
    routes[root + "/issues/3"] = (200, {}, valid)
    routes[root + "/issues/" + missing] = (403, {}, {})
    p = config(); p["criteria"][0]["dependencies"] = ["3"]
    selected = item(project(inv(), p, empty_evidence()), "implement_issue")
    i = collect(Client(provider, endpoint, transport=Routes(routes)), locator, p, AT, selected=selected)
    available = "3" if missing == "2" else "2"
    assert i["issues"]["status"] == "PARTIAL"
    assert [record["id"] for record in i["issues"]["items"]] == [available]
    scope = project(i, p, empty_evidence())
    assert item(scope, "implement_issue")["eligibility"] == "UNKNOWN"
    assert any(task["source"] == "recovery:issue:" + missing for task in scope["items"])
    assert any(task["source"] == "request:Q1" and task["eligibility"] == "READY" for task in scope["items"])
    from devostasis.workscope.bundle import verify_content
    assert verify_content(build(i, p, empty_evidence())[1])["inventory.json"] == i


def test_work_gitlab_manual_jobs_diffs_threads_and_exact_head_unknown():
    f = Routes(gitlab_routes())
    i = collect(Client("gitlab", "https://gitlab.example/api/v4", "read-only", transport=f), "123", config(), AT)
    c = i["changes"]["items"][0]
    assert c["files"]["items"] == ["src/app.py"] and c["files"]["status"] == "COMPLETE"
    assert c["reviews"]["status"] == "UNAVAILABLE" and c["merge_train"] is False
    assert c["checks"]["items"][0]["state"] == "MANUAL"
    assert c["threads"]["items"][0]["resolved"] is False
    assert item(project(i, config(), empty_evidence()), "finish_merge")["merge_gate"]["status"] == "UNKNOWN"
    assert all(call[0] == "GET" for call in f.calls)
    assert all(call[2]["PRIVATE-TOKEN"] == "read-only" for call in f.calls)


@pytest.mark.parametrize("suffix", ["/issues/2", "/merge_requests/1/discussions", "/pipelines/101/jobs", "/merge_trains", "/merge_requests/1/approvals"])
@pytest.mark.parametrize("code", [401, 403, 404, 429, 500])
def test_work_gitlab_missing_capabilities_are_explicit(suffix, code):
    routes = gitlab_routes(); routes["/api/v4/projects/123" + suffix] = (code, {}, {})
    f = Routes(routes); i = collect(Client("gitlab", "https://gitlab.example/api/v4", transport=f), "123", config(), AT)
    assert any(r["status"] == code for r in i["receipts"])
    assert item(project(i, config(), empty_evidence()), "finish_merge")["merge_gate"]["status"] != "READY"
    if suffix == "/issues/2":
        assert item(project(i, config(), empty_evidence()), "implement_issue")["eligibility"] == "UNKNOWN"


def test_work_gitlab_diff_result_cap_and_train_membership():
    routes = gitlab_routes(); routes["/api/v4/projects/123/merge_requests/1"][2]["changes_count"] = "1000+"
    routes["/api/v4/projects/123/merge_trains"] = (200, {"x-next-page": ""}, [{"id": 5, "merge_request": {"iid": 1}}])
    i = collect(Client("gitlab", "https://gitlab.example/api/v4", transport=Routes(routes)), "123", config(), AT)
    c = i["changes"]["items"][0]
    assert c["files"]["status"] == "PARTIAL" and c["merge_train"] is True


def test_work_gitlab_head_moving_during_collection():
    routes = gitlab_routes(); initial = routes["/api/v4/projects/123/merge_requests/1"][2]
    counter = 0
    def moving(calls):
        nonlocal counter
        counter += 1
        return 200, {}, initial if counter == 1 else {**initial, "sha": SHA}
    routes["/api/v4/projects/123/merge_requests/1"] = moving
    i = collect(Client("gitlab", "https://gitlab.example/api/v4", transport=Routes(routes)), "123", config(), AT)
    c = i["changes"]["items"][0]
    assert c["checks"]["status"] == c["threads"]["status"] == "UNAVAILABLE"


def test_work_selected_refresh_does_not_discover_whole_repository():
    routes = gitlab_routes(); selected = item(project(inv(), config(), empty_evidence()), "implement_issue")
    f = Routes(routes)
    i = collect(Client("gitlab", "https://gitlab.example/api/v4", transport=f), "123", config(), AT, selected=selected)
    assert i["selection"]["changes"] == "SELECTED"
    assert not any(urlsplit(c[1]).path.endswith("/merge_requests") for c in f.calls)
    assert len(f.calls) == 3


def test_work_canonical_collection_refuses_wrong_revision():
    with pytest.raises(ScopeError, match="canonical"):
        collect(Client("gitlab", "https://gitlab.example/api/v4", transport=Routes(gitlab_routes())),
                "123", config(), AT, revision=HEAD)


@pytest.mark.parametrize("target", ["http://api.github.com/x", "https://evil.test/x"])
def test_work_redirect_cannot_forward_credentials(target):
    with pytest.raises(ScopeError, match="redirect"):
        SafeRedirect().redirect_request(Request("https://api.github.com/x", headers={"Authorization": "Bearer secret"}),
                                        None, 302, "", {}, target)


@pytest.mark.parametrize("method,url,body", [
    ("DELETE", "https://api.github.com/repos/a/b", None),
    ("POST", "https://api.github.com/repos/a/b/issues", b'{"query":"query($n:Int!){x}"}'),
    ("POST", "https://api.github.com/graphql", b'{"query":"mutation{deleteSomething}"}'),
])
def test_work_transport_refuses_mutation(method, url, body):
    with pytest.raises(ScopeError, match="read"):
        HTTPTransport().request(method, url, {}, body, 1)


def test_work_conditional_304_replays_body_without_credential_crossing(tmp_path):
    f = Routes({"/x": (200, {"etag": "e1"}, [{"id": 1}])})
    c = Client("github", "https://api.github.com", "a", transport=f, cache=tmp_path)
    c.get("/x"); f.routes["/x"] = (304, {}, None)
    assert c.get("/x")[0] == [{"id": 1}]
    assert c.receipts[0] == c.receipts[1]
    assert c.telemetry[0]["status"] == 200 and c.telemetry[1]["status"] == 304
    assert f.calls[-1][2]["If-None-Match"] == "e1"
    other = Client("github", "https://api.github.com", "b", transport=f, cache=tmp_path)
    with pytest.raises(ScopeError, match="304"):
        other.get("/x")


def test_work_enterprise_graphql_uses_api_graphql():
    f = Routes({"/api/graphql": (200, {}, {})})
    c = Client("github", "https://github.example/api/v3", transport=f)
    c.get("/graphql", query={"query": "query($x:Int!){x}", "variables": {"x": 1}})
    assert f.calls[0][1] == "https://github.example/api/graphql"


@pytest.mark.parametrize("change", [
    lambda i: i["subject"].update(project_id="999"),
    lambda i: i["subject"].update(context="CANDIDATE"),
])
def test_work_consumer_checks_project_and_context(change):
    decoded = verify_content_fixture(); i = inv(); change(i)
    with pytest.raises(ScopeError, match="mismatch"):
        recheck(decoded, i, AT, actor="owner", policy_version="example-1", expected_project=identity(inv()["subject"]))


def verify_content_fixture():
    from devostasis.workscope.bundle import verify_content
    return verify_content(build(inv(), config(), empty_evidence())[1])


def test_work_consumer_refuses_stale_scope_actor_and_policy():
    d = verify_content_fixture()
    with pytest.raises(ScopeError, match="expired"):
        recheck(d, inv(), "2026-10-02T14:00:00Z", actor="owner", policy_version="example-1", expected_project=identity(inv()["subject"]))
    with pytest.raises(ScopeError, match="actor"):
        recheck(d, inv(), AT, actor="other", policy_version="example-1", expected_project=identity(inv()["subject"]))
    with pytest.raises(ScopeError, match="policy"):
        recheck(d, inv(), AT, actor="owner", policy_version="other", expected_project=identity(inv()["subject"]))


def test_work_policy_reuse_changes_digest(tmp_path, capsys):
    bundle = publish(tmp_path / "store", build(inv(), config(), empty_evidence())[1])
    p = config(); p["required_checks"] = []
    (tmp_path / "policy.json").write_bytes(canonical_bytes(p))
    (tmp_path / "inventory.json").write_bytes(canonical_bytes(inv()))
    selected = item(verify(bundle)["scope.json"], "finish_merge")
    assert main(["work", "recheck", "--bundle", str(bundle), "--policy", str(tmp_path / "policy.json"),
                 "--inventory", str(tmp_path / "inventory.json"), "--item", selected["id"], "--at", AT,
                 "--actor", "owner", "--policy-version", "example-1", "--expected-project-id", "123"]) == 2
    assert "digest mismatch" in capsys.readouterr().err


def test_work_future_evidence_and_duplicate_inventory_refused():
    i = inv(); i["changes"]["items"][0]["checks"]["items"][0]["at"] = "2026-10-02T12:00:00.000001Z"
    with pytest.raises(ScopeError, match="after"):
        inventory(i)
    i = inv(); i["issues"]["items"].append(deepcopy(i["issues"]["items"][0]))
    with pytest.raises(ScopeError, match="duplicate"):
        inventory(i)


def test_work_satisfied_review_gate_excludes_unrequested_extra_review():
    i = inv(); i["changes"]["items"][0]["reviewers"] = []
    s = project(i, config("executor"), empty_evidence())
    assert not s["queues"]["review"]
    assert any(e["reason"] == "INDEPENDENT_REVIEW_REQUIREMENT_SATISFIED" for e in s["excluded"])
    i["changes"]["items"][0]["reviewers"] = ["executor"]
    assert project(i, config("executor"), empty_evidence())["queues"]["review"]


def test_work_repository_policy_is_admissible_and_versioned():
    from pathlib import Path
    value = json.loads((Path(__file__).resolve().parents[1] / ".devostasis/work-policy.json").read_text())
    assert policy(value)["version"] == "devostasis-work-1"
    assert len(value["required_checks"]) == 3


def test_work_optional_cache_failure_keeps_admitted_source_evidence(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("cache disk unavailable")
    monkeypatch.setattr("devostasis.workscope.collect.atomic", fail)
    f = Routes({"/x": (200, {"etag": "e1"}, [{"id": 1}])})
    c = Client("github", "https://api.github.com", transport=f, cache=tmp_path)
    assert c.get("/x")[0] == [{"id": 1}]
    assert c.receipts[0]["status"] == 200 and c.telemetry[0]["cache_write_failed"]


def test_work_transport_bounds_slow_stream_and_bytes(monkeypatch):
    class Response:
        code, headers = 200, {}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read1(self, size):
            return b"x"
    class Opener:
        def open(self, *args, **kwargs):
            return Response()
    t = HTTPTransport(); t.opener = Opener()
    clock = iter([0, 0, 2])
    monkeypatch.setattr("devostasis.workscope.collect.time.monotonic", lambda: next(clock))
    with pytest.raises(ScopeError, match="TIME_CAP"):
        t.request("GET", "https://api.github.com/x", {}, None, 1)
    monkeypatch.setattr("devostasis.workscope.collect.time.monotonic", lambda: 0)
    monkeypatch.setattr("devostasis.workscope.collect.MAX_RESPONSE", 1)
    with pytest.raises(ScopeError, match="BYTE_CAP"):
        t.request("GET", "https://api.github.com/x", {}, None, 1)


def test_work_unknown_dependency_and_unbounded_criterion_offer_recovery():
    p = config(); p["criteria"][0].update(paths=[], dependencies=["3"])
    s = project(inv(), p, empty_evidence())
    assert item(s, "implement_issue")["eligibility"] == "UNKNOWN"
    assert any(i["source"] == "recovery:issue:3" for i in s["items"])
    assert any(i["source"] == "recovery:issue:2/C1" for i in s["items"])


def test_work_candidate_content_cannot_recheck_an_unrecorded_mutable_ref(tmp_path, capsys, monkeypatch):
    i = inv(); i["subject"]["context"] = "CANDIDATE"
    bundle = publish(tmp_path / "store", build(i, config(), empty_evidence())[1])
    p = tmp_path / "policy.json"; p.write_bytes(canonical_bytes(config()))
    selected = item(verify(bundle)["scope.json"], "implement_issue")
    def forbidden(*args, **kwargs):
        raise AssertionError("must reject before making a network request")
    monkeypatch.setattr("devostasis.workscope.cli.collect", forbidden)
    assert main(["work", "recheck", "--bundle", str(bundle), "--policy", str(p), "--item", selected["id"],
                 "--expected-project-id", "123", "--actor", "owner", "--policy-version", "example-1", "--at", AT]) == 2
    assert "freshly attested" in capsys.readouterr().err
