"""Derive the aggregate observations the Vitals consume from provider-neutral inventories.

Adapters emit inventories (lists of normalized records with coverage metadata).
This module turns them into the aggregate observation keys named by the Vital
contracts, propagating status, freshness and provenance. Nothing here
interprets project health.
"""

from __future__ import annotations

from typing import Any, Callable

from . import canonical, timeutil
from .config import ResolvedProject
from .observations import AVAILABLE, FRESH, OBSERVED_SUBSET_COUNT, PARTIAL, UNAVAILABLE, VALUE_BEARING, VALUE_SEMANTICS, Observation, ObservationSet
from .policy import CLUTTER, FLOW, PLANNING, PULSE

INV_REPO = "forge.repository.metadata"
INV_COMMITS = "git.default_branch.commits_28d"
INV_CRS = "forge.change_requests.inventory"
INV_ISSUES = "forge.issues.inventory"
INV_BRANCHES = "git.nondefault_branches.inventory"
INV_TARGETS = "planning.explicit_targets.inventory"
INV_RELEASES = "forge.releases.inventory"
INV_DEBT_REGISTER = "debt.register.inventory"
CI_CONFIGURED = "ci.configured"
CI_REVISIONS = "ci.revision_verdicts_14d"

INVENTORY_IDS = [INV_REPO, INV_COMMITS, INV_CRS, INV_ISSUES, INV_BRANCHES, INV_TARGETS, INV_RELEASES, INV_DEBT_REGISTER, CI_CONFIGURED, CI_REVISIONS]

# Exact rational merge latency in seconds is the classifier input (PV-FLOW-MERGE-LATENCY-001);
# the whole-hour value is derived from it for presentation and compatibility only.
MEDIAN_SECONDS = "forge.change_requests.median_time_to_merge_seconds_28d"
MEDIAN_HOURS = "forge.change_requests.median_time_to_merge_hours_28d"
MEDIAN_HOURS_NOTE = "whole-hour projection of median_time_to_merge_seconds_28d for presentation; never a classifier input"

# Direction's classifier reads state-neutral linkage (direction.bands.v2). The
# open-target count it read before is kept for presentation only, as the
# accepted judgement allows (PV-REV-DIRECTION-CLOSED-TARGET-001).
LINKAGE_LINKED = "planning.linkage.active_change_requests_linked_count_28d"
LINKAGE_UNLINKED = "planning.linkage.active_change_requests_unlinked_count_28d"
LINKAGE_UNRESOLVED = "planning.linkage.active_change_requests_unresolved_count_28d"
LINKAGE_UNRESOLVED_ITEMS = "planning.linkage.unresolved_change_requests_28d"
LINKAGE_MISSING_REFS = "planning.linkage.missing_target_reference_count_28d"
LINKED_TO_OPEN_NOTE = "active change requests linked to a target that is open now; presentation only since direction.bands.v2, never a classifier input"


def _derived(
    obs: ObservationSet,
    observation_id: str,
    value_type: str,
    source: Observation,
    compute: Callable[[list[dict[str, Any]]], Any],
    complete: bool = True,
    extra_sources: list[str] | None = None,
    reason_override: str | None = None,
    notes: str | None = None,
    subset_count: bool = False,
) -> None:
    """Add an aggregate derived from ``source``; status follows the source and the coverage flag.

    ``subset_count`` declares the aggregate a count of the source records that
    satisfy a predicate, which the records an incomplete enumeration did not
    return can only increase. Only then does a ``PARTIAL`` value say so in its
    coverage (``OBSERVED_SUBSET_COUNT``), which is what lets a Vital read it as
    a lower bound; a median, a maximum or a record never claims it.
    """
    if observation_id in obs:
        return
    evidence = {"derived_from": [source.observation_id] + (extra_sources or [])}
    common = {
        "provider": source.provider,
        "collected_at": source.collected_at,
        "source_ref": f"derived:{source.observation_id}",
        "adapter_version": source.adapter_version,
        "freshness": source.freshness,
        "evidence_ref": evidence,
        "notes": notes,
    }
    if source.status not in VALUE_BEARING or not isinstance(source.value, list):
        obs.add(
            Observation(
                observation_id=observation_id,
                status=source.status if source.status not in VALUE_BEARING else UNAVAILABLE,
                value_type=value_type,
                reason_code=reason_override or source.reason_code or "SOURCE_NOT_AVAILABLE",
                **common,
            )
        )
        return
    value = compute(source.value)
    status = AVAILABLE if (source.status == AVAILABLE and complete) else PARTIAL
    coverage = {"complete": status == AVAILABLE, "source_coverage": source.coverage}
    if status == PARTIAL and subset_count:
        coverage[VALUE_SEMANTICS] = OBSERVED_SUBSET_COUNT
    obs.add(
        Observation(
            observation_id=observation_id,
            status=status,
            value_type=value_type,
            value=value,
            coverage=coverage,
            reason_code=None if status == AVAILABLE else (reason_override or "SOURCE_COVERAGE_INCOMPLETE"),
            **common,
        )
    )


def _flag(source: Observation, key: str) -> bool:
    coverage = source.coverage or {}
    return bool(coverage.get(key, True))


def merge_latencies(items: list[dict[str, Any]]) -> list:
    """Exact merge durations in seconds of merged change requests, order-independent."""
    return [timeutil.exact_seconds_between(item["created_at"], item["merged_at"]) for item in items]


def target_refs(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Explicit target references of a change request, in either record shape."""
    refs = item.get("target_refs")
    if isinstance(refs, list):
        return [ref for ref in refs if isinstance(ref, dict) and ref.get("target_id")]
    if item.get("target_id"):
        return [{"target_id": str(item["target_id"]), "state": item.get("target_state")}]
    return []


# Direction linkage evidence per active change request (PV-DIRECTION-INCOMPLETE-001,
# section 3). A reference resolves when its declared target does, open or closed
# alike (PV-REV-DIRECTION-CLOSED-TARGET-001); MISSING is a complete register
# positively lacking the id, a broken reference and therefore unlinked; every
# other state, an unreadable title, body or milestone, or a reference of an
# older record shape without a state, is evidence nobody could resolve.
LINKED = "LINKED"
UNLINKED = "UNLINKED"
UNRESOLVED = "UNRESOLVED"
RESOLVED_TARGET_STATES = ("OPEN", "CLOSED")
MISSING_TARGET = "MISSING"


def linkage_state(item: dict[str, Any]) -> str:
    """LINKED, UNLINKED or UNRESOLVED for one active change request."""
    refs = target_refs(item)
    if any(ref.get("state") in RESOLVED_TARGET_STATES for ref in refs):
        return LINKED
    if item.get("linkage_unresolved") or any(ref.get("state") != MISSING_TARGET for ref in refs):
        return UNRESOLVED
    return UNLINKED


def unresolved_linkage_reasons(item: dict[str, Any]) -> list[str]:
    """Why an UNRESOLVED change request is unresolved, in a stable order."""
    reasons = [f"TARGET_UNRESOLVED:{ref['target_id']}:{ref.get('state')}" for ref in target_refs(item) if ref.get("state") not in RESOLVED_TARGET_STATES + (MISSING_TARGET,)]
    unreadable = item.get("linkage_unresolved")
    if isinstance(unreadable, list):
        reasons.extend(f"LINKAGE_UNREADABLE:{reason}" for reason in unreadable)
    elif unreadable:
        reasons.append(f"LINKAGE_UNREADABLE:{unreadable}")
    return sorted(set(reasons))


def derive(obs: ObservationSet, project: ResolvedProject) -> ObservationSet:
    observed_at = timeutil.parse_ts(obs.observed_at)
    since_pulse = timeutil.minus_days(observed_at, PULSE["window_days"])
    since_flow = timeutil.minus_days(observed_at, FLOW["window_days"])
    since_planning = timeutil.minus_days(observed_at, PLANNING["frame_days"])
    stale_issue = timeutil.minus_days(observed_at, CLUTTER["issue_stale_days"])
    stale_cr = timeutil.minus_days(observed_at, CLUTTER["change_request_stale_days"])
    stale_branch = timeutil.minus_days(observed_at, CLUTTER["branch_stale_days"])

    commits = obs.get(INV_COMMITS)
    if commits is not None:
        _derived(
            obs, "git.default_branch.commits.count_28d", "count", commits,
            lambda items: len(items), complete=_flag(commits, "complete"), subset_count=True,
        )
        _derived(
            obs, "git.default_branch.commit_active_days_28d", "count", commits,
            lambda items: len({timeutil.utc_day(timeutil.parse_ts(item["committed_at"])) for item in items}),
            complete=_flag(commits, "complete"), subset_count=True,
        )

    crs = obs.get(INV_CRS)
    if crs is not None:
        open_ok = _flag(crs, "open_complete")
        window_ok = _flag(crs, "window_complete")

        def _open(items):
            return [item for item in items if item.get("state") == "OPEN"]

        def _merged_in_window(items):
            return [item for item in items if item.get("merged_at") and timeutil.parse_ts(item["merged_at"]) >= since_flow]

        def _updated_in_window(items):
            return [item for item in items if item.get("updated_at") and timeutil.parse_ts(item["updated_at"]) >= since_flow]

        _derived(obs, "forge.change_requests.open_count", "count", crs, lambda items: len(_open(items)), complete=open_ok, subset_count=True)
        _derived(obs, "forge.change_requests.merged_count_28d", "count", crs, lambda items: len(_merged_in_window(items)), complete=window_ok, subset_count=True)
        _derived(obs, "forge.change_requests.updated_count_28d", "count", crs, lambda items: len(_updated_in_window(items)), complete=window_ok, subset_count=True)
        _derived(
            obs, "forge.change_requests.stale_open_count_14d", "count", crs,
            lambda items: len([i for i in _open(items) if timeutil.parse_ts(i["updated_at"]) < stale_cr]),
            complete=open_ok, subset_count=True,
        )
        if crs.has_value and _open(crs.value):
            _derived(
                obs, "forge.change_requests.oldest_open_age_days", "duration", crs,
                lambda items: max(timeutil.age_days(observed_at, timeutil.parse_ts(i["created_at"])) for i in _open(items)),
                complete=open_ok,
            )
        if crs.has_value and _merged_in_window(crs.value):
            _derived(
                obs, MEDIAN_SECONDS, "duration", crs,
                lambda items: canonical.rational_record(timeutil.median_fraction(merge_latencies(_merged_in_window(items)))),
                complete=window_ok,
            )
            _derived(
                obs, MEDIAN_HOURS, "duration", crs,
                lambda items: int(timeutil.median_fraction(merge_latencies(_merged_in_window(items))) // 3600),
                complete=window_ok,
                extra_sources=[MEDIAN_SECONDS],
                notes=MEDIAN_HOURS_NOTE,
            )

        def _active(items):
            return [item for item in items if item.get("updated_at") and timeutil.parse_ts(item["updated_at"]) >= since_planning]

        def _in_state(items, state):
            return [item for item in _active(items) if linkage_state(item) == state]

        def _linked_to_open(items):
            return [item for item in _active(items) if any(ref.get("state") == "OPEN" for ref in target_refs(item))]

        def _links_per_target(items):
            # State-neutral: a closed target still carries the links of the work
            # declared against it (PV-REV-DIRECTION-CLOSED-TARGET-001, DIR-CLOSED-08).
            counts: dict[str, int] = {}
            for item in _active(items):
                for ref in target_refs(item):
                    if ref.get("state") in RESOLVED_TARGET_STATES:
                        counts[str(ref["target_id"])] = counts.get(str(ref["target_id"]), 0) + 1
            return dict(sorted(counts.items()))

        def _refs_in_state(items, state):
            return len([ref for item in _active(items) for ref in target_refs(item) if ref.get("state") == state])

        def _unresolved_items(items):
            return {str(item.get("number")): unresolved_linkage_reasons(item) for item in _in_state(items, UNRESOLVED)}

        _derived(obs, "planning.linkage.active_change_requests_count_28d", "count", crs, lambda items: len(_active(items)), complete=window_ok, subset_count=True)
        _derived(obs, LINKAGE_LINKED, "count", crs, lambda items: len(_in_state(items, LINKED)), complete=window_ok, subset_count=True)
        _derived(obs, LINKAGE_UNLINKED, "count", crs, lambda items: len(_in_state(items, UNLINKED)), complete=window_ok, subset_count=True)
        _derived(obs, LINKAGE_UNRESOLVED, "count", crs, lambda items: len(_in_state(items, UNRESOLVED)), complete=window_ok, subset_count=True)
        _derived(obs, LINKAGE_UNRESOLVED_ITEMS, "record", crs, _unresolved_items, complete=window_ok)
        _derived(
            obs, "planning.linkage.active_change_requests_linked_to_open_target_count_28d", "count", crs,
            lambda items: len(_linked_to_open(items)), complete=window_ok, subset_count=True, notes=LINKED_TO_OPEN_NOTE,
        )
        _derived(obs, "planning.linkage.links_per_target_28d", "record", crs, _links_per_target, complete=window_ok)
        _derived(obs, "planning.linkage.unknown_target_reference_count_28d", "count", crs, lambda items: _refs_in_state(items, "UNKNOWN"), complete=window_ok, subset_count=True)
        _derived(obs, LINKAGE_MISSING_REFS, "count", crs, lambda items: _refs_in_state(items, MISSING_TARGET), complete=window_ok, subset_count=True)

    issues = obs.get(INV_ISSUES)
    if issues is not None:
        open_ok = _flag(issues, "open_complete")
        window_ok = _flag(issues, "window_complete")

        def _open_issues(items):
            return [item for item in items if item.get("state") == "OPEN"]

        _derived(obs, "forge.issues.open_count", "count", issues, lambda items: len(_open_issues(items)), complete=open_ok, subset_count=True)
        _derived(
            obs, "forge.issues.stale_open_count_30d", "count", issues,
            lambda items: len([i for i in _open_issues(items) if timeutil.parse_ts(i["updated_at"]) < stale_issue]),
            complete=open_ok, subset_count=True,
        )
        _derived(
            obs, "forge.issues.updated_count_28d", "count", issues,
            lambda items: len([i for i in items if timeutil.parse_ts(i["updated_at"]) >= since_pulse]),
            complete=window_ok, subset_count=True,
        )

    _derive_debt(obs, project, issues, stale_issue, since_planning)

    branches = obs.get(INV_BRANCHES)
    if branches is not None:
        heads_ok = _flag(branches, "complete") and _flag(branches, "heads_resolved")
        _derived(
            obs, "git.nondefault_branches.stale_count_30d", "count", branches,
            lambda items: len([
                i for i in items if i.get("head_committed_at") and timeutil.parse_ts(i["head_committed_at"]) < stale_branch
            ]),
            complete=heads_ok,
            reason_override=None if heads_ok else "BRANCH_HEADS_UNRESOLVED", subset_count=True,
        )

    _derive_planning(obs, project, observed_at)
    return obs


def _derive_debt(obs: ObservationSet, project: ResolvedProject, issues: Observation | None, stale_issue, since_planning) -> None:
    if "debt.registry.capability" in obs:
        return
    base = {"provider": "config", "collected_at": obs.observed_at, "source_ref": "config:debt", "adapter_version": "config"}
    mapping = project.debt_mapping
    if mapping is None:
        obs.add(Observation(observation_id="debt.registry.capability", status=AVAILABLE, value_type="enum", value="UNCONFIGURED", **base))
        return
    obs.add(Observation(observation_id="debt.registry.capability", status=AVAILABLE, value_type="enum", value="CONFIGURED", **base))
    obs.add(Observation(observation_id="debt.mapping", status=AVAILABLE, value_type="record", value=dict(mapping), **base))

    if mapping["source"] == "file":
        register = obs.get(INV_DEBT_REGISTER)
        if register is None:
            obs.add(Observation(observation_id="debt.items.open_count", status="UNKNOWN", value_type="count", reason_code="REGISTER_NOT_COLLECTED", **base))
            return

        def _open_items(items):
            return [i for i in items if i.get("state") == "OPEN"]

        _derived(obs, "debt.items.open_count", "count", register, lambda items: len(_open_items(items)), extra_sources=["debt.mapping"], subset_count=True)
        _derived(
            obs, "debt.items.open_stale_count_30d", "count", register,
            lambda items: len([i for i in _open_items(items) if timeutil.parse_ts(i["updated_at"]) < stale_issue]),
            extra_sources=["debt.mapping"], subset_count=True,
        )
        _derived(
            obs, "debt.items.closed_count_28d", "count", register,
            lambda items: len([i for i in items if i.get("state") == "CLOSED" and i.get("closed_at") and timeutil.parse_ts(i["closed_at"]) >= since_planning]),
            extra_sources=["debt.mapping"], subset_count=True,
        )
        return

    labels = set(mapping.get("labels") or [])
    if issues is None:
        obs.add(Observation(observation_id="debt.items.open_count", status="UNKNOWN", value_type="count", reason_code="ISSUES_NOT_COLLECTED", **base))
        return

    def _mapped(item):
        return bool(labels.intersection(item.get("labels") or []))

    open_ok = _flag(issues, "open_complete")
    window_ok = _flag(issues, "window_complete")
    _derived(
        obs, "debt.items.open_count", "count", issues,
        lambda items: len([i for i in items if i.get("state") == "OPEN" and _mapped(i)]),
        complete=open_ok, extra_sources=["debt.mapping"], subset_count=True,
    )
    _derived(
        obs, "debt.items.open_stale_count_30d", "count", issues,
        lambda items: len([i for i in items if i.get("state") == "OPEN" and _mapped(i) and timeutil.parse_ts(i["updated_at"]) < stale_issue]),
        complete=open_ok, extra_sources=["debt.mapping"], subset_count=True,
    )
    _derived(
        obs, "debt.items.closed_count_28d", "count", issues,
        lambda items: len([
            i for i in items if i.get("state") == "CLOSED" and _mapped(i) and i.get("closed_at") and timeutil.parse_ts(i["closed_at"]) >= since_planning
        ]),
        complete=window_ok, extra_sources=["debt.mapping"], subset_count=True,
    )


def _derive_planning(obs: ObservationSet, project: ResolvedProject, observed_at) -> None:
    if "planning.explicit_targets.capability" in obs:
        return
    horizon_edge = timeutil.minus_days(observed_at, -PLANNING["frame_days"])
    base = {"provider": "config", "collected_at": obs.observed_at, "source_ref": "config:planning", "adapter_version": "config"}
    if project.planning_source == "none":
        obs.add(Observation(observation_id="planning.explicit_targets.capability", status=AVAILABLE, value_type="enum", value="UNSUPPORTED", **base))
        return
    targets = obs.get(INV_TARGETS)
    if targets is None:
        obs.add(Observation(observation_id="planning.explicit_targets.capability", status="UNKNOWN", value_type="enum", reason_code="TARGETS_NOT_COLLECTED", **base))
        return
    # A fresh incomplete enumeration that returned a target proves support: more
    # records can only add targets (PV-HORIZON-PARTIAL-001, section 3). One that
    # returned none proves neither support nor its absence.
    proven_subset = targets.status == PARTIAL and targets.freshness == FRESH and isinstance(targets.value, list) and bool(targets.value)
    if not targets.good and not proven_subset:
        obs.add(
            Observation(
                observation_id="planning.explicit_targets.capability",
                status=targets.status if targets.status not in VALUE_BEARING else PARTIAL,
                value_type="enum",
                value="SUPPORTED" if (targets.status == PARTIAL and targets.value) else None,
                reason_code=targets.reason_code or "TARGETS_INCOMPLETE",
                provider=targets.provider, collected_at=targets.collected_at,
                source_ref=f"derived:{INV_TARGETS}", adapter_version=targets.adapter_version, freshness=targets.freshness,
            )
        )
        return
    items = list(targets.value)
    capability = "SUPPORTED" if items else "SUPPORTED_UNUSED"
    obs.add(
        Observation(
            observation_id="planning.explicit_targets.capability", status=AVAILABLE, value_type="enum", value=capability,
            provider=targets.provider, collected_at=targets.collected_at, source_ref=f"derived:{INV_TARGETS}",
            adapter_version=targets.adapter_version, freshness=targets.freshness, evidence_ref={"derived_from": [INV_TARGETS]},
            coverage=None if targets.good else {"complete": True, "basis": "RETURNED_TARGET_RECORD", "source_coverage": targets.coverage},
            notes=None if targets.good else "support is proved by a returned target record; the target enumeration itself is incomplete",
        )
    )
    open_items = [i for i in items if i.get("state") == "OPEN"]
    future = [i for i in open_items if i.get("due_at") and timeutil.parse_ts(i["due_at"]) > observed_at]
    beyond = [i for i in future if timeutil.parse_ts(i["due_at"]) > horizon_edge]
    # Counts over the returned targets; over an incomplete enumeration each is an
    # observed-subset lower bound and says so (PV-REV-PR-031-003, issue #39).
    _derived(obs, "planning.explicit_targets.open_count", "count", targets, lambda _: len(open_items), subset_count=True)
    _derived(obs, "planning.explicit_targets.open_with_future_boundary_count", "count", targets, lambda _: len(future), subset_count=True)
    _derived(obs, "planning.explicit_targets.open_beyond_28d_count", "count", targets, lambda _: len(beyond), subset_count=True)
    if future:
        nearest = min(int((timeutil.parse_ts(i["due_at"]) - observed_at).total_seconds() // 86400) for i in future)
        _derived(obs, "planning.explicit_targets.nearest_future_boundary_days", "duration", targets, lambda _: nearest)
