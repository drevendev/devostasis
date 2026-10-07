# Verification semantics (PV-CI-UNIT-004, outcome map devostasis.ci-outcomes.github.v1)

Integrity is computed over **immutable revisions** of the default branch in
the 14-day window, never over runs. The adapter emits one canonical record per
revision in `ci.revision_verdicts_14d`; the evaluator only counts.

## Outcome normalization (PV-CI-NORM-001)

Provider conclusions map to a provider-neutral vocabulary. Unknown future
values fail closed. The GitHub map `devostasis.ci-outcomes.github.v1` was
accepted by PV-CAL-003 (CI-OUTCOME-01..04).

| Provider state | Normalized |
| --- | --- |
| not completed (queued, in progress, waiting) | `VERIFY_UNRESOLVED`, whatever conclusion is attached (CI-OUTCOME-03) |
| `success` | `VERIFY_PASS` |
| `failure` | `VERIFY_FAIL` |
| `timed_out` | `VERIFY_FAIL`: a verification attempt that exceeded its allowed time did not verify the revision (CI-OUTCOME-01) |
| `cancelled`, `neutral`, `action_required`, `stale` | `NON_VERIFY_TERMINAL` |
| `skipped` | `NOT_EXECUTED` |
| `startup_failure` | `UNKNOWN`: a provider could not start the job, which says nothing about the code; it is neither a project failure nor zero evidence (CI-OUTCOME-02) |
| `null`, anything else | `UNKNOWN` (CI-OUTCOME-04) |

## Parent identity

A **parent** is one logical verification execution of a revision. Identity
is provider-native, never heuristic:

- GitHub Actions: `workflow_run.id` plus `run_attempt`; all attempts of one
  run are one parent, and the greatest observed attempt governs its current
  state;
- generic GitHub Checks: `check_suite.id`; re-requests keep the same id, so
  earlier outcomes are not observable (`PARENT_LEVEL_ONLY` provenance).

When Actions runs exist for a revision, check suites created by Actions are
not collected again (overlap de-duplication). External check apps are only
collected when no Actions runs exist at all (see the adapter document).

## Revision verdicts

Per revision, two independent facts are recorded:

1. **Current verdict** composes the current state of every parent with the
   precedence `UNKNOWN > VERIFY_FAIL > VERIFY_UNRESOLVED > VERIFY_PASS >
   NON_VERIFY_TERMINAL > NOT_EXECUTED`. An unresolved sibling therefore blocks a
   pass but never hides an observed failure.
2. **History state** is derived from every attempt observed for the revision:
   `FAILURE_OBSERVED` if any attempt was `VERIFY_FAIL`; otherwise, only when
   the history is complete (every parent an Actions run whose attempts
   1..latest are all observed), `PASS_ONLY_OBSERVED` if any was `VERIFY_PASS`,
   else `NO_DECISIVE_OBSERVED`; and `UNKNOWN_HISTORY` when it is not complete,
   because a check suite keeps its id across re-requests and a missing attempt
   may have failed (R52, `history_complete` in the record).
   `FAILURE_OBSERVED` is absorbing for the life of the revision in the window.

The **historical contribution** is `VERIFY_FAIL` for `FAILURE_OBSERVED`,
`VERIFY_PASS` for `PASS_ONLY_OBSERVED`, none otherwise (`UNKNOWN_HISTORY`
included: it is neither a pass nor an empty decisive set). Exactly one
contribution per revision enters `decisive_count_14d` and
`failed_count_14d`; attempts are never independent samples, and retry count or
order cannot improve history (rule `ANY_FAIL_ELSE_ANY_PASS_PER_IMMUTABLE_REVISION`).

A newer revision is a distinct sample: a failed revision followed by a passing
newer revision yields one failure and one pass while both are in the window.
Integrity improves through new revisions and window expiry, never through
retries. A secondary workflow that fails on every revision therefore keeps
the band `FAILING` while another workflow passes; PV-CAL-002 confirmed this
reading against a real repository.

## Record shape

```json
{
  "revision": "<sha>",
  "committed_at": "2026-09-01T10:00:00Z",
  "parents": [
    {
      "parent_id": "github_actions:workflow_run:100",
      "kind": "github_actions_workflow_run",
      "name": "CI",
      "event": "push",
      "current_attempt": 2,
      "current_state": "VERIFY_PASS",
      "attempts_observed": [{"attempt": 1, "state": "VERIFY_FAIL"}, {"attempt": 2, "state": "VERIFY_PASS"}],
      "attempts_complete": true,
      "history_state": "FAILURE_OBSERVED",
      "url": "..."
    }
  ],
  "current_verdict": "VERIFY_PASS",
  "history_state": "FAILURE_OBSERVED",
  "historical_contribution": "VERIFY_FAIL",
  "history_provenance": "ATTEMPT_LEVEL",
  "history_complete": true
}
```

## Durable history (PV-HIST-002)

A provider forgets: a re-requested check suite shows only its latest
outcome, and retention removes old runs. Since 0.2.0 what one bundle proved
about a revision is carried into the next one (PV-HIST-002, accepted by
PV-REV-HIST-002, target B3), under the history-semantics lineage
`devostasis.ci-history.v2`.

**The carrier** is the union of every attempt observed per parent per
revision: `{revision, committed_at, history_state, historical_contribution,
history_complete, parent_groups: [{kind, latest_attempt, attempts:
[{attempt, state}], parent_ids}]}`. Parents of one shape are stored once
with their ids, which loses nothing and keeps the carrier small where a busy
default branch attaches hundreds of single-attempt runs to one revision (the
most active project of the fleet: 91 KB of snapshot instead of 393 KB).
Each bundle's union is its predecessor's union plus what the provider shows
now, so it holds every history fact of the chain and selects none (the
complete-chain-equivalent reduction of section C). Records that have aged
out of the window are not carried. It lives in two canonical places:

- `derived.revision_history` of the Integrity result in `snapshot.json`,
  `{lineage, source, records}`: the durable output, present on every
  evaluation path, `UNKNOWN` ones included, and whatever the bundle's
  observations setting; only revisions that carry history are in it;
- `ci.revision_history_carried`, the observation a build adds before
  evaluating, from its immediate predecessor: `AVAILABLE` with `{lineage,
  records, source_bundle_id, source_observed_at, basis}`, `UNAVAILABLE /
  NO_PREVIOUS_BUNDLE` for a first bundle, `UNKNOWN / HISTORY_GAP` when the
  predecessor cannot be read or verified, `UNKNOWN /
  PREDECESSOR_NOT_EARLIER` when it is not earlier, `UNKNOWN /
  PREDECESSOR_CARRIES_NO_HISTORY` when it keeps neither a carrier nor its
  observations.

**The source** is the verified immediately previous bundle of the same
immutable project, the one the comparison resolves, never an older one: when
that bundle is missing, unverifiable or belongs to another project, nothing
is carried and the gap is explicit (`REVISION_HISTORY_GAP`, HIST-08, -18,
-20). `verify` checks that the source a bundle names is the bundle its
manifest follows (`HISTORY_SOURCE_MISMATCH`), and a build refuses
observations that already carry history from another bundle
(`HISTORY_SOURCE_NOT_PREDECESSOR`). A stated carrier must also match the
canonical observation reconstructed from that verified predecessor, including
its records and provenance (`HISTORY_CONTENT_MISMATCH`); an unchanged source
id never authorizes replacement or deletion of a recorded attempt. Carried
records name each nonempty immutable revision once. Duplicate revision ids
are malformed history (`REVISION_HISTORY_CARRY_MALFORMED`), rather than a
last-record-wins override of an earlier failure.

**Reconciliation**, per revision of the current 14-day inventory: the carried
union and the provider's current parents are merged by parent identity, and
the state is a function of the union alone. An observed `VERIFY_FAIL` is
`FAILURE_OBSERVED` from either side and absorbing (HIST-01, -02, -05, -09);
favorable evidence is `PASS_ONLY_OBSERVED` only when the union is complete;
a prior `UNKNOWN_HISTORY` does not heal from a later pass that is complete
only for what is visible (HIST-19), and heals when every attempt is observed.
Retries never add samples (HIST-03), a newer revision is a distinct one
(HIST-04), a revision that ages out of the window stops contributing
(HIST-10), and a revision the complete inventory no longer holds leaves it.
When the current series is partial or unusable, carried records are kept, so
history crosses a bundle whose verification evidence could not be read. A
current verdict is never carried (HIST-16).

**Lineage.** A carried union of `devostasis.ci-history.v2` is read as it is.
The revision records a 0.1.x bundle keeps in `ci.revision_verdicts_14d`
(`devostasis.ci-history.v1`) are replayed from the attempts they kept, never
copied from the state they derived (HIST-13): the first 0.2.0 bundle of a
project carries the history of its 0.1.9 predecessor this way. Any other
lineage has neither a replay nor an accepted migration (HIST-14 has nothing
to execute): its revisions are `UNKNOWN_HISTORY` until complete current
evidence repairs them (HIST-15), and the old bundle keeps its record as
historical evidence.

## The newest revision

The newest in-scope revision speaks for the current state. Its verdict is
read as it was composed: decisive verdicts stand; `VERIFY_UNRESOLVED` makes
the band a conservative superset over the completions the evidence admits;
positively observed `NOT_EXECUTED` and `NON_VERIFY_TERMINAL` fall back to the
latest decisive revision and are diagnosed. `UNKNOWN` is none of those: it is
the absence of an observation (a `startup_failure`, a conclusion this version
has never seen), and under `PV-REV-INTEGRITY-UNKNOWN-001` it never inherits an
older verdict. The Vital is then `UNKNOWN` with no band, the decisive history
stays visible, and `CURRENT_VERDICT_UNKNOWN:<revision>` names the cause
(INT-UNKNOWN-01..06, [vitals.md](vitals.md#integrity)).

## Sample strength

One to three decisive revisions are a `SPARSE` sample and carry
`CI_SPARSE_SAMPLE`; four or more are `ESTABLISHED` (accepted with the exact
R1 and R2 vectors, PV-REV-TEST-VECTORS-002). The strength is emitted in
`derived.sample_strength` and never changes a band.

## Conformance cases implemented

R54 same-revision retry keeps historical failure; R55 retry-count invariance;
R56 newer revision is distinct; R57 order and surface invariance; HIST-01..20
of PV-HIST-002 except HIST-14, which has no accepted migration to execute;
the V0.7
composition precedence; CI-OUTCOME-01..04 outcome mapping; unresolved current
verification degrades instead of claiming `CLEAN`; INT-UNKNOWN-01..06; T2, R1
and R2 as vectors ([conformance.md](conformance.md)). The `ci` vector kind
([vectors.md](vectors.md)) executes a case at the normalization boundary this
page describes.
