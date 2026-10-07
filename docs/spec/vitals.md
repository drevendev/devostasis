# The seven Vitals (PV-VITALS-V1-002, policy devostasis.policy.v1)

## Global rules

- **G1** Missing, unavailable, forbidden, stale, partial, contradictory,
  unknown or errored evidence never becomes zero, empty, false, healthy or
  clean unless that exact state is positively observed.
- **G2** `AVAILABLE` is emitted only when every observation the matched
  predicate needs is complete and fresh. A `DEGRADED` result is a conservative
  bound and cannot improve the band relative to what unknown favourable
  evidence could prove.
- **G3** Rules are evaluated top-down inside a Vital; first match wins.
- **G4** Same normalized observations plus the same policy and configuration
  versions produce the same result, byte for byte after canonicalization.
- **G5** `UNKNOWN` in one Vital never fabricates a band in another.
- **G6** Vitals are not independent votes. Shared signals are declared through
  `shared_signal_groups` and `dependency_group_ids` and are never combined into
  an authoritative score.
- **G7** Text classification, sentiment, embeddings, language models and
  provider-specific labels have no authority unless converted upstream into
  explicit configuration or an enumerated observation with provenance.
- **G8** Adapters normalize topology but preserve unsupported capabilities as
  explicit availability states.
- **G9** Numeric thresholds and windows are policy constants; this version
  freezes the V0 values and adds none.

Every Vital emits: `vital_id`, `vital_version`, `rule_id`, `band`,
`evaluation_status` (`AVAILABLE`, `DEGRADED`, `UNKNOWN`), `band_semantics`
(`EXACT`, `CONSERVATIVE_LOWER_BOUND`, `CONSERVATIVE_UPPER_BOUND`,
`NON_AUTHORITATIVE_CONSERVATIVE_SUPERSET`), `possible_bands` when degraded
(a `DEGRADED` band that every completion of the missing evidence reaches is
`EXACT`, and carries the singleton or no `possible_bands` as its contract
says),
`inputs` with status and freshness, `derived` metrics actually used,
`shared_signal_groups`, `dependency_group_ids`, `diagnostics` and a
deterministic `explanation`. An `UNKNOWN` Vital has `band = null`.

`rule_id` versions the evaluation rule of one Vital independently of the
taxonomy and the policy constants. The seven rule ids of this version:

| Vital | `rule_id` | Since |
| --- | --- | --- |
| Horizon | `horizon.bands.v2` | 0.2.0 (partial target enumeration, PV-HORIZON-PARTIAL-001) |
| Clutter | `clutter.bands.v1` | 0.1.9 (the incomplete-evidence contract and its subset proof) |
| Direction | `direction.bands.v2` | 0.2.0 (state-neutral and incomplete linkage, PV-REV-DIRECTION-CLOSED-TARGET-001 and PV-DIRECTION-INCOMPLETE-001) |
| Flow | `flow.bands.v1` | 0.1.2 (the calibration repairs) |
| Integrity | `integrity.bands.v1+ci-unit-004+hist-002` | 0.2.0 (durable revision history, PV-HIST-002; the band table and the 0.1.9 judgements unchanged) |
| Debt | `debt.bands.v2` | 0.2.0 (partial register, PV-DEBT-PARTIAL-001) |
| Pulse | `pulse.bands.v1` | 0.1.2 (the calibration repairs) |

A rule version change never rewrites a
historical bundle: the affected Vital compares as `INCOMPARABLE`
(`RULE_VERSION_BOUNDARY`) across the boundary while the rest of the bundle
stays comparable ([history-and-reports.md](history-and-reports.md)).

## Pulse

*How intense is recent observable activity?* Not productivity; low Pulse is
not automatically unhealthy.

Required: `git.default_branch.commits.count_28d`,
`git.default_branch.commit_active_days_28d`. Optional channels:
`forge.change_requests.updated_count_28d`, `forge.issues.updated_count_28d`.

Derived: `activity_events_28d` = commits + observed channel updates;
`channel_count` = channels with positive activity.

| Band | Rule |
| --- | --- |
| SURGING | `commit_active_days_28d >= 15` or (`activity_events_28d >= 40` and `channel_count >= 2`) |
| STEADY | `commit_active_days_28d >= 3` and `activity_events_28d >= 5` |
| QUIET | `activity_events_28d > 0` |
| DORMANT | `activity_events_28d = 0` |

Degradation: a required input that is missing, forbidden, unknown, errored or
stale yields `UNKNOWN`. An optional channel that is not exact is never treated
as zero: the band is computed from the observed channels as a
`CONSERVATIVE_LOWER_BOUND` with `possible_bands` listing every band from that
bound upward (zero observed activity therefore degrades to `DORMANT`, not
`QUIET`).

A required input that is `PARTIAL` with a fresh value because a newest-first
enumeration was capped follows **PV-PULSE-REQUIRED-LOWER-BOUND-001** (rule
`pulse.bands.v1`, diagnostic `REQUIRED_INPUT_PARTIAL`): the observed rows are
a lower bound, never complete evidence. The classifier is evaluated over every
admissible completion of the missing tail (more commits, more active days up
to the window, more activity on unobserved optional channels). If every
completion yields the same band, that band is emitted as `DEGRADED` /
`CONSERVATIVE_LOWER_BOUND` with a `possible_bands` of length one
(PULSE-CAP-01). If completions cross a band boundary, `possible_bands` lists
every reachable band and the lowest one is reported without any exactness
claim (PULSE-CAP-02). A capped input without a fresh value stays `UNKNOWN`
(PULSE-CAP-03). Optional evidence never turns a capped required input into
exact certainty (PULSE-CAP-04). Provider page size, order and chunking are
acquisition metadata and cannot change the result (PULSE-CAP-05). The
derived metrics name the bounded inputs (`commits_28d_semantics`,
`commit_active_days_28d_semantics` = `LOWER_BOUND`).

The frozen active-day thresholds are unchanged. Substantial work concentrated
on two active days is `QUIET`; PV-CAL-003 recorded this as an open
calibration observation, not a defect.

Activity that comes from the issue channel alone, with no commit and no
change-request update, carries the diagnostic `PULSE_ISSUE_ONLY_ACTIVITY`
(permanent case T5). It is provenance: it says where the observed activity
came from and implies nothing about productivity, progress or quality.

Groups: `DEFAULT_BRANCH_ACTIVITY`, `CHANGE_REQUEST_ACTIVITY`, `ISSUE_ACTIVITY`;
dependencies `FLOW_PULSE_ACTIVITY`, `DIRECTION_PULSE_ACTIVITY`.

## Flow

*What is the state and friction of the change-request queue?* `NO_QUEUE` is
descriptive, never positive.

Required: `forge.change_requests.open_count`, `.merged_count_28d`; conditional
`.oldest_open_age_days` when open > 0 and
`.median_time_to_merge_seconds_28d` when open > 0 and merged > 0. The median
is an exact rational record `{"numerator": n, "denominator": d}` in seconds
(**PV-FLOW-MERGE-LATENCY-001**). Any applicable input that is not exact
yields `UNKNOWN`.

Rule `flow.bands.v1` applies **PV-FLOW-EMPTY-QUEUE-001** first: a positively
observed empty queue is `NO_QUEUE`, and the friction predicates apply only
when open > 0. Historical merge latency is evidence about completed change
requests and cannot congest a queue that does not exist.

| Band | Rule |
| --- | --- |
| NO_QUEUE | `open = 0`, whatever the historical median |
| GRIDLOCKED | `open > 0` and ((`open >= 3` and `oldest >= 30` days and `merged_28d = 0`) or (`open >= 10` and `median > 1209600` s)) |
| CONGESTED | `open > 0` and (`oldest >= 14` days or `open >= 10` or `median > 604800` s) |
| MOVING | `open > 0` |

The second boundaries are the exact conversions of the frozen 168 h and 336 h
constants with unchanged strictness: a median of exactly 604800 s is not
`> 168 h` (FLOW-PREC-03..05). The whole-hour value
`median_time_to_merge_hours_28d` is still emitted, derived from the exact
record, for presentation and compatibility; it never enters classification.
When the queue is empty and a historical median above 168 h exists, the
diagnostic `FLOW_HISTORICAL_MEDIAN_NOT_APPLICABLE:EMPTY_QUEUE` keeps that
evidence visible (FLOW-EQ-01). Rule `flow.bands.v0` classified this case
`CONGESTED` with `FLOW_MEDIAN_WITH_EMPTY_QUEUE`; PV-CAL-002 judged that a
construct defect, not a threshold to retune.

Groups: `CHANGE_REQUEST_INVENTORY`, `CHANGE_REQUEST_ACTIVITY`; dependencies
`CLUTTER_FLOW_FORGE`, `FLOW_PULSE_ACTIVITY`.

## Integrity

*What does automated verification say about recent immutable revisions?*
Inputs and revision semantics are in [integrity-ci.md](integrity-ci.md).
Derived: `decisive_count_14d`, `failed_count_14d`, `failure_ratio_14d`
(exact rational), the latest revision's current verdict.

| Band | Rule |
| --- | --- |
| UNINSTRUMENTED | CI positively observed as not configured and no verification evidence |
| NO_RECENT_RUNS | CI configured, no revision in the window has a verification execution |
| NO_DECISIVE_RUNS | executions exist but no revision contributes a decisive verdict |
| FAILING | latest decisive verdict is `VERIFY_FAIL`, or `decisive >= 4` and `failed / decisive >= 1/4` |
| FLAKY | `decisive >= 4` and `0 < failed / decisive < 1/4` |
| CLEAN | `decisive >= 4`, `failed = 0`, latest decisive verdict `VERIFY_PASS` |
| SPARSE_MIXED | `1 <= decisive <= 3` with at least one failure |
| SPARSE | `1 <= decisive <= 3` with no failure |

The decisive population also carries its `sample_strength`: `SPARSE` for one
to three decisive revisions, `ESTABLISHED` from four, and the diagnostic
`CI_SPARSE_SAMPLE` is emitted whenever the sample is sparse (R1, R2). A sparse
band is exact about the revisions it counts and says so, so that `FAILING`
over one revision is not read as an established rate.

History is counted over the durable revision history of **PV-HIST-002**
(rule `integrity.bands.v1+ci-unit-004+hist-002`, HIST-01..20): every attempt
one bundle observed for a revision is carried into the next one while the
revision is in the window, so a failure the provider later hides behind a
passing retry, or forgets through retention, still counts, and exactly once.
Favorable evidence that cannot prove every attempt, a parent-level check suite
or an Actions run whose earlier attempts are not all observed, is
`UNKNOWN_HISTORY` rather than a reconstructed pass (R52). The carrier and its
rules are in [integrity-ci.md](integrity-ci.md#durable-history-pv-hist-002).

Degradation and refusal, under rule `integrity.bands.v1+ci-unit-004+hist-002`:

- a recent revision whose history is `UNKNOWN_HISTORY` makes the Vital
  `UNKNOWN` with no band, each such revision named by
  `REVISION_HISTORY_UNKNOWN:<revision>` and the counts of the others kept in
  `derived`: T9 puts unknown history above every conservative branch, so no
  band is derived around it;
- durable history that proves verification happened while the provider shows
  no current verification at all is `UNKNOWN`
  (`CURRENT_VERIFICATION_NOT_OBSERVED`): a current verdict is never carried
  from an earlier bundle (HIST-16);
- carried history that is not the shape its lineage declares is corrupt
  persisted history and `UNKNOWN` (`REVISION_HISTORY_CARRY_MALFORMED`);

- a required revision series with acquisition status `PARTIAL` is `UNKNOWN`
  with no band (`PV-REV-TEST-003`): the accepted chain has no degraded path
  for a truncated required series, and the counts of what was collected stay
  in `derived`, marked `series_status = PARTIAL`;
- a newest in-scope revision whose current verdict is `UNKNOWN` is `UNKNOWN`
  with no band (`PV-REV-INTEGRITY-UNKNOWN-001`, INT-UNKNOWN-01..06):
  `UNKNOWN` is the absence of an observation, so it never inherits an older
  decisive verdict; the decisive history stays in `derived` and is never
  reconstructed as a pass, and the diagnostic `CURRENT_VERDICT_UNKNOWN`
  names the revision;
- a newest revision whose verification is still unresolved is spoken for by
  no older verdict (`PV-INTEGRITY-TOTALITY-001`, INT-TOTAL-01..14): when the
  history already satisfies the established FAILING predicate on its own
  (`decisive >= 4` and `failed / decisive >= 1/4`) the result is
  `DEGRADED / FAILING / EXACT`, exact for this snapshot while the evaluation
  says the current verification is unresolved; every other history is
  `UNKNOWN` with no band. Both carry `CI_CURRENT_VERIFY_UNRESOLVED`, and no
  `possible_bands` is derived: the accepted contract defines no reachability
  algorithm, and the one this rule version first carried could omit the
  band it emitted;
- when the latest revision has a positively observed non-decisive verdict
  (`NOT_EXECUTED`, `NON_VERIFY_TERMINAL`), the latest decisive revision is
  used and diagnosed `LATEST_REVISION_NON_DECISIVE`; that fallback is never
  applied to `UNKNOWN`, nor to a verdict outside the canonical vocabulary,
  which is read as `UNKNOWN` (`CURRENT_VERDICT_UNRECOGNIZED`);
- `ci.configured` positively false with no decisive evidence and only
  non-decisive recent records is `UNINSTRUMENTED`, with those records kept
  visible and diagnosed `CI_UNINSTRUMENTED_WITH_RECENT_NONDECISIVE_HISTORY`;
  with `ci.configured` true the same records stay `NO_DECISIVE_RUNS`;
- a required series that cannot be used (forbidden, errored, unknown, stale)
  is `UNKNOWN` even beside a positive "not configured", and so is a series
  holding a record whose contribution contradicts its own history state
  (`REVISION_RECORD_INCONSISTENT`).

A persistently failing secondary workflow makes every revision
`FAILURE_OBSERVED` and the band `FAILING`; PV-CAL-002 confirmed this as the
evidence-faithful reading of the accepted contract (ROADMAP finding 3).

Groups: `CI_VERIFICATION`; dependency `INTEGRITY_ONLY`.

## Clutter

*How much unresolved stale residue is observable?* Attention burden, not
value.

Inputs: `forge.issues.open_count`, `.stale_open_count_30d`,
`forge.change_requests.open_count`, `.stale_open_count_14d`,
`git.nondefault_branches.stale_count_30d`, and optionally
`git.nondefault_branches.retention_semantics`. Change-request inventory is
required; the issue and branch components may be explicitly `UNAVAILABLE`.

Derived: `tracked_open_count`, `stale_work_count`, `stale_work_ratio` (when
tracked > 0), `stale_branch_count`.

| Band | Rule |
| --- | --- |
| HEAVY | `stale_work >= 25`, or `ratio >= 1/2` with `tracked >= 4`, or `stale_branches >= 20` |
| CLUTTERED | `stale_work >= 5`, or `ratio >= 1/4` with `tracked >= 4`, or `stale_branches >= 6` |
| LIGHT | `stale_work > 0` or `stale_branches > 0` |
| CLEAN | everything observable is zero |

Rule `clutter.bands.v1` (0.1.9) adopts the accepted incomplete-evidence
contract `PV-CLUTTER-INCOMPLETE-001` (cases `CLU-INCOMPLETE-01..20`) and the
reading `PV-ISSUE-026-RECONCILE-001` gave issue #26, without moving a
threshold or a window. The change-request component is required; the issue
and branch components are optional.

**Incomplete evidence.** A component is *incomplete* when it is explicitly
`UNAVAILABLE` (issues or branches only) or `PARTIAL` with a value that is a
trustworthy observed subset. Trustworthy is proven by the evidence, not
implied by the status (`PV-REV-PR-031-003`, cases `CLU-PARTIAL-TRUST-01..08`):
every `PARTIAL` member's coverage must carry `complete = false` and
`value_semantics = OBSERVED_SUBSET_COUNT` over a non-negative integer, the
declaration that the value counts records the incomplete enumeration did
return (see [observations.md](observations.md)). A `PARTIAL` member without
that proof, with other semantics, or with malformed or self-contradicting
coverage makes its component unresolved, diagnosed
`CLUTTER_PARTIAL_NOT_TRUSTED:<observation>:<reason>`, and is never counted
beside the trusted members. The band is then a *confirmed burden floor*
built only from facts omitted records cannot erase:

- observed stale work counts, complete or partial, add to
  `confirmed_stale_work_lower_bound`;
- a stale branch count adds to `confirmed_stale_branch_lower_bound` only when
  the counted residue is known to be residue: a complete count with
  `CLASSIFIED` or undeclared retention semantics, or a `PARTIAL` count with
  explicit complete `CLASSIFIED` semantics (that is the answer to #26: a
  capped head resolution proves a floor, but only for classified branches);
  an `UNCLASSIFIED` count proves nothing and is diagnosed
  `CLUTTER_BRANCH_PURPOSE_UNCLASSIFIED`, an undeclared one behind a partial
  count is diagnosed `CLUTTER_BRANCH_FLOOR_NOT_PROVEN:UNDECLARED`;
- the ratio predicates apply only when every open and stale count of the
  issue and change-request domain is complete; otherwise the ratio is not
  proof (`CLUTTER_RATIO_NOT_PROOF_INCOMPLETE_DENOMINATOR`), because a
  denominator that can still grow proves nothing, even when the observed
  subset would satisfy the predicate.

| Confirmed floor | Result |
| --- | --- |
| HEAVY | `DEGRADED / HEAVY / EXACT`, no `possible_bands`: the terminal band is invariant under any completion |
| CLUTTERED | `DEGRADED / CLUTTERED / CONSERVATIVE_LOWER_BOUND`, `possible_bands = [CLUTTERED, HEAVY]` |
| LIGHT | `DEGRADED / LIGHT / CONSERVATIVE_LOWER_BOUND`, `possible_bands = [LIGHT, CLUTTERED, HEAVY]` |
| NONE | `UNKNOWN`, no band: incomplete evidence is never positive emptiness, and never `CLEAN` |

Every such result carries `CLUTTER_INCOMPLETE_COMPONENT:<component>:<PARTIAL|UNAVAILABLE>`
for each incomplete component and `CLUTTER_CONFIRMED_BURDEN_FLOOR:<floor>`,
and its `derived` keeps the observed values, the floor, the ratio eligibility
and the retention semantics, so the proof is auditable. `possible_bands`
under the lower-bound rows is a `NON_AUTHORITATIVE_CONSERVATIVE_SUPERSET`,
never a claim that every listed band is exactly reachable.

A `FORBIDDEN`, `UNKNOWN` or `ERROR` component, a stale one, a `PARTIAL`
count without a value or without subset proof, a required change-request
component that is not complete or a proven partial subset, and declared
retention semantics that cannot be read all yield `UNKNOWN`, as before.

**Unclassified branches (T7).** A stale branch is residue only when it is
known to be one. When every component is complete, the branch inventory
declares `retention_semantics = UNCLASSIFIED` and the stale count is
positive, that count is an upper bound on the true residue: the band is the
one the full count reaches, the result is `DEGRADED` with
`CONSERVATIVE_UPPER_BOUND` semantics, `possible_bands` holds every band some
classified residue between zero and the count reaches together with the work
items, and `CLUTTER_BRANCH_PURPOSE_UNCLASSIFIED` says why. When the work
items alone already reach that band, the band is invariant and the result is
`DEGRADED` with `EXACT` semantics and no `possible_bands`. The GitHub adapter
does not emit `retention_semantics` in this version, so a complete count is
read as it always was; emitting it is a fleet-wide decision recorded in issue
#22, and until it is made a capped head resolution on GitHub stays `UNKNOWN`
because its retention is undeclared.

Groups: `FORGE_INVENTORY`, `BRANCH_RESIDUE`; dependency `CLUTTER_FLOW_FORGE`.

## Horizon

*Is future work explicitly declared, and does any declaration reach beyond
the 28-day frame?* Forward visibility, not roadmap quality.

Inputs: `planning.explicit_targets.capability`, `.open_count`,
`.open_with_future_boundary_count`, `.open_beyond_28d_count`,
`.nearest_future_boundary_days`.

| Band | Rule |
| --- | --- |
| EXTENDED | `open_beyond_28d > 0` |
| VISIBLE | `open_with_future_boundary > 0` |
| DECLARED | `open > 0` |
| UNDECLARED | `open = 0`, including capability `UNSUPPORTED` or `SUPPORTED_UNUSED` |

`EXTENDED` is not better than `VISIBLE`. Creating empty milestones improves
Horizon; that is why Horizon exposes counts and never contributes to a score.
A boundary exactly 28 days out is not beyond the frame. Only open targets
count: a closed target with a distant boundary proves nothing here, even while
Direction still counts the work linked to it (DIR-CLOSED-07).

**Partial enumeration** (PV-HORIZON-PARTIAL-001, rule `horizon.bands.v2`). A
fresh target enumeration that returned at least one target proves the
capability `SUPPORTED`, because more targets cannot remove it; one that
returned none proves neither support nor its absence, and Horizon is
`UNKNOWN`. Over a partial enumeration the three counts are observed-subset
lower bounds (`value_semantics = OBSERVED_SUBSET_COUNT`, the proof
`PV-REV-PR-031-003` requires), and the band table is evaluated over every
admissible completion of the missing targets. Horizon declares no order, so a
representative of several reachable bands is never chosen:

| Observed subset | Reachable bands | Result |
| --- | --- | --- |
| PH0: no open target | all four | `UNKNOWN`, `HORIZON_PARTIAL_AMBIGUOUS` |
| PH1: open targets, none with a future boundary | DECLARED, VISIBLE, EXTENDED | `UNKNOWN` |
| PH2: a future boundary, none beyond 28 days | VISIBLE, EXTENDED | `UNKNOWN` |
| PH3: an open target beyond 28 days | EXTENDED | `DEGRADED` / `EXTENDED` / `EXACT`, `possible_bands = [EXTENDED]`, `HORIZON_PARTIAL_BAND_INVARIANT` |

`EXACT` there means the band is the same in every completion of this
snapshot, which the observed target beyond the frame guarantees (existential
monotonicity, not an ordering); it never means the enumeration was complete.
The reachable set is kept in `derived.reachable_bands` as explanation, never
as a band claim, and each bounded count says `LOWER_BOUND` in `derived`. A
partial zero is never `UNDECLARED`. Counts no target population can produce
(`beyond > future` or `future > open`) are refused before classification with
`HORIZON_COUNTS_INCONSISTENT` (HOR-PARTIAL-15). Cases HOR-PARTIAL-01..16.

Groups: `PLANNING_TARGETS`; dependency `HORIZON_DIRECTION_PLANNING`.

## Direction

*Is active change work explicitly traceable to declared targets?* Linkage
must be explicit and auditable (milestone on the change request, or the
register marker); keyword, branch-name or model heuristics are forbidden.

Inputs: `planning.linkage.active_change_requests_count_28d` (N),
`.active_change_requests_linked_count_28d` (L),
`.active_change_requests_unlinked_count_28d` (U),
`.active_change_requests_unresolved_count_28d` (R),
`planning.explicit_targets.capability`, `.links_per_target_28d`,
`.missing_target_reference_count_28d`, `.unresolved_change_requests_28d`.

Every active change request is exactly one of:

- **LINKED**: it carries an explicit reference to a declared target that
  resolves, open or closed;
- **UNLINKED**: it carries no reference, or only references that a complete
  register positively lacks (a broken reference, diagnosed
  `DIRECTION_TARGET_REFERENCE_MISSING`);
- **UNRESOLVED**: its linkage evidence could not be read (a title, body or
  milestone of the wrong type), or a reference could not be resolved
  (register unreadable; resolution unavailable, forbidden, errored or stale).
  Absence from a partial target list is never deletion proof.

| Band | Rule, for k linked of N |
| --- | --- |
| NO_ACTIVE_CHANGE | `N = 0` |
| UNDECLARED | `N > 0` and planning capability positively absent (`UNSUPPORTED`, `SUPPORTED_UNUSED`) |
| SCATTERED | `2k < N`, the V1 `unlinked > linked` |
| MIXED | `k < N` and `2k >= N`, the V1 `0 < unlinked <= linked` |
| FULLY_LINKED | `k = N` |

**State-neutral linkage** (PV-REV-DIRECTION-CLOSED-TARGET-001, rule
`direction.bands.v2`). A change request linked to a declared target stays
linked when the target closes: closing the target the work delivered must not
un-trace the work, and counting only open targets rewarded never closing them
(calibration finding 9). Horizon still counts open targets only, so the two
Vitals may diverge. The count of links to targets that are open now is still
derived, `active_change_requests_linked_to_open_target_count_28d`, for
presentation; it is never the classifier's input.

**Incomplete linkage** (PV-DIRECTION-INCOMPLETE-001). With N complete and
fresh, the capability positively present and `L + U + R = N`, every unresolved
change request may complete either way, so k ranges over `L..L+R` and each k
is mapped through the table above:

- `R = 0`: the exact band, `AVAILABLE`;
- `R > 0` and every k gives the same band: `DEGRADED` / band / `EXACT`,
  `possible_bands` the singleton, `DIRECTION_INCOMPLETE_BAND_INVARIANT`, and
  the unresolved change requests named in `derived.unresolved_change_requests`.
  `FULLY_LINKED` can never be the only reachable band while `R > 0`;
- `R > 0` and the completions cross a boundary: `UNKNOWN` with no band,
  `DIRECTION_INCOMPLETE_AMBIGUOUS`, the reachable set in
  `derived.reachable_bands` as explanation only. Direction declares no order to
  choose a representative by.

A partial global target list does not degrade Direction when every target the
active change requests reference is resolved on its own, as a milestone
embedded in the change request is (DIR-INCOMPLETE-10). An active population
that is itself partial, or a capability neither positively present nor
absent, is `UNKNOWN`. Counts with `L + U + R != N` are refused before
classification with `DIRECTION_LINKAGE_COUNTS_INCONSISTENT`. Cases
DIR-CLOSED-01..09 and DIR-INCOMPLETE-01..16.

`FULLY_LINKED` is neutral exact traceability. It is never rendered as
ALIGNED, ON_TRACK or HEALTHY. Mass-linking every change to one target yields
`FULLY_LINKED` truthfully, with the diagnostic `ALL_LINKS_TO_SINGLE_TARGET`.
A repository that never had a milestone is `SUPPORTED_UNUSED` and therefore
`UNDECLARED`, not `SCATTERED`: it truthfully states that no explicit target is
declared on the observed surface (confirmed by PV-CAL-002, ROADMAP finding 4).

Groups: `PLANNING_TARGETS`, `CHANGE_REQUEST_ACTIVITY`; dependencies
`HORIZON_DIRECTION_PLANNING`, `DIRECTION_PULSE_ACTIVITY`.

## Debt

*How much explicitly registered maintenance obligation is unresolved?* Debt
exists only through an explicit, versioned mapping (issue labels or a debt
register file). Age, TODO comments, lint output and prose never count.

Inputs: `debt.registry.capability`, `debt.mapping`, `debt.items.open_count`,
`.open_stale_count_30d`, `.closed_count_28d`.

| Band | Rule |
| --- | --- |
| UNINSTRUMENTED | no mapping configured |
| PRESENT | `open > 0` with complete configured coverage |
| CLEAR | `open = 0` with complete configured coverage |

No universal quantitative thresholds exist for Debt: the retired
`ACCUMULATED` band is never emitted. Configured debt evidence that is
forbidden, unknown, errored or stale yields `UNKNOWN`, never `CLEAR`.

**Partial register** (PV-DEBT-PARTIAL-001, rule `debt.bands.v2`). A `PARTIAL`
open count is read only as an observed-subset lower bound, which its coverage
must declare (`value_semantics = OBSERVED_SUBSET_COUNT`, issue #39), and only
under a configured mapping that is itself observed:

- at least one confirmed open item: `DEGRADED` / `PRESENT` / `EXACT`, no
  `possible_bands`, because every completion of the missing items still holds
  that item. `EXACT` names the band, never the count or a severity:
  `derived.open_count_semantics` is `LOWER_BOUND`, and `confirmed_open_count`
  and the partial receipt (`derived.partial_enumeration`) stay visible, with
  `DEBT_PARTIAL_ENUMERATION`, `DEBT_CONFIRMED_OPEN_LOWER_BOUND:<n>` and
  `DEBT_BAND_FORCED_PRESENT_BY_CONFIRMED_OPEN`;
- none confirmed: `UNKNOWN` with no band. The completions reach `CLEAR` and
  `PRESENT`, Debt declares no order between them, and the observed zero is
  absence of proof, not proof of absence; the zero and the receipt stay
  visible.

A partial count without the subset proof is `UNKNOWN`
(`PARTIAL_COUNT_NOT_A_LOWER_BOUND`). Stale and recently closed counts are
diagnostics and never change a result; a project-local quantitative policy
carried in the mapping never replaces the canonical bands. A change of
`mapping_version` makes history `INCOMPARABLE`. Cases DEBT-PARTIAL-01..16.

Groups: `EXPLICIT_DEBT_REGISTER`, `FORGE_INVENTORY`; dependency
`DEBT_CLUTTER_MAINTENANCE`.

## Band ordering (PV-BAND-ORDER-001)

`devostasis.band-order.v1` declares, for three Vitals, which of two bands of
**that Vital** is better. An order is never declared across Vitals, across
projects, or into an aggregate: the Vitals measure different phenomena over
shared signals, so "better Clutter" and "better Flow" are not commensurable.

| Vital | Order |
| --- | --- |
| Clutter | `CLEAN > LIGHT > CLUTTERED > HEAVY`, one transitive chain |
| Flow | `MOVING > CONGESTED > GRIDLOCKED` for a live queue; `NO_QUEUE` incomparable with all of them |
| Integrity | `CLEAN > FLAKY > FAILING` and `SPARSE > SPARSE_MIXED`, two families with no order between them |
| Pulse, Horizon, Direction, Debt | none |

`NO_QUEUE` is descriptive and never positive: a queue that emptied is a
different situation, not a better one. Integrity's `UNINSTRUMENTED`,
`NO_RECENT_RUNS` and `NO_DECISIVE_RUNS` describe what could be observed rather
than what verification said, so they are ordered against nothing, and a small
sample that passed (`SPARSE`) is not comparable with an established one
(`CLEAN`). The four Vitals that declare no order declare none for a reason:
more activity is not better activity, `EXTENDED` is not better than `VISIBLE`,
`FULLY_LINKED` is neutral exact traceability, and `PRESENT` debt is a fact
about a register rather than a verdict.

Where an order applies, a comparison may report `IMPROVED` or `WORSENED`
instead of `CHANGED`; the eligibility rules and reason codes are in
[history-and-reports.md](history-and-reports.md#band-ordering-pv-band-order-001-devostasisband-orderv1).
Gauges never establish an order ([gauges.md](gauges.md)).

## Cross-Vital contract

Known correlations are metadata, not defects: Horizon and Direction share
planning targets; Clutter and Flow share change-request inventory; Clutter
and Debt may share issue inventory; Direction, Flow and Pulse share
change-request activity. Consumers must not count seven bands as seven
independent confirmations, and the per-Vital band ordering above is never a
step towards combining them.

## Policy constants

| Constant | Value |
| --- | --- |
| Activity and planning window | 28 days |
| Integrity revision window | 14 days |
| Stale issue / stale change request / stale branch | 30 / 14 / 30 days |
| Integrity established sample | 4 decisive revisions |
| Integrity failing ratio | 1/4 |
| Pulse surging | 15 active days, or 40 events on 2 channels |
| Pulse steady | 3 active days and 5 events |
| Flow congested | 14 days, 10 open, median over 168 h = 604800 s |
| Flow gridlocked | 3 open for 30 days with 0 merged, or 10 open with median over 336 h = 1209600 s |
| Clutter heavy / cluttered | 25 / 5 stale items, ratio 1/2 / 1/4 with 4 tracked, 20 / 6 stale branches |
