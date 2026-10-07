# Executable conformance vectors (`devostasis.vectors.v1`)

A conformance case written in prose can only be checked by a person reading
both the sentence and the code. Written as a vector it is a JSON document that
states evidence and expected result, and the runner executes it. This page is
the format; `src/devostasis/vectors.py` is the runner, `devostasis vectors` the
command, and `schemas/conformance-vector.schema.json` the published schema.

The format existed before the vectors it carries: the specification named 70
cases with no test behind them (debt D-1, target B1). Since 0.1.9 the accepted
exact vectors of the research process are in the corpus (seven of those 70,
with sixty-three still to come), beside the accepted families transcribed
from their contracts (`ORDER`, `INT-UNKNOWN`, `INT-TOTAL`, `CLU-INCOMPLETE`,
`ACT-COV`, and since 0.2.0 `DIR-CLOSED`, `DIR-INCOMPLETE`, `HOR-PARTIAL`,
`DEBT-PARTIAL`, `HIST`). Authored against this format a case arrives executable instead of
needing translation.

## A vector file

```json
{
  "schema": "devostasis.vectors.v1",
  "notes": "what this file covers",
  "vectors": [ { "case": "ORDER-01", "title": "...", "kind": "delta",
                 "source_unit": "PV-BAND-ORDER-001",
                 "given": { }, "expect": { } } ]
}
```

`case` is the conformance case identifier, unique across the whole corpus and
never reused; `title` states the claim in one sentence; `source_unit` names the
research unit the case comes from. A file may hold any number of vectors, and
the corpus is every file under the directories the runner is given.

## Kinds

### `kind: "vital"`

Evaluates one Vital over an observation set built from raw observation
envelopes, so a vector states evidence exactly as a collector emits it
([observations.md](observations.md)). Envelope defaults: `status` is
`AVAILABLE`, `value_type` is `count`, freshness is `FRESH`. The envelope is
built through the ordinary observation contract, so evidence that violates it
(an `AVAILABLE` without a value, an unknown status) fails the vector. The
published schema declares this partial envelope as `$defs/envelope`: only
`observation_id` is required, and every key it allows is a key of the full
`RAW-OBS-V0` envelope, so a vector the runner accepts is never one the schema
beside it calls invalid.

```json
{"case": "EXAMPLE-VITAL-01", "kind": "vital",
 "title": "a fully observed inventory with one stale item is exactly LIGHT",
 "given": {"vital": "clutter", "observed_at": "2026-01-01T00:00:00Z",
           "observations": [
             {"observation_id": "forge.issues.open_count", "value": 4},
             {"observation_id": "forge.issues.stale_open_count_30d", "value": 1},
             {"observation_id": "forge.change_requests.open_count", "value": 2},
             {"observation_id": "forge.change_requests.stale_open_count_14d", "value": 0},
             {"observation_id": "git.nondefault_branches.stale_count_30d", "value": 0}]},
 "expect": {"band": "LIGHT", "evaluation_status": "AVAILABLE",
            "band_semantics": "EXACT", "possible_bands": null,
            "rule_id": "clutter.bands.v1",
            "derived": {"tracked_open_count": 6, "stale_work_count": 1},
            "diagnostics_absent": ["COMPONENT_UNAVAILABLE"],
            "explanation_contains": ["1 stale work items out of 6 tracked open items"]}}
```

`band` and `evaluation_status` are required; `band_semantics`,
`possible_bands`, `rule_id`, `shared_signal_groups` and
`dependency_group_ids` are compared when present. `derived` is a
subset: every key it names must exist and be equal, and `derived_absent` names
keys that must not exist. `diagnostics` and `diagnostics_absent` match a
diagnostic that equals the given string or starts with it, so a case can
require `COMPONENT_UNAVAILABLE:issues:ISSUES_DISABLED` or just its prefix.
`explanation_contains` holds substrings of the deterministic explanation.

A case that states one obligation over several evidence shapes, such as a
substitution matrix over `FORBIDDEN`, `UNKNOWN`, `ERROR`, `PARTIAL` and
`STALE`, puts them under `given.variants` instead of `given.observations`: a
list of at least two `{title, observations}` entries, all held to the one
`expect` of the case. The case passes only when every shape does, and a
failure names the shape by its `title`. `variants` replaces `observations`;
stating both is an error.

A case about how inventories become aggregates states the inventories and
`given.derive`: the provider-neutral derivation (`normalize.derive`) runs
over the envelopes before the Vital is evaluated, under the two project
settings it reads, `planning_source` (`none`, `milestones` or `file`) and
`debt_mapping` (the explicit mapping object, or `null`). Aggregates the
envelopes already state are kept, as the derivation keeps them for a saved
observation set. The Direction, Horizon and Debt families of 0.2.0 use it,
so a change request linked to a closed target or a partial target list is
executed where the linkage and the counts are made, not over counts
somebody derived by hand.

```json
{"case": "EXAMPLE-DERIVE-01", "kind": "vital",
 "title": "a returned open target beyond the frame forces EXTENDED over a partial enumeration",
 "given": {"vital": "horizon", "observed_at": "2026-09-07T12:00:00Z",
           "derive": {"planning_source": "milestones", "debt_mapping": null},
           "observations": [
             {"observation_id": "planning.explicit_targets.inventory", "value_type": "series",
              "status": "PARTIAL", "reason_code": "PAGINATION_CAPPED",
              "coverage": {"complete": false, "source": "milestones"},
              "value": [{"target_id": "1", "state": "OPEN", "due_at": "2026-12-01T00:00:00Z"}]}]},
 "expect": {"band": "EXTENDED", "evaluation_status": "DEGRADED", "band_semantics": "EXACT",
            "possible_bands": ["EXTENDED"], "diagnostics": ["HORIZON_PARTIAL_BAND_INVARIANT"]}}
```

A case whose evidence must be refused states `{"rejected": "<code>"}` as its
whole `expect`: the evaluation must raise `InadmissibleEvidence` with that
code (or one it is a prefix of). The totality contracts of 0.2.0 give
contradictory normalized input that outcome, before classification and
never as an `UNKNOWN` or `DEGRADED` result (HOR-PARTIAL-15; Direction's
`L + U + R != N`). A refusal combined with any other expectation, or naming
no code, is an error; a case that expects a refusal and gets a result fails
and says which result it got.

### `kind: "delta"`

Compares two snapshots given as partial Vital rows and checks transition
classes and reason codes. Only the fields the case is about are written; a row
defaults to `AVAILABLE`/`EXACT` when it names a band, to `UNKNOWN` when the
band is `null`, and to the same `rule_id` on both sides so that no rule version
boundary is invented. A case that names `rule_id` on one side only is
therefore a case about a rule version boundary; a case that is not about one
either omits it everywhere or states it on both sides. `comparison_status`
defaults to `COMPARABLE` and must be one of `BASELINE`, `COMPARABLE`,
`HISTORY_GAP` and `INCOMPARABLE`; an unrecognised one is rejected rather than
run as a comparison the case did not mean.

```json
{"case": "EXAMPLE-DELTA-01", "kind": "delta",
 "title": "a Vital with a declared order and exact evidence reports a direction",
 "given": {"comparison_status": "COMPARABLE",
           "previous": {"vitals": [{"vital_id": "clutter", "band": "CLUTTERED"}]},
           "current": {"vitals": [{"vital_id": "clutter", "band": "LIGHT"}]}},
 "expect": {"vitals": {"clutter": {
     "transition_class": "IMPROVED",
     "reason_codes": ["BAND_ORDER_APPLIED:CLEAN>LIGHT>CLUTTERED>HEAVY"],
     "reason_codes_absent": [], "metric_deltas": {}}}}}
```

`expect.vitals` is keyed by Vital; each entry requires `transition_class` and
may add `reason_codes` (prefix matching, as for diagnostics),
`reason_codes_absent`, and exact `metric_deltas` and `coverage_delta`. Vitals
the case does not name are not checked.

An accepted case often names more than one pair — *"`GRIDLOCKED → CONGESTED →
MOVING` follows the WORSENED/IMPROVED direction"* is six comparisons, and
*"every unequal Pulse band pair is CHANGED"* is twelve. Splitting such a case
across several vectors would split its identifier, so `given` may carry
`comparisons` instead of one `previous`/`current`: a list of pairs, each with
its own optional `title` and its own `expect`. The case then reports one
result, and it passes only when every pair passes.

```json
{"case": "EXAMPLE-DELTA-02", "kind": "delta",
 "title": "a case that names several pairs states them all",
 "given": {"comparisons": [
   {"title": "one rank better",
    "previous": {"vitals": [{"vital_id": "flow", "band": "CONGESTED"}]},
    "current": {"vitals": [{"vital_id": "flow", "band": "MOVING"}]},
    "expect": {"vitals": {"flow": {"transition_class": "IMPROVED"}}}},
   {"title": "and one rank worse",
    "previous": {"vitals": [{"vital_id": "flow", "band": "CONGESTED"}]},
    "current": {"vitals": [{"vital_id": "flow", "band": "GRIDLOCKED"}]},
    "expect": {"vitals": {"flow": {"transition_class": "WORSENED"}}}}]}}
```

A comparison takes the same keys as an inline `given` — `comparison_status`,
`previous_bundle_id`, `incomparable_reasons` — so one case can state pairs that
differ in more than their bands. `comparisons` replaces `previous`/`current`
rather than extending them, needs at least two entries, and leaves the vector
with no `expect` of its own; each of those is an error rather than a quietly
different run. A failure names the pair by its `title`, so a case with twelve
comparisons still says which one broke.

### `kind: "ci"`

Starts one stage earlier than `vital`, at the provider-native verification
normalization ([integrity-ci.md](integrity-ci.md)): the outcome map, parent
identity and attempt precedence, and one canonical record per immutable
revision. A case about that contract (`R5`..`R10`, `INT-UNKNOWN-02`,
`INT-UNKNOWN-03`) states workflow runs, their earlier attempts and check suites
exactly as the provider reports them, and is executed at the boundary it is
about instead of over verdicts somebody pre-normalized.

```json
{"case": "EXAMPLE-CI-01", "kind": "ci",
 "title": "a retry that passed keeps the failure of its first attempt",
 "given": {"observed_at": "2026-09-05T12:00:00Z",
           "revisions": [{"sha": "a1", "committed_at": "2026-09-01T10:00:00Z"}],
           "actions_runs": [{"id": 100, "head_sha": "a1", "run_attempt": 2,
                             "status": "completed", "conclusion": "success",
                             "prior_attempts": [{"run_attempt": 1, "status": "completed", "conclusion": "timed_out"}]}]},
 "expect": {"revisions": {"a1": {"current_verdict": "VERIFY_PASS", "history_state": "FAILURE_OBSERVED",
                                 "historical_contribution": "VERIFY_FAIL",
                                 "parents": [{"current_state": "VERIFY_PASS"}]}},
            "integrity": {"band": "SPARSE_MIXED", "evaluation_status": "AVAILABLE",
                          "derived": {"sample_strength": "SPARSE"}, "diagnostics": ["CI_SPARSE_SAMPLE"]}}}
```

`given` names the `revisions` of the window (`sha`, `committed_at`), the
`actions_runs` as the provider lists them (`id`, `head_sha`, `run_attempt`,
`status`, `conclusion`, with earlier attempts under `prior_attempts`) and the
`check_suites` keyed by the sha they verify. `provider` is `github` and is
the only provider with a normalization in this version; another one is an
error, never a skip. `configured` (default `true`, `null` for not observed)
and `series_status` (default `AVAILABLE`) are the acquisition facts handed to
Integrity.

`expect.revisions` is keyed by sha and checks the canonical record fields it
names; `parents` are checked by position, each parent as a subset.
`expect.integrity` is the `vital` expectation shape, evaluated over the
normalized records. A case names at least one of the two.

`given.variants` carries several provider-native evidence shapes, each a
full `given` without `variants` and with an optional `title`, so one accepted
case can hold provider aliases and enumeration orders to one expectation
(`EXAMPLE-CI-02`).

### `kind: "activity"`

Builds the activity member ([history-and-reports.md](history-and-reports.md#activity-interval))
over raw inventories and the `observed_at` of the previous bundle, and checks
the interval it declares and the coverage it discloses (`ACT-COV-01`..`05`).

```json
{"case": "EXAMPLE-ACTIVITY-01", "kind": "activity",
 "title": "an interval wider than the evidence window keeps its bounds and discloses where the evidence starts",
 "given": {"observed_at": "2026-09-06T12:00:00Z", "previous_observed_at": "2026-06-01T00:00:00Z",
           "observations": [{"observation_id": "git.default_branch.commits_28d", "value_type": "series",
                             "value": [{"sha": "a1", "committed_at": "2026-09-06T08:00:00Z", "title": "one change"}],
                             "coverage": {"complete": true}}]},
 "expect": {"interval": {"start": "2026-06-01T00:00:00Z", "end": "2026-09-06T12:00:00Z", "basis": "PREVIOUS_BUNDLE"},
            "coverage_notes": ["INTERVAL_EXCEEDS_EVIDENCE_WINDOW:evidence_from=2026-08-09T12:00:00Z"],
            "classes": {"REVISION": {"count": 1}}}}
```

`previous_observed_at` absent or `null` is a `BASELINE` interval;
`list_cap` defaults to 50. `expect.interval` is a subset of the interval
fields, `coverage_notes` and `coverage_notes_absent` match by prefix like
diagnostics, `classes` holds the counts to assert per activity class as a
checked subset, and `truncated` the truncation flags.

## Rules the runner enforces

- **It fails closed.** An unknown `kind`, an unknown key in a vector, an
  unknown comparison status, a provider without a normalization, a malformed
  observation envelope, a missing path or a duplicate case id is an error. A
  vector that cannot run must never look like a vector that passed, and a
  case family this version cannot execute makes the suite red rather than
  silently skipped.
- **A vector states, it does not compute.** Expectations are literal values.
  Deriving an expectation from the implementation would prove only that the
  implementation equals itself.
- **Every stated expectation is checked**, and an unknown expectation key is
  rejected rather than ignored, so a typo cannot weaken a case.
- **Order is irrelevant.** Vectors run independently, in case-id order, and
  share no state.

## Running them

```bash
devostasis vectors                          # tests/vectors and examples/vectors
devostasis vectors --path path/to/vectors   # repeatable
devostasis vectors --case ORDER-07 --quiet
```

The same corpus runs inside the ordinary test suite
(`tests/conformance/test_vectors.py`), one pytest case per vector, so a
conformance case fails where every other test fails, and every kind the format
declares must be exercised by the corpus. Exit status is 1 when a vector fails
and 2 when the corpus itself cannot be loaded.

## Where the vectors live

| Directory | What it holds |
| --- | --- |
| `tests/vectors/` | the conformance corpus; every case id there is cited in [conformance.md](conformance.md) |
| `examples/vectors/` | the documented examples of this page, executed with the corpus so the format cannot drift |

`tests/test_vector_runner.py` proves the runner itself: a wrong expectation
fails, an invalid document is rejected, and the published schema agrees with
the validator.
