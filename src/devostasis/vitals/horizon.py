"""HORIZON: how much future work is explicitly declared in planning metadata.

Horizon measures forward visibility, not roadmap quality. EXTENDED is not
better than VISIBLE; UNDECLARED may be entirely appropriate.

Rule ``horizon.bands.v2`` adopts **PV-HORIZON-PARTIAL-001** (accepted by
PV-REV-HORIZON-PARTIAL-001, HOR-PARTIAL-01..16) on top of the V1 band table.
When the target enumeration is incomplete, its counts are lower bounds over
the returned targets (each carrying the observed-subset proof of
PV-REV-PR-031-003), and every admissible completion of the missing targets is
classified with the unchanged predicates. Horizon declares no order, so a
completion set that reaches several bands names none of them (``UNKNOWN``);
only a set of one band is a band, ``DEGRADED / <band> / EXACT``. Under an
ordinary partial enumeration that happens exactly when a returned open target
already lies beyond the 28-day frame, because adding targets cannot remove it
(existential monotonicity, not an ordering). A partial zero is never
UNDECLARED. Counts that contradict each other are refused before
classification (HOR-PARTIAL-15).
"""

from __future__ import annotations

from typing import Any

from ..observations import FRESH, PARTIAL, ObservationSet, subset_count_problem
from .common import (
    EVAL_AVAILABLE,
    EVAL_DEGRADED,
    EVAL_UNKNOWN,
    SEM_EXACT,
    SEM_SUPERSET,
    InadmissibleEvidence,
    VitalResult,
    as_int,
    input_meta,
    unknown_result,
)

VITAL_ID = "horizon"
VITAL_VERSION = "PV-VITALS-V1-002/horizon"
RULE_ID = "horizon.bands.v2"
PARTIAL_RULE = "PV-HORIZON-PARTIAL-001"
BANDS = ["UNDECLARED", "DECLARED", "VISIBLE", "EXTENDED"]

CAPABILITY = "planning.explicit_targets.capability"
OPEN = "planning.explicit_targets.open_count"
FUTURE = "planning.explicit_targets.open_with_future_boundary_count"
BEYOND = "planning.explicit_targets.open_beyond_28d_count"
NEAREST = "planning.explicit_targets.nearest_future_boundary_days"
IDS = [CAPABILITY, OPEN, FUTURE, BEYOND, NEAREST]
COUNTS = (OPEN, FUTURE, BEYOND)

SHARED = ["PLANNING_TARGETS"]
GROUPS = ["HORIZON_DIRECTION_PLANNING"]

CAP_SUPPORTED = "SUPPORTED"
CAP_SUPPORTED_UNUSED = "SUPPORTED_UNUSED"
CAP_UNSUPPORTED = "UNSUPPORTED"

BAND_INVARIANT = "HORIZON_PARTIAL_BAND_INVARIANT"
AMBIGUOUS = "HORIZON_PARTIAL_AMBIGUOUS"
COUNTS_INCONSISTENT = "HORIZON_COUNTS_INCONSISTENT"


def classify(open_count: int, future: int, beyond: int) -> str:
    """The V1 first-match table over complete counts."""
    if beyond > 0:
        return "EXTENDED"
    if future > 0:
        return "VISIBLE"
    if open_count > 0:
        return "DECLARED"
    return "UNDECLARED"


def reachable_bands(open_count: int, future: int, beyond: int, exact: tuple[bool, bool, bool]) -> list[str]:
    """Every band some admissible completion reaches, in canonical order.

    A count that is exact keeps its value; a lower bound may grow. Every
    completion keeps beyond <= future <= open. The table reads only whether
    each count is positive, so raising a lower bound by one, or to the count
    it must cover, reaches every region a larger completion could.
    """
    exact_open, exact_future, exact_beyond = exact

    def grow(value: int, is_exact: bool, floor: int = 0) -> set[int]:
        if is_exact:
            return {value}
        return {max(value, floor), max(value, floor) + 1}

    reached: set[str] = set()
    for b in grow(beyond, exact_beyond):
        for f in grow(future, exact_future, b):
            for o in grow(open_count, exact_open, f):
                if b <= f <= o:
                    reached.add(classify(o, f, b))
    return [band for band in BANDS if band in reached]


def _result(
    obs: ObservationSet,
    band: str | None,
    status: str,
    semantics: str | None,
    possible: list[str] | None,
    derived: dict[str, Any],
    explanation: str,
    diagnostics: list[str],
) -> VitalResult:
    return VitalResult(
        vital_id=VITAL_ID,
        vital_version=VITAL_VERSION,
        rule_id=RULE_ID,
        band=band,
        evaluation_status=status,
        band_semantics=semantics,
        possible_bands=possible,
        inputs=input_meta(obs, IDS),
        derived=derived,
        shared_signal_groups=SHARED,
        dependency_group_ids=GROUPS,
        diagnostics=diagnostics,
        explanation=explanation,
    )


def _subset_lower_bound(obs: ObservationSet, oid: str) -> str | None:
    """None when a PARTIAL count is a fresh observed-subset lower bound, else why it is not."""
    item = obs.get(oid)
    if item is None or item.status != PARTIAL or item.freshness != FRESH:
        return f"MISSING_REQUIRED:{oid}:{obs.status_of(oid)}/{obs.freshness_of(oid)}"
    problem = subset_count_problem(item)
    return None if problem is None else f"PARTIAL_COUNT_NOT_A_LOWER_BOUND:{oid}:{problem}"


def _checked(values: dict[str, int]) -> None:
    """HOR-PARTIAL-15: a derived tuple no target population can produce is refused, not compensated."""
    open_count, future, beyond = values[OPEN], values[FUTURE], values[BEYOND]
    if min(open_count, future, beyond) < 0 or not beyond <= future <= open_count:
        raise InadmissibleEvidence(
            COUNTS_INCONSISTENT,
            f"open {open_count}, with a future boundary {future}, beyond 28 days {beyond}: every target beyond the frame has a future boundary and every such target is open",
        )


def evaluate(obs: ObservationSet) -> VitalResult:
    if not obs.is_good(CAPABILITY):
        # HOR-PARTIAL-06: support versus positive absence is not established.
        return unknown_result(
            VITAL_ID, VITAL_VERSION, RULE_ID, obs, IDS,
            [f"MISSING_REQUIRED:{CAPABILITY}:{obs.status_of(CAPABILITY)}/{obs.freshness_of(CAPABILITY)}"],
            SHARED, GROUPS,
        )
    capability = obs.value_of(CAPABILITY)
    if capability in (CAP_UNSUPPORTED, CAP_SUPPORTED_UNUSED):
        return _result(
            obs,
            "UNDECLARED",
            EVAL_AVAILABLE,
            SEM_EXACT,
            None,
            {"capability": capability, "open_count": 0, "open_with_future_boundary_count": 0, "open_beyond_28d_count": 0},
            "No explicit planning targets are declared for this repository.",
            [f"PLANNING_CAPABILITY:{capability}"],
        )

    problems = []
    for oid in COUNTS:
        if not obs.is_good(oid):
            problem = _subset_lower_bound(obs, oid)
            if problem is not None:
                problems.append(problem)
    if problems:
        return unknown_result(VITAL_ID, VITAL_VERSION, RULE_ID, obs, IDS, problems, SHARED, GROUPS)

    values = {oid: as_int(obs.value_of(oid)) for oid in COUNTS}
    _checked(values)
    open_count, future, beyond = values[OPEN], values[FUTURE], values[BEYOND]
    nearest = obs.value_of(NEAREST) if obs.is_good(NEAREST) else None
    derived: dict[str, Any] = {
        "capability": capability,
        "open_count": open_count,
        "open_with_future_boundary_count": future,
        "open_beyond_28d_count": beyond,
        "nearest_future_boundary_days": nearest,
    }
    exact = tuple(obs.is_good(oid) for oid in COUNTS)
    if all(exact):
        band = classify(open_count, future, beyond)
        explanation = f"{open_count} open planning targets, {future} with a future boundary, {beyond} reaching beyond 28 days."
        return _result(obs, band, EVAL_AVAILABLE, SEM_EXACT, None, derived, explanation, [])

    # PV-HORIZON-PARTIAL-001: the counts of a partial enumeration are lower bounds.
    for oid, is_exact in zip(COUNTS, exact):
        if not is_exact:
            derived[f"{oid.rsplit('.', 1)[1]}_semantics"] = "LOWER_BOUND"
    reachable = reachable_bands(open_count, future, beyond, exact)
    derived["reachable_bands"] = reachable
    derived["partial_rule"] = PARTIAL_RULE
    partial = [f"PARTIAL_ENUMERATION:{oid}:{obs.get(oid).reason_code or 'INCOMPLETE'}" for oid, is_exact in zip(COUNTS, exact) if not is_exact]
    if len(reachable) == 1:
        band = reachable[0]
        derived["possible_bands_semantics"] = SEM_SUPERSET
        return _result(
            obs, band, EVAL_DEGRADED, SEM_EXACT, [band], derived,
            f"At least {open_count} open planning targets were returned by an incomplete enumeration, {beyond} of them beyond 28 days; every completion of the missing targets is {band}.",
            partial + [BAND_INVARIANT],
        )
    return _result(
        obs, None, EVAL_UNKNOWN, None, None, derived,
        f"At least {open_count} open planning targets were returned by an incomplete enumeration; the missing ones could make Horizon {', '.join(reachable)}, and Horizon declares no order to choose one.",
        partial + [AMBIGUOUS],
    )
