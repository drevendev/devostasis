"""Durable Integrity revision history across bundles (PV-HIST-002, target B3).

The reconciliation cases are vectors (tests/vectors/revision-history.json).
These are the cases about the chain: which bundle a build carries history
from, what happens when that bundle cannot be read, and what the carried
history does to the identity of the bundle that consumed it.
"""

from __future__ import annotations

import copy
import shutil

import pytest

from devostasis.bundle import BundleError, verify_dir
from devostasis.config import single_project
from devostasis.history import FilesystemHistoryStore
from devostasis.observations import Observation, ObservationSet
from devostasis.revision_history import CARRIED, LINEAGE, REPLAYABLE_LINEAGE
from devostasis.runner import build_from_observations
from helpers import add, finalize, full_inputs, obs_set, parent, revision

LOCATOR = "acme/widget"
PROJECT_ID = "42"


def _run(run_id, attempts, latest=None):
    """An Actions parent; ``attempts`` are the (number, state) pairs the provider shows."""
    latest = latest or max(n for n, _ in attempts)
    record = parent(f"github_actions:workflow_run:{run_id}", attempts[-1][1], [s for _, s in attempts])
    record["attempts_observed"] = [{"attempt": n, "state": s} for n, s in sorted(attempts)]
    record["current_attempt"] = latest
    record["attempts_complete"] = len(attempts) == latest
    return record


def _record(sha, day, parents):
    states = [a["state"] for p in parents for a in p["attempts_observed"]]
    complete = all(p["kind"] == "github_actions_workflow_run" and p["attempts_complete"] for p in parents)
    if not parents:
        history = "NO_DECISIVE_OBSERVED"
    elif "VERIFY_FAIL" in states:
        history = "FAILURE_OBSERVED"
    elif not complete:
        history = "UNKNOWN_HISTORY"
    else:
        history = "PASS_ONLY_OBSERVED"
    current = [p["current_state"] for p in parents]
    verdict = "VERIFY_FAIL" if "VERIFY_FAIL" in current else ("VERIFY_PASS" if current else None)
    record = revision(sha, f"2026-09-{day:02d}T10:00:00Z", parents, verdict, history)
    record["history_complete"] = complete
    return record


def _passing(days):
    return [_record(f"p{day}", day, [_run(800 + day, [(1, "VERIFY_PASS")])]) for day in days]


def _obs(observed_at, revisions, project_id=PROJECT_ID, series_status="AVAILABLE"):
    obs = full_inputs(obs_set(observed_at))
    obs.subject = dict(obs.subject, owner="acme", repo="widget", display_locator=LOCATOR, immutable_project_id=project_id)
    item = obs.get("ci.revision_verdicts_14d")
    value = revisions if series_status in ("AVAILABLE", "PARTIAL") else None
    obs.replace(Observation.from_dict(dict(item.to_dict(), value=value, status=series_status, reason_code=None if series_status == "AVAILABLE" else "PROVIDER_ERROR")))
    return obs


def _build(store, observed_at, revisions, **kwargs):
    project = single_project(LOCATOR, config_version="1")
    bundle = build_from_observations(project, _obs(observed_at, revisions, **kwargs), store)
    path = store.commit(bundle)
    return bundle, path


def _integrity(bundle):
    import json

    snapshot = json.loads(bundle.members["snapshot.json"].decode("utf-8"))
    return next(v for v in snapshot["vitals"] if v["vital_id"] == "integrity")


def _carried(bundle):
    import json

    observations = json.loads(bundle.members["observations.json"].decode("utf-8"))
    return next(o for o in observations["observations"] if o["observation_id"] == CARRIED)


def _states(bundle):
    return {r["revision"]: r["history_state"] for r in _integrity(bundle)["derived"]["revision_history"]["records"]}


RUN_R = 41


def _chain(store):
    """B1 sees r pass, B2 sees a same-revision failure, B3 sees only the pass again."""
    b1, _ = _build(store, "2026-09-06T12:00:00Z", _passing([1, 2, 3]) + [_record("r", 4, [_run(RUN_R, [(1, "VERIFY_PASS")])])])
    b2, b2_path = _build(store, "2026-09-07T12:00:00Z", _passing([1, 2, 3]) + [_record("r", 4, [_run(RUN_R, [(1, "VERIFY_PASS"), (2, "VERIFY_FAIL")])])])
    return b1, b2, b2_path


def test_hist_20_the_immediate_predecessor_carries_a_failure_an_older_bundle_did_not_see(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    b1, b2, _ = _chain(store)
    assert _states(b1)["r"] == "PASS_ONLY_OBSERVED" and _states(b2)["r"] == "FAILURE_OBSERVED"
    # B3: the provider retained only the passing retry, attempt 3, and cannot show 1 and 2.
    b3, _ = _build(store, "2026-09-08T12:00:00Z", _passing([1, 2, 3, 5]) + [_record("r", 4, [_run(RUN_R, [(3, "VERIFY_PASS")], latest=3)])])
    assert _carried(b3)["value"]["source_bundle_id"] == b2.bundle_id, "the source is B2, never B1"
    assert _states(b3)["r"] == "FAILURE_OBSERVED"
    integrity = _integrity(b3)
    assert integrity["derived"]["failed_count_14d"] == 1 and integrity["band"] == "FLAKY"
    assert integrity["derived"]["revision_history"]["source"] == {
        "status": "CARRIED", "lineage": LINEAGE, "bundle_id": b2.bundle_id, "observed_at": "2026-09-07T12:00:00Z", "basis": "SNAPSHOT",
    }


def test_hist_20_and_hist_08_a_lost_predecessor_is_a_gap_and_nothing_older_is_carried(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    b1, b2, b2_path = _chain(store)
    for member in b2_path.iterdir():
        member.unlink()
    shutil.rmtree(store.project_dir(b2.project_key) / "latest")
    b3, _ = _build(store, "2026-09-08T12:00:00Z", _passing([1, 2, 3, 5]) + [_record("r", 4, [])])
    carried = _carried(b3)
    assert (carried["status"], carried["reason_code"]) == ("UNKNOWN", "HISTORY_GAP")
    assert carried["evidence_ref"] == {"previous_bundle_id": b2.bundle_id}
    integrity = _integrity(b3)
    assert integrity["derived"]["revision_history"]["source"]["status"] == "HISTORY_GAP"
    assert "REVISION_HISTORY_GAP:HISTORY_GAP" in integrity["diagnostics"]
    assert "r" not in _states(b3), "B1's PASS_ONLY for r is not reached for across the gap"
    assert b3.manifest["comparison_status"] == "HISTORY_GAP"


def test_the_durable_history_crosses_a_bundle_whose_verification_evidence_was_unusable(tmp_path):
    """B2 claims no Integrity band, and still hands B1's failure on to B3."""
    store = FilesystemHistoryStore(tmp_path)
    _build(store, "2026-09-06T12:00:00Z", _passing([1, 2, 3]) + [_record("r", 4, [_run(RUN_R, [(1, "VERIFY_FAIL")])])])
    b2, _ = _build(store, "2026-09-07T12:00:00Z", [], series_status="ERROR")
    assert _integrity(b2)["band"] is None and _states(b2)["r"] == "FAILURE_OBSERVED"
    b3, _ = _build(store, "2026-09-08T12:00:00Z", _passing([1, 2, 3, 5]) + [_record("r", 4, [])])
    assert _states(b3)["r"] == "FAILURE_OBSERVED" and _integrity(b3)["derived"]["failed_count_14d"] == 1


def test_hist_12_an_unrelated_vital_rule_change_keeps_the_durable_history(tmp_path):
    """A predecessor that compares INCOMPARABLE for another reason still hands its history on."""
    store = FilesystemHistoryStore(tmp_path)
    _build(store, "2026-09-06T12:00:00Z", _passing([1, 2, 3]) + [_record("r", 4, [_run(RUN_R, [(1, "VERIFY_FAIL")])])])
    project = single_project(LOCATOR, config_version="1", debt={"source": "labels", "labels": ["tech-debt"], "mapping_version": "2"})
    obs = _obs("2026-09-07T12:00:00Z", _passing([1, 2, 3, 5]) + [_record("r", 4, [])])
    bundle = build_from_observations(project, obs, store)
    assert bundle.manifest["comparison_status"] == "INCOMPARABLE"
    assert _states(bundle)["r"] == "FAILURE_OBSERVED"


def _older_bundle(project, obs):
    """A bundle as 0.1.x wrote it: observations without carried history, an Integrity result without revision_history."""
    from devostasis import activity as activity_mod
    from devostasis import delta as delta_mod
    from devostasis.bundle import build_bundle
    from devostasis.vitals import build_snapshot, evaluate_all

    snapshot = build_snapshot(obs, evaluate_all(obs))
    for vital in snapshot["vitals"]:
        if vital["vital_id"] == "integrity":
            vital["derived"].pop("revision_history", None)
    delta = delta_mod.compare(snapshot, None, delta_mod.BASELINE, None, [])
    activity = activity_mod.build_activity(obs, None, None, project.activity_list_cap) if project.activity_enabled else None
    return build_bundle(project, obs, snapshot, delta, activity, None, delta_mod.BASELINE, None)


def test_hist_13_the_first_bundle_after_an_older_version_replays_its_revision_records(tmp_path):
    """A 0.1.x predecessor has no carrier in its snapshot; its revision records are replayed, never copied."""
    store = FilesystemHistoryStore(tmp_path)
    project = single_project(LOCATOR, config_version="1")
    older = _older_bundle(project, _obs("2026-09-06T12:00:00Z", _passing([1, 2, 3]) + [_record("r", 4, [_run(RUN_R, [(1, "VERIFY_FAIL"), (2, "VERIFY_PASS")])])]))
    store.commit(older)
    b2, _ = _build(store, "2026-09-07T12:00:00Z", _passing([1, 2, 3, 5]) + [_record("r", 4, [])])
    carried = _carried(b2)
    assert carried["value"]["lineage"] == REPLAYABLE_LINEAGE and carried["value"]["source_bundle_id"] == older.bundle_id
    assert _integrity(b2)["derived"]["revision_history"]["source"]["basis"] == "REPLAYED_SERIES"
    assert _states(b2)["r"] == "FAILURE_OBSERVED"


def test_hist_17_different_durable_history_is_different_canonical_evidence(tmp_path):
    """The same current observation over two different histories never yields one bundle."""
    current = _passing([1, 2, 3, 5]) + [_record("r", 4, [])]
    ids, states = [], []
    for name, prior in (("failed", [(1, "VERIFY_FAIL")]), ("passed", [(1, "VERIFY_PASS")])):
        store = FilesystemHistoryStore(tmp_path / name)
        _build(store, "2026-09-06T12:00:00Z", _passing([1, 2, 3]) + [_record("r", 4, [_run(RUN_R, prior)])])
        bundle, _ = _build(store, "2026-09-07T12:00:00Z", current)
        ids.append(bundle.bundle_id)
        states.append(_states(bundle)["r"])
    assert states == ["FAILURE_OBSERVED", "PASS_ONLY_OBSERVED"]
    assert ids[0] != ids[1], "hidden store state never changes an evaluation without a canonical trace"


def test_hist_18_another_project_at_the_same_locator_is_never_carried(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    _build(store, "2026-09-06T12:00:00Z", _passing([1, 2, 3]) + [_record("r", 4, [_run(RUN_R, [(1, "VERIFY_FAIL")])])])
    project = single_project(LOCATOR, config_version="1")
    obs = _obs("2026-09-07T12:00:00Z", _passing([1, 2, 3, 5]) + [_record("r", 4, [])], project_id="7777")
    bundle = build_from_observations(project, obs, store)
    carried = next(o for o in __import__("json").loads(bundle.members["observations.json"])["observations"] if o["observation_id"] == CARRIED)
    assert carried["status"] != "AVAILABLE", "a foreign project's history is never merged"
    assert "r" not in _states(bundle)


def test_hist_19_complete_evidence_repairs_an_unknown_history(tmp_path):
    """The nearby valid repair: once every attempt is observed, the prior unknown history is proven pass-only."""
    store = FilesystemHistoryStore(tmp_path)
    b1, _ = _build(store, "2026-09-06T12:00:00Z", _passing([1, 2, 3]) + [_record("r", 4, [_run(RUN_R, [(3, "VERIFY_PASS")], latest=3)])])
    assert _states(b1)["r"] == "UNKNOWN_HISTORY" and _integrity(b1)["band"] is None
    b2, _ = _build(store, "2026-09-07T12:00:00Z", _passing([1, 2, 3]) + [_record("r", 4, [_run(RUN_R, [(1, "VERIFY_PASS"), (2, "VERIFY_PASS"), (3, "VERIFY_PASS")])])])
    assert _states(b2)["r"] == "PASS_ONLY_OBSERVED" and _integrity(b2)["band"] == "CLEAN"


def test_a_build_refuses_observations_that_carry_history_from_another_predecessor(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    b1, _ = _build(store, "2026-09-06T12:00:00Z", _passing([1, 2, 3]))
    import json

    replayed = ObservationSet.from_dict(json.loads(b1.members["observations.json"]))
    assert replayed.get(CARRIED).reason_code == "NO_PREVIOUS_BUNDLE"
    replayed.observed_at = "2026-09-07T12:00:00Z"
    with pytest.raises(BundleError, match="HISTORY_SOURCE_NOT_PREDECESSOR"):
        build_from_observations(single_project(LOCATOR, config_version="1"), replayed, store)


@pytest.mark.parametrize("changed", ["records", "attempts", "lineage", "source_observed_at", "basis", "freshness", "source_ref"])
def test_a_build_refuses_changed_history_even_when_it_names_the_right_predecessor(tmp_path, changed):
    """Naming the verified predecessor is not proof of the history it actually contains."""
    from devostasis.runner import attach_revision_history, find_predecessor

    store = FilesystemHistoryStore(tmp_path)
    _, previous, _ = _chain(store)
    project = single_project(LOCATOR, config_version="1")
    obs = _obs("2026-09-08T12:00:00Z", _passing([1, 2, 3, 5]) + [_record("r", 4, [_run(RUN_R, [(1, "VERIFY_PASS")])])])
    predecessor = find_predecessor(store, project, PROJECT_ID, obs.observed_at)
    obs = attach_revision_history(obs, predecessor)
    stated = copy.deepcopy(obs.get(CARRIED).to_dict())
    assert stated["value"]["source_bundle_id"] == previous.bundle_id
    if changed == "records":
        stated["value"]["records"] = []
    elif changed == "attempts":
        failed = next(r for r in stated["value"]["records"] if r["revision"] == "r")
        failed["parent_groups"][0]["attempts"] = [{"attempt": 1, "state": "VERIFY_PASS"}]
    elif changed in ("lineage", "source_observed_at", "basis"):
        stated["value"][changed] = "forged"
    else:
        stated[changed] = "STALE" if changed == "freshness" else "bundle:forged"
    obs.replace(Observation.from_dict(stated))
    with pytest.raises(BundleError, match="HISTORY_CONTENT_MISMATCH"):
        build_from_observations(project, obs, store)


def test_a_build_accepts_an_unchanged_carrier_and_reproduces_the_same_bundle(tmp_path):
    import json

    store = FilesystemHistoryStore(tmp_path)
    _chain(store)
    project = single_project(LOCATOR, config_version="1")
    obs = _obs("2026-09-08T12:00:00Z", _passing([1, 2, 3, 5]) + [_record("r", 4, [_run(RUN_R, [(1, "VERIFY_PASS")])])])
    built = build_from_observations(project, obs, store)
    replayed = ObservationSet.from_dict(json.loads(built.members["observations.json"]))
    rebuilt = build_from_observations(project, replayed, store)
    assert rebuilt.bundle_id == built.bundle_id
    assert rebuilt.members == built.members
    assert _states(rebuilt)["r"] == "FAILURE_OBSERVED"


@pytest.mark.parametrize("lineage", [LINEAGE, REPLAYABLE_LINEAGE])
def test_duplicate_carried_revisions_cannot_overwrite_a_recorded_failure(lineage):
    from devostasis.revision_history import encode, parent_from_current, union_record
    from devostasis.vitals import integrity

    obs = _obs("2026-09-08T12:00:00Z", _passing([1, 2, 3, 5]) + [_record("r", 4, [_run(RUN_R, [(1, "VERIFY_PASS")])])])
    failed = _record("r", 4, [_run(RUN_R, [(1, "VERIFY_FAIL")])])
    passed = _record("r", 4, [_run(RUN_R, [(1, "VERIFY_PASS")])])
    records = [failed, passed]
    if lineage == LINEAGE:
        records = [encode(union_record(r["revision"], r["committed_at"], [parent_from_current(p, "test") for p in r["parents"]], [])) for r in records]
    add(obs, CARRIED, {"lineage": lineage, "records": records}, "record")
    result = integrity.evaluate(obs)
    assert (result.band, result.evaluation_status) == (None, "UNKNOWN")
    assert any(code.startswith("REVISION_HISTORY_CARRY_MALFORMED") for code in result.diagnostics)


def test_a_build_leaves_the_callers_observation_set_as_it_was(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    obs = _obs("2026-09-06T12:00:00Z", _passing([1, 2, 3]))
    bundle = build_from_observations(single_project(LOCATOR, config_version="1"), obs, store)
    assert CARRIED not in obs
    assert _carried(bundle)["reason_code"] == "NO_PREVIOUS_BUNDLE"


def test_carried_history_that_is_not_its_lineages_shape_fails_closed():
    obs = finalize(obs_set("2026-09-10T12:00:00Z"))
    add(obs, "ci.configured", True, "boolean")
    add(obs, "ci.revision_verdicts_14d", _passing([1, 2, 3, 4]), "series")
    add(obs, CARRIED, {"lineage": LINEAGE, "records": [{"revision": "r", "committed_at": "not a time", "parents": []}]}, "record")
    from devostasis.vitals import integrity

    result = integrity.evaluate(obs)
    assert (result.band, result.evaluation_status) == (None, "UNKNOWN")
    assert any(code.startswith("REVISION_HISTORY_CARRY_MALFORMED") for code in result.diagnostics)


def test_every_stored_bundle_verifies_with_its_carried_history(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    b1, b2, b2_path = _chain(store)
    assert verify_dir(b2_path) == []


def test_verify_names_carried_history_that_is_not_from_the_previous_bundle(tmp_path):
    """Section C: the selection of the source is auditable, so a bundle that names another source does not verify."""
    import json

    from devostasis.bundle import _check_history_source

    store = FilesystemHistoryStore(tmp_path)
    _, b2, _ = _chain(store)
    observations = json.loads(b2.members["observations.json"])
    assert _check_history_source(b2.members, b2.manifest, observations) == []
    problems = _check_history_source(b2.members, dict(b2.manifest, previous_bundle_id="c" * 64), observations)
    assert len(problems) == 2 and all(problem.startswith("HISTORY_SOURCE_MISMATCH") for problem in problems)


def test_the_carrier_holds_only_what_the_build_can_consume(tmp_path):
    """Records that have aged out of the window are not carried, and replayed 0.1.x records keep only what replay reads."""
    store = FilesystemHistoryStore(tmp_path)
    project = single_project(LOCATOR, config_version="1")
    older = _older_bundle(project, _obs("2026-09-06T12:00:00Z", _passing([1, 2, 3]) + [_record("r", 4, [_run(RUN_R, [(1, "VERIFY_FAIL")])]), _record("s", 5, [_run(RUN_R + 1, [(1, "VERIFY_PASS")])])]))
    store.commit(older)
    # Observed on 2026-09-19 the window starts at 09-05T12:00: r (09-04) has aged out, s (09-05T10:00) too, nothing else is carried.
    b2, _ = _build(store, "2026-09-19T12:00:00Z", _passing([6, 7]))
    assert _carried(b2)["value"]["records"] == []
    # On 2026-09-20 the window starts at 09-06T12:00, so p6 (09-06T10:00) is no longer carried either.
    b3, _ = _build(store, "2026-09-20T12:00:00Z", _passing([6, 7, 8]))
    assert [r["revision"] for r in _carried(b3)["value"]["records"]] == ["p7"]
    b4_store = FilesystemHistoryStore(tmp_path / "replay")
    b4_store.commit(older)
    b4, _ = _build(b4_store, "2026-09-10T12:00:00Z", _passing([6]))
    replayed = _carried(b4)["value"]["records"]
    assert {r["revision"] for r in replayed} == {"p1", "p2", "p3", "r", "s"}
    assert all(set(r) == {"revision", "committed_at", "parents"} for r in replayed)
    assert all(set(p) == {"parent_id", "kind", "current_attempt", "attempts_observed"} for r in replayed for p in r["parents"])


def test_the_carrier_groups_parents_by_shape_without_losing_one():
    """Hundreds of single-attempt runs on one revision are stored once per shape, and every parent comes back."""
    from devostasis.revision_history import HistoryShapeError, parent_groups, parents_from_groups

    parents = [
        {"parent_id": f"github_actions:workflow_run:{n}", "kind": "github_actions_workflow_run", "latest_attempt": 1, "attempts": [{"attempt": 1, "state": "VERIFY_PASS"}]}
        for n in range(300)
    ] + [
        {"parent_id": "github_actions:workflow_run:900", "kind": "github_actions_workflow_run", "latest_attempt": 2, "attempts": [{"attempt": 1, "state": "VERIFY_FAIL"}, {"attempt": 2, "state": "VERIFY_PASS"}]},
        {"parent_id": "github_checks:check_suite:7", "kind": "github_check_suite", "latest_attempt": None, "attempts": [{"attempt": None, "state": "VERIFY_PASS"}]},
    ]
    groups = parent_groups(parents)
    assert len(groups) == 3 and sum(len(group["parent_ids"]) for group in groups) == 302
    restored = parents_from_groups(groups, "test")
    assert sorted(restored, key=lambda p: p["parent_id"]) == sorted(parents, key=lambda p: p["parent_id"])
    with pytest.raises(HistoryShapeError):
        parents_from_groups([groups[0], {**groups[0]}], "test")
