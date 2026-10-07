# Consumer operations (0.5.0)

These are implementation-owned operational contracts. The canonical work v1/v2
and core bundle lineages remain unchanged. No Instrument/Vital, compatibility
edge, band, threshold or aggregate semantics are introduced.

`devostasis.work-adoption.v1` is a closed explicit binding: integration id,
enabled boolean, exact installed engine version, HTTPS provider/project/locator,
policy actor/version/canonical digest, selection mode and shared budgets.
REGISTERED/CHANGES declare selected coverage; OPEN_AND_REGISTERED attempts full
open-and-registered enumeration. Unknown fields/versions, omitted enablement,
wrong engine/policy and unqualified endpoints fail before client creation.
The collector verifies immutable project identity before dependent reads.
Disabled invocation performs no API reads or canonical publication.

`devostasis.work-invocation.v1` is an immutable operational receipt outside
bundle members, under `operations/<project-identity-digest>/runs/<uuid>.json`.
It records the complete binding/digest, invocation start/end, COMPLETE/PARTIAL/
FAILED/DISABLED status, exact bundle/manifest references when present, reasons
and noncanonical request/returned-response-byte/worker telemetry. Unavailable
transport responses retain their failure reason; their unknown body bytes are
not measured by that returned-byte counter. PARTIAL remains positively
recorded missing evidence, not successful coverage or a failed collection.
Unexpected provider failures become FAILED; audit-file write errors remain
errors. Wrong preflight configuration is rejected without inventing a receipt.

Change reads may use 1..8 workers. Request allocation is locked under one
request/deadline budget; each HTTP thread owns its opener. GitLab merge-train
inventory is shared within the generation; each MR still has its own final
head/update check. Result and material receipt ordering is deterministic.
Concurrency cannot promote missing/partial approval or verification evidence.
Initial/final change reads and registered issue reads must match the requested
native number/iid; substituted objects remain unavailable. Selected invocation
admission also binds returned changes to the explicit and policy-registered refs.
An exhausted shared budget can change which records returned, so that generation
is PARTIAL. Workers do not add independent quotas or extend the deadline.

`devostasis.work-result.v1` retains the complete verified handoff packet, exact
scope id, caller actor/outcome, one reported acceptance row per original
criterion, evidence references, notes and reporting time. A REPORTED_COMPLETE
claim requires PASS plus an evidence reference for every criterion. A BLOCKED
or ABANDONED claim retains FAIL/UNKNOWN. Every claim remains CALLER_REPORT_ONLY;
references are recorded, not dereferenced or certified as independent proof.
Later reports append; they never rewrite earlier reports or heal evidence.
Reporting after scope expiry is allowed because reporting is not execution:
the packet is verified at its recorded checked_at, not asserted fresh now.
Neither a receipt nor a packet digest authenticates a human principal.

`devostasis.work-history-archive.v1` is a deterministic ZIP_STORED transfer
containing canonical index.json, exactly the six named members per generation,
and selected-project invocation/result records. Names, regular-file attributes,
duplicates, sizes, digests, project, lineage/replay, latest binding, result
packets, invocation coverage and same-time collisions are admitted before store
writes. No archive path is extracted. Encrypted/compressed/linked/unknown members
are refused. Archives contain private source bytes when result packets do.
Store/output/archive paths refuse symbolic links and Windows junctions in ancestors.

Import checks source and destination collisions before appending through the
ordinary publisher. Valid backfill/candidates preserve canonical latest; a
restored store recomputes the newest verified canonical pointer. A missing
source pointer is retained as unavailable in export; verified orphan generations
may be recovered by explicit import. Imports are idempotent and resumable after
I/O failure, not one transaction across all files. Coordinate other writers
during transfer. Default total cap is 64 MiB, configurable up to 512 MiB; at most
2,000 generations, 2,000 invocations and 2,000 caller results are admitted.

`devostasis.work-history-audit.v1` verifies every selected-project generation,
invocation, result and pointer, then reports canonical/candidate counts, UTC
calendar-day count, first/last observation and largest gap, invocation statuses,
caller outcome counts, explicit latest coverage/gap count and latest
AVAILABLE/EXPIRED/FUTURE/EMPTY/LATEST_UNAVAILABLE.
Candidate or rapid duplicate runs cannot add calendar days. Counts are operational
facts, not a calibration judgement, score or claim that B7 is complete.
