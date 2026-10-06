"""Inventories to aggregates: windows, exact medians (FLOW-PREC-01/02/07/08), staleness, linkage, debt mapping, planning capability."""

from devostasis import normalize
from devostasis.config import single_project
from devostasis.observations import AVAILABLE, PARTIAL, UNAVAILABLE
from helpers import add, obs_set

NOW = "2026-09-05T12:00:00Z"
COVERAGE = {"open_complete": True, "window_complete": True}


def _crs():
    return [
        {"number": 1, "title": "old open", "state": "OPEN", "created_at": "2026-07-01T00:00:00Z", "updated_at": "2026-08-01T00:00:00Z", "merged_at": None, "closed_at": None, "target_id": None, "target_state": None, "url": "u1"},
        {"number": 2, "title": "fresh open linked", "state": "OPEN", "created_at": "2026-09-01T00:00:00Z", "updated_at": "2026-09-04T00:00:00Z", "merged_at": None, "closed_at": None, "target_id": "5", "target_state": "OPEN", "url": "u2"},
        {"number": 3, "title": "merged fast", "state": "MERGED", "created_at": "2026-09-01T00:00:00Z", "updated_at": "2026-09-01T10:00:00Z", "merged_at": "2026-09-01T10:00:00Z", "closed_at": "2026-09-01T10:00:00Z", "target_id": "5", "target_state": "OPEN", "url": "u3"},
        {"number": 4, "title": "merged slow", "state": "MERGED", "created_at": "2026-08-20T00:00:00Z", "updated_at": "2026-08-30T00:00:00Z", "merged_at": "2026-08-30T00:00:00Z", "closed_at": "2026-08-30T00:00:00Z", "target_id": "9", "target_state": "CLOSED", "url": "u4"},
        {"number": 5, "title": "merged long ago", "state": "MERGED", "created_at": "2026-06-01T00:00:00Z", "updated_at": "2026-06-02T00:00:00Z", "merged_at": "2026-06-02T00:00:00Z", "closed_at": "2026-06-02T00:00:00Z", "target_id": None, "target_state": None, "url": "u5"},
    ]


def _merged(pairs):
    """Merged change requests with the given (created_at, merged_at) pairs, all inside the window."""
    return [
        {"number": i, "title": "m", "state": "MERGED", "created_at": created, "updated_at": merged, "merged_at": merged, "closed_at": merged, "target_id": None, "target_state": None, "url": f"u{i}"}
        for i, (created, merged) in enumerate(pairs, start=1)
    ]


def _derive_merged(pairs):
    obs = obs_set(NOW)
    add(obs, normalize.INV_CRS, _merged(pairs), "series", coverage=COVERAGE)
    normalize.derive(obs, single_project("acme/widget"))
    return obs


def test_change_request_aggregates():
    obs = obs_set(NOW)
    add(obs, normalize.INV_CRS, _crs(), "series", coverage=COVERAGE)
    normalize.derive(obs, single_project("acme/widget"))
    assert obs.value_of("forge.change_requests.open_count") == 2
    assert obs.value_of("forge.change_requests.merged_count_28d") == 2
    assert obs.value_of("forge.change_requests.oldest_open_age_days") == 66
    assert obs.value_of(normalize.MEDIAN_SECONDS) == {"numerator": (10 + 240) * 3600 // 2, "denominator": 1}
    assert obs.value_of(normalize.MEDIAN_HOURS) == (10 + 240) // 2
    assert obs.value_of("forge.change_requests.stale_open_count_14d") == 1
    assert obs.value_of("forge.change_requests.updated_count_28d") == 3
    assert obs.value_of("planning.linkage.active_change_requests_count_28d") == 3
    # Change request 4 delivered target 9, which has closed since; it stays
    # linked (PV-REV-DIRECTION-CLOSED-TARGET-001), and only the presentation
    # count of links to open targets leaves it out.
    assert obs.value_of("planning.linkage.active_change_requests_linked_count_28d") == 3
    assert obs.value_of("planning.linkage.active_change_requests_unlinked_count_28d") == 0
    assert obs.value_of("planning.linkage.active_change_requests_unresolved_count_28d") == 0
    assert obs.value_of("planning.linkage.active_change_requests_linked_to_open_target_count_28d") == 2
    assert obs.get("planning.linkage.active_change_requests_linked_to_open_target_count_28d").notes == normalize.LINKED_TO_OPEN_NOTE
    assert obs.value_of("planning.linkage.links_per_target_28d") == {"5": 2, "9": 1}


def test_flow_prec_01_sub_hour_medians_are_preserved():
    obs = _derive_merged([
        ("2026-09-01T00:00:00Z", "2026-09-01T00:05:00Z"),
        ("2026-09-01T00:00:00Z", "2026-09-01T00:10:00Z"),
        ("2026-09-01T00:00:00Z", "2026-09-01T00:15:00Z"),
    ])
    assert obs.value_of(normalize.MEDIAN_SECONDS) == {"numerator": 600, "denominator": 1}
    assert obs.value_of(normalize.MEDIAN_HOURS) == 0
    hours = obs.get(normalize.MEDIAN_HOURS)
    assert hours.evidence_ref["derived_from"] == [normalize.INV_CRS, normalize.MEDIAN_SECONDS]
    assert hours.notes == normalize.MEDIAN_HOURS_NOTE


def test_flow_prec_02_even_sample_uses_the_exact_arithmetic_mean():
    obs = _derive_merged([
        ("2026-09-01T00:00:00Z", "2026-09-01T00:05:00Z"),
        ("2026-09-01T00:00:00Z", "2026-09-01T00:05:01Z"),
    ])
    assert obs.value_of(normalize.MEDIAN_SECONDS) == {"numerator": 601, "denominator": 2}


def test_flow_prec_07_median_is_invariant_under_permutation():
    pairs = [
        ("2026-09-01T00:00:00Z", "2026-09-01T00:05:00Z"),
        ("2026-09-02T00:00:00Z", "2026-09-02T00:10:00Z"),
        ("2026-09-03T00:00:00Z", "2026-09-03T00:15:00Z"),
        ("2026-09-04T00:00:00Z", "2026-09-04T00:20:00Z"),
    ]
    expected = {"numerator": 750, "denominator": 1}
    assert _derive_merged(pairs).value_of(normalize.MEDIAN_SECONDS) == expected
    assert _derive_merged(list(reversed(pairs))).value_of(normalize.MEDIAN_SECONDS) == expected
    assert _derive_merged([pairs[2], pairs[0], pairs[3], pairs[1]]).value_of(normalize.MEDIAN_SECONDS) == expected


def test_flow_prec_08_fractional_timestamps_are_exact():
    obs = _derive_merged([
        ("2026-09-01T00:00:00Z", "2026-09-01T00:00:01.25Z"),
        ("2026-09-01T00:00:00Z", "2026-09-01T00:00:01.75Z"),
    ])
    assert obs.value_of(normalize.MEDIAN_SECONDS) == {"numerator": 3, "denominator": 2}


def test_partial_open_enumeration_marks_open_aggregates_partial_only():
    obs = obs_set(NOW)
    add(obs, normalize.INV_CRS, _crs(), "series", status=PARTIAL, reason_code="PAGINATION_CAPPED", coverage={"open_complete": False, "window_complete": True})
    normalize.derive(obs, single_project("acme/widget"))
    assert obs.status_of("forge.change_requests.open_count") == PARTIAL
    assert obs.status_of("forge.change_requests.merged_count_28d") == PARTIAL
    assert obs.status_of(normalize.MEDIAN_SECONDS) == PARTIAL


def test_issues_disabled_propagates_unavailable_and_debt_stays_unknown():
    obs = obs_set(NOW)
    add(obs, normalize.INV_ISSUES, status=UNAVAILABLE, value_type="series", reason_code="ISSUES_DISABLED")
    project = single_project("acme/widget", debt={"labels": ["debt"], "mapping_version": "1"})
    normalize.derive(obs, project)
    assert obs.status_of("forge.issues.open_count") == UNAVAILABLE
    assert obs.get("forge.issues.open_count").reason_code == "ISSUES_DISABLED"
    assert obs.value_of("debt.registry.capability") == "CONFIGURED"
    assert obs.status_of("debt.items.open_count") == UNAVAILABLE


def test_issue_and_debt_aggregates():
    issues = [
        {"number": 1, "title": "stale", "state": "OPEN", "created_at": "2026-06-01T00:00:00Z", "updated_at": "2026-07-01T00:00:00Z", "closed_at": None, "labels": ["type:refactor"], "url": "i1"},
        {"number": 2, "title": "fresh", "state": "OPEN", "created_at": "2026-09-01T00:00:00Z", "updated_at": "2026-09-04T00:00:00Z", "closed_at": None, "labels": ["bug"], "url": "i2"},
        {"number": 3, "title": "closed debt", "state": "CLOSED", "created_at": "2026-08-01T00:00:00Z", "updated_at": "2026-08-20T00:00:00Z", "closed_at": "2026-08-20T00:00:00Z", "labels": ["type:refactor"], "url": "i3"},
    ]
    obs = obs_set(NOW)
    add(obs, normalize.INV_ISSUES, issues, "series", coverage=COVERAGE)
    normalize.derive(obs, single_project("acme/widget", debt={"labels": ["type:refactor"], "mapping_version": "2026-09"}))
    assert obs.value_of("forge.issues.open_count") == 2
    assert obs.value_of("forge.issues.stale_open_count_30d") == 1
    assert obs.value_of("forge.issues.updated_count_28d") == 2
    assert obs.value_of("debt.items.open_count") == 1
    assert obs.value_of("debt.items.open_stale_count_30d") == 1
    assert obs.value_of("debt.items.closed_count_28d") == 1
    assert obs.value_of("debt.mapping")["mapping_version"] == "2026-09"


def test_commits_branches_and_planning_aggregates():
    obs = obs_set(NOW)
    add(obs, normalize.INV_COMMITS, [
        {"sha": "a", "committed_at": "2026-09-01T01:00:00Z", "title": "x"},
        {"sha": "b", "committed_at": "2026-09-01T02:00:00Z", "title": "y"},
        {"sha": "c", "committed_at": "2026-09-03T02:00:00Z", "title": "z"},
    ], "series", coverage={"complete": True})
    add(obs, normalize.INV_BRANCHES, [
        {"name": "old", "head_sha": "o", "head_committed_at": "2026-07-01T00:00:00Z", "protected": False},
        {"name": "new", "head_sha": "n", "head_committed_at": "2026-09-01T00:00:00Z", "protected": False},
    ], "series", coverage={"complete": True, "heads_resolved": True})
    add(obs, normalize.INV_TARGETS, [
        {"target_id": "1", "title": "soon", "state": "OPEN", "due_at": "2026-09-10T00:00:00Z", "open_items": 1, "closed_items": 0, "url": "m1"},
        {"target_id": "2", "title": "far", "state": "OPEN", "due_at": "2026-12-01T00:00:00Z", "open_items": 1, "closed_items": 0, "url": "m2"},
        {"target_id": "3", "title": "no date", "state": "OPEN", "due_at": None, "open_items": 0, "closed_items": 0, "url": "m3"},
        {"target_id": "4", "title": "done", "state": "CLOSED", "due_at": "2026-08-01T00:00:00Z", "open_items": 0, "closed_items": 3, "url": "m4"},
    ], "series", coverage={"complete": True})
    normalize.derive(obs, single_project("acme/widget"))
    assert obs.value_of("git.default_branch.commits.count_28d") == 3
    assert obs.value_of("git.default_branch.commit_active_days_28d") == 2
    assert obs.value_of("git.nondefault_branches.stale_count_30d") == 1
    assert obs.value_of("planning.explicit_targets.capability") == "SUPPORTED"
    assert obs.value_of("planning.explicit_targets.open_count") == 3
    assert obs.value_of("planning.explicit_targets.open_with_future_boundary_count") == 2
    assert obs.value_of("planning.explicit_targets.open_beyond_28d_count") == 1
    assert obs.value_of("planning.explicit_targets.nearest_future_boundary_days") == 4


def test_planning_source_none_is_positively_unsupported():
    obs = obs_set(NOW)
    normalize.derive(obs, single_project("acme/widget", planning={"source": "none"}))
    assert obs.value_of("planning.explicit_targets.capability") == "UNSUPPORTED"


def test_no_milestones_ever_is_supported_unused():
    obs = obs_set(NOW)
    add(obs, normalize.INV_TARGETS, [], "series", coverage={"complete": True})
    normalize.derive(obs, single_project("acme/widget"))
    assert obs.value_of("planning.explicit_targets.capability") == "SUPPORTED_UNUSED"
    assert obs.status_of("planning.explicit_targets.open_count") == AVAILABLE
