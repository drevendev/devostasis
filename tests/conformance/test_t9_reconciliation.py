"""T9, the final decision-equivalence reconciliation (PV-TEST-004, generator PV-T9-GEN-003).

PV-REV-TEST-004 accepted T9 with zero CONTRACT_GAP terminals: each of the nine
gap identifiers PV-T9-GEN-002 exposed maps to exactly one deterministic
accepted obligation (sections 3.1 to 3.9), and higher-precedence fail-closed
conditions stay higher (section 4). This is the implementation side of that
reconciliation: a finite generator over the acquisition tokens (CF,
POS_ABSENT, PARTIAL, UNAVAILABLE, FORBIDDEN, UNKNOWN, ERROR, STALE) and the
threshold and relational regions each former gap family names. Every cell is
evaluated, and must reach the one obligation the accepted table gives it.

It is not the T9v2 cell-key serialization: the research process delivers that
as vectors (PV-TEST-VECTORS-00n), and each family's accepted fixtures are
already vectors here (HOR-PARTIAL, CLU-INCOMPLETE, DIR-INCOMPLETE, INT-TOTAL,
DEBT-PARTIAL). What this proves is the property T9 exists for: no cell of the
nine families is left without its obligation, and none reaches another one.
The oracles below restate the accepted table, written from the contract text
rather than from the evaluators.
"""

from __future__ import annotations

import itertools

import pytest

from devostasis.normalize import linkage_state
from devostasis.observations import Observation, ObservationSet
from devostasis.vitals import clutter, debt, direction, horizon, integrity

OBSERVED_AT = "2026-09-10T12:00:00Z"
SUBSET = {"complete": False, "value_semantics": "OBSERVED_SUBSET_COUNT"}
UNCERTAIN = ("UNAVAILABLE", "FORBIDDEN", "UNKNOWN", "ERROR")
TOKENS = ("CF", "PARTIAL") + UNCERTAIN + ("STALE",)


def _obs() -> ObservationSet:
    return ObservationSet(subject={"provider": "t9", "immutable_project_id": "t9"}, observed_at=OBSERVED_AT)


def _put(obs: ObservationSet, oid: str, token: str, value, value_type: str = "count") -> None:
    common = {"provider": "t9", "collected_at": OBSERVED_AT, "source_ref": "t9", "adapter_version": "t9"}
    if token == "CF":
        obs.add(Observation(oid, "AVAILABLE", value_type, value, **common))
    elif token == "STALE":
        obs.add(Observation(oid, "AVAILABLE", value_type, value, freshness="STALE", **common))
    elif token == "PARTIAL":
        obs.add(Observation(oid, "PARTIAL", value_type, value, coverage=SUBSET if value_type == "count" else None, reason_code="PAGINATION_CAPPED", **common))
    else:
        obs.add(Observation(oid, token, value_type, None, reason_code=f"T9_{token}", **common))


def _outcome(result) -> tuple:
    return (result.evaluation_status, result.band, result.band_semantics, result.possible_bands)


UNKNOWN = ("UNKNOWN", None, None, None)


def _assert_one_obligation(result, expected, cell):
    outcome = _outcome(result)
    assert outcome[0] in ("AVAILABLE", "DEGRADED", "UNKNOWN"), cell
    assert (outcome[1] is None) == (outcome[0] == "UNKNOWN"), f"{cell}: a band exactly when the status is not UNKNOWN"
    assert not any("CONTRACT_GAP" in code for code in result.diagnostics), f"{cell}: CONTRACT_GAP is not a terminal"
    assert outcome == expected, f"{cell}: expected {expected}, got {outcome}"


# --------------------------------------------------------------------------- 3.1 Horizon partial bound

HORIZON_SHAPES = {"PH0": (0, 0, 0), "PH1": (2, 0, 0), "PH2": (2, 1, 0), "PH3": (2, 1, 1)}
HORIZON_CAPABILITIES = ("SUPPORTED", "UNSUPPORTED", "SUPPORTED_UNUSED") + UNCERTAIN + ("STALE", "PARTIAL")


def _horizon_expected(capability: str, token: str, shape: str):
    if capability in ("UNSUPPORTED", "SUPPORTED_UNUSED"):
        return ("AVAILABLE", "UNDECLARED", "EXACT", None)
    if capability != "SUPPORTED":
        return UNKNOWN
    open_count, future, beyond = HORIZON_SHAPES[shape]
    if token == "CF":
        band = "EXTENDED" if beyond else "VISIBLE" if future else "DECLARED" if open_count else "UNDECLARED"
        return ("AVAILABLE", band, "EXACT", None)
    if token == "PARTIAL":
        return ("DEGRADED", "EXTENDED", "EXACT", ["EXTENDED"]) if shape == "PH3" else UNKNOWN
    return UNKNOWN


HORIZON_CELLS = list(itertools.product(HORIZON_CAPABILITIES, TOKENS, HORIZON_SHAPES))


@pytest.mark.parametrize("capability, token, shape", HORIZON_CELLS)
def test_t9_gap_horizon_partial_bound_001(capability, token, shape):
    obs = _obs()
    if capability in ("SUPPORTED", "UNSUPPORTED", "SUPPORTED_UNUSED"):
        _put(obs, horizon.CAPABILITY, "CF", capability, "enum")
    elif capability == "STALE":
        _put(obs, horizon.CAPABILITY, "STALE", "SUPPORTED", "enum")
    elif capability == "PARTIAL":
        _put(obs, horizon.CAPABILITY, "PARTIAL", None, "enum")
    else:
        _put(obs, horizon.CAPABILITY, capability, None, "enum")
    for oid, value in zip(horizon.COUNTS, HORIZON_SHAPES[shape]):
        _put(obs, oid, token, value)
    _assert_one_obligation(horizon.evaluate(obs), _horizon_expected(capability, token, shape), (capability, token, shape))


# --------------------------------------------------------------------------- 3.2 / 3.3 Clutter incomplete components and forced bounds

CLUTTER_ISSUES = ("CF", "PARTIAL", "UNAVAILABLE", "FORBIDDEN")
CLUTTER_CRS = ("CF", "PARTIAL", "UNAVAILABLE")
CLUTTER_BRANCHES = ("CF", "PARTIAL", "UNAVAILABLE", "STALE")
STALE_WORK = (0, 3, 30)
STALE_BRANCHES = (0, 7, 25)
CLUTTER_CELLS = list(itertools.product(CLUTTER_ISSUES, CLUTTER_CRS, CLUTTER_BRANCHES, STALE_WORK, STALE_BRANCHES))
DEGRADED_SHAPES = [
    ("DEGRADED", "HEAVY", "EXACT", None),
    ("DEGRADED", "CLUTTERED", "CONSERVATIVE_LOWER_BOUND", ["CLUTTERED", "HEAVY"]),
    ("DEGRADED", "LIGHT", "CONSERVATIVE_LOWER_BOUND", ["LIGHT", "CLUTTERED", "HEAVY"]),
]


@pytest.mark.parametrize("issues, crs, branches, stale_issues, stale_branches", CLUTTER_CELLS)
def test_t9_gap_clutter_unavailable_component_and_partial_forced_bound(issues, crs, branches, stale_issues, stale_branches):
    """3.2 and 3.3: an incomplete cell is a confirmed floor from positive facts only, never CLEAN, never zero-filled."""
    obs = _obs()
    _put(obs, clutter.ISSUES_OPEN, issues, 100)
    _put(obs, clutter.ISSUES_STALE, issues, stale_issues)
    _put(obs, clutter.CR_OPEN, crs, 10)
    _put(obs, clutter.CR_STALE, crs, 0)
    _put(obs, clutter.BRANCHES_STALE, branches, stale_branches)
    if branches == "PARTIAL":
        _put(obs, clutter.BRANCHES_RETENTION, "CF", "CLASSIFIED", "enum")
    result = clutter.evaluate(obs)
    outcome = _outcome(result)
    cell = (issues, crs, branches, stale_issues, stale_branches)
    assert outcome[0] in ("AVAILABLE", "DEGRADED", "UNKNOWN") and (outcome[1] is None) == (outcome[0] == "UNKNOWN"), cell
    fail_closed = crs == "UNAVAILABLE" or issues == "FORBIDDEN" or branches == "STALE"
    complete = issues == crs == branches == "CF"
    if fail_closed:
        assert outcome == UNKNOWN, f"{cell}: a required, forbidden or stale component is never bounded around"
        return
    if complete:
        assert outcome[0] == "AVAILABLE" and outcome[2] == "EXACT", cell
        return
    assert outcome[1] != "CLEAN" and outcome[0] != "AVAILABLE", f"{cell}: incomplete coverage is never exact, never CLEAN"
    if outcome[0] == "DEGRADED":
        assert outcome in DEGRADED_SHAPES, f"{cell}: {outcome} is not an accepted floor shape"
    proven_work = stale_issues if issues in ("CF", "PARTIAL") else 0
    proven_branches = stale_branches if branches in ("CF", "PARTIAL") else 0
    if proven_work >= 25 or proven_branches >= 20:
        assert outcome == ("DEGRADED", "HEAVY", "EXACT", None), f"{cell}: a proven HEAVY fact forces HEAVY"
    if proven_work == 0 and proven_branches == 0:
        assert outcome == UNKNOWN, f"{cell}: without a positive fact there is no floor"


# --------------------------------------------------------------------------- 3.4 Direction partial linkage


def _direction_band(k: int, n: int) -> str:
    return "FULLY_LINKED" if k == n else "MIXED" if 2 * k >= n else "SCATTERED"


def _direction_expected(capability: str, n_token: str, n: int, linked: int, unresolved: int):
    if n_token != "CF":
        return UNKNOWN
    if capability == "POS_ABSENT":
        return ("AVAILABLE", "UNDECLARED", "EXACT", None)
    if capability != "SUPPORTED":
        return UNKNOWN
    if unresolved == 0:
        return ("AVAILABLE", _direction_band(linked, n), "EXACT", None)
    reachable = {_direction_band(k, n) for k in range(linked, linked + unresolved + 1)}
    if len(reachable) == 1:
        band = reachable.pop()
        return ("DEGRADED", band, "EXACT", [band])
    return UNKNOWN


DIRECTION_SPLITS = [(n, l, u, r) for n in range(1, 6) for l in range(n + 1) for u in range(n + 1 - l) for r in [n - l - u]]
DIRECTION_CELLS = list(itertools.product(("SUPPORTED", "POS_ABSENT", "UNKNOWN", "PARTIAL"), ("CF", "PARTIAL"), DIRECTION_SPLITS))


@pytest.mark.parametrize("capability, n_token, split", DIRECTION_CELLS)
def test_t9_gap_direction_partial_linkage_001(capability, n_token, split):
    n, linked, unlinked, unresolved = split
    obs = _obs()
    if capability == "SUPPORTED":
        _put(obs, horizon.CAPABILITY, "CF", "SUPPORTED", "enum")
    elif capability == "POS_ABSENT":
        _put(obs, horizon.CAPABILITY, "CF", "UNSUPPORTED", "enum")
    else:
        _put(obs, horizon.CAPABILITY, capability, None, "enum")
    _put(obs, direction.ACTIVE, n_token, n)
    for oid, value in ((direction.LINKED, linked), (direction.UNLINKED, unlinked), (direction.UNRESOLVED, unresolved)):
        _put(obs, oid, n_token, value)
    expected = _direction_expected(capability, n_token, n, linked, unresolved)
    _assert_one_obligation(direction.evaluate(obs), expected, (capability, n_token, split))
    if unresolved and expected[0] == "DEGRADED":
        assert expected[1] != "FULLY_LINKED", "a singleton FULLY_LINKED is impossible while R > 0"


# --------------------------------------------------------------------------- 3.5 Direction unresolved target

REFERENCE_STATES = ("OPEN", "CLOSED", "MISSING", "UNKNOWN", "UNAVAILABLE", "FORBIDDEN", "ERROR", "STALE", None)


@pytest.mark.parametrize("state, readable", list(itertools.product(REFERENCE_STATES, (True, False))))
def test_t9_gap_direction_unresolved_target_001(state, readable):
    """Resolved identity is LINKED open or closed, positive absence UNLINKED, anything unresolvable UNRESOLVED."""
    item = {"target_refs": [{"target_id": "T", "state": state}], "linkage_unresolved": [] if readable else ["body:dict"]}
    if state in ("OPEN", "CLOSED"):
        expected = "LINKED"
    elif state == "MISSING" and readable:
        expected = "UNLINKED"
    else:
        expected = "UNRESOLVED"
    assert linkage_state(item) == expected
    obs = _obs()
    _put(obs, horizon.CAPABILITY, "CF", "SUPPORTED", "enum")
    for oid, value in ((direction.ACTIVE, 1), (direction.LINKED, int(expected == "LINKED")), (direction.UNLINKED, int(expected == "UNLINKED")), (direction.UNRESOLVED, int(expected == "UNRESOLVED"))):
        _put(obs, oid, "CF", value)
    outcome = {"LINKED": ("AVAILABLE", "FULLY_LINKED", "EXACT", None), "UNLINKED": ("AVAILABLE", "SCATTERED", "EXACT", None), "UNRESOLVED": UNKNOWN}[expected]
    _assert_one_obligation(direction.evaluate(obs), outcome, (state, readable))


# --------------------------------------------------------------------------- 3.6 / 3.7 / 3.8 Integrity


def _parent(pid: str, state: str) -> dict:
    return {
        "parent_id": pid, "kind": "github_actions_workflow_run", "name": "ci", "event": "push",
        "current_attempt": 1, "current_state": state, "attempts_observed": [{"attempt": 1, "state": state}],
        "attempts_complete": True, "history_state": "", "url": None,
    }


def _revision(sha: str, day: int, state: str | None) -> dict:
    parents = [_parent(f"github_actions:workflow_run:{sha}", state)] if state else []
    history = "FAILURE_OBSERVED" if state == "VERIFY_FAIL" else "PASS_ONLY_OBSERVED" if state == "VERIFY_PASS" else "NO_DECISIVE_OBSERVED"
    for parent in parents:
        parent["history_state"] = history
    contribution = {"FAILURE_OBSERVED": "VERIFY_FAIL", "PASS_ONLY_OBSERVED": "VERIFY_PASS"}.get(history)
    return {
        "revision": sha, "committed_at": f"2026-08-{day:02d}T10:00:00Z" if day > 27 else f"2026-09-{day:02d}T10:00:00Z",
        "parents": parents, "current_verdict": state, "history_state": history, "historical_contribution": contribution,
        "history_provenance": "ATTEMPT_LEVEL" if parents else None, "history_complete": True,
    }


def _integrity(configured, revisions, series_token="CF"):
    obs = _obs()
    if configured is not None:
        _put(obs, integrity.CONFIGURED, "CF", configured, "boolean")
    _put(obs, integrity.REVISIONS, series_token, revisions, "series")
    return integrity.evaluate(obs)


def _history(n: int, f: int) -> list[dict]:
    return [_revision(f"d{i}", 1 + i, "VERIFY_FAIL" if i < f else "VERIFY_PASS") for i in range(n)]


INTEGRITY_REGIONS = [(n, f) for n in range(0, 7) for f in range(0, n + 1)]


@pytest.mark.parametrize("n, f", INTEGRITY_REGIONS)
def test_t9_gap_integrity_unresolved_band_001(n, f):
    """3.6: a newest VERIFY_UNRESOLVED names FAILING only where the established predicate already holds."""
    revisions = _history(n, f) + [_revision("newest", 9, "VERIFY_UNRESOLVED")]
    established = n >= 4 and 4 * f >= n
    expected = ("DEGRADED", "FAILING", "EXACT", None) if established else UNKNOWN
    _assert_one_obligation(_integrity(True, revisions), expected, (n, f))


@pytest.mark.parametrize("n, f", INTEGRITY_REGIONS)
def test_t9_gap_integrity_partial_superset_001(n, f):
    """3.7, the false gap: a PARTIAL required series is UNKNOWN with no band and no possible_bands, whatever it holds."""
    revisions = _history(n, f) + [_revision("newest", 9, "VERIFY_UNRESOLVED")]
    _assert_one_obligation(_integrity(True, revisions, "PARTIAL"), UNKNOWN, (n, f))
    _assert_one_obligation(_integrity(True, _history(n, f), "PARTIAL"), UNKNOWN, (n, f, "decided"))


@pytest.mark.parametrize("states", [("NON_VERIFY_TERMINAL",), ("NOT_EXECUTED",), ("NOT_EXECUTED", "NON_VERIFY_TERMINAL"), (None, "NOT_EXECUTED")])
def test_t9_gap_integrity_unconfigured_recent_001(states):
    """3.8: positively unconfigured with only non-decisive recent evidence is exactly UNINSTRUMENTED, the evidence kept."""
    revisions = [_revision(f"r{i}", 3 + i, state) for i, state in enumerate(states)]
    result = _integrity(False, revisions)
    _assert_one_obligation(result, ("AVAILABLE", "UNINSTRUMENTED", "EXACT", None), states)
    assert "CI_UNINSTRUMENTED_WITH_RECENT_NONDECISIVE_HISTORY" in result.diagnostics
    _assert_one_obligation(_integrity(True, revisions), ("AVAILABLE", "NO_DECISIVE_RUNS", "EXACT", None), (states, "configured"))
    newest_unknown = revisions + [_revision("newest", 9, "UNKNOWN")]
    _assert_one_obligation(_integrity(False, newest_unknown), UNKNOWN, (states, "newest UNKNOWN"))


def test_t9_section_4_unknown_history_outranks_the_unresolved_failing_branch():
    """Section 4: unknown history is never routed through a conservative branch to obtain a band."""
    suite = {
        "parent_id": "github_checks:check_suite:1", "kind": "github_check_suite", "name": "app", "event": None,
        "current_attempt": None, "current_state": "VERIFY_PASS", "attempts_observed": [{"attempt": None, "state": "VERIFY_PASS"}],
        "attempts_complete": False, "history_state": "UNKNOWN_HISTORY", "url": None,
    }
    unknown_revision = {
        "revision": "suite", "committed_at": "2026-09-07T10:00:00Z", "parents": [suite], "current_verdict": "VERIFY_PASS",
        "history_state": "UNKNOWN_HISTORY", "historical_contribution": None, "history_provenance": "PARENT_LEVEL_ONLY", "history_complete": False,
    }
    established = _history(6, 3) + [unknown_revision, _revision("newest", 9, "VERIFY_UNRESOLVED")]
    assert _outcome(_integrity(True, _history(6, 3) + [_revision("newest", 9, "VERIFY_UNRESOLVED")]))[1] == "FAILING"
    _assert_one_obligation(_integrity(True, established), UNKNOWN, "established FAILING beside unknown history")


# --------------------------------------------------------------------------- 3.9 Debt partial bound

DEBT_CAPABILITIES = ("CONFIGURED", "UNCONFIGURED", "UNKNOWN", "FORBIDDEN", "STALE")
DEBT_CELLS = list(itertools.product(DEBT_CAPABILITIES, TOKENS, (0, 3)))


def _debt_expected(capability: str, token: str, confirmed: int):
    if capability == "UNCONFIGURED":
        return ("AVAILABLE", "UNINSTRUMENTED", "EXACT", None)
    if capability != "CONFIGURED":
        return UNKNOWN
    if token == "CF":
        return ("AVAILABLE", "PRESENT" if confirmed else "CLEAR", "EXACT", None)
    if token == "PARTIAL":
        return ("DEGRADED", "PRESENT", "EXACT", None) if confirmed else UNKNOWN
    return UNKNOWN


@pytest.mark.parametrize("capability, token, confirmed", DEBT_CELLS)
def test_t9_gap_debt_partial_bound_001(capability, token, confirmed):
    obs = _obs()
    if capability in ("CONFIGURED", "UNCONFIGURED"):
        _put(obs, debt.CAPABILITY, "CF", capability, "enum")
    elif capability == "STALE":
        _put(obs, debt.CAPABILITY, "STALE", "CONFIGURED", "enum")
    else:
        _put(obs, debt.CAPABILITY, capability, None, "enum")
    _put(obs, debt.MAPPING, "CF", {"source": "labels", "labels": ["debt"], "mapping_version": "1"}, "record")
    _put(obs, debt.OPEN, token, confirmed)
    result = debt.evaluate(obs)
    _assert_one_obligation(result, _debt_expected(capability, token, confirmed), (capability, token, confirmed))
    assert result.band != "ACCUMULATED"


def test_t9_generator_covers_every_family():
    """The generator is finite and names every former gap family: nine identifiers, none left without cells."""
    families = {
        "T9-GAP-HORIZON-PARTIAL-BOUND-001": len(HORIZON_CELLS),
        "T9-GAP-CLUTTER-UNAVAILABLE-COMPONENT-001": len(CLUTTER_CELLS),
        "T9-GAP-CLUTTER-PARTIAL-FORCED-BOUND-001": len(CLUTTER_CELLS),
        "T9-GAP-DIRECTION-PARTIAL-LINKAGE-001": len(DIRECTION_CELLS),
        "T9-GAP-DIRECTION-UNRESOLVED-TARGET-001": len(REFERENCE_STATES) * 2,
        "T9-GAP-INTEGRITY-UNRESOLVED-BAND-001": len(INTEGRITY_REGIONS),
        "T9-GAP-INTEGRITY-PARTIAL-SUPERSET-001": len(INTEGRITY_REGIONS),
        "T9-GAP-INTEGRITY-UNCONFIGURED-RECENT-001": 4,
        "T9-GAP-DEBT-PARTIAL-BOUND-001": len(DEBT_CELLS),
    }
    assert len(families) == 9 and all(count > 0 for count in families.values())
