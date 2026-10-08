"""Durable Integrity revision history across bundles (PV-HIST-002, accepted by PV-REV-HIST-002).

A provider forgets: a re-run hides the attempt that failed behind the one that
passed on a parent-level surface, and retention removes old runs altogether.
Integrity's history is a set property of one immutable revision
(``ANY_FAIL_ELSE_ANY_PASS_PER_IMMUTABLE_REVISION``, PV-CI-UNIT-004), so what
one bundle proved about a revision must survive into the next one while the
revision is in the 14-day window.

The carrier is the union of every attempt observed per parent per revision.
Each bundle's union is the previous bundle's union plus what the provider
shows now, which makes it the complete-chain-equivalent reduction section C
of the contract allows: it holds every history fact of the intervening chain
and selects nothing. It is carried in two canonical places:

* ``derived.revision_history`` of the Integrity result in ``snapshot.json``,
  the durable output, present in every bundle whatever its observations
  setting;
* ``ci.revision_history_carried``, the input observation a build adds from its
  immediate predecessor before evaluating, so the bundle names the source it
  consumed and a replay of its observations reproduces its evaluation.

The state of a revision is a function of its union alone:

* a ``VERIFY_FAIL`` attempt anywhere is ``FAILURE_OBSERVED``, absorbing, from
  current evidence or durable history alike (HIST-01, -02, -05, -09);
* otherwise the history is known only when every parent's attempts are
  complete: an Actions run whose attempts cover 1..latest. A check suite never
  is, because a re-request keeps its id and hides the earlier outcome, so
  favorable parent-level or incomplete evidence is ``UNKNOWN_HISTORY``, never
  a reconstructed pass (R52, HIST-06, HIST-19);
* then ``PASS_ONLY_OBSERVED`` or ``NO_DECISIVE_OBSERVED``.

A revision whose prior history could not be carried under the current
lineage stays ``UNKNOWN_HISTORY`` until complete current evidence repairs it
(HIST-15). Current verdicts are never carried: they belong to the current
observation (HIST-16).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import timeutil
from .observations import AVAILABLE, FRESH, PARTIAL, UNAVAILABLE, UNKNOWN, Observation, ObservationSet
from .policy import INTEGRITY

# The history-semantics lineage of this implementation: provider outcome
# normalization (devostasis.ci-outcomes.github.v1), parent and attempt
# identity, the union reduction and the PV-CI-UNIT-004 state mapping with
# R52's completeness rule. Only a change to one of those moves it (section 5).
LINEAGE = "devostasis.ci-history.v2"
# The revision records 0.1.x bundles carry in ci.revision_verdicts_14d: the
# same outcome map and parent identity with every observed attempt kept, so a
# union can be replayed from them deterministically (HIST-13).
REPLAYABLE_LINEAGE = "devostasis.ci-history.v1"

CARRIED = "ci.revision_history_carried"
REVISIONS = "ci.revision_verdicts_14d"

FAILURE_OBSERVED = "FAILURE_OBSERVED"
PASS_ONLY_OBSERVED = "PASS_ONLY_OBSERVED"
NO_DECISIVE_OBSERVED = "NO_DECISIVE_OBSERVED"
UNKNOWN_HISTORY = "UNKNOWN_HISTORY"
STATES = (FAILURE_OBSERVED, PASS_ONLY_OBSERVED, NO_DECISIVE_OBSERVED, UNKNOWN_HISTORY)
CONTRIBUTION = {FAILURE_OBSERVED: "VERIFY_FAIL", PASS_ONLY_OBSERVED: "VERIFY_PASS", NO_DECISIVE_OBSERVED: None, UNKNOWN_HISTORY: None}

ACTIONS_KIND = "github_actions_workflow_run"

# Where the carried history came from.
SOURCE_CARRIED = "CARRIED"
SOURCE_BASELINE = "BASELINE"
SOURCE_GAP = "HISTORY_GAP"
SOURCE_NONE = "NOT_STATED"
SOURCE_MALFORMED = "MALFORMED"
BASIS_SNAPSHOT = "SNAPSHOT"
BASIS_SERIES = "REPLAYED_SERIES"

NO_PREVIOUS_BUNDLE = "NO_PREVIOUS_BUNDLE"
PREDECESSOR_NOT_EARLIER = "PREDECESSOR_NOT_EARLIER"
PREDECESSOR_CARRIES_NO_HISTORY = "PREDECESSOR_CARRIES_NO_HISTORY"
HISTORY_GAP = "HISTORY_GAP"


class HistoryShapeError(ValueError):
    """Carried history that is not the shape its lineage declares: corrupt persisted history."""


# --------------------------------------------------------------------------- the union


def _attempt_key(attempt: dict[str, Any]) -> tuple[int, int, str]:
    number = attempt.get("attempt")
    return (0 if number is None else 1, number if isinstance(number, int) else 0, str(attempt.get("state")))


def _attempts(raw: Any, where: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise HistoryShapeError(f"{where}: attempts is not a list")
    seen: dict[tuple[Any, str], dict[str, Any]] = {}
    for attempt in raw:
        if not isinstance(attempt, dict) or not isinstance(attempt.get("state"), str):
            raise HistoryShapeError(f"{where}: an attempt carries no state")
        number = attempt.get("attempt")
        if number is not None and (isinstance(number, bool) or not isinstance(number, int) or number < 1):
            raise HistoryShapeError(f"{where}: attempt number {number!r} is not a positive integer")
        seen[(number, attempt["state"])] = {"attempt": number, "state": attempt["state"]}
    return sorted(seen.values(), key=_attempt_key)


def _parent(parent_id: Any, kind: Any, latest: Any, attempts: Any, where: str) -> dict[str, Any]:
    if not isinstance(parent_id, str) or not parent_id:
        raise HistoryShapeError(f"{where}: a parent carries no id")
    if not isinstance(kind, str) or not kind:
        raise HistoryShapeError(f"{where}: parent {parent_id} carries no kind")
    if latest is not None and (isinstance(latest, bool) or not isinstance(latest, int) or latest < 1):
        raise HistoryShapeError(f"{where}: parent {parent_id} latest attempt {latest!r} is not a positive integer")
    return {"parent_id": parent_id, "kind": kind, "latest_attempt": latest, "attempts": _attempts(attempts, f"{where} parent {parent_id}")}


def parent_from_current(parent: Any, where: str) -> dict[str, Any]:
    """A parent of a current revision record (github_ci shape) as durable evidence."""
    if not isinstance(parent, dict):
        raise HistoryShapeError(f"{where}: a parent is not an object")
    return _parent(parent.get("parent_id"), parent.get("kind"), parent.get("current_attempt"), parent.get("attempts_observed"), where)


def parents_from_groups(groups: Any, where: str) -> list[dict[str, Any]]:
    """The parents of a carried union record, which the carrier stores grouped by shape."""
    if not isinstance(groups, list):
        raise HistoryShapeError(f"{where}: parent_groups is not a list")
    parents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("parent_ids"), list) or not group["parent_ids"]:
            raise HistoryShapeError(f"{where}: a parent group names no parents")
        for parent_id in group["parent_ids"]:
            if parent_id in seen:
                raise HistoryShapeError(f"{where}: parent {parent_id} is in two groups")
            seen.add(parent_id)
            parents.append(_parent(parent_id, group.get("kind"), group.get("latest_attempt"), group.get("attempts"), where))
    return parents


def parent_groups(parents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parents of one shape (kind, greatest attempt, observed attempts) stored once with their ids.

    A busy default branch attaches hundreds of single-attempt runs to one
    revision; written one object per run, the carrier of such a repository
    was hundreds of kilobytes. The grouping loses nothing: every parent keeps
    its identity and exactly its own attempts.
    """
    groups: dict[tuple, dict[str, Any]] = {}
    for parent in parents:
        key = (parent["kind"], -1 if parent["latest_attempt"] is None else parent["latest_attempt"], tuple(_attempt_key(a) for a in parent["attempts"]))
        group = groups.setdefault(key, {"kind": parent["kind"], "latest_attempt": parent["latest_attempt"], "attempts": parent["attempts"], "parent_ids": []})
        group["parent_ids"].append(parent["parent_id"])
    ordered = [groups[key] for key in sorted(groups)]
    for group in ordered:
        group["parent_ids"] = sorted(group["parent_ids"])
    return ordered


def merge_parents(*groups: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """The union of parents by identity: every attempt either side observed, the greatest attempt number either saw."""
    merged: dict[str, dict[str, Any]] = {}
    conflicts: list[str] = []
    for group in groups:
        for parent in group:
            known = merged.get(parent["parent_id"])
            if known is None:
                merged[parent["parent_id"]] = {**parent, "attempts": list(parent["attempts"])}
                continue
            if known["kind"] != parent["kind"]:
                conflicts.append(f"PARENT_KIND_CONFLICT:{parent['parent_id']}")
            numbers = [n for n in (known["latest_attempt"], parent["latest_attempt"]) if n is not None]
            known["latest_attempt"] = max(numbers) if numbers else None
            known["attempts"] = _attempts(known["attempts"] + parent["attempts"], parent["parent_id"])
    return [merged[key] for key in sorted(merged)], sorted(set(conflicts))


def parent_complete(parent: dict[str, Any]) -> bool:
    """Every attempt of an Actions run, 1..latest, is in the union. A check suite never is."""
    latest = parent.get("latest_attempt")
    if parent.get("kind") != ACTIONS_KIND or not isinstance(latest, int) or latest < 1:
        return False
    numbers = {a["attempt"] for a in parent["attempts"] if isinstance(a.get("attempt"), int)}
    return set(range(1, latest + 1)) <= numbers


def union_state(parents: list[dict[str, Any]], unresolved: list[str]) -> tuple[str, bool]:
    """The PV-CI-UNIT-004 state of a revision's union, and whether its history is complete."""
    states = [a["state"] for p in parents for a in p["attempts"]]
    complete = not unresolved and all(parent_complete(p) for p in parents)
    if "VERIFY_FAIL" in states:
        return FAILURE_OBSERVED, complete
    if not complete:
        return UNKNOWN_HISTORY, False
    if "VERIFY_PASS" in states:
        return PASS_ONLY_OBSERVED, True
    return NO_DECISIVE_OBSERVED, True


def union_record(revision: str, committed_at: str, parents: list[dict[str, Any]], unresolved: list[str]) -> dict[str, Any]:
    state, complete = union_state(parents, unresolved)
    record: dict[str, Any] = {
        "revision": revision,
        "committed_at": committed_at,
        "parents": parents,
        "history_state": state,
        "historical_contribution": CONTRIBUTION[state],
        "history_complete": complete,
    }
    if unresolved:
        record["unresolved"] = sorted(set(unresolved))
    return record


def encode(record: dict[str, Any]) -> dict[str, Any]:
    """A union record as the carrier stores it: its parents grouped by shape."""
    encoded = {key: value for key, value in record.items() if key != "parents"}
    encoded["parent_groups"] = parent_groups(record["parents"])
    return encoded


def current_history(parents: list[dict[str, Any]]) -> tuple[str, bool]:
    """The state current evidence proves on its own (no durable history), for the per-bundle revision record."""
    durable = [parent_from_current(p, "current") for p in parents]
    return union_state(durable, [])


# --------------------------------------------------------------------------- reading carried history


def _carried_records(value: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The carried union records, replayed or marked unresolved according to their lineage."""
    if not isinstance(value, dict):
        raise HistoryShapeError("the carried history is not an object")
    lineage = value.get("lineage")
    raw = value.get("records")
    if not isinstance(lineage, str) or not lineage or not isinstance(raw, list):
        raise HistoryShapeError("the carried history names no lineage or no records")
    source = {
        "lineage": lineage,
        "bundle_id": value.get("source_bundle_id"),
        "observed_at": value.get("source_observed_at"),
        "basis": value.get("basis"),
    }
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for position, record in enumerate(raw):
        where = f"carried record {position}"
        if not isinstance(record, dict) or not isinstance(record.get("revision"), str) or not record["revision"] or not isinstance(record.get("committed_at"), str):
            raise HistoryShapeError(f"{where}: no revision or committed_at")
        if record["revision"] in seen:
            raise HistoryShapeError(f"{where}: duplicate revision {record['revision']}")
        seen.add(record["revision"])
        timeutil.parse_ts(record["committed_at"])
        if lineage == LINEAGE:
            parents = parents_from_groups(record.get("parent_groups") or [], where)
            unresolved = record.get("unresolved") or []
            if not isinstance(unresolved, list) or not all(isinstance(reason, str) for reason in unresolved):
                raise HistoryShapeError(f"{where}: unresolved is not a list of reasons")
            records.append(union_record(record["revision"], record["committed_at"], merge_parents(parents)[0], unresolved))
        elif lineage == REPLAYABLE_LINEAGE:
            # HIST-13: replayed from the canonical attempts the older record kept,
            # never copied from the state it derived under the older semantics.
            parents = [parent_from_current(p, where) for p in record.get("parents") or []]
            records.append(union_record(record["revision"], record["committed_at"], merge_parents(parents)[0], []))
        else:
            # HIST-15: no replay and no accepted migration from this lineage; the
            # old record stays historical evidence in its own bundle, and the
            # revision's history is unknown until current evidence repairs it.
            records.append(union_record(record["revision"], record["committed_at"], [], [f"LINEAGE_INCOMPATIBLE:{lineage}"]))
    return records, source


# --------------------------------------------------------------------------- reconciliation


@dataclass
class Reconciled:
    """The reconciled history of one evaluation."""

    records: dict[str, dict[str, Any]]
    source: dict[str, Any]
    problems: list[str] = field(default_factory=list)

    def output(self) -> dict[str, Any]:
        """The durable carrier the next bundle consumes: ``derived.revision_history``.

        Only revisions that carry history are in it: a revision without a
        verification parent and without an unresolved prior adds nothing a
        later bundle could need.
        """
        bearing = [r for r in self.records.values() if r["parents"] or r.get("unresolved")]
        ordered = sorted(bearing, key=lambda r: (r["committed_at"], r["revision"]))
        return {"lineage": LINEAGE, "source": dict(self.source), "records": [encode(record) for record in ordered]}


def _series_records(series: Observation | None) -> tuple[list[dict[str, Any]] | None, bool]:
    """The current revision records and whether they are the whole 14-day inventory."""
    if series is None or series.status not in (AVAILABLE, PARTIAL) or series.freshness != FRESH or not isinstance(series.value, list):
        return None, False
    return [r for r in series.value if isinstance(r, dict) and isinstance(r.get("revision"), str)], series.status == AVAILABLE


def reconcile(obs: ObservationSet) -> Reconciled:
    """Combine the carried union with what the provider shows now (section D of the contract)."""
    observed_at = timeutil.parse_ts(obs.observed_at)
    window_start = timeutil.minus_days(observed_at, INTEGRITY["window_days"])
    carried_obs = obs.get(CARRIED)
    carried: list[dict[str, Any]] = []
    problems: list[str] = []
    if carried_obs is None:
        source: dict[str, Any] = {"status": SOURCE_NONE}
    elif carried_obs.status == UNAVAILABLE and carried_obs.reason_code == NO_PREVIOUS_BUNDLE:
        source = {"status": SOURCE_BASELINE, "reason": NO_PREVIOUS_BUNDLE}
    elif carried_obs.status != AVAILABLE or carried_obs.freshness != FRESH:
        # HIST-08: a required predecessor that is missing, unverifiable or not
        # earlier is a gap; nothing is carried across it and nothing older is
        # chosen instead (HIST-20).
        source = {"status": SOURCE_GAP, "reason": carried_obs.reason_code or carried_obs.status}
        if isinstance(carried_obs.evidence_ref, dict) and carried_obs.evidence_ref.get("previous_bundle_id"):
            source["bundle_id"] = carried_obs.evidence_ref["previous_bundle_id"]
    else:
        try:
            carried, detail = _carried_records(carried_obs.value)
            source = {"status": SOURCE_CARRIED, **detail}
        except (HistoryShapeError, ValueError, TypeError) as exc:
            source = {"status": SOURCE_MALFORMED}
            problems.append(f"REVISION_HISTORY_CARRY_MALFORMED:{exc}")

    current, inventory_complete = _series_records(obs.get(REVISIONS))
    current_by_rev = {r["revision"]: r for r in current or []}
    records: dict[str, dict[str, Any]] = {}

    for prior in carried:
        if timeutil.parse_ts(prior["committed_at"]) < window_start:
            continue  # HIST-10: aged out of the 14-day window
        if inventory_complete and prior["revision"] not in current_by_rev:
            continue  # the complete inventory no longer holds it: off the default branch
        records[prior["revision"]] = prior

    for revision, record in current_by_rev.items():
        committed_at = record.get("committed_at")
        if not isinstance(committed_at, str):
            problems.append(f"REVISION_RECORD_INCONSISTENT:{revision}")
            continue
        try:
            visible = [parent_from_current(p, f"revision {revision}") for p in record.get("parents") or []]
        except HistoryShapeError as exc:
            problems.append(f"REVISION_RECORD_INCONSISTENT:{revision}:{exc}")
            continue
        prior = records.get(revision)
        prior_parents = prior["parents"] if prior else []
        unresolved = list(prior.get("unresolved") or []) if prior else []
        if unresolved and visible and all(parent_complete(p) for p in visible):
            # HIST-15, HIST-19: complete current evidence repairs a prior that
            # could not be carried; anything less leaves the revision unknown.
            unresolved = []
        parents, conflicts = merge_parents(prior_parents, visible)
        records[revision] = union_record(revision, committed_at, parents, unresolved + conflicts)
    return Reconciled(records=records, source=source, problems=problems)


# --------------------------------------------------------------------------- the carried observation


def _in_window(records: Any, observed_at: str) -> Any:
    """The records a build can consume: those still inside the 14-day window it evaluates.

    A record outside the window would be dropped by the reconciliation anyway
    (HIST-10), so carrying it adds bytes and no evidence. A record whose time
    cannot be read is kept, so the reconciliation reports it as malformed
    instead of it disappearing here.
    """
    if not isinstance(records, list):
        return records
    window_start = timeutil.minus_days(timeutil.parse_ts(observed_at), INTEGRITY["window_days"])
    kept = []
    for record in records:
        try:
            if timeutil.parse_ts(record["committed_at"]) < window_start:
                continue
        except (KeyError, TypeError, ValueError):
            pass
        kept.append(record)
    return kept


def _replay_source(record: Any) -> Any:
    """A 0.1.x revision record reduced to what its replay reads: identity, time and every observed attempt."""
    if not isinstance(record, dict) or not isinstance(record.get("parents"), list):
        return record
    parents = []
    for parent in record["parents"]:
        if not isinstance(parent, dict):
            parents.append(parent)
            continue
        parents.append({key: parent.get(key) for key in ("parent_id", "kind", "current_attempt", "attempts_observed")})
    return {"revision": record.get("revision"), "committed_at": record.get("committed_at"), "parents": parents}


def carried_observation(
    comparison_status: str,
    previous_bundle_id: str | None,
    previous_manifest: dict[str, Any] | None,
    previous_snapshot: dict[str, Any] | None,
    previous_observations: dict[str, Any] | None,
    reasons: list[str],
    observed_at: str,
) -> Observation:
    """The history a build consumes: its immediate predecessor's union, or why there is none.

    Section C: the source is the verified immediately previous successful
    bundle of the same immutable project, the one the comparison already
    resolved; when it is missing, unverifiable or not earlier, the answer is a
    gap, never an older bundle.
    """
    common = {
        "provider": "history",
        "collected_at": observed_at,
        "adapter_version": LINEAGE,
        "source_ref": f"bundle:{previous_bundle_id}" if previous_bundle_id else "store:none",
    }
    if comparison_status == "BASELINE" or previous_bundle_id is None:
        return Observation(observation_id=CARRIED, status=UNAVAILABLE, value_type="record", reason_code=NO_PREVIOUS_BUNDLE, **common)
    evidence = {"previous_bundle_id": previous_bundle_id}
    if comparison_status == "HISTORY_GAP" or previous_manifest is None or previous_snapshot is None:
        return Observation(observation_id=CARRIED, status=UNKNOWN, value_type="record", reason_code=HISTORY_GAP, evidence_ref=evidence, **common)
    if any(str(reason).startswith("NON_MONOTONIC_OBSERVATION") for reason in reasons):
        return Observation(observation_id=CARRIED, status=UNKNOWN, value_type="record", reason_code=PREDECESSOR_NOT_EARLIER, evidence_ref=evidence, **common)
    source = {"source_bundle_id": previous_bundle_id, "source_observed_at": previous_manifest.get("observed_at")}
    integrity = next((v for v in previous_snapshot.get("vitals") or [] if isinstance(v, dict) and v.get("vital_id") == "integrity"), None)
    durable = (integrity or {}).get("derived", {}).get("revision_history") if isinstance((integrity or {}).get("derived"), dict) else None
    if isinstance(durable, dict) and "lineage" in durable:
        value = {"lineage": durable.get("lineage"), "records": _in_window(durable.get("records"), observed_at), "basis": BASIS_SNAPSHOT, **source}
        return Observation(observation_id=CARRIED, status=AVAILABLE, value_type="record", value=value, evidence_ref=evidence, **common)
    series = None
    if isinstance(previous_observations, dict):
        series = next((o for o in previous_observations.get("observations") or [] if isinstance(o, dict) and o.get("observation_id") == REVISIONS), None)
    if series is not None:
        # A bundle older than this carrier: replay its revision records.
        records = series.get("value") if series.get("status") in (AVAILABLE, PARTIAL) and isinstance(series.get("value"), list) else []
        replayable = [_replay_source(record) for record in _in_window(records, observed_at)]
        value = {"lineage": REPLAYABLE_LINEAGE, "records": replayable, "basis": BASIS_SERIES, "source_series_status": series.get("status"), **source}
        return Observation(observation_id=CARRIED, status=AVAILABLE, value_type="record", value=value, evidence_ref=evidence, **common)
    return Observation(observation_id=CARRIED, status=UNKNOWN, value_type="record", reason_code=PREDECESSOR_CARRIES_NO_HISTORY, evidence_ref=evidence, **common)


def with_carried_history(obs: ObservationSet, carried: Observation) -> ObservationSet:
    """A copy of ``obs`` with the carried history added; the caller's set is left as it was."""
    copy = ObservationSet(subject=obs.subject, observed_at=obs.observed_at, observations=obs.sorted(), receipt=obs.receipt)
    copy.add(carried)
    return copy


def carried_source_bundle(obs: ObservationSet) -> str | None:
    """The bundle a stated carried history came from, when it names one."""
    carried = obs.get(CARRIED)
    if carried is None:
        return None
    if isinstance(carried.value, dict) and carried.value.get("source_bundle_id"):
        return str(carried.value["source_bundle_id"])
    if isinstance(carried.evidence_ref, dict) and carried.evidence_ref.get("previous_bundle_id"):
        return str(carried.evidence_ref["previous_bundle_id"])
    return None
