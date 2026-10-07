# Bundle

0.4.0 writes `devostasis.bundle.v3` / `PV-BUNDLE-ID-003` with manifest v2,
observations v2 and the canonical receipt-identity projection. The complete
successor definition and execution boundary are in
[receipt-identity.md](receipt-identity.md); exact source-version admission is
in [compatibility.md](compatibility.md). Required canonical bytes are invariant
under changes to invocation mechanics. Historical members are never rewritten.

The v2 / PV-BUNDLE-ID-002 definition below remains the historical verifier
contract. Common member, config, digest and acyclicity rules also apply to v3,
with the explicitly versioned receipt/manifest changes above.

One successful canonical run of one project produces one immutable bundle.

## Members

| Member | Canonical | In identity | Content |
| --- | --- | --- | --- |
| `snapshot.json` | yes | digest | seven Vitals (authoritative) |
| `delta.json` | yes | digest | comparison with the previous bundle |
| `gauges.json` | yes | digest | 0-100 normalization of every band ([gauges.md](gauges.md)) |
| `demand.json` | yes | digest | demand levels and attention order ([demand.md](demand.md)) |
| `activity.json` | optional | digest or `ACTIVITY_DISABLED` | normalized activity in the interval |
| `observations.json` | optional | digest or `OBSERVATIONS_MEMBER_DISABLED` | every observation and the receipt |
| `effective-config.json` | yes | digest | the exact canonical effective config (B3 repair); the semantic authority of the bundle (B4) |
| `report.md` | yes | no (post-identity) | deterministic rendering under the persisted `display` configuration |
| `report.html` | optional | presence (through the effective config) | not rendered in this version; enabling it fails closed |
| `manifest.json` | yes | no (post-identity) | versions, identity preimage, member profile, member digests, receipt |

## Member schema identifiers

Every canonical member names its own schema in its first field, so a consumer
can tell what it is holding without inferring it from the file name:

| Member | `schema` |
| --- | --- |
| `snapshot.json` | `devostasis.snapshot.v1` |
| `delta.json` | `devostasis.delta.v2` (v1 in bundles written before 0.1.8) |
| `activity.json` | `devostasis.activity.v1` |
| `observations.json` | `devostasis.observations.v1`, with a receipt of `devostasis.receipt.v2` |
| `gauges.json` | `devostasis.gauges.v1` |
| `demand.json` | `devostasis.demand.v2` |
| `effective-config.json` | `devostasis.effective-config.v2` |
| `manifest.json` | `devostasis.manifest.v1` |

The store adds two documents that are not bundle members and carry their own
identifiers: a project's chronological index (`devostasis.index.v1`) and the
fleet index (`devostasis.fleet.v1`, see
[history-and-reports.md](history-and-reports.md)).

## Canonical serialization (devostasis.canon.v1)

UTF-8; object keys sorted by code point; no insignificant whitespace; only
`null`, booleans, integers, strings, arrays and objects; **no floats**
(ratios are `{"num": x, "den": y}` records, exact durations in seconds are
`{"numerator": n, "denominator": d}` records); timestamps are
`YYYY-MM-DDTHH:MM:SSZ`. Digests are `sha256:<hex>` over canonical bytes.
Files may be stored pretty-printed; their digest is computed from the parsed
content. `effective-config.json` is stored in canonical form exactly.

Reading is as strict as writing. The one decoder behind every canonical read
refuses what the profile excludes before any caller interprets the value: a
decimal or exponent number (`1.5`, `1e3`, `-0.0`), which would otherwise
become a host float; `NaN`, `Infinity` and `-Infinity`, which Python accepts
although JSON does not; an object naming a member twice, which a host parser
would collapse to one value of its choosing; and a string with an unpaired
surrogate, which is not UTF-8. Each is a canonicalization error, never a
value a later check may or may not catch (`PV-AUDIT-CANONICAL-*-001`).

## Effective config

Before identity is computed, the runtime projects every resolved
configuration value that can change canonical member presence or bytes into
`effective_bundle_config` (`devostasis.effective-config.v2`): planning source,
path and link marker, debt mapping, `report_html`, locale, activity and its
list cap, observations member, the display options and the full demand
mapping. Omitted defaults and explicit defaults canonicalize identically;
reordered lists canonicalize identically. `effective_config_digest` is the
SHA-256 of that projection.

Every configuration input is classified as (A) already identity-bearing,
(B) projected, or (C) proven non-canonical. An unclassified input fails closed
with `CONFIG_IDENTITY_UNCLASSIFIED` before anything is persisted.

The persisted projection is not merely hashed: it is the **semantic
authority** of the bundle (PV-EFFECTIVE-CONFIG-AUTHORITY-001). The canonical
member profile recorded in the manifest (`report_md`, `report_html`,
`activity_json`, `observations_json`, `gauges_json`, `demand_json`,
`effective_config_json`, each `REQUIRED`, `ENABLED` or `DISABLED`) is derived
from it at build time, and verification derives it again from the stored
file rather than trusting the manifest.

## Identity

Normative order: normalize evidence, build canonical machine artifacts,
digest members and receipt, assemble the identity preimage, compute
`bundle_id`, render outputs, digest outputs, write the manifest, persist
fail-closed, publish `latest`.

The identity preimage contains: `bundle_identity_contract`,
`artifact_contract_version`, `vitals_contract_version`,
`observation_contract_version`, `ci_unit_contract_version`, `gauge_contract`,
`demand_contract`, `policy_version`, `config_version`, `renderer_version`,
`canonical_serialization_version`, `effective_config_contract`,
`effective_config_digest`, `project_identity`, `observed_at`,
`previous_bundle_id`, `comparison_status`, `snapshot_digest`, `delta_digest`,
`activity_digest`, `gauges_digest`, `demand_digest`, `observations_digest`,
`source_receipts_digest`.

`bundle_id = SHA-256(canonical(preimage))` as 64 hex characters. The manifest,
the report, output digests and `run_meta` are post-identity, so the dependency
graph is acyclic; `renderer_version` is identity-bearing so a changed renderer
never collides with an old bundle; `observed_at` is identity-bearing so two
collections of the same repository are distinct bundles.

Bundles written by `devostasis.bundle.v1` remain verifiable: verification
uses the preimage stored in each manifest, validates their
`devostasis.effective-config.v1` projection under that schema (no gauges,
demand, display or demand mapping members), and the comparison logic maps
the older semantic-config shape onto the current one so history stays
`COMPARABLE` across the upgrade.

## Verification

`devostasis verify --bundle <dir>` needs nothing outside the bundle
directory and performs, in this order:

1. every declared member exists, is readable and hashes to its manifest
   digest; every present member is declared; `effective-config.json` is in
   canonical form (ART-21);
2. `bundle_id` recomputes from the stored preimage; the preimage contains no
   post-identity field (ART-22); the persisted effective config hashes to
   `effective_config_digest` in both preimage and manifest, else
   `EFFECTIVE_CONFIG_PREIMAGE_MISMATCH` (ART-20/ART-21);
3. the stored effective config is validated fail-closed under its recorded
   schema (`devostasis.effective-config.v1` or `v2`: exact key set, enums,
   planning, debt mapping, display and demand shapes), else
   `EFFECTIVE_CONFIG_SCHEMA_INVALID_OR_UNSUPPORTED` (ART-25);
4. the canonical member profile is derived from the validated stored config
   and must equal the manifest profile, agree with the members actually
   present and declared, and agree with the `ACTIVITY_DISABLED` /
   `OBSERVATIONS_MEMBER_DISABLED` markers in the identity preimage, else
   `CANONICAL_MEMBER_PROFILE_MISMATCH` (ART-23);
5. the metadata the manifest repeats is bound to what the identity hashes
   (issue #12 finding 4): every identity field the manifest copies from the
   preimage is present in both copies and agrees with it
   (`IDENTITY_FIELD_MISMATCH`); the preimage has exactly the field set of
   its lineage, the exact `artifact_contract_version` it names
   (`devostasis.bundle.v1`: twenty fields, without `gauge_contract`,
   `demand_contract` and their digests; `devostasis.bundle.v2`: twenty-four),
   so a field deleted or added is `IDENTITY_PREIMAGE_SHAPE_MISMATCH` (without
   `source_receipts_digest` the receipt was simply not checked); a lineage
   this verifier does not know is `UNSUPPORTED_ARTIFACT_LINEAGE`, and a
   `renderer_version` that is not one of the renderers its lineage was
   written with is `RENDERER_VERSION_NOT_IN_LINEAGE`
   (`PV-AUDIT-MANIFEST-PREIMAGE-BINDING-001`: a deleted manifest copy of
   `renderer_version` used to pass and skip the replay it gates); every member
   the preimage hashes (not a disabled marker) is declared in the manifest,
   else `IDENTITY_MEMBER_NOT_DECLARED` (a bundle that dropped `delta.json` or
   `snapshot.json` with its entry kept its id, stopped the replay and
   verified with any report); `adapters`, which the report prints, is exactly
   the provider of the bound identity and the collector of the bound receipt
   (`ADAPTERS_MISMATCH`); the manifest receipt
   hashes to `source_receipts_digest` (`RECEIPT_DIGEST_MISMATCH`), the
   receipt inside `observations.json` is that receipt
   (`RECEIPT_COPY_MISMATCH`), `snapshot.json` names the evidence the bundle
   carries (`OBSERVATIONS_DIGEST_MISMATCH`), the durable revision history the
   Integrity result and `observations.json` name was carried from the bundle
   the manifest follows (`HISTORY_SOURCE_MISMATCH`, PV-HIST-002), and
   `semantic_config`, the field
   the comparison reads, is exactly the projection of the validated stored
   config under its schema (`SEMANTIC_CONFIG_MISMATCH`). A manifest that is
   not an object, or whose `members`, `receipt`, `identity_preimage` or
   `semantic_config` is not one, is a verification problem, never an
   exception;
6. only when steps 3 and 4 passed, and the renderer version is the current
   one, is `report.md` re-rendered from the immutable machine members and the
   `display` of the stored config (never from current defaults) and compared
   byte for byte (ART-12/ART-24). A bundle written by an earlier renderer of
   its lineage verifies without the replay, because that renderer is not
   carried; step 5 is what keeps a bundle from claiming one it was not
   written with. A bundle whose stored config failed the
   checks reports that the replay was skipped instead of replaying from an
   untrusted source.

Any problem is a verification failure. A consistently re-hashed forgery that
claims a member disabled in the stored config while keeping the member, or
that changes the stored config to an unsupported shape, fails at step 3 or 4
even though every digest matches; one that rewrites the comparability
metadata, the receipt or an identity field without touching a member fails
at step 5.

A bundle is built only over evidence derived under its own configuration:
when the receipt carries a real digest that differs from the effective
configuration a build resolves, the build is refused with `CONFIG_MISMATCH`
(issue #27) instead of persisting a semantic authority that contradicts its
snapshot.

## Conformance cases implemented

ART-01 baseline, ART-02 repeatability, ART-06 neutral rendering, ART-07
immutability, ART-12 renderer purity, ART-13 acyclicity, ART-14
cross-implementation identity, ART-16 observed_at identity, ART-17 effective
config collision, ART-18 optional member identity (enabled HTML fails closed
in this version), ART-19 canonicalization invariance, ART-20 and ART-21
persisted preimage, ART-22 no identity cycle, ART-23 member profile from
stored config, ART-24 stored-config render authority, ART-25 effective config
schema verification.
