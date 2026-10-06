"""Regenerate examples/observations.json and examples/sample-bundle from synthetic evidence.

Run from the repository root:  python scripts/make_examples.py
The evidence is invented for a fictional repository; nothing private is used.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from devostasis import normalize  # noqa: E402
from devostasis.config import single_project  # noqa: E402
from devostasis.history import FilesystemHistoryStore  # noqa: E402
from devostasis.observations import AVAILABLE, Observation, ObservationSet, Receipt  # noqa: E402
from devostasis.runner import build_from_observations  # noqa: E402

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


def obs(oid: str, value, value_type: str, coverage=None) -> Observation:
    return Observation(
        observation_id=oid,
        status=AVAILABLE,
        value_type=value_type,
        value=value,
        provider="github",
        collected_at=OBSERVED_AT,
        source_ref=f"example:{oid}",
        coverage=coverage,
        adapter_version="devostasis.github.v1",
        evidence_ref={"example": True},
    )


def _example_link(i: int) -> dict:
    """Odd changes link to the open release 1.2; change 32 delivered release 1.1, closed since, and stays linked."""
    if i % 2:
        target, state = "3", "OPEN"
    elif i == 2:
        target, state = "2", "CLOSED"
    else:
        return {"target_id": None, "target_state": None, "target_refs": [], "linkage_unresolved": []}
    return {"target_id": target, "target_state": state, "target_refs": [{"target_id": target, "state": state}], "linkage_unresolved": []}


def build_observation_set() -> ObservationSet:
    commits = [
        {"sha": f"{i:040x}", "committed_at": f"2026-08-{10 + i:02d}T09:00:00Z", "title": f"feat: change number {i}"} for i in range(1, 20)
    ]
    change_requests = [
        {"number": 40, "id": 40, "title": "Refactor the pricing module", "state": "OPEN", "draft": False, "created_at": "2026-09-02T10:00:00Z", "updated_at": "2026-09-04T10:00:00Z", "merged_at": None, "closed_at": None, "target_id": "3", "target_state": "OPEN", "target_refs": [{"target_id": "3", "state": "OPEN"}], "linkage_unresolved": [], "author": "dev", "url": "https://example.invalid/pull/40"},
        {"number": 41, "id": 41, "title": "Add the export button", "state": "OPEN", "draft": True, "created_at": "2026-09-03T10:00:00Z", "updated_at": "2026-09-05T08:00:00Z", "merged_at": None, "closed_at": None, "target_id": None, "target_state": None, "target_refs": [], "linkage_unresolved": [], "author": "dev", "url": "https://example.invalid/pull/41"},
    ] + [
        {"number": 30 + i, "id": 30 + i, "title": f"Merged change {i}", "state": "MERGED", "draft": False, "created_at": f"2026-08-{12 + i:02d}T10:00:00Z", "updated_at": f"2026-08-{13 + i:02d}T10:00:00Z", "merged_at": f"2026-08-{13 + i:02d}T06:00:00Z", "closed_at": f"2026-08-{13 + i:02d}T06:00:00Z", **_example_link(i), "author": "dev", "url": f"https://example.invalid/pull/{30 + i}"}
        for i in range(1, 9)
    ]
    issues = [
        {"number": 5, "id": 5, "title": "Old feature request", "state": "OPEN", "created_at": "2026-05-01T10:00:00Z", "updated_at": "2026-06-01T10:00:00Z", "closed_at": None, "labels": ["enhancement"], "target_id": None, "author": "user", "url": "https://example.invalid/issues/5"},
        {"number": 12, "id": 12, "title": "Replace the legacy parser", "state": "OPEN", "created_at": "2026-08-20T10:00:00Z", "updated_at": "2026-09-01T10:00:00Z", "closed_at": None, "labels": ["type:refactor"], "target_id": "3", "author": "dev", "url": "https://example.invalid/issues/12"},
        {"number": 13, "id": 13, "title": "Crash on empty input", "state": "OPEN", "created_at": "2026-09-04T10:00:00Z", "updated_at": "2026-09-04T12:00:00Z", "closed_at": None, "labels": ["bug"], "target_id": None, "author": "user", "url": "https://example.invalid/issues/13"},
        {"number": 11, "id": 11, "title": "Remove dead configuration flags", "state": "CLOSED", "created_at": "2026-08-01T10:00:00Z", "updated_at": "2026-08-25T10:00:00Z", "closed_at": "2026-08-25T10:00:00Z", "labels": ["type:refactor"], "target_id": None, "author": "dev", "url": "https://example.invalid/issues/11"},
    ]
    branches = [
        {"name": "experiment/old-idea", "head_sha": "e" * 40, "head_committed_at": "2026-06-15T10:00:00Z", "protected": False},
        {"name": "feature/export", "head_sha": "f" * 40, "head_committed_at": "2026-09-05T08:00:00Z", "protected": False},
    ]
    targets = [
        {"target_id": "3", "id": 3, "title": "Release 1.2", "state": "OPEN", "due_at": "2026-10-31T00:00:00Z", "open_items": 3, "closed_items": 4, "url": "https://example.invalid/milestone/3"},
        {"target_id": "2", "id": 2, "title": "Release 1.1", "state": "CLOSED", "due_at": "2026-08-15T00:00:00Z", "open_items": 0, "closed_items": 9, "url": "https://example.invalid/milestone/2"},
    ]
    releases = [{"tag": "v1.1.0", "name": "Release 1.1", "published_at": "2026-08-16T10:00:00Z", "prerelease": False, "url": "https://example.invalid/releases/v1.1.0"}]
    revisions = []
    for commit in commits[-8:]:
        state = "VERIFY_PASS"
        attempts = [{"attempt": 1, "state": "VERIFY_PASS"}]
        history = "PASS_ONLY_OBSERVED"
        if commit["title"].endswith("15"):
            attempts = [{"attempt": 1, "state": "VERIFY_FAIL"}, {"attempt": 2, "state": "VERIFY_PASS"}]
            history = "FAILURE_OBSERVED"
        revisions.append(
            {
                "revision": commit["sha"],
                "committed_at": commit["committed_at"],
                "parents": [
                    {
                        "parent_id": f"github_actions:workflow_run:{900 + len(revisions)}",
                        "kind": "github_actions_workflow_run",
                        "name": "CI",
                        "event": "push",
                        "current_attempt": len(attempts),
                        "current_state": state,
                        "attempts_observed": attempts,
                        "attempts_complete": True,
                        "history_state": history,
                        "url": "https://example.invalid/actions/runs/900",
                    }
                ],
                "current_verdict": state,
                "history_state": history,
                "historical_contribution": "VERIFY_FAIL" if history == "FAILURE_OBSERVED" else "VERIFY_PASS",
                "history_provenance": "ATTEMPT_LEVEL",
                "history_complete": True,
            }
        )
    window_revisions = [c for c in commits if c["committed_at"] >= "2026-08-22"]
    by_sha = {r["revision"]: r for r in revisions}
    series = [by_sha.get(c["sha"], {"revision": c["sha"], "committed_at": c["committed_at"], "parents": [], "current_verdict": None, "history_state": "NO_DECISIVE_OBSERVED", "historical_contribution": None, "history_provenance": None, "history_complete": True}) for c in window_revisions]

    result = ObservationSet(subject=SUBJECT, observed_at=OBSERVED_AT)
    result.add(obs(normalize.INV_REPO, {"id": 123456, "full_name": "acme/widget", "default_branch": "master", "visibility": "public", "has_issues": True, "archived": False, "pushed_at": "2026-09-05T08:00:00Z", "html_url": "https://example.invalid/acme/widget"}, "record"))
    result.add(obs(normalize.INV_COMMITS, commits, "series", {"window_start": "2026-08-08T12:00:00Z", "window_end": OBSERVED_AT, "complete": True, "branch": "master"}))
    result.add(obs(normalize.INV_CRS, change_requests, "series", {"open_complete": True, "window_complete": True, "window_start": "2026-08-08T12:00:00Z"}))
    result.add(obs(normalize.INV_ISSUES, issues, "series", {"open_complete": True, "window_complete": True, "window_start": "2026-08-08T12:00:00Z"}))
    result.add(obs(normalize.INV_BRANCHES, branches, "series", {"complete": True, "heads_resolved": True, "head_lookups": 2}))
    result.add(obs(normalize.INV_TARGETS, targets, "series", {"complete": True, "source": "milestones"}))
    result.add(obs(normalize.INV_RELEASES, releases, "series", {"recent_only": True, "limit": 30, "complete": True}))
    result.add(obs(normalize.CI_CONFIGURED, True, "boolean"))
    result.add(obs(normalize.CI_REVISIONS, series, "series", {"window_start": "2026-08-22T12:00:00Z", "window_end": OBSERVED_AT, "runs_complete": True, "attempts_complete": True, "outcome_map_version": "devostasis.ci-outcomes.github.v1", "surface": "github_actions"}))
    result.finalize_receipt(
        Receipt(
            run_id="run-20260905T120000Z-acme-widget",
            collector_version="devostasis.github.v1",
            target=SUBJECT,
            started_at=OBSERVED_AT,
            ended_at=OBSERVED_AT,
            capability_notes=["CI_SURFACE:GITHUB_ACTIONS_ONLY", "CHECKS_SURFACE_NOT_COLLECTED"],
            config_hash="example",
        )
    )
    return result


def main() -> int:
    examples = ROOT / "examples"
    observation_set = build_observation_set()
    observation_set.save(examples / "observations.json")

    project = single_project("acme/widget", config_version="example-1", debt={"labels": ["type:refactor"], "mapping_version": "example-1"})
    normalize.derive(observation_set, project)
    store_dir = examples / ".store"
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = FilesystemHistoryStore(store_dir)
    bundle = build_from_observations(project, observation_set, store, run_meta={"example": True})
    target = examples / "sample-bundle"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name, data in bundle.members.items():
        (target / name).write_bytes(data)
    shutil.rmtree(store_dir, ignore_errors=True)
    print(f"wrote {examples / 'observations.json'} and {target} (bundle {bundle.bundle_id[:12]})")
    print(" ".join(f"{k}={v}" for k, v in bundle.bands().items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
