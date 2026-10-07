# Roadmap

Ordered by what unblocks what, not by what is interesting. Every item names
who or what blocks it, so a reader can tell the difference between work not
started and work that cannot start.

## Release state and next steps — 2026-10-07

**0.5.0 Consumer Operations (E3) is implemented on
`zendreven/release-0.5.0` in [PR #69](https://github.com/drevendev/Devostasis/pull/69),
stacked on [0.4 PR #64](https://github.com/drevendev/Devostasis/pull/64).**
It provides explicit adopter project/policy/engine bindings, repeated canonical
observation and immutable invocation receipts, bounded parallel collection,
packet-bound caller outcomes, full private-history audit/export/restore and
protected GitHub/GitLab caller recipes. Existing canonical core/work lineages
and historical replay remain unchanged. See [work-operations.md](docs/work-operations.md).

An outside GitLab consumer is selected. Keep deployment qualification evidence,
source bytes, timing, inventory counts and calendar history in its private issue
and durable store. Full bridge collection qualification remains #62. Missing
records remain explicit evidence gaps. Protected production runner/scheduling
and sustained B7 calibration remain separate gates.

The next gates are review/release of the prepared increments, activation of
the reviewed pinned caller in the chosen private deployment, sustained calendar
history/independent consumer feedback, the remaining B1 exact vectors (#23),
and accepted Phase C carriers after their existing gates. Private fleet billing
(#32), GitLab exact-head approvals (#58), full collection qualification (#62),
upstream release-branch automation (#63) and incremental archive scale (#67)
remain explicit. E3 closes the implemented operations path, not those gates.

The audit of 2026-10-07 confirmed a clean initial working tree, 22 pending
commits beyond released `master`, and eight open, conflict-free PRs. All local
and remote development heads are ancestors of the 0.5 head; there is no
separate unintegrated branch to salvage. Latest published tag remains `v0.1.9`;
none of `v0.2.0` through `v0.5.0` exists. The 0.5 source head `aa642b3` passed
the complete 2,307-test suite locally on Python 3.13.13, all 148 CLI vectors,
current/frozen core and work verification, and work replay. Its
[fork matrix](https://github.com/abogun-product/Devostasis/actions/runs/37597164266)
passed on Python 3.12/3.13/3.14; its
[upstream run](https://github.com/drevendev/Devostasis/actions/runs/37597163077)
requires maintainer approval, and independent review remains pending.
Later commits require their own green CI; pushes to `zendreven/release-*` now
start that matrix automatically in the fork.

### Next delivery sequence

| Step | Deliverable | Completion evidence / blocker |
| --- | --- | --- |
| Release the implemented increments | #57 into upstream `release/0.2.0`, then #53, #59, #64 and #69 into `master`, with each release tag | Maintainer workflow approval, independent review and green checks on each final head; carried maintenance PRs #36/#37/#50 are reconciled when their commits land |
| Activate the selected outside consumer | Install a reviewed exact pin, project/policy binding, protected runner, durable writer and regular observation schedule | Actual private deployment receipts and verified stored generations; a recipe or shadow probe alone does not complete B7 |
| Qualify useful repeated operation | Complete large-project GitLab collection (#62), recover private fleet observation (#32), and collect independent consumer feedback | Repeated complete inventories, explicit partial/failure recovery, real calendar-day history and one completed bounded task with original acceptance evidence |
| Close the remaining assurance gaps | B1 exact conformance (#20/#23), timestamp/lineage/store audit families (#35), and GitLab exact-head approvals where needed (#58) | Accepted fixtures at the named boundary and explicit capability qualification; 62 named conformance cases remain without executable proof |
| Extend reach after the gates | Core GitLab Vital adapter and accepted TestState/Coverage/Deployment/Work Instrument carrier | B7 and compatibility gates, selected adopter needs, preserved historical replay; the existing GitLab work collector is a separate companion |

**The highest-impact next major increment is operational adoption and a
measured feedback loop for the implemented Evidence to Action path.** Propose
this as the next product milestone, without assigning a release number or
changing the permanent B7/v1.0 acceptance. One outside repository should run
the pinned caller on a real schedule, retain and restore its verifiable private
history, and have an independent developer/agent complete work from a verified
scope and packet. Record requests, bytes, elapsed time, recovery causes and
consumer feedback in that private deployment. Exercise a moved-source negative
control and archive restore; keep reported completion separate from independent
acceptance. Regular observations must add calendar history, not just duplicate
bundle counts. That evidence determines which Phase C instrument is useful next
and whether the current bounded handoff actually saves repository rediscovery.
It does not by itself establish predictive calibration or close all Phase B
and 1.0 gates.

Upstream Dependabot still names an absent `release/0.3.0`; #63 requires the
maintainer to establish the actual upstream release branch and route updates
there. The fork push-filter repair does not resolve that upstream deployment
choice. Long-term incremental history transfer remains #67; current whole-store
caps fail explicitly and do not prune private evidence.

### Historical 0.4/0.3 readiness snapshots

The snapshots below retain earlier release context; the current sequence and
qualification boundaries are those above.

**0.4.0 Reproducible consumer handoff (E2) is now implemented on
`zendreven/release-0.4.0`.** It carries the pending 0.2/0.3 ancestry and adds
accepted receipt identity and compatibility, complete recorded bundle tuple
admission, work v2 named mutable sources and enforced pinned source packets.
Historical core/work examples remain replayable. See
[external-adoption.md](docs/external-adoption.md) for the consumer path.

The external GitLab path supports verified scope/slice/packet and deleted-ref
negative controls with existing glab credentials. Detailed pilot evidence stays
in the adopter's private issue/history.
Issue #61 records credential/locator adoption; #62 records full-inventory
throughput debt. Sustained history, an installed production caller and exact-head
GitLab approval qualification (#58) remain open. E2 does not close B1, B7, private fleet
recovery (#32) or the deferred core GitLab/Instrument carrier. Production
activation and sustained calibration remain the next deployment milestone.

The earlier 0.3 readiness snapshot below is retained as release context.
Compatibility adoption and candidate binding (#60) now have implementation;
their remaining deployment/qualification boundaries are described above.

The repository is at the **release-readiness and external-adoption stage**:
the observation engine is released, the work companion is implemented, and
Phase B is still open. The audit started with a clean working tree. Every
outstanding development branch already has a pull request:

| Work | Pull request | Integration state |
| --- | --- | --- |
| 0.2.0 accepted Vital/history adoption | [#53](https://github.com/drevendev/Devostasis/pull/53) | Open; targets `master` |
| 0.2.0 history admission/readiness repair | [#57](https://github.com/drevendev/Devostasis/pull/57) | Open; targets `release/0.2.0`, before #53 |
| 0.3.0 Evidence to Action | [#59](https://github.com/drevendev/Devostasis/pull/59) | Open; includes the original commits of #53 and #57 |
| 0.4.0 reproducible consumer handoff | [#64](https://github.com/drevendev/Devostasis/pull/64) | Open; includes #59 and earlier pending commits |
| 0.5.0 consumer operations | [#69](https://github.com/drevendev/Devostasis/pull/69) | Open; includes #64 and all earlier development heads |
| Dependabot, CI concurrency, Hungry Crab state | [#36](https://github.com/drevendev/Devostasis/pull/36), [#37](https://github.com/drevendev/Devostasis/pull/37), [#50](https://github.com/drevendev/Devostasis/pull/50) | Original commits included in #57 and #59; both attribution receipts/notices retained |

The release heads are mergeable. Fork CI passed for the prepared heads on
Python 3.12/3.13/3.14; upstream runs for #57/#59 require maintainer approval,
and neither PR has an independent review yet. A later push needs fresh CI
for its own head. Inclusion in a release branch is not an upstream merge:
all eight PRs remain open and no `v0.2.0` through `v0.5.0` tag exists.

**0.3.0 Evidence to Action is implemented on this release branch**, with its
own consumer contract and target E1. The companion supplies five queues,
GitHub/GitLab work context, revision-bound producer findings, durable scope
history, replay, bounded handoff and read-only pre-execution checks. See
[docs/work-scopes.md](docs/work-scopes.md) for the complete adopter path.
The public GitHub pilot read all five then-open PRs in 38 successful requests.
GitLab exact-head approvals remain explicit UNKNOWN, tracked in
[#58](https://github.com/drevendev/Devostasis/issues/58); its deployment pilot
belongs to the independently integrating GitLab project. This implements a
companion consumer contour, not the core accepted Phase C Instrument carrier
or the unaccepted Evidence Observatory composition.

Automatic candidate content recheck also needs a named mutable source binding
([#60](https://github.com/drevendev/Devostasis/issues/60)); v1 refuses to infer
freshness from a historical SHA and requires a fresh attested inventory there.

This is an unreleased increment. E1 being implemented does not close B1, B7,
the earlier target `v0.3` (the deferred Phase B/adoption completion bar), or
v1.0. Their permanent ids and original acceptance are preserved. Review and
release the carried 0.2.0 fixes and this increment; then prioritize sustained
observation (#32), remaining conformance (#23), compatibility adoption (#34)
and an external calibration consumer. Do not substitute the public integration
check for that sustained outside-consumer evidence.

The latest tagged release on `master` is **v0.1.9**. **0.2.0 is prepared,
not released**: [#53](https://github.com/drevendev/Devostasis/pull/53) is still
open and there is no `v0.2.0` tag. The adoption statements below describe the
implementation on `release/0.2.0`, not availability on `master`. Phase A is
closed; Phase B has four completed items in the released version and five
in this branch, where B3 is implemented. B1 and B7 remain open. The
specification still names 62 cases without executable proof in this branch.

The next work is ordered by the evidence each step makes possible:

1. **Review and release the prepared increments.** #57 already binds carried
   history to the verified predecessor, rejects duplicate carried revision
   ids and integrates the pending maintenance. The review of 2026-10-06 also
   repairs unknown issue-state coercion and mixed-availability collection in
   the 0.3.0 work collector. The release sequence is #57 into `release/0.2.0`,
   #53 into `master` and tag `v0.2.0`, then #59 into `master` and tag `v0.3.0`.
   Approve upstream CI and review each final head first. Retire the superseded
   maintenance PRs when their commits land through the release; do not apply
   them again independently.
2. **Restore sustained observation and complete Phase B.** The latest public
   evidence in [#32](https://github.com/drevendev/Devostasis/issues/32) records
   an Actions billing refusal and a fleet history ending on 2026-09-10; check
   and restore the private observer before claiming fresh calibration data.
   Repair the GitHub run-listing ceiling
   ([#51](https://github.com/drevendev/Devostasis/issues/51)), keep external
   check-app history uncertainty explicit
   ([#52](https://github.com/drevendev/Devostasis/issues/52)), adopt the
   compatibility policy, finish B1, and run a B7 pilot selected by the owner.
3. **Adopt the implemented bounded work companion.** The consumer
   work-scope surface in [#54](https://github.com/drevendev/Devostasis/issues/54)
   projects five typed queues (`review`, `finish_merge`, `implement_issue`,
   `research`, `analyze_code`) with stable ids, exact revisions, explicit
   consumer priority, acceptance, dependencies, freshness and coverage.
   [#55](https://github.com/drevendev/Devostasis/issues/55) supplies
   revision-bound findings and source slices;
   [#56](https://github.com/drevendev/Devostasis/issues/56) supplies the GitLab
   CI and durable handoff recipe. This branch implements the separate
   `devostasis.work.v1` consumer contract and workflows. These are not
   accepted core Vital/Instrument semantics; task selection remains outside
   the observational engine. Adopter policy, sustained external deployment
   and the revision-bound GitLab approval capability are the remaining steps.
4. **Deliver the accepted reach contracts in small packages.** GitLab,
   Coverage, TestState, Deployment and Work follow the existing Phase C gates.
   The additional CLI and Explorer composition in
   [#47](https://github.com/drevendev/Devostasis/issues/47) still needs its
   independent G1 judgement; acceptance of its component contracts does not
   accept the whole candidate.

The product increment already implemented in this branch is **Evidence to Action**:
trusted observations plus reproducible, bounded work scopes for an outside
consumer. Its success criterion is a developer or agent selecting one task
from verified evidence, recovering explicitly missing input, and verifying
the stated acceptance without rediscovering the whole repository. GitLab
and the Instruments expand that evidence; a presentation-only release does
not satisfy this consumer criterion. No queue grants permission to merge,
claim or deploy, and business priority remains explicit consumer policy.

## Recommended next major increment: external adoption of Evidence to Action

Treat this as a proposed next increment, not a newly accepted research unit
or a promise of a release date. The largest product gain now comes from an
outside consumer relying on the implemented scopes over time. More surface
before that feedback cannot establish whether the current handoff is useful.

Deliver it in this order:

1. Publish the prepared releases, restore the private fleet observer (#32)
   and choose one outside repository for B7. Public self-observation succeeded
   on 2026-10-05, but it is a different workflow; the latest public statement
   about the private fleet is still its 2026-09-30 billing failure. Fresh
   private history must be checked directly before it is called restored.
2. Adopt the accepted compatibility policy (#34) and work the outstanding
   timestamp, lineage and store audit families (#35), including the explicit
   core receipt-identity adoption decision (#19). Give stored versions
   exact verification/replay dispatch and keep old bundles verifiable.
   Complete the remaining executable conformance through B1/#23; keep the
   public gap count explicit until accepted fixtures actually run.
3. Run an outside developer/agent against verified scopes with a declared
   policy, bounded reads, acceptance and live recheck. Add the named candidate
   source binding (#60) and validate GitLab revision-bound approvals (#58)
   where the consumer needs them. Record whether tasks were completed, what
   evidence was missing and whether recheck correctly invalidated moved work.
4. After the Phase B and compatibility gates, expand the same consumer path
   with the core GitLab adapter and accepted Instruments carrier. Prioritize
   TestState/Coverage/Deployment/Work from observed adopter needs; the existing
   companion report profiles do not close those core contracts.

Acceptance: an outside repository produces sustained verifiable history;
its consumer selects and completes a task from the declared scope without
rediscovering the whole repository; missing evidence yields bounded recovery;
changed revisions invalidate stale work; historical bundles still replay.
Keep the observer read-only and execution/merge/deploy authority in that
outside client. An HTML Explorer, renderer themes and PyPI distribution
remain later reach/presentation work, subject to their existing gates.

## How this roadmap is worked

```text
standing obligations (interrupt anything)
        │
        ▼
Phase A  observe ourselves honestly            closed
        │
        ▼
Phase B  durability and coverage               5 of 7 done
        │
        ▼
Phase C  reach: other providers and instruments
        │
        └── back to A whenever a consumer or the research process
            says the base is wrong
```

**Standing obligations** are not phases and do not wait their turn:

| Obligation | Trigger | Response |
| --- | --- | --- |
| Research finding | an entry in `ANSWERS_TO_IMPLEMENTER`, an issue labelled `for:researcher`, or an accepted unit this repository has not adopted | adopt it, or record why not, before continuing queued work. Since 2026-09-20 the research process also runs static audits of this repository and records them on Drive only; [#35](https://github.com/drevendev/Devostasis/issues/35) is their catalogue here, and a session that starts on this repository reads the handoff document first |
| Calibration contradiction | a bundle that contradicts a rule on real evidence | record it under "Calibration findings"; never change a threshold to make one repository look right |
| Consumer question | a consumer cannot do something the contract promised | answer it before adding surface |

**Rule changes are research units, not maintenance.** A band rule, threshold,
window or gauge constant changes only with named evidence, fixtures and an
independent judgement. Making the engine's own report look better by moving
its own thresholds is the failure the whole contract chain exists to prevent.

**Improving a project's Vitals is a different activity from improving the
Vitals themselves.** Devostasis reporting `SCATTERED` about itself is a true
statement; the fix belongs in this repository, not in the rule.

## Who blocks what

| Item | Owner of the next step | Blocker |
| --- | --- | --- |
| B1 vectors | research process, then this repository | `PV-TEST-001` is being produced as `PV-TEST-VECTORS-00n` units; their findings are [#20](https://github.com/drevendev/Devostasis/issues/20), [#21](https://github.com/drevendev/Devostasis/issues/21), [#22](https://github.com/drevendev/Devostasis/issues/22) and [#23](https://github.com/drevendev/Devostasis/issues/23), and two of them need vector kinds this repository has not built |
| B7 first outside consumer | integrating owner and elapsed observation time | repository selected; production caller/schedule, sustained private history and independent feedback remain |
| C1 GitLab adapter | **this repository, after B7 and the compatibility policy** | the requirements are accepted (`PV-GITLAB-003` by `PV-REV-GITLAB-003`, [#34](https://github.com/drevendev/Devostasis/issues/34)) |
| C2 uncollected GitHub surfaces | this repository | each surface needs a contract decision first |
| C3 Instruments | **this repository, after B7 and the compatibility policy** | the envelope, the carrier and four instruments are accepted ([#34](https://github.com/drevendev/Devostasis/issues/34)); the carrier moves the configuration and bundle contracts, which is why the policy comes first |
| C4 register generators | this repository | none; low value until a second project uses registers |
| Renderer themes | owner | needs an owner-selected vocabulary per band |
| PyPI publication | owner | needs an owner decision that the API surface is stable |
| Compatibility policy | maintainer release/review | accepted PV-COMPAT-002 implementation is in pending 0.4/0.5 ancestry; no production nonidentity edge is declared |
| `PV-CAL-004` predictive validity | elapsed time | needs calendar days of bundles, not more bundles (see the self-review) |
| Judgements owed to us | delivered | all four, listed below; one of them is a required repair |
| Accepted judgements not yet adopted | this repository after existing reach gates | core Phase C GitLab/Instrument carriers and blocked executable conformance surface remain; compatibility and receipt identity are implemented in pending 0.4/0.5 ancestry; Vital repairs/B3 are in pending 0.2 ancestry |
| Audit handoffs | this repository | about forty `REPAIR REQUIRED` static audits since 2026-09-20, catalogued in [#35](https://github.com/drevendev/Devostasis/issues/35); 0.1.9 repairs the store, transport, decoder and payload families, the timestamp and lineage families are open |
| Review of 2026-09-30 | this repository, research for four | [#48](https://github.com/drevendev/Devostasis/issues/48): its defects are repaired in 0.1.9; what needs work or a decision is #38 to #46, four of them `for:researcher` (#39, #40, #42, #43) |
| "Evidence Observatory" candidate | research review, then this repository | the owner asked for a large next release on 2026-09-30; the pending 0.2.0 branch implements the part that rests on accepted contracts, and the candidate specification (`PV-RELEASE-020-001`, not yet accepted) keeps the rest; [#47](https://github.com/drevendev/Devostasis/issues/47) maps its sixteen packages onto the issues here |

The four judgements the research process owed this repository about work
already shipped have all been delivered:

| Unit | About | Verdict |
| --- | --- | --- |
| `PV-REV-REGISTERS-001` | whether a `Target: <id>` marker is auditable enough under G7, and whether a bulk-editable register is gameable | ACCEPT (J1..J6, cases REG-01..08): the literal marker satisfies G7; editability stays provenance-visible; no new rule |
| `PV-REV-FLEET-001` | whether `devostasis.fleet.v1` is right to declare no cross-project ordering | ACCEPT (FLEET-01..10): `aggregate` and `cross_project_order` stay exactly null; a control plane that routes across repositories owns that policy outside Devostasis |
| `PV-REV-DIRECTION-CLOSED-TARGET-001` | calibration finding 9: closing a delivered target un-links the work that delivered it | REPAIR REQUIRED: Direction linkage must be state-neutral, an active change request linked to a resolvable declared target stays linked when the target closes; versioned Direction rule, cases DIR-CLOSED-01..09; adopted in 0.2.0 as `direction.bands.v2` ([#33](https://github.com/drevendev/Devostasis/issues/33)) |
| `PV-SPEC-001` | the conformance review of every adoption since the specification was last reviewed, including B5 | two passes on 2026-09-07: the 0.1.8 adoption reused the ORDER identifiers (repaired before the tag, #16); the post-repair pass found the runtime conformant and the public status prose stale, which 0.1.9 reconciles in `PROVENANCE.md` and here |

Delivered judgements and their adoption. Under the standing obligation above
they came before any queued target; 0.1.9 adopted every one that did not need
an owner decision:

| Unit | Where | State |
| --- | --- | --- |
| `PV-REV-INTEGRITY-UNKNOWN-001` | [#13](https://github.com/drevendev/Devostasis/issues/13) | adopted in 0.1.9: `integrity.bands.v1+ci-unit-004`, cases `INT-UNKNOWN-01..06` executable |
| `PV-REV-TEST-003` | [#12](https://github.com/drevendev/Devostasis/issues/12) finding 3 | adopted in 0.1.9: a `PARTIAL` required series is `UNKNOWN` with no band |
| `PV-REV-TEST-VECTORS-002` | [#21](https://github.com/drevendev/Devostasis/issues/21) | adopted in 0.1.9: `sample_strength`, `CI_SPARSE_SAMPLE`, the accepted `T2`/`R1`/`R2` vectors |
| `PV-REV-ACTIVITY-COVERAGE-001` | [#9](https://github.com/drevendev/Devostasis/issues/9) | adopted in 0.1.9: `ACT-COV-01..05` as `activity` vectors, the `PROVENANCE.md` entry |
| `PV-REV-TEST-VECTORS-004/005/007` | [#22](https://github.com/drevendev/Devostasis/issues/22) | adopted in 0.1.9: `R3`, `R4`, `T4`, `T5`, `T7` vectors; the T5 diagnostic and the T7 upper-bound path in the evaluators; whether the GitHub adapter emits `retention_semantics` is a fleet-wide decision still open there, and since the Clutter adoption it also decides whether a capped branch head resolution can ever prove a floor on GitHub |
| `PV-CLUTTER-INCOMPLETE-001`, `PV-ISSUE-026-RECONCILE-001`, `PV-REV-PR-031-003` | [#26](https://github.com/drevendev/Devostasis/issues/26) | adopted in 0.1.9: `clutter.bands.v1`, cases `CLU-INCOMPLETE-01..20` executable; an incomplete component is a confirmed burden floor, never a manufactured band, and a `PARTIAL` count proves one only with its subset proof (`CLU-PARTIAL-TRUST-01..08`) |
| `PV-INT-TOTALITY-001` | [#33](https://github.com/drevendev/Devostasis/issues/33) | adopted in 0.1.9 under the same Integrity rule version, in place of the unresolved superset the review of 2026-09-30 found could omit the band it emitted ([#48](https://github.com/drevendev/Devostasis/issues/48)); `INT-TOTAL-01..06` and `08..13` executable |
| `PV-REV-DIRECTION-CLOSED-TARGET-001`, `PV-DEBT-PARTIAL-001`, `PV-HORIZON-PARTIAL-001`, `PV-DIRECTION-INCOMPLETE-001`, `PV-TEST-004` | [#33](https://github.com/drevendev/Devostasis/issues/33) | adopted in 0.2.0: `direction.bands.v2`, `horizon.bands.v2`, `debt.bands.v2`, one rule version each; `DIR-CLOSED-01..09`, `DIR-INCOMPLETE-01..16`, `HOR-PARTIAL-01..16`, `DEBT-PARTIAL-01..16` executable; T9 held by its generator over the nine former gap families |
| `PV-REV-HIST-002` | [#34](https://github.com/drevendev/Devostasis/issues/34) | adopted in 0.2.0 as target B3: `integrity.bands.v1+ci-unit-004+hist-002`, HIST-01..20 executable except HIST-14, which has no accepted migration to execute |
| `PV-REV-GITLAB-003`, instrument contracts, `PV-CONFORMANCE-SURFACE-001`, `PV-RENDER-CLINICAL-001` | [#34](https://github.com/drevendev/Devostasis/issues/34) | core reach/conformance/theme work remains unadopted under its existing gates; compatibility is implemented since pending 0.4.0; clinical owner selection is not established |
| `PV-REV-RECEIPT-IDENTITY-003` | [#19](https://github.com/drevendev/Devostasis/issues/19) | implemented in pending 0.4/0.5 ancestry: bundle v3, manifest v2, observations v2 and receipt identity v1 with historical verification dispatch; maintainer review/release remains |

One judgement is ours to ask for rather than to wait on: `ORDER-01..15` are
this repository's enumeration of the rules the accepted ordering contract
states, so `PV-SPEC-001` reviews whether the enumeration covers the contract,
not only whether the code matches the enumeration.

## Phase A: observe ourselves honestly — closed

- **A1. Devostasis declares its own plan and debt.** Done in 0.1.3. The
  registers are `.devostasis/targets.json` and `.devostasis/debt.json`, the
  fleet and the self-observation workflow read them, and a pull request links
  to a target with a `Target: <id>` line.
- **A2. This repository is the first consumer.** Continuing, not a
  deliverable: whatever a stranger would trip over, we trip over first.

Exit gate, met: Devostasis reports `DECLARED` for Horizon and a real linkage
share for Direction, and its own attention order is actionable.

## Phase B: make it trustworthy over time

### B1. Executable conformance vectors — the format is built, the vectors are owed

The specification names **62 conformance cases with no test behind them**
(T3, T6, T8, R5..R53, ART-05, ART-08..ART-11, ART-15, RPT-4..RPT-6, RPT-9).
It named 70 until 0.1.9 adopted the seven exact vectors the research process
has accepted so far (`T2`, `R1`, `R2`, `R3`, `R4`, `T4`, `T5`, `T7`), and 63
until 0.2.0 held T9 to its accepted table with a generator; the rest are
still the research process's to produce, one accepted family per unit.

The half that was ours shipped in 0.1.8: `devostasis.vectors.v1`, a runner, a
`devostasis vectors` command and a published schema
([vectors.md](docs/spec/vectors.md)). A case is a JSON document that states
evidence and expected result; the `vital` kind evaluates one Vital over raw
observation envelopes, the `delta` kind compares two snapshots. It fails
closed, so an unknown kind or a malformed vector is a red build rather than a
case that silently did not run, and `ORDER-01..15` are already carried that
way. 0.1.9 added the `ci` kind, which reaches the provider-native
normalization `R5..R10` are about ([#20](https://github.com/drevendev/Devostasis/issues/20)),
the `activity` kind for `ACT-COV-01..05`, and `variants`, the one-identifier
multi-variant shape `T8` and `R9` need
([#23](https://github.com/drevendev/Devostasis/issues/23)). Two more kinds
remain deliberately absent until a case needs them: bundle-level identity
cases (`ART-*`) and store cases (`RPT-4..RPT-6`, `RPT-9`) that need a fixture
store rather than a snapshot pair; `T3` needs a surface that carries
`RAW_RUNS` provenance into Integrity, which no accepted contract defines yet.

Closing B1 needs the vectors themselves. Until then debt D-1 stays open, and
the specification keeps saying that "conformance" covers about half of what it
names.

### B7. First outside repository integrates self-observation — the owner's move

The owner selected an outside GitLab repository. The 0.4/0.5 implementation
provides source handoff, an explicitly bound caller, operational records and
portable restore. Keep adopter qualification evidence private. The point remains
independent consumer feedback over sustained time. Protected production
scheduling, private durable deployment and calibration history are still open;
templates and local proofs do not substitute for them.


### Also open from the reporting review

`RPT-4..RPT-6` and `RPT-9` as executable cases, including a permission-domain
fixture for the store. Ours, and covered by B1's format.

### Done

- **B3** (0.2.0): durable revision history across bundles, `PV-HIST-002`
  (accepted by `PV-REV-HIST-002`). The union of every attempt observed per
  parent per revision is carried from the immediate predecessor
  (`ci.revision_history_carried` in, `derived.revision_history` out), so a
  failure the provider stops showing still counts while its revision is in
  the window, and a gap in the chain is explicit rather than bridged by an
  older bundle. Parent-level and incomplete favorable evidence is
  `UNKNOWN_HISTORY`, never a reconstructed pass (R52). It changed Integrity's
  history source, not the consumer surface.
- **B5** (0.1.8): the band ordering of `PV-BAND-ORDER-001`, adopted.
  `delta.json` is `devostasis.delta.v2`, emits `IMPROVED` and `WORSENED` where
  a Vital declares an order over the pair, and names the ordering it applied.
  Every row that could have been ordered and was not says why. Ordering is per
  Vital only: Clutter `CLEAN > LIGHT > CLUTTERED > HEAVY`, Flow
  `MOVING > CONGESTED > GRIDLOCKED` for a live queue with `NO_QUEUE`
  incomparable, Integrity `CLEAN > FLAKY > FAILING` and
  `SPARSE > SPARSE_MIXED` with no order across the families or with the
  evidence states; Pulse, Horizon, Direction and Debt declare none. A direction
  needs a `COMPARABLE` pair, an unchanged `rule_id` and `AVAILABLE`/`EXACT`
  evidence on both sides; observability transitions and
  `RULE_VERSION_BOUNDARY` keep precedence and gauges establish no order.
  Conformance `ORDER-01..15`, executable. It moved bundle identity once and
  made `PV-SPEC-001` due. `PV-BAND-ORDER-001` supersedes `PV-ORDER-001`, the
  research item that asked whether an order could be declared at all;
  [`docs/spec/PROVENANCE.md`](docs/spec/PROVENANCE.md) records the acceptance
  and [`docs/spec/history-and-reports.md`](docs/spec/history-and-reports.md)
  now names the new identifier.
- **B2** (0.1.5): a project is located by `immutable_project_id`; a rename or
  transfer relocates the directory once and is recorded, and two projects are
  never merged into one directory. Closed debt D-3.
- **B4** (0.1.6): conditional requests with a persisted entity-tag cache,
  retries bounded by what the provider asks and by a total waiting budget, and
  a per-project request budget that truncates honestly. Measured on the fleet:
  rate-limited requests fell from 248 to 66 per run. Closed debt D-2.
- **B6** (0.1.4): `projects/index.json` under `devostasis.fleet.v1`, with no
  aggregate and no cross-project ordering.

Exit gate for Phase B: a fleet run survives a rate-limit day, a renamed
repository keeps its history, the conformance table names no case that is
unimplemented, and one outside repository has produced a bundle and said what
was unclear.

## The consumer surface

Integration is deferred until this list stops moving, because an adopter who
builds on a contract we then change pays for our churn. Version 0.1.2 is the
cautionary case: `devostasis.demand.v2` removed `attention_key`, and anything
built on it would have broken on our release, not theirs.

| Surface | Status |
| --- | --- |
| `demand.json` levels and attention order | `devostasis.demand.v2`, stable since 0.1.2 |
| `observe-self.yml` inputs and outputs | stable since 0.1.1 |
| `snapshot.json` bands and evaluation states | stable since 0.1.0 |
| machine-readable fleet index | `devostasis.fleet.v1`, stable since 0.1.4 |
| `delta.json` transition classes | `devostasis.delta.v2`, stable since 0.1.8 |

No row is moving. "The base is implemented" was stated as an observable
condition rather than a feeling, and the condition is now met: the next change
to any of these surfaces is a breaking change to somebody, which is exactly
why B7 comes next and why the compatibility policy is now the gap that matters.

## Phase C: reach

Not before Phase B, because each item multiplies the surface Phase B makes
trustworthy.

- **C1. GitLab adapter** (requirements accepted, `PV-GITLAB-003`,
  [#34](https://github.com/drevendev/Devostasis/issues/34)): merge requests,
  pipelines with in-place retries, epics and iterations as planning targets,
  under the same provider-neutral observation keys. Until it exists, provider
  neutrality is a design intent rather than a demonstrated property.
- **C2. GitHub surfaces not collected yet** (ours, each needs a contract
  decision): external check apps alongside Actions, legacy commit statuses,
  branch protection and rulesets as an *enforcement* observation, pull request
  to issue to milestone linkage, GitHub Projects fields as planning targets.
- **C3. Instruments** (envelope, carrier and four instruments accepted,
  [#34](https://github.com/drevendev/Devostasis/issues/34)): configurable
  deterministic instruments separable from the seven Vitals and sharing their
  availability, freshness, coverage and provenance semantics: test state
  (`PV-TESTSTATE-002`), coverage (`PV-COV-003`), deployment state
  (`PV-DEPLOY-002`), normalized work since the previous bundle
  (`PV-WORK-002`), carried by `devostasis.instrument-carrier.v1`, which moves
  the configuration and bundle contracts and therefore waits for the
  compatibility policy.
- **C4. Register generators** (ours, unblocked): scripts that derive
  `targets.json` from a project's own roadmap format, so the register never
  drifts from the roadmap. Worth little until a second project uses registers.

## Presentation

- **Custom report templates** (ours, deferred by decision): a user-supplied
  template persisted in the bundle and hashed into its identity. The `display`
  configuration covers selection and layout without a template engine.
- **`report.html`** (ours, deferred): already identity-bearing, since enabling
  it changes `bundle_id`; the reporting review confirmed it stays optional.
- **Renderer themes** (blocked by the owner): vivid or clinical labels beside
  the canonical bands, in a layer that cannot alter machine semantics
  (`PV-RENDER-CLINICAL-001`). Needs an owner-selected vocabulary per band that
  respects the neutrality of Direction `FULLY_LINKED` and Debt `PRESENT`.
- **Per-Vital history views** (ours): transition timelines and observability
  history.
- **Locales beyond English** (ours).

## Storage and governance

- Object storage and same-repository history ref backends behind the
  `HistoryStore` interface (ours).
- Retention and compaction for convenience and derived views only; immutable
  bundles needed for audit are never destroyed (decided by the reporting
  review, ours to implement).
- Optional exclusion of `observations.json` for very active repositories
  (ours).
- **Publication to PyPI** (blocked by the owner): needs a decision that the
  API surface is stable.
- **Versioning and compatibility policy per contract identifier** (accepted,
  `devostasis.contract-compatibility.v1` by `PV-REV-COMPAT-002`,
  [#34](https://github.com/drevendev/Devostasis/issues/34)): the repository
  declares 22 contract identifiers; the accepted policy makes them opaque
  exact tokens dispatched under an immutable versioned policy, which is what
  a consumer may rely on across versions. Ours to adopt, before any Phase C
  contract move.

## What ends the loop

**0.2 was defined here as** Phase A and Phase B closed, which includes one
consumer outside this repository depending on a bundle, and no accepted
research unit waiting for adoption. The pending 0.2.0 adoption release is
scoped to ship before that, at the owner's request for a large release (#47),
with the accepted Vital repairs and durable history. What the definition still asks for,
B7 and the adoption of the Phase C contracts of #34, is now the bar for 0.3.

**1.0 is reached when** the contract identifiers have a compatibility policy,
a second provider is implemented, and the calibration corpus is large enough
that a threshold change can be argued from evidence rather than from one
repository.

## Background clock

`PV-CAL-004` measures whether the attention order of one bundle predicts where
work happened in the next ones. It is blocked by elapsed time, and by corpus
quality rather than corpus size: see the self-review below.

## Self-review, 2026-09-06

An honest reading of the state, including what is weaker than the numbers
suggest.

**The calibration corpus is thinner than it looks.** 218 bundles across 18
projects sounds substantial. They span **two calendar days**, and 144 of them
were produced on the second day by manual runs minutes apart while releases
were being verified. `PV-CAL-004` asks whether the attention order of bundle N
predicts activity in bundles N+1..N+k; bundles minutes apart have almost no
activity between them by construction, so they add count without adding
evidence and could make the study look ready while it holds about one day of
real signal. The study must count calendar days, not bundles, and manual
triggering should stop now that the release chain is quiet.

**Half of the named conformance surface is unproven.** 79 table rows cite a
test; 70 named cases have none. The specification says so and the roadmap
admits it, so nothing is being hidden, but "conformance" currently covers
about half of what it names. This is debt D-1 and target B1. Since 0.1.8 the
missing half is missing evidence, not missing machinery: a case can be written
as a vector and executed, and the fifteen ordering cases are carried that way.
Building the runner did not prove one of the 70, and counting it as progress on
D-1 would be counting the tooling as the test.

**Provider neutrality is a design intent, not a demonstrated property.** Every
provider-neutral contract has exactly one implemented provider. The GitLab
semantics exist in the research contracts and nothing exercises them. Until a
second adapter exists, "provider-neutral" should be read as "designed to be",
and the first GitLab implementation should be expected to find contract
defects rather than to confirm the design.

**Bundle identity moved four times in two days** (0.1.2 receipt and rule
versions, 0.1.6 receipt v2, 0.1.7 evidence shape, 0.1.8 delta v2). Every one
was justified and comparability held throughout, but for a system whose product
is durable comparable history that cadence is a cost paid by whoever reads the
store. The fourth was the last planned one: the consumer surface is now frozen,
which is the natural place to slow down, and a fifth move would need a reason
strong enough to state here.

**The engine still has one consumer, and it wrote the contracts.** This is the
largest untested assumption in the project. It is deferred deliberately rather
than forgotten, and B7 is one step away.

**What is genuinely solid.** The core contracts have documented research
provenance in `docs/spec/PROVENANCE.md`; local and pending extensions stay
explicitly identified there and in the judgement table above. Selected
fail-closed paths have regression coverage: an invalid stored configuration
stops a replay, and a locator held by another project refuses a write.
Pagination limits are checked for the inventories that have tests; CI
check-suite coverage still has the gaps tracked in
[#12](https://github.com/drevendev/Devostasis/issues/12), where a truncated
sample can still be emitted as complete. All 218 bundles in the
store verify from their own contents. Two automated guards now catch the
mechanical half of specification drift, and one of them found five undocumented
identifiers on the day it was written.

## Calibration findings from the real runs

Recorded so they reach the research process. Dispositions after `PV-CAL-002`
and `PV-CAL-003` (2026-09-06):

1. **Flow with an empty queue and a slow median.** Repaired in
   `flow.bands.v1` (`PV-FLOW-EMPTY-QUEUE-001`, FLOW-EQ-01..06).
2. **Pulse and bursty solo development.** Open observation: substantial work
   on two active days remains `QUIET`. The frozen active-day rule was found
   defensible; contrasting fixtures are wanted before any change.
3. **Integrity with a persistently failing secondary workflow.** Confirmed as
   the evidence-faithful reading; no repair.
4. **Direction when no milestone ever existed.** Confirmed: `SUPPORTED_UNUSED`
   yields `UNDECLARED`, not `SCATTERED`.
5. **`timed_out` and `startup_failure`.** Confirmed as `VERIFY_FAIL` and
   `UNKNOWN` (CI-OUTCOME-01..04).
6. **Pulse on capped enumerations.** Repaired in `pulse.bands.v1`
   (`PV-PULSE-REQUIRED-LOWER-BOUND-001`, PULSE-CAP-01..05).
7. **Median time to merge in whole hours.** Repaired: the classifier consumes
   the exact rational median in seconds (`PV-FLOW-MERGE-LATENCY-001`,
   FLOW-PREC-01..09).

Judged since:

8. **Per-Vital rule version boundary.** Accepted by
   `PV-REV-RULEBOUNDARY-001`: a Vital whose `rule_id` changed is
   `INCOMPARABLE` on its own while the bundle stays `COMPARABLE`.
9. **Closing a delivered target un-links the work that delivered it.**
   Direction counted links to *open* targets, so completing a target removed
   the linkage of the pull requests that delivered it while they were still
   in the 28-day window. Measured here: closing A1 and B6 took the linked
   count from 2 of 6 to 0. Repaired in `direction.bands.v2` (0.2.0,
   `PV-REV-DIRECTION-CLOSED-TARGET-001`): on the same store this repository
   reads 9 of 18 active change requests traced, `MIXED`, where the open-target
   count said 4 of 18, `SCATTERED`.

Open:

10. **Activity can declare an interval wider than its evidence.** Declared
    since 0.1.7 with `INTERVAL_EXCEEDS_EVIDENCE_WINDOW`; whether collection
    should widen instead is [issue #9](https://github.com/drevendev/Devostasis/issues/9).
