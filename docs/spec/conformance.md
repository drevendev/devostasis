# Conformance cases

Identifiers come from the research units that defined them and are never
reused. "Test" names the pytest function that implements the case, or the
executable vector that does: `vector:<CASE>` is the vector with that case id in
`tests/vectors/`, run by `devostasis vectors` and by the test suite
([vectors.md](vectors.md)). Every vector in the corpus is cited here and every
citation resolves; both directions are a test (`test_spec_drift.py`).

## Observation contract (PV-OBS-001)

| Case | Meaning | Test |
| --- | --- | --- |
| C1 | observed zero is AVAILABLE with value 0 | `test_c1_observed_zero_is_available_with_value_zero` |
| C2 | tier limitation is UNAVAILABLE without value | `test_c2_tier_limitation_is_unavailable_without_value`, adapter `test_c2_c3_c7_http_failures_become_explicit_statuses` |
| C3 | permission denial is FORBIDDEN | same |
| C4 | truncated history is PARTIAL with coverage | `test_c4_truncated_history_is_partial_with_coverage`, adapter `test_c4_pagination_cap_is_partial` |
| C5 | stale evidence keeps its value but is not fresh | `test_c5_stale_evidence_keeps_value_but_is_not_fresh` |
| C6 | connector ambiguity is UNKNOWN | `test_c6_connector_ambiguity_is_unknown` |
| C7 | transient failure is ERROR | `test_c7_transient_failure_is_error_not_unknown` |

## Vitals V0.x repairs

| Case | Meaning | Test |
| --- | --- | --- |
| T1 | configured CI with zero runs is NO_RECENT_RUNS | `test_t1_no_recent_runs_is_neither_clean_nor_uninstrumented` |
| T2 | configured false with zero recent revision verification is exactly UNINSTRUMENTED | `vector:T2` |
| T4 | unavailable change-request activity keeps Pulse a conservative lower bound | `vector:T4` |
| T5 | issue-only activity is QUIET with the provenance diagnostic `PULSE_ISSUE_ONLY_ACTIVITY` | `vector:T5` |
| T7 | unclassified stale branches are an upper bound on Clutter burden (`CONSERVATIVE_UPPER_BOUND`, `CLUTTER_BRANCH_PURPOSE_UNCLASSIFIED`) | `vector:T7` |
| R1 | two deduped revisions, one historical failure, latest success: SPARSE_MIXED with `sample_strength` SPARSE and `CI_SPARSE_SAMPLE` | `vector:R1` |
| R2 | one deduped failing revision: FAILING, and still a sparse sample | `vector:R2` |
| R3 | zero observed activity with an unavailable channel is DEGRADED DORMANT | `test_r3_zero_activity_with_unavailable_channel_is_degraded_dormant_lower_bound`, `vector:R3` |
| R4 | complete fresh zero activity across every Pulse channel is exactly DORMANT | `vector:R4` |
| V0.7 precedence | unresolved sibling blocks PASS, never hides FAIL | `test_v0_7_unresolved_sibling_blocks_pass_but_not_fail` |
| R54 | same-revision retry keeps historical failure | `test_r54_same_revision_retry_success_keeps_historical_failure` |
| R55 | retry-count invariance | `test_r55_retry_count_invariance` |
| R56 | newer revision is a distinct sample | `test_r56_newer_revision_is_a_distinct_sample` |
| R57 | order and surface invariance | `test_r57_order_and_surface_invariance` |

## Integrity: the newest revision and the sample (PV-REV-INTEGRITY-UNKNOWN-001, PV-REV-TEST-003, PV-REV-TEST-VECTORS-002)

Rule `integrity.bands.v1+ci-unit-004`, adopted in 0.1.9; since 0.2.0 the same
cases hold under `integrity.bands.v1+ci-unit-004+hist-002`. The six cases of the
accepted judgement on issue #13 are executable; two of them start at the
provider-native normalization, because their subject is that `startup_failure`
and an unsupported conclusion reach the Vital as `UNKNOWN`.

| Case | Meaning | Test |
| --- | --- | --- |
| INT-UNKNOWN-01 | four historical passes plus a newest in-scope UNKNOWN revision evaluate UNKNOWN with no band; the passes stay auditable | `vector:INT-UNKNOWN-01` |
| INT-UNKNOWN-02 | the same shape with the UNKNOWN produced by `startup_failure`, in either enumeration order | `vector:INT-UNKNOWN-02` |
| INT-UNKNOWN-03 | the same shape with an unsupported or future conclusion, or none at all | `vector:INT-UNKNOWN-03` |
| INT-UNKNOWN-04 | a newest positively NOT_EXECUTED revision keeps the accepted fallback | `vector:INT-UNKNOWN-04` |
| INT-UNKNOWN-05 | a newest positively NON_VERIFY_TERMINAL revision keeps the accepted fallback | `vector:INT-UNKNOWN-05` |
| INT-UNKNOWN-06 | a newest UNKNOWN over failure-bearing history stays UNKNOWN and the failure is not erased | `vector:INT-UNKNOWN-06` |
| partial series | a required revision series that is PARTIAL is UNKNOWN with no band, its counts visible (PV-REV-TEST-003) | `test_partial_revision_series_is_unknown_with_its_evidence_preserved` |
| sample strength | one to three decisive revisions are SPARSE with `CI_SPARSE_SAMPLE`; four are ESTABLISHED | `test_sparse_samples_declare_their_strength_and_established_ones_do_not_carry_the_diagnostic` |
| unresolved newest revision | over every history, a newest revision still being verified yields FAILING exactly where the established FAILING predicate already holds and no band elsewhere; the superset this rule version first carried, which could omit the band it emitted, is gone (#12 finding 3, PV-INTEGRITY-TOTALITY-001) | `test_an_unresolved_newest_revision_never_emits_a_band_its_history_does_not_already_prove`, `test_current_unresolved_is_unknown_unless_failing_is_already_established`, `test_a_newest_revision_with_one_workflow_passed_and_one_running_is_already_counted_and_still_unresolved` |
| verdict vocabulary | a current verdict outside the canonical vocabulary is read as UNKNOWN, never as a non-decisive state an older pass speaks for | `test_a_verdict_outside_the_vocabulary_fails_closed_instead_of_falling_back_to_an_older_pass` |
| record consistency | a record whose contribution contradicts its own history state, or that names no revision, is a defect, not a pass | `test_a_record_whose_contribution_contradicts_its_history_is_a_defect_not_a_pass`, `test_a_record_without_its_revision_identity_is_a_defect_not_a_crash` |
| unusable series | an unusable required series is UNKNOWN even beside a positive `ci.configured = false` (precedence A of PV-INTEGRITY-TOTALITY-001) | `test_an_unusable_series_is_unknown_even_beside_a_positive_not_configured` |

## Integrity: durable revision history (PV-HIST-002)

Rule `integrity.bands.v1+ci-unit-004+hist-002`, adopted in 0.2.0 (target B3).
The reconciliation cases state the carried history as the observation a build
adds (`ci.revision_history_carried`) and are vectors; the cases about the
chain, which bundle is the source and what a lost one means, need a history
store and are tests.

| Case | Meaning | Test |
| --- | --- | --- |
| HIST-01 | a revision a prior bundle proved failing stays FAILURE_OBSERVED when the provider now shows the same revision passing; the current verdict is PASS | `vector:HIST-01` |
| HIST-02 | a revision the prior bundle recorded PASS_ONLY_OBSERVED becomes FAILURE_OBSERVED when a failure of it is newly observed, and stays there | `vector:HIST-02` |
| HIST-03 | a prior failure plus any number of same-revision retries that passed is one failed contribution, whatever the number or order of the retries | `vector:HIST-03` |
| HIST-04 | a failed revision and a newer passing revision are two samples while both are in the window | `vector:HIST-04` |
| HIST-05 | a failure the provider no longer exposes stays historical evidence while its revision is in the window | `vector:HIST-05` |
| HIST-06 | without durable history a parent-level pass cannot prove the earlier attempts: UNKNOWN_HISTORY, no favorable PASS_ONLY reconstruction | `vector:HIST-06`, `test_parent_level_provenance_is_diagnosed_and_a_favorable_one_is_unknown_history` |
| HIST-07 | complete attempt-level current evidence with no unresolved prior gap proves PASS_ONLY_OBSERVED | `vector:HIST-07` |
| HIST-08 | a required predecessor that is missing or unverifiable is a HISTORY_GAP: nothing is carried through it | `test_hist_20_and_hist_08_a_lost_predecessor_is_a_gap_and_nothing_older_is_carried` |
| HIST-09 | the same failure in durable history and in the current enumeration is one failed contribution, never two | `vector:HIST-09` |
| HIST-10 | a revision whose durable failure has aged beyond the 14-day window no longer contributes | `vector:HIST-10` |
| HIST-11 | equivalent failure histories on the Actions and the check-suite surfaces, in any enumeration order, give the identical record and result | `vector:HIST-11` |
| HIST-12 | an unrelated rule or configuration change keeps the durable Integrity history | `test_hist_12_an_unrelated_vital_rule_change_keeps_the_durable_history` |
| HIST-13 | carried history of the older lineage is replayed from the attempts it kept, never copied from the state it derived: its failure stays, its parent-level pass is unknown | `vector:HIST-13`, `test_hist_13_the_first_bundle_after_an_older_version_replays_its_revision_records` |
| HIST-14 | a history-semantics change with an accepted deterministic migration records the migration | not executable: no migration has been accepted, so the mechanism accepts none and a foreign lineage takes the HIST-15 path |
| HIST-15 | carried history of a lineage with neither replay nor an accepted migration leaves the revisions it names unknown, until complete current evidence repairs them | `vector:HIST-15` |
| HIST-16 | a prior bundle's current verdict is never inherited: the revision the provider no longer shows keeps its history and speaks for nothing current | `vector:HIST-16` |
| HIST-17 | the same current observation over different durable histories is different canonical evidence and a different bundle | `test_hist_17_different_durable_history_is_different_canonical_evidence` |
| HIST-18 | history of another immutable project at the same locator is never carried | `test_hist_18_another_project_at_the_same_locator_is_never_carried` |
| HIST-19 | a prior UNKNOWN_HISTORY does not heal because the provider now shows a pass that is complete only for what is visible | `vector:HIST-19`, `test_hist_19_complete_evidence_repairs_an_unknown_history` (the nearby repair) |
| HIST-20 | B1 pass, B2 same-revision failure, B3 pass again: B3 carries from B2 and keeps the failure; with B2 lost it is a gap, never a fallback to B1 | `test_hist_20_the_immediate_predecessor_carries_a_failure_an_older_bundle_did_not_see`, `test_hist_20_and_hist_08_a_lost_predecessor_is_a_gap_and_nothing_older_is_carried` |
| parent-level failure | an observed failure is proven on any surface; only favorable parent-level evidence is unknown | `test_a_parent_level_failure_is_still_a_proven_failure` |
| continuity | the history crosses a bundle whose verification evidence was unusable | `test_the_durable_history_crosses_a_bundle_whose_verification_evidence_was_unusable` |
| source is the predecessor | a build refuses observations that carry history from another bundle, leaves the caller's set untouched, and `verify` names a source that is not the previous bundle | `test_a_build_refuses_observations_that_carry_history_from_another_predecessor`, `test_a_build_leaves_the_callers_observation_set_as_it_was`, `test_verify_names_carried_history_that_is_not_from_the_previous_bundle`, `test_every_stored_bundle_verifies_with_its_carried_history` |
| corrupt carried history | carried history that is not its lineage's shape fails closed | `test_carried_history_that_is_not_its_lineages_shape_fails_closed` |

## Integrity: totality (PV-INTEGRITY-TOTALITY-001)

Accepted by `PV-REV-INT-TOTALITY-001` and adopted in 0.1.9 under the same
unreleased rule `integrity.bands.v1+ci-unit-004`. The cases are transcribed
from the contract's Required conformance cases section.

| Case | Meaning | Test |
| --- | --- | --- |
| INT-TOTAL-01 | configured, newest unresolved, no decisive history: UNKNOWN with no band, never NO_DECISIVE_RUNS | `vector:INT-TOTAL-01` |
| INT-TOTAL-02 | two passes and a newest unresolved revision: UNKNOWN, never SPARSE through an older pass | `vector:INT-TOTAL-02` |
| INT-TOTAL-03 | one pass, one failure, newest unresolved: UNKNOWN, neither SPARSE_MIXED nor FAILING | `vector:INT-TOTAL-03` |
| INT-TOTAL-04 | four passes, newest unresolved: UNKNOWN, never CLEAN | `vector:INT-TOTAL-04` |
| INT-TOTAL-05 | five decisive, one failure, newest unresolved: UNKNOWN, never FLAKY | `vector:INT-TOTAL-05` |
| INT-TOTAL-06 | four decisive, one failure (the established FAILING predicate), newest unresolved: DEGRADED / FAILING / EXACT, no `possible_bands` | `vector:INT-TOTAL-06` |
| INT-TOTAL-07 | the same region under RAW_RUNS is PROVISIONAL_NONINDEPENDENT | not materialized: this implementation has no RAW_RUNS sample path (issue #23) |
| INT-TOTAL-08 | not configured, no decisive evidence, one NOT_EXECUTED record: UNINSTRUMENTED with `CI_UNINSTRUMENTED_WITH_RECENT_NONDECISIVE_HISTORY` | `vector:INT-TOTAL-08` |
| INT-TOTAL-09 | the same with one NON_VERIFY_TERMINAL record | `vector:INT-TOTAL-09` |
| INT-TOTAL-10 | configured with only non-decisive records stays NO_DECISIVE_RUNS | `vector:INT-TOTAL-10` |
| INT-TOTAL-11 | a newest UNKNOWN stays UNKNOWN over any history, an established FAILING one included | `vector:INT-TOTAL-11` |
| INT-TOTAL-12 | a PARTIAL required series stays UNKNOWN whatever it holds | `vector:INT-TOTAL-12` |
| INT-TOTAL-13 | a failure followed by a re-run in progress keeps its contribution in every enumeration order | `vector:INT-TOTAL-13` |
| INT-TOTAL-14 | equivalent GitHub and GitLab evidence give one result | not materialized: there is no GitLab adapter yet (target C1, issue #34) |

## Clutter: incomplete evidence (PV-CLUTTER-INCOMPLETE-001, PV-ISSUE-026-RECONCILE-001)

Rule `clutter.bands.v1`, adopted in 0.1.9. The twenty cases of the accepted
contract, transcribed from its `Required conformance fixtures` section; the
ranges a case names (6..19, 1..5) are stated as variants under the one
identifier. Cases 13 to 16 are the accepted answer to issue #26.

| Case | Meaning | Test |
| --- | --- | --- |
| CLU-INCOMPLETE-01 | an unavailable issue inventory cannot manufacture CLEAN | `vector:CLU-INCOMPLETE-01` |
| CLU-INCOMPLETE-02 | an unavailable issue inventory with one confirmed stale change request is a LIGHT lower bound | `vector:CLU-INCOMPLETE-02` |
| CLU-INCOMPLETE-03 | an absolute stale-work count of five proves CLUTTERED while the ratio over an unavailable denominator proves nothing | `vector:CLU-INCOMPLETE-03` |
| CLU-INCOMPLETE-04 | an absolute stale-work count of twenty-five is HEAVY and exact | `vector:CLU-INCOMPLETE-04` |
| CLU-INCOMPLETE-05 | an unavailable branch inventory cannot manufacture CLEAN | `vector:CLU-INCOMPLETE-05` |
| CLU-INCOMPLETE-06 | an unavailable branch inventory above a complete LIGHT core is a LIGHT lower bound | `vector:CLU-INCOMPLETE-06` |
| CLU-INCOMPLETE-07 | a complete issue and change-request ratio domain is admissible proof when only the branch inventory is unavailable | `vector:CLU-INCOMPLETE-07` |
| CLU-INCOMPLETE-08 | a ratio-only trigger is not proof when the issue denominator is unavailable | `vector:CLU-INCOMPLETE-08` |
| CLU-INCOMPLETE-09 | partial required change-request evidence with twenty-five observed stale items forces HEAVY | `vector:CLU-INCOMPLETE-09` |
| CLU-INCOMPLETE-10 | partial change-request evidence with five observed stale items proves a CLUTTERED floor | `vector:CLU-INCOMPLETE-10` |
| CLU-INCOMPLETE-11 | a partial denominator cannot elevate a ratio-only threshold | `vector:CLU-INCOMPLETE-11` |
| CLU-INCOMPLETE-12 | a partial zero subset remains UNKNOWN | `vector:CLU-INCOMPLETE-12` |
| CLU-INCOMPLETE-13 | a partial classified branch subset of twenty forces HEAVY | `vector:CLU-INCOMPLETE-13` |
| CLU-INCOMPLETE-14 | a partial classified branch subset of six to nineteen proves a CLUTTERED floor | `vector:CLU-INCOMPLETE-14` |
| CLU-INCOMPLETE-15 | a partial classified branch subset of one to five proves a LIGHT floor | `vector:CLU-INCOMPLETE-15` |
| CLU-INCOMPLETE-16 | a partial classified branch zero subset remains UNKNOWN | `vector:CLU-INCOMPLETE-16` |
| CLU-INCOMPLETE-17 | an unavailable issue component beside twenty unclassified branches is two-sided uncertainty and stays UNKNOWN | `vector:CLU-INCOMPLETE-17` |
| CLU-INCOMPLETE-18 | an independent positive core floor survives unclassified branch ambiguity | `vector:CLU-INCOMPLETE-18` |
| CLU-INCOMPLETE-19 | the complete UNCLASSIFIED upper-bound path of T7 is preserved | `vector:CLU-INCOMPLETE-19` |
| CLU-INCOMPLETE-20 | provider naming, enumeration order and pagination metadata cannot enter the classification | `vector:CLU-INCOMPLETE-20`, `test_clu_incomplete_20_provider_and_order_invariance_is_exact_over_the_whole_result` |
| undeclared retention | a partial branch count whose retention semantics are undeclared or unclassified proves no floor; declared but unreadable semantics fail closed (#26) | `test_clutter_partial_branch_count_without_classified_retention_is_unknown`, `test_clutter_partial_branch_count_that_is_unclassified_proves_nothing`, `test_clutter_declared_but_unreadable_retention_semantics_fail_closed` |
| partial without a value | a PARTIAL count that carries no observed subset is unresolved, not a lower bound | `test_clutter_partial_count_without_a_value_is_unresolved_not_a_subset` |
| CLU-PARTIAL-TRUST-01 | a PARTIAL stale-work count whose coverage proves an observed subset contributes its observed count (PV-REV-PR-031-003) | `test_clu_partial_trust_01_a_proven_subset_of_stale_work_contributes_its_observed_count` |
| CLU-PARTIAL-TRUST-02 | a proven PARTIAL stale-branch count with fresh CLASSIFIED retention contributes its observed count | `test_clu_partial_trust_02_a_proven_subset_of_branches_with_classified_retention_contributes` |
| CLU-PARTIAL-TRUST-03 | a value-bearing PARTIAL count without subset proof cannot establish a floor | `test_clu_partial_trust_03_a_partial_count_without_subset_proof_cannot_establish_a_floor` |
| CLU-PARTIAL-TRUST-04 | coverage that describes an estimate, an aggregate or any non-subset value cannot establish a floor | `test_clu_partial_trust_04_coverage_that_describes_a_non_subset_cannot_establish_a_floor` |
| CLU-PARTIAL-TRUST-05 | malformed or self-contradicting coverage, or a value that is not a count, fails closed as a diagnosed unresolved component, never an exception | `test_clu_partial_trust_05_malformed_or_contradictory_coverage_fails_closed_without_an_exception` |
| CLU-PARTIAL-TRUST-06 | an untrusted member is not counted beside trusted ones, and the higher-precedence missing-required rule is unchanged | `test_clu_partial_trust_06_an_untrusted_member_is_not_counted_beside_trusted_ones` |
| CLU-PARTIAL-TRUST-07 | a count derived from a capped enumeration carries its proof, and the saved and reloaded evidence reaches the same decision | `test_clu_partial_trust_07_derived_and_saved_evidence_reach_the_same_decision`, `test_a_derived_count_proves_its_subset_only_when_partial_and_only_as_a_count` |
| CLU-PARTIAL-TRUST-08 | complete AVAILABLE/FRESH evidence and the optional UNAVAILABLE path are unchanged | `test_clu_partial_trust_08_complete_and_optional_unavailable_evidence_are_unchanged` |
| invariant band under unclassified branches | when the work items alone reach the band the full unclassified count reaches, the band is DEGRADED and EXACT (section 5 of the contract) | `test_clutter_unclassified_branches_that_the_work_items_already_reach_are_an_invariant_band` |

## Direction: state-neutral and incomplete linkage (PV-REV-DIRECTION-CLOSED-TARGET-001, PV-DIRECTION-INCOMPLETE-001)

Rule `direction.bands.v2`, adopted in 0.2.0 as one Direction rule version for
both repairs. The cases are transcribed from the judgement's and the
contract's required fixtures. A case about how one change request's evidence
becomes LINKED, UNLINKED or UNRESOLVED states the change-request and target
inventories and runs the derivation (`given.derive`); a case about the
completion rule states N, L, U and R. PV-REV-DIRECTION-INCOMPLETE-001 narrowed
DIR-CLOSED-04's "unlinked or unresolved": a positively missing target is
UNLINKED (DIR-CLOSED-04, DIR-INCOMPLETE-07), an unresolvable one UNRESOLVED
(DIR-INCOMPLETE-08, -09).

| Case | Meaning | Test |
| --- | --- | --- |
| DIR-CLOSED-01 | an active change request with an explicit link to an open target is linked | `vector:DIR-CLOSED-01` |
| DIR-CLOSED-02 | the same change request and target id stay linked when the target moves from open to closed; the linkage share is unchanged | `vector:DIR-CLOSED-02`, `test_change_request_aggregates` |
| DIR-CLOSED-03 | a link to a closed target is linked when the target identity resolves authoritatively | `vector:DIR-CLOSED-03`, `test_a_closed_register_target_is_still_a_resolved_reference` |
| DIR-CLOSED-04 | a reference to a target the complete register positively lacks is unlinked with the missing-reference diagnostic; linkage is never fabricated | `vector:DIR-CLOSED-04` |
| DIR-CLOSED-05 | closing a target cannot by itself worsen the Direction band | `vector:DIR-CLOSED-05` |
| DIR-CLOSED-06 | reopening a target cannot by itself improve the Direction band | `vector:DIR-CLOSED-06` |
| DIR-CLOSED-07 | Horizon's open-target counts still exclude the closed target a change request stays linked to, so the two Vitals may diverge | `vector:DIR-CLOSED-07` |
| DIR-CLOSED-08 | every active change request linked to one closed target is FULLY_LINKED with the single-target diagnostic: traceability, not alignment | `vector:DIR-CLOSED-08` |
| DIR-CLOSED-09 | adopting the repair changes the Direction rule id: the first comparison across it is INCOMPARABLE for Direction alone, while an unaffected Vital still compares | `vector:DIR-CLOSED-09` |

| Case | Meaning | Test |
| --- | --- | --- |
| DIR-INCOMPLETE-01 | N=5, L=0, U=3, R=2: every completion k in {0,1,2} is SCATTERED | `vector:DIR-INCOMPLETE-01` |
| DIR-INCOMPLETE-02 | N=5, L=3, U=1, R=1: every completion k in {3,4} is MIXED | `vector:DIR-INCOMPLETE-02` |
| DIR-INCOMPLETE-03 | N=4, L=2, U=0, R=2: completions reach MIXED and FULLY_LINKED, so no band | `vector:DIR-INCOMPLETE-03` |
| DIR-INCOMPLETE-04 | N=5, L=1, U=1, R=3: completions reach SCATTERED and MIXED, so no band | `vector:DIR-INCOMPLETE-04` |
| DIR-INCOMPLETE-05 | N=1, L=0, U=0, R=1: completions reach SCATTERED and FULLY_LINKED; never DEGRADED FULLY_LINKED | `vector:DIR-INCOMPLETE-05` |
| DIR-INCOMPLETE-06 | a marker to an authoritatively resolved closed target is LINKED; closing or reopening the target alone does not change the linkage | `vector:DIR-INCOMPLETE-06` |
| DIR-INCOMPLETE-07 | a marker to T that a complete authoritative lookup proves absent is UNLINKED: N=1, L=0, U=1, R=0 is exactly SCATTERED with the missing-reference diagnostic | `vector:DIR-INCOMPLETE-07`, `test_a_reference_the_complete_register_lacks_is_missing_and_one_the_register_could_not_answer_is_unknown` |
| DIR-INCOMPLETE-08 | a marker to T while the target list is PARTIAL and T is not in the observed subset, with no direct lookup, is UNRESOLVED: no band | `vector:DIR-INCOMPLETE-08` |
| DIR-INCOMPLETE-09 | a marker whose target resolution is unavailable, forbidden, unknown, errored or stale is UNRESOLVED, never LINKED by fallback | `vector:DIR-INCOMPLETE-09`, `test_unreadable_linkage_evidence_is_unresolved_not_unlinked_and_not_a_failed_project`, `test_a_milestone_without_a_number_is_unresolved_linkage_not_a_failed_project` |
| DIR-INCOMPLETE-10 | a PARTIAL global target enumeration does not degrade Direction when every referenced target is resolved on its own | `vector:DIR-INCOMPLETE-10` |
| DIR-INCOMPLETE-11 | partial link evidence leaves two change requests unresolved, but N/L/U/R forces SCATTERED for every completion | `vector:DIR-INCOMPLETE-11` |
| DIR-INCOMPLETE-12 | partial link evidence admits MIXED and FULLY_LINKED, so no band | `vector:DIR-INCOMPLETE-12` |
| DIR-INCOMPLETE-13 | linkage capability that is neither positively present nor absent is UNKNOWN with no band | `vector:DIR-INCOMPLETE-13` |
| DIR-INCOMPLETE-14 | an active-change inventory that is PARTIAL leaves N unproven: UNKNOWN with no band | `vector:DIR-INCOMPLETE-14` |
| DIR-INCOMPLETE-15 | reversed and reshuffled enumeration, page boundaries, marker order and target order leave L/U/R, the reachable bands, the status, the band and the diagnostics unchanged | `vector:DIR-INCOMPLETE-15` |
| DIR-INCOMPLETE-16 | several active change requests all linked to one authoritatively resolved closed target, with complete evidence, are exactly FULLY_LINKED: neutral, no concentration threshold | `vector:DIR-INCOMPLETE-16` |
| readable link dominates | a resolved reference links a change request even when another of its linkage fields is unreadable | `test_a_readable_link_is_not_undone_by_an_unreadable_field` |
| contradictory counts | `L + U + R != N` is refused before classification, and the command line reports it as an input error | `vector:HOR-PARTIAL-15` (the Horizon analogue), `test_observations_whose_counts_contradict_each_other_are_an_input_error` |

## Target marker syntax (PV-AUDIT-TARGET-MARKER-SYNTAX-001)

The audit's regressions `LINK-MARKER-01..08` reached this repository only as
the categories its handoff names; the tests below cover each category and do
not claim the individual case texts.

| Category | Meaning | Test |
| --- | --- | --- |
| exact marker | a standalone marker links, at the start of the text, after a newline, a space, a tab or punctuation | `test_an_exact_marker_links_wherever_it_stands_alone` |
| embedded prefix | `NotTarget:`, `SubTarget:`, `PreTarget:` and any marker glued to a preceding word character link nothing | `test_a_marker_embedded_in_a_larger_token_links_nothing`, `test_a_marker_ending_in_a_word_character_needs_a_boundary_after_it_too` |
| custom marker | a configured marker replaces the default and is matched exactly | `test_a_custom_marker_replaces_the_default_and_is_matched_exactly` |
| multiple markers | several markers keep their order and link each target once | `test_several_markers_keep_their_order_and_link_each_target_once` |
| prose without the marker | a lowercase, pluralised or paraphrased marker links nothing | `test_prose_without_the_configured_marker_links_nothing` |
| end to end | under file planning only the standalone marker becomes a reference, and Direction counts only it | `test_embedded_markers_do_not_link_end_to_end` |

## Horizon: partial enumeration (PV-HORIZON-PARTIAL-001)

Rule `horizon.bands.v2`, adopted in 0.2.0. The sixteen cases of the accepted
contract, stated as target inventories and derived, so the counts, their
observed-subset proof and the capability a returned target proves are executed
where they are made. HOR-PARTIAL-15 states the contradictory counts directly
and expects their refusal (`expect.rejected`).

| Case | Meaning | Test |
| --- | --- | --- |
| HOR-PARTIAL-01 | capability present, complete and fresh, zero open targets: exactly UNDECLARED (the positive-zero control) | `vector:HOR-PARTIAL-01` |
| HOR-PARTIAL-02 | complete and fresh, one open target with no future boundary: exactly DECLARED | `vector:HOR-PARTIAL-02` |
| HOR-PARTIAL-03 | complete and fresh, an open target exactly 28 days out and none later: exactly VISIBLE; the frame is unchanged | `vector:HOR-PARTIAL-03` |
| HOR-PARTIAL-04 | complete and fresh, an open target strictly beyond 28 days: exactly EXTENDED | `vector:HOR-PARTIAL-04` |
| HOR-PARTIAL-05 | explicit targets positively unsupported and no planning register configured: exactly UNDECLARED, a descriptive state, not missing evidence | `vector:HOR-PARTIAL-05` |
| HOR-PARTIAL-06 | capability unknown, forbidden, errored, stale, unavailable or an unresolved partial: UNKNOWN, never UNDECLARED by default | `vector:HOR-PARTIAL-06` |
| HOR-PARTIAL-07 | PH0: a partial enumeration returned no open target, so every band is reachable: UNKNOWN, never UNDECLARED | `vector:HOR-PARTIAL-07` |
| HOR-PARTIAL-08 | PH1: returned open targets without a future boundary reach DECLARED, VISIBLE and EXTENDED: UNKNOWN, DECLARED is never a representative | `vector:HOR-PARTIAL-08` |
| HOR-PARTIAL-09 | PH2: a returned open target within or exactly at 28 days reaches VISIBLE and EXTENDED: UNKNOWN, VISIBLE is never a bound | `vector:HOR-PARTIAL-09` |
| HOR-PARTIAL-10 | PH3: a returned open target strictly beyond 28 days forces EXTENDED in every completion: DEGRADED / EXTENDED / EXACT | `vector:HOR-PARTIAL-10` |
| HOR-PARTIAL-11 | a returned closed target beyond 28 days and an open target without a boundary: the closed one forces nothing, PH1, UNKNOWN | `vector:HOR-PARTIAL-11` |
| HOR-PARTIAL-12 | only closed returned targets, one beyond 28 days: PH0, UNKNOWN, never UNDECLARED or EXTENDED | `vector:HOR-PARTIAL-12` |
| HOR-PARTIAL-13 | the same PH3 evidence in reversed order, other page boundaries and an equivalent provider-neutral record shape: identical DEGRADED / EXTENDED / EXACT | `vector:HOR-PARTIAL-13` |
| HOR-PARTIAL-14 | the same PH2 subset under record and page permutations: identical UNKNOWN, pagination order cannot manufacture exactness | `vector:HOR-PARTIAL-14` |
| HOR-PARTIAL-15 | a derived tuple no target population can produce (beyond above future, future above open) fails validation before evaluation, never UNKNOWN or DEGRADED compensation | `vector:HOR-PARTIAL-15` |
| HOR-PARTIAL-16 | PH3 is the direct proof: whatever else the returned subset holds, and whatever the omitted records are, the observed open target beyond 28 days keeps every completion EXTENDED | `vector:HOR-PARTIAL-16` |

## Debt: partial register (PV-DEBT-PARTIAL-001)

Rule `debt.bands.v2`, adopted in 0.2.0 together with the observed-subset proof
issue #39 asked Debt to require: a PARTIAL open count is a lower bound only
when its coverage says so.

| Case | Meaning | Test |
| --- | --- | --- |
| DEBT-PARTIAL-01 | a partial enumeration with no confirmed open item cannot manufacture CLEAR | `vector:DEBT-PARTIAL-01` |
| DEBT-PARTIAL-02 | a returned subset of closed debt items only is still not CLEAR: the closed count is a diagnostic, omitted open items stay possible | `vector:DEBT-PARTIAL-02` |
| DEBT-PARTIAL-03 | one confirmed open item forces PRESENT: DEGRADED / PRESENT / EXACT with the partial receipt retained | `vector:DEBT-PARTIAL-03` |
| DEBT-PARTIAL-04 | thirty-seven confirmed open items remain PRESENT, never ACCUMULATED or any quantitative severity | `vector:DEBT-PARTIAL-04` |
| DEBT-PARTIAL-05 | the size of the omitted tail cannot erase a confirmed open item: two different partial receipts give the same band | `vector:DEBT-PARTIAL-05` |
| DEBT-PARTIAL-06 | provider naming, item order, page order and page boundaries do not change the normalized result | `vector:DEBT-PARTIAL-06` |
| DEBT-PARTIAL-07 | positively absent debt authority stays exactly UNINSTRUMENTED; the repair does not turn positive absence into UNKNOWN | `vector:DEBT-PARTIAL-07` |
| DEBT-PARTIAL-08 | uncertain mapping authority is never inferred from a partial payload that happens to hold an apparent open debt record | `vector:DEBT-PARTIAL-08` |
| DEBT-PARTIAL-09 | a complete, fresh positive zero remains exactly CLEAR | `vector:DEBT-PARTIAL-09` |
| DEBT-PARTIAL-10 | a complete, fresh positive open count remains exactly PRESENT | `vector:DEBT-PARTIAL-10` |
| DEBT-PARTIAL-11 | a partial zero stays UNKNOWN beside one hundred closed items: closed history cannot prove current open emptiness | `vector:DEBT-PARTIAL-11` |
| DEBT-PARTIAL-12 | a forced PRESENT under partial acquisition stays visibly DEGRADED, never AVAILABLE, with the acquisition machine-visible | `vector:DEBT-PARTIAL-12` |
| DEBT-PARTIAL-13 | a stale positive count is not a confirmed current open item: UNKNOWN, as before the repair | `vector:DEBT-PARTIAL-13` |
| DEBT-PARTIAL-14 | one confirmed current open item survives other returned or tail records that stay unresolved under the partial receipt | `vector:DEBT-PARTIAL-14` |
| DEBT-PARTIAL-15 | a versioned project-local quantitative policy does not replace the canonical core under partial positive evidence | `vector:DEBT-PARTIAL-15` |
| DEBT-PARTIAL-16 | a project-local policy cannot turn a partial zero into any canonical conclusion | `vector:DEBT-PARTIAL-16` |
| subset proof | a PARTIAL open count whose coverage is missing, not a subset, an estimate, contradictory or malformed is no lower bound, and Debt is UNKNOWN (issue #39) | `test_a_partial_debt_count_without_the_subset_proof_is_not_a_lower_bound` |
| PD1 in the tests | a confirmed open item under partial acquisition is DEGRADED / PRESENT / EXACT, a stale one proves nothing | `test_partial_register_with_observed_items_is_degraded_present`, `test_a_stale_partial_register_proves_nothing_about_now` |

## T9: the decision-equivalence reconciliation (PV-TEST-004, PV-T9-GEN-003)

`PV-REV-TEST-004` accepted the final T9 reconciliation with zero
`CONTRACT_GAP` terminals: each of the nine gap identifiers of `PV-T9-GEN-002`
maps to one deterministic accepted obligation. 0.2.0 adopts the last of the
repairs those obligations come from, so the implementation side of T9 is a
finite generator over the acquisition tokens and the regions each family
names, which evaluates every cell and holds it to the accepted table
(`tests/conformance/test_t9_reconciliation.py`, about 1,270 cells). The T9v2
cell-key serialization itself is the research process's to deliver as
vectors.

| Gap identifier | Accepted obligation | Test |
| --- | --- | --- |
| T9-GAP-HORIZON-PARTIAL-BOUND-001 | PH0..PH2 `UNKNOWN`, PH3 `DEGRADED / EXTENDED / EXACT` (PV-HORIZON-PARTIAL-001) | `test_t9_gap_horizon_partial_bound_001` |
| T9-GAP-CLUTTER-UNAVAILABLE-COMPONENT-001, T9-GAP-CLUTTER-PARTIAL-FORCED-BOUND-001 | a confirmed floor from positive facts only, never `CLEAN` under incomplete coverage (PV-CLUTTER-INCOMPLETE-001) | `test_t9_gap_clutter_unavailable_component_and_partial_forced_bound` |
| T9-GAP-DIRECTION-PARTIAL-LINKAGE-001 | the completion set over k in L..L+R (PV-DIRECTION-INCOMPLETE-001) | `test_t9_gap_direction_partial_linkage_001` |
| T9-GAP-DIRECTION-UNRESOLVED-TARGET-001 | resolved identity LINKED open or closed, positive absence UNLINKED, the rest UNRESOLVED | `test_t9_gap_direction_unresolved_target_001` |
| T9-GAP-INTEGRITY-UNRESOLVED-BAND-001 | `DEGRADED / FAILING / EXACT` only over an established FAILING history, else `UNKNOWN` (PV-INTEGRITY-TOTALITY-001) | `test_t9_gap_integrity_unresolved_band_001` |
| T9-GAP-INTEGRITY-PARTIAL-SUPERSET-001 | the false gap: a PARTIAL required series is `UNKNOWN`, no `possible_bands` (PV-REV-TEST-003) | `test_t9_gap_integrity_partial_superset_001` |
| T9-GAP-INTEGRITY-UNCONFIGURED-RECENT-001 | `UNINSTRUMENTED` with the non-decisive history kept visible | `test_t9_gap_integrity_unconfigured_recent_001` |
| T9-GAP-DEBT-PARTIAL-BOUND-001 | confirmed open `DEGRADED / PRESENT / EXACT`, none confirmed `UNKNOWN` (PV-DEBT-PARTIAL-001) | `test_t9_gap_debt_partial_bound_001` |
| section 4 precedence | unknown history outranks every conservative branch | `test_t9_section_4_unknown_history_outranks_the_unresolved_failing_branch` |
| finiteness | nine identifiers, none without cells | `test_t9_generator_covers_every_family` |

## Activity coverage (PV-REV-ACTIVITY-COVERAGE-001)

Reading 3 of issue #9, accepted: the interval stays the full canonical gap and
a shortfall of evidence is disclosed with the exact earliest evidence
timestamp. Executable as `activity` vectors.

| Case | Meaning | Test |
| --- | --- | --- |
| ACT-COV-01 | full-gap interval within the evidence window: no shortfall note | `vector:ACT-COV-01` |
| ACT-COV-02 | full-gap interval wider than the window: canonical bounds unchanged, note with the exact `evidence_from` | `vector:ACT-COV-02` |
| ACT-COV-03 | a 97-day gap with 28 days of evidence and one revision states one observed revision with the shortfall, never one revision across 97 days | `vector:ACT-COV-03` |
| ACT-COV-04 | BASELINE reports the observation window and never a historical overrun | `vector:ACT-COV-04` |
| ACT-COV-05 | a capped enumeration and an interval shortfall are both disclosed | `vector:ACT-COV-05` |

## Seven-Vital taxonomy (PV-VIT-010, PV-VIT-012)

| Case | Meaning | Test |
| --- | --- | --- |
| V1-01 | empty repository with complete observations | `test_v1_01_empty_repository_with_complete_observations` |
| V1-02 | commits without change requests or targets | `test_v1_02_commits_without_change_requests_or_targets` |
| V1-03 to V1-04 | linkage bands | `test_direction_bands` |
| V1-05 | forbidden planning enumeration is UNKNOWN | `test_v1_05_forbidden_planning_enumeration_is_unknown_not_undeclared` |
| V1-06 | clear Debt with heavy Clutter | `test_v1_06_clear_debt_can_coexist_with_heavy_clutter` |
| V1-07 | mapping change makes history incomparable | `test_art_04_rpt_10_semantic_config_change_is_incomparable` |
| V1-08 | fail then rerun pass | `test_r54_...` |
| V1-10 | unavailable channel never becomes zero | `test_v1_10_unavailable_channel_never_becomes_zero_but_lower_bound_still_classifies` |
| V1-11 | branch enumeration unavailable cannot emit exact CLEAN (since `clutter.bands.v1` it emits no band at all, CLU-INCOMPLETE-05) | `test_v1_11_branch_enumeration_unavailable_cannot_emit_exact_clean`, `test_clutter_issues_disabled_with_no_observed_residue_is_unknown_not_clean`, `test_clutter_issues_disabled_with_observed_residue_is_a_lower_bound` |
| V1-12 | dependency metadata, no aggregate | `test_v1_12_snapshot_carries_dependency_metadata_and_no_aggregate` |
| V1-13 | no calibrated Debt policy | `test_v1_13_no_calibrated_policy_keeps_large_debt_as_present` |
| V1-14 | mass-linking yields neutral FULLY_LINKED | `test_v1_14_mass_linking_yields_neutral_fully_linked_with_diagnostic` |
| V1-15 | provider and order invariance | `test_r57_order_and_surface_invariance`, `test_g4_same_observations_produce_identical_snapshot_digest` |

## Calibration repairs (PV-CAL-002, PV-CAL-003)

| Case | Meaning | Test |
| --- | --- | --- |
| FLOW-EQ-01 | empty queue with a slow historical median is NO_QUEUE | `test_flow_eq_01_empty_queue_with_slow_historical_median_is_no_queue` |
| FLOW-EQ-02 | an extreme historical median cannot gridlock an empty queue | `test_flow_eq_02_extreme_historical_median_cannot_gridlock_an_empty_queue` |
| FLOW-EQ-03 | a live queue keeps the > 168 h predicate | `test_flow_eq_03_live_queue_keeps_the_congested_median_threshold` |
| FLOW-EQ-04 | a live large queue keeps the gridlocked predicate | `test_flow_eq_04_live_large_queue_keeps_the_gridlocked_predicate` |
| FLOW-EQ-05 | a missing open count never becomes an empty queue | `test_flow_eq_05_missing_open_count_never_becomes_an_empty_queue` |
| FLOW-EQ-06 | provider and order invariance | `test_flow_eq_06_provider_and_order_invariance` |
| FLOW-PREC-01 | sub-hour medians are preserved | `test_flow_prec_01_sub_hour_medians_are_preserved` |
| FLOW-PREC-02 | an even sample uses the exact arithmetic mean | `test_flow_prec_02_even_sample_uses_the_exact_arithmetic_mean` |
| FLOW-PREC-03 / 04 | 604800 s is not > 168 h, 604801 s is | `test_flow_prec_03_04_lower_boundary_is_exact_in_seconds` |
| FLOW-PREC-05 | 1209600 s is not > 336 h, 1209601 s is | `test_flow_prec_05_upper_boundary_is_exact_in_seconds` |
| FLOW-PREC-06 | empty queue takes precedence over any median | `test_flow_prec_06_empty_queue_takes_precedence_over_any_median` |
| FLOW-PREC-07 | the median is invariant under permutation | `test_flow_prec_07_median_is_invariant_under_permutation` |
| FLOW-PREC-08 | fractional timestamps stay exact | `test_flow_prec_08_fractional_timestamps_are_exact` |
| FLOW-PREC-09 | partial evidence stays UNKNOWN | `test_flow_prec_09_partial_evidence_stays_unknown` |
| PULSE-CAP-01 | invariant lower bound forces one band | `test_pulse_cap_01_invariant_lower_bound_forces_one_band`, `test_pulse_cap_01_exact_days_with_capped_commits_is_forced_quiet` |
| PULSE-CAP-02 | a reachable boundary lists every reachable band, no exact band | `test_pulse_cap_02_boundary_crossing_lists_every_reachable_band_and_no_exact_band` |
| PULSE-CAP-03 | an unconstrained required tail is UNKNOWN | `test_pulse_cap_03_unconstrained_required_tail_is_unknown` |
| PULSE-CAP-04 | optional channels cannot make a capped required input exact | `test_pulse_cap_04_optional_channel_cannot_make_capped_required_input_exact` |
| PULSE-CAP-05 | pagination metadata is non-semantic | `test_pulse_cap_05_pagination_metadata_is_non_semantic` |
| CI-OUTCOME-01 | timed_out is VERIFY_FAIL | `test_ci_outcome_01_timed_out_is_a_verification_failure` |
| CI-OUTCOME-02 | startup_failure is UNKNOWN | `test_ci_outcome_02_startup_failure_is_unknown_not_a_project_failure` |
| CI-OUTCOME-03 | a non-completed status outranks any conclusion | `test_ci_outcome_03_current_execution_state_outranks_a_conclusion` |
| CI-OUTCOME-04 | unknown conclusions fail closed | `test_ci_outcome_04_unknown_future_conclusions_fail_closed` |

## Gauges and demand (PV-REV-GAUGE-001, PV-ROLE-001)

| Case | Meaning | Test |
| --- | --- | --- |
| GAUGE-J1 | UNKNOWN or not-applicable Vital has value null | `test_unknown_and_not_applicable_states_have_no_value` |
| GAUGE-J2 | a DEGRADED bound carries a qualifier, never exact | `test_degraded_results_carry_a_bound_qualifier` |
| GAUGE-J3 | within a band the gauge never decreases with the phenomenon | `test_gauges_are_monotone_inside_a_band` |
| GAUGE-J4 | gauges of different Vitals are never ranked together | `test_role_01_same_level_gauge_invariance` |
| GAUGE-J5 | no aggregate over gauges | `test_demand_rows_and_attention_order` (`aggregate` is null) |
| GAUGE-J6 | constants or semantics change only with a new identifier | by construction: `devostasis.gauge.v1` is frozen in `gauges.py` |
| GAUGE-J7 | gauges.json is reproducible and identity-bound | `test_every_band_lands_inside_its_declared_range`, `test_art_20_21_12_persisted_bundle_verifies_from_its_own_contents` |
| ROLE-01 | same level, only gauges change, order unchanged | `test_role_01_same_level_gauge_invariance` |
| ROLE-02 | a Vital without a band is UNRESOLVED and sorts first | `test_unknown_vital_is_unresolved_and_first` |
| ROLE-03 | aggregate stays null | `test_demand_rows_and_attention_order` |
| ROLE-04 | overrides require a mapping version and valid values | `test_demand_overrides_require_a_mapping_version_and_valid_values` |

## Artifact and history (PV-ARTIFACT-001..005, PV-REPORT-001)

| Case | Meaning | Test |
| --- | --- | --- |
| ART-01 / RPT-1 | baseline without fabricated delta | `test_art_01_first_bundle_is_baseline_without_fabricated_delta` |
| ART-02 / ART-14 | repeatability and cross-implementation identity | `test_art_02_and_art_14_identity_is_reproducible_across_builds` |
| ART-03 / RPT-3 | history gap | `test_rpt_3_history_gap_keeps_current_snapshot_and_infers_no_change` |
| ART-04 / RPT-10 | semantic boundary is INCOMPARABLE | `test_art_04_rpt_10_semantic_config_change_is_incomparable` |
| ART-06 | neutral rendering | `test_art_06_neutral_rendering_of_fully_linked_and_present` |
| ART-07 | immutability | `test_art_07_immutability` |
| ART-12 | renderer purity | `test_art_20_21_12_persisted_bundle_verifies_from_its_own_contents`, CLI `test_build_verify_render_and_index` |
| ART-13 / ART-22 | acyclic identity | `test_art_13_and_art_22_preimage_excludes_post_identity_members` |
| ART-16 | observed_at is identity-bearing | `test_art_16_observed_at_is_identity_bearing` |
| ART-17 | effective config collision | `test_art_17_config_change_changes_bundle_id`, `test_art_17_byte_affecting_option_changes_the_digest` |
| ART-18 | optional member identity | `test_art_18_enabled_html_without_renderer_fails_closed`, `test_art_18_optional_member_presence_is_identity_bearing` |
| ART-19 | config canonicalization invariance | `test_art_19_*` |
| ART-20 / ART-21 | persisted effective config preimage | `test_art_20_21_12_persisted_bundle_verifies_from_its_own_contents` |
| ART-23 | member profile derived from the stored config | `test_art_23_member_profile_derives_from_the_stored_config` |
| ART-24 | replay only from a validated stored config | `test_art_24_replay_happens_only_from_a_validated_stored_config` |
| ART-25 | stored config schema verification | `test_art_25_stored_config_is_schema_validated_before_any_semantic_use`, `test_legacy_effective_config_v1_is_still_verifiable` |
| RPT-2 | interval from previous successful bundle | `test_second_run_is_comparable_with_unchanged_and_ordered_transitions` |
| RPT-7 | rename and transfer continuity by immutable project id | `test_rpt_7_a_renamed_repository_keeps_one_history`, `test_a_transfer_to_another_owner_is_the_same_event`, `test_an_old_name_reused_by_a_new_repository_is_a_new_project`, `test_a_locator_held_by_another_project_fails_closed`, `test_without_an_immutable_id_the_locator_is_the_identity` |
| rule boundary | a Vital with a changed rule id is INCOMPARABLE on its own | `test_rule_version_boundary_makes_one_vital_incomparable_inside_a_comparable_bundle` |
| CONFIG_IDENTITY_UNCLASSIFIED | unknown config fails closed | `test_unclassified_configuration_input_fails_closed` |
| non-monotonic observation | an observation not later than the previous bundle is INCOMPARABLE (`NON_MONOTONIC_OBSERVATION`) and claims no direction; activity never runs backwards (#17) | `test_an_older_observation_is_incomparable_and_claims_no_direction`, `test_an_observation_at_the_same_instant_is_on_the_same_side_of_the_boundary`, `test_activity_refuses_an_interval_that_ends_before_it_starts` |
| immutable authority | the comparison reads the immutable bundle the index names; a compacted or damaged `latest/` is not a history gap, a divergent one is reported (#28) | `test_the_comparison_reads_the_immutable_bundle_and_survives_a_compacted_latest_copy`, `test_a_damaged_latest_copy_is_not_a_history_gap_but_a_divergent_one_is`, `test_without_an_index_the_newest_immutable_bundle_is_found_by_scanning` |
| metadata binding | `semantic_config` is the projection of the stored config; every identity field the manifest repeats agrees with the preimage; the receipt and the evidence hash to what the identity names; a manifest of the wrong shape is a problem, not an exception (#12 finding 4) | `test_a_manifest_semantic_config_that_is_not_the_projection_of_the_stored_config_fails_verification`, `test_every_identity_field_the_manifest_repeats_must_agree_with_the_preimage`, `test_the_receipt_and_the_evidence_are_bound_to_the_identity`, `test_a_manifest_of_the_wrong_shape_is_a_verification_problem_not_an_exception` |
| receipt configuration | a build over observations derived under another effective configuration is refused (#27) | `test_build_refuses_observations_collected_under_another_configuration` |
| check-suite coverage | a sampled, failed or capped check-suite surface is PARTIAL with its coverage recorded, at the 100/101 revision and suite boundaries; collected failures are kept (#12 finding 1) | `test_the_hundred_and_first_revision_makes_the_suite_sample_partial`, `test_an_access_failure_after_four_revisions_makes_the_sample_partial_and_keeps_what_was_seen`, `test_a_second_page_of_suites_is_read_and_a_capped_page_count_is_partial`, `test_a_spent_budget_makes_the_suite_sample_partial` |

## Store, transport and decoder boundaries (research audits, 2026-09-20 to 2026-09-24)

Implementation-local labels: the audits define regression boundaries, not
permanent research case identifiers, and none of these rows claims one.

| Case | Meaning | Test |
| --- | --- | --- |
| index tail containment | the tail is followed only along the canonical history path of the bundle it names, inside this project's tree; an escaping, absolute or mislabelled path is a gap, never a comparison (review of #28's repair) | `test_a_tail_path_that_escapes_the_history_tree_is_a_history_gap_never_a_comparison`, `test_an_absolute_tail_path_is_refused`, `test_a_tail_whose_basename_is_not_its_bundle_id_is_refused` |
| project identity binding | the bundle the tail names must carry this project's identity, or its locator for a store without identities | `test_another_projects_bundle_inside_the_history_tree_is_refused_by_identity`, `test_without_identities_the_locator_binds_the_bundle`, `test_an_honest_store_still_verifies_and_compares` |
| malformed index | an index of the wrong shape is a gap and is never appended to | `test_an_index_of_the_wrong_shape_is_a_history_gap_and_is_never_appended_to` |
| identity field presence | every identity field the manifest repeats is present in both copies and equal; the exact stored lineage decides which fields are required and which renderers a bundle may name; deleting the manifest `renderer_version` no longer skips the report replay silently (PV-AUDIT-MANIFEST-PREIMAGE-BINDING-001) | `test_a_duplicated_identity_field_deleted_from_either_copy_fails_verification`, `test_deleting_the_renderer_version_no_longer_skips_the_report_replay_silently`, `test_an_unknown_lineage_or_a_renderer_outside_its_lineage_fails_verification`, `test_the_lineage_table_carries_the_lineage_and_renderer_this_version_writes` |
| preimage shape | the preimage has exactly its lineage's field set; a deleted `source_receipts_digest` no longer switches the receipt binding off (review of 2026-09-30) | `test_a_preimage_field_added_or_removed_is_an_unsupported_shape` |
| hashed members | a member the identity hashes, deleted together with its manifest entry, fails instead of stopping the replay (review of 2026-09-30) | `test_a_hashed_member_deleted_with_its_entry_no_longer_verifies` |
| adapter provenance | the `adapters` line the report prints is the provider and collector the identity binds (review of 2026-09-30) | `test_the_adapters_the_report_names_are_bound_to_the_identity` |
| honest verify | `verify` claims report reproducibility only for a report it replayed; an earlier renderer's report is bound by its digest and said to be (review of 2026-09-30) | `test_verify_does_not_claim_a_replay_it_did_not_perform` |
| identity lookup fails closed | an unreadable index elsewhere in the store makes the immutable-id lookup fail rather than pass for absence (PV-AUDIT-HISTORYSTORE-001) | `test_an_unreadable_index_elsewhere_makes_the_identity_lookup_fail_closed` |
| FLEET-COV | an unreadable or malformed project index, or a present but unreadable demand member, stops the fleet surfaces instead of dropping the project; an absent demand member stays the legacy null case (PV-AUDIT-FLEET-INDEX-001, PV-AUDIT-FLEET-COVERAGE-001) | `test_a_corrupt_project_index_stops_the_fleet_surfaces_instead_of_dropping_the_project`, `test_a_single_corrupt_project_is_a_failure_not_an_empty_store`, `test_a_present_but_unreadable_demand_member_is_not_a_pre_demand_bundle`, `test_an_absent_demand_member_is_a_pre_demand_bundle_and_an_unreadable_one_is_a_failure`, `test_the_run_command_reports_a_fleet_surface_failure_as_a_store_error` |
| HISTORY-PUBLISH | the index is replaced, never truncated; a failure between the index and the copy leaves a stale copy that is recovered, not a gap; a copy of an unknown bundle is still refused (PV-AUDIT-HISTORYSTORE-ATOMIC-PUBLICATION-001) | `test_the_index_is_replaced_never_truncated`, `test_a_stale_copy_left_by_an_interrupted_publication_is_recovered_not_a_gap`, `test_leftovers_of_an_interrupted_latest_publication_are_cleared_by_the_next`, `test_a_copy_of_a_bundle_the_index_does_not_know_is_still_refused` |
| STORE-ID-BIND | a wrapper whose bundle id or project key disagrees with its manifest is refused before any write (PV-AUDIT-STORE-BUNDLE-PATH-BINDING-001, PV-AUDIT-STORE-PROJECT-BINDING-001) | `test_a_wrapper_that_disagrees_with_its_manifest_is_refused_before_anything_is_written` |
| store path containment | a key that is not a `<forge>/<owner>/<repo>` triple of name characters derives no store path, and the configuration admits only such names (PV-AUDIT-STORE-PATH-001) | `test_a_key_that_is_not_a_locator_derives_no_store_path`, `test_a_locator_stays_beneath_the_store`, `test_a_configured_repo_that_is_not_a_locator_is_rejected` |
| LOCATOR-ALIAS | two spellings of one repository are one project in the configuration and in the run (PV-AUDIT-PROJECT-LOCATOR-ALIAS-001) | `test_case_variants_of_one_locator_are_one_configured_project`, `test_two_locators_the_provider_resolves_to_one_repository_are_observed_once`, `test_run_project_refuses_the_second_locator_of_one_repository_before_writing` |
| CONFIG-SHAPE | `activity.enabled` and `store` of the wrong type are rejected, not coerced (PV-AUDIT-CONFIG-SHAPE-001) | `test_configuration_of_the_wrong_shape_is_rejected_not_coerced` |
| GH-*-PAYLOAD | a malformed successful row of any inventory is `ERROR / UNEXPECTED_PAYLOAD` for that inventory alone; the repository metadata bootstrap fails the project explicitly; a head detail that cannot be read leaves the head unresolved; a check-suite answer of the wrong shape is a failure, not zero suites (PV-AUDIT-GITHUB-REPO/COMMITS/CR/ISSUES/BRANCH/RELEASE/CI-PAYLOAD-001) | `test_a_malformed_successful_row_is_a_declared_failure_of_that_inventory_alone`, `test_repository_metadata_that_does_not_establish_the_routing_facts_is_a_declared_collection_failure`, `test_a_malformed_repository_in_a_fleet_run_costs_one_outcome_and_the_next_project_still_runs`, `test_a_head_detail_that_cannot_be_read_leaves_the_head_unresolved_not_the_inventory_failed`, `test_a_check_suite_answer_of_the_wrong_shape_is_a_declared_failure_not_zero_suites`, `test_a_valid_draft_release_without_a_date_is_ignored_and_valid_rows_keep_their_order`, `test_an_unreadable_commit_inventory_leaves_verification_unknown_not_uninstrumented`, `test_a_malformed_workflows_answer_is_a_declared_failure_not_an_invented_count` |
| REG-STATE | the register state vocabulary is closed; a state outside it is `INVALID_REGISTER`, never an open item (PV-AUDIT-REGISTER-STATE-001) | `test_reg_state_01_02_the_documented_vocabulary_is_read`, `test_reg_state_03_04_06_07_a_state_outside_the_vocabulary_is_an_invalid_register_not_an_open_item`, `test_reg_state_05_08_the_collectors_turn_an_invalid_state_into_error_invalid_register` |
| GH-RETRY-HEADER | an unreadable wait hint is no hint; the bounded backoff applies and the answer's own classification stands (PV-AUDIT-GITHUB-RETRY-HEADER-001) | `test_gh_retry_header_01_03_an_unreadable_wait_hint_is_no_hint`, `test_gh_retry_header_04_06_a_malformed_hint_takes_the_bounded_backoff_and_ends_in_the_declared_status` |
| GH-REDIRECT-AUTH | a redirect off the API origin is refused and the credential never leaves; same-origin redirects still work (PV-AUDIT-GITHUB-REDIRECT-AUTH-001) | `test_gh_redirect_auth_a_redirect_to_another_origin_is_refused_and_the_token_never_leaves`, `test_gh_redirect_auth_a_same_origin_redirect_is_followed_with_the_credential`, `test_gh_redirect_auth_the_origin_is_the_configured_api_base`, `test_gh_redirect_auth_a_refused_redirect_is_a_declared_transport_failure` |
| GH-CACHE-INTEGRITY | a cache entry is replayed only when complete and still hashing to its digest; anything else is a miss and one refetch (PV-AUDIT-GITHUB-CACHE-INTEGRITY-001) | `test_gh_cache_integrity_01_02_05_unreadable_metadata_is_a_miss_never_an_exception`, `test_gh_cache_integrity_03_07_a_body_that_no_longer_hashes_to_its_digest_is_not_replayed`, `test_gh_cache_integrity_04_06_a_304_over_an_invalid_entry_refetches_once_and_a_valid_one_replays` |
| CANON-NONFINITE / DECIMAL / JSON-PARSER / UNICODE | the canonical decoder rejects non-finite constants, decimal and exponent numbers, duplicate members and unpaired surrogates; integers of any size and valid Unicode survive (PV-AUDIT-CANONICAL-*-001) | `test_canon_nonfinite_and_decimal_tokens_reject_at_the_decoder`, `test_canon_decimal_07_integers_of_any_size_stay_integers`, `test_canon_json_parser_a_member_named_twice_is_rejected_not_collapsed`, `test_canon_unicode_01_04_an_unpaired_surrogate_is_rejected`, `test_canon_unicode_05_08_a_valid_pair_and_ordinary_unicode_survive`, `test_canon_unicode_06_07_a_direct_surrogate_value_or_key_is_a_canonicalization_error_not_a_unicode_error` |

## Vitals and vectors (review of 2026-09-30)

Implementation-local labels, as above.

| Case | Meaning | Test |
| --- | --- | --- |
| Pulse over 29 dates | a capped enumeration over all 29 UTC dates the 28-day window touches is evaluated, not a crash | `test_a_capped_enumeration_over_all_29_dates_the_window_touches_is_evaluated_not_a_crash` |
| Pulse completions | every band an admissible completion reaches is in `possible_bands`, the QUIET threshold included | `test_every_band_a_completion_reaches_is_in_the_possible_set` |
| Debt freshness | a stale or freshness-unknown partial register is UNKNOWN, never a PRESENT lower bound | `test_a_stale_partial_register_proves_nothing_about_now` |
| vacuous expectations | an expectation that states nothing (an empty object or list, an empty code) is refused; an exactly compared empty `metric_deltas` is still a statement | `test_an_expectation_that_states_nothing_is_refused`, `test_an_exactly_empty_metric_delta_is_still_a_statement` |
| schema conditional | every envelope of the corpus satisfies the published schema's value conditional as JSON Schema evaluates it | `test_every_envelope_satisfies_the_schemas_value_conditional` |
| rule ids documented | every Vital `rule_id` the code declares is in vitals.md | `test_every_vital_rule_id_the_code_declares_is_documented` |

## Store and command line (review of 2026-09-30)

Implementation-local labels, as above.

| Case | Meaning | Test |
| --- | --- | --- |
| index-less scan | without an index, an unreadable or mislabelled bundle directory is a gap, never a comparison against an older bundle and never a baseline; an interrupted write is not a candidate | `test_without_an_index_an_unreadable_newest_bundle_is_a_gap_not_a_comparison_with_an_older_one`, `test_without_an_index_a_single_unreadable_bundle_is_a_gap_not_a_baseline`, `test_an_interrupted_write_is_not_a_candidate` |
| project index location | a repository named `index.json` is a project, not an index | `test_a_repository_named_index_json_does_not_break_the_store` |
| reproducible gap reasons | the reasons of a HISTORY_GAP carry no absolute path or exception message; the same damage is one bundle id wherever the store lives | `test_history_gap_reasons_do_not_depend_on_where_the_store_is_checked_out` |
| fleet surfaces | both fleet surfaces are replaced, never truncated | `test_the_fleet_surfaces_are_replaced_never_truncated` |
| reporting | a fleet-surface failure comes after every project's result in `run` and after the committed bundle in `build`; a cache that cannot be saved is a warning; a missing or unreadable input is an input error (exit 2), not a traceback | `test_run_reports_every_project_before_a_fleet_surface_error`, `test_a_cache_that_cannot_be_saved_is_a_warning_not_the_end_of_the_run`, `test_build_reports_the_committed_bundle_before_a_fleet_surface_error`, `test_a_missing_or_unreadable_input_is_an_input_error_not_a_traceback` |

## Collection completeness (review of 2026-09-30)

Implementation-local labels, as above.

| Case | Meaning | Test |
| --- | --- | --- |
| runs search ceiling | a workflow-runs listing that ends short of the provider's `total_count` (the 1,000-result search ceiling) is PARTIAL; a `total_count` that is not a count is a declared failure | `test_a_runs_listing_that_ends_short_of_the_providers_total_is_partial`, `test_a_total_count_that_is_not_a_count_is_a_declared_failure` |
| shifted listing | a listing that repeats a commit or a run between pages counts it once and is PARTIAL with `LISTING_SHIFTED` | `test_a_commit_listing_that_repeats_a_commit_between_pages_counts_it_once_and_is_partial`, `test_a_runs_listing_that_repeats_a_run_is_partial_and_the_run_counts_once` |
| unexamined revision | a revision whose first check-suite page the budget refused is not examined, and `ci.configured` is not a false nobody observed | `test_a_revision_the_budget_refused_is_not_examined_and_configured_is_not_a_false_nobody_observed` |
| transport failures | `http.client` failures are network failures; an unreadable error body keeps its status; a body nested past the decoder's depth is `MALFORMED_RESPONSE` | `test_http_client_failures_are_network_failures`, `test_an_error_body_that_cannot_be_read_keeps_the_status`, `test_a_body_nested_past_the_decoder_depth_is_a_malformed_response` |
| out-of-range instants and registers | an instant outside the representable range is a `ValueError`; a register file with non-string content, no size, invalid base64, excessive nesting or more bytes than the bound is a declared failure | `test_an_out_of_range_instant_is_a_value_error_not_an_overflow`, `test_a_malformed_register_file_is_a_declared_failure_not_an_exception` |
| parent fields typed | a run or suite field the parent record carries into the bundle is typed, so a number there is `UNEXPECTED_PAYLOAD`, not a lost bundle | `test_an_untyped_run_field_is_a_declared_payload_failure_not_a_lost_bundle`, `test_an_untyped_suite_url_is_a_declared_payload_failure` |

## Band ordering (PV-BAND-ORDER-001)

The fifteen cases the accepted contract requires, under the names it gives
them, executable as vectors. A case that names several pairs executes all of
them and passes only when every pair does, so a result citing `ORDER-nn` is a
result about research case `ORDER-nn` and nothing else. The claims that no pair
of bands can express are beside them in `tests/conformance/test_band_order.py`.

| Case | Meaning | Test |
| --- | --- | --- |
| ORDER-01 | `CLUTTER_TRANSITIVE_IMPROVEMENT`: HEAVY→LIGHT is IMPROVED, the reverse WORSENED | `vector:ORDER-01` |
| ORDER-02 | `FLOW_LIVE_QUEUE_ORDER`: GRIDLOCKED→CONGESTED→MOVING follows the WORSENED/IMPROVED direction | `vector:ORDER-02` |
| ORDER-03 | `FLOW_NO_QUEUE_INCOMPARABLE`: NO_QUEUE against MOVING and against GRIDLOCKED is CHANGED | `vector:ORDER-03` |
| ORDER-04 | `INTEGRITY_ESTABLISHED_CHAIN`: FAILING→FLAKY→CLEAN improving, the reverse worsening | `vector:ORDER-04` |
| ORDER-05 | `INTEGRITY_SPARSE_CHAIN`: SPARSE_MIXED→SPARSE is IMPROVED, the reverse WORSENED | `vector:ORDER-05` |
| ORDER-06 | `INTEGRITY_CROSS_FAMILY`: SPARSE→CLEAN, SPARSE_MIXED→FAILING and NO_RECENT_RUNS→CLEAN are CHANGED | `vector:ORDER-06` |
| ORDER-07 | `PULSE_NEUTRALITY`: every unequal Pulse band pair is CHANGED | `vector:ORDER-07` |
| ORDER-08 | `HORIZON_NEUTRALITY`: every unequal Horizon band pair is CHANGED | `vector:ORDER-08` |
| ORDER-09 | `DIRECTION_NEUTRALITY`: SCATTERED→FULLY_LINKED is CHANGED, and so is the reverse | `vector:ORDER-09` |
| ORDER-10 | `DEBT_NEUTRALITY`: PRESENT against CLEAR is CHANGED | `vector:ORDER-10` |
| ORDER-11 | `DEGRADED_NEVER_ORDERED`: a DEGRADED evaluation on either side emits no direction | `vector:ORDER-11` |
| ORDER-12 | `UNKNOWN_OBSERVABILITY_PRECEDENCE`: an appearing or disappearing band uses the observability transitions | `vector:ORDER-12` |
| ORDER-13 | `RULE_VERSION_BOUNDARY_PRECEDENCE`: a changed rule id stays INCOMPARABLE inside a declared chain | `vector:ORDER-13` |
| ORDER-14 | `GAUGE_INVARIANCE`: a gauge that moved inside unchanged bands stays UNCHANGED | `vector:ORDER-14`, `test_a_gauge_that_moved_inside_one_band_is_not_a_direction` |
| ORDER-15 | `CROSS_VITAL_PROHIBITION`: no rank of one Vital is compared with a rank of another | `vector:ORDER-15`, `test_no_order_is_declared_across_vitals`, `test_the_delta_declares_the_ordering_contract_it_applied_and_no_aggregate` |

Two of the accepted cases are half structural. ORDER-14 states that *changing
only a gauge* leaves the classification alone: a vector states bands and
derived metrics, so it proves that the delta ignores the moved metric, and the
pytest case beside it computes the gauge and proves it actually moved. ORDER-15
states that a comparator does not exist, which no pair of bands can express;
the vector proves that two Vitals moving in opposite directions are classified
independently and that a band two Vitals share is not ordered by the other
one's chain, and the pytest cases prove the absence itself.

Beyond the accepted set, this implementation keeps three cases of its own. They
carry `DEV-ORDER` identifiers, which are local to this repository and belong to
no research unit, so a result citing one can never be read as evidence about an
accepted case.

| Case | Meaning | Test |
| --- | --- | --- |
| DEV-ORDER-01 | Clutter improves one adjacent rank, not only across the transitive step ORDER-01 states | `vector:DEV-ORDER-01` |
| DEV-ORDER-02 | Clutter improves across the whole chain, HEAVY→CLEAN | `vector:DEV-ORDER-02` |
| DEV-ORDER-03 | NO_QUEUE is incomparable with CONGESTED too, the band between the two ORDER-03 names | `vector:DEV-ORDER-03` |
| ordering needs a comparable pair | a BASELINE, HISTORY_GAP or INCOMPARABLE comparison reports no direction | `test_a_bundle_that_is_not_comparable_never_reports_a_direction` |
| gauges establish no order | a gauge that moved inside a band is UNCHANGED | `test_a_gauge_that_moved_inside_one_band_is_not_a_direction` |
| ordered bands are emittable | every ordered band is one its Vital emits, and the unordered ones are exactly the descriptive and evidence states | `test_every_ordered_band_is_a_band_its_vital_can_emit`, `test_the_bands_left_unordered_are_exactly_the_descriptive_and_evidence_states` |

## Carried-history admission (implementation regressions)

These regressions enforce the accepted predecessor and immutable-revision
requirements without assigning new research case identifiers.

| Boundary | Meaning | Test |
| --- | --- | --- |
| carrier content | edited records, attempts, lineage or provenance cannot replace the verified predecessor's history, even with its correct bundle id | `test_a_build_refuses_changed_history_even_when_it_names_the_right_predecessor` |
| exact rebuild | an unchanged admitted carrier reproduces all bundle members and keeps the recorded failure | `test_a_build_accepts_an_unchanged_carrier_and_reproduces_the_same_bundle` |
| duplicate revision | neither current nor replayable carried lineage can overwrite a failure with a second record for the same revision | `test_duplicate_carried_revisions_cannot_overwrite_a_recorded_failure` |

## The vector runner (target B1)

| Case | Meaning | Test |
| --- | --- | --- |
| runner | a wrong expectation fails, a correct one passes | `test_a_wrong_expectation_fails_and_says_what_it_expected`, `test_a_correct_vector_passes` |
| fail closed | an unknown kind, key, vital, comparison status or duplicate case id is an error, never a skip | `test_a_vector_that_cannot_run_is_rejected_at_load_time`, `test_a_comparison_status_the_engine_does_not_know_is_rejected`, `test_two_files_may_not_claim_the_same_case_id`, `test_a_missing_path_is_an_error_not_an_empty_run` |
| evidence is contract-checked | an envelope that violates the observation contract fails the vector | `test_an_envelope_that_violates_the_observation_contract_is_a_failure_not_a_pass` |
| published schema | the schema and the validator agree on the shape, including the partial evidence envelope and the comparison statuses | `test_the_published_vector_schema_and_the_runner_agree_on_the_shape`, `test_the_schema_publishes_the_partial_envelope_the_runner_actually_accepts`, `test_every_envelope_in_the_corpus_is_one_the_published_schema_accepts` |
| corpus | every vector in the corpus runs, and every declared kind is exercised | `test_conformance_vector`, `test_every_kind_the_format_declares_is_exercised_by_the_corpus` |
| variants | one case over several evidence shapes passes only when every shape does, and a failure names the shape | `test_variants_hold_every_evidence_shape_to_the_one_expectation` |
| ci kind | provider-native outcomes are normalized before Integrity sees them; a provider without a normalization is rejected | `test_the_ci_kind_normalizes_provider_native_outcomes_before_integrity_sees_them` |
| derive | a vital case over inventories runs the derivation first, under the two settings it reads, and no others | `test_derive_runs_the_derivation_before_the_vital_is_evaluated`, `test_derive_names_only_the_settings_the_derivation_reads` |
| rejected | a case expecting refused evidence passes only when the evaluation raises with that code, and the refusal is its whole expectation | `test_a_rejected_case_passes_only_when_the_evidence_is_refused_with_that_code`, `test_rejected_is_the_whole_expectation_and_names_a_code` |
| activity kind | the interval and the coverage notes of the activity member are checked | `test_the_activity_kind_checks_the_interval_and_the_coverage_it_discloses` |

Cases not yet implemented as tests (T3, T6, T8, R5..R53, ART-05,
ART-08..ART-11, ART-15, RPT-4..RPT-6, RPT-9) are listed in the ROADMAP under the
synthetic fixture suite; T9 is implemented by its generator since 0.2.0, and
its cell-key vectors are still the research process's to deliver. The research process delivers them as executable JSON
vectors in the format of [vectors.md](vectors.md), one accepted family per
unit; the ones accepted so far (T2, R1, R2, R3, R4, T4, T5, T7) are in the
corpus above, and so are the twenty cases of `PV-CLUTTER-INCOMPLETE-001`,
transcribed from the accepted contract the way `ORDER-01..15` were. The `ci` kind reaches the normalization boundary R5..R10 are
about, so that family can be materialized against it (issue #20); `variants`
and the dependency-group assertions close the T8 and part of the T6 gap of
issue #23, while T3 and the bundle and store cases still need a surface this
version does not publish.

## Companion regression evidence (implementation-owned)

These DEV-WORK families exercise `devostasis.work.v1`; they do not replace
the outstanding research cases above or claim acceptance of a Vital rule.

| Family | Proof |
| --- | --- |
| queues and identity | `test_work_five_queues_and_bounded_acceptance`, `test_work_determinism_ids_and_explicit_priority` |
| exact-head admission | `test_work_merge_admission_matrix`, `test_work_missing_cannot_admit_merge`, `test_work_stale_verdict_dismissal_and_self_review` |
| source and producer gaps | `test_work_report_profiles`, `test_work_malformed_and_unavailable_reports_are_not_zero`, `test_work_report_wrong_repo_and_revision`, `test_work_gitlab_missing_capabilities_are_explicit` |
| bounded handoff | `test_work_cursor_exhaustive_binding_and_expiry`, `test_work_selected_refresh_does_not_discover_whole_repository`, `test_work_cli_offline_end_to_end_and_recheck` |
| durable replay | `test_work_bundle_replay_and_forged_rehashed_projection_rejected`, `test_work_store_backfill_candidate_rename_and_latest_binding`, `test_work_store_lock_and_failed_pointer_write_preserve_history` |
| transport | `test_work_redirect_cannot_forward_credentials`, `test_work_transport_refuses_mutation`, `test_work_conditional_304_replays_body_without_credential_crossing` |
