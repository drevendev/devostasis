"""Integrity bands and PV-CI-UNIT-004 revision semantics (R54-R57 and the V0.x chain)."""

from devostasis.adapters import github_ci
from devostasis.observations import PARTIAL
from devostasis.vitals import integrity
from helpers import add, integrity_inputs, obs_set, parent, passing_revisions, revision


def test_uninstrumented_when_ci_positively_absent():
    obs = obs_set()
    integrity_inputs(obs, False, [revision("a", "2026-09-01T00:00:00Z")])
    result = integrity.evaluate(obs)
    assert result.band == "UNINSTRUMENTED" and result.evaluation_status == "AVAILABLE"


def test_unknown_when_configuration_cannot_be_established():
    obs = obs_set()
    integrity_inputs(obs, None, [revision("a", "2026-09-01T00:00:00Z")])
    result = integrity.evaluate(obs)
    assert result.band is None and result.evaluation_status == "UNKNOWN"


def test_t1_no_recent_runs_is_neither_clean_nor_uninstrumented():
    obs = obs_set()
    integrity_inputs(obs, True, [revision("a", "2026-09-01T00:00:00Z")])
    assert integrity.evaluate(obs).band == "NO_RECENT_RUNS"


def test_no_decisive_runs_when_only_cancelled_or_unresolved():
    obs = obs_set()
    integrity_inputs(obs, True, [revision("a", "2026-09-01T00:00:00Z", [parent("p1", "NON_VERIFY_TERMINAL")], "NON_VERIFY_TERMINAL")])
    assert integrity.evaluate(obs).band == "NO_DECISIVE_RUNS"


def test_sparse_and_sparse_mixed():
    obs = obs_set()
    integrity_inputs(obs, True, passing_revisions(2))
    assert integrity.evaluate(obs).band == "SPARSE"
    obs = obs_set()
    revs = passing_revisions(2) + [revision("bad", "2026-08-30T00:00:00Z", [parent("pf", "VERIFY_FAIL")], "VERIFY_FAIL", "FAILURE_OBSERVED")]
    integrity_inputs(obs, True, revs)
    assert integrity.evaluate(obs).band == "SPARSE_MIXED"


def test_clean_flaky_and_failing_by_ratio():
    obs = obs_set()
    integrity_inputs(obs, True, passing_revisions(4))
    assert integrity.evaluate(obs).band == "CLEAN"

    obs = obs_set()
    revs = passing_revisions(7) + [revision("f1", "2026-08-30T00:00:00Z", [parent("pf", "VERIFY_FAIL")], "VERIFY_FAIL", "FAILURE_OBSERVED")]
    integrity_inputs(obs, True, revs)
    result = integrity.evaluate(obs)
    assert result.band == "FLAKY" and result.derived["failure_ratio_14d"] == {"num": 1, "den": 8}

    obs = obs_set()
    revs = passing_revisions(3) + [revision("f1", "2026-08-30T00:00:00Z", [parent("pf", "VERIFY_FAIL")], "VERIFY_FAIL", "FAILURE_OBSERVED")]
    integrity_inputs(obs, True, revs)
    assert integrity.evaluate(obs).band == "FAILING"


def test_failing_when_latest_revision_currently_fails_even_with_clean_history():
    obs = obs_set()
    revs = passing_revisions(6) + [revision("zz", "2026-09-09T00:00:00Z", [parent("pf", "VERIFY_FAIL")], "VERIFY_FAIL", "FAILURE_OBSERVED")]
    integrity_inputs(obs, True, revs)
    assert integrity.evaluate(obs).band == "FAILING"


def test_r54_same_revision_retry_success_keeps_historical_failure():
    run = {"id": 1, "run_attempt": 2, "status": "completed", "conclusion": "success", "name": "ci", "event": "push"}
    prior = [{"run_attempt": 1, "status": "completed", "conclusion": "failure"}]
    parent_record = github_ci.actions_parent(run, prior)
    assert parent_record["current_state"] == "VERIFY_PASS" and parent_record["history_state"] == "FAILURE_OBSERVED"
    records = github_ci.build_revision_records([{"sha": "r", "committed_at": "2026-09-01T00:00:00Z"}], {"r": [parent_record]})
    assert records[0]["current_verdict"] == "VERIFY_PASS"
    assert records[0]["historical_contribution"] == "VERIFY_FAIL"
    obs = obs_set()
    integrity_inputs(obs, True, passing_revisions(3) + records)
    result = integrity.evaluate(obs)
    assert result.derived["failed_count_14d"] == 1 and result.derived["decisive_count_14d"] == 4 and result.band == "FAILING"


def test_r55_retry_count_invariance():
    def contribution(retries: int) -> str:
        prior = [{"run_attempt": 1, "status": "completed", "conclusion": "failure"}] + [
            {"run_attempt": n, "status": "completed", "conclusion": "success"} for n in range(2, retries + 1)
        ]
        run = {"id": 9, "run_attempt": retries + 1, "status": "completed", "conclusion": "success", "name": "ci"}
        records = github_ci.build_revision_records([{"sha": "r", "committed_at": "2026-09-01T00:00:00Z"}], {"r": [github_ci.actions_parent(run, prior)]})
        return records[0]["historical_contribution"]

    assert {contribution(n) for n in (1, 2, 3, 4)} == {"VERIFY_FAIL"}


def test_r56_newer_revision_is_a_distinct_sample():
    failed = revision("r1", "2026-09-01T00:00:00Z", [parent("p1", "VERIFY_FAIL")], "VERIFY_FAIL", "FAILURE_OBSERVED")
    passed = revision("r2", "2026-09-02T00:00:00Z", [parent("p2", "VERIFY_PASS")], "VERIFY_PASS", "PASS_ONLY_OBSERVED")
    obs = obs_set()
    integrity_inputs(obs, True, [failed, passed])
    result = integrity.evaluate(obs)
    assert result.derived["decisive_count_14d"] == 2 and result.derived["failed_count_14d"] == 1
    assert result.band == "SPARSE_MIXED"


def test_r57_order_and_surface_invariance():
    commits = [{"sha": "a", "committed_at": "2026-09-01T00:00:00Z"}, {"sha": "b", "committed_at": "2026-09-02T00:00:00Z"}]
    run_a = {"id": 1, "run_attempt": 2, "status": "completed", "conclusion": "success", "name": "ci"}
    prior_a = [{"run_attempt": 1, "status": "completed", "conclusion": "failure"}]
    run_b = {"id": 2, "run_attempt": 1, "status": "completed", "conclusion": "success", "name": "ci"}
    forward = github_ci.build_revision_records(commits, {"a": [github_ci.actions_parent(run_a, prior_a)], "b": [github_ci.actions_parent(run_b, [])]})
    backward = github_ci.build_revision_records(list(reversed(commits)), {"b": [github_ci.actions_parent(run_b, [])], "a": [github_ci.actions_parent(run_a, list(reversed(prior_a)))]})
    assert forward == backward


def test_v0_7_unresolved_sibling_blocks_pass_but_not_fail():
    assert github_ci.compose_current(["VERIFY_PASS", "VERIFY_UNRESOLVED"]) == "VERIFY_UNRESOLVED"
    assert github_ci.compose_current(["VERIFY_FAIL", "VERIFY_UNRESOLVED"]) == "VERIFY_FAIL"
    assert github_ci.compose_current(["UNKNOWN", "VERIFY_PASS"]) == "UNKNOWN"
    assert github_ci.compose_current(["NOT_EXECUTED", "VERIFY_PASS"]) == "VERIFY_PASS"


def test_ci_norm_outcome_mapping_fails_closed():
    assert github_ci.normalize_outcome("completed", "success") == "VERIFY_PASS"
    assert github_ci.normalize_outcome("completed", "failure") == "VERIFY_FAIL"
    assert github_ci.normalize_outcome("completed", "timed_out") == "VERIFY_FAIL"
    assert github_ci.normalize_outcome("completed", "cancelled") == "NON_VERIFY_TERMINAL"
    assert github_ci.normalize_outcome("completed", "skipped") == "NOT_EXECUTED"
    assert github_ci.normalize_outcome("in_progress", None) == "VERIFY_UNRESOLVED"
    assert github_ci.normalize_outcome("completed", "startup_failure") == "UNKNOWN"
    assert github_ci.normalize_outcome("completed", "some_future_value") == "UNKNOWN"


def test_current_unresolved_is_unknown_unless_failing_is_already_established():
    """PV-INTEGRITY-TOTALITY-001: an older pass never speaks for a revision still being verified."""
    revs = passing_revisions(4) + [revision("new", "2026-09-09T00:00:00Z", [parent("pn", "VERIFY_UNRESOLVED")], "VERIFY_UNRESOLVED", "NO_DECISIVE_OBSERVED")]
    obs = obs_set()
    integrity_inputs(obs, True, revs)
    result = integrity.evaluate(obs)
    assert result.band is None and result.evaluation_status == "UNKNOWN" and result.possible_bands is None
    assert "CI_CURRENT_VERIFY_UNRESOLVED" in result.diagnostics

    revs = passing_revisions(3) + [revision("f1", "2026-08-30T00:00:00Z", [parent("pf", "VERIFY_FAIL")], "VERIFY_FAIL", "FAILURE_OBSERVED")]
    revs += [revision("new", "2026-09-09T00:00:00Z", [parent("pn", "VERIFY_UNRESOLVED")], "VERIFY_UNRESOLVED", "NO_DECISIVE_OBSERVED")]
    obs = obs_set()
    integrity_inputs(obs, True, revs)
    result = integrity.evaluate(obs)
    assert (result.band, result.evaluation_status, result.band_semantics, result.possible_bands) == ("FAILING", "DEGRADED", "EXACT", None)


def test_partial_revision_series_is_unknown_with_its_evidence_preserved():
    """PV-REV-TEST-003: a truncated required series has no accepted degraded path.

    Rule v0 emitted CLEAN / DEGRADED with a fixed three-band tail it called a
    superset (#12 finding 3). The accepted Integrity chain says a PARTIAL
    required input is UNKNOWN with no band; what was collected stays visible.
    """
    obs = obs_set()
    integrity_inputs(obs, True, passing_revisions(5), status=PARTIAL)
    result = integrity.evaluate(obs)
    assert result.band is None and result.evaluation_status == "UNKNOWN" and result.possible_bands is None
    assert result.derived["decisive_count_14d"] == 5 and result.derived["series_status"] == "PARTIAL"
    assert "REVISION_SERIES_PARTIAL:PAGINATION_CAPPED" in result.diagnostics
    assert result.rule_id == "integrity.bands.v1+ci-unit-004+hist-002"


def test_sparse_samples_declare_their_strength_and_established_ones_do_not_carry_the_diagnostic():
    """PV-REV-TEST-VECTORS-002 (R1, R2): one to three decisive revisions are SPARSE and say so."""
    for count in (1, 2, 3):
        obs = obs_set()
        integrity_inputs(obs, True, passing_revisions(count))
        result = integrity.evaluate(obs)
        assert result.derived["sample_strength"] == "SPARSE" and "CI_SPARSE_SAMPLE" in result.diagnostics, count
    obs = obs_set()
    integrity_inputs(obs, True, passing_revisions(4))
    result = integrity.evaluate(obs)
    assert result.derived["sample_strength"] == "ESTABLISHED" and "CI_SPARSE_SAMPLE" not in result.diagnostics
    obs = obs_set()
    integrity_inputs(obs, True, [revision("a", "2026-09-01T00:00:00Z", [parent("p1", "NON_VERIFY_TERMINAL")], "NON_VERIFY_TERMINAL")])
    result = integrity.evaluate(obs)
    assert "sample_strength" not in result.derived, "no decisive sample has no strength"


def test_a_newest_unknown_verdict_never_inherits_an_older_pass():
    """PV-REV-INTEGRITY-UNKNOWN-001 (#13): unknown is the absence of an observation, not a skipped run."""
    revs = passing_revisions(4) + [revision("new", "2026-09-09T00:00:00Z", [parent("pn", "UNKNOWN")], "UNKNOWN", "NO_DECISIVE_OBSERVED")]
    obs = obs_set()
    integrity_inputs(obs, True, revs)
    result = integrity.evaluate(obs)
    assert result.band is None and result.evaluation_status == "UNKNOWN" and result.possible_bands is None
    assert result.derived["decisive_count_14d"] == 4 and result.derived["failed_count_14d"] == 0
    assert "CURRENT_VERDICT_UNKNOWN:new" in result.diagnostics
    assert not any(code.startswith("LATEST_REVISION_NON_DECISIVE") for code in result.diagnostics)
    assert result.derived["unknown_verdict_rule"] == "PV-REV-INTEGRITY-UNKNOWN-001"


def _unresolved_over(passes: int, fails: int, newest_history: str = "NO_DECISIVE_OBSERVED"):
    revs = passing_revisions(passes) + [
        revision(f"f{i}", f"2026-08-{20 + i:02d}T00:00:00Z", [parent(f"pf{i}", "VERIFY_FAIL")], "VERIFY_FAIL", "FAILURE_OBSERVED") for i in range(fails)
    ]
    revs += [revision("new", "2026-09-09T00:00:00Z", [parent("pn", "VERIFY_UNRESOLVED")], "VERIFY_UNRESOLVED", newest_history)]
    obs = obs_set()
    integrity_inputs(obs, True, revs)
    return integrity.evaluate(obs)


def test_an_unresolved_newest_revision_never_emits_a_band_its_history_does_not_already_prove():
    """The superset this rule version first carried could omit the band it emitted (777 of 7,029 shapes).

    Under the accepted totality rule there is no superset to get wrong: over
    every history, the band is FAILING exactly where the established FAILING
    predicate already holds, and nothing everywhere else.
    """
    for passes in range(0, 9):
        for fails in range(0, 5):
            result = _unresolved_over(passes, fails)
            n, f = passes + fails, fails
            if integrity.established_failing(n, f):
                assert (result.band, result.evaluation_status, result.band_semantics) == ("FAILING", "DEGRADED", "EXACT"), (n, f)
            else:
                assert (result.band, result.evaluation_status) == (None, "UNKNOWN"), (n, f)
            assert result.possible_bands is None and "CI_CURRENT_VERIFY_UNRESOLVED" in result.diagnostics, (n, f)
            assert result.derived["decisive_count_14d"] == n and result.derived["failed_count_14d"] == f


def test_a_newest_revision_with_one_workflow_passed_and_one_running_is_already_counted_and_still_unresolved():
    """The live shape the superset got wrong: the revision is decisive history and unresolved at once."""
    revs = passing_revisions(1) + [revision("f1", "2026-08-30T00:00:00Z", [parent("pf", "VERIFY_FAIL")], "VERIFY_FAIL", "FAILURE_OBSERVED")]
    revs += [revision("new", "2026-09-09T00:00:00Z", [parent("ci", "VERIFY_PASS"), parent("docs", "VERIFY_UNRESOLVED")], "VERIFY_UNRESOLVED", "PASS_ONLY_OBSERVED")]
    obs = obs_set()
    integrity_inputs(obs, True, revs)
    result = integrity.evaluate(obs)
    assert result.derived["decisive_count_14d"] == 3, "the passed workflow already counts the revision"
    assert (result.band, result.evaluation_status) == (None, "UNKNOWN"), "SPARSE_MIXED would let the older sample speak for the running workflow"


def test_a_verdict_outside_the_vocabulary_fails_closed_instead_of_falling_back_to_an_older_pass():
    for token in ("PENDING", "VERIFY_PASSED", "SOME_FUTURE_STATE"):
        revs = passing_revisions(4) + [revision("new", "2026-09-09T00:00:00Z", [parent("pn", token)], token, "NO_DECISIVE_OBSERVED")]
        obs = obs_set()
        integrity_inputs(obs, True, revs)
        result = integrity.evaluate(obs)
        assert (result.band, result.evaluation_status) == (None, "UNKNOWN"), token
        assert f"CURRENT_VERDICT_UNRECOGNIZED:{token}" in result.diagnostics
        assert not any(code.startswith("LATEST_REVISION_NON_DECISIVE") for code in result.diagnostics)


def test_a_record_whose_contribution_contradicts_its_history_is_a_defect_not_a_pass():
    contradictory = revision("r9", "2026-09-05T00:00:00Z", [parent("p9", "VERIFY_PASS")], "VERIFY_PASS", "PASS_ONLY_OBSERVED")
    contradictory["historical_contribution"] = "VERIFY_FAIL"
    obs = obs_set()
    integrity_inputs(obs, True, passing_revisions(4) + [contradictory])
    result = integrity.evaluate(obs)
    assert (result.band, result.evaluation_status) == (None, "UNKNOWN")
    assert "REVISION_RECORD_INCONSISTENT:r9" in result.diagnostics


def test_an_unusable_series_is_unknown_even_beside_a_positive_not_configured():
    """UNINSTRUMENTED claims there is no verification evidence; an unreadable series cannot establish that."""
    for status in ("FORBIDDEN", "ERROR", "UNKNOWN"):
        obs = obs_set()
        add(obs, "ci.configured", False, "boolean")
        add(obs, "ci.revision_verdicts_14d", None, "series", status=status, reason_code="X")
        result = integrity.evaluate(obs)
        assert (result.band, result.evaluation_status) == (None, "UNKNOWN"), status
    obs = obs_set()
    add(obs, "ci.configured", False, "boolean")
    add(obs, "ci.revision_verdicts_14d", [], "series", freshness="STALE")
    assert integrity.evaluate(obs).evaluation_status == "UNKNOWN"


def test_latest_non_decisive_revision_falls_back_to_latest_decisive_verdict():
    revs = passing_revisions(4) + [revision("skip", "2026-09-09T00:00:00Z", [parent("ps", "NOT_EXECUTED")], "NOT_EXECUTED", "NO_DECISIVE_OBSERVED")]
    obs = obs_set()
    integrity_inputs(obs, True, revs)
    result = integrity.evaluate(obs)
    assert result.band == "CLEAN" and result.evaluation_status == "AVAILABLE"
    assert any(code.startswith("LATEST_REVISION_NON_DECISIVE") for code in result.diagnostics)


def test_parent_level_provenance_is_diagnosed_and_a_favorable_one_is_unknown_history():
    """R52 and PV-HIST-002 HIST-06: a check suite hides its earlier outcomes, so its pass proves no history.

    The record states PASS_ONLY_OBSERVED, as a 0.1.x record would; the union
    is rebuilt from its parents, and a parent-level pass is not a complete
    history, so the Vital claims no band around it.
    """
    revs = [revision("s", "2026-09-01T00:00:00Z", [parent("suite", "VERIFY_PASS", kind="github_check_suite")], "VERIFY_PASS", "PASS_ONLY_OBSERVED", provenance="PARENT_LEVEL_ONLY")]
    obs = obs_set()
    integrity_inputs(obs, True, revs)
    result = integrity.evaluate(obs)
    assert "HISTORY_PROVENANCE_PARENT_LEVEL_ONLY:1" in result.diagnostics and "REVISION_HISTORY_UNKNOWN:s" in result.diagnostics
    assert (result.band, result.evaluation_status) == (None, "UNKNOWN")
    assert result.derived["revision_history"]["records"][0]["history_state"] == "UNKNOWN_HISTORY"


def test_a_parent_level_failure_is_still_a_proven_failure():
    """Only favorable parent-level evidence is unknown: an observed failure is proven on any surface."""
    revs = [revision("s", "2026-09-01T00:00:00Z", [parent("suite", "VERIFY_FAIL", kind="github_check_suite")], "VERIFY_FAIL", "FAILURE_OBSERVED", provenance="PARENT_LEVEL_ONLY")]
    obs = obs_set()
    integrity_inputs(obs, True, revs)
    result = integrity.evaluate(obs)
    assert (result.band, result.evaluation_status) == ("FAILING", "AVAILABLE") and result.derived["failed_count_14d"] == 1


def test_a_record_without_its_revision_identity_is_a_defect_not_a_crash():
    """Durable history is keyed by immutable revision (PV-HIST-002): a record that names none cannot be counted or carried."""
    anonymous = revision("x", "2026-09-01T00:00:00Z", [parent("p", "VERIFY_PASS")], "VERIFY_PASS", "PASS_ONLY_OBSERVED")
    del anonymous["revision"]
    obs = obs_set()
    integrity_inputs(obs, True, passing_revisions(4) + [anonymous])
    result = integrity.evaluate(obs)
    assert (result.band, result.evaluation_status) == (None, "UNKNOWN")
    assert any(code.startswith("REVISION_RECORD_INCONSISTENT") for code in result.diagnostics)
