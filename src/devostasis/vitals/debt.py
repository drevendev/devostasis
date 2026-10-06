"""DEBT: explicitly registered unresolved technical-maintenance obligations.

Debt never infers itself from age, TODO text, lint output or issue prose. It
exists only through an explicit, versioned mapping (for example issue labels)
and without an accepted calibrated policy its bands are PRESENT, CLEAR and
UNINSTRUMENTED plus raw diagnostics (PV-VITALS-V1-002).

Rule ``debt.bands.v2`` adopts **PV-DEBT-PARTIAL-001** (accepted by
PV-REV-DEBT-PARTIAL-001, DEBT-PARTIAL-01..16). A configured register whose
enumeration is PARTIAL is an observed subset: its open count is a lower bound,
admitted only with the observed-subset proof of PV-REV-PR-031-003 (issue #39).
With at least one confirmed open item every completion of the missing items
is still PRESENT, so the result is ``DEGRADED / PRESENT / EXACT``: the band is
exact, the acquisition is not, and neither the count nor any severity is
claimed. With none confirmed, completions reach both CLEAR and PRESENT, and
Debt declares no order between them, so the result is ``UNKNOWN`` with the
partial receipt kept visible. A partial zero is never CLEAR, and PARTIAL
evidence never establishes UNINSTRUMENTED, which needs positive absence of
configured debt authority.
"""

from __future__ import annotations

from typing import Any

from ..observations import FRESH, PARTIAL, ObservationSet, subset_count_problem
from .common import (
    EVAL_AVAILABLE,
    EVAL_DEGRADED,
    EVAL_UNKNOWN,
    SEM_EXACT,
    VitalResult,
    as_int,
    input_meta,
    unknown_result,
)

VITAL_ID = "debt"
VITAL_VERSION = "PV-VITALS-V1-002/debt"
RULE_ID = "debt.bands.v2"
PARTIAL_RULE = "PV-DEBT-PARTIAL-001"
BANDS = ["UNINSTRUMENTED", "CLEAR", "PRESENT"]

CAPABILITY = "debt.registry.capability"
OPEN = "debt.items.open_count"
STALE = "debt.items.open_stale_count_30d"
CLOSED = "debt.items.closed_count_28d"
MAPPING = "debt.mapping"
IDS = [CAPABILITY, OPEN, STALE, CLOSED, MAPPING]

SHARED = ["EXPLICIT_DEBT_REGISTER", "FORGE_INVENTORY"]
GROUPS = ["DEBT_CLUTTER_MAINTENANCE"]

CAP_CONFIGURED = "CONFIGURED"
CAP_UNCONFIGURED = "UNCONFIGURED"

PARTIAL_ENUMERATION = "DEBT_PARTIAL_ENUMERATION"
LOWER_BOUND = "DEBT_CONFIRMED_OPEN_LOWER_BOUND"
FORCED_PRESENT = "DEBT_BAND_FORCED_PRESENT_BY_CONFIRMED_OPEN"


def _result(obs: ObservationSet, band: str | None, status: str, semantics: str | None, derived: dict, explanation: str, diagnostics: list[str]) -> VitalResult:
    return VitalResult(
        vital_id=VITAL_ID,
        vital_version=VITAL_VERSION,
        rule_id=RULE_ID,
        band=band,
        evaluation_status=status,
        band_semantics=semantics,
        possible_bands=None,
        inputs=input_meta(obs, IDS),
        derived=derived,
        shared_signal_groups=SHARED,
        dependency_group_ids=GROUPS,
        diagnostics=diagnostics,
        explanation=explanation,
    )


def _mapping_version(mapping: Any) -> str:
    return mapping.get("mapping_version") if isinstance(mapping, dict) else "n/a"


def _partial_receipt(obs: ObservationSet, item: Any) -> dict[str, Any]:
    """What the incomplete enumeration was: its reason and the inventory it was counted over."""
    sources = (item.evidence_ref or {}).get("derived_from") if isinstance(item.evidence_ref, dict) else None
    source = obs.get(sources[0]) if isinstance(sources, list) and sources else None
    return {
        "status": item.status,
        "reason_code": item.reason_code,
        "source": source.observation_id if source is not None else None,
        "source_reason_code": source.reason_code if source is not None else None,
    }


def evaluate(obs: ObservationSet) -> VitalResult:
    if not obs.is_good(CAPABILITY):
        # DEBT-PARTIAL-08: uncertain authority is never inferred from records.
        return unknown_result(
            VITAL_ID, VITAL_VERSION, RULE_ID, obs, IDS,
            [f"MISSING_REQUIRED:{CAPABILITY}:{obs.status_of(CAPABILITY)}/{obs.freshness_of(CAPABILITY)}"],
            SHARED, GROUPS,
        )
    capability = obs.value_of(CAPABILITY)
    mapping = obs.value_of(MAPPING) if obs.is_good(MAPPING) else None
    if capability == CAP_UNCONFIGURED:
        # DEBT-PARTIAL-07: positive absence of configured debt authority.
        return _result(
            obs, "UNINSTRUMENTED", EVAL_AVAILABLE, SEM_EXACT,
            {"capability": capability, "mapping": None},
            "No debt register or category mapping is configured; debt is not instrumented.",
            [],
        )
    stale = obs.value_of(STALE) if obs.is_good(STALE) else None
    closed = obs.value_of(CLOSED) if obs.is_good(CLOSED) else None
    derived_base = {"capability": capability, "mapping": mapping, "open_stale_count_30d": stale, "closed_count_28d": closed}

    if obs.is_good(OPEN):
        open_count = as_int(obs.value_of(OPEN))
        band = "PRESENT" if open_count > 0 else "CLEAR"
        derived = dict(derived_base, open_count=open_count)
        explanation = f"{open_count} open registered debt items under mapping version {_mapping_version(mapping)}."
        return _result(obs, band, EVAL_AVAILABLE, SEM_EXACT, derived, explanation, [])

    open_obs = obs.get(OPEN)
    if open_obs is None or open_obs.status != PARTIAL or open_obs.freshness != FRESH or not open_obs.has_value:
        # DEBT-PARTIAL-13: stale, unavailable, forbidden, unknown or errored
        # configured evidence stays outside the partial repair.
        return unknown_result(
            VITAL_ID, VITAL_VERSION, RULE_ID, obs, IDS,
            [f"MISSING_REQUIRED:{OPEN}:{obs.status_of(OPEN)}/{obs.freshness_of(OPEN)}"],
            SHARED, GROUPS,
            explanation="Debt is configured but its register could not be observed completely; CLEAR is never assumed.",
        )
    problem = subset_count_problem(open_obs)
    if problem is not None:
        # Issue #39: status PARTIAL alone proves nothing about the value.
        return unknown_result(
            VITAL_ID, VITAL_VERSION, RULE_ID, obs, IDS,
            [f"MISSING_REQUIRED:{OPEN}:{PARTIAL}/{open_obs.freshness}", f"PARTIAL_COUNT_NOT_A_LOWER_BOUND:{OPEN}:{problem}"],
            SHARED, GROUPS,
            explanation="Debt is configured, but the partial open count does not prove it is a count over returned register items; no bound is read from it.",
        )
    if mapping is None:
        # A PD1 result must name the authority it counted under (section 5).
        return unknown_result(
            VITAL_ID, VITAL_VERSION, RULE_ID, obs, IDS,
            [f"MISSING_REQUIRED:{MAPPING}:{obs.status_of(MAPPING)}/{obs.freshness_of(MAPPING)}"],
            SHARED, GROUPS,
            explanation="Debt is configured and partially enumerated, but the mapping the items were counted under is not observed; no band is claimed.",
        )

    confirmed = as_int(open_obs.value)
    derived = dict(
        derived_base,
        open_count=confirmed,
        open_count_semantics="LOWER_BOUND",
        confirmed_open_count=confirmed,
        partial_enumeration=_partial_receipt(obs, open_obs),
        partial_rule=PARTIAL_RULE,
    )
    diagnostics = [PARTIAL_ENUMERATION, f"{LOWER_BOUND}:{confirmed}"]
    if confirmed > 0:
        # PD1: a confirmed current open item survives every completion.
        return _result(
            obs, "PRESENT", EVAL_DEGRADED, SEM_EXACT, derived,
            f"At least {confirmed} open registered debt items were observed under mapping version {_mapping_version(mapping)}; "
            "the register enumeration is incomplete, so the count is a lower bound and the band is PRESENT in every completion.",
            diagnostics + [FORCED_PRESENT],
        )
    # PD0: zero confirmed open items is absence of proof, not proof of absence.
    return _result(
        obs, None, EVAL_UNKNOWN, None, derived,
        "The debt register enumeration is incomplete and returned no open item; the missing items could make Debt CLEAR or PRESENT, and no band is claimed.",
        diagnostics,
    )
