"""Demand interface, display configuration and register files."""

import json

import pytest

from devostasis import canonical
from devostasis.adapters import github as github_module
from devostasis.adapters.github import GitHubAdapter, GitHubClient, marker_target_ids, parse_debt_register, parse_targets_register, RegisterError
from devostasis.config import ConfigError, load_config_dict, single_project
from devostasis.demand import DEFAULT_LEVELS, build_demand
from devostasis.gauges import gauges_for_snapshot
from devostasis.history import FilesystemHistoryStore
from devostasis.normalize import INV_DEBT_REGISTER, INV_TARGETS, derive
from devostasis.runner import build_from_observations
from devostasis.vitals import build_snapshot, evaluate_all
from helpers import full_inputs, obs_set
from test_github_adapter import BASE, FakeTransport, NOW, _paged, _routes


def _config(**project):
    return load_config_dict({"config_version": "1", "projects": [dict({"repo": "acme/widget"}, **project)]}).projects[0]


def test_default_demand_levels_cover_every_band():
    from devostasis.vitals import BANDS

    for vital, bands in BANDS.items():
        assert set(DEFAULT_LEVELS[vital]) == set(bands), vital


def test_demand_rows_and_attention_order():
    snapshot = build_snapshot(full_inputs(obs_set()))
    demand = build_demand(snapshot, gauges_for_snapshot(snapshot), {"mapping_version": "t", "levels": DEFAULT_LEVELS})
    rows = {r["vital_id"]: r for r in demand["vitals"]}
    assert rows["integrity"]["level"] == "MINIMAL" and rows["direction"]["level"] == "MEDIUM" and rows["debt"]["level"] == "MEDIUM"
    order = [e["vital_id"] for e in demand["attention_order"]]
    assert order == ["direction", "debt", "clutter", "flow", "horizon", "integrity", "pulse"]
    assert demand["aggregate"] is None and demand["mapping_version"] == "t"
    assert demand["contract"] == "devostasis.demand.v2" and demand["schema"] == "devostasis.demand.v2"
    levels = [e["level"] for e in demand["attention_order"]]
    ranks = [demand["levels"].index(level) for level in levels]
    assert ranks == sorted(ranks)
    assert all("attention_key" not in row for row in demand["vitals"])


def test_role_01_same_level_gauge_invariance():
    snapshot = build_snapshot(full_inputs(obs_set()))
    base = gauges_for_snapshot(snapshot)
    orders = []
    for direction_gauge, debt_gauge in ((0, 100), (100, 0), (37, 37)):
        gauges = [
            dict(g, value=direction_gauge if g["vital_id"] == "direction" else debt_gauge if g["vital_id"] == "debt" else g["value"])
            for g in base
        ]
        demand = build_demand(snapshot, gauges, {"mapping_version": "t", "levels": DEFAULT_LEVELS})
        rows = {r["vital_id"]: r for r in demand["vitals"]}
        assert rows["direction"]["level"] == rows["debt"]["level"] == "MEDIUM"
        orders.append([e["vital_id"] for e in demand["attention_order"]])
        assert all(set(e) == {"vital_id", "level"} for e in demand["attention_order"])
    assert orders[0] == orders[1] == orders[2]
    assert orders[0].index("direction") < orders[0].index("debt")


def test_unknown_vital_is_unresolved_and_first():
    obs = full_inputs(obs_set())
    obs.replace(type(obs.get("ci.configured"))(**dict(obs.get("ci.configured").to_dict(), status="ERROR", value=None, reason_code="PROVIDER_ERROR")))
    obs.replace(type(obs.get("ci.revision_verdicts_14d"))(**dict(obs.get("ci.revision_verdicts_14d").to_dict(), status="ERROR", value=None, reason_code="PROVIDER_ERROR")))
    snapshot = build_snapshot(obs)
    demand = build_demand(snapshot, gauges_for_snapshot(snapshot), {"mapping_version": "t", "levels": DEFAULT_LEVELS})
    assert demand["attention_order"][0] == {"vital_id": "integrity", "level": "UNRESOLVED"}
    rows = {r["vital_id"]: r for r in demand["vitals"]}
    assert rows["integrity"]["gauge"] is None and rows["integrity"]["reason"] == "EVALUATION_UNKNOWN"
    assert demand["aggregate"] is None


def test_demand_overrides_require_a_mapping_version_and_valid_values():
    project = _config(demand={"mapping_version": "team-1", "levels": {"debt": {"PRESENT": "HIGH"}}})
    assert project.demand["levels"]["debt"]["PRESENT"] == "HIGH" and project.demand["levels"]["flow"]["GRIDLOCKED"] == "CRITICAL"
    with pytest.raises(ConfigError):
        _config(demand={"levels": {"debt": {"PRESENT": "HIGH"}}})
    with pytest.raises(ConfigError):
        _config(demand={"mapping_version": "x", "levels": {"debt": {"NOPE": "HIGH"}}})
    with pytest.raises(ConfigError):
        _config(demand={"mapping_version": "x", "levels": {"debt": {"PRESENT": "URGENT"}}})


def test_display_configuration_changes_report_and_identity(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    obs = full_inputs(obs_set())
    full = build_from_observations(_config(), obs, store)
    narrow = build_from_observations(_config(display={"vitals": ["integrity", "flow"], "gauge": ["number", "band"], "sections": ["demand"]}), obs, store)
    assert full.bundle_id != narrow.bundle_id
    report = narrow.members["report.md"].decode("utf-8")
    assert "Integrity" in report and "Horizon" not in report.split("## Vitals")[1]
    assert "█" not in report and "## Observability" not in report and "## Attention" in report
    assert "gauges.json" in narrow.members and "demand.json" in narrow.members
    path = store.commit(narrow)
    from devostasis.bundle import verify_dir

    assert verify_dir(path) == []
    index = store.read_index(narrow.project_key)
    assert index["bundles"][-1]["top_attention"].split(" ")[1] in ("MEDIUM", "HIGH", "CRITICAL", "LOW", "MINIMAL")


def test_display_validation():
    with pytest.raises(ConfigError):
        _config(display={"vitals": ["pulse", "pulse"]})
    with pytest.raises(ConfigError):
        _config(display={"gauge": ["pie"]})
    with pytest.raises(ConfigError):
        _config(display={"sections": ["footer"]})
    project = _config(display={"gauge": ["band", "bar"]})
    assert project.display["gauge"] == ["bar", "band"]


def test_marker_target_ids():
    assert marker_target_ids("Target: T-3\nsome text\nTarget: T-7, done", "Target:") == ["T-3", "T-7"]
    assert marker_target_ids("Fixes #12", "Target:") == []
    assert marker_target_ids("Goal: release/1.2", "Goal:") == ["release/1.2"]


def test_register_parsers():
    targets = parse_targets_register({"schema": "devostasis.targets.v1", "targets": [{"id": "T-1", "title": "Ship", "state": "open", "due": "2026-10-31"}, {"id": "T-0", "state": "done"}]})
    assert [t["target_id"] for t in targets] == ["T-0", "T-1"]
    assert targets[1]["due_at"] == "2026-10-31T00:00:00Z" and targets[0]["state"] == "CLOSED"
    with pytest.raises(RegisterError):
        parse_targets_register({"schema": "other", "targets": []})
    with pytest.raises(RegisterError):
        parse_targets_register({"schema": "devostasis.targets.v1", "targets": [{"id": "A"}, {"id": "A"}]})
    debt = parse_debt_register({"schema": "devostasis.debt.v1", "items": [{"id": "D-1", "title": "Old parser", "opened": "2026-06-01", "updated": "2026-07-01"}, {"id": "D-2", "state": "closed", "opened": "2026-08-01", "closed": "2026-08-20T10:00:00Z"}]})
    assert debt[0]["updated_at"] == "2026-07-01T00:00:00Z" and debt[1]["state"] == "CLOSED"
    with pytest.raises(RegisterError):
        parse_debt_register({"schema": "devostasis.debt.v1", "items": [{"id": "D-3"}]})


def _file_response(document: dict) -> tuple[int, dict, dict]:
    import base64

    content = base64.b64encode(json.dumps(document).encode("utf-8")).decode("ascii")
    return 200, {}, {"type": "file", "size": len(content), "encoding": "base64", "content": content}


def test_file_registers_feed_horizon_direction_and_debt():
    targets = {"schema": "devostasis.targets.v1", "targets": [{"id": "T-3", "title": "Release 1.2", "state": "open", "due": "2026-12-01"}, {"id": "T-2", "state": "closed"}]}
    debt = {"schema": "devostasis.debt.v1", "items": [{"id": "D-1", "title": "Replace parser", "opened": "2026-06-01", "updated": "2026-07-01"}, {"id": "D-2", "state": "closed", "opened": "2026-08-01", "closed": "2026-08-30"}]}
    pulls_open = [
        {"number": 7, "id": 7, "title": "wip", "body": "Target: T-3\n\nDetails", "state": "open", "draft": False, "created_at": "2026-08-25T00:00:00Z", "updated_at": "2026-09-01T00:00:00Z", "merged_at": None, "closed_at": None, "milestone": None, "user": {"login": "a"}, "html_url": "p7"},
        {"number": 8, "id": 8, "title": "orphan", "body": "Target: T-9", "state": "open", "draft": False, "created_at": "2026-08-26T00:00:00Z", "updated_at": "2026-09-02T00:00:00Z", "merged_at": None, "closed_at": None, "milestone": None, "user": {"login": "a"}, "html_url": "p8"},
    ]
    routes = _routes(**{
        f"{BASE}/contents/plans/targets.json": _file_response(targets),
        f"{BASE}/contents/plans/debt.json": _file_response(debt),
        f"{BASE}/pulls": lambda params: _paged(pulls_open)(params),
    })
    transport = FakeTransport(routes)
    project = single_project("acme/widget", planning={"source": "file", "path": "plans/targets.json"}, debt={"source": "file", "path": "plans/debt.json", "mapping_version": "r1"})
    obs = GitHubAdapter(GitHubClient(transport), NOW).collect(project)
    assert not any(path.endswith("/milestones") for path, _ in transport.calls)
    assert obs.get(INV_TARGETS).value[1]["target_id"] == "T-3" and obs.get(INV_DEBT_REGISTER).value[0]["id"] == "D-1"
    crs = {c["number"]: c for c in obs.value_of("forge.change_requests.inventory")}
    assert crs[7]["target_refs"] == [{"target_id": "T-3", "state": "OPEN"}]
    # T-9 is not in the complete register: a broken reference, not missing evidence (DIR-INCOMPLETE-07).
    assert crs[8]["target_refs"] == [{"target_id": "T-9", "state": "MISSING"}]
    derive(obs, project)
    assert obs.value_of("planning.explicit_targets.capability") == "SUPPORTED"
    assert obs.value_of("planning.linkage.active_change_requests_linked_count_28d") == 1
    assert obs.value_of("planning.linkage.active_change_requests_unlinked_count_28d") == 1
    assert obs.value_of("planning.linkage.active_change_requests_linked_to_open_target_count_28d") == 1
    assert obs.value_of("planning.linkage.unknown_target_reference_count_28d") == 0
    assert obs.value_of("planning.linkage.missing_target_reference_count_28d") == 1
    assert obs.value_of("debt.items.open_count") == 1 and obs.value_of("debt.items.open_stale_count_30d") == 1 and obs.value_of("debt.items.closed_count_28d") == 1
    bands = {r.vital_id: r.band for r in evaluate_all(obs)}
    assert bands["horizon"] == "EXTENDED" and bands["direction"] == "MIXED" and bands["debt"] == "PRESENT"
    direction = {r.vital_id: r for r in evaluate_all(obs)}["direction"]
    assert "DIRECTION_TARGET_REFERENCE_MISSING:1" in direction.diagnostics


def test_missing_register_is_explicit_not_undeclared():
    project = single_project("acme/widget", planning={"source": "file", "path": "plans/targets.json"})
    transport = FakeTransport(_routes())
    obs = GitHubAdapter(GitHubClient(transport), NOW).collect(project)
    assert obs.get(INV_TARGETS).status == "UNAVAILABLE" and obs.get(INV_TARGETS).reason_code == "REGISTER_NOT_FOUND"
    derive(obs, project)
    bands = {r.vital_id: (r.band, r.evaluation_status) for r in evaluate_all(obs)}
    assert bands["horizon"] == (None, "UNKNOWN") and bands["direction"] == (None, "UNKNOWN")


def test_invalid_register_is_an_error_observation():
    project = single_project("acme/widget", planning={"source": "file", "path": "plans/targets.json"})
    transport = FakeTransport(_routes(**{f"{BASE}/contents/plans/targets.json": _file_response({"schema": "wrong"})}))
    obs = GitHubAdapter(GitHubClient(transport), NOW).collect(project)
    assert obs.get(INV_TARGETS).status == "ERROR" and obs.get(INV_TARGETS).reason_code == "INVALID_REGISTER"


def test_register_config_validation():
    with pytest.raises(ConfigError):
        single_project("acme/widget", planning={"source": "file"})
    with pytest.raises(ConfigError):
        single_project("acme/widget", planning={"source": "file", "path": "/abs/path.json"})
    with pytest.raises(ConfigError):
        single_project("acme/widget", debt={"source": "file", "mapping_version": "1"})
    legacy = single_project("acme/widget", debt={"labels": ["debt"], "mapping_version": "1"})
    assert legacy.debt_mapping == {"source": "labels", "labels": ["debt"], "mapping_version": "1"}
    project = single_project("acme/widget", planning={"source": "file", "path": "plans/targets.json", "link_marker": "Goal:"})
    assert project.effective_bundle_config()["planning"] == {"source": "file", "path": "plans/targets.json", "link_marker": "Goal:"}
    assert canonical.digest(project.semantic_config()) != canonical.digest(single_project("acme/widget").semantic_config())
