"""Accepted RECEIPT-ID-01..15,17..21; 16 remains rejected and unassigned."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from devostasis import canonical
from devostasis.bundle import verify_members, load_bundle_dir
from devostasis.config import single_project
from devostasis.history import FilesystemHistoryStore, ImmutabilityError
from devostasis.observations import Observation, Receipt
from devostasis.runner import build_from_observations
from helpers import full_inputs, obs_set


def build(tmp_path, obs=None, project=None, run_meta=None):
    return build_from_observations(project or single_project("acme/widget", config_version="1"),
        obs or full_inputs(obs_set()), FilesystemHistoryStore(tmp_path), run_meta)


@pytest.mark.parametrize("field,value", [("run_id", "another invocation"), ("started_at", "2026-10-06T10:00:00Z"),
                                        ("ended_at", "2026-10-06T10:10:00Z")], ids=["RECEIPT-ID-01", "RECEIPT-ID-02", "RECEIPT-ID-03"])
def test_execution_fields_have_no_canonical_path(tmp_path, field, value):
    obs = full_inputs(obs_set()); first = build(tmp_path, obs)
    setattr(obs.receipt, field, value); second = build(tmp_path, obs)
    assert first.bundle_id == second.bundle_id and first.members == second.members
    assert first.execution_receipt != second.execution_receipt


def test_receipt_id_04_14_17_19_run_mechanics_are_external(tmp_path):
    obs = full_inputs(obs_set()); first = build(tmp_path, obs)
    obs.receipt.run_id = "run2"; obs.receipt.started_at = "later"; obs.receipt.ended_at = "slower"
    obs.receipt.diagnostics = ["cache hit, retry, host narration"]
    second = build(tmp_path, obs, run_meta={"requests": 77, "retries": 2, "host": "another host"})
    assert first.bundle_id == second.bundle_id and first.members == second.members
    assert second.execution_receipt["result_bundle_id"] == second.bundle_id
    assert second.execution_receipt["run_meta"]["requests"] == 77
    assert "run_meta" not in second.manifest and "receipt" not in second.manifest
    assert not any(b"run2" in content or b"slower" in content for content in second.members.values())
    assert verify_members(second.members) == []


def test_request_budget_count_cannot_leak_through_material_capability_notes(tmp_path):
    obs = full_inputs(obs_set()); obs.receipt.capability_notes = ["REQUEST_BUDGET_EXHAUSTED:3"]
    first = build(tmp_path, obs)
    obs.receipt.capability_notes = ["REQUEST_BUDGET_EXHAUSTED:30"]
    second = build(tmp_path, obs)
    assert first.members == second.members and first.bundle_id == second.bundle_id
    assert first.execution_receipt != second.execution_receipt
    assert second.manifest["receipt_identity"]["capability_notes"] == ["REQUEST_BUDGET_EXHAUSTED"]


def test_receipt_id_05_observation_time_stays_material(tmp_path):
    a = full_inputs(obs_set()); b = deepcopy(a); b.observed_at = "2026-10-06T12:00:00Z"
    assert build(tmp_path, a).bundle_id != build(tmp_path, b).bundle_id


@pytest.mark.parametrize("change", ["available", "unknown", "partial", "zero", "freshness", "capability", "version", "scope"],
                         ids=["RECEIPT-ID-06", "RECEIPT-ID-07", "RECEIPT-ID-08", "RECEIPT-ID-09", "RECEIPT-ID-10",
                              "RECEIPT-ID-11", "RECEIPT-ID-12", "RECEIPT-ID-13"])
def test_material_acquisition_distinctions_change_identity(tmp_path, change):
    obs = full_inputs(obs_set())
    # Compare partial/full, zero/unknown and stale/fresh at the same key;
    # adding a previously absent key would prove only absence/presence.
    if change in ("partial", "zero", "freshness"):
        baseline = "UNKNOWN" if change == "zero" else "AVAILABLE"
        obs.add(Observation("extra", baseline, "count", None if baseline == "UNKNOWN" else 0))
        obs.finalize_receipt(obs.receipt)
    first = build(tmp_path, obs)
    if change in ("available", "unknown", "partial", "zero", "freshness"):
        status = {"unknown": "UNKNOWN", "partial": "PARTIAL"}.get(change, "AVAILABLE")
        obs.replace(Observation("extra", status, "count", None if status == "UNKNOWN" else 0,
                            freshness="STALE" if change == "freshness" else "FRESH"))
        obs.finalize_receipt(obs.receipt)
    elif change == "capability":
        obs.receipt.capability_notes = ["MATERIAL_CAPABILITY_UNAVAILABLE"]
    elif change == "version":
        obs.receipt.collector_version = "normalization.v2"
    else:
        obs.receipt.target["immutable_project_id"] = "different-project"
    second = build(tmp_path, obs)
    assert second.bundle_id != first.bundle_id
    assert second.manifest["identity_preimage"]["source_receipts_digest"] != first.manifest["identity_preimage"]["source_receipts_digest"]


def test_receipt_id_15_18_historical_version_is_not_projected(tmp_path):
    legacy = load_bundle_dir(Path(__file__).parents[1] / "examples/legacy/bundle-v2")
    before = dict(legacy)
    assert verify_members(legacy) == [] and before == legacy
    successor = build(tmp_path)
    assert verify_members(successor.members) == []
    for value in ("devostasis.manifest.v1", "devostasis.manifest.v999"):
        broken = dict(successor.members); m = deepcopy(successor.manifest); m["schema"] = value
        broken["manifest.json"] = canonical.pretty_json(m).encode()
        assert any("LINEAGE_MISMATCH" in p for p in verify_members(broken))


def test_receipt_id_20_exact_duplicate_put_preserves_collision_rule(tmp_path):
    store = FilesystemHistoryStore(tmp_path); obs = full_inputs(obs_set())
    first = build(tmp_path, obs)
    obs.receipt.run_id = "other"; second = build(tmp_path, obs)
    dest = store.commit(first)
    assert store.commit(second) == dest
    assert load_bundle_dir(dest) == first.members
    second.members["report.md"] += b"forged\n"
    with pytest.raises(ImmutabilityError):
        store.commit(second)


def test_receipt_id_21_receipt_is_durable_when_observations_disabled(tmp_path):
    b = build(tmp_path, project=single_project("acme/widget", config_version="1", observations_member=False))
    assert "observations.json" not in b.members and b.manifest["receipt_identity"]
    assert canonical.digest(b.manifest["receipt_identity"]) == b.manifest["identity_preimage"]["source_receipts_digest"]
    assert verify_members(b.members) == []
    for mutate in (lambda m: m.pop("receipt_identity"), lambda m: m["receipt_identity"].update(schema="devostasis.receipt.v2"),
                   lambda m: m["receipt_identity"].update(run_id="leaked"), lambda m: m["receipt_identity"].update(coverage={"unknown": {}})):
        m = deepcopy(b.manifest); mutate(m); content = dict(b.members); content["manifest.json"] = canonical.pretty_json(m).encode()
        assert verify_members(content)


def test_successor_verification_rejects_same_id_noncanonical_manifest_variants(tmp_path):
    b = build(tmp_path)
    for key, value in (("invocation", "execution leak"), ("supersedes_bundle_id", "another id"),
                       ("project_key", "github.com/acme/alias")):
        m = deepcopy(b.manifest); m[key] = value; content = dict(b.members)
        content["manifest.json"] = canonical.pretty_json(m).encode()
        assert any("MANIFEST_SCHEMA_INVALID" in p for p in verify_members(content))
    content = dict(b.members); content["snapshot.json"] += b"\n"
    assert any("CANONICAL_BYTES_MISMATCH" in p for p in verify_members(content))


def test_alias_input_cannot_change_unhashed_canonical_project_key(tmp_path):
    first = build(tmp_path)
    second = build(tmp_path, project=single_project("acme/alias", config_version="1"))
    assert first.bundle_id == second.bundle_id and first.members == second.members
