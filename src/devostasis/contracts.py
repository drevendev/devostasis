"""Version identifiers of every contract the runtime implements.

Identifiers that end in an accepted research unit name (PV-...) implement that
unit as written. Identifiers under the ``devostasis.`` prefix are this
implementation's own versioned choices; ``docs/spec/PROVENANCE.md`` maps each
one to its source unit and acceptance status.
"""

# Observation envelope: RAW_OBSERVATION_CONTRACT_V0 (unit PV-OBS-001).
OBSERVATION_CONTRACT_VERSION = "RAW-OBS-V0"

# Seven-Vital taxonomy: accepted PV-VITALS-V1-002 (units PV-VIT-010/012).
# Per-Vital rule versions (``rule_id`` in the snapshot) carry the repairs
# adopted on top of it: flow.bands.v1 (PV-FLOW-EMPTY-QUEUE-001,
# PV-FLOW-MERGE-LATENCY-001), pulse.bands.v1 (PV-PULSE-REQUIRED-LOWER-BOUND-001),
# clutter.bands.v1 (PV-CLUTTER-INCOMPLETE-001), and since 0.2.0
# direction.bands.v2 (PV-REV-DIRECTION-CLOSED-TARGET-001, PV-DIRECTION-INCOMPLETE-001),
# horizon.bands.v2 (PV-HORIZON-PARTIAL-001), debt.bands.v2 (PV-DEBT-PARTIAL-001)
# and integrity.bands.v1+ci-unit-004+hist-002 (PV-HIST-002); vitals.md lists them.
VITALS_CONTRACT_VERSION = "PV-VITALS-V1-002"

# Integrity revision/verification semantics: accepted PV-CI-UNIT-004 (PV-VIT-011).
CI_UNIT_CONTRACT_VERSION = "PV-CI-UNIT-004"

# Numeric thresholds and windows frozen in V0 and preserved by V1.1.
POLICY_VERSION = "devostasis.policy.v1"

# Bundle layout: PV-ARTIFACT-V1-005 (accepted by PV-REV-ARTIFACT-005) with the
# gauges.json and demand.json members in the identity preimage (v2) and the
# stored effective config as the semantic authority of verification (ART-23..25).
ARTIFACT_CONTRACT_VERSION = "devostasis.bundle.v2"
BUNDLE_IDENTITY_CONTRACT = "PV-BUNDLE-ID-002"
EFFECTIVE_CONFIG_CONTRACT = "PV-EFFECTIVE-CONFIG-001"
EFFECTIVE_CONFIG_AUTHORITY_CONTRACT = "PV-EFFECTIVE-CONFIG-AUTHORITY-001"
EFFECTIVE_CONFIG_SCHEMA = "devostasis.effective-config.v2"

# Normative per-Vital band ordering: accepted PV-BAND-ORDER-001, adopted in
# 0.1.8. Ordering is per Vital only, never across Vitals or projects and never
# into an aggregate; it is what makes IMPROVED and WORSENED emittable.
BAND_ORDER_CONTRACT = "PV-BAND-ORDER-001"
BAND_ORDER_VERSION = "devostasis.band-order.v1"

# Executable conformance vectors: the file format a conformance case is written
# in and the runner that executes it. The vectors of PV-TEST-001 are authored
# against this format.
VECTOR_SCHEMA = "devostasis.vectors.v1"

# Deterministic Markdown renderer (v4 states the demand ordering of demand.v2 and
# renders exact rational durations).
RENDERER_VERSION = "devostasis.render.v4"

# 0-100 gauges: accepted by PV-REV-GAUGE-001 as the versioned normalization for
# presentation and same-Vital ordering; never compared across Vitals.
GAUGE_CONTRACT = "devostasis.gauge.v1"
GAUGES_SCHEMA = "devostasis.gauges.v1"

# Generic consumer demand interface: band -> level plus an attention order, no
# aggregate. v2 orders inside a level by canonical Vital order only (ROLE-01).
DEMAND_CONTRACT = "devostasis.demand.v2"

# Machine-readable fleet index of a history store: the facts of projects/README.md
# as data, with no aggregate and no cross-project ordering.
FLEET_SCHEMA = "devostasis.fleet.v1"

# Canonical JSON profile used for every digest.
CANONICAL_SERIALIZATION_VERSION = "devostasis.canon.v1"

# Schema identifiers of the machine artifacts.
SNAPSHOT_SCHEMA = "devostasis.snapshot.v1"
DELTA_SCHEMA = "devostasis.delta.v2"
ACTIVITY_SCHEMA = "devostasis.activity.v1"
MANIFEST_SCHEMA = "devostasis.manifest.v1"
OBSERVATIONS_SCHEMA = "devostasis.observations.v1"
RECEIPT_SCHEMA = "devostasis.receipt.v2"

# Canonical order of the seven core Vitals inside every snapshot.
CORE_VITAL_IDS = ("horizon", "clutter", "direction", "flow", "integrity", "debt", "pulse")
