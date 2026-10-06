# History, comparison and reports (PV-REPORT-001, accepted by PV-REV-REPORT-001)

## Comparison states

| State | When |
| --- | --- |
| `BASELINE` | no canonical bundle exists yet for the project |
| `COMPARABLE` | the latest bundle loads, verifies, and shares `vitals_contract_version`, `observation_contract_version`, `policy_version` and the semantic configuration (planning source, debt mapping) |
| `HISTORY_GAP` | history is known to exist but the latest bundle cannot be loaded or verified |
| `INCOMPARABLE` | the latest bundle was produced under different semantics, or the current observation is not later than it (`NON_MONOTONIC_OBSERVATION:<previous>-><current>`, issue #17): an older or simultaneous observation is written and stays immutable, but it claims no direction and no interval |

A current snapshot is always produced when current evidence is sufficient.
`HISTORY_GAP` and `INCOMPARABLE` never emit `UNCHANGED`; missing prior values
are never substituted by current values or zero.

Inside a `COMPARABLE` bundle, one Vital whose `rule_id` differs from the
previous bundle is `INCOMPARABLE` on its own with the reason
`RULE_VERSION_BOUNDARY:<old>-><new>` and no metric deltas: a rule repair
(for example `flow.bands.v0` to `flow.bands.v1`) never reinterprets the
historical band, and the other six Vitals keep comparing. Coverage deltas
are still reported because observability facts remain comparable.

## Delta (`devostasis.delta.v2`)

Per Vital: `previous_band`, `current_band`, evaluation statuses,
`transition_class`, `metric_deltas` (integers and rational records only),
`coverage_delta` (inputs whose status or freshness changed), `reason_codes`.
The document names the ordering it applied in `band_order_contract`
(`PV-BAND-ORDER-001`) and `band_order_version`
(`devostasis.band-order.v1`), so a stored delta always says under which order
its classes were decided.

Transition classes: `BASELINE`, `UNCHANGED`, `CHANGED`, `IMPROVED`,
`WORSENED`, `OBSERVABILITY_GAINED`, `OBSERVABILITY_LOST`, `INCOMPARABLE`.

### Band ordering (PV-BAND-ORDER-001, `devostasis.band-order.v1`)

An order relates two bands of **one** Vital and nothing else: never two
Vitals, never two projects, and never an aggregate. The ordering is in
[vitals.md](vitals.md#band-ordering-pv-band-order-001); this page says when a
comparison may use it.

A changed band becomes `IMPROVED` or `WORSENED` only when all of these hold:

- the bundle comparison is `COMPARABLE`;
- the Vital's `rule_id` is unchanged (a rule version boundary is
  `INCOMPARABLE` and keeps precedence);
- both sides are `AVAILABLE` with `EXACT` band semantics — an order compares
  measurements, and a `DEGRADED` band is a bound, so calling a move between
  bounds an improvement would invent evidence (G2);
- the two bands sit in the same declared family of that Vital.

Anything else stays `CHANGED`, and the row says why with one reason code:
`BAND_ORDER_NOT_DECLARED:<vital>` when the Vital declares no order,
`BAND_ORDER_INCOMPARABLE:<previous>|<current>` when the order does not relate
the pair, and `BAND_ORDER_NOT_ELIGIBLE:EVALUATION_NOT_AVAILABLE` or
`:BAND_SEMANTICS_NOT_EXACT` when the evidence is not exact on both sides.
An ordered row carries `BAND_ORDER_APPLIED:<the family it used>`. Observability
transitions keep precedence: a band that appeared or disappeared is
`OBSERVABILITY_GAINED` or `OBSERVABILITY_LOST`, never a direction. Gauges never
establish an order ([gauges.md](gauges.md)); movement inside a band is
`UNCHANGED`. Conformance `ORDER-01..15`.

## Activity interval

The interval is `(previous.observed_at, current.observed_at]`, never a blind
24 hours: a missed day is covered by the next run. A `BASELINE` bundle reports
the trailing 28-day observation window and says so in `interval.basis`.

The inventories behind the report cover a fixed trailing window of 28 days.
When a run follows an outage longer than that, the interval it declares is
wider than the evidence behind it, and `coverage_notes` says so with
`INTERVAL_EXCEEDS_EVIDENCE_WINDOW:evidence_from=<timestamp>`: the older part of
the interval was not observed rather than quiet. Whether the collection window
should instead widen to the interval is
[an open question for the reporting contract](https://github.com/drevendev/Devostasis/issues/9).

Activity classes: `REVISION` (default-branch commits), `CHANGE_REQUEST`
(opened, merged, closed), `WORK_ITEM` (opened, closed), `VERIFICATION`
(revisions verified, failed, unresolved), `RELEASE`, `CAPABILITY_CHANGE`
(observation statuses that differ from the previous receipt). This is the
GitHub implementation subset of PV-REPORT-001: `DEPLOYMENT` waits for an
adapter contract and branch changes appear as classifier diagnostics rather
than activity events. Lists are ordered by timestamp and identifier and
capped by `activity.list_cap`; truncation is explicit. Titles are reproduced
as source facts and never interpreted.

## History store

Layout of the filesystem store, intended to be a companion Git repository
committed by the scheduler:

```text
projects/README.md                               fleet overview for people (convenience)
projects/index.json                              fleet index for machines (convenience)
projects/<forge>/<owner>/<repo>/latest/          copy of the newest bundle
projects/<forge>/<owner>/<repo>/history/YYYY/MM/DD/<bundle_id>/
projects/<forge>/<owner>/<repo>/index.json       chronological index with bands
```

Rules: history directories are append-only and never overwritten (an
identical re-put is idempotent, a different one is an `ImmutabilityError`);
`latest` is a convenience pointer, never authoritative; storage activity is
never observed as project activity because the store is not a target; a store
must not be more permissive than its sources.

The previous bundle of a comparison is the immutable bundle the project index
names (its tail), verified from its own contents; without an index the newest
immutable bundle is found by scanning `history/` (issue #28), and every bundle
directory there is a candidate: one whose manifest is missing, unreadable or
names another bundle makes the order unprovable, so the state is unverified
and the next comparison a `HISTORY_GAP` (`INDEXLESS_CANDIDATE_UNREADABLE`),
never a comparison against an older readable bundle and never a `BASELINE`;
only an interrupted write (`*.staging`) is not a candidate. The tail is
followed only along the canonical `history/YYYY/MM/DD/<bundle_id>` path,
resolved inside this project's `history/` tree, with a basename equal to the
id it claims; the bundle found there must carry the identity the index
records (its locator, for a store without identities). A tail that points
anywhere else, or at another project's bundle, is `INDEX_TAIL_INVALID` or
`PROJECT_IDENTITY_MISMATCH`: an unverified state and a `HISTORY_GAP`, never a
comparison against what it points at. A malformed index is a store failure
and is never appended to.

`latest/` is republished on every commit and may be compacted or damaged
without turning the next run into a `HISTORY_GAP`. The index is written
first, through a temporary file replaced in one step, and the copy last, with
the previous copy kept until the new one is in place; an interruption between
the two therefore leaves a stale copy of an indexed bundle, which the next
commit replaces, not a gap. A `latest/` that names a bundle the index does
not know, or one observed after the tail, is a store inconsistency and is
still refused (`latest pointer ... differs from index tail`). `HISTORY_GAP`
therefore means what its definition says: the previous immutable bundle
cannot be loaded or verified.

The same predecessor is the source of the durable Integrity revision
history a build carries (PV-HIST-002): the bundle the comparison resolves,
never an older one, so a `HISTORY_GAP` is also a gap in that history and says
so (`REVISION_HISTORY_GAP`); see
[integrity-ci.md](integrity-ci.md#durable-history-pv-hist-002).

A bundle is routed by what its canonical members say: a wrapper whose
`bundle_id` or `project_key` disagrees with its own manifest is refused
before anything is written. A locator derives a store path only as a
`<forge>/<owner>/<repo>` triple of letters, digits, dots, hyphens and
underscores, strictly beneath `projects/`. While proving that an immutable id
lives nowhere else in the store, and while generating the fleet surfaces, an
unreadable or malformed project index, a tail that cannot be followed, or a
demand member that is present but unreadable is an explicit store failure,
not an absent project: the fleet surfaces are then not rewritten, and the
`run` and `index` commands report a store error, after every project's own
result (the bundles are committed; only the surfaces are missing). The two
fleet surfaces are written beside themselves and moved into place, never
truncated first. A project index is exactly
`projects/<forge>/<owner>/<repo>/index.json`, so a repository named
`index.json` is a project like any other. Problem texts name store paths
relative to the store root and exceptions by their type, because they reach
the delta of a `HISTORY_GAP` bundle: the same evidence and the same damage
are one bundle id wherever the store is checked out. A bundle that predates
the demand interface has no demand member and keeps its null levels.

### Identity and rename continuity (RPT-7)

A project **is** its `project_identity.immutable_project_id`; the directory
keeps the human-readable locator because a store is browsed by people. The
store therefore locates a project by identity first and by locator second:

1. if the locator's directory already carries this identity, use it;
2. if it carries a *different* identity, refuse to write and report it, rather
   than merging two projects into one history;
3. otherwise, if the identity is found under another locator, the repository
   was renamed or transferred: relocate that directory once to the new
   locator and record the move;
4. otherwise this is a new project.

The relocation moves the directory; it never copies, so history stays one
chain and the old path does not survive as an orphan. Each bundle keeps the
`project_key` it was observed under, because that is what the project was
called at that moment, and the per-project index records the move:

```json
"renames": [
  {"from": "github.com/acme/widget", "to": "github.com/acme/gadget",
   "observed_at": "2026-09-06T12:00:00Z", "bundle_id": "..."}
]
```

Two consequences are deliberate. A repository whose old name is immediately
reused by a *new* repository yields two separate histories, because the ids
differ. An adapter that cannot prove an immutable id falls back to locator
keying, so a rename starts a new `BASELINE`: without proof that two names are
the same project, losing continuity is more honest than guessing.

Decisions taken by PV-REV-REPORT-001 on the questions the contract left open:

- **Store naming** is deployment configuration, not contract.
- **One store per permission domain.** Several projects may share a store
  only when the deployment can establish one equivalent access boundary for
  all of them; otherwise they get separate stores. A store is never more
  readable than the most private repository it observes.
- **`report.html`** is an optional canonical member controlled by the
  identity-bearing effective config, not a mandatory one.
- **Daily wall-clock time** is a deployment choice; the core is
  schedule-agnostic and the comparison interval prevents missed-day
  truncation.
- **Retention.** Immutable canonical bundles required for audit and replay
  are never destroyed; convenience, index and derived views may be compacted.
  A different durability promise needs a versioned retention contract.
- **Self-observation durability.** The self-observation workflow writes its
  bundle to an ephemeral workspace and uploads it as a CI artifact; without a
  configured `HistoryStore` this is a convenience shape whose comparison is
  `BASELINE` and whose artifact expires. It is not canonical durable history,
  and a deployment claiming durable history must persist through a store
  outside CI artifact retention ([deployment.md](../deployment.md)).

## Fleet index (devostasis.fleet.v1)

`projects/README.md` is written for a human and cannot be parsed without
guessing. `projects/index.json` carries the same facts as data, so a control
plane routing attention across many projects does not read Markdown.

One entry per project, ordered by `project_key` so the file is byte-stable
between runs of an unchanged store: the project key and locator, the immutable
project id, `observed_at`, `bundle_id`, `previous_bundle_id`,
`comparison_status`, the project's own `attention` and `attention_order`, one
row per Vital with `band`, `evaluation_status`, `gauge` and `level`, and
relative paths to the report and to the immutable bundle the entry came from.

Three rules make it safe to consume:

- **It adds no meaning.** Every value comes from the latest bundle of that
  project. A consumer that needs provenance, coverage or the reasoning behind
  a band reads the bundle the entry points at, which stays authoritative.
- **There is no aggregate**, per project or across projects, and `aggregate`
  is explicitly `null`. The seven Vitals share signals and are not
  independent votes.
- **There is no cross-project ordering**, and `cross_project_order` is
  explicitly `null`. Demand levels order Vitals inside one project; no
  accepted contract defines what it means for one project's `CRITICAL` to
  outrank another's. A consumer that wants a fleet-wide order applies its own
  policy and owns that decision.

A bundle written before the demand interface existed has no `demand.json`, so
its `level` and `evaluation_status` are `null` rather than invented, and its
`attention_order` is empty. The index carries no generation timestamp: a run
that changes nothing rewrites the same bytes, so the store stays quiet in
version control. Schema: `schemas/fleet-index.schema.json`.

## Report rendering (devostasis.render.v4)

`report.md` is generated only from the machine bundle and the persisted
`display` configuration, in this order: identity and comparison header; a
monospace status card with gauge, value and band per Vital; the "Attention"
section of the demand interface (levels, then canonical Vital order; gauges
shown, never compared); the shown Vitals with gauge, band, evaluation,
semantics and explanation; per-Vital metrics and diagnostics; observability
(non-available observations, capability notes); changes since the previous
bundle; activity; provenance. Exact rational durations render as a decimal
with the fraction beside it; the explanation states them in whole hours,
minutes and seconds.

Renderer rules: gauges are labelled as the versioned normalization and never
enter `snapshot.json` ([gauges.md](gauges.md)); no colours or icons that
imply an ordering the contract does not declare; no evaluative aliases for
neutral bands; `UNKNOWN` and `DEGRADED` are always visible; no language model
anywhere. `devostasis render` regenerates the report from a bundle and
`verify` checks that the stored report is byte-identical to what the current
renderer produces from the immutable members and the validated stored
config, when the bundle was written by the current renderer. The renderers
of earlier releases are not carried, so the report of a bundle they wrote
is bound by its digest but not replayed, and `verify` says so instead of
claiming reproducibility (see [bundle.md](bundle.md), step 6).

## Conformance cases implemented

RPT-1 (ART-01) baseline without fake delta; RPT-2 interval from the previous
successful bundle; RPT-3 (ART-03) history gap, over the immutable bundle;
RPT-7 rename and transfer continuity keyed by immutable project id, including
the fail-closed cases; RPT-8 storage isolation by construction; RPT-10
(ART-04) semantic incompatibility; per-Vital rule version boundary; the
non-monotonic observation boundary; the immutable authority of the comparison;
ACT-COV-01..05 as `activity` vectors. RPT-4..RPT-6 and RPT-9, including an
executable permission-domain fixture, remain open implementation work named by
PV-REV-REPORT-001.
