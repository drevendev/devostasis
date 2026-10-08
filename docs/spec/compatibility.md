# Exact contract compatibility

`devostasis.contract-compatibility.v1` implements accepted PV-COMPAT-001/002
and PV-REV-COMPAT-002. Tokens are opaque exact strings. The complete required
lineage tuple is admitted; individually known components do not authorize a
new combination. `src/devostasis/lineages.py` records supported historical and
successor bundle tuples. Existing effective-config and artifact validators
validate source bytes before report replay; unknown tokens and mixed tuples fail.

The `devostasis.compatibility.Registry` API validates the source under its
exact registered historical validator before identity dispatch or projection.
Exact source/target identity wins before an edge policy can shadow it.
Nonidentity compatibility requires an explicitly registered edge, named
deterministic precondition/projection algorithms, exact source/target tuples,
finite operation set, unknown-field policy, semantic-invariance and comparison
flags, and canonical identity effect NONE. READ never implies COMPARE;
direction, transitivity and semantic-successor compatibility are not inferred.

There are **no accepted production nonidentity edges or migrations**.
Test-only edges illustrate the machinery; they do not authorize converting
stored bundles or comparing changed Vital/Instrument rules. Existing per-Vital
rule boundaries continue to make only the affected Vital incomparable.

`devostasis.compatibility-dispatch-policy.v1` pins a finite eligible-edge set
through immutable policy id, version and canonical digest. Its only selection
rule is `EXACT_UNIQUE_OR_AMBIGUOUS.v1`. Edge order does not matter. Every named
edge must exist at its exact identity; missing/colliding registry entries fail.
Only literal true preconditions admit candidates. Zero candidates means
NO_DECLARED_COMPATIBILITY; more than one means AMBIGUOUS_COMPATIBILITY_EDGE,
even when their output bytes would be equal.

Successful dispatch returns source/target/result lineages, operation, exact
policy reference, selected edge and result. `Registry.replay(record, source)`
validates the source and resolves that recorded policy and edge again, checks
uniqueness, applies the pinned projection and target validator, and checks the
entire result/provenance record. Registry growth outside the recorded policy
cannot change replay. Missing historical policy never falls back to current.

Migration is a separate accepted operation creating new bytes/identity while
preserving its source. This release declares none. Release support/EOL policy,
PyPI publishing and Instrument semantics are separate owner decisions.

Proof: `tests/test_compatibility.py` covers source-before-projection validation,
exact opaque tokens, mixed tuples, operation/direction/transitivity boundaries,
identity collisions, fail-closed preconditions, COMPAT-21 replay pinning and
COMPAT-22 ambiguity. Bundle lineage regressions supplement it in
`tests/test_receipt_identity.py` and `tests/test_bundle_history.py`. These tests
do not claim all still-undelivered Phase B vector families are complete.
