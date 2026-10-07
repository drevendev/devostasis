# Evidence to Action companion — devostasis.work.v1

This is an implementation-owned consumer contract introduced in 0.3.0 in
response to #54–56. It is separate from the seven Vitals and
`devostasis.demand.v2`. It does not claim acceptance as a research Vital or
Instrument contract. Gauges, bands, urgency inferred from titles and models
never participate in task ordering. Runtime dependencies remain empty.

The public Python surface is `devostasis.workscope.planner.project`,
`evidence.normalize`, `bundle.build/verify/publish/latest/slice_scope`,
and `collect.Client/collect`. Inputs and outputs are JSON values; filesystem
bundles use `devostasis.canon.v1`. Errors are `ScopeError` or strict canonical
decoder errors. Unknown fields, duplicate ids, ambiguous timestamps and
non-integer policy numbers are refused. All timestamps must include a zone;
microseconds are preserved. Commit ids are full lowercase SHA-1/SHA-256.

## Input authority

`inventory.json` has `contract`, `kind=inventory`, `subject`, `observed_at`,
`changes`, `issues`, `selection`, `receipts`. Subject has provider (`github`
or `gitlab`), HTTPS API endpoint, immutable project id as a string, locator,
exact content revision and `CANONICAL`/`CANDIDATE` context. Endpoint and
immutable project id define project identity; renames do not split history.

A collection has `status=COMPLETE|PARTIAL|UNAVAILABLE`, `items`, `reasons`.
UNAVAILABLE has no items. COMPLETE has no missing-evidence reasons. Empty
COMPLETE means empty **within the declared selection**. Issues are read from
the explicit criteria/dependency register, not the whole issue tracker.
`selection.issues` names those ids; `selection.changes` distinguishes
`OPEN_AND_REGISTERED` from the narrow `SELECTED` refresh used by recheck.
Unavailable or malformed issue records stay missing evidence, including an
unknown provider lifecycle state; they never become CLOSED. A selection
containing both readable and missing issues is PARTIAL regardless of read
order, retaining readable records and bounded recovery for missing ids.
Discovery, collection budgets and source authentication do not make this a
cryptographically signed statement about a forge. Consumers trust their
collector and transport; hashes bind stored inputs and deterministic replay.

Canonical acquisition receipts record path, semantic response status and body
digest. A validated 304 replay and its equivalent 200 response have the same
receipt. Invocation timings, network byte counts and physical 200/304 status
remain in `Client.telemetry` outside the canonical inventory; they cannot
change a work-bundle id. Source failure statuses remain evidence-bearing.

A change has id, title, OPEN/CLOSED/MERGED state, author, owners, requested reviewers, exact head
and base ids, updated_at, nullable booleans draft/conflict/merge_train, and
collections reviews/checks/threads/files. Reviews bind id, actor, revision,
APPROVED/CHANGES_REQUESTED/DISMISSED/COMMENTED and at. Checks bind id, name,
revision, PASS/FAIL/PENDING/MANUAL/UNKNOWN and at. Threads have id and resolved;
files contain repository-relative paths. An issue has id, title, OPEN/CLOSED
state, owners and updated_at. Future source events are not admitted.

`policy.json` has contract, kind=policy, explicit version and actor, roles,
ttl_seconds (1–86400), queue_order (all five exactly once), required_checks,
minimum_approvals (1–100), allow_merge_train, read_budget, priorities,
criteria, requests and dispositions. Policy is consumer authority; no issue
body, report or source title changes it. Required check names must be selected
by the adopter, including provider-required checks. An empty list explicitly
declares no check gate; it cannot certify branch protection or grant a merge.
Changing policy content invalidates its digest even if the version was reused.

Priority keys are `change:<number>`, `issue:<number>`, `request:<id>` or finding
ids; each contains integer rank (smaller first) and explicit rationale.
Unspecified sources receive rank 1000 and an explicit absence rationale.
`read_budget` bounds max_files and max_bytes; consumers enforce the byte cap
when reading the named paths at the recorded revision. This library does not
read code or execute repository instructions.

Criteria have permanent id, numeric issue id, nonempty acceptance, paths,
symbols, numeric issue dependencies, explicitly correlated implementation
change ids, and done. Sibling criteria remain independent. A closed issue,
done criterion or correlated OPEN/MERGED implementation excludes new work.
An absent referenced implementation is UNKNOWN, not evidence of no work.
Unregistered equivalence is not inferred from natural language. Requests have
id, research/analyze_code queue, question/observed trigger, paths, symbols,
nonempty expected acceptance, dependencies and nullable owner. Code analysis
requires named paths. Dispositions bind finding id, exact revision, expiry,
ACKNOWLEDGED/IMPLEMENTING and reference; implementing references must resolve
to a currently open implementation to suppress recurrence.

## Projection and eligibility

Each item contains stable id, queue/source/criterion, subject, exact revision,
title, action, implementation_owner, executor, explicit priority,
continuation, eligibility, reasons, dependencies, bounded read_set,
acceptance, input/evidence digests, optional merge_gate and fingerprint.
Stable identity hashes immutable project identity + queue + source + criterion.
Revision, freshness and evidence are separate bindings; a new commit keeps
the task id but invalidates its earlier scope. Fingerprints include bindings.

| Queue | Admission |
| --- | --- |
| review | Independent executor, outstanding verdict on the exact head, complete files/review inventory, non-draft |
| finish_merge | Continue an implementation; distinguish merge readiness from rework eligibility |
| implement_issue | Explicit unfulfilled criterion, no correlated equivalent implementation, resolved ownership/dependencies |
| research | Explicit question or one bounded recovery request per missing source |
| analyze_code | Named paths/symbols, observed producer finding or explicit trigger, verification objective |

Merge gates require exact-head independent approvals (latest decisive review
per actor; dismissals invalidate approvals), explicit required checks passing
on that head, resolved discussions, complete files/reviews/checks/threads,
known non-draft/non-conflicting state and explicit merge-train policy.
An unknown required fact produces UNKNOWN, never merge-ready. A known red
check, conflict or requested change can produce READY **rework**, while
`merge_gate` stays BLOCKED. Foreign or ambiguous implementation ownership
prevents execution; executor and owner are distinct fields. The planner
does not infer permission from these fields. Current branch protection,
CODEOWNERS and merge authority must still be enforced by the execution client.

Sort order is eligibility (READY, BLOCKED, UNKNOWN), business rank,
continuation, declared queue preference, stable id. No aggregate health score
is introduced. Read-set overflow is explicit UNKNOWN. Incomplete collections
retain bounded evidence recovery; a recovery item never requests a repo-wide
search. Expired inventories cannot produce executable normal work.

## Bundles, history and handoff

Members are inventory.json, policy.json, evidence.json, scope.json, report.md
and manifest.json. The manifest identifies `devostasis.work-engine.v1`, exact
member digests and an optional externally verified Vitals reference. Its id
is SHA-256 of the canonical preimage without bundle_id. Replay rebuilds every
derived member from stored input and clock and compares all bytes; rehashing
a forged scope does not make it valid. Unsupported contract/engine versions
fail closed. Future incompatible changes must get new contract/engine ids;
v1 replay stays available. Existing Vitals bundles and renderers keep their
existing contracts. Optional Vitals anchors are provenance references, not
an eighth input to priority; verification of a work bundle does not certify
the availability of that external bundle.

Store: `work/<identity-digest>/bundles/<bundle-id>/` plus latest.json.
Verified immutable publication occurs under an OS process lock, with staging
and fsync before rename. Identical retries are idempotent. Backfills remain
history; only a strictly newer CANONICAL observation advances latest. Different
canonical bundles at one timestamp are rejected. Candidate bundles never
replace canonical latest. Latest is a pointer bound to bundle id, manifest
digest and project, and is reverified on read. A failed pointer write leaves
the prior verified latest and recoverable immutable history. This is a local
filesystem transaction, not a distributed object-store lock or authenticity
signature. Use CI serialization for replication to a separate history repo.

`work slice` returns a bounded role-filtered page, total, overflow, exclusions,
coverage and a cursor bound to scope digest, role and offset. Changed scope or
role rejects the cursor. Expired slices return one correlated recovery request.
EMPTY, INCOMPLETE, EXPIRED and AVAILABLE are distinct. A consumer verifies
the bundle, confirms its expected project/actor/policy, then uses `work recheck`
with its current policy file. Recheck reads only the selected source,
correlated implementations and dependencies; it refuses changed revision,
owner, policy, action, stale evidence or lost eligibility. No command claims,
dispatches, labels, comments, closes, merges or deploys. Source state can change
after recheck; the execution client must condition its mutation on the exact
revision and enforce authority immediately before acting.

CANDIDATE content-only proposals have an immutable content id but no recorded
mutable branch ref in v1. Live CLI recheck for issue/research/analysis/recovery
therefore requires a freshly attested input inventory from the execution
client; it refuses automatic historical-SHA reuse. Selected PR head recheck
and CANONICAL default-branch content have live bindings. Named candidate ref
support is tracked in #60.

## Executable evidence

Implementation-owned regression cases are in `tests/test_workscope.py` and
`tests/test_workscope_adapters.py`; they are not research conformance ids.
They cover five queues, explicit priority, stable ids, stale/dismissed/self
approvals, checks, threads, conflicts, drafts, trains, ownership, dependencies,
sibling criteria, malformed/stale reports, dispositions, replay forgery,
cursor binding, backfills, candidate isolation and failed history writes.
The public fixture `examples/work/bundle` replays offline, regenerated by
`scripts/make_work_examples.py`. Adoption and live checks are documented in
[../work-scopes.md](../work-scopes.md).
