"""The vector runner itself: it must fail closed, and a wrong expectation must fail.

A test suite that only ever runs passing vectors proves nothing about the
runner. These cases prove the two properties a conformance runner has to have:
a vector that cannot be executed is an error rather than a silent pass, and a
vector whose expectation is wrong fails.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devostasis import vectors
from devostasis.cli import main

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"

CLUTTER_OBSERVATIONS = [
    {"observation_id": "forge.issues.open_count", "value": 4},
    {"observation_id": "forge.issues.stale_open_count_30d", "value": 1},
    {"observation_id": "forge.change_requests.open_count", "value": 2},
    {"observation_id": "forge.change_requests.stale_open_count_14d", "value": 0},
    {"observation_id": "git.nondefault_branches.stale_count_30d", "value": 0},
]


def document(**overrides):
    vector = {
        "case": "T-VECTOR-01",
        "title": "an exactly observed inventory with one stale item is LIGHT",
        "kind": "vital",
        "given": {"vital": "clutter", "observations": CLUTTER_OBSERVATIONS},
        "expect": {"band": "LIGHT", "evaluation_status": "AVAILABLE"},
    }
    vector.update(overrides)
    return {"schema": "devostasis.vectors.v1", "vectors": [vector]}


def parse(**overrides):
    return vectors.parse_document(document(**overrides))[0]


def test_a_correct_vector_passes():
    assert vectors.run(parse()).ok


def test_a_wrong_expectation_fails_and_says_what_it_expected():
    result = vectors.run(parse(expect={"band": "CLEAN", "evaluation_status": "AVAILABLE"}))
    assert not result.ok
    assert "band: expected 'CLEAN', got 'LIGHT'" in result.failures[0]


def test_a_derived_metric_that_the_vital_never_emits_fails():
    result = vectors.run(parse(expect={"band": "LIGHT", "evaluation_status": "AVAILABLE", "derived": {"invented_metric": 1}}))
    assert not result.ok and "derived.invented_metric" in result.failures[0]


def test_an_expected_diagnostic_that_is_absent_fails():
    result = vectors.run(parse(expect={"band": "LIGHT", "evaluation_status": "AVAILABLE", "diagnostics": ["COMPONENT_UNAVAILABLE"]}))
    assert not result.ok and "diagnostics" in result.failures[0]


def test_a_forbidden_diagnostic_that_is_emitted_fails():
    given = {
        "vital": "clutter",
        "observations": [
            {"observation_id": "forge.issues.open_count", "status": "UNAVAILABLE", "reason_code": "ISSUES_DISABLED"},
            {"observation_id": "forge.issues.stale_open_count_30d", "status": "UNAVAILABLE", "reason_code": "ISSUES_DISABLED"},
            {"observation_id": "forge.change_requests.open_count", "value": 2},
            {"observation_id": "forge.change_requests.stale_open_count_14d", "value": 0},
            {"observation_id": "git.nondefault_branches.stale_count_30d", "value": 0},
        ],
    }
    expect = {"band": None, "evaluation_status": "UNKNOWN", "diagnostics_absent": ["COMPONENT_UNAVAILABLE"]}
    result = vectors.run(parse(given=given, expect=expect))
    assert not result.ok and "must not be emitted" in result.failures[0]


def test_an_envelope_that_violates_the_observation_contract_is_a_failure_not_a_pass():
    """AVAILABLE without a value is invalid evidence; the vector reports it instead of crashing."""
    given = {"vital": "clutter", "observations": [{"observation_id": "forge.issues.open_count", "status": "AVAILABLE"}]}
    result = vectors.run(parse(given=given))
    assert not result.ok and "ObservationError" in result.failures[0]


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"kind": "bundle"}, "unknown kind"),
        ({"unexpected": 1}, "unknown keys"),
        ({"expect": {"band": "LIGHT", "evaluation_status": "AVAILABLE", "invented": 1}}, "unknown keys"),
        ({"given": {"vital": "gravity", "observations": CLUTTER_OBSERVATIONS}}, "unknown vital"),
        ({"given": {"vital": "clutter", "observations": []}}, "non-empty list"),
        ({"expect": {"band": "LIGHT"}}, "missing keys"),
    ],
)
def test_a_vector_that_cannot_run_is_rejected_at_load_time(overrides, message):
    with pytest.raises(vectors.VectorError) as error:
        parse(**overrides)
    assert message in str(error.value)


def test_a_file_that_is_not_a_vector_document_is_rejected():
    for bad in ({"schema": "devostasis.vectors.v99", "vectors": []}, {"schema": "devostasis.vectors.v1", "vectors": []}, {"vectors": []}):
        with pytest.raises(vectors.VectorError):
            vectors.parse_document(bad)


def test_two_files_may_not_claim_the_same_case_id(tmp_path):
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_text(json.dumps(document()), encoding="utf-8")
    with pytest.raises(vectors.VectorError) as error:
        vectors.load([tmp_path])
    assert "duplicate case T-VECTOR-01" in str(error.value)


def test_a_missing_path_is_an_error_not_an_empty_run(tmp_path):
    with pytest.raises(vectors.VectorError):
        vectors.load([tmp_path / "absent"])


def test_the_delta_kind_defaults_both_sides_to_the_same_rule_so_no_boundary_is_invented():
    vector = parse(
        kind="delta",
        given={"previous": {"vitals": [{"vital_id": "flow", "band": "GRIDLOCKED"}]}, "current": {"vitals": [{"vital_id": "flow", "band": "MOVING"}]}},
        expect={"vitals": {"flow": {"transition_class": "IMPROVED"}}},
    )
    assert vectors.run(vector).ok


def test_the_cli_runs_a_corpus_and_reports_failures(tmp_path, capsys):
    (tmp_path / "good.json").write_text(json.dumps(document()), encoding="utf-8")
    assert main(["vectors", "--path", str(tmp_path)]) == 0
    assert "PASS T-VECTOR-01" in capsys.readouterr().out

    (tmp_path / "bad.json").write_text(
        json.dumps(document(case="T-VECTOR-02", expect={"band": "HEAVY", "evaluation_status": "AVAILABLE"})), encoding="utf-8"
    )
    assert main(["vectors", "--path", str(tmp_path)]) == 1
    assert "FAIL T-VECTOR-02" in capsys.readouterr().out

    assert main(["vectors", "--path", str(tmp_path), "--case", "T-VECTOR-01"]) == 0
    assert main(["vectors", "--path", str(tmp_path), "--case", "T-NOT-A-CASE"]) == 2


def test_the_published_vector_schema_and_the_runner_agree_on_the_shape():
    from devostasis import canonical

    schema = canonical.load_file(SCHEMAS / "conformance-vector.schema.json")
    entry = schema["properties"]["vectors"]["items"]
    assert set(entry["required"]) == vectors.REQUIRED_VECTOR_KEYS
    assert set(entry["properties"]) == vectors.VECTOR_KEYS
    assert set(entry["properties"]["kind"]["enum"]) == set(vectors.KINDS)
    branches = {branch["if"]["properties"]["kind"]["const"]: branch["then"]["properties"] for branch in entry["allOf"]}
    assert set(branches) == set(vectors.KINDS), "every kind the runner executes has a schema branch, and no other"
    vital, delta, ci, activity = (branches[kind] for kind in ("vital", "delta", "ci", "activity"))
    assert set(vital["given"]["properties"]) == vectors.VITAL_GIVEN_KEYS
    assert set(vital["given"]["properties"]["variants"]["items"]["properties"]) == vectors.VITAL_VARIANT_KEYS
    vital_expect = schema["$defs"]["vital_expect"]
    assert vital["expect"] == {"$ref": "#/$defs/vital_expect"}
    assert set(vital_expect["properties"]) == vectors.VITAL_EXPECT_KEYS
    result_shape, refusal_shape = vital_expect["oneOf"]
    assert set(result_shape["required"]) == vectors.REQUIRED_VITAL_EXPECT_KEYS and result_shape["not"] == {"required": ["rejected"]}
    assert refusal_shape == {"required": ["rejected"], "maxProperties": 1}, "a refusal is the whole expectation"
    assert set(vital["given"]["properties"]["derive"]["properties"]) == vectors.DERIVE_KEYS
    assert set(vital["given"]["properties"]["derive"]["properties"]["planning_source"]["enum"]) == set(vectors.PLANNING_SOURCES)
    assert set(ci["given"]["properties"]) == vectors.CI_GIVEN_KEYS
    assert set(ci["given"]["properties"]["variants"]["items"]["properties"]) == vectors.CI_VARIANT_KEYS
    assert set(ci["given"]["properties"]["provider"]["enum"]) == set(vectors.CI_PROVIDERS)
    assert set(ci["expect"]["properties"]) == vectors.CI_EXPECT_KEYS
    assert ci["expect"]["properties"]["integrity"] == {"$ref": "#/$defs/vital_expect"}, "the Integrity a ci case chains into is checked by the vital shape"
    revision_expect = ci["expect"]["properties"]["revisions"]["additionalProperties"]
    assert set(revision_expect["properties"]) == vectors.CI_REVISION_EXPECT_KEYS
    assert set(revision_expect["properties"]["parents"]["items"]["properties"]) == vectors.CI_PARENT_EXPECT_KEYS
    assert set(activity["given"]["properties"]) == vectors.ACTIVITY_GIVEN_KEYS
    assert set(activity["expect"]["properties"]) == vectors.ACTIVITY_EXPECT_KEYS
    assert set(activity["expect"]["properties"]["interval"]["properties"]) == vectors.ACTIVITY_INTERVAL_KEYS
    assert set(delta["given"]["properties"]) == vectors.DELTA_GIVEN_KEYS
    delta_expect = schema["$defs"]["delta_expect"]
    assert delta["expect"] == {"$ref": "#/$defs/delta_expect"}, "the two expect shapes must be one definition, not two copies"
    assert set(delta_expect["properties"]) == vectors.DELTA_EXPECT_KEYS
    comparison = delta["given"]["properties"]["comparisons"]["items"]
    assert set(comparison["properties"]) == vectors.DELTA_COMPARISON_KEYS
    assert comparison["properties"]["expect"] == {"$ref": "#/$defs/delta_expect"}
    row = schema["$defs"]["side"]["properties"]["vitals"]["items"]
    assert set(row["properties"]) == vectors.DELTA_ROW_KEYS
    expect_row = delta_expect["properties"]["vitals"]["additionalProperties"]
    assert set(expect_row["properties"]) == vectors.DELTA_ROW_EXPECT_KEYS
    for holder in (delta["given"]["properties"], comparison["properties"], delta_expect["properties"]):
        assert set(holder["comparison_status"]["enum"]) == set(vectors.COMPARISON_STATUSES)


def test_the_schema_publishes_the_partial_envelope_the_runner_actually_accepts():
    """A vector states evidence, not a whole envelope; the published schema must say so.

    The runner fills status, provider, collected_at, source_ref and adapter_version
    before handing the envelope to the observation contract, so requiring the full
    RAW-OBS-V0 envelope here would declare every vector in this repository invalid
    against the schema that ships beside it.
    """
    from devostasis import canonical

    schema = canonical.load_file(SCHEMAS / "conformance-vector.schema.json")
    observation = canonical.load_file(SCHEMAS / "observation.schema.json")
    envelope = schema["$defs"]["envelope"]
    assert envelope["required"] == ["observation_id"]
    assert set(envelope["properties"]) == set(observation["properties"])
    branches = {branch["if"]["properties"]["kind"]["const"]: branch["then"]["properties"] for branch in schema["properties"]["vectors"]["items"]["allOf"]}
    assert branches["vital"]["given"]["properties"]["observations"]["items"] == {"$ref": "#/$defs/envelope"}
    assert branches["vital"]["given"]["properties"]["variants"]["items"]["properties"]["observations"]["items"] == {"$ref": "#/$defs/envelope"}
    assert branches["activity"]["given"]["properties"]["observations"]["items"] == {"$ref": "#/$defs/envelope"}


def test_variants_hold_every_evidence_shape_to_the_one_expectation():
    """One obligation, several shapes: the case fails when any shape disagrees, and the failure names it."""
    shapes = [
        {"title": "stated zero", "observations": CLUTTER_OBSERVATIONS},
        {"title": "stated zero again", "observations": list(CLUTTER_OBSERVATIONS)},
    ]
    assert vectors.run(parse(given={"vital": "clutter", "variants": shapes})).ok
    heavier = [dict(o, value=30) if o["observation_id"] == "forge.issues.stale_open_count_30d" else o for o in CLUTTER_OBSERVATIONS]
    heavier = [dict(o, value=40) if o["observation_id"] == "forge.issues.open_count" else o for o in heavier]
    result = vectors.run(parse(given={"vital": "clutter", "variants": shapes + [{"title": "a heavier shape", "observations": heavier}]}))
    assert not result.ok and result.failures[0].startswith("a heavier shape: band")
    with pytest.raises(vectors.VectorError, match="at least two"):
        parse(given={"vital": "clutter", "variants": shapes[:1]})
    with pytest.raises(vectors.VectorError, match="replaces"):
        parse(given={"vital": "clutter", "observations": CLUTTER_OBSERVATIONS, "variants": shapes})


def test_the_ci_kind_normalizes_provider_native_outcomes_before_integrity_sees_them():
    """A ci case starts at the outcome map; a pre-normalized verdict would prove nothing about it."""
    given = {
        "revisions": [{"sha": "a", "committed_at": "2026-09-01T10:00:00Z"}],
        "actions_runs": [{"id": 1, "head_sha": "a", "run_attempt": 2, "status": "completed", "conclusion": "success", "prior_attempts": [{"run_attempt": 1, "status": "completed", "conclusion": "timed_out"}]}],
    }
    expect = {
        "revisions": {"a": {"current_verdict": "VERIFY_PASS", "history_state": "FAILURE_OBSERVED", "historical_contribution": "VERIFY_FAIL", "parents": [{"current_state": "VERIFY_PASS", "attempts_observed": [{"attempt": 1, "state": "VERIFY_FAIL"}, {"attempt": 2, "state": "VERIFY_PASS"}]}]}},
        "integrity": {"band": "SPARSE_MIXED", "evaluation_status": "AVAILABLE", "derived": {"sample_strength": "SPARSE"}, "diagnostics": ["CI_SPARSE_SAMPLE"]},
    }
    assert vectors.run(parse(kind="ci", given=given, expect=expect)).ok
    wrong = dict(expect, integrity=dict(expect["integrity"], band="CLEAN"))
    result = vectors.run(parse(kind="ci", given=given, expect=wrong))
    assert not result.ok and "integrity.band: expected 'CLEAN'" in result.failures[0]
    with pytest.raises(vectors.VectorError, match="provider"):
        parse(kind="ci", given=dict(given, provider="gitlab"), expect=expect)
    with pytest.raises(vectors.VectorError, match="states nothing"):
        parse(kind="ci", given=given, expect={})
    unknown_status = dict(given, series_status="UNAVAILABLE")
    result = vectors.run(parse(kind="ci", given=unknown_status, expect={"integrity": {"band": None, "evaluation_status": "UNKNOWN"}}))
    assert result.ok, "the series status a ci case states reaches Integrity as an acquisition status"


def test_the_activity_kind_checks_the_interval_and_the_coverage_it_discloses():
    given = {
        "observed_at": "2026-09-06T12:00:00Z",
        "previous_observed_at": "2026-06-01T00:00:00Z",
        "observations": [{"observation_id": "git.default_branch.commits_28d", "value_type": "series", "value": [{"sha": "a1", "committed_at": "2026-09-06T08:00:00Z", "title": "x"}]}],
    }
    expect = {"interval": {"start": "2026-06-01T00:00:00Z", "basis": "PREVIOUS_BUNDLE"}, "coverage_notes": ["INTERVAL_EXCEEDS_EVIDENCE_WINDOW:evidence_from=2026-08-09T12:00:00Z"], "classes": {"REVISION": {"count": 1}}}
    assert vectors.run(parse(kind="activity", given=given, expect=expect)).ok
    result = vectors.run(parse(kind="activity", given=given, expect={"coverage_notes_absent": ["INTERVAL_EXCEEDS_EVIDENCE_WINDOW"]}))
    assert not result.ok and "must not be emitted" in result.failures[0]
    result = vectors.run(parse(kind="activity", given=given, expect={"classes": {"REVISION": {"count": 2}}}))
    assert not result.ok and "classes.REVISION.count: expected 2" in result.failures[0]
    with pytest.raises(vectors.VectorError, match="unknown keys"):
        parse(kind="activity", given=given, expect={"interval": {"width": 1}})


def test_a_comparison_status_the_engine_does_not_know_is_rejected():
    """An unrecognised status would silently run a different comparison and still pass."""
    given = {"previous": {"vitals": [{"vital_id": "flow", "band": "MOVING"}]}, "current": {"vitals": [{"vital_id": "flow", "band": "MOVING"}]}}
    expect = {"vitals": {"flow": {"transition_class": "UNCHANGED"}}}
    with pytest.raises(vectors.VectorError) as error:
        parse(kind="delta", given=dict(given, comparison_status="COMPARABEL"), expect=expect)
    assert "unknown comparison_status" in str(error.value)
    with pytest.raises(vectors.VectorError):
        parse(kind="delta", given=given, expect=dict(expect, comparison_status="COMPARABEL"))


@pytest.mark.parametrize(
    "kind, given, expect",
    [
        ("ci", {"revisions": [{"sha": "a", "committed_at": "2026-09-01T00:00:00Z"}]}, {"revisions": {}}),
        ("ci", {"revisions": [{"sha": "a", "committed_at": "2026-09-01T00:00:00Z"}]}, {"revisions": {"a": {}}}),
        ("activity", {"observations": [{"observation_id": "git.default_branch.commits_28d", "value_type": "series", "value": []}]}, {"coverage_notes": []}),
        ("activity", {"observations": [{"observation_id": "git.default_branch.commits_28d", "value_type": "series", "value": []}]}, {"interval": {}, "classes": {}}),
        ("vital", {"vital": "clutter", "observations": CLUTTER_OBSERVATIONS}, {"band": "LIGHT", "evaluation_status": "AVAILABLE", "diagnostics": [""]}),
        ("vital", {"vital": "clutter", "observations": CLUTTER_OBSERVATIONS}, {"band": "LIGHT", "evaluation_status": "AVAILABLE", "derived": {}}),
    ],
    ids=["ci-empty-revisions", "ci-empty-row", "activity-empty-notes", "activity-empty-interval", "vital-empty-code", "vital-empty-derived"],
)
def test_an_expectation_that_states_nothing_is_refused(kind, given, expect):
    """An empty container asserts nothing and an empty code matches every code; neither may pass as proof."""
    with pytest.raises(vectors.VectorError, match="states nothing|not a code"):
        parse(kind=kind, given=given, expect=expect)


def test_an_exactly_empty_metric_delta_is_still_a_statement():
    """metric_deltas is compared exactly, so an empty list says 'no metric moved'."""
    comparison = {
        "previous": {"vitals": [{"vital_id": "clutter", "band": "LIGHT"}]},
        "current": {"vitals": [{"vital_id": "clutter", "band": "LIGHT"}]},
    }
    vector = parse(kind="delta", given=comparison, expect={"vitals": {"clutter": {"transition_class": "UNCHANGED", "metric_deltas": []}}})
    assert vector.kind == "delta"


# --------------------------------------------------------------------------- derive and rejected (0.2.0)

HORIZON_COUNTS = [
    {"observation_id": "planning.explicit_targets.capability", "value_type": "enum", "value": "SUPPORTED"},
    {"observation_id": "planning.explicit_targets.open_count", "value": 1},
    {"observation_id": "planning.explicit_targets.open_with_future_boundary_count", "value": 1},
    {"observation_id": "planning.explicit_targets.open_beyond_28d_count", "value": 2},
]


def test_derive_runs_the_derivation_before_the_vital_is_evaluated():
    """A case about an inventory is executed over the derivation, not over counts somebody pre-derived."""
    inventory = [{
        "observation_id": "planning.explicit_targets.inventory",
        "value_type": "series",
        "value": [{"target_id": "1", "state": "OPEN", "due_at": None}],
        "coverage": {"complete": True, "source": "milestones"},
    }]
    given = {"vital": "horizon", "observations": inventory, "derive": {"planning_source": "milestones", "debt_mapping": None}}
    assert vectors.run(parse(given=given, expect={"band": "DECLARED", "evaluation_status": "AVAILABLE", "derived": {"open_count": 1}})).ok
    without = vectors.run(parse(given={"vital": "horizon", "observations": inventory}, expect={"band": "DECLARED", "evaluation_status": "AVAILABLE"}))
    assert not without.ok, "without derive the inventory alone is not Horizon's input"


def test_derive_names_only_the_settings_the_derivation_reads():
    for derive in ({"planning_source": "jira"}, {"debt_mapping": None}, {"planning_source": "none", "extra": 1}, {"planning_source": "none", "debt_mapping": ["debt"]}):
        with pytest.raises(vectors.VectorError):
            parse(given={"vital": "horizon", "observations": HORIZON_COUNTS, "derive": derive})


def test_a_rejected_case_passes_only_when_the_evidence_is_refused_with_that_code():
    given = {"vital": "horizon", "observations": HORIZON_COUNTS}
    assert vectors.run(parse(given=given, expect={"rejected": "HORIZON_COUNTS_INCONSISTENT"})).ok
    wrong_code = vectors.run(parse(given=given, expect={"rejected": "DIRECTION_LINKAGE_COUNTS_INCONSISTENT"}))
    assert not wrong_code.ok and "HORIZON_COUNTS_INCONSISTENT" in wrong_code.failures[0]
    admissible = vectors.run(parse(expect={"rejected": "HORIZON_COUNTS_INCONSISTENT"}))
    assert not admissible.ok and "it evaluated to LIGHT / AVAILABLE" in admissible.failures[0]


def test_rejected_is_the_whole_expectation_and_names_a_code():
    for expect in ({"rejected": "X", "band": None}, {"rejected": ""}, {"rejected": 3}):
        with pytest.raises(vectors.VectorError):
            parse(given={"vital": "horizon", "observations": HORIZON_COUNTS}, expect=expect)
