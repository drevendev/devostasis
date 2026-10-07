"""INTEGRITY: automated verification stability of recent immutable revisions.

The adapter produces one canonical record per default-branch revision of the
14-day window (PV-CI-UNIT-004 semantics: one contribution per immutable
revision, failure-sticky history, current verdict independent of history).
This evaluator only counts and classifies; it never re-interprets provider
outcomes.

Rule ``integrity.bands.v1`` carries three accepted repairs on top of the V0
band table, none of which moves a threshold or a window:

* **PV-REV-INTEGRITY-UNKNOWN-001** (INT-UNKNOWN-01..06): a newest in-scope
  revision whose current verdict is ``UNKNOWN`` never inherits an older
  decisive verdict. ``UNKNOWN`` is the absence of an observation, so the Vital
  is ``UNKNOWN`` with no band; historical decisive evidence stays in
  ``derived`` and is never reconstructed as a pass. Positively observed
  ``NOT_EXECUTED`` and ``NON_VERIFY_TERMINAL`` keep the accepted fallback to
  the latest decisive revision.
* **PV-REV-TEST-003**: a required revision series with acquisition status
  ``PARTIAL`` has no accepted degraded path. It is ``UNKNOWN`` with no band;
  the counts of the truncated evidence stay visible, marked as such.
* **PV-REV-TEST-VECTORS-002** (R1, R2): one to three decisive revisions are a
  ``SPARSE`` sample, four or more an ``ESTABLISHED`` one, and
  ``CI_SPARSE_SAMPLE`` is emitted whenever the sample is sparse.

* **PV-INTEGRITY-TOTALITY-001** (accepted by PV-REV-INT-TOTALITY-001,
  INT-TOTAL-01..14): a newest revision still being verified is never spoken
  for by an older verdict. Only an already-true established historical
  FAILING predicate names a band, ``DEGRADED / FAILING / EXACT``; every other
  unresolved region is ``UNKNOWN`` with no band. The accepted contract
  deliberately defines no ``possible_bands`` reachability algorithm, and the
  one this rule version first carried (#12 finding 3) could omit the band it
  emitted. A positively unconfigured repository whose only recent evidence is
  non-decisive is ``UNINSTRUMENTED``, with that evidence kept visible.

A required series that cannot be used is ``UNKNOWN`` whatever ``ci.configured``
says, because "no verification evidence" is exactly what it cannot establish,
and a verdict outside the canonical vocabulary is read as ``UNKNOWN``.

Rule ``integrity.bands.v1+ci-unit-004+hist-002`` (0.2.0) counts history over
the durable union of **PV-HIST-002** (accepted by PV-REV-HIST-002, HIST-01..20)
instead of over what the provider still shows: a failure one bundle proved
stays in the counts while its revision is in the window, whatever the provider
shows later, and favorable evidence that cannot prove every attempt
(parent-level check suites, incomplete attempts) is ``UNKNOWN_HISTORY``, never
a pass (R52). Any revision whose history is unknown makes the Vital
``UNKNOWN``: T9 puts unknown history above every conservative branch, so no
band is derived around it. The current verdict is still the current
observation's alone (HIST-16), and the reconciled union is emitted in
``derived.revision_history`` on every path, so the next bundle can carry it
even across an evaluation that claimed no band (see ``revision_history``).
"""

from __future__ import annotations

from typing import Any

from ..canonical import ratio
from ..observations import AVAILABLE, FRESH, PARTIAL, ObservationSet
from ..policy import INTEGRITY
from ..revision_history import CARRIED, SOURCE_GAP, UNKNOWN_HISTORY, Reconciled, reconcile
from .common import (
    EVAL_AVAILABLE,
    EVAL_DEGRADED,
    EVAL_UNKNOWN,
    SEM_EXACT,
    VitalResult,
    input_meta,
)

VITAL_ID = "integrity"
VITAL_VERSION = "PV-VITALS-V1-002/integrity"
RULE_ID = "integrity.bands.v1+ci-unit-004+hist-002"
HISTORY_RULE = "PV-HIST-002"
UNKNOWN_RULE = "PV-REV-INTEGRITY-UNKNOWN-001"
PARTIAL_RULE = "PV-REV-TEST-003"
SPARSE_RULE = "PV-REV-TEST-VECTORS-002"
TOTALITY_RULE = "PV-INTEGRITY-TOTALITY-001"
UNRESOLVED_DIAGNOSTIC = "CI_CURRENT_VERIFY_UNRESOLVED"
UNINSTRUMENTED_WITH_HISTORY = "CI_UNINSTRUMENTED_WITH_RECENT_NONDECISIVE_HISTORY"
BANDS = ["UNINSTRUMENTED", "NO_RECENT_RUNS", "NO_DECISIVE_RUNS", "SPARSE", "SPARSE_MIXED", "FLAKY", "CLEAN", "FAILING"]

CONFIGURED = "ci.configured"
REVISIONS = "ci.revision_verdicts_14d"
IDS = [CONFIGURED, REVISIONS, CARRIED]

SHARED = ["CI_VERIFICATION"]
GROUPS = ["INTEGRITY_ONLY"]

VERIFY_PASS = "VERIFY_PASS"
VERIFY_FAIL = "VERIFY_FAIL"
VERIFY_UNRESOLVED = "VERIFY_UNRESOLVED"
NON_VERIFY_TERMINAL = "NON_VERIFY_TERMINAL"
NOT_EXECUTED = "NOT_EXECUTED"
VERDICT_UNKNOWN = "UNKNOWN"
DECISIVE = {VERIFY_PASS, VERIFY_FAIL}
NON_DECISIVE_TERMINAL = {NON_VERIFY_TERMINAL, NOT_EXECUTED}
VERDICTS = DECISIVE | NON_DECISIVE_TERMINAL | {VERIFY_UNRESOLVED, VERDICT_UNKNOWN}

SAMPLE_SPARSE = "SPARSE"
SAMPLE_ESTABLISHED = "ESTABLISHED"
SPARSE_DIAGNOSTIC = "CI_SPARSE_SAMPLE"


def _result(
    obs: ObservationSet,
    band: str | None,
    status: str,
    semantics: str | None,
    possible: list[str] | None,
    derived: dict[str, Any],
    diagnostics: list[str],
    explanation: str,
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


def _newest(records: list[dict[str, Any]]) -> dict[str, Any]:
    return max(records, key=lambda r: (r.get("committed_at") or "", r.get("revision") or ""))


def classify(n: int, f: int, current_reference: str | None) -> str:
    """The V0 band table over a decisive population and the verdict that speaks for the newest revision."""
    established = INTEGRITY["established_sample"]
    fail_num, fail_den = INTEGRITY["failing_ratio"]
    if n == 0:
        return "NO_DECISIVE_RUNS"
    if current_reference == VERIFY_FAIL or (n >= established and f * fail_den >= n * fail_num):
        return "FAILING"
    if n >= established and f > 0:
        return "FLAKY"
    if n >= established:
        return "CLEAN"
    if f >= 1:
        return "SPARSE_MIXED"
    return "SPARSE"


def sample_strength(n: int) -> str | None:
    """``SPARSE`` for one to three decisive revisions, ``ESTABLISHED`` from four; none without a sample."""
    if n <= 0:
        return None
    return SAMPLE_SPARSE if n < INTEGRITY["established_sample"] else SAMPLE_ESTABLISHED


HISTORY_CONTRIBUTION = {"FAILURE_OBSERVED": VERIFY_FAIL, "PASS_ONLY_OBSERVED": VERIFY_PASS, "NO_DECISIVE_OBSERVED": None, UNKNOWN_HISTORY: None}


def _record_consistent(record: Any) -> bool:
    """A revision record names its immutable revision, its history state is in the vocabulary, and its contribution is the one PV-CI-UNIT-004 derives from it."""
    if not isinstance(record, dict) or not isinstance(record.get("revision"), str) or not record["revision"]:
        return False
    if not isinstance(record.get("history_state"), str) or record["history_state"] not in HISTORY_CONTRIBUTION:
        return False
    if not isinstance(record.get("current_verdict"), (str, type(None))):
        return False
    return record.get("historical_contribution") == HISTORY_CONTRIBUTION[record["history_state"]]


def _record_label(record: Any) -> str:
    if isinstance(record, dict) and isinstance(record.get("revision"), str):
        return record["revision"]
    return type(record).__name__


def established_failing(n: int, f: int) -> bool:
    """The historical FAILING predicate on its own: an established sample whose failure ratio reaches the threshold."""
    fail_num, fail_den = INTEGRITY["failing_ratio"]
    return n >= INTEGRITY["established_sample"] and f * fail_den >= n * fail_num


def _unknown(obs: ObservationSet, history: dict[str, Any], diagnostics: list[str], explanation: str = "Evidence is insufficient for a deterministic band; no band is fabricated.") -> VitalResult:
    """UNKNOWN with no band, still carrying the durable history for the next bundle."""
    return _result(obs, None, EVAL_UNKNOWN, None, None, dict(history), diagnostics, explanation)


def _bearing(history: Reconciled, revisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The reconciled records of the current inventory that carry any verification history."""
    records = [history.records[r.get("revision")] for r in revisions if isinstance(r, dict) and r.get("revision") in history.records]
    return [r for r in records if r["parents"] or r.get("unresolved")]


def evaluate(obs: ObservationSet) -> VitalResult:
    diagnostics: list[str] = []
    reconciled = reconcile(obs)
    history = {"revision_history": reconciled.output()}
    if reconciled.source["status"] == SOURCE_GAP:
        # HIST-08: explicit, and nothing older is carried in its place.
        diagnostics.append(f"REVISION_HISTORY_GAP:{reconciled.source.get('reason')}")
    configured_obs = obs.get(CONFIGURED)
    series = obs.get(REVISIONS)
    configured_known = configured_obs is not None and configured_obs.good
    configured = bool(configured_obs.value) if configured_known else None

    series_usable = (
        series is not None
        and series.status in (AVAILABLE, PARTIAL)
        and series.freshness == FRESH
        and isinstance(series.value, list)
    )
    if not series_usable:
        # Precedence A of PV-INTEGRITY-TOTALITY-001: an unusable required series
        # is UNKNOWN, also beside a positive "not configured", because
        # UNINSTRUMENTED claims there is no verification evidence and an
        # unreadable series is exactly what cannot establish that.
        diagnostics.append(f"MISSING_REQUIRED:{REVISIONS}:{obs.status_of(REVISIONS)}/{obs.freshness_of(REVISIONS)}")
        if not configured_known:
            diagnostics.append(f"MISSING_REQUIRED:{CONFIGURED}:{obs.status_of(CONFIGURED)}/{obs.freshness_of(CONFIGURED)}")
        return _unknown(obs, history, diagnostics)

    revisions: list[dict[str, Any]] = list(series.value)
    inconsistent = [r for r in revisions if not _record_consistent(r)]
    if inconsistent or reconciled.problems:
        # A record whose contribution contradicts its own history (or names a
        # state outside the vocabulary), or carried history that is not the
        # shape its lineage declares, is a coverage defect, not a pass.
        diagnostics.extend(f"REVISION_RECORD_INCONSISTENT:{_record_label(r)}" for r in inconsistent)
        diagnostics.extend(reconciled.problems)
        return _unknown(obs, history, diagnostics)
    active = [r for r in revisions if r.get("parents")]
    provenance: dict[str, int] = {}
    for r in active:
        key = r.get("history_provenance") or "UNKNOWN"
        provenance[key] = provenance.get(key, 0) + 1
    if provenance.get("PARENT_LEVEL_ONLY"):
        # Parent-level surfaces cannot prove an earlier failure; since R52 a
        # favorable one is unknown history, and this names the surface.
        diagnostics.append(f"HISTORY_PROVENANCE_PARENT_LEVEL_ONLY:{provenance['PARENT_LEVEL_ONLY']}")
    bearing = _bearing(reconciled, revisions)
    decisive = [r for r in bearing if r.get("historical_contribution") in DECISIVE]
    failed = [r for r in decisive if r.get("history_state") == "FAILURE_OBSERVED"]
    unknown_history = [r for r in bearing if r.get("history_state") == UNKNOWN_HISTORY]
    n, f = len(decisive), len(failed)
    counts: dict[str, Any] = {
        "revisions_in_window": len(revisions),
        "revisions_with_verification": len(active),
        "revisions_with_history": len(bearing),
        "decisive_count_14d": n,
        "failed_count_14d": f,
        "unknown_history_count_14d": len(unknown_history),
        "history_rule": HISTORY_RULE,
    }

    if series.status == PARTIAL:
        # PV-REV-TEST-003: a truncated required series has no accepted degraded
        # path. The counts of what was collected stay visible, marked as
        # incomplete, and no band is claimed over evidence known to be short.
        diagnostics.append(f"MISSING_REQUIRED:{REVISIONS}:{PARTIAL}/{series.freshness}")
        diagnostics.append(f"REVISION_SERIES_PARTIAL:{series.reason_code or 'INCOMPLETE'}")
        return _result(
            obs,
            None,
            EVAL_UNKNOWN,
            None,
            None,
            {**counts, "series_status": PARTIAL, "partial_series_rule": PARTIAL_RULE, **history},
            diagnostics,
            f"The revision series is incomplete ({series.reason_code or 'truncated'}); {n} decisive revisions were observed, and no band is claimed over evidence known to be short.",
        )

    if unknown_history:
        # R52 and PV-HIST-002: history nobody can prove is neither a pass nor a
        # zero, and T9 puts it above every conservative branch.
        diagnostics.extend(f"REVISION_HISTORY_UNKNOWN:{r['revision']}" for r in unknown_history)
        return _result(
            obs, None, EVAL_UNKNOWN, None, None, {**counts, **history}, diagnostics,
            f"The verification history of {len(unknown_history)} recent revisions cannot be proven complete; {f} of {n} decisive revisions failed, and no band is claimed around the unknown ones.",
        )

    if not active:
        if bearing:
            # Durable history proves verification happened, but nothing current
            # was observed, and a current verdict is never carried (HIST-16).
            diagnostics.append("CURRENT_VERIFICATION_NOT_OBSERVED")
            return _result(
                obs, None, EVAL_UNKNOWN, None, None, {**counts, **history}, diagnostics,
                f"{len(bearing)} recent revisions carry verification history from earlier bundles, but the provider shows no current verification, so no current band is claimed.",
            )
        if configured_known and configured is False:
            return _result(
                obs,
                "UNINSTRUMENTED",
                EVAL_AVAILABLE,
                SEM_EXACT,
                None,
                {**counts, **history},
                diagnostics,
                "No automated verification is configured and no verification evidence exists for recent revisions.",
            )
        if not configured_known:
            diagnostics.append(f"MISSING_REQUIRED:{CONFIGURED}:{obs.status_of(CONFIGURED)}/{obs.freshness_of(CONFIGURED)}")
            return _unknown(obs, history, diagnostics)
        return _result(
            obs,
            "NO_RECENT_RUNS",
            EVAL_AVAILABLE,
            SEM_EXACT,
            None,
            {**counts, **history},
            diagnostics,
            f"Verification is configured but none of the {len(revisions)} recent default-branch revisions has a verification execution.",
        )

    if not configured_known:
        diagnostics.append("CONFIGURED_INFERRED_FROM_RUNS")

    latest = _newest(active)
    current = latest.get("current_verdict") or VERDICT_UNKNOWN
    if not isinstance(current, str) or current not in VERDICTS:
        # integrity-ci.md: an unknown future value fails closed. It is read as
        # UNKNOWN, never as a non-decisive terminal state an older pass could
        # speak for.
        diagnostics.append(f"CURRENT_VERDICT_UNRECOGNIZED:{current}")
        current = VERDICT_UNKNOWN

    strength = sample_strength(n)
    if strength == SAMPLE_SPARSE:
        diagnostics.append(SPARSE_DIAGNOSTIC)

    derived: dict[str, Any] = {
        **counts,
        "failure_ratio_14d": ratio(f, n) if n else None,
        "current_revision": {
            "revision": latest.get("revision"),
            "committed_at": latest.get("committed_at"),
            "current_verdict": current,
            "history_state": reconciled.records.get(latest.get("revision"), {}).get("history_state", latest.get("history_state")),
        },
        "history_provenance": dict(sorted(provenance.items())),
        **history,
    }
    if strength is not None:
        derived["sample_strength"] = strength

    if current == VERDICT_UNKNOWN:
        # PV-REV-INTEGRITY-UNKNOWN-001: nobody observed what verification said
        # about the newest revision, so nothing exact can be said about the
        # current state. The decisive history above is preserved as it is.
        diagnostics.append(f"CURRENT_VERDICT_UNKNOWN:{latest.get('revision')}")
        derived["unknown_verdict_rule"] = UNKNOWN_RULE
        return _result(
            obs,
            None,
            EVAL_UNKNOWN,
            None,
            None,
            derived,
            diagnostics,
            f"The verification outcome of the newest revision is unknown; {f} of {n} decisive revisions failed in 14 days, and no current band is claimed over an unobserved verdict.",
        )

    if current == VERIFY_UNRESOLVED:
        # PV-INTEGRITY-TOTALITY-001, section 4 (INT-TOTAL-01..06): the revision
        # still being verified is spoken for by no older verdict. The history
        # names a band only when it already satisfies FAILING on its own, and
        # then the band is exact for this snapshot while the evaluation says
        # the current verification is unresolved.
        diagnostics.append(UNRESOLVED_DIAGNOSTIC)
        derived["unresolved_verdict_rule"] = TOTALITY_RULE
        if established_failing(n, f):
            return _result(
                obs, "FAILING", EVAL_DEGRADED, SEM_EXACT, None, derived, diagnostics,
                f"{f} of {n} decisive revisions failed verification in 14 days, which is FAILING on its own; the newest revision is still being verified.",
            )
        return _result(
            obs, None, EVAL_UNKNOWN, None, None, derived, diagnostics,
            f"The newest revision is still being verified; {f} of {n} decisive revisions failed in 14 days, and no older verdict speaks for the unresolved one.",
        )

    if configured_known and configured is False and n == 0 and all(r.get("current_verdict") in NON_DECISIVE_TERMINAL for r in active):
        # PV-INTEGRITY-TOTALITY-001, section 5 (INT-TOTAL-08/09): a positively
        # unconfigured repository whose recent records are only non-decisive
        # is UNINSTRUMENTED, and those records stay visible, never zero-filled.
        diagnostics.append(UNINSTRUMENTED_WITH_HISTORY)
        derived["uninstrumented_rule"] = TOTALITY_RULE
        return _result(
            obs, "UNINSTRUMENTED", EVAL_AVAILABLE, SEM_EXACT, None, derived, diagnostics,
            f"No automated verification is configured; {len(active)} recent revisions carry only non-decisive verification records, kept visible.",
        )

    current_reference = current
    decisive_current = [r for r in active if r.get("current_verdict") in DECISIVE]
    if current in NON_DECISIVE_TERMINAL and decisive_current:
        fallback = _newest(decisive_current)
        current_reference = fallback.get("current_verdict")
        derived["latest_decisive_revision"] = {
            "revision": fallback.get("revision"),
            "committed_at": fallback.get("committed_at"),
            "current_verdict": current_reference,
        }
        diagnostics.append(f"LATEST_REVISION_NON_DECISIVE:{current}")

    band = classify(n, f, current_reference)
    if band == "NO_DECISIVE_RUNS":
        explanation = f"{len(active)} recent revisions carry verification executions but none produced a decisive pass/fail verdict."
    elif band in ("FAILING", "FLAKY"):
        explanation = f"{f} of {n} decisive revisions failed verification in 14 days; latest decisive verdict is {current_reference}."
    elif band == "CLEAN":
        explanation = f"All {n} decisive revisions passed verification in 14 days; latest decisive verdict is {current_reference}."
    elif band == "SPARSE_MIXED":
        explanation = f"Only {n} decisive revisions in 14 days, {f} of them failed; the sample is too small for a rate."
    else:
        explanation = f"Only {n} decisive revisions in 14 days, all passed; the sample is too small for a rate."

    return _result(obs, band, EVAL_AVAILABLE, SEM_EXACT, None, derived, diagnostics, explanation)
