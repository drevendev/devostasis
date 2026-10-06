# Devostasis

**Deterministic, model-free vital signs for software repositories.**

Devostasis reads a repository through its forge API and reports seven named
states, the *Vitals*: **Pulse**, **Flow**, **Integrity**, **Clutter**,
**Horizon**, **Direction** and **Debt**. Every run produces an immutable,
verifiable bundle with the current state, a deterministic comparison against
the previous run and a plain-language report. No language model is involved at
any point, there is no health score, and evidence that could not be collected
never makes a project look healthier.

The name is *development* plus *homeostasis*: the goal is a stable, honest
reading of where a project actually stands, so that people and autonomous
development systems can react to it.

The latest published tag is **v0.1.9**. This checkout prepares **0.4.0**,
including the pending 0.2.0/0.3.0 increments; these are not released yet.
Use the checkout installation below to try the new companion before its tag
is published. See [ROADMAP.md](ROADMAP.md) for release gates and next steps.

The **0.3.0 Evidence to Action** companion adds five bounded work queues:
`review`, `finish_merge`, `implement_issue`, `research`, `analyze_code`.
It binds tasks to exact revisions, explicit consumer priorities, dependencies,
read budgets and acceptance; verifies immutable scope bundles offline; and
rechecks selected source state before execution. Optional SARIF, JUnit,
Cobertura and performance reports provide scoped analysis triggers. Collectors
read GitHub and GitLab; unknown capabilities remain explicit. See the
[adopter walkthrough](docs/work-scopes.md),
[consumer contract](docs/spec/work-scope.md) and
[frozen example](examples/work/bundle/report.md).

**0.4.0 Reproducible consumer handoff** adds byte-invariant canonical bundles,
exact contract compatibility, mutable source bindings and verified source
packets that enforce the task's file/byte budget. Existing glab authentication
works for self-hosted GitLab without a new token. Historical bundles still
verify. Start with the [external adoption guide](docs/external-adoption.md).

```sh
devostasis work policy --actor YOUR_LOGIN --output policy.json
devostasis work run --repo OWNER/REPO --policy policy.json --store /private/work-history
devostasis work verify --bundle examples/work/bundle
devostasis work slice --bundle examples/work/bundle --at 2026-10-02T12:00:00Z --limit 2
```

Configure the consumer policy's required checks and criteria before use.
Queues propose work; they grant no merge/deploy permission and execute no
repository instructions. Seven Vitals keep their own contracts and ordering.

## Why this exists

Repository dashboards usually fail in one of four ways:

1. **They collapse everything into one number.** A green badge hides a red
   workflow; a "health 82" hides which of five different questions is bad.
2. **They treat missing data as zero.** A denied API call becomes "no branch
   protection"; a disabled issue tracker becomes "no backlog"; a rate-limited
   query becomes "no activity".
3. **They can be gamed by noise.** Retrying CI until it passes erases a real
   failure; closing valid issues improves a backlog metric; mass-linking every
   change to one milestone looks like focus.
4. **They summarise with a model** whose output changes from run to run and
   cannot be audited afterwards.

Devostasis is built against those failures:

- **Seven orthogonal questions, seven named bands.** No arithmetic ever
  combines them into an authoritative scalar. Correlations between Vitals are
  declared as metadata instead of hidden.
- **Unknown is not zero.** Every observation carries an explicit status
  (`AVAILABLE`, `PARTIAL`, `UNAVAILABLE`, `FORBIDDEN`, `UNKNOWN`, `ERROR`) and
  a freshness. A Vital without sufficient evidence says `UNKNOWN`, or emits a
  conservative `DEGRADED` bound with the set of bands still possible.
- **Same evidence, same output.** Evaluation is a pure function of the
  recorded observations and a declared policy version. Two implementations
  computing the same bundle get the same identity.
- **History is immutable and self-contained.** A bundle can be verified and
  re-rendered years later from its own files, without the original
  configuration or provider access.
- **Anti-gaming rules are part of the contract.** A revision that failed
  verification keeps its failure in the history window even if a retry later
  passes, and even after the provider stops showing the failed attempt: the
  history is carried from one bundle to the next. Closing the target a change
  delivered does not un-link the change. A zero queue is not "good flow".
  Full milestone linkage is a fact, not a compliment.

## The seven Vitals

| Vital | Question it answers | Bands |
| --- | --- | --- |
| Pulse | How intense is recent observable activity? | DORMANT, QUIET, STEADY, SURGING |
| Flow | What is the state and friction of the change-request queue? | NO_QUEUE, MOVING, CONGESTED, GRIDLOCKED |
| Integrity | What does automated verification say about recent revisions? | UNINSTRUMENTED, NO_RECENT_RUNS, NO_DECISIVE_RUNS, SPARSE, SPARSE_MIXED, FLAKY, CLEAN, FAILING |
| Clutter | How much unresolved stale residue is observable? | CLEAN, LIGHT, CLUTTERED, HEAVY |
| Horizon | Is future work explicitly declared, and how far ahead? | UNDECLARED, DECLARED, VISIBLE, EXTENDED |
| Direction | Is active change work explicitly traceable to declared targets? | NO_ACTIVE_CHANGE, UNDECLARED, SCATTERED, MIXED, FULLY_LINKED |
| Debt | How much explicitly registered maintenance obligation is unresolved? | UNINSTRUMENTED, CLEAR, PRESENT |

Bands describe state, not virtue. A mature project may be temporarily
`CONGESTED`; a young project may be `CLEAN` and `UNINSTRUMENTED` at the same
time. The exact rules, windows and thresholds are in
[docs/spec/vitals.md](docs/spec/vitals.md).

Every report opens with a status card that places each band on a 0-100
gauge of the phenomenon it describes, so gradation inside a band is visible:

```text
Horizon    ████████░░    84  EXTENDED
Clutter    █░░░░░░░░░    10  LIGHT
Direction  █████░░░░░    50  MIXED
Flow       █░░░░░░░░░    10  MOVING
Integrity  ██████░░░░    62  FLAKY
Debt       █░░░░░░░░░    11  PRESENT
Pulse      ████████░░    82  SURGING
```

Gauges are a versioned normalization ([docs/spec/gauges.md](docs/spec/gauges.md))
persisted as `gauges.json`; the band stays the semantic truth, the gauge is
the position inside it, and nothing is ever summed into a health score.

## Where to focus

Every bundle also carries `demand.json`
([docs/spec/demand.md](docs/spec/demand.md)): one level per Vital from
CRITICAL, HIGH, MEDIUM, LOW, MINIMAL or UNRESOLVED, taken from a versioned
band-to-level table you can override, plus an attention order that ranks the
Vitals by level and then by their canonical order (gauges are shown but never
compared across Vitals, because they measure different phenomena). Autonomous
development systems consume it to decide what to work on; the report shows it
as the "Attention" section.
UNRESOLVED means evidence was missing and must never be read as "nothing to
do".

Horizon, Direction and Debt read explicit planning metadata only: GitHub
milestones with due dates and milestones set on pull requests, or two small
register files committed to the repository, `targets.json` and `debt.json`
([docs/spec/registers.md](docs/spec/registers.md)), with pull requests linked
to targets by a `Target: <id>` line. A repository without any of those
declares nothing and gets `UNDECLARED` or `UNINSTRUMENTED`, which is a fact
about its metadata, not about its code.

Devostasis uses the register files on itself: see
[`.devostasis/targets.json`](.devostasis/targets.json) and
[`.devostasis/debt.json`](.devostasis/debt.json), which are the worked example
to copy.

The `display` configuration chooses which Vitals appear, whether the card
shows bars, numbers or band names, and which report sections are rendered
([docs/configuration.md](docs/configuration.md)).

## What a run produces

One successful run of one project writes one immutable bundle:

| Member | Content |
| --- | --- |
| `snapshot.json` | The authoritative machine state: seven Vitals with band, evaluation status, inputs, derived metrics, diagnostics. |
| `gauges.json` | The 0-100 position of every band on the scale of its phenomenon, under a versioned normalization contract. |
| `demand.json` | One demand level per Vital and the attention order, for consumers that decide where to work. |
| `delta.json` | Deterministic comparison with the previous bundle: `BASELINE`, `COMPARABLE`, `HISTORY_GAP` or `INCOMPARABLE`, plus per-Vital transitions, including `IMPROVED` and `WORSENED` where the Vital declares a band ordering. |
| `activity.json` | Normalized activity since the previous successful bundle: revisions, change requests, work items, verification, releases, capability changes. |
| `observations.json` | Every raw observation with its status, coverage and evidence references, so the snapshot can be recomputed. |
| `effective-config.json` | The exact configuration that shaped the bundle, in canonical form. |
| `report.md` | A neutral, deterministic report rendered only from the files above. |
| `manifest.json` | Versions, project identity, receipts, member digests and the identity preimage from which `bundle_id` is recomputed. |

Bundles live in an append-only history store, normally a private companion
Git repository, next to a convenience `latest/` copy and a fleet overview:

```text
projects/
  README.md                          fleet overview for people
  index.json                         the same fleet as data, for machines
  github.com/<owner>/<repo>/
    latest/                          convenience copy, never authoritative
    history/YYYY/MM/DD/<bundle_id>/  immutable bundles
    index.json
```

`projects/index.json` ([docs/spec/history-and-reports.md](docs/spec/history-and-reports.md))
gives a control plane the bands, gauges and demand levels of every project
without parsing Markdown. It adds no meaning to the bundles it points at, and
it carries neither an aggregate nor a cross-project ordering: which project
comes first is the consumer's policy, and no accepted contract defines it.

## Quick start

Requires Python 3.12 or newer. The runtime uses the standard library only.

For this unreleased checkout:

```bash
pip install -e .
```

After the 0.4.0 release tag is published:

```bash
pip install git+https://github.com/drevendev/devostasis@v0.4.0
```

Observe one repository (a GitHub token is read from `DEVOSTASIS_GITHUB_TOKEN`,
`GITHUB_TOKEN`, `GH_TOKEN` or `gh auth token`; public repositories work
without one, with a low rate limit):

```bash
devostasis observe --repo owner/name --out observations.json
devostasis evaluate --observations observations.json --out snapshot.json
```

Run a fleet from a configuration file and persist bundles into a store:

```bash
devostasis run --config devostasis.json --store ./history
```

Verify any bundle from its own contents, or re-render its report:

```bash
devostasis verify --bundle history/projects/github.com/owner/name/latest
devostasis render --bundle history/projects/github.com/owner/name/latest
```

Execute the conformance vectors of a checkout
([docs/spec/vectors.md](docs/spec/vectors.md)):

```bash
devostasis vectors --path tests/vectors
```

A minimal configuration:

```json
{
  "schema": "devostasis.config.v1",
  "config_version": "2026-09-05.1",
  "store": { "path": "." },
  "projects": [
    { "repo": "owner/name" },
    { "repo": "owner/other", "debt": { "labels": ["type:refactor"], "mapping_version": "1" } }
  ]
}
```

A project can also observe itself from its own GitHub Actions, with no
secret at all, and branch its next steps on the demand levels:

```yaml
permissions:
  contents: read
  issues: read
  pull-requests: read
  actions: read
  checks: read

jobs:
  vitals:
    uses: drevendev/devostasis/.github/workflows/observe-self.yml@v0.4.0
  decide:
    needs: vitals
    runs-on: ubuntu-latest
    steps:
      - run: echo "work on ${{ needs.vitals.outputs.attention }}"
```

See [docs/configuration.md](docs/configuration.md) for every option and
[docs/deployment.md](docs/deployment.md) for both deployment shapes: the
fleet observer with a companion history repository, and self-observation.

## Example

The fleet overview written to `projects/README.md`:

| Project | Observed at | Comparison | Attention | Pulse | Flow | Integrity | Clutter | Horizon | Direction | Debt | Report |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| acme/widget | 2026-09-05T12:00:00Z | BASELINE | integrity HIGH | SURGING 82 | MOVING 10 | FLAKY 62 | LIGHT 10 | EXTENDED 84 | MIXED 50 | PRESENT 11 | [report](github.com/acme/widget/latest/report.md) |

A complete synthetic bundle is checked in under
[examples/sample-bundle](examples/sample-bundle); its
[report.md](examples/sample-bundle/report.md) shows what a human reads.

## Semantics worth knowing before you trust a band

- `evaluation_status` is as important as the band. `AVAILABLE` means the
  band is exact. `DEGRADED` means a conservative bound: the `possible_bands`
  list says what could still be true. `UNKNOWN` means no band at all.
- Integrity works on immutable revisions, not on runs. One revision
  contributes at most one verdict to the 14-day sample; once a revision was
  observed to fail, that failure stays in its history for the rest of the
  window even if a retry of the same revision passes. A newest revision whose
  verification outcome is unknown makes the whole Vital `UNKNOWN` rather than
  inheriting an older pass, and one to three decisive revisions are a sparse
  sample that says so.
- `NO_QUEUE` for Flow, `UNDECLARED` for Horizon and Direction, and
  `UNINSTRUMENTED` for Integrity and Debt are descriptive states, never
  healthy defaults.
- Direction `FULLY_LINKED` and Debt `PRESENT` are neutral facts. The renderer
  never relabels them as aligned, on track, healthy or unhealthy.
- A changed band is `IMPROVED` or `WORSENED` only where that Vital declares
  an ordering: Clutter's chain, Flow's live queue, and Integrity's two verdict
  families. Everything else is `CHANGED`, and the row says why. An order is
  never declared across Vitals or across projects, and never becomes a score.
- Comparisons are only ever `COMPARABLE` when both bundles share the same
  contract versions and the same semantic configuration. A missing or corrupt
  previous bundle yields `HISTORY_GAP`, never "unchanged".
- Thresholds are provisional calibration constants under an explicit policy
  version. They are not tuned to make any single repository look right.

## Status

The published 0.1.9 engine supplies seven Vitals, GitHub observation,
immutable bundles, filesystem history, fleet data, Markdown reports, demand,
gauges, accepted band ordering and executable conformance vectors. The
pending 0.2.0 adoption adds the accepted Vital repairs and durable Integrity
history; 0.3.0 adds the separate Evidence to Action companion and 0.4.0 adds
reproducible consumer handoff and accepted receipt/compatibility contracts.
Its GitLab work collector does not yet implement the core GitLab Vital
adapter or the accepted Instruments carrier.

Phase A is closed. Phase B has five of seven items implemented on this
branch; complete executable conformance (B1) and an outside adopter (B7)
remain open. The [ROADMAP](ROADMAP.md) names the release sequence,
compatibility/audit obligations and external-adoption gates. The
[CHANGELOG](CHANGELOG.md) records every contract and policy version change.

## Provenance

The contracts implemented here come from an independent research process that
produced and reviewed them unit by unit before any code existed. The
specifications are reproduced in [docs/spec](docs/spec) and the mapping from
each contract to its research unit is in
[docs/spec/PROVENANCE.md](docs/spec/PROVENANCE.md). Disagreements between the
implementation and the specification are reported back to that process rather
than patched ad hoc.

## License

[MIT](LICENSE).
