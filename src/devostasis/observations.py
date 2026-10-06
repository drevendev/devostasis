"""Typed observation envelopes and collection receipts (RAW_OBSERVATION_CONTRACT_V0).

The core invariant of the contract: ``value != evidence status``. A collector
that cannot prove a value emits no value and an explicit non-available status.
Zero, empty and false are only ever positively observed values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import canonical
from .contracts import OBSERVATION_CONTRACT_VERSION, OBSERVATIONS_SCHEMA, RECEIPT_SCHEMA
from .contracts import RECEIPT_IDENTITY_CONTRACT, RECEIPT_IDENTITY_SCHEMA, EXECUTION_RECEIPT_SCHEMA

AVAILABLE = "AVAILABLE"
PARTIAL = "PARTIAL"
UNAVAILABLE = "UNAVAILABLE"
FORBIDDEN = "FORBIDDEN"
UNKNOWN = "UNKNOWN"
ERROR = "ERROR"
STATUSES = frozenset({AVAILABLE, PARTIAL, UNAVAILABLE, FORBIDDEN, UNKNOWN, ERROR})
VALUE_BEARING = frozenset({AVAILABLE, PARTIAL})

FRESH = "FRESH"
STALE = "STALE"
FRESHNESS_UNKNOWN = "UNKNOWN"
FRESHNESSES = frozenset({FRESH, STALE, FRESHNESS_UNKNOWN})

VALUE_TYPES = frozenset({"count", "ratio", "duration", "boolean", "enum", "string", "set", "series", "record"})

NOT_REQUESTED = "NOT_REQUESTED"

# What the value of a PARTIAL envelope is, recorded in its coverage
# (PV-REV-PR-031-003). The one semantics a consumer may read as a lower bound
# is a count over the records an incomplete enumeration did return: the
# records it did not return can only add to it. status=PARTIAL alone proves
# nothing about the value, so absent, other or malformed semantics are never
# promoted to a floor.
VALUE_SEMANTICS = "value_semantics"
OBSERVED_SUBSET_COUNT = "OBSERVED_SUBSET_COUNT"
SUBSET_NOT_PROVEN = "PARTIAL_SUBSET_NOT_PROVEN"
NOT_A_SUBSET = "PARTIAL_NOT_AN_OBSERVED_SUBSET"
COVERAGE_MALFORMED = "PARTIAL_COVERAGE_MALFORMED"
COVERAGE_CONTRADICTORY = "PARTIAL_COVERAGE_CONTRADICTS_STATUS"
VALUE_NOT_A_COUNT = "PARTIAL_VALUE_NOT_A_COUNT"


class ObservationError(ValueError):
    """Raised when an envelope violates the observation contract."""


def failed_execution(target, started_at, ended_at, reason, counters=None):
    """An invocation can fail before any admissible receipt identity exists."""
    from uuid import uuid4
    return {"schema": EXECUTION_RECEIPT_SCHEMA, "run_id": uuid4().hex,
            "started_at": started_at, "ended_at": ended_at, "result_bundle_id": None,
            "receipt_identity": None, "diagnostics": [reason],
            "run_meta": {"target_requested": target, **(counters or {})}}


@dataclass(frozen=True)
class Observation:
    observation_id: str
    status: str
    value_type: str
    value: Any = None
    freshness: str = FRESH
    provider: str = "unknown"
    collected_at: str | None = None
    source_ref: str | None = None
    coverage: dict[str, Any] | None = None
    evidence_ref: Any = None
    adapter_version: str | None = None
    reason_code: str | None = None
    notes: str | None = None
    schema_version: str = OBSERVATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not self.observation_id:
            raise ObservationError("observation_id is required")
        if self.status not in STATUSES:
            raise ObservationError(f"{self.observation_id}: invalid status {self.status!r}")
        if self.freshness not in FRESHNESSES:
            raise ObservationError(f"{self.observation_id}: invalid freshness {self.freshness!r}")
        if self.value_type not in VALUE_TYPES:
            raise ObservationError(f"{self.observation_id}: invalid value_type {self.value_type!r}")
        if self.status not in VALUE_BEARING and self.value is not None:
            raise ObservationError(
                f"{self.observation_id}: status {self.status} must not carry a value (value != evidence status)"
            )
        if self.status == AVAILABLE and self.value is None and self.value_type != "record":
            raise ObservationError(f"{self.observation_id}: AVAILABLE observation must carry a value")

    @property
    def good(self) -> bool:
        """Exact evidence: positively observed and fresh."""
        return self.status == AVAILABLE and self.freshness == FRESH

    @property
    def has_value(self) -> bool:
        return self.status in VALUE_BEARING and self.value is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "schema_version": self.schema_version,
            "provider": self.provider,
            "collected_at": self.collected_at,
            "source_ref": self.source_ref,
            "status": self.status,
            "freshness": self.freshness,
            "value_type": self.value_type,
            "value": self.value,
            "coverage": self.coverage,
            "evidence_ref": self.evidence_ref,
            "adapter_version": self.adapter_version,
            "reason_code": self.reason_code,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Observation":
        return cls(
            observation_id=data["observation_id"],
            status=data["status"],
            value_type=data.get("value_type", "count"),
            value=data.get("value"),
            freshness=data.get("freshness", FRESH),
            provider=data.get("provider", "unknown"),
            collected_at=data.get("collected_at"),
            source_ref=data.get("source_ref"),
            coverage=data.get("coverage"),
            evidence_ref=data.get("evidence_ref"),
            adapter_version=data.get("adapter_version"),
            reason_code=data.get("reason_code"),
            notes=data.get("notes"),
            schema_version=data.get("schema_version", OBSERVATION_CONTRACT_VERSION),
        )


@dataclass
class Receipt:
    """Collection receipt: distinguishes not requested, requested-but-unknown and observed zero.

    It records *what* was asked for and what came back, never *how* the answers
    were fetched. The number of HTTP calls a run needed is a property of the
    client and its cache, not of the evidence. Successor bundles retain only
    ``identity()``; invocation fields and counters live in the external
    ``execution()`` receipt. ``to_dict()`` preserves the historical v2 shape.
    """

    run_id: str
    collector_version: str
    target: dict[str, Any]
    started_at: str
    ended_at: str
    requested_keys: list[str] = field(default_factory=list)
    returned_keys: list[str] = field(default_factory=list)
    per_key: dict[str, dict[str, str]] = field(default_factory=dict)
    capability_notes: list[str] = field(default_factory=list)
    config_hash: str | None = None
    coverage: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)

    def identity(self, coverage: dict[str, Any] | None = None) -> dict[str, Any]:
        """Material acquisition provenance; invocation mechanics have no path here."""
        result = {
            "schema": RECEIPT_IDENTITY_SCHEMA,
            "contract": RECEIPT_IDENTITY_CONTRACT,
            "collector_version": self.collector_version,
            "target": dict(self.target),
            "requested_keys": sorted(set(self.requested_keys)),
            "returned_keys": sorted(set(self.returned_keys)),
            "per_key": {key: dict(self.per_key[key]) for key in sorted(self.per_key)},
            "capability_notes": sorted(set(material_capability(n) for n in self.capability_notes)),
            "coverage": dict(self.coverage, **(coverage or {})),
            "config_hash": self.config_hash,
        }
        validate_receipt_identity(result)
        return result

    def execution(self, bundle_id: str | None = None, run_meta=None, receipt_identity=None) -> dict[str, Any]:
        """Current invocation audit, returned outside immutable bundle storage."""
        return {"schema": EXECUTION_RECEIPT_SCHEMA, "run_id": self.run_id,
                "started_at": self.started_at, "ended_at": self.ended_at,
                "result_bundle_id": bundle_id, "diagnostics": list(self.diagnostics) +
                [n for n in self.capability_notes if n.startswith("REQUEST_BUDGET_EXHAUSTED:")],
                "run_meta": dict(run_meta or {}), "receipt_identity": receipt_identity or self.identity()}

    @classmethod
    def from_identity(cls, data):
        validate_receipt_identity(data)
        return cls(run_id="", started_at="", ended_at="",
                   collector_version=data["collector_version"], target=dict(data["target"]),
                   requested_keys=list(data["requested_keys"]), returned_keys=list(data["returned_keys"]),
                   per_key={k: dict(v) for k, v in data["per_key"].items()},
                   capability_notes=list(data["capability_notes"]), config_hash=data["config_hash"],
                   coverage=dict(data["coverage"]))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RECEIPT_SCHEMA,
            "run_id": self.run_id,
            "collector_version": self.collector_version,
            "target": self.target,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "requested_keys": sorted(self.requested_keys),
            "returned_keys": sorted(self.returned_keys),
            "per_key": {key: dict(self.per_key[key]) for key in sorted(self.per_key)},
            "capability_notes": sorted(set(self.capability_notes)),
            "config_hash": self.config_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Receipt":
        return cls(
            run_id=data["run_id"],
            collector_version=data.get("collector_version", "unknown"),
            target=data.get("target", {}),
            started_at=data.get("started_at", ""),
            ended_at=data.get("ended_at", ""),
            requested_keys=list(data.get("requested_keys", [])),
            returned_keys=list(data.get("returned_keys", [])),
            per_key={k: dict(v) for k, v in data.get("per_key", {}).items()},
            capability_notes=list(data.get("capability_notes", [])),
            config_hash=data.get("config_hash"),
        )


class ObservationSet:
    """All observations of one subject at one ``observed_at`` plus the receipt."""

    def __init__(
        self,
        subject: dict[str, Any],
        observed_at: str,
        observations: Iterable[Observation] = (),
        receipt: Receipt | None = None,
    ) -> None:
        self.subject = dict(subject)
        self.observed_at = observed_at
        self._items: dict[str, Observation] = {}
        self.receipt = receipt
        for item in observations:
            self.add(item)

    def add(self, item: Observation) -> None:
        if item.observation_id in self._items:
            raise ObservationError(f"duplicate observation {item.observation_id}")
        self._items[item.observation_id] = item

    def replace(self, item: Observation) -> None:
        self._items[item.observation_id] = item

    def __contains__(self, observation_id: str) -> bool:
        return observation_id in self._items

    def __iter__(self):
        return iter(self.sorted())

    def __len__(self) -> int:
        return len(self._items)

    def ids(self) -> list[str]:
        return sorted(self._items)

    def sorted(self) -> list[Observation]:
        return [self._items[key] for key in sorted(self._items)]

    def get(self, observation_id: str) -> Observation | None:
        return self._items.get(observation_id)

    def status_of(self, observation_id: str) -> str:
        item = self._items.get(observation_id)
        return item.status if item else NOT_REQUESTED

    def freshness_of(self, observation_id: str) -> str:
        item = self._items.get(observation_id)
        return item.freshness if item else FRESHNESS_UNKNOWN

    def is_good(self, observation_id: str) -> bool:
        item = self._items.get(observation_id)
        return bool(item and item.good)

    def is_explicitly(self, observation_id: str, status: str) -> bool:
        item = self._items.get(observation_id)
        return bool(item and item.status == status)

    def value_of(self, observation_id: str, default: Any = None) -> Any:
        item = self._items.get(observation_id)
        if item is None or not item.has_value:
            return default
        return item.value

    def finalize_receipt(self, receipt: Receipt) -> Receipt:
        receipt.requested_keys = sorted(set(receipt.requested_keys) | set(self._items))
        receipt.returned_keys = [key for key in sorted(self._items) if self._items[key].has_value]
        receipt.per_key = {
            key: {"status": self._items[key].status, "freshness": self._items[key].freshness}
            for key in sorted(self._items)
        }
        self.receipt = receipt
        return receipt

    def receipt_identity(self):
        if self.receipt is None:
            return None
        coverage = {key: self._items[key].coverage for key in self.receipt.requested_keys
                    if key in self._items and self._items[key].coverage is not None}
        return self.receipt.identity(coverage)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": OBSERVATIONS_SCHEMA,
            "observation_contract_version": OBSERVATION_CONTRACT_VERSION,
            "subject": self.subject,
            "observed_at": self.observed_at,
            "observations": [item.to_dict() for item in self.sorted()],
            "receipt_identity": self.receipt_identity(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ObservationSet":
        if not isinstance(data, dict) or data.get("observation_contract_version") != OBSERVATION_CONTRACT_VERSION:
            raise ObservationError("observations: unsupported observation contract")
        schema = data.get("schema")
        if schema == OBSERVATIONS_SCHEMA:
            if "receipt" in data or "receipt_identity" not in data:
                raise ObservationError("observations: mixed receipt lineage")
            receipt = Receipt.from_identity(data["receipt_identity"]) if data["receipt_identity"] else None
        elif schema == "devostasis.observations.v1":
            if "receipt_identity" in data:
                raise ObservationError("observations: mixed receipt lineage")
            receipt = Receipt.from_dict(data["receipt"]) if data.get("receipt") else None
        else:
            raise ObservationError("observations: unsupported schema")
        return cls(
            subject=data.get("subject", {}),
            observed_at=data["observed_at"],
            observations=[Observation.from_dict(item) for item in data.get("observations", [])],
            receipt=receipt,
        )

    def save(self, path: str | Path) -> None:
        canonical.write_pretty(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path) -> "ObservationSet":
        return cls.from_dict(canonical.load_file(path))

    def digest(self) -> str:
        return canonical.digest(self.to_dict())


def material_capability(note):
    """Preserve exhaustion as evidence; its numeric request limit is mechanics."""
    if not isinstance(note, str):
        raise ObservationError("capability note must be a semantic string")
    if note.startswith("REQUEST_BUDGET_EXHAUSTED:"):
        if not note.split(":", 1)[1].isdigit():
            raise ObservationError("ambiguous request-budget capability note")
        return "REQUEST_BUDGET_EXHAUSTED"
    return note


def validate_receipt_identity(value):
    required = {"schema", "contract", "collector_version", "target", "requested_keys",
                "returned_keys", "per_key", "capability_notes", "coverage", "config_hash"}
    def check(ok, message):
        if not ok:
            raise ObservationError("receipt_identity: " + message)
    check(isinstance(value, dict) and set(value) == required, "missing or unknown fields")
    check(value["schema"] == RECEIPT_IDENTITY_SCHEMA and value["contract"] == RECEIPT_IDENTITY_CONTRACT,
          "unsupported lineage")
    check(isinstance(value["collector_version"], str) and bool(value["collector_version"]), "collector version required")
    check(isinstance(value["target"], dict), "target must be an object")
    for key in ("requested_keys", "returned_keys", "capability_notes"):
        entries = value[key]
        check(isinstance(entries, list) and all(isinstance(x, str) and x for x in entries), key + " must be strings")
        check(entries == sorted(set(entries)), key + " must be unique and sorted")
    requested = set(value["requested_keys"])
    check(all(material_capability(n) == n for n in value["capability_notes"]), "invocation accounting in capability facts")
    check(set(value["returned_keys"]) <= requested, "returned key was not requested")
    check(isinstance(value["per_key"], dict) and set(value["per_key"]) <= requested, "per-key scope mismatch")
    for meta in value["per_key"].values():
        check(isinstance(meta, dict) and set(meta) == {"status", "freshness"}, "invalid per-key fields")
        check(isinstance(meta["status"], str) and meta["status"] in STATUSES and
              isinstance(meta["freshness"], str) and meta["freshness"] in FRESHNESSES, "invalid acquisition state")
    check(isinstance(value["coverage"], dict) and set(value["coverage"]) <= requested and
          all(isinstance(x, dict) for x in value["coverage"].values()), "invalid coverage")
    check(value["config_hash"] is None or isinstance(value["config_hash"], str), "invalid config hash")
    canonical.canonical_bytes(value)
    return value


def subset_count_problem(item: Observation) -> str | None:
    """Why a PARTIAL count is not a proven observed-subset lower bound, or None when it is.

    Proof is the coverage the envelope carries: ``complete`` false and
    ``value_semantics`` ``OBSERVED_SUBSET_COUNT``, over a non-negative integer
    value. Missing semantics is not proof; other semantics (an estimate, an
    aggregate, anything not monotone in the records returned) is proof of the
    opposite; malformed or self-contradicting coverage is neither, and is
    reported as such rather than raised.
    """
    coverage = item.coverage
    if coverage is None:
        return SUBSET_NOT_PROVEN
    if not isinstance(coverage, dict):
        return COVERAGE_MALFORMED
    complete = coverage.get("complete")
    if complete is True:
        return COVERAGE_CONTRADICTORY
    semantics = coverage.get(VALUE_SEMANTICS)
    if semantics is None:
        return SUBSET_NOT_PROVEN
    if not isinstance(semantics, str) or complete is not False:
        return COVERAGE_MALFORMED
    if semantics != OBSERVED_SUBSET_COUNT:
        return f"{NOT_A_SUBSET}:{semantics}"
    if isinstance(item.value, bool) or not isinstance(item.value, int) or item.value < 0:
        return VALUE_NOT_A_COUNT
    return None


def unavailable(observation_id: str, value_type: str, reason_code: str, **extra: Any) -> Observation:
    return Observation(observation_id=observation_id, status=UNAVAILABLE, value_type=value_type, reason_code=reason_code, **extra)


def forbidden(observation_id: str, value_type: str, reason_code: str, **extra: Any) -> Observation:
    return Observation(observation_id=observation_id, status=FORBIDDEN, value_type=value_type, reason_code=reason_code, **extra)


def unknown(observation_id: str, value_type: str, reason_code: str, **extra: Any) -> Observation:
    return Observation(observation_id=observation_id, status=UNKNOWN, value_type=value_type, reason_code=reason_code, **extra)


def error(observation_id: str, value_type: str, reason_code: str, **extra: Any) -> Observation:
    return Observation(observation_id=observation_id, status=ERROR, value_type=value_type, reason_code=reason_code, **extra)
