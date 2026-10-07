"""Normalized project activity since the previous successful bundle.

The interval is ``(previous.observed_at, current.observed_at]``, never a blind
24 hours. A BASELINE bundle has no previous bundle, so it reports the trailing
28-day observation window and says so in ``interval.basis``.
"""

from __future__ import annotations

from typing import Any

from . import timeutil
from .contracts import ACTIVITY_SCHEMA
from .normalize import CI_REVISIONS, INV_COMMITS, INV_CRS, INV_ISSUES, INV_RELEASES
from .observations import ObservationSet
from .policy import ACTIVITY

BASIS_PREVIOUS = "PREVIOUS_BUNDLE"
BASIS_WINDOW = "OBSERVATION_WINDOW_28D"


def _in_interval(ts: str | None, start, end) -> bool:
    if not ts:
        return False
    moment = timeutil.parse_ts(ts)
    return start < moment <= end


def _cap(items: list[dict[str, Any]], cap: int) -> tuple[list[dict[str, Any]], bool]:
    if cap >= 0 and len(items) > cap:
        return items[:cap], True
    return items, False


def build_activity(
    obs: ObservationSet,
    previous_manifest: dict[str, Any] | None,
    interval_start: str | None,
    cap: int,
) -> dict[str, Any]:
    end = timeutil.parse_ts(obs.observed_at)
    if interval_start:
        start = timeutil.parse_ts(interval_start)
        basis = BASIS_PREVIOUS
        if start >= end:
            # An interval that ends before it starts describes nothing. The
            # runner never asks for one since #17; a caller that does has
            # compared against the wrong bundle, and that is not repaired here.
            raise ValueError(f"activity interval must start before it ends: {interval_start} is not before {obs.observed_at}")
    else:
        start = timeutil.minus_days(end, ACTIVITY["window_days"])
        basis = BASIS_WINDOW
    coverage_notes: list[str] = []
    # The inventories this report reads cover a fixed trailing window. When a
    # run follows a long outage, the interval it claims is wider than the
    # evidence behind it, and silence about the older part would read as "no
    # activity" (G1). Say so instead.
    evidence_start = timeutil.minus_days(end, ACTIVITY["window_days"])
    if start < evidence_start:
        coverage_notes.append(f"INTERVAL_EXCEEDS_EVIDENCE_WINDOW:evidence_from={timeutil.format_ts(evidence_start)}")
    truncated: dict[str, bool] = {}
    classes: dict[str, Any] = {}

    commits = obs.get(INV_COMMITS)
    revisions = []
    if commits is not None and commits.has_value:
        revisions = sorted(
            [
                {"revision": c["sha"], "committed_at": c["committed_at"], "title": c.get("title")}
                for c in commits.value if _in_interval(c.get("committed_at"), start, end)
            ],
            key=lambda c: (c["committed_at"], c["revision"]),
        )
        if commits.status != "AVAILABLE":
            coverage_notes.append(f"REVISION:{commits.status}:{commits.reason_code}")
    else:
        coverage_notes.append(f"REVISION:{obs.status_of(INV_COMMITS)}")
    items, cut = _cap(revisions, cap)
    truncated["REVISION"] = cut
    classes["REVISION"] = {"count": len(revisions), "items": items}

    crs = obs.get(INV_CRS)
    cr_events: list[dict[str, Any]] = []
    if crs is not None and crs.has_value:
        for cr in crs.value:
            base = {"number": cr["number"], "title": cr.get("title"), "url": cr.get("url")}
            if _in_interval(cr.get("created_at"), start, end):
                cr_events.append(dict(base, kind="OPENED", at=cr["created_at"]))
            if _in_interval(cr.get("merged_at"), start, end):
                cr_events.append(dict(base, kind="MERGED", at=cr["merged_at"]))
            elif cr.get("state") == "CLOSED" and _in_interval(cr.get("closed_at"), start, end):
                cr_events.append(dict(base, kind="CLOSED", at=cr["closed_at"]))
        if crs.status != "AVAILABLE":
            coverage_notes.append(f"CHANGE_REQUEST:{crs.status}:{crs.reason_code}")
    else:
        coverage_notes.append(f"CHANGE_REQUEST:{obs.status_of(INV_CRS)}")
    cr_events.sort(key=lambda e: (e["at"], e["number"], e["kind"]))
    items, cut = _cap(cr_events, cap)
    truncated["CHANGE_REQUEST"] = cut
    classes["CHANGE_REQUEST"] = {
        "opened": sum(1 for e in cr_events if e["kind"] == "OPENED"),
        "merged": sum(1 for e in cr_events if e["kind"] == "MERGED"),
        "closed": sum(1 for e in cr_events if e["kind"] == "CLOSED"),
        "items": items,
    }

    issues = obs.get(INV_ISSUES)
    issue_events: list[dict[str, Any]] = []
    if issues is not None and issues.has_value:
        for issue in issues.value:
            base = {"number": issue["number"], "title": issue.get("title"), "url": issue.get("url")}
            if _in_interval(issue.get("created_at"), start, end):
                issue_events.append(dict(base, kind="OPENED", at=issue["created_at"]))
            if issue.get("state") == "CLOSED" and _in_interval(issue.get("closed_at"), start, end):
                issue_events.append(dict(base, kind="CLOSED", at=issue["closed_at"]))
        if issues.status != "AVAILABLE":
            coverage_notes.append(f"WORK_ITEM:{issues.status}:{issues.reason_code}")
    else:
        coverage_notes.append(f"WORK_ITEM:{obs.status_of(INV_ISSUES)}")
    issue_events.sort(key=lambda e: (e["at"], e["number"], e["kind"]))
    items, cut = _cap(issue_events, cap)
    truncated["WORK_ITEM"] = cut
    classes["WORK_ITEM"] = {
        "opened": sum(1 for e in issue_events if e["kind"] == "OPENED"),
        "closed": sum(1 for e in issue_events if e["kind"] == "CLOSED"),
        "items": items,
    }

    ci = obs.get(CI_REVISIONS)
    verification_items: list[dict[str, Any]] = []
    verified = failed = unresolved = 0
    if ci is not None and ci.has_value:
        for rev in ci.value:
            if not rev.get("parents") or not _in_interval(rev.get("committed_at"), start, end):
                continue
            verified += 1
            if rev.get("history_state") == "FAILURE_OBSERVED":
                failed += 1
            if rev.get("current_verdict") == "VERIFY_UNRESOLVED":
                unresolved += 1
            if rev.get("history_state") == "FAILURE_OBSERVED" or rev.get("current_verdict") in ("VERIFY_UNRESOLVED", "VERIFY_FAIL"):
                verification_items.append(
                    {
                        "revision": rev["revision"],
                        "committed_at": rev["committed_at"],
                        "current_verdict": rev.get("current_verdict"),
                        "history_state": rev.get("history_state"),
                        "parents": [{"parent_id": p["parent_id"], "name": p.get("name"), "current_state": p.get("current_state"), "url": p.get("url")} for p in rev.get("parents", [])],
                    }
                )
        if ci.status != "AVAILABLE":
            coverage_notes.append(f"VERIFICATION:{ci.status}:{ci.reason_code}")
    else:
        coverage_notes.append(f"VERIFICATION:{obs.status_of(CI_REVISIONS)}")
    verification_items.sort(key=lambda r: (r["committed_at"], r["revision"]))
    items, cut = _cap(verification_items, cap)
    truncated["VERIFICATION"] = cut
    classes["VERIFICATION"] = {"revisions_verified": verified, "failed": failed, "unresolved": unresolved, "items": items}

    releases = obs.get(INV_RELEASES)
    release_items: list[dict[str, Any]] = []
    if releases is not None and releases.has_value:
        release_items = sorted(
            [r for r in releases.value if _in_interval(r.get("published_at"), start, end)],
            key=lambda r: (r.get("published_at") or "", r.get("tag") or ""),
        )
        if releases.status != "AVAILABLE":
            coverage_notes.append(f"RELEASE:{releases.status}:{releases.reason_code}")
    else:
        coverage_notes.append(f"RELEASE:{obs.status_of(INV_RELEASES)}")
    items, cut = _cap(release_items, cap)
    truncated["RELEASE"] = cut
    classes["RELEASE"] = {"count": len(release_items), "items": items}

    capability_changes: list[dict[str, Any]] = []
    previous_receipt = (previous_manifest or {}).get("receipt_identity") or (previous_manifest or {}).get("receipt") or {}
    prev_keys = previous_receipt.get("per_key") or {}
    cur_keys = obs.receipt.per_key if obs.receipt else {}
    if previous_manifest is not None:
        for key in sorted(set(prev_keys) | set(cur_keys)):
            before = prev_keys.get(key)
            after = cur_keys.get(key)
            if before != after:
                capability_changes.append({"observation_id": key, "previous": before, "current": after})
    classes["CAPABILITY_CHANGE"] = {"count": len(capability_changes), "items": capability_changes}

    return {
        "schema": ACTIVITY_SCHEMA,
        "interval": {"start": timeutil.format_ts(start), "end": timeutil.format_ts(end), "basis": basis, "exclusive_start": True},
        "coverage_notes": sorted(set(coverage_notes)),
        "truncated": dict(sorted(truncated.items())),
        "list_cap": cap,
        "classes": classes,
    }
