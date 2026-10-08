"""Immutable canonical bundle: identity, members, manifest and verification.

Normative order (PV-BUNDLE-ID-002): canonical machine artifacts -> member and
receipt digests -> identity metadata and preimage -> bundle_id -> deterministic
renderer outputs -> output digests -> manifest -> persistence. The manifest,
report and output digests are post-identity, so the graph is acyclic.

The exact canonical effective config preimage is persisted as the member
``effective-config.json`` (B3 repair) and is the semantic authority of a
historical bundle (PV-EFFECTIVE-CONFIG-AUTHORITY-001, B4): verification
validates it under its recorded schema, derives the canonical member profile
from it, checks that profile against the actual members and the manifest, and
only then replays the renderer from stored config plus immutable machine
members. ``gauges.json`` and ``demand.json`` are derived from the snapshot
under versioned contracts and are identity-bearing members.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__, canonical, render
from .config import EFFECTIVE_CONFIG_SCHEMA_V1, PROFILE_MEMBERS, ResolvedProject, member_profile_from_config, validate_effective_config
from .contracts import (
    ARTIFACT_CONTRACT_VERSION,
    BUNDLE_IDENTITY_CONTRACT,
    CANONICAL_SERIALIZATION_VERSION,
    CI_UNIT_CONTRACT_VERSION,
    DEMAND_CONTRACT,
    EFFECTIVE_CONFIG_AUTHORITY_CONTRACT,
    EFFECTIVE_CONFIG_CONTRACT,
    GAUGE_CONTRACT,
    MANIFEST_SCHEMA,
    OBSERVATIONS_SCHEMA,
    RECEIPT_IDENTITY_CONTRACT,
    RECEIPT_IDENTITY_SCHEMA,
    OBSERVATION_CONTRACT_VERSION,
    RENDERER_VERSION,
    VITALS_CONTRACT_VERSION,
)
from .demand import build_demand
from .gauges import gauges_member
from .observations import ObservationSet, validate_receipt_identity
from .policy import POLICY_VERSION

ACTIVITY_DISABLED = "ACTIVITY_DISABLED"
OBSERVATIONS_DISABLED = "OBSERVATIONS_MEMBER_DISABLED"
MEMBER_NAMES = (
    "manifest.json",
    "snapshot.json",
    "delta.json",
    "activity.json",
    "observations.json",
    "gauges.json",
    "demand.json",
    "effective-config.json",
    "report.md",
    "report.html",
)

# Verification problem codes named by the accepted artifact contract.
EFFECTIVE_CONFIG_SCHEMA_INVALID = "EFFECTIVE_CONFIG_SCHEMA_INVALID_OR_UNSUPPORTED"
CANONICAL_MEMBER_PROFILE_MISMATCH = "CANONICAL_MEMBER_PROFILE_MISMATCH"
EFFECTIVE_CONFIG_PREIMAGE_MISMATCH = "EFFECTIVE_CONFIG_PREIMAGE_MISMATCH"
# Problem codes of the metadata binding (#12 finding 4): a field that decides
# comparability or names the evidence must agree with what verification hashes.
SEMANTIC_CONFIG_MISMATCH = "SEMANTIC_CONFIG_MISMATCH"
IDENTITY_FIELD_MISMATCH = "IDENTITY_FIELD_MISMATCH"
RECEIPT_DIGEST_MISMATCH = "RECEIPT_DIGEST_MISMATCH"
RECEIPT_COPY_MISMATCH = "RECEIPT_COPY_MISMATCH"
HISTORY_SOURCE_MISMATCH = "HISTORY_SOURCE_MISMATCH"
OBSERVATIONS_DIGEST_MISMATCH = "OBSERVATIONS_DIGEST_MISMATCH"
UNSUPPORTED_LINEAGE = "UNSUPPORTED_ARTIFACT_LINEAGE"
RENDERER_NOT_IN_LINEAGE = "RENDERER_VERSION_NOT_IN_LINEAGE"
PREIMAGE_SHAPE_MISMATCH = "IDENTITY_PREIMAGE_SHAPE_MISMATCH"
MEMBER_NOT_DECLARED = "IDENTITY_MEMBER_NOT_DECLARED"
ADAPTERS_MISMATCH = "ADAPTERS_MISMATCH"

# Fields the manifest repeats from the identity preimage. Every one of them
# must agree: the preimage is what bundle_id commits to, the manifest copy is
# what readers and the comparison read.
DUPLICATED_IDENTITY_FIELDS = (
    "manifest_schema",
    "observations_schema",
    "receipt_identity_contract",
    "receipt_identity_schema",
    "bundle_identity_contract",
    "artifact_contract_version",
    "vitals_contract_version",
    "observation_contract_version",
    "ci_unit_contract_version",
    "gauge_contract",
    "demand_contract",
    "policy_version",
    "config_version",
    "renderer_version",
    "canonical_serialization_version",
    "effective_config_contract",
    "project_identity",
    "observed_at",
    "previous_bundle_id",
    "comparison_status",
)

# The identity preimage of each stored lineage, field for field. Every bundle
# of the fleet's store carries exactly one of these two sets.
_PREIMAGE_V1 = (
    "bundle_identity_contract",
    "artifact_contract_version",
    "vitals_contract_version",
    "observation_contract_version",
    "ci_unit_contract_version",
    "policy_version",
    "config_version",
    "renderer_version",
    "canonical_serialization_version",
    "effective_config_contract",
    "effective_config_digest",
    "project_identity",
    "observed_at",
    "previous_bundle_id",
    "comparison_status",
    "snapshot_digest",
    "delta_digest",
    "activity_digest",
    "observations_digest",
    "source_receipts_digest",
)
_PREIMAGE_V2 = _PREIMAGE_V1 + ("gauge_contract", "demand_contract", "gauges_digest", "demand_digest")
_PREIMAGE_V3 = _PREIMAGE_V2 + ("manifest_schema", "observations_schema", "receipt_identity_contract", "receipt_identity_schema")
MANIFEST_V2_FIELDS = frozenset({
    "schema", "bundle_id", "project_key", "project_identity", "observed_at", "previous_bundle_id",
    "comparison_status", "supersedes_bundle_id", "artifact_contract_version", "bundle_identity_contract",
    "vitals_contract_version", "observation_contract_version", "ci_unit_contract_version", "gauge_contract",
    "demand_contract", "policy_version", "config_version", "renderer_version", "canonical_serialization_version",
    "effective_config_contract", "effective_config_authority_contract", "effective_config_digest", "semantic_config",
    "canonical_member_profile", "adapters", "receipt_identity", "identity_preimage", "manifest_schema",
    "observations_schema", "receipt_identity_contract", "receipt_identity_schema", "members",
})

# The stored lineages verification dispatches on, keyed by the preimage's
# ``artifact_contract_version`` as an exact token
# (PV-AUDIT-MANIFEST-PREIMAGE-BINDING-001): the exact field set of the
# identity preimage (a field deleted or added is a different, unsupported
# shape, and the duplicated identity fields among them are present in both
# copies), and the renderers the lineage was written with, which is what
# gates the report replay. ``devostasis.bundle.v1`` predates the gauges and
# demand members. The tokens are literal on purpose: moving RENDERER_VERSION or
# ARTIFACT_CONTRACT_VERSION must add a row here, never silently retire the row
# older bundles need.
LINEAGES: dict[str, dict[str, Any]] = {
    "devostasis.bundle.v1": {
        "preimage_fields": frozenset(_PREIMAGE_V1),
        "renderers": ("devostasis.render.v1", "devostasis.render.v2"),
    },
    "devostasis.bundle.v2": {
        "preimage_fields": frozenset(_PREIMAGE_V2),
        "renderers": ("devostasis.render.v3", "devostasis.render.v4"),
    },
    "devostasis.bundle.v3": {
        "preimage_fields": frozenset(_PREIMAGE_V3),
        "renderers": ("devostasis.render.v5",),
    },
}


@dataclass
class Bundle:
    bundle_id: str
    project_key: str
    observed_at: str
    manifest: dict[str, Any]
    members: dict[str, bytes] = field(default_factory=dict)
    execution_receipt: dict[str, Any] | None = None

    def _json(self, name: str) -> dict[str, Any]:
        return canonical.loads(self.members[name].decode("utf-8"))

    @property
    def snapshot(self) -> dict[str, Any]:
        return self._json("snapshot.json")

    def bands(self) -> dict[str, str | None]:
        return {item["vital_id"]: item["band"] for item in self.snapshot["vitals"]}

    def gauges(self) -> dict[str, int | None]:
        return {g["vital_id"]: g["value"] for g in self._json("gauges.json")["gauges"]}

    def demand(self) -> dict[str, Any]:
        return self._json("demand.json")


class BundleError(Exception):
    """Raised when a bundle cannot be built or verified."""


def project_identity(obs: ObservationSet, project: ResolvedProject) -> dict[str, Any]:
    subject = obs.subject
    return {
        "provider": "github",
        "forge_instance": subject.get("forge_instance", "github.com"),
        "immutable_project_id": subject.get("immutable_project_id"),
        "display_locator": subject.get("display_locator", project.locator),
        "default_branch": subject.get("default_branch"),
    }


def build_bundle(
    project: ResolvedProject,
    obs: ObservationSet,
    snapshot: dict[str, Any],
    delta: dict[str, Any],
    activity: dict[str, Any] | None,
    previous_bundle_id: str | None,
    comparison_status: str,
    run_meta: dict[str, Any] | None = None,
) -> Bundle:
    if project.report_html:
        raise BundleError("report_html=ENABLED is not supported by this version; canonical persistence fails closed rather than silently disabling the member")
    if obs.receipt is None:
        raise BundleError("observation set has no collection receipt")

    effective_config = project.effective_bundle_config()
    effective_bytes = canonical.canonical_bytes(effective_config)
    effective_digest = canonical.digest_bytes(effective_bytes)
    receipt_dict = obs.receipt_identity()
    identity = project_identity(obs, project)
    canonical_key = identity["forge_instance"] + "/" + identity["display_locator"]
    member_profile = member_profile_from_config(effective_config)
    if (activity is None) != (member_profile["activity_json"] == "DISABLED"):
        raise BundleError("activity member presence disagrees with the effective configuration")

    gauges_doc = gauges_member(snapshot)
    demand_doc = build_demand(snapshot, gauges_doc["gauges"], project.demand)

    snapshot_digest = canonical.digest(snapshot)
    delta_digest = canonical.digest(delta)
    activity_digest = canonical.digest(activity) if activity is not None else ACTIVITY_DISABLED
    gauges_digest = canonical.digest(gauges_doc)
    demand_digest = canonical.digest(demand_doc)
    observations_dict = obs.to_dict()
    observations_digest = canonical.digest(observations_dict)
    receipt_digest = canonical.digest(receipt_dict)

    preimage = {
        "manifest_schema": MANIFEST_SCHEMA,
        "observations_schema": OBSERVATIONS_SCHEMA,
        "receipt_identity_contract": RECEIPT_IDENTITY_CONTRACT,
        "receipt_identity_schema": RECEIPT_IDENTITY_SCHEMA,
        "bundle_identity_contract": BUNDLE_IDENTITY_CONTRACT,
        "artifact_contract_version": ARTIFACT_CONTRACT_VERSION,
        "vitals_contract_version": VITALS_CONTRACT_VERSION,
        "observation_contract_version": OBSERVATION_CONTRACT_VERSION,
        "ci_unit_contract_version": CI_UNIT_CONTRACT_VERSION,
        "gauge_contract": GAUGE_CONTRACT,
        "demand_contract": DEMAND_CONTRACT,
        "policy_version": POLICY_VERSION,
        "config_version": project.config_version,
        "renderer_version": RENDERER_VERSION,
        "canonical_serialization_version": CANONICAL_SERIALIZATION_VERSION,
        "effective_config_contract": EFFECTIVE_CONFIG_CONTRACT,
        "effective_config_digest": effective_digest,
        "project_identity": identity,
        "observed_at": obs.observed_at,
        "previous_bundle_id": previous_bundle_id,
        "comparison_status": comparison_status,
        "snapshot_digest": snapshot_digest,
        "delta_digest": delta_digest,
        "activity_digest": activity_digest,
        "gauges_digest": gauges_digest,
        "demand_digest": demand_digest,
        "observations_digest": observations_digest if project.observations_member else OBSERVATIONS_DISABLED,
        "source_receipts_digest": receipt_digest,
    }
    bundle_id = canonical.sha256_hex(canonical.canonical_bytes(preimage))

    manifest_core = {
        "manifest_schema": MANIFEST_SCHEMA,
        "observations_schema": OBSERVATIONS_SCHEMA,
        "receipt_identity_contract": RECEIPT_IDENTITY_CONTRACT,
        "receipt_identity_schema": RECEIPT_IDENTITY_SCHEMA,
        "schema": MANIFEST_SCHEMA,
        "bundle_id": bundle_id,
        "project_key": canonical_key,
        "project_identity": identity,
        "observed_at": obs.observed_at,
        "previous_bundle_id": previous_bundle_id,
        "comparison_status": comparison_status,
        "supersedes_bundle_id": None,
        "artifact_contract_version": ARTIFACT_CONTRACT_VERSION,
        "bundle_identity_contract": BUNDLE_IDENTITY_CONTRACT,
        "vitals_contract_version": VITALS_CONTRACT_VERSION,
        "observation_contract_version": OBSERVATION_CONTRACT_VERSION,
        "ci_unit_contract_version": CI_UNIT_CONTRACT_VERSION,
        "gauge_contract": GAUGE_CONTRACT,
        "demand_contract": DEMAND_CONTRACT,
        "policy_version": POLICY_VERSION,
        "config_version": project.config_version,
        "renderer_version": RENDERER_VERSION,
        "canonical_serialization_version": CANONICAL_SERIALIZATION_VERSION,
        "effective_config_contract": EFFECTIVE_CONFIG_CONTRACT,
        "effective_config_authority_contract": EFFECTIVE_CONFIG_AUTHORITY_CONTRACT,
        "effective_config_digest": effective_digest,
        "semantic_config": project.semantic_config(),
        "canonical_member_profile": member_profile,
        "adapters": [{"provider": "github", "adapter_version": obs.receipt.collector_version}],
        "receipt_identity": receipt_dict,
        "identity_preimage": preimage,
    }

    report_text = render.render_report(manifest_core, snapshot, delta, activity, gauges_doc, demand_doc, effective_config.get("display"))
    report_bytes = report_text.encode("utf-8")

    members: dict[str, bytes] = {
        "snapshot.json": canonical.pretty_json(snapshot).encode("utf-8"),
        "delta.json": canonical.pretty_json(delta).encode("utf-8"),
        "gauges.json": canonical.pretty_json(gauges_doc).encode("utf-8"),
        "demand.json": canonical.pretty_json(demand_doc).encode("utf-8"),
        "effective-config.json": effective_bytes,
        "report.md": report_bytes,
    }
    if activity is not None:
        members["activity.json"] = canonical.pretty_json(activity).encode("utf-8")
    if project.observations_member:
        members["observations.json"] = canonical.pretty_json(observations_dict).encode("utf-8")

    manifest = dict(manifest_core)
    manifest["members"] = {
        "snapshot.json": snapshot_digest,
        "delta.json": delta_digest,
        "gauges.json": gauges_digest,
        "demand.json": demand_digest,
        "effective-config.json": effective_digest,
        "report.md": canonical.digest_bytes(report_bytes),
    }
    if activity is not None:
        manifest["members"]["activity.json"] = activity_digest
    if project.observations_member:
        manifest["members"]["observations.json"] = observations_digest
    members["manifest.json"] = canonical.pretty_json(manifest).encode("utf-8")
    execution = obs.receipt.execution(bundle_id, dict(run_meta or {}, tool={"name": "devostasis", "version": __version__}), receipt_dict)
    return Bundle(bundle_id=bundle_id, project_key=canonical_key, observed_at=obs.observed_at,
                  manifest=manifest, members=members, execution_receipt=execution)


def load_bundle_dir(directory: str | Path) -> dict[str, bytes]:
    directory = Path(directory)
    members: dict[str, bytes] = {}
    for name in MEMBER_NAMES:
        path = directory / name
        if path.exists():
            members[name] = path.read_bytes()
    return members


PREIMAGE_MEMBER_DIGESTS = (
    ("snapshot.json", "snapshot_digest"),
    ("delta.json", "delta_digest"),
    ("activity.json", "activity_digest"),
    ("observations.json", "observations_digest"),
    ("gauges.json", "gauges_digest"),
    ("demand.json", "demand_digest"),
)

BYTE_DIGESTED_MEMBERS = ("report.md", "report.html", "effective-config.json")


def _member_digest(name: str, data: bytes) -> str:
    if name in BYTE_DIGESTED_MEMBERS:
        return canonical.digest_bytes(data)
    return canonical.digest(canonical.loads(data.decode("utf-8")))


def semantic_projection(config: dict[str, Any]) -> dict[str, Any]:
    """The comparability subset of a stored effective config, in the shape the manifest of its lineage records."""
    if config.get("schema") == EFFECTIVE_CONFIG_SCHEMA_V1:
        return {"planning_source": config.get("planning_source"), "debt_mapping": config.get("debt_mapping")}
    return {"planning": config.get("planning"), "debt_mapping": config.get("debt_mapping")}


def _check_semantic_binding(members: dict[str, bytes], manifest: dict[str, Any], config: dict[str, Any]) -> list[str]:
    """#12 finding 4: the manifest's comparability metadata must be the projection of the stored config."""
    expected = semantic_projection(config)
    recorded = manifest.get("semantic_config")
    if recorded != expected:
        return [f"{SEMANTIC_CONFIG_MISMATCH}: manifest semantic_config {recorded} is not the projection {expected} of the stored effective config"]
    return []


def _check_identity_fields(manifest: dict[str, Any], preimage: dict[str, Any]) -> list[str]:
    """Presence and equality of every identity field the manifest repeats, under the stored lineage.

    Comparing only the fields both copies carry let a deletion pass: without
    its manifest ``renderer_version`` a bundle kept its id and silently lost
    the report replay that field gates. A field the lineage requires must be
    in the preimage, and a field in either copy must be in both, equal.
    """
    problems: list[str] = []
    lineage_name = preimage.get("artifact_contract_version")
    lineage = LINEAGES.get(lineage_name) if isinstance(lineage_name, str) else None
    if lineage is None:
        problems.append(f"{UNSUPPORTED_LINEAGE}: artifact_contract_version {lineage_name!r} is not a lineage this verifier dispatches on")
    else:
        for key in sorted(lineage["preimage_fields"] - set(preimage)):
            problems.append(f"{PREIMAGE_SHAPE_MISMATCH}: {key} is a field of the {lineage_name} identity preimage and is absent")
        for key in sorted(set(preimage) - lineage["preimage_fields"]):
            problems.append(f"{PREIMAGE_SHAPE_MISMATCH}: {key} is not a field of the {lineage_name} identity preimage")
    for key in DUPLICATED_IDENTITY_FIELDS:
        in_preimage, in_manifest = key in preimage, key in manifest
        if in_preimage and not in_manifest:
            problems.append(f"{IDENTITY_FIELD_MISMATCH}: {key} is {preimage[key]!r} in the identity preimage and absent from the manifest")
        elif in_manifest and not in_preimage:
            problems.append(f"{IDENTITY_FIELD_MISMATCH}: {key} is {manifest[key]!r} in the manifest and absent from the identity preimage")
        elif in_preimage and preimage[key] != manifest[key]:
            problems.append(f"{IDENTITY_FIELD_MISMATCH}: {key} is {manifest[key]!r} in the manifest and {preimage[key]!r} in the identity preimage")
    if lineage is not None and preimage.get("renderer_version") not in lineage["renderers"]:
        problems.append(
            f"{RENDERER_NOT_IN_LINEAGE}: renderer_version {preimage.get('renderer_version')!r} is not a renderer the {lineage_name} lineage was written with"
        )
    return problems


def _check_hashed_members(manifest: dict[str, Any], preimage: dict[str, Any]) -> list[str]:
    """A member the identity hashes must be declared: deleting it with its entry must not pass.

    The declared-member loop only checks the members the manifest names, so a
    bundle that dropped ``delta.json`` or ``snapshot.json`` together with its
    ``members`` entry kept its id, skipped the report replay (which needs
    both) and verified with any report.
    """
    declared = manifest.get("members") or {}
    problems: list[str] = []
    for member, key in PREIMAGE_MEMBER_DIGESTS:
        if key in preimage and preimage[key] not in (ACTIVITY_DISABLED, OBSERVATIONS_DISABLED) and member not in declared:
            problems.append(f"{MEMBER_NOT_DECLARED}: {member} is hashed into the identity preimage as {key} but the manifest does not declare it")
    return problems


def _check_adapters(manifest: dict[str, Any]) -> list[str]:
    """``adapters`` is rendered into the report, so it is bound to the facts the identity hashes.

    Its only honest value is the provider of the bound project identity and the
    collector version of the bound receipt; anything else is provenance nobody
    collected under.
    """
    identity = manifest.get("project_identity")
    receipt = manifest.get("receipt_identity") if manifest.get("schema") == MANIFEST_SCHEMA else manifest.get("receipt")
    expected = [
        {
            "provider": identity.get("provider") if isinstance(identity, dict) else None,
            "adapter_version": receipt.get("collector_version") if isinstance(receipt, dict) else None,
        }
    ]
    if manifest.get("adapters") != expected:
        return [f"{ADAPTERS_MISMATCH}: manifest adapters {manifest.get('adapters')!r} are not {expected!r}, the provider and collector the identity binds"]
    return []


def _check_evidence_binding(members: dict[str, bytes], manifest: dict[str, Any], preimage: dict[str, Any]) -> list[str]:
    """The receipt and the evidence the manifest names must be the ones the identity hashes."""
    problems: list[str] = []
    successor = manifest.get("schema") == MANIFEST_SCHEMA
    receipt_key = "receipt_identity" if successor else "receipt"
    receipt = manifest.get(receipt_key)
    if successor:
        try:
            validate_receipt_identity(receipt)
        except (ValueError, TypeError) as exc:
            problems.append(f"RECEIPT_IDENTITY_INVALID: {exc}")
    if "source_receipts_digest" in preimage:
        try:
            actual = canonical.digest(receipt)
        except Exception as exc:  # noqa: BLE001
            actual = f"unhashable ({exc})"
        if actual != preimage["source_receipts_digest"]:
            problems.append(f"{RECEIPT_DIGEST_MISMATCH}: the manifest receipt hashes to {actual}, the identity preimage names {preimage['source_receipts_digest']}")
    observations = None
    if "observations.json" in members:
        try:
            observations = canonical.loads(members["observations.json"].decode("utf-8"))
        except Exception:  # noqa: BLE001
            observations = None
        if isinstance(observations, dict) and observations.get(receipt_key) != receipt:
            problems.append(f"{RECEIPT_COPY_MISMATCH}: the receipt in observations.json differs from the manifest receipt")
        expected_schema = OBSERVATIONS_SCHEMA if successor else "devostasis.observations.v1"
        if not isinstance(observations, dict) or observations.get("schema") != expected_schema or (
                "receipt" if successor else "receipt_identity") in observations:
            problems.append("LINEAGE_MISMATCH: observations receipt schema")
    if "snapshot.json" in members and "observations.json" in (manifest.get("members") or {}):
        try:
            snapshot = canonical.loads(members["snapshot.json"].decode("utf-8"))
        except Exception:  # noqa: BLE001
            snapshot = None
        declared = manifest["members"]["observations.json"]
        if isinstance(snapshot, dict) and snapshot.get("observations_digest") != declared:
            problems.append(f"{OBSERVATIONS_DIGEST_MISMATCH}: snapshot.json was evaluated over {snapshot.get('observations_digest')}, the bundle carries {declared}")
    problems.extend(_check_history_source(members, manifest, observations))
    return problems


def _history_source_named(snapshot: Any) -> tuple[str | None, str | None]:
    """The status and bundle of the durable history source the Integrity result names, if it names one."""
    if not isinstance(snapshot, dict):
        return None, None
    for vital in snapshot.get("vitals") or []:
        if isinstance(vital, dict) and vital.get("vital_id") == "integrity":
            history = (vital.get("derived") or {}).get("revision_history") if isinstance(vital.get("derived"), dict) else None
            source = history.get("source") if isinstance(history, dict) else None
            if isinstance(source, dict):
                return source.get("status"), source.get("bundle_id")
    return None, None


def _check_history_source(members: dict[str, bytes], manifest: dict[str, Any], observations: Any) -> list[str]:
    """PV-HIST-002 section C: the carried history came from the bundle this one follows, and says so.

    The selection of the source is auditable only if the bundle names it; a
    bundle whose carried history names another bundle than the one its
    manifest says it follows consumed history from outside its own chain.
    Bundles older than the carrier name nothing and are not checked.
    """
    problems: list[str] = []
    previous = manifest.get("previous_bundle_id")
    try:
        snapshot = canonical.loads(members["snapshot.json"].decode("utf-8")) if "snapshot.json" in members else None
    except Exception:  # noqa: BLE001
        snapshot = None
    status, source = _history_source_named(snapshot)
    if status == "CARRIED" and source != previous:
        problems.append(f"{HISTORY_SOURCE_MISMATCH}: the Integrity history was carried from {source}, the manifest follows {previous}")
    if isinstance(observations, dict):
        for item in observations.get("observations") or []:
            if not isinstance(item, dict) or item.get("observation_id") != "ci.revision_history_carried":
                continue
            value = item.get("value")
            named = value.get("source_bundle_id") if isinstance(value, dict) else None
            if named is not None and named != previous:
                problems.append(f"{HISTORY_SOURCE_MISMATCH}: observations.json carries history from {named}, the manifest follows {previous}")
    return problems


def _check_member_profile(members: dict[str, bytes], manifest: dict[str, Any], config: dict[str, Any]) -> list[str]:
    """ART-23: the profile implied by the stored config must match the manifest and the actual members."""
    problems: list[str] = []
    expected = member_profile_from_config(config)
    recorded = manifest.get("canonical_member_profile")
    if recorded != expected:
        problems.append(
            f"{CANONICAL_MEMBER_PROFILE_MISMATCH}: manifest profile {recorded} differs from the profile implied by the stored effective config {expected} (ART-23)"
        )
    declared = manifest.get("members") or {}
    for key, member in PROFILE_MEMBERS.items():
        state = expected.get(key)
        present = member in members or member in declared
        if state is None:
            if present:
                problems.append(f"{CANONICAL_MEMBER_PROFILE_MISMATCH}: {member} is present but the stored effective config schema knows no such member (ART-23)")
            continue
        if state in ("REQUIRED", "ENABLED") and not present:
            problems.append(f"{CANONICAL_MEMBER_PROFILE_MISMATCH}: {member} is {state} by the stored effective config but absent (ART-23)")
        if state == "DISABLED" and present:
            problems.append(f"{CANONICAL_MEMBER_PROFILE_MISMATCH}: {member} is DISABLED by the stored effective config but present (ART-23)")
    preimage = manifest.get("identity_preimage") or {}
    if preimage:
        activity_disabled = preimage.get("activity_digest") == ACTIVITY_DISABLED
        if activity_disabled != (expected["activity_json"] == "DISABLED"):
            problems.append(f"{CANONICAL_MEMBER_PROFILE_MISMATCH}: identity preimage activity marker disagrees with the stored effective config (ART-23)")
        observations_disabled = preimage.get("observations_digest") == OBSERVATIONS_DISABLED
        if observations_disabled != (expected["observations_json"] == "DISABLED"):
            problems.append(f"{CANONICAL_MEMBER_PROFILE_MISMATCH}: identity preimage observations marker disagrees with the stored effective config (ART-23)")
    return problems


def verify_members(members: dict[str, bytes]) -> list[str]:
    """Return verification problems for a bundle (empty list means verified).

    Order: member digests and canonical form; identity preimage and bundle_id;
    the stored effective config as semantic authority (schema, member profile,
    identity markers); only then the renderer replay from stored config.
    """
    problems: list[str] = []
    if "manifest.json" not in members:
        return ["manifest.json missing"]
    try:
        manifest = canonical.loads(members["manifest.json"].decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"manifest.json unreadable: {exc}"]
    if not isinstance(manifest, dict):
        return [f"manifest.json is not an object but {type(manifest).__name__}"]
    for key, kind in (("members", dict), ("identity_preimage", dict), ("receipt", dict), ("semantic_config", dict)):
        if key in manifest and not isinstance(manifest[key], kind):
            problems.append(f"manifest {key} is not an object but {type(manifest[key]).__name__}")
    if problems:
        return problems

    from .lineages import validate_bundle_lineage
    problems.extend(validate_bundle_lineage(manifest, members))

    successor = manifest.get("artifact_contract_version") == "devostasis.bundle.v3"
    if successor:
        expected = {"schema": MANIFEST_SCHEMA, "manifest_schema": MANIFEST_SCHEMA,
                    "bundle_identity_contract": BUNDLE_IDENTITY_CONTRACT,
                    "receipt_identity_contract": RECEIPT_IDENTITY_CONTRACT,
                    "receipt_identity_schema": RECEIPT_IDENTITY_SCHEMA,
                    "observations_schema": OBSERVATIONS_SCHEMA}
        if any(manifest.get(k) != v for k, v in expected.items()) or "receipt" in manifest or "run_meta" in manifest:
            problems.append("LINEAGE_MISMATCH: successor manifest/receipt contract")
        if set(manifest) != MANIFEST_V2_FIELDS:
            problems.append("MANIFEST_SCHEMA_INVALID: missing or unknown successor fields")
        if manifest.get("supersedes_bundle_id") is not None or manifest.get("effective_config_authority_contract") != EFFECTIVE_CONFIG_AUTHORITY_CONTRACT:
            problems.append("MANIFEST_SCHEMA_INVALID: unsupported authority or supersession")
        project_ref = manifest.get("project_identity")
        if not isinstance(project_ref, dict) or manifest.get("project_key") != (
                str(project_ref.get("forge_instance")) + "/" + str(project_ref.get("display_locator"))):
            problems.append("MANIFEST_SCHEMA_INVALID: project key differs from bound identity")
        for name, data in members.items():
            if name.endswith(".json"):
                try:
                    value = canonical.loads(data.decode("utf-8"))
                    expected_bytes = canonical.canonical_bytes(value) if name == "effective-config.json" else canonical.pretty_json(value).encode("utf-8")
                    if data != expected_bytes:
                        problems.append("CANONICAL_BYTES_MISMATCH: " + name)
                except (ValueError, TypeError, UnicodeError):
                    problems.append("CANONICAL_BYTES_MISMATCH: " + name)
        if not set(manifest.get("members") or {}) <= set(MEMBER_NAMES) - {"manifest.json"}:
            problems.append("CANONICAL_MEMBER_PROFILE_MISMATCH: unsupported successor member")
    elif manifest.get("schema") != "devostasis.manifest.v1" or manifest.get("bundle_identity_contract") not in (
            "PV-BUNDLE-ID-001", "PV-BUNDLE-ID-002") or "receipt_identity" in manifest:
        problems.append("LINEAGE_MISMATCH: historical manifest/receipt contract")

    declared = manifest.get("members") or {}
    for name, digest in sorted(declared.items()):
        if name not in members:
            problems.append(f"{name} declared but missing")
            continue
        data = members[name]
        try:
            actual = _member_digest(name, data)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{name} unreadable: {exc}")
            continue
        if name == "effective-config.json":
            try:
                if canonical.canonical_bytes(canonical.loads(data.decode("utf-8"))) != data:
                    problems.append("effective-config.json is not stored in canonical form (ART-21)")
            except Exception as exc:  # noqa: BLE001
                problems.append(f"effective-config.json unreadable: {exc}")
        if actual != digest:
            problems.append(f"{name} digest mismatch: manifest {digest}, actual {actual}")
    for name in sorted(members):
        if name != "manifest.json" and name not in declared:
            problems.append(f"{name} is present but not declared in the manifest")
    if "effective-config.json" not in members:
        problems.append("effective-config.json missing (ART-20)")

    preimage = manifest.get("identity_preimage") or {}
    if not preimage:
        problems.append("identity preimage missing from manifest")
    else:
        recomputed = canonical.sha256_hex(canonical.canonical_bytes(preimage))
        if recomputed != manifest.get("bundle_id"):
            problems.append(f"bundle_id mismatch: manifest {manifest.get('bundle_id')}, recomputed {recomputed}")
        if preimage.get("effective_config_digest") != manifest.get("effective_config_digest"):
            problems.append(f"{EFFECTIVE_CONFIG_PREIMAGE_MISMATCH}: effective_config_digest differs between preimage and manifest")
        if "effective-config.json" in members and preimage.get("effective_config_digest") != canonical.digest_bytes(members["effective-config.json"]):
            problems.append(f"{EFFECTIVE_CONFIG_PREIMAGE_MISMATCH}: persisted effective config does not hash to effective_config_digest (ART-20/ART-21)")
        for member, key in PREIMAGE_MEMBER_DIGESTS:
            if member in declared and key in preimage and preimage.get(key) != declared[member]:
                problems.append(f"{member} digest differs between preimage and manifest members")
        for key in ("bundle_id", "members", "run_meta"):
            if key in preimage:
                problems.append(f"identity preimage must not contain post-identity field {key} (ART-22)")
        problems.extend(_check_identity_fields(manifest, preimage))
        problems.extend(_check_hashed_members(manifest, preimage))
        problems.extend(_check_adapters(manifest))
        problems.extend(_check_evidence_binding(members, manifest, preimage))

    # B4: the stored effective config is the semantic authority (ART-25, then ART-23).
    config: dict[str, Any] | None = None
    authority_ok = "effective-config.json" in members
    if authority_ok:
        try:
            config = canonical.loads(members["effective-config.json"].decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{EFFECTIVE_CONFIG_SCHEMA_INVALID}: effective-config.json unreadable: {exc} (ART-25)")
            authority_ok = False
    if authority_ok:
        schema_problems = validate_effective_config(config)
        if schema_problems:
            problems.extend(f"{EFFECTIVE_CONFIG_SCHEMA_INVALID}: {problem} (ART-25)" for problem in schema_problems)
            authority_ok = False
    if authority_ok:
        profile_problems = _check_member_profile(members, manifest, config)
        if profile_problems:
            problems.extend(profile_problems)
            authority_ok = False
    if authority_ok:
        problems.extend(_check_semantic_binding(members, manifest, config))

    # ART-24: replay only from the validated stored config and immutable machine members.
    if "report.md" in members:
        if not authority_ok:
            problems.append("report.md replay skipped: the stored effective config is not a valid authority (ART-24)")
        elif "snapshot.json" in members and "delta.json" in members and manifest.get("renderer_version") in ("devostasis.render.v4", "devostasis.render.v5"):
            try:
                snapshot = canonical.loads(members["snapshot.json"].decode("utf-8"))
                delta = canonical.loads(members["delta.json"].decode("utf-8"))
                activity = canonical.loads(members["activity.json"].decode("utf-8")) if "activity.json" in members else None
                gauges_doc = canonical.loads(members["gauges.json"].decode("utf-8")) if "gauges.json" in members else None
                demand_doc = canonical.loads(members["demand.json"].decode("utf-8")) if "demand.json" in members else None
                rendered = render.render_report(manifest, snapshot, delta, activity, gauges_doc, demand_doc, config.get("display")).encode("utf-8")
                if rendered != members["report.md"]:
                    problems.append("report.md is not reproducible from the machine bundle and the stored effective config with the current renderer (ART-12/ART-24)")
            except Exception as exc:  # noqa: BLE001
                problems.append(f"report re-rendering failed: {exc}")
    return problems


def verify_dir(directory: str | Path) -> list[str]:
    return verify_members(load_bundle_dir(directory))


def report_renderer(directory: str | Path) -> str | None:
    """The renderer a verified bundle names, which decides whether its report was replayed."""
    members = load_bundle_dir(directory)
    try:
        manifest = canonical.loads(members["manifest.json"].decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    renderer = manifest.get("renderer_version") if isinstance(manifest, dict) else None
    return renderer if isinstance(renderer, str) else None
