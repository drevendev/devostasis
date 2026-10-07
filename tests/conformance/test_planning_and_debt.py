"""Horizon, Direction and Debt (V1-03..V1-07, V1-13..V1-15)."""

import pytest

from devostasis.observations import FORBIDDEN, PARTIAL
from devostasis.vitals import debt, direction, horizon
from helpers import add, debt_inputs, direction_inputs, obs_set, planning_inputs


def test_horizon_bands():
    for capability, kwargs, expected in (
        ("SUPPORTED_UNUSED", {}, "UNDECLARED"),
        ("UNSUPPORTED", {}, "UNDECLARED"),
        ("SUPPORTED", {"open_count": 0}, "UNDECLARED"),
        ("SUPPORTED", {"open_count": 2}, "DECLARED"),
        ("SUPPORTED", {"open_count": 2, "future": 1, "nearest": 10}, "VISIBLE"),
        ("SUPPORTED", {"open_count": 2, "future": 1, "beyond": 1, "nearest": 40}, "EXTENDED"),
    ):
        obs = obs_set()
        planning_inputs(obs, capability, **kwargs)
        result = horizon.evaluate(obs)
        assert result.band == expected and result.evaluation_status == "AVAILABLE", (capability, kwargs)


def test_v1_05_forbidden_planning_enumeration_is_unknown_not_undeclared():
    obs = obs_set()
    add(obs, "planning.explicit_targets.capability", status=FORBIDDEN, reason_code="FORBIDDEN", value_type="enum")
    direction_inputs(obs, active=3)
    assert horizon.evaluate(obs).evaluation_status == "UNKNOWN"
    assert direction.evaluate(obs).evaluation_status == "UNKNOWN"


def test_direction_bands():
    obs = obs_set()
    direction_inputs(obs, active=0)
    assert direction.evaluate(obs).band == "NO_ACTIVE_CHANGE"

    obs = obs_set()
    planning_inputs(obs, "SUPPORTED_UNUSED")
    direction_inputs(obs, active=4)
    assert direction.evaluate(obs).band == "UNDECLARED"

    for linked, expected in ((1, "SCATTERED"), (2, "MIXED"), (3, "MIXED"), (4, "FULLY_LINKED")):
        obs = obs_set()
        planning_inputs(obs, "SUPPORTED", open_count=1)
        direction_inputs(obs, active=4, linked=linked, links={"1": linked})
        assert direction.evaluate(obs).band == expected, linked


def test_v1_14_mass_linking_yields_neutral_fully_linked_with_diagnostic():
    obs = obs_set()
    planning_inputs(obs, "SUPPORTED", open_count=1)
    direction_inputs(obs, active=10, linked=10, links={"7": 10})
    result = direction.evaluate(obs)
    assert result.band == "FULLY_LINKED" and "ALL_LINKS_TO_SINGLE_TARGET" in result.diagnostics
    assert "ALIGNED" not in result.to_dict()["explanation"]


def test_direction_missing_linkage_is_unknown():
    obs = obs_set()
    planning_inputs(obs, "SUPPORTED", open_count=1)
    direction_inputs(obs, active=3)
    assert direction.evaluate(obs).evaluation_status == "UNKNOWN"


def test_debt_bands():
    obs = obs_set()
    debt_inputs(obs, "UNCONFIGURED")
    assert debt.evaluate(obs).band == "UNINSTRUMENTED"
    obs = obs_set()
    debt_inputs(obs, "CONFIGURED", open_count=0, stale=0, closed=1)
    assert debt.evaluate(obs).band == "CLEAR"
    obs = obs_set()
    debt_inputs(obs, "CONFIGURED", open_count=2, stale=0, closed=0)
    assert debt.evaluate(obs).band == "PRESENT"


def test_v1_13_no_calibrated_policy_keeps_large_debt_as_present():
    obs = obs_set()
    debt_inputs(obs, "CONFIGURED", open_count=37, stale=20, closed=0)
    result = debt.evaluate(obs)
    assert result.band == "PRESENT" and result.derived["open_stale_count_30d"] == 20
    assert "ACCUMULATED" not in {result.band}


def test_configured_debt_with_forbidden_register_is_unknown_never_clear():
    obs = obs_set()
    add(obs, "debt.registry.capability", "CONFIGURED", "enum")
    add(obs, "debt.items.open_count", status=FORBIDDEN, reason_code="FORBIDDEN")
    result = debt.evaluate(obs)
    assert result.band is None and result.evaluation_status == "UNKNOWN"


SUBSET = {"complete": False, "value_semantics": "OBSERVED_SUBSET_COUNT"}
MAPPING = {"source": "labels", "labels": ["debt"], "mapping_version": "1"}


def test_partial_register_with_observed_items_is_degraded_present():
    """PD1 of PV-DEBT-PARTIAL-001: the band is exact, the acquisition is not."""
    obs = obs_set()
    add(obs, "debt.registry.capability", "CONFIGURED", "enum")
    add(obs, "debt.mapping", MAPPING, "record")
    add(obs, "debt.items.open_count", 3, status=PARTIAL, reason_code="PAGINATION_CAPPED", coverage=SUBSET)
    result = debt.evaluate(obs)
    assert (result.band, result.evaluation_status, result.band_semantics, result.possible_bands) == ("PRESENT", "DEGRADED", "EXACT", None)
    assert result.derived["open_count_semantics"] == "LOWER_BOUND" and result.derived["confirmed_open_count"] == 3


def test_a_stale_partial_register_proves_nothing_about_now():
    """vitals.md: configured debt evidence that is stale yields UNKNOWN; a fresh partial one is a lower bound."""
    for freshness, expected in (("FRESH", "PRESENT"), ("STALE", None), ("UNKNOWN", None)):
        obs = obs_set()
        add(obs, "debt.registry.capability", "CONFIGURED", "enum")
        add(obs, "debt.mapping", MAPPING, "record")
        add(obs, "debt.items.open_count", 2, status=PARTIAL, freshness=freshness, reason_code="PAGINATION_CAPPED", coverage=SUBSET)
        result = debt.evaluate(obs)
        assert result.band == expected, freshness


@pytest.mark.parametrize("coverage", [None, {"complete": False}, {"complete": False, "value_semantics": "ESTIMATE"}, {"complete": True, "value_semantics": "OBSERVED_SUBSET_COUNT"}, "not a record"])
def test_a_partial_debt_count_without_the_subset_proof_is_not_a_lower_bound(coverage):
    """Issue #39: status PARTIAL proves nothing about the value; only a proven observed-subset count is a floor."""
    obs = obs_set()
    add(obs, "debt.registry.capability", "CONFIGURED", "enum")
    add(obs, "debt.mapping", MAPPING, "record")
    add(obs, "debt.items.open_count", 4, status=PARTIAL, reason_code="PAGINATION_CAPPED", coverage=coverage)
    result = debt.evaluate(obs)
    assert (result.band, result.evaluation_status) == (None, "UNKNOWN")
    assert any(code.startswith("PARTIAL_COUNT_NOT_A_LOWER_BOUND:debt.items.open_count") for code in result.diagnostics)
