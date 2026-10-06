"""GitHub adapter against a fake transport: status classification, pagination, CI normalization."""

from datetime import datetime, timezone

import pytest

from devostasis.adapters.github import GitHubAdapter, GitHubClient, classify_http_error
from devostasis.config import single_project
from devostasis.normalize import CI_CONFIGURED, CI_REVISIONS, INV_BRANCHES, INV_CRS, INV_ISSUES, INV_TARGETS, derive
from devostasis.observations import AVAILABLE, ERROR, FORBIDDEN, PARTIAL, UNAVAILABLE
from devostasis.vitals import evaluate_all

NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
BASE = "/repos/acme/widget"


class FakeTransport:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        handler = self.routes.get(path)
        if handler is None:
            return 404, {}, {"message": "Not Found"}
        if callable(handler):
            return handler(params or {})
        return handler


def _repo(has_issues=True):
    return 200, {}, {"id": 42, "full_name": "acme/widget", "default_branch": "main", "visibility": "private", "has_issues": has_issues, "archived": False, "pushed_at": "2026-09-05T10:00:00Z", "html_url": "https://github.com/acme/widget"}


def _commit(sha, when):
    return {"sha": sha, "commit": {"message": f"commit {sha}\n\nbody", "committer": {"date": when}, "author": {"date": when}}}


def _paged(items):
    def handler(params):
        page = int(params.get("page", 1))
        per_page = int(params.get("per_page", 100))
        return 200, {}, items[(page - 1) * per_page: page * per_page]
    return handler


def _routes(**overrides):
    commits = [_commit("c1", "2026-09-04T10:00:00Z"), _commit("c2", "2026-09-01T10:00:00Z"), _commit("c3", "2026-08-20T10:00:00Z")]
    pulls_open = [{"number": 7, "id": 7, "title": "wip", "state": "open", "draft": False, "created_at": "2026-08-25T00:00:00Z", "updated_at": "2026-09-01T00:00:00Z", "merged_at": None, "closed_at": None, "milestone": {"number": 1, "state": "open"}, "user": {"login": "a"}, "html_url": "p7"}]
    pulls_recent = pulls_open + [{"number": 6, "id": 6, "title": "done", "state": "closed", "draft": False, "created_at": "2026-08-28T00:00:00Z", "updated_at": "2026-08-29T00:00:00Z", "merged_at": "2026-08-29T00:00:00Z", "closed_at": "2026-08-29T00:00:00Z", "milestone": None, "user": {"login": "a"}, "html_url": "p6"}]
    issues_open = [{"number": 3, "id": 3, "title": "bug", "state": "open", "created_at": "2026-07-01T00:00:00Z", "updated_at": "2026-07-02T00:00:00Z", "closed_at": None, "labels": [{"name": "bug"}], "user": {"login": "b"}, "html_url": "i3"}]
    runs = [
        {"id": 100, "run_attempt": 2, "head_sha": "c1", "status": "completed", "conclusion": "success", "name": "CI", "event": "push", "html_url": "r100", "workflow_id": 1},
        {"id": 101, "run_attempt": 1, "head_sha": "c2", "status": "completed", "conclusion": "success", "name": "CI", "event": "push", "html_url": "r101", "workflow_id": 1},
        {"id": 102, "run_attempt": 1, "head_sha": "c2", "status": "completed", "conclusion": "skipped", "name": "Docs", "event": "push", "html_url": "r102", "workflow_id": 2},
    ]
    routes = {
        BASE: _repo(),
        f"{BASE}/commits": _paged(commits),
        f"{BASE}/pulls": lambda params: _paged(pulls_open if params.get("state") == "open" else pulls_recent)(params),
        f"{BASE}/issues": lambda params: _paged(issues_open if params.get("state") == "open" else [])(params),
        f"{BASE}/branches": _paged([{"name": "main", "commit": {"sha": "c1"}, "protected": True}, {"name": "feature", "commit": {"sha": "c3"}, "protected": False}]),
        f"{BASE}/milestones": _paged([{"number": 1, "id": 1, "title": "v1", "state": "open", "due_on": "2026-10-30T00:00:00Z", "open_issues": 2, "closed_issues": 1, "html_url": "m1"}]),
        f"{BASE}/releases": (200, {}, []),
        f"{BASE}/actions/workflows": (200, {}, {"total_count": 2, "workflows": []}),
        f"{BASE}/actions/runs": lambda params: (200, {}, {"total_count": len(runs), "workflow_runs": runs if int(params.get("page", 1)) == 1 else []}),
        f"{BASE}/actions/runs/100/attempts/1": (200, {}, {"id": 100, "run_attempt": 1, "status": "completed", "conclusion": "failure"}),
    }
    routes.update(overrides)
    return routes


def _collect(routes, **project):
    transport = FakeTransport(routes)
    # A retryable answer must not make the suite wait for real backoff.
    client = GitHubClient(transport, sleep=lambda seconds: None)
    adapter = GitHubAdapter(client, NOW)
    obs = adapter.collect(single_project("acme/widget", **project))
    return obs, transport, client


def test_full_collection_and_evaluation():
    obs, transport, client = _collect(_routes())
    derive(obs, single_project("acme/widget"))
    assert obs.subject["immutable_project_id"] == "42" and obs.subject["default_branch"] == "main"
    assert obs.value_of("git.default_branch.commits.count_28d") == 3
    assert obs.value_of("forge.change_requests.open_count") == 1
    assert obs.value_of("forge.change_requests.merged_count_28d") == 1
    assert obs.value_of("forge.issues.open_count") == 1 and obs.value_of("forge.issues.stale_open_count_30d") == 1
    assert obs.value_of("git.nondefault_branches.stale_count_30d") == 0
    assert obs.value_of("planning.explicit_targets.capability") == "SUPPORTED"
    assert obs.value_of("planning.linkage.active_change_requests_linked_to_open_target_count_28d") == 1
    revisions = obs.value_of(CI_REVISIONS)
    by_sha = {r["revision"]: r for r in revisions}
    assert set(by_sha) == {"c1", "c2"}
    assert by_sha["c1"]["current_verdict"] == "VERIFY_PASS" and by_sha["c1"]["history_state"] == "FAILURE_OBSERVED"
    assert by_sha["c2"]["current_verdict"] == "VERIFY_PASS" and len(by_sha["c2"]["parents"]) == 2
    assert obs.value_of(CI_CONFIGURED) is True
    bands = {r.vital_id: r.band for r in evaluate_all(obs)}
    assert bands["integrity"] == "SPARSE_MIXED" and bands["pulse"] == "STEADY" and bands["flow"] == "MOVING"
    assert bands["horizon"] == "EXTENDED" and bands["direction"] == "MIXED" and bands["debt"] == "UNINSTRUMENTED"
    assert client.request_count > 0 and not hasattr(obs.receipt, "request_count"), "how evidence was fetched is not part of the receipt (v2)"
    assert "CHECKS_SURFACE_NOT_COLLECTED" in obs.receipt.capability_notes


def test_c2_c3_c7_http_failures_become_explicit_statuses():
    routes = _routes(**{
        f"{BASE}/branches": (403, {}, {"message": "Upgrade to GitHub Pro or make this repository public to enable this feature."}),
        f"{BASE}/milestones": (403, {"x-ratelimit-remaining": "5"}, {"message": "Resource not accessible by integration"}),
        f"{BASE}/pulls": (503, {}, {"message": "Service Unavailable"}),
    })
    obs, _, _ = _collect(routes)
    assert obs.status_of(INV_BRANCHES) == UNAVAILABLE and obs.get(INV_BRANCHES).reason_code == "TIER_UNAVAILABLE"
    assert obs.status_of(INV_TARGETS) == FORBIDDEN
    assert obs.status_of(INV_CRS) == ERROR and obs.get(INV_CRS).reason_code == "PROVIDER_ERROR"
    assert obs.value_of(INV_CRS) is None


def test_issues_disabled_is_unavailable_not_zero():
    routes = _routes(**{BASE: _repo(has_issues=False)})
    obs, transport, _ = _collect(routes)
    assert obs.status_of(INV_ISSUES) == UNAVAILABLE and obs.get(INV_ISSUES).reason_code == "ISSUES_DISABLED"
    assert not any(path.endswith("/issues") for path, _ in transport.calls)


def test_c4_pagination_cap_is_partial(monkeypatch):
    from devostasis.adapters import github as github_module

    monkeypatch.setattr(github_module, "MAX_COMMIT_PAGES", 2)
    many = [_commit(f"s{i:03d}", "2026-09-01T10:00:00Z") for i in range(250)]
    obs, _, _ = _collect(_routes(**{f"{BASE}/commits": _paged(many)}))
    commits = obs.get("git.default_branch.commits_28d")
    assert commits.status == PARTIAL and commits.reason_code == "PAGINATION_CAPPED" and len(commits.value) == 200
    derive(obs, single_project("acme/widget"))
    assert obs.status_of("git.default_branch.commits.count_28d") == PARTIAL
    bands = {r.vital_id: r for r in evaluate_all(obs)}
    assert bands["pulse"].evaluation_status == "DEGRADED" and bands["pulse"].band_semantics == "CONSERVATIVE_LOWER_BOUND"
    assert bands["integrity"].evaluation_status == "UNKNOWN" and bands["integrity"].band is None, "a truncated required series is UNKNOWN (PV-REV-TEST-003)"


def test_no_workflows_and_no_check_suites_is_positively_uninstrumented():
    routes = _routes(**{
        f"{BASE}/actions/workflows": (200, {}, {"total_count": 0, "workflows": []}),
        f"{BASE}/commits/c1/check-suites": (200, {}, {"total_count": 0, "check_suites": []}),
        f"{BASE}/commits/c2/check-suites": (200, {}, {"total_count": 0, "check_suites": []}),
    })
    obs, _, _ = _collect(routes)
    assert obs.value_of(CI_CONFIGURED) is False
    assert all(not r["parents"] for r in obs.value_of(CI_REVISIONS))
    assert {r.vital_id: r.band for r in evaluate_all(derive(obs, single_project("acme/widget")))}["integrity"] == "UNINSTRUMENTED"


def test_external_check_suites_are_parent_level_provenance():
    routes = _routes(**{
        f"{BASE}/actions/workflows": (200, {}, {"total_count": 0, "workflows": []}),
        f"{BASE}/commits/c1/check-suites": (200, {}, {"total_count": 1, "check_suites": [{"id": 9, "status": "completed", "conclusion": "failure", "app": {"slug": "circleci"}, "url": "s9", "latest_check_runs_count": 3}]}),
        f"{BASE}/commits/c2/check-suites": (200, {}, {"total_count": 0, "check_suites": []}),
    })
    obs, _, _ = _collect(routes)
    revisions = {r["revision"]: r for r in obs.value_of(CI_REVISIONS)}
    assert revisions["c1"]["history_provenance"] == "PARENT_LEVEL_ONLY" and revisions["c1"]["current_verdict"] == "VERIFY_FAIL"
    assert obs.value_of(CI_CONFIGURED) is True


def test_classify_http_error_table():
    assert classify_http_error(401, {"message": "Bad credentials"}, {}) == (FORBIDDEN, "UNAUTHENTICATED", False)
    assert classify_http_error(403, {"message": "API rate limit exceeded"}, {}) == (ERROR, "RATE_LIMITED", True)
    assert classify_http_error(403, {"message": "x"}, {"x-ratelimit-remaining": "0"}) == (ERROR, "RATE_LIMITED", True)
    assert classify_http_error(404, {}, {}) == (UNAVAILABLE, "NOT_FOUND", False)
    assert classify_http_error(410, {}, {}) == (UNAVAILABLE, "DISABLED", False)
    assert classify_http_error(500, {}, {}) == (ERROR, "PROVIDER_ERROR", True)


def test_planning_source_none_skips_milestone_requests():
    obs, transport, _ = _collect(_routes(), planning={"source": "none"})
    assert obs.status_of(INV_TARGETS) == UNAVAILABLE
    assert not any(path.endswith("/milestones") for path, _ in transport.calls)
    derive(obs, single_project("acme/widget", planning={"source": "none"}))
    assert obs.value_of("planning.explicit_targets.capability") == "UNSUPPORTED"


def test_collection_error_when_repository_is_unreachable():
    import pytest
    from devostasis.adapters.github import CollectionError

    with pytest.raises(CollectionError):
        _collect({BASE: (404, {}, {"message": "Not Found"})})


def test_observation_set_round_trips_through_json(tmp_path):
    obs, _, _ = _collect(_routes())
    path = tmp_path / "obs.json"
    obs.save(path)
    from devostasis.observations import ObservationSet

    loaded = ObservationSet.load(path)
    assert loaded.digest() == obs.digest()


def test_a_full_page_of_releases_is_partial_not_complete():
    """A capped enumeration is never complete evidence, even when nothing failed."""
    from devostasis.adapters.github import MAX_RELEASES
    from devostasis.normalize import INV_RELEASES

    full_page = [
        {"tag_name": f"v{i}", "name": f"release {i}", "published_at": f"2026-09-{i % 28 + 1:02d}T10:00:00Z", "draft": False, "prerelease": False, "html_url": f"r{i}"}
        for i in range(MAX_RELEASES)
    ]
    obs, _, _ = _collect(_routes(**{f"{BASE}/releases": (200, {}, full_page)}))
    item = obs.get(INV_RELEASES)
    assert item.status == PARTIAL and item.reason_code == "PAGINATION_CAPPED"
    assert item.coverage["complete"] is False and item.coverage["limit"] == MAX_RELEASES

    short_page = full_page[:-1]
    obs, _, _ = _collect(_routes(**{f"{BASE}/releases": (200, {}, short_page)}))
    item = obs.get(INV_RELEASES)
    assert item.status == AVAILABLE and item.reason_code is None and item.coverage["complete"] is True


# --------------------------------------------------------------------------- error boundaries (#12 finding 5)


def test_a_register_title_that_is_only_whitespace_is_a_register_error_not_a_crash():
    """`text.strip().splitlines()[0]` raised IndexError, which no boundary caught."""
    from devostasis.adapters.github import RegisterError, parse_targets_register

    items = parse_targets_register({"schema": "devostasis.targets.v1", "targets": [{"id": "T-1", "title": "   "}]})
    assert items[0]["title"] == ""
    try:
        parse_targets_register({"schema": "devostasis.targets.v1", "targets": [{"id": "T-1", "title": 1}]})
    except RegisterError as exc:
        assert "must be a string" in str(exc)
    else:
        raise AssertionError("a non-string target title must be an invalid register")


def test_a_debt_title_of_the_wrong_type_is_a_register_error():
    from devostasis.adapters.github import RegisterError, parse_debt_register

    document = {"schema": "devostasis.debt.v1", "items": [{"id": "D-1", "title": ["not", "a", "string"], "opened": "2026-01-01"}]}
    try:
        parse_debt_register(document)
    except RegisterError as exc:
        assert "D-1" in str(exc)
    else:
        raise AssertionError("a non-string debt title must be an invalid register")


def test_a_provider_title_of_the_wrong_type_is_a_missing_title_not_a_failed_run():
    """Commit messages, change-request and issue titles are payload, not contract."""
    from devostasis.adapters.github import _title

    assert _title(None) == "" and _title("") == "" and _title("   \n  ") == ""
    assert _title(7) == "" and _title(["a"]) == ""
    assert _title("  first line\nsecond") == "first line"


def test_an_invalid_register_reaches_the_snapshot_as_an_error_observation():
    """The contract says INVALID_REGISTER, and only a RegisterError can produce it."""
    import base64
    import json as json_mod

    register = json_mod.dumps({"schema": "devostasis.targets.v1", "targets": [{"id": "T-1", "title": 1}]})
    routes = _routes()
    routes[f"{BASE}/contents/.devostasis/targets.json"] = (
        200,
        {},
        {"type": "file", "size": len(register.encode("utf-8")), "encoding": "base64", "content": base64.b64encode(register.encode("utf-8")).decode("ascii")},
    )
    client = GitHubClient(FakeTransport(routes))
    project = single_project("acme/widget", planning={"source": "file", "path": ".devostasis/targets.json"})
    obs = GitHubAdapter(client, NOW).collect(project)
    targets = obs.get(INV_TARGETS)
    assert targets.status == ERROR and targets.reason_code == "INVALID_REGISTER"


def test_a_successful_response_that_is_not_json_becomes_a_declared_provider_failure():
    """HTTP 200 with an unreadable body escaped every handler as a ValueError."""
    import io

    from devostasis.adapters.github import ApiFailure, UrllibTransport

    class _Response(io.BytesIO):
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    transport = UrllibTransport(token=None)
    transport._open = lambda request: _Response(b"<html>maintenance</html>")
    try:
        transport.get("/repos/acme/widget")
    except ApiFailure as exc:
        assert exc.reason_code == "MALFORMED_RESPONSE" and exc.status_code == 200
    else:
        raise AssertionError("a 200 with a non-JSON body must be a declared failure")


# --------------------------------------------------------------------------- linkage evidence (PV-REV-PR-015, PV-DIRECTION-INCOMPLETE-001)


def _pull(number=7, **fields):
    base = {
        "number": number,
        "id": number,
        "title": "wip",
        "body": None,
        "state": "open",
        "draft": False,
        "created_at": "2026-08-25T00:00:00Z",
        "updated_at": "2026-09-01T00:00:00Z",
        "merged_at": None,
        "closed_at": None,
        "milestone": None,
        "user": {"login": "a"},
        "html_url": "p7",
    }
    base.update(fields)
    return base


def _file_planning_project():
    return single_project("acme/widget", planning={"source": "file", "path": ".devostasis/targets.json", "link_marker": "Target:"})


def _observe(routes, project):
    return GitHubAdapter(GitHubClient(FakeTransport(routes)), NOW).collect(project)


def _register_route(ids_and_states):
    import base64
    import json as _json

    document = {"schema": "devostasis.targets.v1", "targets": [{"id": tid, "state": state} for tid, state in ids_and_states]}
    content = base64.b64encode(_json.dumps(document).encode("utf-8")).decode("ascii")
    return 200, {}, {"type": "file", "size": len(content), "encoding": "base64", "content": content}


def _file_planning_routes(pulls, register=(("B1", "open"),)):
    return _routes(**{f"{BASE}/pulls": _paged(pulls), f"{BASE}/contents/.devostasis/targets.json": _register_route(register)})


@pytest.mark.parametrize("field, value", [("title", 7), ("title", ["a"]), ("body", {"a": 1}), ("body", 3.5)])
def test_unreadable_linkage_evidence_is_unresolved_not_unlinked_and_not_a_failed_project(field, value):
    """`Target: <id>` lives in the title and the body, so payload of the wrong type there is not an absent link.

    Since PV-DIRECTION-INCOMPLETE-001 it is not a failed project either: the
    change request keeps what could be read, names what could not, and enters
    Direction as UNRESOLVED instead of UNLINKED.
    """
    project = _file_planning_project()
    obs = _observe(_file_planning_routes([_pull(**{field: value})]), project)
    record = obs.get(INV_CRS).value[0]
    assert record["target_refs"] == [] and record["linkage_unresolved"] == [f"{field}:{type(value).__name__}"]
    derive(obs, project)
    assert obs.value_of("planning.linkage.active_change_requests_unresolved_count_28d") == 1
    assert obs.value_of("planning.linkage.active_change_requests_unlinked_count_28d") == 0
    assert obs.value_of("planning.linkage.unresolved_change_requests_28d") == {"7": [f"LINKAGE_UNREADABLE:{field}:{type(value).__name__}"]}
    direction = {r.vital_id: r for r in evaluate_all(obs)}["direction"]
    assert (direction.band, direction.evaluation_status) == (None, "UNKNOWN"), "one unresolved of one could be FULLY_LINKED or SCATTERED"


def test_a_readable_link_is_not_undone_by_an_unreadable_field():
    """Unreadable evidence can only add references, and a resolved one already links the change request."""
    project = _file_planning_project()
    obs = _observe(_file_planning_routes([_pull(title="Target: B1", body={"not": "text"})]), project)
    record = obs.get(INV_CRS).value[0]
    assert record["target_refs"] == [{"target_id": "B1", "state": "OPEN"}] and record["linkage_unresolved"] == ["body:dict"]
    derive(obs, project)
    assert obs.value_of("planning.linkage.active_change_requests_linked_count_28d") == 1
    assert obs.value_of("planning.linkage.active_change_requests_unresolved_count_28d") == 0


def test_a_change_request_with_no_marker_is_unlinked_and_that_is_not_an_error():
    """The distinction the unresolved state exists to preserve: absent evidence is a fact, unreadable evidence is not."""
    routes = _routes(**{f"{BASE}/pulls": _paged([_pull(title="nothing to see", body="no marker here")])})
    item = _observe(routes, _file_planning_project()).get(INV_CRS)
    assert item.status == AVAILABLE
    assert item.value[0]["target_refs"] == [] and item.value[0]["target_id"] is None and item.value[0]["linkage_unresolved"] == []


def test_a_marker_in_the_body_still_links_after_the_repair():
    routes = _routes(**{f"{BASE}/pulls": _paged([_pull(title="a change", body="Target: B1")])})
    item = _observe(routes, _file_planning_project()).get(INV_CRS)
    assert item.value[0]["target_id"] == "B1"


def test_a_milestone_without_a_number_is_unresolved_linkage_not_a_failed_project():
    """Under planning.source=milestones the milestone *is* the link; a malformed one is unreadable evidence, kept as such."""
    project = single_project("acme/widget")
    routes = _routes(**{f"{BASE}/pulls": _paged([_pull(milestone={"state": "open"})])})
    obs = _observe(routes, project)
    record = obs.get(INV_CRS).value[0]
    assert record["target_refs"] == [] and record["linkage_unresolved"] == ["milestone:NO_NUMBER"]
    derive(obs, project)
    assert obs.value_of("planning.linkage.active_change_requests_unresolved_count_28d") == 1


def test_a_reference_the_complete_register_lacks_is_missing_and_one_the_register_could_not_answer_is_unknown():
    """DIR-INCOMPLETE-07 against DIR-INCOMPLETE-09: positive absence is a broken reference, an unreadable register is no evidence."""
    project = _file_planning_project()
    present = _observe(_file_planning_routes([_pull(body="Target: T-9")]), project)
    assert present.get(INV_CRS).value[0]["target_refs"] == [{"target_id": "T-9", "state": "MISSING"}]
    absent = _observe(_routes(**{f"{BASE}/pulls": _paged([_pull(body="Target: T-9")])}), project)
    assert absent.get(INV_TARGETS).reason_code == "REGISTER_NOT_FOUND"
    assert absent.get(INV_CRS).value[0]["target_refs"] == [{"target_id": "T-9", "state": "UNKNOWN"}]


def test_a_closed_register_target_is_still_a_resolved_reference():
    """DIR-CLOSED-03 at the adapter: the register resolves the id, and its lifecycle is carried, not used to unlink."""
    project = _file_planning_project()
    obs = _observe(_file_planning_routes([_pull(body="Target: B1")], register=(("B1", "closed"),)), project)
    assert obs.get(INV_CRS).value[0]["target_refs"] == [{"target_id": "B1", "state": "CLOSED"}]
    derive(obs, project)
    assert obs.value_of("planning.linkage.active_change_requests_linked_count_28d") == 1
    assert obs.value_of("planning.linkage.active_change_requests_linked_to_open_target_count_28d") == 0


# --------------------------------------------------------------------------- register shapes (#12 finding 5)


@pytest.mark.parametrize(
    "document, expected",
    [
        ([], "must be an object"),
        ("not a document", "must be an object"),
        ({"schema": "devostasis.targets.v1", "targets": {"T-1": "open"}}, "requires a targets list"),
        ({"schema": "devostasis.targets.v1", "targets": [1]}, "string id"),
        ({"schema": "devostasis.targets.v1", "targets": [{"id": "T-1", "title": "x", "due": "the third of never"}]}, "invalid date"),
        ({"schema": "devostasis.targets.v1", "targets": [{"id": "T-1", "title": "x", "due": 20260101}]}, "date must be a string"),
    ],
)
def test_a_register_of_the_wrong_shape_or_with_an_invalid_date_is_an_invalid_register(document, expected):
    from devostasis.adapters.github import RegisterError, parse_targets_register

    try:
        parse_targets_register(document)
    except RegisterError as exc:
        assert expected in str(exc)
    else:
        raise AssertionError(f"{document!r} must not parse as a valid register")


def test_an_invalid_date_reaches_the_snapshot_as_an_error_observation():
    """The whole point of RegisterError: it survives the collector as a status, not as a crash."""
    import base64
    import json as json_mod

    register = json_mod.dumps({"schema": "devostasis.targets.v1", "targets": [{"id": "T-1", "title": "x", "due": "the third of never"}]})
    routes = _routes()
    routes[f"{BASE}/contents/.devostasis/targets.json"] = (
        200,
        {},
        {"type": "file", "size": len(register.encode("utf-8")), "encoding": "base64", "content": base64.b64encode(register.encode("utf-8")).decode("ascii")},
    )
    targets = _observe(routes, _file_planning_project()).get(INV_TARGETS)
    assert targets.status == ERROR and targets.reason_code == "INVALID_REGISTER"


# --------------------------------------------------------------------------- malformed payloads and a silent surface switch (review 2026-09-22)


def test_a_successful_response_of_the_wrong_shape_costs_one_inventory_not_the_project():
    """A 200 whose body is not the documented shape used to escape as AttributeError and end the project."""
    from devostasis.normalize import INV_RELEASES

    obs, _, _ = _collect(_routes(**{f"{BASE}/actions/runs": (200, {}, None)}))
    revisions = obs.get(CI_REVISIONS)
    assert revisions.status == ERROR and revisions.reason_code == "UNEXPECTED_PAYLOAD"
    assert obs.status_of(INV_CRS) == AVAILABLE, "the other inventories were still collected"

    obs, _, _ = _collect(_routes(**{f"{BASE}/actions/runs": (200, {}, {"total_count": 1, "workflow_runs": {"id": 1}})}))
    assert obs.get(CI_REVISIONS).reason_code == "UNEXPECTED_PAYLOAD"

    obs, _, _ = _collect(_routes(**{f"{BASE}/releases": (200, {}, {"message": "unexpected"})}))
    releases = obs.get(INV_RELEASES)
    assert releases.status == ERROR and releases.reason_code == "UNEXPECTED_PAYLOAD"
    assert obs.status_of(CI_REVISIONS) == AVAILABLE


def test_a_failed_workflow_lookup_is_recorded_when_check_suites_supply_the_evidence():
    """Actions FORBIDDEN, check suites readable: the evidence is parent-level, and the receipt must say why."""
    actions_suite = {"id": 9, "status": "completed", "conclusion": "success", "app": {"slug": "github-actions"}, "url": "s9", "latest_check_runs_count": 3}
    routes = _routes(**{
        f"{BASE}/actions/workflows": (403, {}, {"message": "Resource not accessible by integration"}),
        f"{BASE}/commits/c1/check-suites": (200, {}, {"total_count": 1, "check_suites": [actions_suite]}),
        f"{BASE}/commits/c2/check-suites": (200, {}, {"total_count": 0, "check_suites": []}),
    })
    obs, transport, _ = _collect(routes)
    assert not any(path.endswith("/actions/runs") for path, _ in transport.calls), "runs are never asked for without a workflow count"
    revisions = obs.get(CI_REVISIONS)
    assert revisions.status == AVAILABLE and revisions.coverage["surface"] == "github_check_suites"
    assert obs.value_of(CI_CONFIGURED) is True
    assert "WORKFLOWS_UNAVAILABLE:FORBIDDEN" in obs.receipt.capability_notes
    assert "CI_SURFACE:GITHUB_CHECK_SUITES_SAMPLED" in obs.receipt.capability_notes
    assert "CI_SURFACE:GITHUB_ACTIONS_ONLY" not in obs.receipt.capability_notes

    plain, _, _ = _collect(_routes())
    assert not any(note.startswith("WORKFLOWS_UNAVAILABLE") for note in plain.receipt.capability_notes)


# --------------------------------------------------------------------------- check-suite coverage (#12 finding 1)


def _window_commits(count):
    """`count` default-branch commits inside the 14-day Integrity window, newest first in the API order."""
    return [_commit(f"w{i:03d}", f"2026-09-{5 - (i % 10) // 1 if False else 5:02d}T{(23 - i % 24):02d}:{(59 - i // 24) % 60:02d}:00Z") for i in range(count)]


def _suite(suite_id, conclusion="success", app="circleci"):
    return {"id": suite_id, "status": "completed", "conclusion": conclusion, "app": {"slug": app}, "url": f"s{suite_id}", "latest_check_runs_count": 1}


def _suite_routes(commits, suites_by_sha, workflows_total=0):
    routes = _routes(**{
        f"{BASE}/commits": _paged(commits),
        f"{BASE}/actions/workflows": (200, {}, {"total_count": workflows_total, "workflows": []}),
    })
    for commit in commits:
        sha = commit["sha"]
        suites = suites_by_sha.get(sha, [])

        def handler(params, suites=suites):
            page = int(params.get("page", 1))
            per_page = int(params.get("per_page", 100))
            return 200, {}, {"total_count": len(suites), "check_suites": suites[(page - 1) * per_page: page * per_page]}

        routes[f"{BASE}/commits/{sha}/check-suites"] = handler
    return routes


def test_check_suites_examined_for_every_revision_are_complete_evidence():
    commits = _window_commits(100)
    routes = _suite_routes(commits, {c["sha"]: [_suite(i)] for i, c in enumerate(commits)})
    obs, _, _ = _collect(routes)
    item = obs.get(CI_REVISIONS)
    assert item.status == AVAILABLE and item.coverage["suites_complete"] is True
    assert item.coverage["suite_revisions_planned"] == 100 and item.coverage["suite_revisions_examined"] == 100
    assert item.coverage["suites_stop_reason"] is None


def test_the_hundred_and_first_revision_makes_the_suite_sample_partial():
    """The exact boundary the review asked for: 101 revisions, suites examined for 100, every one passing."""
    commits = _window_commits(101)
    routes = _suite_routes(commits, {c["sha"]: [_suite(i)] for i, c in enumerate(commits)})
    obs, _, _ = _collect(routes)
    item = obs.get(CI_REVISIONS)
    assert item.status == PARTIAL and item.reason_code == "CHECK_SUITES_INCOMPLETE"
    assert item.coverage["suite_revisions_planned"] == 101 and item.coverage["suite_revisions_examined"] == 100
    assert item.coverage["suites_stop_reason"] == "CHECK_SUITE_SAMPLE_CAPPED"
    assert sum(1 for record in item.value if record["parents"]) == 100, "the evidence collected is kept"
    derive(obs, single_project("acme/widget"))
    integrity = {r.vital_id: r for r in evaluate_all(obs)}["integrity"]
    assert integrity.evaluation_status == "UNKNOWN" and integrity.band is None, "a truncated sample is never an exact favourable result"


def test_an_access_failure_after_four_revisions_makes_the_sample_partial_and_keeps_what_was_seen():
    commits = _window_commits(5)
    suites = {c["sha"]: [_suite(i, "failure" if i == 1 else "success")] for i, c in enumerate(commits)}
    routes = _suite_routes(commits, suites)
    routes[f"{BASE}/commits/{commits[4]['sha']}/check-suites"] = (403, {}, {"message": "Resource not accessible by integration"})
    obs, _, _ = _collect(routes)
    item = obs.get(CI_REVISIONS)
    assert item.status == PARTIAL and item.reason_code == "CHECK_SUITES_INCOMPLETE"
    assert item.coverage["suites_stop_reason"] == "FORBIDDEN"
    assert item.coverage["suite_revisions_examined"] == 4, "the revision whose request failed was not examined"
    assert "CHECK_SUITES_UNAVAILABLE:FORBIDDEN" in obs.receipt.capability_notes
    failed = [record for record in item.value if record["history_state"] == "FAILURE_OBSERVED"]
    assert len(failed) == 1, "an observed failure is retained"
    assert obs.value_of(CI_CONFIGURED) is True


def test_a_second_page_of_suites_is_read_and_a_capped_page_count_is_partial():
    from devostasis.adapters import github as github_module

    commits = _window_commits(1)
    sha = commits[0]["sha"]
    routes = _suite_routes(commits, {sha: [_suite(i) for i in range(100)] + [_suite(100, "failure")]})
    obs, transport, _ = _collect(routes)
    item = obs.get(CI_REVISIONS)
    assert item.status == AVAILABLE, "101 suites over two pages are complete evidence"
    assert item.value[0]["history_state"] == "FAILURE_OBSERVED", "the failing suite on the second page is seen"
    assert [params.get("page") for path, params in transport.calls if path.endswith("/check-suites")] == [1, 2]

    original = github_module.MAX_SUITE_PAGES
    github_module.MAX_SUITE_PAGES = 1
    try:
        obs, _, _ = _collect(routes)
    finally:
        github_module.MAX_SUITE_PAGES = original
    item = obs.get(CI_REVISIONS)
    assert item.status == PARTIAL and item.coverage["suites_complete"] is False
    assert item.coverage["suites_stop_reason"] == "PAGINATION_CAPPED"


def test_a_spent_budget_makes_the_suite_sample_partial():
    commits = _window_commits(6)
    routes = _suite_routes(commits, {c["sha"]: [_suite(i)] for i, c in enumerate(commits)})
    client = GitHubClient(FakeTransport(routes), budget=12)
    obs = GitHubAdapter(client, NOW).collect(single_project("acme/widget"))
    item = obs.get(CI_REVISIONS)
    assert item.status == PARTIAL and item.reason_code in ("CHECK_SUITES_INCOMPLETE", "REQUEST_BUDGET_EXHAUSTED")
    assert item.coverage["suites_stop_reason"] == "REQUEST_BUDGET_EXHAUSTED"
    assert item.coverage["suite_revisions_examined"] < 6


def test_the_actions_surface_is_untouched_by_suite_coverage():
    obs, _, _ = _collect(_routes())
    item = obs.get(CI_REVISIONS)
    assert item.status == AVAILABLE and item.coverage["surface"] == "github_actions"
    assert item.coverage["suites_complete"] is True and item.coverage["suite_revisions_planned"] == 0
@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        "two",
        {"total_count": "many", "workflows": []},
        {"total_count": True, "workflows": []},
        {"total_count": -1, "workflows": []},
        {"workflows": []},
    ],
    ids=["null", "list", "string", "text count", "boolean count", "negative count", "no count"],
)
def test_a_malformed_workflows_answer_is_a_declared_failure_not_an_invented_count(body):
    """PV-REV-PR-029: a 200 from /actions/workflows of the wrong shape or value must reach the
    declared per-inventory boundary. Before, a non-object body raised AttributeError and a
    non-numeric total_count raised ValueError past the WORKFLOWS_UNAVAILABLE fallback."""
    routes = _routes(**{
        f"{BASE}/actions/workflows": (200, {}, body),
        f"{BASE}/commits/c1/check-suites": (200, {}, {"total_count": 0, "check_suites": []}),
        f"{BASE}/commits/c2/check-suites": (200, {}, {"total_count": 0, "check_suites": []}),
    })
    obs, transport, _ = _collect(routes)
    configured = obs.get(CI_CONFIGURED)
    assert configured.status == ERROR and configured.reason_code == "UNEXPECTED_PAYLOAD", "no workflow count is invented"
    assert configured.value is None
    assert "WORKFLOWS_UNAVAILABLE:UNEXPECTED_PAYLOAD" in obs.receipt.capability_notes
    assert not any(path.endswith("/actions/runs") for path, _ in transport.calls), "runs are never asked for without a workflow count"
    assert obs.status_of(INV_CRS) == AVAILABLE and obs.status_of(INV_ISSUES) == AVAILABLE, "independent inventories are still collected"
    revisions = obs.get(CI_REVISIONS)
    assert revisions.status == AVAILABLE and revisions.coverage["surface"] == "none", "the check-suite surface was sampled instead"
    derive(obs, single_project("acme/widget"))
    integrity = {r.vital_id: r for r in evaluate_all(obs)}["integrity"]
    assert integrity.evaluation_status == "UNKNOWN" and integrity.band is None, "an unreadable Actions surface is never UNINSTRUMENTED"


def test_a_malformed_workflows_answer_still_lets_external_check_suites_supply_the_evidence():
    """The fallback the note exists for: Actions unreadable, an external suite readable."""
    suite = {"id": 9, "status": "completed", "conclusion": "failure", "app": {"slug": "circleci"}, "url": "s9", "latest_check_runs_count": 3}
    routes = _routes(**{
        f"{BASE}/actions/workflows": (200, {}, {"total_count": None}),
        f"{BASE}/commits/c1/check-suites": (200, {}, {"total_count": 1, "check_suites": [suite]}),
        f"{BASE}/commits/c2/check-suites": (200, {}, {"total_count": 0, "check_suites": []}),
    })
    obs, _, _ = _collect(routes)
    assert obs.value_of(CI_CONFIGURED) is True
    revisions = {r["revision"]: r for r in obs.value_of(CI_REVISIONS)}
    assert revisions["c1"]["current_verdict"] == "VERIFY_FAIL" and revisions["c1"]["history_provenance"] == "PARENT_LEVEL_ONLY"
    assert "WORKFLOWS_UNAVAILABLE:UNEXPECTED_PAYLOAD" in obs.receipt.capability_notes


def test_a_well_formed_workflows_answer_is_read_as_before():
    from devostasis.adapters.github import _workflows_total

    assert _workflows_total("/x", {"total_count": 0, "workflows": []}) == 0
    assert _workflows_total("/x", {"total_count": 7}) == 7
