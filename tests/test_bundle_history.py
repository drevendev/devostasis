"""Bundle identity, verification, immutability, comparison states and activity (ART-*, RPT-*)."""

import json

import pytest

from devostasis import canonical
from devostasis.bundle import DUPLICATED_IDENTITY_FIELDS, LINEAGES, BundleError, verify_dir, verify_members
from devostasis.contracts import ARTIFACT_CONTRACT_VERSION, RENDERER_VERSION
from devostasis.config import single_project
from devostasis.history import FilesystemHistoryStore, ImmutabilityError
from devostasis.observations import Observation
from devostasis.runner import build_from_observations
from helpers import OBSERVED_AT, add, finalize, full_inputs, obs_set


def _project(**overrides):
    return single_project("acme/widget", config_version="1", **overrides)


def _obs(observed_at=OBSERVED_AT):
    return full_inputs(obs_set(observed_at))


def test_art_01_first_bundle_is_baseline_without_fabricated_delta(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    bundle = build_from_observations(_project(), _obs(), store)
    assert bundle.manifest["comparison_status"] == "BASELINE" and bundle.manifest["previous_bundle_id"] is None
    delta = json.loads(bundle.members["delta.json"])
    assert {row["transition_class"] for row in delta["vitals"]} == {"BASELINE"}
    assert all(row["metric_deltas"] == {} for row in delta["vitals"])


def test_art_02_and_art_14_identity_is_reproducible_across_builds(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    first = build_from_observations(_project(), _obs(), store)
    second = build_from_observations(_project(), _obs(), store)
    assert first.bundle_id == second.bundle_id
    assert first.members == second.members
    preimage = first.manifest["identity_preimage"]
    assert canonical.sha256_hex(canonical.canonical_bytes(preimage)) == first.bundle_id


def test_art_13_and_art_22_preimage_excludes_post_identity_members(tmp_path):
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    preimage = bundle.manifest["identity_preimage"]
    assert "members" not in preimage and "bundle_id" not in preimage and "run_meta" not in preimage
    assert preimage["effective_config_digest"] == bundle.manifest["effective_config_digest"]
    assert set(preimage) >= {"snapshot_digest", "delta_digest", "activity_digest", "source_receipts_digest", "observed_at"}


def test_art_16_observed_at_is_identity_bearing(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    a = build_from_observations(_project(), _obs("2026-09-05T12:00:00Z"), store)
    b = build_from_observations(_project(), _obs("2026-09-05T12:00:01Z"), store)
    assert a.bundle_id != b.bundle_id


def test_art_17_config_change_changes_bundle_id(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    a = build_from_observations(_project(activity={"list_cap": 50}), _obs(), store)
    b = build_from_observations(_project(activity={"list_cap": 5}), _obs(), store)
    assert a.bundle_id != b.bundle_id and a.manifest["config_version"] == b.manifest["config_version"]


def test_art_18_enabled_html_without_renderer_fails_closed(tmp_path):
    with pytest.raises(BundleError):
        build_from_observations(_project(report_html=True), _obs(), FilesystemHistoryStore(tmp_path))


def test_art_20_21_12_persisted_bundle_verifies_from_its_own_contents(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    bundle = build_from_observations(_project(), _obs(), store)
    path = store.commit(bundle, bundle.bands())
    assert verify_dir(path) == []
    stored = (path / "effective-config.json").read_bytes()
    assert canonical.digest_bytes(stored) == bundle.manifest["effective_config_digest"]
    assert canonical.canonical_bytes(json.loads(stored)) == stored


def test_tampering_is_detected(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    bundle = build_from_observations(_project(), _obs(), store)
    path = store.commit(bundle, bundle.bands())
    report = path / "report.md"
    report.write_bytes(report.read_bytes() + b"\nedited\n")
    problems = verify_dir(path)
    assert any("report.md" in p for p in problems)
    snapshot = json.loads((path / "snapshot.json").read_text("utf-8"))
    snapshot["vitals"][0]["band"] = "DECLARED"
    (path / "snapshot.json").write_text(json.dumps(snapshot), "utf-8")
    assert any("snapshot.json digest mismatch" in p for p in verify_dir(path))


def test_art_07_immutability(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    bundle = build_from_observations(_project(), _obs(), store)
    store.commit(bundle, bundle.bands())
    store.put_immutable(bundle)
    bundle.members["report.md"] = b"different"
    with pytest.raises(ImmutabilityError):
        store.put_immutable(bundle)


def test_second_run_is_comparable_with_unchanged_and_ordered_transitions(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    first = build_from_observations(_project(), _obs("2026-09-05T12:00:00Z"), store)
    store.commit(first, first.bands())
    later = obs_set("2026-09-06T12:00:00Z")
    full_inputs(later)
    later.replace(type(later.get("forge.change_requests.open_count"))(**dict(later.get("forge.change_requests.open_count").to_dict(), value=12)))
    second = build_from_observations(_project(), later, store)
    assert second.manifest["comparison_status"] == "COMPARABLE" and second.manifest["previous_bundle_id"] == first.bundle_id
    delta = json.loads(second.members["delta.json"])
    rows = {row["vital_id"]: row for row in delta["vitals"]}
    assert rows["flow"]["transition_class"] == "WORSENED" and rows["flow"]["previous_band"] == "MOVING" and rows["flow"]["current_band"] == "CONGESTED"
    assert "BAND_ORDER_APPLIED:MOVING>CONGESTED>GRIDLOCKED" in rows["flow"]["reason_codes"]
    assert rows["flow"]["metric_deltas"]["open_count"] == {"previous": 2, "current": 12, "change": 10}
    assert rows["pulse"]["transition_class"] == "UNCHANGED"
    activity = json.loads(second.members["activity.json"])
    assert activity["interval"] == {"start": "2026-09-05T12:00:00Z", "end": "2026-09-06T12:00:00Z", "basis": "PREVIOUS_BUNDLE", "exclusive_start": True}


def test_observability_transitions(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    first_obs = _obs("2026-09-05T12:00:00Z")
    first_obs.replace(type(first_obs.get("ci.revision_verdicts_14d"))(**dict(first_obs.get("ci.revision_verdicts_14d").to_dict(), status="ERROR", value=None, reason_code="PROVIDER_ERROR")))
    finalize(first_obs)
    first = build_from_observations(_project(), first_obs, store)
    store.commit(first, first.bands())
    second = build_from_observations(_project(), _obs("2026-09-06T12:00:00Z"), store)
    rows = {row["vital_id"]: row for row in json.loads(second.members["delta.json"])["vitals"]}
    assert rows["integrity"]["transition_class"] == "OBSERVABILITY_GAINED"
    activity = json.loads(second.members["activity.json"])
    assert activity["classes"]["CAPABILITY_CHANGE"]["count"] == 1


def test_rpt_3_history_gap_keeps_current_snapshot_and_infers_no_change(tmp_path):
    """The previous *immutable* bundle cannot be loaded: that is what HISTORY_GAP means (#28)."""
    store = FilesystemHistoryStore(tmp_path)
    first = build_from_observations(_project(), _obs("2026-09-05T12:00:00Z"), store)
    path = store.commit(first, first.bands())
    (path / "snapshot.json").unlink()
    second = build_from_observations(_project(), _obs("2026-09-06T12:00:00Z"), store)
    assert second.manifest["comparison_status"] == "HISTORY_GAP"
    assert second.manifest["previous_bundle_id"] == first.bundle_id
    delta = json.loads(second.members["delta.json"])
    assert {row["transition_class"] for row in delta["vitals"]} == {"INCOMPARABLE"}
    assert json.loads(second.members["snapshot.json"])["vitals"][0]["band"] == "EXTENDED"
    assert path.exists()
    assert any("snapshot.json" in problem for problem in store.latest(first.project_key, "123456").problems)


def test_art_04_rpt_10_semantic_config_change_is_incomparable(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    first = build_from_observations(_project(), _obs("2026-09-05T12:00:00Z"), store)
    store.commit(first, first.bands())
    second = build_from_observations(_project(debt={"labels": ["debt"], "mapping_version": "1"}), _obs("2026-09-06T12:00:00Z"), store)
    assert second.manifest["comparison_status"] == "INCOMPARABLE"
    delta = json.loads(second.members["delta.json"])
    assert "SEMANTIC_CONFIG_CHANGED" in delta["incomparable_reasons"]
    assert {row["transition_class"] for row in delta["vitals"]} == {"INCOMPARABLE"}
    store.commit(second, second.bands())
    index = store.read_index(second.project_key)
    assert [entry["bundle_id"] for entry in index["bundles"]] == [first.bundle_id, second.bundle_id]


def test_rule_version_boundary_makes_one_vital_incomparable_inside_a_comparable_bundle():
    from devostasis.delta import compare
    from devostasis.vitals import build_snapshot

    previous = build_snapshot(full_inputs(obs_set("2026-09-05T12:00:00Z")))
    current = build_snapshot(full_inputs(obs_set("2026-09-06T12:00:00Z")))
    for vital in previous["vitals"]:
        if vital["vital_id"] == "flow":
            vital["rule_id"] = "flow.bands.v0"
    delta = compare(current, previous, "COMPARABLE", "previous-id")
    rows = {row["vital_id"]: row for row in delta["vitals"]}
    assert rows["flow"]["transition_class"] == "INCOMPARABLE"
    assert rows["flow"]["reason_codes"] == ["RULE_VERSION_BOUNDARY:flow.bands.v0->flow.bands.v1"]
    assert rows["flow"]["metric_deltas"] == {}
    assert rows["pulse"]["transition_class"] == "UNCHANGED" and delta["comparison_status"] == "COMPARABLE"


def test_art_06_neutral_rendering_of_fully_linked_and_present(tmp_path):
    obs = obs_set()
    full_inputs(obs)
    for key, value in (("linked", 10), ("unlinked", 0)):
        observation_id = f"planning.linkage.active_change_requests_{key}_count_28d"
        obs.replace(Observation.from_dict(dict(obs.get(observation_id).to_dict(), value=value)))
    bundle = build_from_observations(_project(), obs, FilesystemHistoryStore(tmp_path))
    report = bundle.members["report.md"].decode("utf-8")
    assert "FULLY_LINKED" in report and "PRESENT" in report
    for banned in ("ALIGNED", "ON_TRACK", "HEALTHY", "UNHEALTHY", "score"):
        assert banned not in report


def test_verify_members_reports_missing_manifest():
    assert verify_members({}) == ["manifest.json missing"]


def test_legacy_semantic_config_shape_stays_comparable():
    from devostasis.delta import compatibility_reasons

    current = {"vitals_contract_version": "PV-VITALS-V1-002", "observation_contract_version": "RAW-OBS-V0", "policy_version": "devostasis.policy.v1", "semantic_config": _project().semantic_config()}
    legacy = dict(current, semantic_config={"planning_source": "milestones", "debt_mapping": None})
    assert compatibility_reasons(current, legacy) == []
    legacy_debt = dict(current, semantic_config={"planning_source": "milestones", "debt_mapping": {"labels": ["debt"], "mapping_version": "1"}})
    current_debt = dict(current, semantic_config=_project(debt={"labels": ["debt"], "mapping_version": "1"}).semantic_config())
    assert compatibility_reasons(current_debt, legacy_debt) == []
    assert compatibility_reasons(current, legacy_debt) == ["SEMANTIC_CONFIG_CHANGED"]


def test_activity_disabled_marker_enters_identity(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    enabled = build_from_observations(_project(), _obs(), store)
    disabled = build_from_observations(_project(activity={"enabled": False}), _obs(), store)
    assert "activity.json" not in disabled.members
    assert disabled.manifest["identity_preimage"]["activity_digest"] == "ACTIVITY_DISABLED"
    assert disabled.manifest["canonical_member_profile"]["activity_json"] == "DISABLED"
    assert enabled.bundle_id != disabled.bundle_id
    assert verify_members(disabled.members) == []


def _rehash(members):
    """Recompute every digest and the bundle id after a mutation, the way a consistent forgery would."""
    members = dict(members)
    manifest = json.loads(members["manifest.json"])
    preimage = manifest["identity_preimage"]
    for name, key in (("snapshot.json", "snapshot_digest"), ("delta.json", "delta_digest"), ("activity.json", "activity_digest"), ("observations.json", "observations_digest"), ("gauges.json", "gauges_digest"), ("demand.json", "demand_digest")):
        if name in members:
            preimage[key] = canonical.digest(json.loads(members[name]))
    preimage["effective_config_digest"] = canonical.digest_bytes(members["effective-config.json"])
    manifest["effective_config_digest"] = preimage["effective_config_digest"]
    manifest["bundle_id"] = canonical.sha256_hex(canonical.canonical_bytes(preimage))
    manifest["members"] = {
        name: (canonical.digest_bytes(members[name]) if name in ("report.md", "effective-config.json") else canonical.digest(json.loads(members[name])))
        for name in members
        if name != "manifest.json"
    }
    members["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
    return members


def _stored_config(members):
    return json.loads(members["effective-config.json"])


def test_rehash_helper_keeps_a_valid_bundle_valid(tmp_path):
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    assert verify_members(_rehash(bundle.members)) == []


def test_art_23_member_profile_derives_from_the_stored_config(tmp_path):
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    config = _stored_config(bundle.members)
    config["activity"] = "DISABLED"
    forged = dict(bundle.members)
    forged["effective-config.json"] = canonical.canonical_bytes(config)
    problems = verify_members(_rehash(forged))
    assert any(p.startswith("CANONICAL_MEMBER_PROFILE_MISMATCH") and "manifest profile" in p for p in problems)
    assert any("ART-24" in p for p in problems)
    manifest = json.loads(forged["manifest.json"])
    manifest["canonical_member_profile"]["activity_json"] = "DISABLED"
    forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
    problems = verify_members(_rehash(forged))
    assert any("activity.json is DISABLED by the stored effective config but present" in p for p in problems)
    assert any("activity marker disagrees" in p for p in problems)


def test_art_25_stored_config_is_schema_validated_before_any_semantic_use(tmp_path):
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    forged = dict(bundle.members)
    config = _stored_config(bundle.members)
    config["schema"] = "devostasis.effective-config.v9"
    forged["effective-config.json"] = canonical.canonical_bytes(config)
    problems = verify_members(_rehash(forged))
    assert any(p.startswith("EFFECTIVE_CONFIG_SCHEMA_INVALID_OR_UNSUPPORTED") and "v9" in p for p in problems)
    config = _stored_config(bundle.members)
    config["surprise"] = True
    forged["effective-config.json"] = canonical.canonical_bytes(config)
    problems = verify_members(_rehash(forged))
    assert any(p.startswith("EFFECTIVE_CONFIG_SCHEMA_INVALID_OR_UNSUPPORTED") and "surprise" in p for p in problems)
    config = _stored_config(bundle.members)
    config["display"]["vitals"] = ["pulse", "health"]
    forged["effective-config.json"] = canonical.canonical_bytes(config)
    assert any(p.startswith("EFFECTIVE_CONFIG_SCHEMA_INVALID_OR_UNSUPPORTED") for p in verify_members(_rehash(forged)))
    config = _stored_config(bundle.members)
    config["demand"]["levels"]["flow"] = {"GRIDLOCKED": "URGENT"}
    forged["effective-config.json"] = canonical.canonical_bytes(config)
    assert any("URGENT" in p for p in verify_members(_rehash(forged)))


def test_art_24_replay_happens_only_from_a_validated_stored_config(tmp_path):
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    forged = dict(bundle.members)
    config = _stored_config(bundle.members)
    config["schema"] = "devostasis.effective-config.v9"
    forged["effective-config.json"] = canonical.canonical_bytes(config)
    forged["report.md"] = forged["report.md"] + b"\nedited\n"
    problems = verify_members(_rehash(forged))
    assert any("replay skipped" in p and "ART-24" in p for p in problems)
    assert not any("ART-12" in p for p in problems)

    honest = build_from_observations(_project(display={"vitals": ["pulse", "flow"], "gauge": ["band"], "sections": ["details"]}), _obs(), FilesystemHistoryStore(tmp_path))
    assert verify_members(honest.members) == []
    tampered = dict(honest.members)
    tampered["report.md"] = bundle.members["report.md"]
    problems = verify_members(_rehash(tampered))
    assert any("ART-12/ART-24" in p for p in problems)


def test_legacy_effective_config_v1_is_still_verifiable(tmp_path):
    from devostasis.config import member_profile_from_config, validate_effective_config

    legacy = {"activity": "ENABLED", "activity_list_cap": 50, "debt_mapping": None, "locale": "en", "observations_member": "ENABLED", "planning_source": "milestones", "report_html": "DISABLED", "schema": "devostasis.effective-config.v1"}
    assert validate_effective_config(legacy) == []
    assert member_profile_from_config(legacy) == {"report_md": "REQUIRED", "report_html": "DISABLED", "activity_json": "ENABLED", "observations_json": "ENABLED", "effective_config_json": "REQUIRED"}
    legacy_debt = dict(legacy, debt_mapping={"labels": ["type:refactor"], "mapping_version": "1"})
    assert validate_effective_config(legacy_debt) == []
    assert validate_effective_config(dict(legacy, planning_source="wiki"))
    assert validate_effective_config(dict(legacy, schema="devostasis.effective-config.v0"))


# --------------------------------------------------------------------------- #17: an observation is comparable only when it is later than the previous one


def test_an_older_observation_is_incomparable_and_claims_no_direction(tmp_path):
    """#17: written after a newer bundle, an older observation is not a comparable pair.

    Before the repair it was COMPARABLE, its delta reported IMPROVED and
    WORSENED with the direction inverted, and activity.json carried an
    interval that ended before it started.
    """
    store = FilesystemHistoryStore(tmp_path)
    newer = build_from_observations(_project(), _obs("2026-09-05T12:00:00Z"), store)
    store.commit(newer)
    older_obs = obs_set("2026-09-01T12:00:00Z")
    full_inputs(older_obs)
    older_obs.replace(type(older_obs.get("forge.issues.stale_open_count_30d"))(**dict(older_obs.get("forge.issues.stale_open_count_30d").to_dict(), value=9)))
    older = build_from_observations(_project(), older_obs, store)
    assert older.manifest["comparison_status"] == "INCOMPARABLE"
    delta = json.loads(older.members["delta.json"])
    assert any(reason.startswith("NON_MONOTONIC_OBSERVATION:2026-09-05T12:00:00Z->2026-09-01T12:00:00Z") for reason in delta["incomparable_reasons"])
    assert {row["transition_class"] for row in delta["vitals"]} == {"INCOMPARABLE"}
    assert delta["previous_observed_at"] is None
    activity = json.loads(older.members["activity.json"])
    assert activity["interval"]["basis"] == "OBSERVATION_WINDOW_28D"
    assert activity["interval"]["start"] < activity["interval"]["end"]


def test_an_observation_at_the_same_instant_is_on_the_same_side_of_the_boundary(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    first = build_from_observations(_project(), _obs("2026-09-05T12:00:00Z"), store)
    store.commit(first)
    same = build_from_observations(_project(), _obs("2026-09-05T12:00:00Z"), store)
    assert same.manifest["comparison_status"] == "INCOMPARABLE"
    assert any("NON_MONOTONIC_OBSERVATION" in reason for reason in json.loads(same.members["delta.json"])["incomparable_reasons"])
    later = build_from_observations(_project(), _obs("2026-09-05T12:00:01Z"), store)
    assert later.manifest["comparison_status"] == "COMPARABLE", "one second later is the normal case, untouched"


def test_activity_refuses_an_interval_that_ends_before_it_starts():
    from devostasis.activity import build_activity

    obs = full_inputs(obs_set("2026-09-01T12:00:00Z"))
    with pytest.raises(ValueError, match="must start before it ends"):
        build_activity(obs, {"observed_at": "2026-09-05T12:00:00Z"}, "2026-09-05T12:00:00Z", 50)
    with pytest.raises(ValueError):
        build_activity(obs, {"observed_at": "2026-09-01T12:00:00Z"}, "2026-09-01T12:00:00Z", 50)


# --------------------------------------------------------------------------- #28: the previous bundle is the immutable one the index names


def test_the_comparison_reads_the_immutable_bundle_and_survives_a_compacted_latest_copy(tmp_path):
    """#28: latest/ is a convenience copy the contract lets a store compact; comparability never depended on it."""
    import shutil

    store = FilesystemHistoryStore(tmp_path)
    first = build_from_observations(_project(), _obs("2026-09-05T12:00:00Z"), store)
    store.commit(first)
    latest_dir = store.project_dir(first.project_key) / "latest"
    shutil.rmtree(latest_dir)
    second = build_from_observations(_project(), _obs("2026-09-06T12:00:00Z"), store)
    assert second.manifest["comparison_status"] == "COMPARABLE"
    assert second.manifest["previous_bundle_id"] == first.bundle_id
    store.commit(second)
    assert (latest_dir / "manifest.json").exists(), "the copy is republished on the next commit"
    assert json.loads((latest_dir / "manifest.json").read_text("utf-8"))["bundle_id"] == second.bundle_id


def test_a_damaged_latest_copy_is_not_a_history_gap_but_a_divergent_one_is(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    first = build_from_observations(_project(), _obs("2026-09-05T12:00:00Z"), store)
    store.commit(first)
    latest_dir = store.project_dir(first.project_key) / "latest"
    (latest_dir / "snapshot.json").unlink()
    state = store.latest(first.project_key, "123456")
    assert state.verified and state.bundle_id == first.bundle_id, "the immutable bundle is intact; a damaged copy is repaired on the next commit"

    other = build_from_observations(_project(), _obs("2026-09-04T12:00:00Z"), FilesystemHistoryStore(tmp_path / "elsewhere"))
    store.publish_latest(other, store.project_dir(first.project_key))
    state = store.latest(first.project_key, "123456")
    assert not state.verified
    assert any("latest pointer" in problem and "differs from index tail" in problem for problem in state.problems)


def test_without_an_index_the_newest_immutable_bundle_is_found_by_scanning(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    first = build_from_observations(_project(), _obs("2026-09-05T12:00:00Z"), store)
    store.commit(first)
    second = build_from_observations(_project(), _obs("2026-09-06T12:00:00Z"), store)
    store.commit(second)
    (store.project_dir(first.project_key) / "index.json").unlink()
    state = store.latest(first.project_key)
    assert state.verified and state.bundle_id == second.bundle_id


def test_the_fleet_surfaces_link_to_the_immutable_report_when_the_copy_is_compacted(tmp_path):
    import shutil

    store = FilesystemHistoryStore(tmp_path)
    bundle = build_from_observations(_project(), _obs(), store)
    store.commit(bundle)
    shutil.rmtree(store.project_dir(bundle.project_key) / "latest")
    entry = store.all_projects()[0]
    assert entry["report_path"].endswith(f"/{bundle.bundle_id}/report.md")
    assert entry["attention_order"], "the attention order is read from the immutable bundle, not from the copy"
    assert (store.projects_root / entry["report_path"]).exists()


# --------------------------------------------------------------------------- #12 finding 4: metadata that decides comparability is bound to the evidence


def test_a_manifest_semantic_config_that_is_not_the_projection_of_the_stored_config_fails_verification(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    bundle = build_from_observations(_project(), _obs(), store)
    forged = dict(bundle.members)
    manifest = json.loads(forged["manifest.json"])
    manifest["semantic_config"] = {"planning": {"source": "none", "path": None, "link_marker": "Target:"}, "debt_mapping": None}
    forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
    problems = verify_members(_rehash(forged))
    assert any(p.startswith("SEMANTIC_CONFIG_MISMATCH") for p in problems)

    path = store.commit(bundle)
    (path / "manifest.json").write_bytes(forged["manifest.json"])
    state = store.latest(bundle.project_key, "123456")
    assert not state.verified, "a bundle whose comparability metadata is forged is not a source for COMPARABLE history"
    later = build_from_observations(_project(), _obs("2026-09-06T12:00:00Z"), store)
    assert later.manifest["comparison_status"] == "HISTORY_GAP"


def test_every_identity_field_the_manifest_repeats_must_agree_with_the_preimage(tmp_path):
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    for key, value in (("observed_at", "2026-01-01T00:00:00Z"), ("comparison_status", "COMPARABLE"), ("config_version", "forged"), ("project_identity", {"provider": "github", "forge_instance": "github.com", "immutable_project_id": "999", "display_locator": "acme/widget", "default_branch": "master"})):
        forged = dict(bundle.members)
        manifest = json.loads(forged["manifest.json"])
        manifest[key] = value
        forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
        problems = verify_members(_rehash(forged))
        assert any(p.startswith(f"IDENTITY_FIELD_MISMATCH: {key}") for p in problems), key


def test_a_duplicated_identity_field_deleted_from_either_copy_fails_verification(tmp_path):
    """PV-AUDIT-MANIFEST-PREIMAGE-BINDING-001: presence is bound, not only equality."""
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    for key in DUPLICATED_IDENTITY_FIELDS:
        forged = dict(bundle.members)
        manifest = json.loads(forged["manifest.json"])
        del manifest[key]
        forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
        # The preimage is untouched, so the bundle id still recomputes.
        problems = verify_members(forged)
        assert any(p.startswith(f"IDENTITY_FIELD_MISMATCH: {key}") and "absent from the manifest" in p for p in problems), key

        forged = dict(bundle.members)
        manifest = json.loads(forged["manifest.json"])
        del manifest["identity_preimage"][key]
        forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
        problems = verify_members(_rehash(forged))
        assert any(p.startswith(f"IDENTITY_FIELD_MISMATCH: {key}") for p in problems), key


def test_deleting_the_renderer_version_no_longer_skips_the_report_replay_silently(tmp_path):
    """The concrete bypass of the audit: without the field the replay was skipped and the bundle verified."""
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    forged = dict(bundle.members)
    forged["report.md"] = b"# Anything at all\n"
    manifest = json.loads(forged["manifest.json"])
    del manifest["renderer_version"]
    manifest["members"]["report.md"] = canonical.digest_bytes(forged["report.md"])
    forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
    problems = verify_members(forged)
    assert problems, "a report nobody can replay must not verify"
    assert any(p.startswith("IDENTITY_FIELD_MISMATCH: renderer_version") for p in problems)

    for field in ("renderer_version", "artifact_contract_version"):
        forged = dict(bundle.members)
        manifest = json.loads(forged["manifest.json"])
        del manifest[field]
        del manifest["identity_preimage"][field]
        forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
        assert verify_members(_rehash(forged)), f"a consistent forgery without {field} in either copy still fails"


def test_an_unknown_lineage_or_a_renderer_outside_its_lineage_fails_verification(tmp_path):
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    for key, value, code in (
        ("artifact_contract_version", "devostasis.bundle.v9", "UNSUPPORTED_ARTIFACT_LINEAGE"),
        ("renderer_version", "devostasis.render.v1", "RENDERER_VERSION_NOT_IN_LINEAGE"),
        ("renderer_version", "devostasis.render.v999", "RENDERER_VERSION_NOT_IN_LINEAGE"),
    ):
        forged = dict(bundle.members)
        manifest = json.loads(forged["manifest.json"])
        manifest[key] = value
        manifest["identity_preimage"][key] = value
        forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
        problems = verify_members(_rehash(forged))
        assert any(p.startswith(code) for p in problems), (key, value, problems)


def test_the_lineage_table_carries_the_lineage_and_renderer_this_version_writes(tmp_path):
    assert ARTIFACT_CONTRACT_VERSION in LINEAGES
    assert RENDERER_VERSION in LINEAGES[ARTIFACT_CONTRACT_VERSION]["renderers"]
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    written = set(bundle.manifest["identity_preimage"])
    assert written == LINEAGES[ARTIFACT_CONTRACT_VERSION]["preimage_fields"], "a new preimage field needs a new lineage row"


def test_a_preimage_field_added_or_removed_is_an_unsupported_shape(tmp_path):
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    for mutate, expected in (
        (lambda preimage: preimage.update({"forged_field": "x"}), "IDENTITY_PREIMAGE_SHAPE_MISMATCH: forged_field is not a field"),
        # Without it the receipt binding was simply not checked: an unbound receipt verified.
        (lambda preimage: preimage.pop("source_receipts_digest"), "IDENTITY_PREIMAGE_SHAPE_MISMATCH: source_receipts_digest is a field"),
    ):
        forged = dict(bundle.members)
        manifest = json.loads(forged["manifest.json"])
        mutate(manifest["identity_preimage"])
        forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
        problems = verify_members(_rehash(forged))
        assert any(p.startswith(expected) for p in problems), problems


def _rerender(members):
    """Re-render report.md from the (possibly forged) manifest and members, and re-digest it, as a careful forger would."""
    from devostasis import render

    members = dict(members)
    manifest = json.loads(members["manifest.json"])
    parsed = {name: json.loads(members[name]) for name in ("snapshot.json", "delta.json", "activity.json", "gauges.json", "demand.json") if name in members}
    report = render.render_report(
        manifest, parsed.get("snapshot.json"), parsed.get("delta.json"), parsed.get("activity.json"),
        parsed.get("gauges.json"), parsed.get("demand.json"), json.loads(members["effective-config.json"]).get("display"),
    ).encode("utf-8")
    members["report.md"] = report
    manifest["members"]["report.md"] = canonical.digest_bytes(report)
    members["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
    return members


@pytest.mark.parametrize("dropped", ["delta.json", "snapshot.json"])
def test_a_hashed_member_deleted_with_its_entry_no_longer_verifies(tmp_path, dropped):
    """The deletion kept the bundle id, stopped the replay (which needs both) and let any report verify."""
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    forged = dict(bundle.members)
    del forged[dropped]
    forged["report.md"] = b"# Anything at all\n"
    manifest = json.loads(forged["manifest.json"])
    del manifest["members"][dropped]
    manifest["members"]["report.md"] = canonical.digest_bytes(forged["report.md"])
    forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
    problems = verify_members(forged)
    assert any(p.startswith(f"IDENTITY_MEMBER_NOT_DECLARED: {dropped}") for p in problems), problems


def test_the_adapters_the_report_names_are_bound_to_the_identity(tmp_path):
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    for adapters in ([{"provider": "gitlab", "adapter_version": "devostasis.gitlab.v9"}], None):
        forged = dict(bundle.members)
        manifest = json.loads(forged["manifest.json"])
        if adapters is None:
            del manifest["adapters"]
        else:
            manifest["adapters"] = adapters
        forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
        if adapters is not None:
            forged = _rerender(forged)
        problems = verify_members(forged)
        assert any(p.startswith("ADAPTERS_MISMATCH") for p in problems), (adapters, problems)
    assert verify_members(bundle.members) == []


def test_the_receipt_and_the_evidence_are_bound_to_the_identity(tmp_path):
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    forged = dict(bundle.members)
    manifest = json.loads(forged["manifest.json"])
    manifest["receipt_identity"]["capability_notes"] = ["FORGED"]
    forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
    problems = verify_members(_rehash(forged))
    assert any(p.startswith("RECEIPT_DIGEST_MISMATCH") for p in problems)
    assert any(p.startswith("RECEIPT_COPY_MISMATCH") for p in problems), "observations.json still carries the receipt that was hashed"

    forged = dict(bundle.members)
    observations = json.loads(forged["observations.json"])
    observations["observations"][0]["value"] = {"forged": True}
    forged["observations.json"] = canonical.pretty_json(observations).encode("utf-8")
    problems = verify_members(_rehash(forged))
    assert any(p.startswith("OBSERVATIONS_DIGEST_MISMATCH") for p in problems), "the snapshot names the evidence it was evaluated over"


def test_a_manifest_of_the_wrong_shape_is_a_verification_problem_not_an_exception(tmp_path):
    bundle = build_from_observations(_project(), _obs(), FilesystemHistoryStore(tmp_path))
    assert verify_members({"manifest.json": b"[]"}) == ["manifest.json is not an object but list"]
    forged = dict(bundle.members)
    manifest = json.loads(forged["manifest.json"])
    manifest["members"] = ["snapshot.json"]
    forged["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
    assert verify_members(forged) == ["manifest members is not an object but list"]


def test_the_binding_holds_every_bundle_this_version_writes(tmp_path):
    store = FilesystemHistoryStore(tmp_path)
    for project in (_project(), _project(observations_member=False), _project(activity={"enabled": False}), _project(debt={"labels": ["debt"], "mapping_version": "1"})):
        bundle = build_from_observations(project, _obs(), store)
        assert verify_members(bundle.members) == [], project.effective_config_digest()
