"""Builders for synthetic observation sets used by the conformance tests."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from devostasis.canonical import rational_record
from devostasis.observations import AVAILABLE, FRESH, Observation, ObservationSet, Receipt

OBSERVED_AT = "2026-09-05T12:00:00Z"
SUBJECT = {
    "provider": "github",
    "forge_instance": "github.com",
    "owner": "acme",
    "repo": "widget",
    "display_locator": "acme/widget",
    "immutable_project_id": "123456",
    "default_branch": "master",
    "visibility": "public",
}

MEDIAN_SECONDS = "forge.change_requests.median_time_to_merge_seconds_28d"
MEDIAN_HOURS = "forge.change_requests.median_time_to_merge_hours_28d"


def obs_set(observed_at: str = OBSERVED_AT, subject: dict[str, Any] | None = None) -> ObservationSet:
    return ObservationSet(subject=subject or SUBJECT, observed_at=observed_at)


def add(
    obs: ObservationSet,
    observation_id: str,
    value: Any = None,
    value_type: str = "count",
    status: str = AVAILABLE,
    freshness: str = FRESH,
    reason_code: str | None = None,
    coverage: dict[str, Any] | None = None,
) -> Observation:
    item = Observation(
        observation_id=observation_id,
        status=status,
        value_type=value_type,
        value=value,
        freshness=freshness,
        provider="github",
        collected_at=obs.observed_at,
        source_ref=f"test:{observation_id}",
        coverage=coverage,
        adapter_version="test",
        reason_code=reason_code,
    )
    obs.add(item)
    return item


def finalize(obs: ObservationSet, run_id: str = "run-test") -> ObservationSet:
    obs.finalize_receipt(
        Receipt(
            run_id=run_id,
            collector_version="test",
            target=obs.subject,
            started_at=obs.observed_at,
            ended_at=obs.observed_at,
            config_hash="sha256:test",
        )
    )
    return obs


def pulse_inputs(obs: ObservationSet, commits: int, active_days: int, cr_updates: int | None = 0, issue_updates: int | None = 0, **cr_status: Any) -> None:
    add(obs, "git.default_branch.commits.count_28d", commits)
    add(obs, "git.default_branch.commit_active_days_28d", active_days)
    if cr_updates is not None:
        add(obs, "forge.change_requests.updated_count_28d", cr_updates)
    if issue_updates is not None:
        add(obs, "forge.issues.updated_count_28d", issue_updates)


def flow_inputs(
    obs: ObservationSet,
    open_count: int,
    merged: int,
    oldest: int | None = None,
    median: int | None = None,
    median_seconds: int | Fraction | tuple[int, int] | None = None,
) -> None:
    """Flow inputs; ``median`` is whole hours, ``median_seconds`` an exact rational number of seconds."""
    add(obs, "forge.change_requests.open_count", open_count)
    add(obs, "forge.change_requests.merged_count_28d", merged)
    if oldest is not None:
        add(obs, "forge.change_requests.oldest_open_age_days", oldest, "duration")
    seconds: Fraction | None = None
    if median_seconds is not None:
        seconds = Fraction(*median_seconds) if isinstance(median_seconds, tuple) else Fraction(median_seconds)
    elif median is not None:
        seconds = Fraction(median) * 3600
    if seconds is not None:
        add(obs, MEDIAN_SECONDS, rational_record(seconds), "duration")
        add(obs, MEDIAN_HOURS, int(seconds // 3600), "duration")


def clutter_inputs(obs: ObservationSet, issues_open: int, issues_stale: int, cr_open: int, cr_stale: int, stale_branches: int) -> None:
    add(obs, "forge.issues.open_count", issues_open)
    add(obs, "forge.issues.stale_open_count_30d", issues_stale)
    if "forge.change_requests.open_count" not in obs:
        add(obs, "forge.change_requests.open_count", cr_open)
    add(obs, "forge.change_requests.stale_open_count_14d", cr_stale)
    add(obs, "git.nondefault_branches.stale_count_30d", stale_branches)


def revision(sha: str, committed_at: str, parents: list[dict[str, Any]] | None = None, current: str | None = None, history: str = "NO_DECISIVE_OBSERVED", provenance: str | None = "ATTEMPT_LEVEL") -> dict[str, Any]:
    parents = parents if parents is not None else []
    contribution = {"FAILURE_OBSERVED": "VERIFY_FAIL", "PASS_ONLY_OBSERVED": "VERIFY_PASS"}.get(history)
    return {
        "revision": sha,
        "committed_at": committed_at,
        "parents": parents,
        "current_verdict": current,
        "history_state": history,
        "historical_contribution": contribution,
        "history_provenance": provenance if parents else None,
    }


def parent(parent_id: str, current_state: str, states: list[str] | None = None, kind: str = "github_actions_workflow_run") -> dict[str, Any]:
    states = states or [current_state]
    return {
        "parent_id": parent_id,
        "kind": kind,
        "name": "ci",
        "event": "push",
        "current_attempt": len(states),
        "current_state": current_state,
        "attempts_observed": [{"attempt": i + 1, "state": s} for i, s in enumerate(states)],
        "attempts_complete": True,
        "history_state": "FAILURE_OBSERVED" if "VERIFY_FAIL" in states else ("PASS_ONLY_OBSERVED" if "VERIFY_PASS" in states else "NO_DECISIVE_OBSERVED"),
        "url": None,
    }


def passing_revisions(count: int, start_day: int = 1) -> list[dict[str, Any]]:
    return [
        revision(f"sha{i:02d}", f"2026-09-{start_day + i:02d}T10:00:00Z", [parent(f"p{i}", "VERIFY_PASS")], "VERIFY_PASS", "PASS_ONLY_OBSERVED")
        for i in range(count)
    ]


def integrity_inputs(obs: ObservationSet, configured: bool | None, revisions: list[dict[str, Any]] | None, status: str = AVAILABLE) -> None:
    if configured is not None:
        add(obs, "ci.configured", configured, "boolean")
    if revisions is not None:
        add(obs, "ci.revision_verdicts_14d", revisions, "series", status=status, reason_code=None if status == AVAILABLE else "PAGINATION_CAPPED")


def planning_inputs(obs: ObservationSet, capability: str, open_count: int = 0, future: int = 0, beyond: int = 0, nearest: int | None = None) -> None:
    add(obs, "planning.explicit_targets.capability", capability, "enum")
    if capability == "SUPPORTED":
        add(obs, "planning.explicit_targets.open_count", open_count)
        add(obs, "planning.explicit_targets.open_with_future_boundary_count", future)
        add(obs, "planning.explicit_targets.open_beyond_28d_count", beyond)
        if nearest is not None:
            add(obs, "planning.explicit_targets.nearest_future_boundary_days", nearest, "duration")


def direction_inputs(obs: ObservationSet, active: int, linked: int | None = None, links: dict[str, int] | None = None, unresolved: int = 0) -> None:
    """Direction's inputs: the active population and, when ``linked`` is given, its state-neutral L/U/R split."""
    add(obs, "planning.linkage.active_change_requests_count_28d", active)
    if linked is not None:
        add(obs, "planning.linkage.active_change_requests_linked_count_28d", linked)
        add(obs, "planning.linkage.active_change_requests_unlinked_count_28d", active - linked - unresolved)
        add(obs, "planning.linkage.active_change_requests_unresolved_count_28d", unresolved)
        add(obs, "planning.linkage.active_change_requests_linked_to_open_target_count_28d", linked)
    if links is not None:
        add(obs, "planning.linkage.links_per_target_28d", links, "record")


def debt_inputs(obs: ObservationSet, capability: str, open_count: int | None = None, stale: int | None = None, closed: int | None = None, mapping_version: str = "1") -> None:
    add(obs, "debt.registry.capability", capability, "enum")
    if capability == "CONFIGURED":
        add(obs, "debt.mapping", {"labels": ["debt"], "mapping_version": mapping_version, "source": "issue_labels"}, "record")
        if open_count is not None:
            add(obs, "debt.items.open_count", open_count)
        if stale is not None:
            add(obs, "debt.items.open_stale_count_30d", stale)
        if closed is not None:
            add(obs, "debt.items.closed_count_28d", closed)


def full_inputs(obs: ObservationSet) -> ObservationSet:
    """A complete, ordinary repository: every Vital exactly evaluable."""
    pulse_inputs(obs, commits=20, active_days=8, cr_updates=12, issue_updates=6)
    flow_inputs(obs, open_count=2, merged=9, oldest=3, median=20)
    clutter_inputs(obs, issues_open=10, issues_stale=1, cr_open=2, cr_stale=0, stale_branches=1)
    integrity_inputs(obs, True, passing_revisions(5))
    planning_inputs(obs, "SUPPORTED", open_count=2, future=1, beyond=1, nearest=40)
    direction_inputs(obs, active=10, linked=8, links={"1": 8})
    debt_inputs(obs, "CONFIGURED", open_count=3, stale=1, closed=2)
    return finalize(obs)
