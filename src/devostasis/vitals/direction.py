"""DIRECTION: explicit traceability of active change work to declared targets.

FULLY_LINKED is neutral exact traceability; it is not strategy, prioritization
or target quality, and renderers must never alias it to ALIGNED or ON_TRACK.

Rule ``direction.bands.v2`` adopts two accepted repairs on top of the V1 band
table, neither of which moves a threshold or the 28-day frame:

* **PV-REV-DIRECTION-CLOSED-TARGET-001** (DIR-CLOSED-01..09): linkage is
  state-neutral. An active change request linked to a declared target stays
  linked when the target closes, because closing the target the work delivered
  must not un-trace the work (calibration finding 9). Horizon still counts open
  targets only, so the two Vitals may legitimately diverge.
* **PV-DIRECTION-INCOMPLETE-001** (DIR-INCOMPLETE-01..16): over a complete
  active population of N change requests, each one is LINKED, UNLINKED or
  UNRESOLVED (L + U + R = N). Every unresolved one may complete either way, so
  the linked count k ranges over L..L+R and each k is mapped through the
  unchanged predicates (k = N FULLY_LINKED, 2k >= N MIXED, else SCATTERED).
  With R = 0 the band is exact as before. With R > 0 a band that every
  completion reaches is ``DEGRADED / <band> / EXACT``; completions that cross a
  boundary are ``UNKNOWN`` with no band, because Direction declares no order to
  pick a representative by. A singleton FULLY_LINKED is impossible with R > 0.

The open-target count the V1 rule classified by is still derived, for
presentation only; the judgement forbids it as the classifier's authority.
"""

from __future__ import annotations

from typing import Any

from ..observations import ObservationSet
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
from .horizon import CAP_SUPPORTED_UNUSED, CAP_UNSUPPORTED, CAPABILITY

VITAL_ID = "direction"
VITAL_VERSION = "PV-VITALS-V1-002/direction"
RULE_ID = "direction.bands.v2"
CLOSED_TARGET_RULE = "PV-REV-DIRECTION-CLOSED-TARGET-001"
INCOMPLETE_RULE = "PV-DIRECTION-INCOMPLETE-001"
BANDS = ["NO_ACTIVE_CHANGE", "UNDECLARED", "SCATTERED", "MIXED", "FULLY_LINKED"]

ACTIVE = "planning.linkage.active_change_requests_count_28d"
LINKED = "planning.linkage.active_change_requests_linked_count_28d"
UNLINKED = "planning.linkage.active_change_requests_unlinked_count_28d"
UNRESOLVED = "planning.linkage.active_change_requests_unresolved_count_28d"
UNRESOLVED_ITEMS = "planning.linkage.unresolved_change_requests_28d"
MISSING_REFS = "planning.linkage.missing_target_reference_count_28d"
TARGET_LINKS = "planning.linkage.links_per_target_28d"
# Presentation only since this rule version: never read to classify.
LINKED_TO_OPEN = "planning.linkage.active_change_requests_linked_to_open_target_count_28d"
IDS = [ACTIVE, LINKED, UNLINKED, UNRESOLVED, CAPABILITY, TARGET_LINKS, MISSING_REFS, UNRESOLVED_ITEMS]

SHARED = ["PLANNING_TARGETS", "CHANGE_REQUEST_ACTIVITY"]
GROUPS = ["HORIZON_DIRECTION_PLANNING", "DIRECTION_PULSE_ACTIVITY"]

BAND_INVARIANT = "DIRECTION_INCOMPLETE_BAND_INVARIANT"
AMBIGUOUS = "DIRECTION_INCOMPLETE_AMBIGUOUS"
REFERENCE_MISSING = "DIRECTION_TARGET_REFERENCE_MISSING"
SINGLE_TARGET = "ALL_LINKS_TO_SINGLE_TARGET"
COUNTS_INCONSISTENT = "DIRECTION_LINKAGE_COUNTS_INCONSISTENT"


def band_for(linked: int, active: int) -> str:
    """The V1 predicates over complete linkage, with unlinked = active - linked."""
    if linked == active:
        return "FULLY_LINKED"
    if 2 * linked >= active:
        return "MIXED"
    return "SCATTERED"


def reachable_bands(linked: int, unresolved: int, active: int) -> list[str]:
    """Every band some completion of the unresolved change requests reaches, in canonical order."""
    reached = {band_for(k, active) for k in range(linked, linked + unresolved + 1)}
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


def _missing(obs: ObservationSet, ids: list[str]) -> list[str]:
    return [f"MISSING_REQUIRED:{oid}:{obs.status_of(oid)}/{obs.freshness_of(oid)}" for oid in ids if not obs.is_good(oid)]


def _count(obs: ObservationSet, oid: str) -> int:
    value = as_int(obs.value_of(oid))
    if value < 0:
        raise InadmissibleEvidence(COUNTS_INCONSISTENT, f"{oid} is {value}, a count below zero")
    return value


def evaluate(obs: ObservationSet) -> VitalResult:
    missing = _missing(obs, [ACTIVE])
    if missing:
        return unknown_result(VITAL_ID, VITAL_VERSION, RULE_ID, obs, IDS, missing, SHARED, GROUPS)
    active = _count(obs, ACTIVE)
    if active == 0:
        return _result(obs, "NO_ACTIVE_CHANGE", EVAL_AVAILABLE, SEM_EXACT, None, {"active_change_count_28d": 0}, "No active change requests in the 28-day frame.", [])

    missing = _missing(obs, [CAPABILITY])
    if missing:
        # DIR-INCOMPLETE-13: linkage capability neither positively present nor absent.
        return unknown_result(VITAL_ID, VITAL_VERSION, RULE_ID, obs, IDS, missing, SHARED, GROUPS)
    capability = obs.value_of(CAPABILITY)
    if capability in (CAP_UNSUPPORTED, CAP_SUPPORTED_UNUSED):
        return _result(
            obs,
            "UNDECLARED",
            EVAL_AVAILABLE,
            SEM_EXACT,
            None,
            {"active_change_count_28d": active, "capability": capability},
            f"{active} active change requests, but no explicit planning target or linkage mechanism is declared.",
            [f"PLANNING_CAPABILITY:{capability}"],
        )

    missing = _missing(obs, [LINKED, UNLINKED, UNRESOLVED])
    if missing:
        return unknown_result(VITAL_ID, VITAL_VERSION, RULE_ID, obs, IDS, missing, SHARED, GROUPS)
    linked, unlinked, unresolved = _count(obs, LINKED), _count(obs, UNLINKED), _count(obs, UNRESOLVED)
    if linked + unlinked + unresolved != active:
        # PV-DIRECTION-INCOMPLETE-001 section 7: invalid normalized input, never classified.
        raise InadmissibleEvidence(COUNTS_INCONSISTENT, f"linked {linked} + unlinked {unlinked} + unresolved {unresolved} != active {active}")

    links = obs.value_of(TARGET_LINKS) if obs.is_good(TARGET_LINKS) else None
    missing_refs = as_int(obs.value_of(MISSING_REFS)) if obs.is_good(MISSING_REFS) else None
    derived: dict[str, Any] = {
        "active_change_count_28d": active,
        "linked_active_change_count_28d": linked,
        "unlinked_active_change_count_28d": unlinked,
        "unresolved_active_change_count_28d": unresolved,
        "capability": capability,
        "links_per_target": links,
        "linkage_rule": CLOSED_TARGET_RULE,
    }
    if obs.is_good(LINKED_TO_OPEN):
        derived["linked_to_open_target_count_28d"] = as_int(obs.value_of(LINKED_TO_OPEN))
    if missing_refs is not None:
        derived["missing_target_reference_count_28d"] = missing_refs

    diagnostics: list[str] = []
    if isinstance(links, dict) and len(links) == 1 and linked > 1:
        diagnostics.append(SINGLE_TARGET)
    if missing_refs:
        # DIR-INCOMPLETE-07: a positively missing target is a broken reference, counted unlinked.
        diagnostics.append(f"{REFERENCE_MISSING}:{missing_refs}")

    if unresolved == 0:
        band = band_for(linked, active)
        explanation = f"{linked} of {active} active change requests are explicitly linked to a declared target, open or closed."
        return _result(obs, band, EVAL_AVAILABLE, SEM_EXACT, None, derived, explanation, diagnostics)

    reachable = reachable_bands(linked, unresolved, active)
    derived["reachable_bands"] = reachable
    derived["incomplete_rule"] = INCOMPLETE_RULE
    items = obs.value_of(UNRESOLVED_ITEMS) if obs.is_good(UNRESOLVED_ITEMS) else None
    if isinstance(items, dict):
        derived["unresolved_change_requests"] = items
    if len(reachable) == 1:
        band = reachable[0]
        derived["possible_bands_semantics"] = SEM_SUPERSET
        return _result(
            obs, band, EVAL_DEGRADED, SEM_EXACT, [band], derived,
            f"{linked} of {active} active change requests are linked and {unresolved} unresolved; every completion of the unresolved ones is {band}.",
            diagnostics + [BAND_INVARIANT],
        )
    return _result(
        obs, None, EVAL_UNKNOWN, None, None, derived,
        f"{linked} of {active} active change requests are linked and {unresolved} unresolved; completing them could give {', '.join(reachable)}, and Direction declares no order to choose one.",
        diagnostics + [AMBIGUOUS],
    )
