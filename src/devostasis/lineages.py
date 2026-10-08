"""Finite public bundle lineage tuples. Tokens are opaque, never ordered."""

from .canonical import loads

# artifact, identity, manifest, renderer, receipt, observations, config, delta, demand
BUNDLE_LINEAGES = frozenset({
    ("devostasis.bundle.v1", identity, "devostasis.manifest.v1", renderer, "devostasis.receipt.v1",
     "devostasis.observations.v1", "devostasis.effective-config.v1", "devostasis.delta.v1", None)
    for identity in ("PV-BUNDLE-ID-001", "PV-BUNDLE-ID-002")
    for renderer in ("devostasis.render.v1", "devostasis.render.v2")
} | {
    ("devostasis.bundle.v2", "PV-BUNDLE-ID-002", "devostasis.manifest.v1", "devostasis.render.v3",
     "devostasis.receipt.v1", "devostasis.observations.v1", "devostasis.effective-config.v2", "devostasis.delta.v1", "devostasis.demand.v1"),
    ("devostasis.bundle.v2", "PV-BUNDLE-ID-002", "devostasis.manifest.v1", "devostasis.render.v4",
     "devostasis.receipt.v1", "devostasis.observations.v1", "devostasis.effective-config.v2", "devostasis.delta.v1", "devostasis.demand.v2"),
    ("devostasis.bundle.v2", "PV-BUNDLE-ID-002", "devostasis.manifest.v1", "devostasis.render.v4",
     "devostasis.receipt.v2", "devostasis.observations.v1", "devostasis.effective-config.v2", "devostasis.delta.v1", "devostasis.demand.v2"),
    ("devostasis.bundle.v2", "PV-BUNDLE-ID-002", "devostasis.manifest.v1", "devostasis.render.v4",
     "devostasis.receipt.v2", "devostasis.observations.v1", "devostasis.effective-config.v2", "devostasis.delta.v2", "devostasis.demand.v2"),
    ("devostasis.bundle.v3", "PV-BUNDLE-ID-003", "devostasis.manifest.v2", "devostasis.render.v5",
     "devostasis.receipt-identity.v1", "devostasis.observations.v2", "devostasis.effective-config.v2", "devostasis.delta.v2", "devostasis.demand.v2"),
})


def validate_bundle_lineage(manifest, members):
    """Admit a whole tuple, including persisted member schemas, before replay."""
    def schema(name, fallback=None):
        if name not in members:
            return fallback
        value = loads(members[name].decode("utf-8"))
        return value.get("schema") if isinstance(value, dict) else None
    try:
        successor = manifest.get("schema") == "devostasis.manifest.v2"
        receipt = manifest.get("receipt_identity" if successor else "receipt")
        observed_schema = manifest.get("observations_schema") if successor else "devostasis.observations.v1"
        actual = (manifest.get("artifact_contract_version"), manifest.get("bundle_identity_contract"), manifest.get("schema"),
                  manifest.get("renderer_version"), receipt.get("schema") if isinstance(receipt, dict) else None,
                  schema("observations.json", observed_schema), schema("effective-config.json"), schema("delta.json"),
                  manifest.get("demand_contract"))
        if actual not in BUNDLE_LINEAGES:
            return ["LINEAGE_MISMATCH: undeclared bundle schema/contract tuple"]
        required = {"vitals_contract_version": "PV-VITALS-V1-002", "observation_contract_version": "RAW-OBS-V0",
                    "ci_unit_contract_version": "PV-CI-UNIT-004", "policy_version": "devostasis.policy.v1",
                    "canonical_serialization_version": "devostasis.canon.v1", "effective_config_contract": "PV-EFFECTIVE-CONFIG-001"}
        if any(manifest.get(k) != v for k, v in required.items()):
            return ["LINEAGE_MISMATCH: unsupported required contract token"]
        for name, expected in (("snapshot.json", "devostasis.snapshot.v1"), ("activity.json", "devostasis.activity.v1"),
                               ("gauges.json", "devostasis.gauges.v1"), ("demand.json", actual[-1])):
            if name in members and schema(name) != expected:
                return ["LINEAGE_MISMATCH: " + name]
        if "gauges.json" in members and manifest.get("gauge_contract") != "devostasis.gauge.v1":
            return ["LINEAGE_MISMATCH: gauge contract"]
    except (ValueError, TypeError, UnicodeError, AttributeError):
        return ["LINEAGE_MISMATCH: unreadable versioned member"]
    return []
