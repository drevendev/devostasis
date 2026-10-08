"""Executable conformance vectors: the format and the runner (``devostasis.vectors.v1``).

A conformance case is a claim about behaviour. Written in prose it can only be
checked by a person reading both the sentence and the code; written as a vector
it is a JSON document that states the evidence and the expected result, and the
runner executes it against this implementation. The specification names cases
that no test covers (debt D-1, target B1); the vectors of ``PV-TEST-001`` are
authored against this format so that they arrive executable instead of needing
translation.

A vector file is::

    {"schema": "devostasis.vectors.v1", "notes": "...", "vectors": [ <vector>, ... ]}

and a vector is::

    {"case": "ORDER-01", "title": "...", "kind": "vital" | "delta" | "ci" | "activity",
     "source_unit": "PV-BAND-ORDER-001", "given": {...}, "expect": {...}}

``kind`` selects what is executed:

* **vital** evaluates one Vital over an observation set built from raw
  observation envelopes (``RAW_OBSERVATION_CONTRACT_V0``), so a vector states
  evidence exactly as a collector would emit it. With ``derive`` the
  provider-neutral derivation runs first, so a case about how inventories
  become aggregates (a change request linked to a closed target, a partial
  target enumeration) is executed at that boundary rather than over counts
  somebody pre-derived. ``expect.rejected`` states that the evidence must be
  refused before classification (``InadmissibleEvidence``), the outcome the
  totality contracts give contradictory normalized input.
* **delta** compares two snapshots given as partial Vital rows and checks the
  transition classes and reason codes. An accepted case often names more than
  one pair — "``GRIDLOCKED -> CONGESTED -> MOVING`` follows WORSENED/IMPROVED
  direction" is four comparisons — so ``given`` may carry ``comparisons``, a
  list of pairs each with its own ``expect``, instead of a single
  ``previous``/``current``. One case id then reports one result over every pair
  the case names, rather than splitting an accepted identifier across several.
* **ci** starts one stage earlier than ``vital``: it runs the provider-native
  verification normalization (outcome map, parent identity, one record per
  immutable revision) over workflow runs, their earlier attempts and check
  suites exactly as the provider reports them, checks the canonical revision
  records, and optionally evaluates Integrity over them. A case about the
  normalization contract (``R5``..``R10``) is executed at the boundary it is
  about, instead of over verdicts somebody pre-normalized.
* **activity** builds the activity member over raw inventories and a previous
  bundle's ``observed_at``, and checks the interval it declares and the coverage
  it discloses (``ACT-COV-01``..``05``).

A case that names one obligation over several evidence shapes states them as
``variants`` (``vital`` and ``ci``): every variant is executed against the one
``expect`` of the case, and the case passes only when all of them do, so a
provider-alias equivalence or a substitution matrix keeps its one identifier.

Three rules keep a vector suite honest:

* **It fails closed.** An unknown ``kind``, an unknown key, an unknown
  comparison status, a malformed envelope or a duplicate case id is an error,
  never a skip: a vector that cannot run must never look like a vector that
  passed.
* **It states, never computes.** Expectations are literal values. A vector
  that derived its expectation from the implementation would prove only that
  the implementation equals itself.
* **Every expectation is checked.** Absent keys are not checked, but a key that
  is present is asserted, and unknown expectation keys are rejected rather than
  quietly ignored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .activity import build_activity
from .adapters import github_ci
from .contracts import CORE_VITAL_IDS, VECTOR_SCHEMA
from .delta import BASELINE, COMPARABLE, HISTORY_GAP, INCOMPARABLE, compare
from .normalize import derive as derive_aggregates
from .observations import AVAILABLE, PARTIAL, STATUSES, Observation, ObservationSet
from .vitals import EVALUATORS
from .vitals.common import InadmissibleEvidence

KINDS = ("vital", "delta", "ci", "activity")
COMPARISON_STATUSES = (BASELINE, COMPARABLE, HISTORY_GAP, INCOMPARABLE)
CI_PROVIDERS = ("github",)

FILE_KEYS = {"schema", "notes", "vectors"}
VECTOR_KEYS = {"case", "title", "kind", "source_unit", "notes", "given", "expect"}
# ``expect`` is required by every kind, but a delta case that states several
# comparisons carries one expectation per comparison instead of one for the
# vector, so the kind validators require it rather than this set.
REQUIRED_VECTOR_KEYS = {"case", "title", "kind", "given"}

VITAL_GIVEN_KEYS = {"vital", "observations", "observed_at", "subject", "variants", "derive"}
VITAL_VARIANT_KEYS = {"title", "observations"}
# The configuration the derivation reads: where planning targets come from and
# the explicit debt mapping, the two project settings normalize.derive consults.
DERIVE_KEYS = {"planning_source", "debt_mapping"}
PLANNING_SOURCES = ("none", "milestones", "file")
VITAL_EXPECT_KEYS = {
    "band",
    "evaluation_status",
    "band_semantics",
    "possible_bands",
    "rule_id",
    "derived",
    "derived_absent",
    "diagnostics",
    "diagnostics_absent",
    "explanation_contains",
    "shared_signal_groups",
    "dependency_group_ids",
    "rejected",
}
REQUIRED_VITAL_EXPECT_KEYS = {"band", "evaluation_status"}

DELTA_GIVEN_KEYS = {"comparison_status", "previous", "current", "previous_bundle_id", "incomparable_reasons", "comparisons"}
DELTA_PAIR_KEYS = {"comparison_status", "previous", "current", "previous_bundle_id", "incomparable_reasons"}
DELTA_COMPARISON_KEYS = DELTA_PAIR_KEYS | {"title", "expect"}
DELTA_SIDE_KEYS = {"observed_at", "vitals"}
DELTA_ROW_KEYS = {"vital_id", "band", "evaluation_status", "band_semantics", "rule_id", "derived", "inputs"}
DELTA_EXPECT_KEYS = {"comparison_status", "vitals"}
DELTA_ROW_EXPECT_KEYS = {"transition_class", "reason_codes", "reason_codes_absent", "metric_deltas", "coverage_delta"}

CI_EVIDENCE_KEYS = {"revisions", "actions_runs", "check_suites"}
CI_SETTING_KEYS = {"provider", "observed_at", "configured", "series_status"}
CI_GIVEN_KEYS = CI_EVIDENCE_KEYS | CI_SETTING_KEYS | {"variants"}
CI_VARIANT_KEYS = CI_EVIDENCE_KEYS | CI_SETTING_KEYS | {"title"}
CI_EXPECT_KEYS = {"revisions", "integrity"}
CI_REVISION_EXPECT_KEYS = {"current_verdict", "history_state", "historical_contribution", "history_provenance", "parents"}
CI_PARENT_EXPECT_KEYS = {"parent_id", "kind", "current_state", "history_state", "current_attempt", "attempts_observed", "attempts_complete"}

ACTIVITY_GIVEN_KEYS = {"observations", "observed_at", "previous_observed_at", "list_cap", "subject"}
ACTIVITY_EXPECT_KEYS = {"interval", "coverage_notes", "coverage_notes_absent", "classes", "truncated"}
ACTIVITY_INTERVAL_KEYS = {"start", "end", "basis", "exclusive_start"}

DEFAULT_OBSERVED_AT = "2026-01-01T00:00:00Z"
DEFAULT_SUBJECT = {
    "provider": "vector",
    "forge_instance": "vector.invalid",
    "owner": "vector",
    "repo": "vector",
    "display_locator": "vector/vector",
    "immutable_project_id": "vector",
    "default_branch": "master",
    "visibility": "public",
}


class VectorError(ValueError):
    """Raised when a vector file cannot be read as a valid vector document."""


@dataclass(frozen=True)
class Vector:
    case: str
    title: str
    kind: str
    given: dict[str, Any]
    expect: dict[str, Any]
    source_unit: str | None = None
    notes: str | None = None
    path: str = ""

    @property
    def label(self) -> str:
        return f"{self.case} ({self.kind})"


@dataclass
class VectorResult:
    vector: Vector
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def case(self) -> str:
        return self.vector.case

    def report(self) -> str:
        head = f"{'PASS' if self.ok else 'FAIL'} {self.vector.case:<16} {self.vector.title}"
        return "\n".join([head] + [f"     - {failure}" for failure in self.failures])


# --------------------------------------------------------------------------- loading


def _require_keys(where: str, data: Any, allowed: set[str], required: set[str]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise VectorError(f"{where}: expected an object, got {type(data).__name__}")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise VectorError(f"{where}: unknown keys {unknown}")
    missing = sorted(required - set(data))
    if missing:
        raise VectorError(f"{where}: missing keys {missing}")
    return data


def _require_variants(where: str, given: dict[str, Any], own_keys: set[str], variant_keys: set[str], required: set[str]) -> None:
    """``variants`` replaces the evidence keys of ``given`` with a list of at least two evidence shapes."""
    if set(given) & own_keys:
        raise VectorError(f"{where} given: variants replaces {sorted(own_keys)}, it does not extend them")
    variants = given["variants"]
    if not isinstance(variants, list) or len(variants) < 2:
        raise VectorError(f"{where} given: variants must be a list of at least two evidence shapes; one shape is stated inline")
    for index, variant in enumerate(variants):
        _require_keys(f"{where} variant[{index}]", variant, variant_keys, required)


def _validate_observations(where: str, observations: Any) -> None:
    if not isinstance(observations, list) or not observations:
        raise VectorError(f"{where}: observations must be a non-empty list")


CODE_LIST_KEYS = ("diagnostics", "diagnostics_absent", "reason_codes", "reason_codes_absent", "coverage_notes", "coverage_notes_absent")


def _require_statement(where: str, holder: dict[str, Any], keys: tuple[str, ...]) -> None:
    """An expectation that states nothing cannot fail, so it is refused.

    An empty object or list asserts nothing, and an empty code matches every
    code emitted (codes match by prefix): either would let a typo or an
    unfinished case pass as proof.
    """
    for key in keys:
        if key not in holder:
            continue
        value = holder[key]
        if isinstance(value, (dict, list)) and not value:
            raise VectorError(f"{where}: {key} is empty and states nothing")
        if key in CODE_LIST_KEYS:
            if not isinstance(value, list):
                raise VectorError(f"{where}: {key} must be a list of codes")
            for code in value:
                if not isinstance(code, str) or not code:
                    raise VectorError(f"{where}: {key} holds {code!r}, which is not a code (an empty prefix matches everything)")


def _validate_vital_expect(where: str, expect: Any) -> None:
    if expect is None:
        raise VectorError(f"{where}: missing keys ['expect']")
    if isinstance(expect, dict) and "rejected" in expect:
        # A refused evaluation has no band, status or metrics to check: the
        # rejection code is the whole expectation.
        if set(expect) != {"rejected"}:
            raise VectorError(f"{where} expect: rejected is the whole expectation of a refused evaluation, not combined with {sorted(set(expect) - {'rejected'})}")
        if not isinstance(expect["rejected"], str) or not expect["rejected"]:
            raise VectorError(f"{where} expect: rejected must name the rejection code (an empty prefix matches everything)")
        return
    _require_keys(f"{where} expect", expect, VITAL_EXPECT_KEYS, REQUIRED_VITAL_EXPECT_KEYS)
    _require_statement(f"{where} expect", expect, ("derived",) + CODE_LIST_KEYS)


def _validate_derive(where: str, derive: Any) -> None:
    _require_keys(f"{where} given.derive", derive, DERIVE_KEYS, {"planning_source"})
    if derive["planning_source"] not in PLANNING_SOURCES:
        raise VectorError(f"{where} given.derive: planning_source {derive['planning_source']!r} is not one of {list(PLANNING_SOURCES)}")
    mapping = derive.get("debt_mapping")
    if mapping is not None and not isinstance(mapping, dict):
        raise VectorError(f"{where} given.derive: debt_mapping is an object or null")


def _validate_vital(where: str, given: dict[str, Any], expect: Any) -> None:
    _require_keys(f"{where} given", given, VITAL_GIVEN_KEYS, {"vital"})
    if given["vital"] not in EVALUATORS:
        raise VectorError(f"{where} given: unknown vital {given['vital']!r}")
    if "derive" in given:
        _validate_derive(where, given["derive"])
    if "variants" in given:
        _require_variants(where, given, {"observations"}, VITAL_VARIANT_KEYS, {"observations"})
        for index, variant in enumerate(given["variants"]):
            _validate_observations(f"{where} variant[{index}]", variant["observations"])
    else:
        if "observations" not in given:
            raise VectorError(f"{where} given: missing keys ['observations']")
        _validate_observations(f"{where} given", given["observations"])
    _validate_vital_expect(where, expect)


def _comparison_status(where: str, holder: dict[str, Any]) -> None:
    """A comparison status the engine does not know is an error, not a silently different run."""
    status = holder.get("comparison_status")
    if status is not None and status not in COMPARISON_STATUSES:
        raise VectorError(f"{where}: unknown comparison_status {status!r}, known are {list(COMPARISON_STATUSES)}")


def _validate_delta_pair(where: str, pair: dict[str, Any], expect: Any) -> None:
    _comparison_status(f"{where} given", pair)
    for side in ("previous", "current"):
        rows = _require_keys(f"{where} given.{side}", pair[side], DELTA_SIDE_KEYS, {"vitals"})["vitals"]
        if not isinstance(rows, list) or not rows:
            raise VectorError(f"{where} given.{side}: vitals must be a non-empty list")
        for row in rows:
            _require_keys(f"{where} given.{side} row", row, DELTA_ROW_KEYS, {"vital_id", "band"})
            if row["vital_id"] not in CORE_VITAL_IDS:
                raise VectorError(f"{where} given.{side}: unknown vital {row['vital_id']!r}")
    rows_expect = _require_keys(f"{where} expect", expect, DELTA_EXPECT_KEYS, {"vitals"})["vitals"]
    _comparison_status(f"{where} expect", expect)
    if not isinstance(rows_expect, dict) or not rows_expect:
        raise VectorError(f"{where} expect: vitals must be a non-empty object keyed by vital id")
    for vital_id, row in rows_expect.items():
        if vital_id not in CORE_VITAL_IDS:
            raise VectorError(f"{where} expect: unknown vital {vital_id!r}")
        _require_keys(f"{where} expect.{vital_id}", row, DELTA_ROW_EXPECT_KEYS, {"transition_class"})
        _require_statement(f"{where} expect.{vital_id}", row, CODE_LIST_KEYS)


def _validate_delta(where: str, given: dict[str, Any], expect: Any) -> None:
    _require_keys(f"{where} given", given, DELTA_GIVEN_KEYS, set())
    if "comparisons" in given:
        if set(given) & DELTA_PAIR_KEYS:
            raise VectorError(f"{where} given: comparisons replaces previous/current, it does not extend them")
        if expect is not None:
            raise VectorError(f"{where}: a case with comparisons states one expect per comparison, not one for the vector")
        comparisons = given["comparisons"]
        if not isinstance(comparisons, list) or len(comparisons) < 2:
            raise VectorError(f"{where} given: comparisons must be a list of at least two pairs; one pair is previous/current")
        for index, comparison in enumerate(comparisons):
            label = f"{where} comparison[{index}]"
            entry = _require_keys(label, comparison, DELTA_COMPARISON_KEYS, {"previous", "current", "expect"})
            _validate_delta_pair(label, entry, entry["expect"])
        return
    missing = sorted({"previous", "current"} - set(given))
    if missing:
        raise VectorError(f"{where} given: missing keys {missing}")
    if expect is None:
        raise VectorError(f"{where}: missing keys ['expect']")
    _validate_delta_pair(where, given, expect)


def _validate_ci_evidence(where: str, shape: dict[str, Any]) -> None:
    provider = shape.get("provider", "github")
    if provider not in CI_PROVIDERS:
        raise VectorError(f"{where}: provider {provider!r} has no CI normalization in this version; known are {list(CI_PROVIDERS)}")
    status = shape.get("series_status", AVAILABLE)
    if status not in STATUSES:
        raise VectorError(f"{where}: unknown series_status {status!r}")
    revisions = shape.get("revisions")
    if not isinstance(revisions, list) or not revisions:
        raise VectorError(f"{where}: revisions must be a non-empty list of {{sha, committed_at}}")
    for revision in revisions:
        _require_keys(f"{where} revision", revision, {"sha", "committed_at"}, {"sha", "committed_at"})
    for run in shape.get("actions_runs") or []:
        if not isinstance(run, dict) or "head_sha" not in run or "id" not in run:
            raise VectorError(f"{where}: every actions run needs at least id and head_sha")
    suites = shape.get("check_suites") or {}
    if not isinstance(suites, dict) or any(not isinstance(v, list) for v in suites.values()):
        raise VectorError(f"{where}: check_suites must be an object of sha -> list of suites")


def _validate_ci(where: str, given: dict[str, Any], expect: Any) -> None:
    _require_keys(f"{where} given", given, CI_GIVEN_KEYS, set())
    if "variants" in given:
        _require_variants(where, given, CI_EVIDENCE_KEYS, CI_VARIANT_KEYS, {"revisions"})
        for index, variant in enumerate(given["variants"]):
            _validate_ci_evidence(f"{where} variant[{index}]", dict(given, **variant))
    else:
        if "revisions" not in given:
            raise VectorError(f"{where} given: missing keys ['revisions']")
        _validate_ci_evidence(f"{where} given", given)
    if expect is None:
        raise VectorError(f"{where}: missing keys ['expect']")
    _require_keys(f"{where} expect", expect, CI_EXPECT_KEYS, set())
    if not expect:
        raise VectorError(f"{where} expect: states nothing; a ci case checks revisions, integrity or both")
    _require_statement(f"{where} expect", expect, ("revisions", "integrity"))
    for sha, row in (expect.get("revisions") or {}).items():
        _require_keys(f"{where} expect.revisions.{sha}", row, CI_REVISION_EXPECT_KEYS, set())
        if not row:
            raise VectorError(f"{where} expect.revisions.{sha}: states nothing")
        _require_statement(f"{where} expect.revisions.{sha}", row, ("parents",))
        for index, parent in enumerate(row.get("parents") or []):
            _require_keys(f"{where} expect.revisions.{sha}.parents[{index}]", parent, CI_PARENT_EXPECT_KEYS, set())
            if not parent:
                raise VectorError(f"{where} expect.revisions.{sha}.parents[{index}]: states nothing")
    if "integrity" in expect:
        _validate_vital_expect(f"{where} integrity", expect["integrity"])


def _validate_activity(where: str, given: dict[str, Any], expect: Any) -> None:
    _require_keys(f"{where} given", given, ACTIVITY_GIVEN_KEYS, {"observations"})
    _validate_observations(f"{where} given", given["observations"])
    cap = given.get("list_cap", 50)
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
        raise VectorError(f"{where} given: list_cap must be a non-negative integer")
    if expect is None:
        raise VectorError(f"{where}: missing keys ['expect']")
    _require_keys(f"{where} expect", expect, ACTIVITY_EXPECT_KEYS, set())
    if not expect:
        raise VectorError(f"{where} expect: states nothing")
    _require_statement(f"{where} expect", expect, ("interval", "classes") + CODE_LIST_KEYS)
    if "interval" in expect:
        _require_keys(f"{where} expect.interval", expect["interval"], ACTIVITY_INTERVAL_KEYS, set())
    for name, counts in (expect.get("classes") or {}).items():
        if not isinstance(counts, dict):
            raise VectorError(f"{where} expect.classes.{name}: expected an object of counts")


VALIDATORS = {"vital": _validate_vital, "delta": _validate_delta, "ci": _validate_ci, "activity": _validate_activity}


def parse_document(document: Any, path: str = "") -> list[Vector]:
    """Every vector of one parsed file, validated structurally. Fails closed."""
    where = path or "<document>"
    data = _require_keys(where, document, FILE_KEYS, {"schema", "vectors"})
    if data["schema"] != VECTOR_SCHEMA:
        raise VectorError(f"{where}: schema {data['schema']!r} is not {VECTOR_SCHEMA}")
    if not isinstance(data["vectors"], list) or not data["vectors"]:
        raise VectorError(f"{where}: vectors must be a non-empty list")
    parsed: list[Vector] = []
    for index, item in enumerate(data["vectors"]):
        label = f"{where}[{index}]"
        entry = _require_keys(label, item, VECTOR_KEYS, REQUIRED_VECTOR_KEYS)
        case = entry["case"]
        if not isinstance(case, str) or not case:
            raise VectorError(f"{label}: case must be a non-empty string")
        kind = entry["kind"]
        if kind not in KINDS:
            raise VectorError(f"{where}[{case}]: unknown kind {kind!r}, known kinds are {list(KINDS)}")
        VALIDATORS[kind](f"{where}[{case}]", entry["given"], entry.get("expect"))
        parsed.append(
            Vector(
                case=case,
                title=entry["title"],
                kind=kind,
                given=entry["given"],
                expect=entry.get("expect") or {},
                source_unit=entry.get("source_unit"),
                notes=entry.get("notes"),
                path=path,
            )
        )
    return parsed


def load_file(path: str | Path) -> list[Vector]:
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VectorError(f"{path}: {exc}") from exc
    return parse_document(document, str(path))


def load(paths: Iterable[str | Path]) -> list[Vector]:
    """Vectors of every given file or directory, ordered by case id, with unique case ids."""
    files: list[Path] = []
    for entry in paths:
        entry = Path(entry)
        if entry.is_dir():
            files.extend(sorted(entry.rglob("*.json")))
        elif entry.exists():
            files.append(entry)
        else:
            raise VectorError(f"{entry}: no such file or directory")
    vectors: list[Vector] = []
    seen: dict[str, str] = {}
    for file in files:
        for vector in load_file(file):
            if vector.case in seen:
                raise VectorError(f"duplicate case {vector.case} in {vector.path} and {seen[vector.case]}")
            seen[vector.case] = vector.path
            vectors.append(vector)
    return sorted(vectors, key=lambda vector: (vector.case, vector.path))


# --------------------------------------------------------------------------- execution


def _observation_set(given: dict[str, Any], case: str, observations: list[dict[str, Any]] | None = None) -> ObservationSet:
    observed_at = given.get("observed_at", DEFAULT_OBSERVED_AT)
    obs = ObservationSet(subject=dict(given.get("subject") or DEFAULT_SUBJECT), observed_at=observed_at)
    for envelope in observations if observations is not None else given["observations"]:
        if not isinstance(envelope, dict) or "observation_id" not in envelope:
            raise VectorError(f"{case}: an observation envelope needs an observation_id")
        filled = dict(envelope)
        filled.setdefault("status", "AVAILABLE")
        filled.setdefault("provider", "vector")
        filled.setdefault("collected_at", observed_at)
        filled.setdefault("source_ref", f"vector:{case}")
        filled.setdefault("adapter_version", VECTOR_SCHEMA)
        obs.add(Observation.from_dict(filled))
    return obs


def _matches(expected: str, emitted: list[str]) -> bool:
    """A code expectation matches a code it equals or is a prefix of."""
    return any(code == expected or code.startswith(expected) for code in emitted)


def _check_codes(kind: str, expected: Any, absent: Any, emitted: list[str], failures: list[str]) -> None:
    for code in expected or []:
        if not _matches(code, emitted):
            failures.append(f"{kind}: expected {code!r}, emitted {emitted}")
    for code in absent or []:
        if _matches(code, emitted):
            failures.append(f"{kind}: {code!r} must not be emitted, emitted {emitted}")


def _check_equal(what: str, expected: Any, actual: Any, failures: list[str]) -> None:
    if expected != actual:
        failures.append(f"{what}: expected {expected!r}, got {actual!r}")


def _check_vital_result(result: dict[str, Any], expect: dict[str, Any], failures: list[str], where: str = "") -> None:
    """Every expectation a vital case may state, against one evaluator result."""
    for key in ("band", "evaluation_status", "band_semantics", "possible_bands", "rule_id", "shared_signal_groups", "dependency_group_ids"):
        if key in expect:
            _check_equal(f"{where}{key}", expect[key], result.get(key), failures)
    for key, value in (expect.get("derived") or {}).items():
        if key not in result["derived"]:
            failures.append(f"{where}derived.{key}: expected {value!r}, the Vital derived no such metric")
        else:
            _check_equal(f"{where}derived.{key}", value, result["derived"][key], failures)
    for key in expect.get("derived_absent") or []:
        if key in result["derived"]:
            failures.append(f"{where}derived.{key}: must be absent, got {result['derived'][key]!r}")
    _check_codes(f"{where}diagnostics", expect.get("diagnostics"), expect.get("diagnostics_absent"), result["diagnostics"], failures)
    for text in expect.get("explanation_contains") or []:
        if text not in result["explanation"]:
            failures.append(f"{where}explanation: {text!r} not in {result['explanation']!r}")


def _vital_shapes(given: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    if "variants" in given:
        return [(f"{variant.get('title') or index}: ", variant["observations"]) for index, variant in enumerate(given["variants"])]
    return [("", given["observations"])]


@dataclass(frozen=True)
class _DeriveScope:
    """The two project settings the derivation reads, stated by a vector instead of a configuration file."""

    planning_source: str
    debt_mapping: dict[str, Any] | None


def _run_vital(vector: Vector) -> list[str]:
    """One case, every evidence shape it names. A case passes only when all of them do."""
    failures: list[str] = []
    derive = vector.given.get("derive")
    for where, observations in _vital_shapes(vector.given):
        obs = _observation_set(vector.given, vector.case, observations)
        if derive is not None:
            derive_aggregates(obs, _DeriveScope(derive["planning_source"], derive.get("debt_mapping")))
        _evaluate_and_check(EVALUATORS[vector.given["vital"]], obs, vector.expect, failures, where)
    return failures


def _evaluate_and_check(evaluator: Any, obs: ObservationSet, expect: dict[str, Any], failures: list[str], where: str) -> None:
    """Evaluate one Vital and check the result, or check that the evidence is refused when the case says it must be."""
    if "rejected" not in expect:
        _check_vital_result(evaluator(obs).to_dict(), expect, failures, where)
        return
    try:
        result = evaluator(obs).to_dict()
    except InadmissibleEvidence as exc:
        if not _matches(expect["rejected"], [exc.code]):
            failures.append(f"{where}rejected: expected {expect['rejected']!r}, the evidence was refused with {exc.code!r}")
        return
    failures.append(f"{where}rejected: expected the evidence to be refused with {expect['rejected']!r}, it evaluated to {result['band']} / {result['evaluation_status']}")


def _delta_row(row: dict[str, Any]) -> dict[str, Any]:
    """A partial Vital row completed with the defaults a vector may leave out."""
    band = row.get("band")
    return {
        "vital_id": row["vital_id"],
        "band": band,
        "evaluation_status": row.get("evaluation_status", "AVAILABLE" if band is not None else "UNKNOWN"),
        "band_semantics": row.get("band_semantics", "EXACT" if band is not None else None),
        "rule_id": row.get("rule_id", f"{row['vital_id']}.vector"),
        "derived": row.get("derived") or {},
        "inputs": row.get("inputs") or [],
    }


def _delta_side(side: dict[str, Any]) -> dict[str, Any]:
    return {
        "observed_at": side.get("observed_at", DEFAULT_OBSERVED_AT),
        "vitals": [_delta_row(row) for row in side["vitals"]],
    }


def _run_comparison(pair: dict[str, Any], expect: dict[str, Any], where: str) -> list[str]:
    failures: list[str] = []
    document = compare(
        _delta_side(pair["current"]),
        _delta_side(pair["previous"]),
        pair.get("comparison_status", COMPARABLE),
        pair.get("previous_bundle_id"),
        pair.get("incomparable_reasons"),
    )
    rows = {row["vital_id"]: row for row in document["vitals"]}
    if "comparison_status" in expect:
        _check_equal(f"{where}comparison_status", expect["comparison_status"], document["comparison_status"], failures)
    for vital_id, row_expect in expect["vitals"].items():
        row = rows[vital_id]
        _check_equal(f"{where}{vital_id}.transition_class", row_expect["transition_class"], row["transition_class"], failures)
        _check_codes(f"{where}{vital_id}.reason_codes", row_expect.get("reason_codes"), row_expect.get("reason_codes_absent"), row["reason_codes"], failures)
        for key in ("metric_deltas", "coverage_delta"):
            if key in row_expect:
                _check_equal(f"{where}{vital_id}.{key}", row_expect[key], row[key], failures)
    return failures


def _run_delta(vector: Vector) -> list[str]:
    """One case, every pair it names. A case passes only when all of them do."""
    given = vector.given
    if "comparisons" not in given:
        return _run_comparison(given, vector.expect, "")
    failures: list[str] = []
    for index, comparison in enumerate(given["comparisons"]):
        where = f"{comparison.get('title') or index}: "
        failures.extend(_run_comparison(comparison, comparison["expect"], where))
    return failures


def normalize_ci_evidence(shape: dict[str, Any]) -> list[dict[str, Any]]:
    """Canonical revision records from provider-native runs, attempts and check suites.

    This is the adapter's normalization stage without the adapter's transport:
    every workflow run becomes one parent through the accepted outcome map and
    attempt precedence, every check suite one parent-level parent, and every
    revision one record with its current verdict and failure-sticky history.
    """
    commits = [{"sha": r["sha"], "committed_at": r["committed_at"]} for r in shape["revisions"]]
    parents_by_sha: dict[str, list[dict[str, Any]]] = {}
    for run in shape.get("actions_runs") or []:
        run = dict(run)
        prior = run.pop("prior_attempts", None) or []
        parents_by_sha.setdefault(run["head_sha"], []).append(github_ci.actions_parent(run, prior))
    for sha, suites in (shape.get("check_suites") or {}).items():
        for suite in suites:
            parents_by_sha.setdefault(sha, []).append(github_ci.check_suite_parent(suite))
    return github_ci.build_revision_records(commits, parents_by_sha)


def _ci_shapes(given: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    settings = {key: given[key] for key in CI_SETTING_KEYS if key in given}
    if "variants" in given:
        return [(f"{variant.get('title') or index}: ", dict(settings, **{k: v for k, v in variant.items() if k != "title"})) for index, variant in enumerate(given["variants"])]
    return [("", given)]


def _check_ci_records(records: list[dict[str, Any]], expect: dict[str, Any], failures: list[str], where: str) -> None:
    by_sha = {record["revision"]: record for record in records}
    for sha, row_expect in (expect.get("revisions") or {}).items():
        record = by_sha.get(sha)
        if record is None:
            failures.append(f"{where}revisions.{sha}: no such revision in the normalized records {sorted(by_sha)}")
            continue
        for key in ("current_verdict", "history_state", "historical_contribution", "history_provenance"):
            if key in row_expect:
                _check_equal(f"{where}revisions.{sha}.{key}", row_expect[key], record.get(key), failures)
        if "parents" in row_expect:
            parents = record.get("parents") or []
            if len(parents) != len(row_expect["parents"]):
                failures.append(f"{where}revisions.{sha}.parents: expected {len(row_expect['parents'])} parents, got {len(parents)}")
                continue
            for index, (parent_expect, parent) in enumerate(zip(row_expect["parents"], parents)):
                for key, value in parent_expect.items():
                    _check_equal(f"{where}revisions.{sha}.parents[{index}].{key}", value, parent.get(key), failures)


def _run_ci(vector: Vector) -> list[str]:
    """Normalize provider-native evidence, check the records, optionally evaluate Integrity over them."""
    failures: list[str] = []
    for where, shape in _ci_shapes(vector.given):
        records = normalize_ci_evidence(shape)
        _check_ci_records(records, vector.expect, failures, where)
        if "integrity" not in vector.expect:
            continue
        observed_at = shape.get("observed_at", DEFAULT_OBSERVED_AT)
        obs = ObservationSet(subject=dict(DEFAULT_SUBJECT), observed_at=observed_at)
        configured = shape.get("configured", True)
        common = {"provider": "vector", "collected_at": observed_at, "source_ref": f"vector:{vector.case}", "adapter_version": VECTOR_SCHEMA}
        if configured is None:
            obs.add(Observation(observation_id="ci.configured", status="UNKNOWN", value_type="boolean", reason_code="NOT_OBSERVED", **common))
        else:
            obs.add(Observation(observation_id="ci.configured", status=AVAILABLE, value_type="boolean", value=bool(configured), **common))
        status = shape.get("series_status", AVAILABLE)
        obs.add(
            Observation(
                observation_id="ci.revision_verdicts_14d",
                status=status,
                value_type="series",
                value=records if status in (AVAILABLE, PARTIAL) else None,
                reason_code=None if status == AVAILABLE else "PAGINATION_CAPPED",
                **common,
            )
        )
        _evaluate_and_check(EVALUATORS["integrity"], obs, vector.expect["integrity"], failures, f"{where}integrity.")
    return failures


def _run_activity(vector: Vector) -> list[str]:
    failures: list[str] = []
    given = vector.given
    obs = _observation_set(given, vector.case)
    previous = given.get("previous_observed_at")
    activity = build_activity(obs, {"observed_at": previous} if previous else None, previous, given.get("list_cap", 50))
    expect = vector.expect
    for key, value in (expect.get("interval") or {}).items():
        _check_equal(f"interval.{key}", value, activity["interval"].get(key), failures)
    _check_codes("coverage_notes", expect.get("coverage_notes"), expect.get("coverage_notes_absent"), activity["coverage_notes"], failures)
    for name, counts in (expect.get("classes") or {}).items():
        actual = activity["classes"].get(name)
        if actual is None:
            failures.append(f"classes.{name}: no such activity class, known are {sorted(activity['classes'])}")
            continue
        for key, value in counts.items():
            _check_equal(f"classes.{name}.{key}", value, actual.get(key), failures)
    for name, value in (expect.get("truncated") or {}).items():
        _check_equal(f"truncated.{name}", value, activity["truncated"].get(name), failures)
    return failures


RUNNERS = {"vital": _run_vital, "delta": _run_delta, "ci": _run_ci, "activity": _run_activity}


def run(vector: Vector) -> VectorResult:
    """Execute one vector. A vector that cannot run is a failure, never a skip."""
    runner = RUNNERS.get(vector.kind)
    if runner is None:  # unreachable through load(); reachable through a hand-built Vector
        return VectorResult(vector, [f"unknown kind {vector.kind!r}"])
    try:
        return VectorResult(vector, runner(vector))
    except Exception as exc:  # noqa: BLE001 - a vector must report, never crash the suite
        return VectorResult(vector, [f"{type(exc).__name__}: {exc}"])


def run_all(vectors: Iterable[Vector]) -> list[VectorResult]:
    return [run(vector) for vector in vectors]
