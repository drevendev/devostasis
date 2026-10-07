"""End-to-end pipeline: observe -> normalize -> evaluate -> compare -> bundle -> persist."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import activity as activity_mod
from . import delta as delta_mod
from . import canonical, fleet, normalize, render, revision_history, timeutil
from .adapters.cache import ConditionalCache
from .adapters.github import CollectionError, GitHubAdapter, GitHubClient, UrllibTransport
from .bundle import Bundle, BundleError, build_bundle
from .config import Config, ResolvedProject
from .contracts import OBSERVATION_CONTRACT_VERSION, VITALS_CONTRACT_VERSION
from .history import FilesystemHistoryStore, HistoryStoreError, _write_atomic
from .observations import ObservationSet, failed_execution
from .policy import POLICY_VERSION
from .vitals import build_snapshot, evaluate_all

NON_MONOTONIC_OBSERVATION = "NON_MONOTONIC_OBSERVATION"
CONFIG_MISMATCH = "CONFIG_MISMATCH"
DUPLICATE_PROJECT_IDENTITY = "DUPLICATE_PROJECT_IDENTITY"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass
class RunOutcome:
    locator: str
    ok: bool
    bundle_id: str | None = None
    comparison_status: str | None = None
    bands: dict[str, str | None] = field(default_factory=dict)
    path: str | None = None
    error: str | None = None
    requests: int = 0
    conditional_hits: int = 0
    execution_receipt: dict[str, Any] | None = None


def observe(project: ResolvedProject, client: GitHubClient, now: datetime) -> ObservationSet:
    obs = GitHubAdapter(client, now).collect(project)
    normalize.derive(obs, project)
    return obs


def evaluate(obs: ObservationSet, project: ResolvedProject | None = None) -> dict[str, Any]:
    if project is not None:
        normalize.derive(obs, project)
    return build_snapshot(obs, evaluate_all(obs))


@dataclass
class Predecessor:
    """The bundle a new one follows: what the comparison and the carried history both consume."""

    status: str
    bundle_id: str | None
    manifest: dict[str, Any] | None
    snapshot: dict[str, Any] | None
    observations: dict[str, Any] | None
    reasons: list[str]


def decide_comparison(
    store: FilesystemHistoryStore,
    project: ResolvedProject,
    immutable_project_id: str | None = None,
    observed_at: str | None = None,
) -> tuple[str, str | None, dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """Return (comparison_status, previous_bundle_id, previous_manifest, previous_snapshot, reasons)."""
    found = find_predecessor(store, project, immutable_project_id, observed_at)
    return found.status, found.bundle_id, found.manifest, found.snapshot, found.reasons


def find_predecessor(
    store: FilesystemHistoryStore,
    project: ResolvedProject,
    immutable_project_id: str | None = None,
    observed_at: str | None = None,
) -> Predecessor:
    """The immediate predecessor of a new bundle and how the two compare.

    The immutable project id locates history across a rename or transfer
    (RPT-7); without it the locator is the identity and a renamed project
    starts a new BASELINE, which is the honest outcome when nothing proves
    the two names are the same project.

    A pair is only comparable when the current observation is later than the
    previous one (#17). An observation older than, or as old as, the bundle it
    would be compared against is ``INCOMPARABLE`` with the reason
    ``NON_MONOTONIC_OBSERVATION``: the band ordering assumes that "previous"
    precedes "current" in time, and a delta computed backwards would report
    every direction inverted while citing the accepted order as its authority.
    """
    latest = store.latest(project.project_key, immutable_project_id)
    if not latest.exists:
        return Predecessor(delta_mod.BASELINE, None, None, None, None, [])
    if not latest.verified or latest.manifest is None or latest.snapshot is None:
        return Predecessor(delta_mod.HISTORY_GAP, latest.bundle_id, None, None, None, latest.problems)
    current_fields = {
        "vitals_contract_version": VITALS_CONTRACT_VERSION,
        "observation_contract_version": OBSERVATION_CONTRACT_VERSION,
        "policy_version": POLICY_VERSION,
        "semantic_config": project.semantic_config(),
    }
    reasons = delta_mod.compatibility_reasons(current_fields, latest.manifest)
    previous_observed_at = latest.manifest.get("observed_at")
    if observed_at is not None and isinstance(previous_observed_at, str):
        if timeutil.parse_ts(observed_at) <= timeutil.parse_ts(previous_observed_at):
            reasons.append(f"{NON_MONOTONIC_OBSERVATION}:{previous_observed_at}->{observed_at}")
    if reasons:
        return Predecessor(delta_mod.INCOMPARABLE, latest.bundle_id, latest.manifest, latest.snapshot, latest.observations, reasons)
    return Predecessor(delta_mod.COMPARABLE, latest.bundle_id, latest.manifest, latest.snapshot, latest.observations, [])


def check_receipt_config(project: ResolvedProject, obs: ObservationSet) -> None:
    """Refuse to build over evidence that was derived under another effective configuration (#27).

    The receipt records the digest of the configuration the aggregates were
    derived under. A build whose resolved configuration differs would persist
    a semantic authority that contradicts its own snapshot, and verify. Only a
    real digest is compared: fixtures and examples carry placeholders.
    """
    recorded = obs.receipt.config_hash if obs.receipt is not None else None
    if not isinstance(recorded, str) or not _DIGEST.fullmatch(recorded):
        return
    resolved = project.effective_config_digest()
    if recorded != resolved:
        raise BundleError(
            f"{CONFIG_MISMATCH}: the observations were collected under effective configuration {recorded}, "
            f"this build resolves {resolved}. The digest covers the whole effective configuration (planning, debt, activity, "
            f"display, demand, the observations member); build accepts only the planning and debt options, so pass the ones the "
            f"observation used, and observe again when the difference is anywhere else"
        )


HISTORY_SOURCE_NOT_PREDECESSOR = "HISTORY_SOURCE_NOT_PREDECESSOR"
HISTORY_CONTENT_MISMATCH = "HISTORY_CONTENT_MISMATCH"


def attach_revision_history(obs: ObservationSet, predecessor: Predecessor) -> ObservationSet:
    """The observations with the durable revision history the predecessor carries (PV-HIST-002, section C).

    The source is the bundle the comparison resolved, the immediate
    predecessor, never an older one. A set that already states carried history
    (rebuilt from a bundle's own observations) is kept only when it names that
    same predecessor and exactly matches the observation reconstructed from
    its verified contents. Naming a source alone cannot prove its history:
    accepting edited records would let an earlier failure disappear.
    """
    carried = revision_history.carried_observation(
        predecessor.status,
        predecessor.bundle_id,
        predecessor.manifest,
        predecessor.snapshot,
        predecessor.observations,
        predecessor.reasons,
        obs.observed_at,
    )
    stated = obs.get(revision_history.CARRIED)
    if stated is None:
        return revision_history.with_carried_history(obs, carried)
    if revision_history.carried_source_bundle(obs) != predecessor.bundle_id or stated.status != carried.status:
        raise BundleError(
            f"{HISTORY_SOURCE_NOT_PREDECESSOR}: the observations carry revision history from "
            f"{revision_history.carried_source_bundle(obs) or 'no bundle'} ({stated.status}), this store's predecessor is "
            f"{predecessor.bundle_id or 'none'} ({predecessor.status}); durable history is consumed only from the immediate predecessor"
        )
    if canonical.canonical_bytes(stated.to_dict()) != canonical.canonical_bytes(carried.to_dict()):
        raise BundleError(
            f"{HISTORY_CONTENT_MISMATCH}: the stated revision history does not match the observation reconstructed "
            f"from the verified immediate predecessor {predecessor.bundle_id or 'none'}; records and provenance cannot be substituted"
        )
    return obs


def build_from_observations(project: ResolvedProject, obs: ObservationSet, store: FilesystemHistoryStore, run_meta: dict[str, Any] | None = None) -> Bundle:
    check_receipt_config(project, obs)
    predecessor = find_predecessor(store, project, obs.subject.get("immutable_project_id"), obs.observed_at)
    obs = attach_revision_history(obs, predecessor)
    snapshot = build_snapshot(obs, evaluate_all(obs))
    status, previous_id, previous_manifest, reasons = predecessor.status, predecessor.bundle_id, predecessor.manifest, predecessor.reasons
    delta = delta_mod.compare(snapshot, predecessor.snapshot, status, previous_id, reasons)
    activity = None
    if project.activity_enabled:
        interval_start = previous_manifest.get("observed_at") if (status == delta_mod.COMPARABLE and previous_manifest) else None
        activity = activity_mod.build_activity(obs, previous_manifest if status == delta_mod.COMPARABLE else None, interval_start, project.activity_list_cap)
    return build_bundle(project, obs, snapshot, delta, activity, previous_id, status, run_meta)


def run_project(
    project: ResolvedProject,
    store: FilesystemHistoryStore,
    client: GitHubClient,
    now: datetime,
    *,
    admitted: dict[str, str] | None = None,
) -> RunOutcome:
    """Observe one project and commit its bundle.

    ``admitted`` maps the immutable identity of every project already observed
    in this run to the locator that observed it. Two configured locators that
    the provider resolves to one repository (a case variant, a redirect) are
    one project: the second is refused before anything is written, so it can
    neither collect twice nor be mistaken for a rename of the first
    (PV-AUDIT-PROJECT-LOCATOR-ALIAS-001).
    """
    started = timeutil.now_utc()
    try:
        obs = observe(project, client, now)
    except CollectionError as exc:
        execution = failed_execution(project.locator, timeutil.format_ts(started), timeutil.format_ts(timeutil.now_utc()), str(exc),
                                     {"requests": client.request_count, "conditional_hits": client.conditional_hits})
        return RunOutcome(project.locator, False, error=str(exc), requests=client.request_count,
                          conditional_hits=client.conditional_hits, execution_receipt=execution)
    identity = obs.subject.get("immutable_project_id")
    if admitted is not None and identity not in (None, ""):
        key = f"{obs.subject.get('forge_instance') or 'github.com'}:{identity}"
        earlier = admitted.get(key)
        if earlier is not None and earlier != project.locator:
            return RunOutcome(
                project.locator,
                False,
                error=f"{DUPLICATE_PROJECT_IDENTITY}: {project.locator} is repository {identity}, already observed in this run as {earlier}; one repository is observed once",
                requests=client.request_count,
                conditional_hits=client.conditional_hits,
                execution_receipt=obs.receipt.execution(receipt_identity=obs.receipt_identity()),
            )
        admitted[key] = project.locator
    try:
        # How the evidence was fetched is provenance, not evidence: it lives in
        # run_meta, which is post-identity, so a cached run and a fresh run of
        # the same repository produce the same bundle_id.
        run_meta = {
            "collection_started_at": timeutil.format_ts(started),
            "requests": client.request_count,
            "billed_requests": client.billed_count,
            "conditional_hits": client.conditional_hits,
            "retries": client.retries,
        }
        bundle = build_from_observations(project, obs, store, run_meta)
        path = store.commit(bundle)
    except (BundleError, HistoryStoreError) as exc:
        execution = obs.receipt.execution(run_meta=run_meta, receipt_identity=obs.receipt_identity())
        execution["diagnostics"].append(str(exc))
        return RunOutcome(project.locator, False, error=str(exc), requests=client.request_count,
                          conditional_hits=client.conditional_hits, execution_receipt=execution)
    return RunOutcome(
        project.locator,
        True,
        bundle_id=bundle.bundle_id,
        comparison_status=bundle.manifest["comparison_status"],
        bands=bundle.bands(),
        path=str(path),
        requests=client.request_count,
        conditional_hits=client.conditional_hits,
        execution_receipt=bundle.execution_receipt,
    )


def write_fleet_index(store: FilesystemHistoryStore) -> Path | None:
    """Write both fleet surfaces: the Markdown overview for people, the index for machines.

    Each is written beside itself and moved into place, so a reader (or a
    full disk) never leaves a truncated index.json behind a README that
    already lists the new project.
    """
    entries = store.all_projects()
    if not entries:
        return None
    directory = store.root / "projects"
    directory.mkdir(parents=True, exist_ok=True)
    readme = render.render_fleet_index(entries).encode("utf-8")
    index = canonical.pretty_json(fleet.build_index(entries)).encode("utf-8")
    _write_atomic(directory / "index.json", index)
    _write_atomic(directory / "README.md", readme)
    return directory / "README.md"


class FleetSurfaceError(HistoryStoreError):
    """The projects of a run are done and their bundles committed; the fleet surfaces could not be written.

    It carries the outcomes, so the run still reports every project before it
    reports the store failure.
    """

    def __init__(self, message: str, outcomes: list["RunOutcome"], cache_warning: str | None = None) -> None:
        super().__init__(message)
        self.outcomes = outcomes
        self.cache_warning = cache_warning


class RunOutcomes(list):
    """The outcomes of a run, plus a warning when the conditional cache could not be kept."""

    def __init__(self, outcomes=(), cache_warning: str | None = None) -> None:
        super().__init__(outcomes)
        self.cache_warning = cache_warning


def run_all(
    config: Config,
    store: FilesystemHistoryStore,
    token: str | None,
    now: datetime,
    only: list[str] | None = None,
    user_agent: str | None = None,
    request_budget: int | None = None,
    cache_dir: str | Path | None = None,
) -> list[RunOutcome]:
    """Observe every configured project.

    ``request_budget`` is per project, not per run: one very active repository
    must not be able to starve the rest of the fleet. ``cache_dir`` holds the
    entity tags of previous runs, shared by every project and written once at
    the end, so a repeated run spends quota only on what actually changed.
    """
    cache = ConditionalCache(Path(cache_dir) / "github-etags.json") if cache_dir else None
    outcomes = []
    admitted: dict[str, str] = {}
    for project in config.projects:
        if only and project.locator not in only:
            continue
        transport = UrllibTransport(token, user_agent=user_agent or "devostasis/0.1 (+https://github.com/drevendev/devostasis)")
        client = GitHubClient(transport, budget=request_budget, cache=cache)
        invocation_started = timeutil.format_ts(timeutil.now_utc())
        try:
            outcomes.append(run_project(project, store, client, now, admitted=admitted))
        except Exception as exc:  # noqa: BLE001 - one project's data must not end the fleet run
            # run_project already turns every failure it anticipates into an
            # unsuccessful outcome. This boundary is for the ones it does not:
            # a malformed provider payload or a defect in a collector must cost
            # one project's bundle, not every project queued behind it. The
            # reason is kept and the outcome stays unsuccessful, so the run
            # still exits non-zero.
            outcomes.append(
                RunOutcome(
                    project.locator,
                    False,
                    error=f"{type(exc).__name__}: {exc}",
                    requests=client.request_count,
                    conditional_hits=client.conditional_hits,
                    execution_receipt=failed_execution(project.locator, invocation_started,
                        timeutil.format_ts(timeutil.now_utc()), f"{type(exc).__name__}: {exc}",
                        {"requests": client.request_count, "conditional_hits": client.conditional_hits}),
                )
            )
    # The fleet surfaces first: they are part of the result. The cache is an
    # optimization, and failing to keep it costs requests next time, never
    # this run's surfaces or its report.
    cache_warning: str | None = None
    if cache is not None:
        try:
            cache.save()
        except OSError as exc:
            cache_warning = f"conditional cache not saved: {type(exc).__name__}: {exc}"
    try:
        write_fleet_index(store)
    except HistoryStoreError as exc:
        raise FleetSurfaceError(str(exc), outcomes, cache_warning) from exc
    return RunOutcomes(outcomes, cache_warning)
