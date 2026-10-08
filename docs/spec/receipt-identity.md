# Canonical receipt identity in 0.4.0

Accepted PV-RECEIPT-IDENTITY-001/002/003, independently accepted by
PV-REV-RECEIPT-IDENTITY-003, define the cumulative `PV-BUNDLE-ID-003` repair.
The implementation uses `PV-RECEIPT-IDENTITY-003` to name that cumulative
receipt projection. No Vital, threshold, comparison rule or demand mapping changes.

The exact successor tuple is `devostasis.bundle.v3`,
`devostasis.manifest.v2`, `devostasis.receipt-identity.v1`,
`devostasis.observations.v2`, `devostasis.render.v5`. New bundles bind these
tokens in their identity preimage. `source_receipts_digest` hashes the complete
canonical `manifest.receipt_identity`, which is required even with observations
disabled. Enabled observations carry the exact same projection. Verification
checks its closed schema and digest, copy equality and complete lineage;
it needs no provider, execution receipt or ambient current policy.

Material fields: semantic collector version, target/scope provenance,
requested and returned keys, per-key status/freshness, material capability
notes, per-key coverage and acquisition config hash. Missing, UNKNOWN,
PARTIAL, forbidden, stale and positively observed zero remain distinct.
Capability notes are material labels; operational prose belongs in diagnostics.
`observed_at` and observation `collected_at` retain their evidence meanings.

Run id, start/end times, counters, retries, cache behavior, diagnostics and tool
build version live in `devostasis.execution-receipt.v1`, outside the canonical
bundle. Python callers receive `Bundle.execution_receipt` and
`RunOutcome.execution_receipt`. CLI observe writes an adjacent
`<observations>.execution-receipt.json`; build/run write operational receipts
under `<store>/executions/`. They are not declared members, renderer inputs
or authority for Vitals. There is no operational retention contract yet.

The same canonical evidence and identity metadata, including `observed_at`,
produce the same id and byte-identical complete required member set, including
manifest and report. Different genuine observation times intentionally move
identity. HistoryStore exact-byte collision checks are preserved. Duplicate
payloads use its ordinary idempotent put; differing canonical bytes remain an error.

Historical v1/v2 bundle identities, full receipt v1/v2, observations v1 and
manifest v1 remain immutable and verify under their recorded preimages.
Frozen public examples live in `examples/legacy/`. Mixed old/new tuples fail
closed. Renderer v4 and v5 replay use the same presentation function, with
receipt provenance selected by the admitted schema. Earlier renderer replay
remains tracked in issue #46; digest verification does not claim it replayed.

Permanent cases RECEIPT-ID-01..15 and 17..21 are exercised in
`tests/test_receipt_identity.py`. RECEIPT-ID-16 retains its rejected historical
meaning and is not reassigned. Optional observations never remove the only
durable receipt preimage.
