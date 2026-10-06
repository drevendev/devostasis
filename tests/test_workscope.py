"""Implementation-owned DEV-WORK cases, distinct from research Vital vectors."""

import base64
from copy import deepcopy
import json
from pathlib import Path

import pytest

from devostasis.canonical import canonical_bytes, digest, digest_bytes
from devostasis.cli import main
from devostasis.workscope import CONTRACT
from devostasis.workscope.bundle import build, latest, locked, publish, slice_scope, verify, verify_content
from devostasis.workscope.collect import Client, collect, complete, unavailable
from devostasis.workscope.evidence import empty_evidence, normalize, source, validate
from devostasis.workscope.model import ScopeError, default_policy, instant, inventory, path, policy
from devostasis.workscope.planner import project

AT = "2026-10-02T12:00:00Z"
SHA = "a" * 40
HEAD = "b" * 40
BASE = "c" * 40


def subject():
    return {"provider": "github", "endpoint": "https://api.github.com", "project_id": "123",
            "locator": "acme/widget", "revision": SHA, "context": "CANONICAL"}


def change(author="owner"):
    return {"id": "1", "title": "Change", "state": "OPEN", "author": author, "owners": [], "reviewers": ["executor"],
            "head": HEAD, "base": BASE, "updated_at": AT, "draft": False, "conflict": False,
            "merge_train": False, "reviews": complete([{"id": "r1", "actor": "reviewer", "revision": HEAD,
                "state": "APPROVED", "at": AT}]),
            "checks": complete([{"id": "c1", "name": "tests", "revision": HEAD, "state": "PASS", "at": AT}]),
            "threads": complete(), "files": complete(["src/app.py"])}


def inv():
    return {"contract": CONTRACT, "kind": "inventory", "subject": subject(), "observed_at": AT,
            "changes": complete([change()]), "issues": complete([{"id": "2", "title": "Feature",
                "state": "OPEN", "owners": [], "updated_at": AT}]), "receipts": [],
            "selection": {"changes": "OPEN_AND_REGISTERED", "issues": ["2"]}}


def config(actor="owner"):
    p = default_policy(actor); p["required_checks"] = ["tests"]
    p["criteria"] = [{"id": "C1", "issue": "2", "acceptance": ["Feature passes a behavioral test."],
                      "paths": ["src/app.py"], "symbols": ["app"], "dependencies": [],
                      "implementations": [], "done": False}]
    p["requests"] = [{"id": "Q1", "queue": "research", "question": "Resolve the observed contradiction.",
                      "paths": ["src/app.py"], "symbols": [], "acceptance": ["Record bounded evidence and a verdict."],
                      "dependencies": [], "owner": None}]
    return p


def report(profile="junit.v1", raw=None, project=None, at=AT):
    raw = raw or b'<testsuite><testcase file="src/app.py" line="4" name="test_behavior"><failure/></testcase></testsuite>'
    return {"contract": CONTRACT, "kind": "evidence", "sources": [source(profile, "pytest", "1", project or subject(), at, raw)]}


def item(scope, queue):
    return next(i for i in scope["items"] if i["queue"] == queue)


def test_work_five_queues_and_bounded_acceptance():
    result = project(inv(), config("executor"), report())
    assert all(result["queues"].values())
    assert all(i["acceptance"] and i["read_set"]["budget"] for i in result["items"])
    assert item(result, "review")["implementation_owner"] is None
    assert item(result, "finish_merge")["executor"] == "executor"


def test_work_determinism_ids_and_explicit_priority():
    i, p = inv(), config()
    p["priorities"]["issue:2"] = {"rank": 0, "rationale": "Customer commitment."}
    first = project(i, p, report())
    assert first["items"][0]["queue"] == "implement_issue"
    assert canonical_bytes(first) == canonical_bytes(project(deepcopy(i), deepcopy(p), report()))
    newer = deepcopy(i); newer["observed_at"] = "2026-10-02T12:01:00Z"
    second = project(newer, p, report())
    assert {v["id"] for v in first["items"]} == {v["id"] for v in second["items"]}
    assert digest(first) != digest(second)


@pytest.mark.parametrize("state", ["FAIL", "PENDING", "MANUAL", "UNKNOWN"])
def test_work_checks_block_merge_without_hiding_rework(state):
    i = inv(); i["changes"]["items"][0]["checks"]["items"][0]["state"] = state
    selected = item(project(i, config(), empty_evidence()), "finish_merge")
    assert selected["action"] == "rework"
    assert selected["merge_gate"]["status"] != "READY"
    assert selected["eligibility"] == ("UNKNOWN" if state == "UNKNOWN" else "READY")


@pytest.mark.parametrize("field", ["reviews", "checks", "threads", "files"])
@pytest.mark.parametrize("status", ["PARTIAL", "UNAVAILABLE"])
def test_work_missing_cannot_admit_merge(field, status):
    i = inv(); i["changes"]["items"][0][field] = {"status": status, "items": [], "reasons": ["AUTH"]}
    s = project(i, config(), empty_evidence())
    assert item(s, "finish_merge")["merge_gate"]["status"] == "UNKNOWN"
    assert any(v["action"] == "recover_evidence" for v in s["items"])


@pytest.mark.parametrize("mutation,reason", [
    (lambda c: c.update(draft=True), "DRAFT"),
    (lambda c: c.update(conflict=True), "CONFLICT"),
    (lambda c: c.update(merge_train=True), "MERGE_TRAIN_NOT_AUTHORIZED"),
    (lambda c: c["threads"]["items"].append({"id": "t1", "resolved": False}), "UNRESOLVED_DISCUSSION"),
    (lambda c: c["reviews"]["items"][0].update(revision=SHA), "EXACT_HEAD_APPROVAL_REQUIRED"),
    (lambda c: c["reviews"]["items"][0].update(state="CHANGES_REQUESTED"), "CHANGES_REQUESTED"),
    (lambda c: c["checks"].update(items=[]), "CHECK_MISSING:tests"),
])
def test_work_merge_admission_matrix(mutation, reason):
    i = inv(); mutation(i["changes"]["items"][0])
    s = project(i, config(), empty_evidence())
    assert reason in item(s, "finish_merge")["merge_gate"]["reasons"]


def test_work_stale_verdict_dismissal_and_self_review():
    i = inv(); c = i["changes"]["items"][0]
    c["reviews"]["items"].append({"id": "r2", "actor": "reviewer", "revision": HEAD,
        "state": "DISMISSED", "at": AT})
    assert item(project(i, config(), empty_evidence()), "finish_merge")["merge_gate"]["status"] == "BLOCKED"
    c["reviews"]["items"][0]["actor"] = "owner"
    c["reviews"]["items"] = c["reviews"]["items"][:1]
    assert item(project(i, config(), empty_evidence()), "finish_merge")["merge_gate"]["status"] == "BLOCKED"
    assert not project(i, config(), empty_evidence())["queues"]["review"]


def test_work_roles_foreign_owners_dependencies_and_sibling_criteria():
    i, p = inv(), config()
    i["issues"]["items"][0]["owners"] = ["someone"]
    assert "FOREIGN_IMPLEMENTATION_OWNER" in item(project(i, p, empty_evidence()), "implement_issue")["reasons"]
    i["issues"]["items"][0]["owners"] = []
    p["criteria"][0]["dependencies"] = ["3"]
    assert item(project(i, p, empty_evidence()), "implement_issue")["eligibility"] == "UNKNOWN"
    i["issues"]["items"].append({"id": "3", "title": "Dependency", "state": "OPEN", "owners": [], "updated_at": AT})
    assert item(project(i, p, empty_evidence()), "implement_issue")["eligibility"] == "BLOCKED"
    i["issues"]["items"][-1]["state"] = "CLOSED"
    sibling = deepcopy(p["criteria"][0]); sibling.update(id="C2", done=True); p["criteria"].append(sibling)
    assert len(project(i, p, empty_evidence())["queues"]["implement_issue"]) == 1
    p["criteria"][0]["implementations"] = ["1"]
    assert not project(i, p, empty_evidence())["queues"]["implement_issue"]
    p["roles"] = ["analyst"]
    s = project(i, p, report())
    assert len(s["items"]) == 1 and s["items"][0]["queue"] == "analyze_code"


@pytest.mark.parametrize("bad", ["../a.py", "/a.py", "C:/a.py", "a\\b.py", "%2e%2e/a.py", "a//b.py", "a/./b.py", "a.py\n"])
def test_work_out_of_tree_paths_rejected(bad):
    with pytest.raises(ScopeError):
        path(bad)


@pytest.mark.parametrize("bad", ["2026-10-02", "2026-10-02T12:00:00", "2026-99-02T12:00:00Z", "2026-10-02T12:00:00.1234567Z"])
def test_work_timestamp_requires_unambiguous_instant(bad):
    with pytest.raises(ScopeError):
        instant(bad)


@pytest.mark.parametrize("profile,raw", [
    ("sarif.v1", b'{"version":"2.1.0","runs":[{"results":[{"ruleId":"S1","locations":[{"physicalLocation":{"artifactLocation":{"uri":"src/app.py"},"region":{"startLine":4}}}]}]}]}'),
    ("junit.v1", b'<testsuite><testcase file="src/app.py" line="4" name="t"><failure/></testcase></testsuite>'),
    ("cobertura.v1", b'<coverage lines-valid="2"><packages><package><classes><class name="app" filename="src/app.py"><lines><line number="4" hits="0"/><line number="5" hits="1"/></lines></class></classes></package></packages></coverage>'),
    ("performance.v1", ('{"measurements":[{"name":"latency","path":"src/app.py","line":4,"baseline":100,"current":120,"limit_percent":10,"unit":"ms","baseline_revision":"' + SHA + '"}]}').encode()),
])
def test_work_report_profiles(profile, raw):
    normalized = normalize(report(profile, raw), subject(), AT, 3600)
    assert len(normalized["findings"]) == 1 and not normalized["gaps"]
    assert normalized["findings"][0]["path"] == "src/app.py"


@pytest.mark.parametrize("profile,raw", [
    ("sarif.v1", b'{"version":"2.1.0","version":"2.1.0","runs":[]}'),
    ("sarif.v1", b'{"version":"2.1.0","runs":[{"results":[{}]}]}'),
    ("sarif.v1", b'{"version":"2.1.0","runs":['),
    ("junit.v1", b'<!DOCTYPE testsuite [<!ENTITY x "bad">]><testsuite/>'),
    ("junit.v1", b'<testsuite><testcase name="t"><failure/></testcase></testsuite>'),
    ("junit.v1", b'<testsuite><testcase file="../a.py" name="t"><failure/></testcase></testsuite>'),
    ("cobertura.v1", b'<coverage lines-valid="0"/>'),
    ("cobertura.v1", b'<coverage/>'),
    ("cobertura.v1", b'<coverage lines-valid="2"/>'),
    ("junit.v1", b'<testsuite tests="0"/>'),
    ("sarif.v1", b'{"version":"2.1.0","runs":[]}'),
])
def test_work_malformed_and_unavailable_reports_are_not_zero(profile, raw):
    normalized = normalize(report(profile, raw), subject(), AT, 3600)
    assert not normalized["findings"] and normalized["gaps"]


@pytest.mark.parametrize("mutate", [lambda s: s.update(project_id="999"), lambda s: s.update(revision=HEAD)])
def test_work_report_wrong_repo_and_revision(mutate):
    s = subject(); mutate(s)
    n = normalize(report(project=s), subject(), AT, 3600)
    assert not n["findings"] and n["gaps"][0]["reason"] == "REPORT_IDENTITY_OR_REVISION_MISMATCH"


def test_work_stale_duplicate_and_tampered_reports():
    assert normalize(report(at="2026-10-01T12:00:00Z"), subject(), AT, 3600)["gaps"]
    r = report(); r["sources"].append(deepcopy(r["sources"][0]))
    with pytest.raises(ScopeError, match="duplicate"):
        validate(r)
    r = report(); r["sources"][0]["report"]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ScopeError, match="digest"):
        validate(r)


def test_work_partial_report_retains_location_without_executable_admission():
    r = report(); r["sources"][0].update(status="PARTIAL", reason="PRODUCER_CAP")
    s = project(inv(), config(), r)
    assert item(s, "analyze_code")["eligibility"] == "UNKNOWN"
    assert any(i["action"] == "recover_evidence" for i in s["items"])


def test_work_disposition_expires_and_revision_recurs():
    i, p, r = inv(), config(), report()
    finding = normalize(r, subject(), AT, 3600)["findings"][0]
    p["dispositions"] = [{"finding": finding["id"], "revision": SHA, "until": "2026-10-02T12:01:00Z",
                           "state": "ACKNOWLEDGED", "reference": "issue:2"}]
    assert not project(i, p, r)["queues"]["analyze_code"]
    assert project(i, p, r, "2026-10-02T12:02:00Z")["queues"]["analyze_code"]
    i["subject"]["revision"] = HEAD; r["sources"][0]["subject"]["revision"] = HEAD
    assert project(i, p, r)["queues"]["analyze_code"]


def test_work_bundle_replay_and_forged_rehashed_projection_rejected():
    m, content = build(inv(), config(), report())
    assert verify_content(content)["manifest.json"] == m
    c = deepcopy(content); s = json.loads(c["scope.json"]); s["items"][0]["eligibility"] = "MADE_UP"
    c["scope.json"] = canonical_bytes(s)
    forged = json.loads(c["manifest.json"]); forged["members"]["scope.json"] = digest_bytes(c["scope.json"])
    forged["bundle_id"] = digest({k: v for k, v in forged.items() if k != "bundle_id"})
    c["manifest.json"] = canonical_bytes(forged)
    with pytest.raises(ScopeError, match="replay"):
        verify_content(c)


def test_work_store_backfill_candidate_rename_and_latest_binding(tmp_path):
    i = inv(); _, content = build(i, config(), report()); dest = publish(tmp_path, content)
    root = dest.parent.parent
    assert publish(tmp_path, content) == dest
    old = deepcopy(i); old["observed_at"] = "2026-10-02T11:00:00Z"
    for obj in old["changes"]["items"] + old["issues"]["items"]:
        obj["updated_at"] = old["observed_at"]
    for row in old["changes"]["items"][0]["checks"]["items"] + old["changes"]["items"][0]["reviews"]["items"]:
        row["at"] = old["observed_at"]
    publish(tmp_path, build(old, config(), empty_evidence())[1])
    assert latest(root)["scope.json"]["observed_at"] == AT
    candidate = deepcopy(i); candidate["subject"]["context"] = "CANDIDATE"; candidate["observed_at"] = "2026-10-02T12:01:00Z"
    publish(tmp_path, build(candidate, config(), report())[1])
    assert latest(root)["scope.json"]["observed_at"] == AT
    i["observed_at"] = "2026-10-02T12:02:00Z"; i["subject"]["locator"] = "new/name"
    renamed = publish(tmp_path, build(i, config(), report())[1])
    assert renamed.parent.parent == root and latest(root)["scope.json"]["subject"]["locator"] == "new/name"
    pointer = json.loads((root / "latest.json").read_bytes()); pointer["manifest_digest"] = "bad"
    (root / "latest.json").write_bytes(canonical_bytes(pointer))
    with pytest.raises(ScopeError, match="binding"):
        latest(root)


def test_work_store_lock_and_failed_pointer_write_preserve_history(tmp_path, monkeypatch):
    _, content = build(inv(), config(), report()); dest = publish(tmp_path, content); root = dest.parent.parent
    with locked(root / ".lock"):
        with pytest.raises(ScopeError, match="locked"):
            publish(tmp_path, content)
    i = inv(); i["observed_at"] = "2026-10-02T12:01:00Z"
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr("devostasis.workscope.bundle.atomic", fail)
    with pytest.raises(OSError):
        publish(tmp_path, build(i, config(), report())[1])
    assert latest(root)["scope.json"]["observed_at"] == AT
    assert len(list((root / "bundles").iterdir())) == 2


def test_work_cursor_exhaustive_binding_and_expiry():
    s = project(inv(), config("executor"), report())
    seen, cursor = [], None
    while True:
        result = slice_scope(s, limit=1, cursor=cursor, at=AT)
        seen += [i["id"] for i in result["items"]]; cursor = result["cursor"]
        if not cursor:
            break
    assert seen == [i["id"] for i in s["items"]]
    c = slice_scope(s, limit=1)["cursor"]
    with pytest.raises(ScopeError, match="another"):
        slice_scope(s, role="analyst", cursor=c)
    expired = slice_scope(s, at="2026-10-02T14:00:00Z")
    assert expired["status"] == "EXPIRED" and len(expired["items"]) == 1


class Fake:
    def __init__(self, routes):
        self.routes, self.calls = routes, []
    def request(self, method, url, headers, data, timeout):
        self.calls.append((method, url, headers, data))
        path = url.split("https://api.github.com", 1)[-1].split("?", 1)[0]
        value = self.routes.get(path, (404, {}, {}))
        return value[0], value[1], canonical_bytes(value[2])


def test_work_transport_caps_and_cache_partition(tmp_path):
    transport = Fake({"/x": (200, {"etag": "e1"}, [{"id": 1}])})
    client = Client("github", "https://api.github.com", "secret-a", transport=transport, max_requests=1, cache=tmp_path)
    assert client.pages("/x")["status"] == "COMPLETE"
    assert client.pages("/x")["status"] == "UNAVAILABLE"
    other = Client("github", "https://api.github.com", "secret-b", transport=transport, cache=tmp_path)
    other.pages("/x")
    assert "If-None-Match" not in transport.calls[-1][2]
    assert "secret-a" not in "".join(p.read_text() for p in tmp_path.rglob("*.json"))


def test_work_pagination_duplicate_and_page_cap():
    f = Fake({"/x": (200, {"link": '<https://evil.test>; rel="next"'}, [{"id": i} for i in range(100)])})
    client = Client("github", "https://api.github.com", transport=f, max_pages=1)
    assert client.pages("/x")["status"] == "PARTIAL"
    client = Client("github", "https://api.github.com", transport=f, max_pages=2)
    assert "PAGINATION_IDENTITY_SHIFT" in client.pages("/x")["reasons"]
    assert all("evil.test" not in c[1] for c in f.calls)


def test_work_live_shape_github_adapter_and_readonly_graphql():
    repo = "/repos/acme/widget"; pr = repo + "/pulls/1"
    p = {"number": 1, "title": "Change", "state": "open", "merged": False, "head": {"sha": HEAD},
         "base": {"sha": BASE}, "user": {"login": "owner"}, "assignees": [], "updated_at": AT,
         "draft": False, "mergeable": True, "changed_files": 1}
    routes = {repo: (200, {}, {"id": 123, "default_branch": "main", "full_name": "acme/widget"}),
              repo + "/commits/main": (200, {}, {"sha": SHA}), repo + "/pulls": (200, {}, [{"id": 99, **p}]),
              pr: (200, {}, p), pr + "/reviews": (200, {}, []), pr + "/files": (200, {}, [{"filename": "src/app.py"}]),
              repo + f"/commits/{HEAD}/check-runs": (200, {}, {"total_count": 0, "check_runs": []}),
              repo + f"/commits/{HEAD}/statuses": (200, {}, []),
              repo + "/issues/2": (200, {}, {"number": 2, "title": "Feature", "state": "open", "assignees": [], "updated_at": AT}),
              "/graphql": (200, {}, {"data": {"repository": {"pullRequest": {"headRefOid": HEAD,
                  "mergeQueueEntry": None, "reviewThreads": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}})}
    f = Fake(routes); c = Client("github", "https://api.github.com", transport=f)
    i = collect(c, "acme/widget", config(), AT)
    assert i["changes"]["status"] == "COMPLETE" and i["changes"]["items"][0]["files"]["items"] == ["src/app.py"]
    assert all(m == "GET" or m == "POST" and b"mutation" not in data for m, _, _, data in f.calls)
    assert i["changes"]["items"][0]["threads"]["status"] == "COMPLETE"


def test_work_cli_offline_end_to_end_and_recheck(tmp_path, capsys):
    for name, value in (("inventory", inv()), ("policy", config()), ("evidence", report())):
        (tmp_path / (name + ".json")).write_bytes(canonical_bytes(value))
    args = ["--inventory", str(tmp_path / "inventory.json"), "--policy", str(tmp_path / "policy.json"),
            "--evidence", str(tmp_path / "evidence.json"), "--store", str(tmp_path / "store")]
    assert main(["work", "build", *args]) == 0
    output = json.loads(capsys.readouterr().out); dest = output["path"]
    assert main(["work", "verify", "--bundle", dest]) == 0; capsys.readouterr()
    scope = verify(dest)["scope.json"]; selected = item(scope, "finish_merge")
    recheck_args = ["work", "recheck", "--bundle", dest, "--inventory", str(tmp_path / "inventory.json"),
                    "--policy", str(tmp_path / "policy.json"), "--item", selected["id"], "--at", AT,
                    "--actor", "owner", "--policy-version", "example-1", "--expected-project-id", "123"]
    assert main(recheck_args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "RECHECKED"
    i = inv(); i["changes"]["items"][0]["head"] = SHA
    (tmp_path / "inventory.json").write_bytes(canonical_bytes(i))
    assert main(recheck_args) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "INVALIDATED"
