"""GitHub verification normalization: PV-CI-NORM-001 outcomes, provider-native parent
identity (workflow_run.id + run_attempt, check_suite.id) and PV-CI-UNIT-004
revision semantics.

* one immutable revision contributes at most one historical verdict;
* the greatest observed attempt governs a parent's current state;
* history is failure-sticky: any observed VERIFY_FAIL for a revision keeps its
  historical contribution VERIFY_FAIL while the revision is in the window;
* attempts are never independent samples;
* history is known only where every attempt is: an Actions run whose attempts
  cover 1..latest. A check suite keeps its id across re-requests and shows
  only the latest outcome, so favorable parent-level or incomplete evidence is
  ``UNKNOWN_HISTORY``, never a reconstructed pass (PV-CI-UNIT-004 R52,
  PV-HIST-002 HIST-06). An observed failure is proven on any surface.
"""

from __future__ import annotations

from typing import Any

VERIFY_PASS = "VERIFY_PASS"
VERIFY_FAIL = "VERIFY_FAIL"
VERIFY_UNRESOLVED = "VERIFY_UNRESOLVED"
NON_VERIFY_TERMINAL = "NON_VERIFY_TERMINAL"
NOT_EXECUTED = "NOT_EXECUTED"
UNKNOWN = "UNKNOWN"

OUTCOME_MAP_VERSION = "devostasis.ci-outcomes.github.v1"
OUTCOME_MAP = {
    "success": VERIFY_PASS,
    "failure": VERIFY_FAIL,
    "timed_out": VERIFY_FAIL,
    "cancelled": NON_VERIFY_TERMINAL,
    "neutral": NON_VERIFY_TERMINAL,
    "action_required": NON_VERIFY_TERMINAL,
    "stale": NON_VERIFY_TERMINAL,
    "skipped": NOT_EXECUTED,
}

PRECEDENCE = [UNKNOWN, VERIFY_FAIL, VERIFY_UNRESOLVED, VERIFY_PASS, NON_VERIFY_TERMINAL, NOT_EXECUTED]

ATTEMPT_LEVEL = "ATTEMPT_LEVEL"
PARENT_LEVEL_ONLY = "PARENT_LEVEL_ONLY"
ACTIONS_KIND = "github_actions_workflow_run"
UNKNOWN_HISTORY = "UNKNOWN_HISTORY"


def normalize_outcome(status: str | None, conclusion: str | None) -> str:
    if status != "completed":
        return VERIFY_UNRESOLVED
    if conclusion is None:
        return UNKNOWN
    return OUTCOME_MAP.get(conclusion, UNKNOWN)


def compose_current(states: list[str]) -> str | None:
    if not states:
        return None
    for candidate in PRECEDENCE:
        if candidate in states:
            return candidate
    return UNKNOWN


def history_state(states: list[str]) -> str:
    if VERIFY_FAIL in states:
        return "FAILURE_OBSERVED"
    if VERIFY_PASS in states:
        return "PASS_ONLY_OBSERVED"
    return "NO_DECISIVE_OBSERVED"


def known_history_state(states: list[str], complete: bool) -> str:
    """The state evidence proves: a failure always, anything favorable only over complete attempts."""
    if VERIFY_FAIL in states:
        return "FAILURE_OBSERVED"
    if not complete:
        return UNKNOWN_HISTORY
    return history_state(states)


def contribution(state: str) -> str | None:
    return {"FAILURE_OBSERVED": VERIFY_FAIL, "PASS_ONLY_OBSERVED": VERIFY_PASS}.get(state)


def actions_parent(run: dict[str, Any], prior_attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """One GitHub Actions workflow run (all attempts) as one verification parent."""
    attempts = []
    for attempt in prior_attempts:
        attempts.append({"attempt": int(attempt["run_attempt"]), "state": normalize_outcome(attempt.get("status"), attempt.get("conclusion"))})
    latest_attempt = int(run.get("run_attempt") or 1)
    attempts.append({"attempt": latest_attempt, "state": normalize_outcome(run.get("status"), run.get("conclusion"))})
    attempts.sort(key=lambda a: a["attempt"])
    current = attempts[-1]["state"]
    states = [a["state"] for a in attempts]
    complete = len(attempts) == latest_attempt
    return {
        "parent_id": f"github_actions:workflow_run:{run['id']}",
        "kind": "github_actions_workflow_run",
        "name": run.get("name") or f"workflow {run.get('workflow_id')}",
        "event": run.get("event"),
        "current_attempt": latest_attempt,
        "current_state": current,
        "attempts_observed": attempts,
        "attempts_complete": complete,
        "history_state": known_history_state(states, complete),
        "url": run.get("html_url"),
    }


def check_suite_parent(suite: dict[str, Any]) -> dict[str, Any]:
    state = normalize_outcome(suite.get("status"), suite.get("conclusion"))
    app = (suite.get("app") or {}).get("slug") or "unknown-app"
    return {
        "parent_id": f"github_checks:check_suite:{suite['id']}",
        "kind": "github_check_suite",
        "name": app,
        "event": None,
        "current_attempt": None,
        "current_state": state,
        "attempts_observed": [{"attempt": None, "state": state}],
        "attempts_complete": False,
        "history_state": known_history_state([state], False),
        "url": suite.get("url"),
    }


def build_revision_records(
    commits: list[dict[str, Any]],
    parents_by_sha: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """One canonical record per immutable revision, ordered by (committed_at, sha)."""
    records = []
    for commit in sorted(commits, key=lambda c: (c["committed_at"], c["sha"])):
        parents = sorted(parents_by_sha.get(commit["sha"], []), key=lambda p: p["parent_id"])
        current_states = [p["current_state"] for p in parents]
        all_states = [a["state"] for p in parents for a in p["attempts_observed"]]
        complete = all(p["kind"] == ACTIONS_KIND and p.get("attempts_complete") is True for p in parents)
        history = known_history_state(all_states, complete) if parents else "NO_DECISIVE_OBSERVED"
        provenance = None
        if parents:
            provenance = ATTEMPT_LEVEL if all(p["kind"] == ACTIONS_KIND for p in parents) else PARENT_LEVEL_ONLY
        records.append(
            {
                "revision": commit["sha"],
                "committed_at": commit["committed_at"],
                "parents": parents,
                "current_verdict": compose_current(current_states),
                "history_state": history,
                "historical_contribution": contribution(history),
                "history_provenance": provenance,
                "history_complete": complete,
            }
        )
    return records
