# Changelog

All notable changes to this project are documented here. Semantic changes to a
contract or a policy always come with a version bump of that contract.

## 0.3.0 (unreleased)

Release-readiness review, 2026-10-06:

- GitHub/GitLab work issue collectors reject unknown lifecycle states instead
  of treating them as CLOSED and silently completing a consumer criterion.
- A mix of available and missing selected issues remains PARTIAL regardless
  of read order. Previously a missing issue read first left an UNAVAILABLE
  collection containing later readable records and failed the entire scope.
  Readable work and bounded evidence recovery now survive together.
- README and roadmap distinguish the published 0.1.9 engine, the pending
  0.2.0/0.3.0 releases and the proposed external-adoption increment.

Evidence to Action, target E1: a separate deterministic consumer companion
(`devostasis.work.v1`, replay engine `devostasis.work-engine.v1`).

- Five typed queues: review, finish_merge, implement_issue, research and
  analyze_code. Explicit consumer priorities, exact revisions, independent
  reviewer/owner roles, dependencies, acceptance and bounded read sets.
- Read-only GitHub and GitLab work collectors with request/time/page/byte
  budgets, capability receipts, conditional cache partitioning and explicit
  completeness. GitHub collects exact-head review verdicts, checks/statuses,
  threads and merge-queue state. GitLab approval SHA uncertainty stays UNKNOWN
  and is tracked in #58; no aggregate approval is fabricated as an exact-head
  verdict. This companion does not claim the core Phase C adapter/carrier work.
- Optional revision-bound SARIF, JUnit, Cobertura and measured-performance
  profiles, with raw source digests, path admission, scoped dispositions,
  malformed/missing/stale evidence recovery and offline replay.
- Immutable work bundles, verified latest pointers, process-locked atomic
  publication, candidate isolation and backfill protection. Bounded role
  slices have scope-bound cursors, overflow and explicit exclusion reasons.
- `devostasis work policy/import/collect/build/run/verify/replay/slice/explain/recheck`.
  Recheck binds consumer policy and refreshes only selected sources before
  returning eligibility; candidate content tasks without a mutable ref require
  a fresh attested inventory (follow-up #60). No command claims or executes work.
- GitHub reusable read-only workflow with optional protected durable history
  runner, GitLab canonical/candidate CI recipes, adopter guide, public frozen
  example and implementation-owned regression cases. The public GitHub live
  pilot is distinct from the outstanding external calibration target B7.

Seven Vitals, their thresholds, bands, gauges and demand ordering retain their
contracts. This branch includes the still-pending 0.2.0 adoption/readiness
work below; neither version is represented as already tagged or released.

## 0.2.0 (unreleased)

Release-readiness review, 2026-10-02:

- A saved carried-history observation is admitted only when its canonical
  content and provenance match what the verified immediate predecessor
  supplies. Previously the correct source bundle id and acquisition status
  were enough to admit edited records, including removal of a prior failure.
  The build now refuses those inputs with `HISTORY_CONTENT_MISMATCH`.
- A duplicate carried revision id fails closed with
  `REVISION_HISTORY_CARRY_MALFORMED`, in both the current carrier and replay
  from 0.1.x. Previously the last duplicate could overwrite an observed
  failure. These are admission repairs under the existing accepted history
  contract; valid evidence, contract ids, thresholds and windows are unchanged.
- Pending maintenance from #36, #37 and #50 is integrated into the release:
  weekly Dependabot updates, cancellation of superseded CI runs, and the
  Hungry Crab configuration and ledger. The two attribution receipts are
  retained together rather than losing one to their add/add conflict.
- The roadmap distinguishes the tagged 0.1.9 release from the pending 0.2.0
  adoption branch and names the next consumer-facing development sequence.

The adoption release. Every accepted research contract about the Vitals and
their history that this repository had not adopted, and that needs no owner
decision, is adopted: the repairs of Direction, Horizon and Debt that issue
#33 listed, the final T9 reconciliation, and target B3, durable Integrity
revision history (`PV-HIST-002`, #34). The owner asked for a large next
release on 2026-09-30 (#47); the candidate specification written for that
request (`PV-RELEASE-020-001`, "Evidence Observatory") has not been accepted
yet, so 0.2.0 is the part of that ambition that rests on accepted contracts.
No threshold, window, gauge constant or demand mapping changed. Four rule ids
moved, each with the judgement that moved it, so the first 0.2.0 bundle of
every project compares `INCOMPARABLE` (`RULE_VERSION_BOUNDARY`) on Horizon,
Direction, Integrity and Debt and stays comparable on the rest.

- **Direction `direction.bands.v2`: state-neutral linkage, and incomplete
  linkage without failing the project.** `PV-REV-DIRECTION-CLOSED-TARGET-001`
  (cases `DIR-CLOSED-01..09`): an active change request linked to a declared
  target stays linked when the target closes. Calibration finding 9 is
  repaired: closing a delivered target used to un-link the work that
  delivered it, so never closing targets kept the band higher than finishing
  them. Measured on a copy of the fleet store: this repository reads `MIXED`,
  9 of 18 active change requests traced to a declared target, where the
  open-target count said 4 of 18, `SCATTERED`. That count is still derived,
  for presentation only. `PV-DIRECTION-INCOMPLETE-001` (accepted by
  `PV-REV-DIRECTION-INCOMPLETE-001`, cases `DIR-INCOMPLETE-01..16`): every
  active change request is `LINKED`, `UNLINKED` or `UNRESOLVED`. A reference
  the complete register lacks is a broken reference, unlinked and diagnosed
  `DIRECTION_TARGET_REFERENCE_MISSING`; a reference nobody could resolve, or a
  title, body or milestone of the wrong type, is unresolved. Over
  `L + U + R = N` the completions `k = L..L+R` go through the unchanged
  predicates: one reachable band is `DEGRADED / <band> / EXACT`, several are
  `UNKNOWN` with the reachable set in `derived`. Unreadable linkage evidence no
  longer fails the whole project: `LinkageEvidenceError` is gone, and a change
  request names what it could not read in `linkage_unresolved`. A partial
  target list no longer blocks Direction when every referenced target resolves
  on its own, as a milestone embedded in the change request does.
- **Target markers are standalone tokens** (`PV-AUDIT-TARGET-MARKER-SYNTAX-001`).
  `SubTarget: B1`, `NotTarget: B1` and `PreTarget:B1` linked their change
  request to B1, because the configured marker was matched as a substring.
  The marker now starts the text or follows a character that cannot continue
  a word, and a marker ending in a letter needs a boundary after it too. The
  audit's regressions `LINK-MARKER-01..08` reached this repository only as
  categories; the tests cover each category and say so.
- **Horizon `horizon.bands.v2`: partial target enumeration**
  (`PV-HORIZON-PARTIAL-001`, accepted by `PV-REV-HORIZON-PARTIAL-001`, cases
  `HOR-PARTIAL-01..16`). A partial enumeration that returned a target proves
  the capability; its counts are observed-subset lower bounds with the proof
  #39 asked for; only an open target already beyond the frame forces a band,
  `DEGRADED / EXTENDED / EXACT`. Every other partial shape stays `UNKNOWN`,
  because Horizon declares no order to pick a representative by, and a
  partial zero is never `UNDECLARED`.
- **Debt `debt.bands.v2`: partial register** (`PV-DEBT-PARTIAL-001`, accepted
  by `PV-REV-DEBT-PARTIAL-001`, cases `DEBT-PARTIAL-01..16`). A confirmed open
  item under a partial enumeration is `DEGRADED / PRESENT / EXACT`, the band
  exact and the count a lower bound, none confirmed is `UNKNOWN`, and a
  `PARTIAL` count is read as a lower bound only with its
  `OBSERVED_SUBSET_COUNT` proof (the Debt part of #39). Before, a partial
  positive count was `CONSERVATIVE_LOWER_BOUND` on its status alone, so an
  estimate could prove `PRESENT`.
- **Integrity `integrity.bands.v1+ci-unit-004+hist-002`: durable revision
  history** (`PV-HIST-002`, accepted by `PV-REV-HIST-002`, target B3). History
  was reconstructed from whatever the provider still showed, so a failure
  hidden behind a passing re-request of a check suite, or dropped by
  retention, vanished from the counts. The union of every attempt observed per
  parent per revision is now carried from bundle to bundle: a build adds its
  immediate predecessor's union as `ci.revision_history_carried`, Integrity
  merges it with what the provider shows now and emits the result as
  `derived.revision_history`, on every path, so history also crosses a bundle
  whose verification evidence could not be read. A missing, unverifiable,
  foreign or later predecessor is an explicit gap (`REVISION_HISTORY_GAP`);
  nothing older is ever carried in its place, and `verify` checks that the
  source a bundle names is the bundle its manifest follows
  (`HISTORY_SOURCE_MISMATCH`). Favorable evidence proves `PASS_ONLY_OBSERVED`
  only when every attempt of every parent is observed, so a check-suite pass,
  or a run whose earlier attempts are not all known, is `UNKNOWN_HISTORY`
  (R52), and unknown history makes the Vital `UNKNOWN`: T9 puts it above every
  conservative branch. On the stored corpus every active revision is
  attempt-complete, so no fleet project loses its band to that rule. The first
  0.2.0 bundle of a project replays the revision records of its 0.1.9
  predecessor (lineage `devostasis.ci-history.v1`) instead of starting empty.
  The band table and every 0.1.9 judgement are unchanged. Cases `HIST-01..07`,
  `09..11`, `13`, `15`, `16` and `19` are vectors, `08`, `12`, `17`, `18` and
  `20` store tests; `HIST-14` has no accepted migration to execute.
- **T9 is adopted** (`PV-TEST-004`, generator `PV-T9-GEN-003`, accepted by
  `PV-REV-TEST-004`). With the repairs above, every obligation T9 consumes is
  implemented; a finite generator of about 1,270 cells over the nine former
  gap families holds each cell to the accepted table. The T9v2 cell-key
  vectors are still the research process's to deliver.
- **Contradictory counts are refused as input.** Counts no population can
  produce (`L + U + R != N`, a beyond-28-day count above the future-boundary
  count) are `InadmissibleEvidence` before classification, as both totality
  contracts require, and `evaluate` and `build` report an input error (exit
  status 2) instead of a band.
- **The vector format learned two things.** `given.derive` runs the derivation
  over stated inventories, so a case about how a change request becomes
  linked, or how a partial target list is counted, is executed where that
  happens; `expect.rejected` states a refusal (`HOR-PARTIAL-15`). Seventy-one
  new vectors: `DIR-CLOSED`, `DIR-INCOMPLETE`, `HOR-PARTIAL`, `DEBT-PARTIAL`,
  `HIST`.

Upgrading: the first 0.2.0 bundle of every project carries four
`RULE_VERSION_BOUNDARY` rows. Durable history starts from the predecessor's
in-window records; after the fleet's pause since 2026-09-10 (#32) none are
left, so the first carried history is effectively empty, and a project whose
predecessor kept no observations member starts with one explained gap. A
saved 0.1.x observation set under file planning recorded a reference outside
the register as `UNKNOWN`; replayed, that change request is unresolved rather
than unlinked, and a fresh observation tells the two apart. The change-request
record gains `linkage_unresolved` and the reference state `MISSING`; the
revision record gains `history_complete`. The snapshot carries the durable
history, stored grouped by parent shape: 91 KB for the busiest project of the
fleet, whose 834 dispatched workflow runs in two weeks #40 already asks about.

Not in this release: the fifth identity move (#19, the owner's decision), the
Phase C contracts of #34 (after B7 and the compatibility policy), the Pulse
part of #39 (a question for the research side), and the "Evidence
Observatory" candidate of #47, which awaits its review.

## 0.1.9 (2026-09-30)

Four things in one release. First, the adoption of the research judgements
that had been delivered and not adopted, which the roadmap's standing
obligation puts before queued work: one Integrity and one Clutter rule
version, one accepted diagnostic under an existing rule, eight accepted exact
vectors and thirty-one cases of three judgements, plus the vector kinds those
cases needed. Second, the review pass of 2026-09-22 (issue #30). Third, the
repairs of the research audits of 2026-09-20 to 2026-09-24, which were
handed off on Drive and had no record in this repository until the review
of 2026-09-25 catalogued them in issue #35. Fourth, the review of
2026-09-30 (issue #48), which found defects in this release's own new code
(among them an Integrity superset that could omit the band it emitted,
replaced by the accepted totality rule) and older ones in verification,
collection, the store and the command line, and filed what needs a decision
as #38 to #47. No threshold, window or gauge changed; the two band rules
that changed did so under accepted judgements, and their `rule_id` moved
with them.

- **Integrity rule `integrity.bands.v1+ci-unit-004`.** Four accepted
  judgements, one rule version, one `RULE_VERSION_BOUNDARY` per project.
  `PV-REV-INTEGRITY-UNKNOWN-001` (issue #13): a newest in-scope revision whose
  current verdict is `UNKNOWN` never inherits an older decisive verdict; the
  Vital is `UNKNOWN` with no band, the decisive history stays in `derived`,
  and `CURRENT_VERDICT_UNKNOWN:<revision>` names the cause. Positively
  observed `NOT_EXECUTED` and `NON_VERIFY_TERMINAL` keep the accepted
  fallback. Before this, four passes and a newest `startup_failure` produced
  `CLEAN / AVAILABLE / EXACT`, and since 0.1.8 a false `IMPROVED`.
  `PV-REV-TEST-003` (issue #12 finding 3): a required revision series that is
  `PARTIAL` is `UNKNOWN` with no band, its counts visible and marked; the
  `DEGRADED` path with a fixed three-band tail called a superset is gone.
  `PV-REV-TEST-VECTORS-002` (issue #21): one to three decisive revisions carry
  `sample_strength = SPARSE` and `CI_SPARSE_SAMPLE`, four or more
  `ESTABLISHED`. `PV-INTEGRITY-TOTALITY-001` (accepted by
  `PV-REV-INT-TOTALITY-001`, #33): a newest revision still being verified is
  spoken for by no older verdict; the history names a band only when it
  already satisfies FAILING on its own (four or more decisive revisions, a
  quarter or more failed), `DEGRADED / FAILING / EXACT`, and every other
  history is `UNKNOWN` with no band, diagnosed `CI_CURRENT_VERIFY_UNRESOLVED`.
  This rule version first carried a `possible_bands` derived from the
  completions instead; the review of 2026-09-30 found it could omit the band
  it emitted (777 of 7,029 shapes, the commonest being one workflow passed
  and one still running) and could miss bands a completion reaches, and the
  accepted contract defines no reachability algorithm at all. A positively
  unconfigured repository with only non-decisive recent records is
  `UNINSTRUMENTED` with `CI_UNINSTRUMENTED_WITH_RECENT_NONDECISIVE_HISTORY`;
  an unusable series is `UNKNOWN` even beside "not configured"; a verdict
  outside the vocabulary is `UNKNOWN`, never a fallback to an older pass; a
  record whose contribution contradicts its history is a defect. Cases
  `INT-UNKNOWN-01..06`, `INT-TOTAL-01..06` and `08..13`, `T2`, `R1`, `R2` are
  executable vectors.
- **Pulse diagnoses issue-only activity** (`PULSE_ISSUE_ONLY_ACTIVITY`,
  permanent case T5, issue #22), under `pulse.bands.v1` as the accepted vector
  requires: provenance, not a judgement about productivity. It is emitted
  only when every channel was positively observed: with a channel unobserved
  or a required enumeration capped, "every observed event came from issues"
  would be a claim about evidence nobody has.
- **Clutter rule `clutter.bands.v1`: incomplete evidence is a confirmed burden
  floor, never a manufactured band.** Adopts `PV-CLUTTER-INCOMPLETE-001`
  (accepted by `PV-REV-CLUTTER-INCOMPLETE-001`, cases `CLU-INCOMPLETE-01..20`,
  all executable) and the reading `PV-ISSUE-026-RECONCILE-001` gave issue
  #26. An explicitly `UNAVAILABLE` issue or branch component, or a `PARTIAL`
  count with an observed subset, no longer yields a band from the rest: the
  band is the floor the observed facts prove. Observed stale work and
  classified stale branches prove it; the ratio proves it only over a
  complete issue and change-request domain; an `UNCLASSIFIED` branch count
  proves nothing. A `PARTIAL` count counts as an observed subset only when
  its coverage says so (`complete = false`,
  `value_semantics = OBSERVED_SUBSET_COUNT`, which the derivation now records
  on every count aggregate of an incomplete inventory and on nothing else);
  without that proof, with other semantics or with malformed coverage the
  component is unresolved and diagnosed `CLUTTER_PARTIAL_NOT_TRUSTED`
  (review `PV-REV-PR-031-003`, cases `CLU-PARTIAL-TRUST-01..08`; before, any
  fresh `PARTIAL` value was promoted to a floor on its status alone, so a
  saved observation set could prove `HEAVY` with an estimate).
  `HEAVY` is `DEGRADED / EXACT` (terminal), `CLUTTERED` and
  `LIGHT` are `DEGRADED` lower bounds with a conservative superset, and a
  floor of nothing is `UNKNOWN` with no band. Before, an unavailable
  component with nothing else observed produced `DEGRADED CLEAN`, a band
  made from absence; on the fleet's store that is exactly one project, whose
  issues are disabled and which has no stale residue: it becomes `UNKNOWN`,
  which is what the evidence supports. The #26 case, a capped branch head
  resolution, proves a floor only with explicit `CLASSIFIED` retention
  semantics (`>= 20` HEAVY exact, `6..19` CLUTTERED, `1..5` LIGHT, zero
  UNKNOWN); the GitHub adapter does not emit retention semantics, so on
  GitHub that case stays `UNKNOWN` until issue #22 decides whether it should.
  Permanent case T7 (issue #22), the `UNCLASSIFIED` upper bound with
  `CLUTTER_BRANCH_PURPOSE_UNCLASSIFIED`, moves under the same rule id
  unchanged, and when the work items alone reach the band the full count
  reaches, that band is `DEGRADED / EXACT` as the contract's section 5 says.
  One `RULE_VERSION_BOUNDARY` on Clutter per project; no threshold or window
  moved. The GitHub adapter still does not emit `retention_semantics`:
  emitting `UNCLASSIFIED` would make Clutter `DEGRADED` for every project with
  a stale branch and take the accepted ordering away from it, so that is a
  fleet-wide decision left with issue #22, not a default.
- **The accepted exact vectors are in the corpus** as the research process
  wrote them: `T2`, `R1`, `R2` (PV-REV-TEST-VECTORS-002), `R4`
  (PV-REV-TEST-VECTORS-004), `R3` (PV-REV-TEST-VECTORS-005), `T4`, `T5`, `T7`
  (PV-REV-TEST-VECTORS-007). Seven of the seventy named cases without a test
  now have one; sixty-three remain.
- **Two vector kinds and one shape, in answer to the format findings.** The
  `ci` kind (issue #20) starts at the provider-native normalization: workflow
  runs, their earlier attempts and check suites as the provider reports them,
  through the outcome map to canonical revision records and, when the case
  asks, into Integrity. `R5..R10` can now be materialized at the boundary they
  are about; `INT-UNKNOWN-02` and `03` already are. The `activity` kind
  carries `ACT-COV-01..05` of `PV-REV-ACTIVITY-COVERAGE-001` (issue #9), the
  runtime of which 0.1.7 already had. `variants` lets one case hold several
  evidence shapes to one expectation, for `vital` and `ci` cases, which is
  the one-identifier multi-variant mechanism T8 and R9 need (issue #23);
  `vital` cases may also assert `shared_signal_groups` and
  `dependency_group_ids` (part of T6). Every kind fails closed as before; a
  provider without a normalization is an error, never a skip.
- **An observation not later than the previous bundle is `INCOMPARABLE`**
  (issue #17, `NON_MONOTONIC_OBSERVATION:<previous>-><current>`). It was
  `COMPARABLE`, its delta reported `IMPROVED` and `WORSENED` with the
  direction inverted while citing the accepted order, and `activity.json`
  carried an interval that ended before it started. The bundle is still
  written and immutable; it claims no direction and no interval, and
  `build_activity` refuses a backwards interval outright. Where such a bundle
  *lands* is the monotonic-write policy of issue #12 finding 6, still to be
  decided.
- **The comparison reads the immutable bundle the index names, not
  `latest/`** (issue #28). A compacted or damaged convenience copy no longer
  turns the next run into a `HISTORY_GAP`; a copy that names a different
  bundle than the index is still refused, so finding 6 stays visible. Without
  an index the newest immutable bundle is found by scanning. The fleet
  surfaces link to the immutable report when the copy is gone. RPT-3 now
  corrupts the immutable copy, which is what its sentence always meant.
- **Verification binds the manifest's metadata to what the identity hashes**
  (issue #12 finding 4). `semantic_config`, the field the comparison reads,
  must be the projection of the validated stored config
  (`SEMANTIC_CONFIG_MISMATCH`); every identity field the manifest repeats must
  be present in both copies and agree with the preimage
  (`IDENTITY_FIELD_MISMATCH`), with the fields a bundle must carry and the
  renderers it may name decided by its exact lineage
  (`UNSUPPORTED_ARTIFACT_LINEAGE`, `RENDERER_VERSION_NOT_IN_LINEAGE`;
  `PV-AUDIT-MANIFEST-PREIMAGE-BINDING-001`, whose concrete case was a bundle
  that lost its manifest `renderer_version`, kept its id, skipped the report
  replay and verified with any report at all); the manifest receipt
  must hash to `source_receipts_digest` and be the receipt inside
  `observations.json` (`RECEIPT_DIGEST_MISMATCH`, `RECEIPT_COPY_MISMATCH`);
  and `snapshot.json` must name the evidence the bundle carries
  (`OBSERVATIONS_DIGEST_MISMATCH`). A manifest of the wrong shape is a
  problem, not an `AttributeError`. All 308 bundles of the fleet's store
  (both lineages, all four renderers) still verify.
- **Verification holds the whole identity, not only what a forger left in
  place** (review of 2026-09-30). The preimage must have exactly its
  lineage's field set (`IDENTITY_PREIMAGE_SHAPE_MISMATCH`): without
  `source_receipts_digest` the receipt binding was simply skipped. Every
  member the preimage hashes must be declared (`IDENTITY_MEMBER_NOT_DECLARED`):
  a bundle that dropped `delta.json` or `snapshot.json` together with its
  entry kept its id, stopped the replay and verified with any report. The
  `adapters` line the report prints must be the provider and collector the
  identity binds (`ADAPTERS_MISMATCH`). And `verify` no longer says "report
  reproducibility all match" for a report it did not replay: the 74 stored
  bundles written by renderers v1 to v3 are bound by their report digest and
  are now reported as such; replaying them needs the historical renderers,
  which this version does not carry.
- **Collection no longer claims completeness it did not have** (review of
  2026-09-30). A filtered `/actions/runs` query stops at 1,000 results and
  answers the next page empty; that empty page was read as the end, so a busy
  repository's oldest runs (and their failures) vanished from an `AVAILABLE`
  series. The listing is now read against the provider's `total_count` and
  is `PARTIAL` when it ends short. A listing that repeats a commit or a run
  between pages (a push during pagination) counts it once and is `PARTIAL`
  with `LISTING_SHIFTED`; it used to count it twice as complete evidence. A
  revision whose check-suite page the budget refused was counted as
  examined, which could make `ci.configured` a positive `false`; it is now
  `UNKNOWN / SAMPLE_INCOMPLETE`. Failures that escaped the inventory boundary
  and cost the project its bundle are now declared: `http.client`
  exceptions, a timeout while reading an error body, JSON nested past the
  decoder's depth, instants outside the representable range (a register
  date of `0001-01-01T00:00:00+01:00`), register files with non-string
  content, no `size`, invalid base64 or more bytes than the bound, and run or
  suite fields (`name`, `event`, `html_url`, `workflow_id`, `url`) of the
  wrong type, which failed the canonical encoder.
- **Workflows, documentation and tests** (review of 2026-09-30).
  `released-pins.yml` no longer runs on push: the file reaches master only
  in a release merge, the one moment its pins cannot resolve, and its single
  push run (a8726f5, 72 seconds before v0.1.8 was tagged) kept this
  repository's own Integrity `FAILING` for two weeks. The reusable
  `observe-self.yml` passes `devostasis-ref` to the shell through the
  environment instead of interpolating it, and trims debt labels without
  `xargs`, which rewrote quotes and backslashes and failed on an apostrophe.
  The README's self-observation snippet carries the `permissions` block it
  needs (a called workflow can only narrow the caller's token, so without it
  GitHub refuses the run), and deployment.md says that instead of promising
  `FORBIDDEN` Vitals; its cache snippet keeps the token, `id` and
  `continue-on-error` of the step it extends; the store layout names a
  `.gitattributes` so a Windows clone does not break every report digest.
  `build`'s `CONFIG_MISMATCH` says which part of the configuration it can
  and cannot be passed. The example fleet table, the vector page, debt D-1,
  CONTRIBUTING's case families and the `--now` paragraph (which promised
  what #19 still breaks) say what is true now. The suite no longer sleeps
  three real seconds, runs from any working directory, and the pin guards
  are case-insensitive; one register assertion that could not fail now can.
- **Vitals and vectors** (review of 2026-09-30). Pulse crashed with
  `IndexError` when a capped commit enumeration covered all 29 UTC dates a
  28-day window touches (the completion grid stopped at 28 and was empty),
  which cost the project its bundle; the grid now reaches 29 and includes
  the one-event QUIET threshold it missed, and an empty set would be
  `UNKNOWN` as `PV-PULSE-REQUIRED-LOWER-BOUND-001` says. Debt read a stale
  or freshness-unknown partial register as a `PRESENT` lower bound; it is
  `UNKNOWN`, as vitals.md always said. The vector runner refuses an
  expectation that states nothing (an empty object or list, an empty code,
  which as a prefix matched every code), and the published vector schema
  requires `status` in its value conditional: without it the schema rejected
  39 of the 64 vectors the runner accepts. vitals.md lists all seven rule
  ids (it said four Vitals kept their V0 ids; Clutter moved in this
  release), and a drift test now reads them from the code.
- **The store and the command line tell the truth about what they did**
  (review of 2026-09-30). Without an index, the scan for the newest bundle
  skipped a directory whose manifest it could not read, so the next run
  compared against an older bundle, or called a store with history
  `BASELINE`; such a directory now makes the state unverified and the
  comparison a `HISTORY_GAP` (`INDEXLESS_CANDIDATE_UNREADABLE`). A
  repository named `index.json` was read as a project index and broke every
  identity lookup; index files are now found at their exact depth. Problem
  texts carried absolute store paths and exception messages into the delta
  of a `HISTORY_GAP` bundle, so the same damage gave a different bundle id
  per checkout (and a local path inside a committed store); they are now
  store-relative and name exceptions by type. The fleet surfaces are moved
  into place instead of being truncated first. `run` prints every project's
  result before a fleet-surface failure, and `build` its committed bundle; a
  conditional cache that cannot be saved is a warning, written after the
  fleet surfaces, not a traceback that skips them; and `evaluate`, `build`,
  `render`, `gauges`, `demand` and `actions-summary` answer a missing or
  unreadable input with `input error` and exit 2.
- **A build over evidence derived under another configuration is refused**
  (issue #27, `CONFIG_MISMATCH`). `observe` records the digest of the
  configuration its aggregates were derived under; `build` with different
  planning or debt options produced a verified bundle whose effective config
  said one thing and whose snapshot said another. Only a real digest is
  compared, so fixtures and examples with placeholders are unaffected.
- **Check-suite coverage is tracked, paginated and reported** (issue #12
  finding 1). Suites are read page by page, and the series records how many
  revisions were planned and examined, whether every page was read and why
  sampling stopped. Past 100 revisions, past 3 pages, after a failed fetch or
  a spent budget the series is `PARTIAL / CHECK_SUITES_INCOMPLETE`; the
  parents already collected are kept and an observed failure stays. The 101st
  revision and the 101st suite are tests.
- **The example bundle was regenerated** under the new Integrity and Clutter
  rules.

The research audits of 2026-09-20 to 2026-09-24, each reproduced here before
it was repaired (the review of 2026-09-25 found twenty-six malformed
successful payloads escaping the collectors with a probe, and the rest by
the audits' own constructions):

- **The index tail is bound to this project's history** (review of #28's
  repair on this branch). The tail is followed only along the canonical
  `history/YYYY/MM/DD/<bundle_id>` path, resolved inside this project's
  `history/` tree, with a basename equal to the id it claims, and the bundle
  found there must carry the identity the index records; a damaged index
  that names another project's bundle, by a parent reference, an absolute
  path or a copy inside the tree, is `INDEX_TAIL_INVALID` or
  `PROJECT_IDENTITY_MISMATCH`, a `HISTORY_GAP` and never a comparison. A
  malformed index is a store failure and is never appended to.
- **The store fails closed on what it reads about itself.** An unreadable
  index met while proving an immutable id lives nowhere else fails the lookup
  instead of passing for absence (`PV-AUDIT-HISTORYSTORE-001`); an
  unreadable or malformed project index, an unfollowable tail or a demand
  member that is present but unreadable stops the fleet surfaces instead of
  dropping the project, and the `run` and `index` commands report a store
  error (`PV-AUDIT-FLEET-INDEX-001`, `PV-AUDIT-FLEET-COVERAGE-001`); a
  wrapper whose `bundle_id` or `project_key` disagrees with its manifest is
  refused before any write (`PV-AUDIT-STORE-BUNDLE-PATH-BINDING-001`,
  `PV-AUDIT-STORE-PROJECT-BINDING-001`).
- **Publication is recoverable.** The index is replaced through a temporary
  file, never truncated in place; it is written before the convenience copy,
  and the previous copy stays until the new one is in place, so an
  interruption leaves a stale copy of an indexed bundle that the next commit
  replaces rather than a gap. A copy of a bundle the index does not know, or
  one observed after the tail, is still refused
  (`PV-AUDIT-HISTORYSTORE-ATOMIC-PUBLICATION-001`).
- **A locator is a name, not a path.** A project key derives a store path
  only as a `<forge>/<owner>/<repo>` triple of letters, digits, dots, hyphens
  and underscores, strictly beneath `projects/`, and the configuration admits
  only such owner and repository names, so `C:\escape/widget` or `../x` never
  reaches the filesystem (`PV-AUDIT-STORE-PATH-001`). Two spellings of one
  repository are one project in the configuration, and once the provider has
  named the repository, in the run: the second is refused with
  `DUPLICATE_PROJECT_IDENTITY` before it can collect twice or be mistaken for
  a rename (`PV-AUDIT-PROJECT-LOCATOR-ALIAS-001`). `activity.enabled` must be
  a boolean and `store` an object (`PV-AUDIT-CONFIG-SHAPE-001`).
- **Every successful payload is validated before it is read**
  (`PV-AUDIT-GITHUB-REPO/COMMITS/CR/ISSUES/BRANCH/RELEASE/CI-PAYLOAD-001`).
  The two shapes 0.1.9 already caught were members of a family: every
  collector dereferenced its 200 after the boundary that turns failed
  requests into observations, so a scalar row, a missing field or an
  unreadable timestamp escaped as a Python exception and the project produced
  no bundle. Now every consumed field is typed evidence; a body that does not
  establish it is `ERROR / UNEXPECTED_PAYLOAD` for that inventory alone, the
  other inventories are still collected, and nothing is coerced, defaulted
  or skipped: no guessed `main` for a repository without a default branch,
  no truthiness of the string `"false"`, no commit or published release
  silently omitted for lacking a date, no run skipped for lacking a head, no
  check-suite count assumed, and an attempt that names another run or another
  number is not this run's history. Repository metadata that does not
  establish the routing facts fails the project explicitly. A branch head
  whose detail cannot be read stays unresolved, `PARTIAL /
  BRANCH_HEADS_UNRESOLVED`, never stale or fresh.
  ([docs/spec/github-adapter.md](docs/spec/github-adapter.md) has the table.)
- **A register state outside the vocabulary is an invalid register**, not an
  open item (`PV-AUDIT-REGISTER-STATE-001`): `clsoed`, `17` or `false` no
  longer manufacture an open target or debt item.
- **A wait hint that cannot be read is no hint** (`PV-AUDIT-GITHUB-RETRY-HEADER-001`):
  `Retry-After: inf` or an overflowing reset epoch used to escape as
  `OverflowError`; the bounded backoff applies and the answer's own
  classification stands.
- **A redirect never carries the token off the API origin**
  (`PV-AUDIT-GITHUB-REDIRECT-AUTH-001`). `urllib` copies `Authorization` onto
  a redirected request, to any host; the transport now follows redirects only
  to the configured API origin and refuses the rest as `REDIRECT_REFUSED`. A
  renamed repository still resolves.
- **The entity-tag cache is `devostasis.http-cache.v2`**
  (`PV-AUDIT-GITHUB-CACHE-INTEGRITY-001`): an entry is replayed after a 304
  only when its complete shape is readable and its body still hashes to the
  digest stored beside the tag; a corrupt entry or a previous cache file is a
  miss and one unconditional refetch, never a replayed body and never a
  `ValueError` while loading. The first fleet run after the upgrade pays a
  full quota once.
- **The canonical decoder is as strict as the writer**
  (`PV-AUDIT-CANONICAL-NONFINITE/DECIMAL/UNICODE/JSON-PARSER-001`): decimal
  and exponent numbers, `NaN` and the infinities, an object naming a member
  twice, and an unpaired surrogate are refused when read, as a
  canonicalization error, instead of becoming a host value that a later
  check may or may not catch. All 308 bundles of the fleet's store still
  read and verify.

The review pass of 2026-09-22, each defect reproduced before it was fixed:

- **A successful response of the wrong shape costs one inventory, not the
  project.** `GET /actions/runs` answering 200 with no body, or
  `GET /releases` answering an object instead of a list, escaped as
  `AttributeError`; `run_all`'s boundary caught it, so the project produced no
  bundle at all. Both are now `ERROR / UNEXPECTED_PAYLOAD` on that inventory
  alone, like every other provider failure, and the rest of the evidence is
  still collected. The review of this change (`PV-REV-PR-029`) found the same
  hole one endpoint over: `GET /actions/workflows` answering 200 with a body
  that is not an object, or a `total_count` that is not a non-negative
  integer, raised past the `WORKFLOWS_UNAVAILABLE` fallback. The count is now
  validated before it is read; a malformed one is `UNEXPECTED_PAYLOAD`, the
  receipt says `WORKFLOWS_UNAVAILABLE:UNEXPECTED_PAYLOAD`, check suites are
  sampled as for any other failed lookup, and no count is invented.
- **A failed workflow lookup is no longer silent.** When
  `GET /actions/workflows` fails (a token without `actions: read` is enough)
  the collector samples check suites instead, Actions-created suites
  included, and the evidence is parent-level. That was correct and invisible:
  the receipt said `CI_SURFACE:GITHUB_CHECK_SUITES_SAMPLED` and nothing about
  why. It now also carries `WORKFLOWS_UNAVAILABLE:<reason>`, mirroring
  `CHECK_SUITES_UNAVAILABLE`. Capability notes are identity-bearing, so a
  project in exactly that state gets a new bundle id once; every other bundle
  is unchanged.
- **The build metadata names the setuptools that can read it.**
  `pyproject.toml` uses PEP 639 (`license = "MIT"`, `license-files`) but
  required only `setuptools>=69`. setuptools 76 rejects the file
  (`project.license must be valid exactly by one definition`); isolated builds
  always fetched a newer setuptools, which is why CI never saw it, and
  `--no-build-isolation` did. Now `setuptools>=77`.
- **The documentation described a token order the code never used.** The
  configured `token_env` is read first, before `DEVOSTASIS_GITHUB_TOKEN`,
  `GITHUB_TOKEN` and `GH_TOKEN`; the configuration guide and the adapter page
  said last. The code was right, since a runner's own `GITHUB_TOKEN` must not
  override the token a fleet configuration names, and the pages now say so.
- **Bookkeeping:** the README status paragraph still described 0.1.0; the
  roadmap listed issue #9 as "filed, not yet indexed" after it had been
  answered, and had no row for the accepted judgements this repository has
  not adopted (#13, #19, #21, #12 finding 3, the cases of #9). It has one now,
  under the standing obligation that names them. Three findings of the same
  review pass are filed as issues rather than fixed here, because each is a
  rule or a contract decision: Clutter `UNKNOWN` past the branch lookup cap
  ([#26](https://github.com/drevendev/Devostasis/issues/26)),
  `devostasis build` accepting flags that disagree with the receipt
  ([#27](https://github.com/drevendev/Devostasis/issues/27)), and
  comparability decided from the convenience copy `latest/`
  ([#28](https://github.com/drevendev/Devostasis/issues/28)).

## 0.1.8 (2026-09-07)

Roadmap targets B5 and B1: the first accepted band ordering, and the format
and runner that make a conformance case executable. No threshold, window or
gauge changed, and no rule was retuned.

- **Band ordering (target B5, `PV-BAND-ORDER-001`).** Three Vitals now declare
  which of two of *their own* bands is better: Clutter
  `CLEAN > LIGHT > CLUTTERED > HEAVY`, Flow `MOVING > CONGESTED > GRIDLOCKED`
  for a live queue, Integrity `CLEAN > FLAKY > FAILING` and
  `SPARSE > SPARSE_MIXED`. `delta.json` therefore emits `IMPROVED` and
  `WORSENED` where the order applies. Pulse, Horizon, Direction and Debt
  declare no order at all, and neither does `NO_QUEUE` against a live queue or
  an Integrity evidence state against a verdict: those transitions stay
  `CHANGED`. No order is declared across Vitals or across projects, and none of
  this is a step towards an aggregate.
- **A direction is only ever reported about exact measurements.** The pair must
  be `COMPARABLE`, the `rule_id` unchanged and both sides `AVAILABLE` with
  `EXACT` band semantics; a `DEGRADED` band is a bound, and a move between
  bounds is not an improvement. The rule version boundary and observability
  transitions keep precedence, and a gauge that moved inside a band is still
  `UNCHANGED`. Every row that could have been ordered but was not says why:
  `BAND_ORDER_NOT_DECLARED`, `BAND_ORDER_INCOMPARABLE` or
  `BAND_ORDER_NOT_ELIGIBLE`.
- **`devostasis.delta.v2`** carries the two new classes and names the ordering
  it applied in `band_order_contract` and `band_order_version`, so a stored
  delta says under which order its classes were decided. This is the fourth
  and, with the consumer surface now frozen, the last planned move of bundle
  identity: every row of the consumer surface in the ROADMAP is stable.
- **Executable conformance vectors (target B1).** A conformance case can now be
  written as JSON and executed: `devostasis.vectors.v1` with a `vital` kind
  that evaluates one Vital over raw observation envelopes and a `delta` kind
  that compares two snapshots, a runner, a `devostasis vectors` command and a
  published schema ([docs/spec/vectors.md](docs/spec/vectors.md)). It fails
  closed: an unknown kind, an unknown key, an unknown comparison status, a
  malformed envelope or a duplicate case id is an error, never a skipped case
  that looks like a pass. The schema declares the partial evidence envelope a
  vector actually states, and a test holds it to the envelopes the corpus
  writes, so the runner and the published schema cannot accept different files.
- **The ordering ships as fifteen vectors, not as prose.** `ORDER-01..15` live
  in `tests/vectors/band-order.json`, run inside the ordinary test suite and in
  CI through the command line, and the conformance table cites them as
  `vector:ORDER-nn`. A third drift guard now checks both directions: a citation
  without a vector fails, and a vector nobody cites fails.
- **Those fifteen carry the meanings the contract gives them.** The first
  version of this release derived the cases from the contract's rules instead
  of transcribing its `Required conformance cases` section, which moved every
  identifier from `ORDER-02` onward onto a different claim — a research
  identifier is never reused, and `conformance.md` says so on the same page.
  `PV-SPEC-001` found it; the cases are now transcribed, and the two accepted
  pairs the corpus never executed (`NO_QUEUE` against `GRIDLOCKED`,
  `SPARSE_MIXED` to `FAILING`) are executed. Semantics did not change: the
  ordering itself was conformant, and no band, threshold or rule moved.
  The split, adjacency and precedence cases this implementation wanted beyond
  the accepted set are kept under local `DEV-ORDER` ids, which belong to no
  research unit. A fourth guard holds each `ORDER-nn` to the accepted case name
  and to the band pairs that case names, because the first two guards pass
  happily while every identifier means something else.
- **A vector case can state more than one pair.** `given.comparisons` is a
  list, each entry with its own `expect`, and the case passes only when all of
  them do. Accepted cases are written that way — "`GRIDLOCKED → CONGESTED →
  MOVING` follows the WORSENED/IMPROVED direction" is six comparisons, "every
  unequal Pulse band pair" is twelve — and splitting one across several vectors
  would split its identifier. `ORDER-01..15` now execute 85 comparisons between
  them. `devostasis.vectors.v1` is unchanged for the single-pair shape it
  already had.
- The vectors of `PV-TEST-001` are still owed by the research process. The 70
  named cases without a test remain open (debt D-1), but what was missing on
  our side is now built, so those vectors arrive executable instead of needing
  translation.
- **A documented pin that names a tag nobody published is now a red build.**
  `tests/test_release_pins.py` proves the pins agree with `pyproject.toml`; it
  cannot prove the tag they name exists, because on a release branch that tag
  legitimately does not exist yet. Nothing closed the window afterwards, and
  0.1.8 fell into it: every pin said `v0.1.8` while master carried no such tag,
  so the install command in the README failed for anyone who ran it. A new
  `Released pins resolve` workflow runs daily on master and resolves every
  documented pin against the remote. Daily rather than per push, because the
  window is legitimate for as long as it takes to tag a merge and not a day
  longer. The self-observation workflow could never have caught this: it passes
  `devostasis-ref: ${{ github.sha }}`, which is right for its purpose and means
  the one live exercise of `observe-self.yml` overrides the input that goes
  stale (issue #18).
- **Bookkeeping:** the 0.1.7 section still said "unreleased" after v0.1.7 was
  tagged and released, which is the exact drift debt D-4 names.

Alongside the two targets, the defects the external review of 0.1.7 found
([#12](https://github.com/drevendev/Devostasis/issues/12), finding 5). Each was
reproduced before it was fixed. No contract, threshold or rule changed.

- **A malformed title no longer ends a fleet run.** `_title` crashed with
  `IndexError` on a title that is only whitespace and with `AttributeError` on
  one of the wrong type. Neither is a `RegisterError`, so neither reached the
  collector's error boundary. `_title` is now total for provider payload — a
  commit message, change-request or issue title of the wrong type is a missing
  title — while a register title of the wrong type is a `RegisterError` and
  reaches the snapshot as `ERROR` / `INVALID_REGISTER`, which is what the
  register contract says it should be.
- **Linkage evidence is the exception, and it is now declared.** A title or
  body of the wrong type is a missing title everywhere except where the target
  marker lives: `_target_refs` joined the raw fields, so a non-string there
  raised `TypeError` under `planning.source = file`, and reading it as an
  absent link would report a project unlinked on evidence nobody could parse.
  Unreadable title, body or milestone is now `LinkageEvidenceError`, a
  `CollectionError`, so the project fails explicitly with its reason while the
  rest of the fleet is still observed. A change request with no marker is
  still simply unlinked, because absent evidence is a fact and unreadable
  evidence is not.
- **A successful response that is not JSON is a declared provider failure.**
  `UrllibTransport.get` raised `json.JSONDecodeError` out of every handler on
  an HTTP 200 with an unreadable body. It is now `ApiFailure` with
  `MALFORMED_RESPONSE`, so it becomes an observation status like every other
  provider failure.
- **One project's failure costs one project.** `run_all` had no boundary of its
  own, so anything `run_project` did not anticipate stopped every project
  queued behind it, skipped the entity-tag cache write and left the fleet index
  stale. Each project now fails on its own, keeping its reason and its
  unsuccessful outcome, so the run still exits non-zero.

## 0.1.7 (2026-09-06)

A review of what exists, with no new capability. Six defects found and fixed,
one open question filed, and two guards added so the same classes cannot come
back. No rule, threshold, window or gauge changed.

- **A capped release enumeration reported itself as complete.** The collector
  always emitted `AVAILABLE` with `recent_only`, so a repository with more
  than thirty releases had the newest thirty recorded as the whole truth. A
  full page is now `PARTIAL` with the cap reason, like every other
  enumeration. No band reads releases, so no band was ever wrong.
- **A `PARTIAL` release inventory left no coverage note in `activity.json`**,
  so a truncated list looked complete in the report even when the collector
  had flagged it.
- **Activity could declare an interval wider than its evidence.** The
  inventories reach back 28 days; after a longer outage the report claimed the
  whole gap and the unobserved part read as "nothing happened". It now carries
  `INTERVAL_EXCEEDS_EVIDENCE_WINDOW:evidence_from=<timestamp>`. Whether the
  collection window should widen instead is
  [issue #9](https://github.com/drevendev/Devostasis/issues/9) for the
  reporting contract.
- **A `304` answered to a request that carried no entity tag** was treated as
  a successful empty body. It is now `UNEXPECTED_NOT_MODIFIED`, an explicit
  failure, because an empty answer that nobody asked for is not evidence.
- **A cached entry whose body was null kept its tag**, so every later `304`
  read as a miss and refetched forever. Such an entry is no longer stored.
- **`all_projects` collected a `renames` list that nothing consumed.** Rename
  history stays in the project index; a fleet consumer follows
  `immutable_project_id`, which the fleet index already carries.
- **Bookkeeping:** target B4 shipped in 0.1.6 and was never closed in the
  register.
- **Two guards against specification drift** (debt D-4): the conformance table
  may not cite a test that no longer exists, the specification index must link
  every specification page, and every contract identifier the runtime writes
  into a bundle must be findable in the specification. The last one immediately
  found five member schema identifiers that were documented nowhere, now listed
  in [bundle.md](docs/spec/bundle.md).

## 0.1.6 (2026-09-06)

Roadmap target B4: spend provider quota on what actually changed, wait only
when waiting helps, and truncate honestly when a budget runs out. No rule,
threshold, window or gauge changed.

- **Conditional requests.** `--cache <dir>` keeps the entity tags of previous
  runs (`devostasis.http-cache.v1`); an unchanged answer comes back as
  `304 Not Modified`, replays the stored body, and costs a round trip but no
  rate-limit quota. A missing or corrupt cache costs requests, never
  correctness.
- **Bounded retries.** A retryable failure waits only as long as the provider
  asked, through `Retry-After` or the rate-limit reset, and only while a
  single wait and a total waiting budget allow it. A primary rate limit resets
  on the hour, so waiting it out would be a hang: that becomes an explicit
  `ERROR / RATE_LIMITED` observation and the run moves on.
- **A request budget** per project, `--request-budget <n>`, so one very active
  repository cannot starve the rest of a fleet. When it bites, a partially
  enumerated inventory is `PARTIAL` and one that never started is `UNKNOWN`,
  both with the reason `REQUEST_BUDGET_EXHAUSTED`, and the receipt carries a
  matching capability note. A short list is never reported as complete.
- **Receipt `devostasis.receipt.v2`** no longer records the request count.
  How evidence was fetched is a property of the client and its cache, not of
  the evidence, and the receipt is identity-bearing: without this change,
  turning the cache on would have silently moved every `bundle_id`. The counts
  moved to the bundle's post-identity `run_meta`, which now also carries
  `billed_requests`, `conditional_hits` and `retries`. Bundles written under
  `devostasis.receipt.v1` remain verifiable, and their identities are
  unaffected because verification uses each bundle's stored preimage.
- Debt item D-2 is closed by this change; target B2 is closed as delivered.

Bundle identities change once for identical evidence, because the receipt
shape changed. Comparability is unaffected: the receipt is not part of the
semantic configuration.

## 0.1.5 (2026-09-06)

Roadmap target B2 and conformance case RPT-7: a project is its immutable id,
not its path. No rule, threshold, window or gauge changed.

- The history store locates a project by
  `project_identity.immutable_project_id` and uses the locator only as the
  human-readable place to put it. A renamed or transferred repository is
  relocated once to its new locator instead of starting a second history, and
  the move is recorded in the project index as a `renames` entry.
- Fail closed on ambiguity: a locator already held by a different project is
  refused rather than merged, and `latest()` reports the conflict instead of
  comparing against the wrong project's history. A repository whose old name
  is immediately reused by a new repository therefore yields two separate
  histories, because the ids differ.
- An adapter that cannot prove an immutable id keeps the previous behaviour:
  the locator is the identity and a rename starts a `BASELINE`, which is more
  honest than guessing that two names are the same project.
- Bundles are unchanged, including the `project_key` each records: a bundle
  keeps the locator it was observed under, and moving the directory does not
  rewrite it. Every relocated bundle still verifies.
- Debt item D-3 is closed by this change; targets A1 and B6 are closed as
  delivered.
- New calibration finding 9 for the research process, found by dogfooding:
  closing a delivered target un-links the pull requests that delivered it,
  because Direction counts links to *open* targets only.

## 0.1.4 (2026-09-06)

Roadmap target B6: the fleet as data, not only as Markdown. No rule,
threshold, window or gauge changed.

- `projects/index.json` (`devostasis.fleet.v1`, schema
  `schemas/fleet-index.schema.json`): one entry per project with the locator,
  the immutable project id, `observed_at`, `bundle_id`, `comparison_status`,
  the project's own attention order and one row per Vital carrying band,
  evaluation status, gauge and demand level, plus relative paths to the report
  and to the immutable bundle the entry came from. Written beside
  `projects/README.md` by every fleet run and by `devostasis index`.
- The index adds no meaning: every value comes from the latest bundle, which
  stays authoritative. `aggregate` and `cross_project_order` are explicitly
  `null`, because no accepted contract says what it means for one project's
  `CRITICAL` to outrank another's; a fleet-wide priority is the consumer's
  policy.
- Entries are ordered by project key and the file carries no generation
  timestamp, so a run that changes nothing rewrites the same bytes and the
  store stays quiet in version control.
- A bundle written before the demand interface existed yields `null` levels
  and an empty attention order rather than invented ones.

This is the last change to the consumer surface that the implementation owns.
The remaining one is the band ordering contract, which decides whether
`delta.json` ever emits `IMPROVED` and `WORSENED`, and it belongs to the
research process.

## 0.1.3 (2026-09-06)

Roadmap target A1: Devostasis declares its own plan and debt, so its report
about itself stops saying `UNDECLARED` and `UNINSTRUMENTED` and starts saying
something a consumer can act on. No rule, threshold, window or gauge changed.

- `.devostasis/targets.json` and `.devostasis/debt.json`: this repository's
  planning targets and registered maintenance obligations, maintained by hand
  and mirroring the phases in `ROADMAP.md`. They are also the worked example
  an adopter copies, replacing the fictional paths in the specification.
- Self-observation reads them: `self-observe.yml` passes `planning-source:
  file`, both register paths and a debt `mapping_version`, so the workflow and
  the fleet observation see the same metadata and cannot disagree.
- `CONTRIBUTING.md` documents the `Target: <id>` line that links a pull
  request to a target, the rule that a `due` date is written only when it is
  real, and the boundary between a target and a debt item.
- `docs/deployment.md` names this repository as the worked example and states
  that registers are read from the default branch, so a register on a working
  branch is `REGISTER_NOT_FOUND` until it merges.
- The reusable workflow's default `devostasis-ref` is `v0.1.3`, so a caller
  that pins the workflow at this tag and passes no ref installs this engine
  rather than the previous one (debt item D-5). Every documented pin in the
  README and the deployment guide names the same tag, and
  `tests/test_release_pins.py` fails the build when one of them, the package
  version or the changelog section falls behind.

This is the first real-repository evidence for `planning.source = file` and
`debt.source = file`; until now both contracts existed only in synthetic
fixtures. Devostasis's own history is `INCOMPARABLE` once when the fleet
configuration adopts the registers, because the semantic configuration
changed.

## 0.1.2 (2026-09-06)

Adopts the first round of research judgements and calibration repairs made
against real bundles (PV-REV-ARTIFACT-005, PV-REV-REPORT-001,
PV-REV-GAUGE-001, PV-ROLE-001, PV-CAL-002, PV-CAL-003 and their repair
units). No numeric threshold or window changed.

- Flow rule `flow.bands.v1`: a positively observed empty queue is `NO_QUEUE`
  regardless of the historical merge median (PV-FLOW-EMPTY-QUEUE-001); the
  classifier consumes the exact rational median merge latency in seconds,
  `forge.change_requests.median_time_to_merge_seconds_28d`, with the
  boundaries 604800 s and 1209600 s as exact conversions of 168 h and 336 h
  (PV-FLOW-MERGE-LATENCY-001); the whole-hour observation stays as a derived
  presentation projection. Fractional timestamps are handled exactly.
- Pulse rule `pulse.bands.v1`: a capped required enumeration is evaluated
  over every admissible completion of the missing tail
  (PV-PULSE-REQUIRED-LOWER-BOUND-001): one forced band, or every reachable
  band in `possible_bands`, or `UNKNOWN` when no bound is defensible.
- Delta: a Vital whose rule version changed since the previous bundle is
  `INCOMPARABLE` on its own (`RULE_VERSION_BOUNDARY`) while the bundle stays
  `COMPARABLE`; historical bands are never reinterpreted.
- Demand `devostasis.demand.v2`: the attention order is level rank, then
  canonical Vital order; the cross-Vital gauge tie-break of v1 is removed
  (ROLE-01 SAME_LEVEL_GAUGE_INVARIANCE) and `attention_key` is gone.
- Verification adopts PV-EFFECTIVE-CONFIG-AUTHORITY-001: the stored effective
  config is schema-validated fail-closed
  (`EFFECTIVE_CONFIG_SCHEMA_INVALID_OR_UNSUPPORTED`, ART-25), the canonical
  member profile is derived from it and checked against the manifest, the
  members and the identity markers (`CANONICAL_MEMBER_PROFILE_MISMATCH`,
  ART-23), and the report is replayed only from the validated stored config
  (ART-24). Bundles of both effective-config schemas (v1 history, v2) verify.
- Renderer `devostasis.render.v4`: states the v2 demand ordering and renders
  exact rational durations.
- GitHub outcome map `devostasis.ci-outcomes.github.v1` confirmed by
  PV-CAL-003 (`timed_out` is `VERIFY_FAIL`, `startup_failure` is `UNKNOWN`),
  with CI-OUTCOME-01..04 tests.
- Documentation: gauges accepted (PV-REV-GAUGE-001) and their cross-Vital
  boundary stated; reporting decisions of PV-REV-REPORT-001 (permission-domain
  stores, optional `report.html`, retention, self-observation is not durable
  history); provenance, conformance table and calibration findings updated;
  the stale gauges docstring fixed.
- Conformance tests added: FLOW-EQ-01..06, FLOW-PREC-01..09, PULSE-CAP-01..05,
  ROLE-01..04, CI-OUTCOME-01..04, ART-23..ART-25, rule version boundary,
  legacy effective-config v1 verification.

Bundle identities change for every project (new rule ids, demand v2,
renderer v4). History stays `COMPARABLE`; Flow and Pulse report
`RULE_VERSION_BOUNDARY` on the first bundle after the upgrade.

## 0.1.1 (2026-09-05)

- Self-observation: the reusable workflow `.github/workflows/observe-self.yml`
  lets any repository observe itself with its own `GITHUB_TOKEN`, upload the
  bundle as an artifact, print the status card and attention order in the job
  summary and expose `attention`, `attention-order`, `levels`, `bands`,
  `gauges`, `bundle-id` and `comparison-status` as outputs; optional read-only
  comparison against a history store.
- `devostasis run --repo owner/name` observes one repository from flags
  without a configuration file; `devostasis actions-summary` writes the job
  summary and step outputs.
- Devostasis observes itself weekly with the workflow it ships.
- No contract, policy or bundle change: bundles of 0.1.0 and 0.1.1 are
  identical for identical evidence.

## 0.1.0 (2026-09-05)

First minimum viable version: useful on real repositories today.

- Observation envelope `RAW-OBS-V0` with explicit AVAILABLE / PARTIAL /
  UNAVAILABLE / FORBIDDEN / UNKNOWN / ERROR statuses, orthogonal freshness and
  collection receipts.
- Seven deterministic Vitals under `PV-VITALS-V1-002`: Horizon, Clutter,
  Direction, Flow, Integrity, Debt and Pulse, with the V0 thresholds frozen as
  `devostasis.policy.v1`.
- Integrity implements `PV-CI-UNIT-004`: revision-level verdicts,
  provider-native parent identity (GitHub Actions run + attempt, check suite),
  greatest-attempt current state, failure-sticky history.
- Read-only GitHub adapter (REST, stdlib only) with pagination caps reported as
  PARTIAL and tier or permission failures reported as UNAVAILABLE / FORBIDDEN.
  Caps sized for very active repositories (3000 commits, 2000 change requests
  or issues, 2000 workflow runs per window); a capped newest-first enumeration
  is a lower bound, and Pulse degrades to a conservative lower bound instead
  of UNKNOWN.
- Immutable bundle (`devostasis.bundle.v1`): manifest, snapshot, delta,
  activity, observations, persisted effective config and a deterministic
  Markdown report; SHA-256 identity over an acyclic preimage
  (`PV-BUNDLE-ID-002`, `PV-EFFECTIVE-CONFIG-001`).
- Append-only filesystem history store with BASELINE / COMPARABLE /
  HISTORY_GAP / INCOMPARABLE comparison and a fleet overview.
- CLI: `observe`, `evaluate`, `run`, `build`, `verify`, `render`, `index`,
  `gauges`.
- Gauges (`devostasis.gauge.v1`): deterministic 0-100 placement of each
  band on the scale of its phenomenon, persisted as the identity-bearing
  member `gauges.json`, rendered as a status card in `report.md` and in the
  fleet overview; the band stays the semantic authority.
- Demand interface (`devostasis.demand.v1`, member `demand.json`): one level
  per Vital from a versioned, overridable band-to-level table plus an
  attention order; `UNRESOLVED` for missing evidence; no aggregate.
- Register files: planning targets from `targets.json` and debt items from
  `debt.json` committed to the observed repository, change requests linked
  to targets with a `Target: <id>` marker; label-based debt mapping kept.
- Display configuration: which Vitals, which card components (bar, number,
  band) and which report sections are rendered; part of the effective config
  and therefore of the bundle identity (renderer `devostasis.render.v3`,
  bundle `devostasis.bundle.v2`, effective config `v2`).
- `demand` CLI command; older `bundle.v1` history stays verifiable and
  comparable.
- 107 conformance and unit tests named after the research cases they
  implement.
- Released under the MIT license.
