"""Command-line interface."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__, canonical, render, timeutil
from .adapters.cache import ConditionalCache
from .adapters.github import CollectionError, GitHubClient, UrllibTransport
from .bundle import BundleError, load_bundle_dir, report_renderer, verify_dir
from .contracts import RENDERER_VERSION
from .config import ConfigError, load_config, single_project
from .history import FilesystemHistoryStore, HistoryStoreError
from .observations import ObservationSet
from .runner import FleetSurfaceError, build_from_observations, evaluate, observe, run_all, write_fleet_index
from .vitals.common import InadmissibleEvidence

TOKEN_ENVS = ("DEVOSTASIS_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")


def resolve_token(explicit: str | None, extra_env: str | None = None) -> tuple[str | None, str]:
    if explicit:
        return explicit, "argument"
    names = ([extra_env] if extra_env else []) + list(TOKEN_ENVS)
    for name in names:
        value = os.environ.get(name)
        if value:
            return value, f"env:{name}"
    gh = shutil.which("gh")
    if gh:
        try:
            result = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=15, check=False)
            token = result.stdout.strip()
            if result.returncode == 0 and token:
                return token, "gh auth token"
        except (OSError, subprocess.SubprocessError):
            pass
    return None, "none (unauthenticated: public repositories only, low rate limit)"


def _now(value: str | None):
    return timeutil.parse_ts(value) if value else timeutil.now_utc()


def _bands_line(bands: dict[str, str | None]) -> str:
    order = ("pulse", "flow", "integrity", "clutter", "horizon", "direction", "debt")
    return " ".join(f"{name}={bands.get(name) or 'UNKNOWN'}" for name in order)


def _project_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """Planning and debt configuration from CLI flags."""
    overrides: dict[str, Any] = {}
    planning: dict[str, Any] = {"source": getattr(args, "planning", "milestones")}
    if getattr(args, "planning_path", None):
        planning["path"] = args.planning_path
    if getattr(args, "link_marker", None):
        planning["link_marker"] = args.link_marker
    overrides["planning"] = planning
    labels = getattr(args, "debt_label", None)
    debt_path = getattr(args, "debt_path", None)
    version = getattr(args, "debt_mapping_version", None) or "cli-1"
    if debt_path:
        overrides["debt"] = {"source": "file", "path": debt_path, "mapping_version": version}
    elif labels:
        overrides["debt"] = {"source": "labels", "labels": list(labels), "mapping_version": version}
    return overrides


def _add_project_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--planning", choices=("milestones", "file", "none"), default="milestones", help="planning target source")
    parser.add_argument("--planning-path", help="repository path of the targets register when --planning file")
    parser.add_argument("--link-marker", help="marker that links a change request to a target (default 'Target:')")
    parser.add_argument("--debt-label", action="append", help="issue label that marks a registered debt item (repeatable)")
    parser.add_argument("--debt-path", help="repository path of the debt register (source file)")
    parser.add_argument("--debt-mapping-version")


def _add_rate_flags(parser: argparse.ArgumentParser) -> None:
    """Operational limits. They shape how evidence is fetched, never what it means."""
    parser.add_argument(
        "--request-budget",
        type=int,
        default=None,
        help="stop collecting after this many rate-limited requests per project; a truncated enumeration becomes PARTIAL",
    )
    parser.add_argument(
        "--cache",
        default=None,
        help="directory holding entity tags of previous runs; unchanged answers cost a round trip but no rate-limit quota",
    )


def _cache_for(args: argparse.Namespace) -> ConditionalCache | None:
    directory = getattr(args, "cache", None)
    return ConditionalCache(Path(directory) / "github-etags.json") if directory else None


def _requests_line(client: GitHubClient) -> str:
    parts = [f"{client.request_count} requests"]
    if client.conditional_hits:
        parts.append(f"{client.conditional_hits} unchanged")
    if client.retries:
        parts.append(f"{client.retries} retries")
    if client.budget_exhausted:
        parts.append("budget exhausted")
    return ", ".join(parts)


def cmd_observe(args: argparse.Namespace) -> int:
    token, source = resolve_token(args.token)
    project = single_project(args.repo, **_project_overrides(args))
    client = GitHubClient(UrllibTransport(token), budget=args.request_budget, cache=_cache_for(args))
    print(f"token: {source}", file=sys.stderr)
    try:
        obs = observe(project, client, _now(args.now))
    except CollectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    obs.save(args.out)
    print(f"observations: {args.out} ({len(obs)} keys, {_requests_line(client)})")
    if client.cache is not None:
        try:
            client.cache.save()
        except OSError as exc:
            print(f"warning: conditional cache not saved: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 0


class InputError(Exception):
    """A file or directory named on the command line cannot be read as what the command needs."""


def _load_observations(path: str) -> ObservationSet:
    try:
        return ObservationSet.load(path)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise InputError(f"{path} is not a readable observation set: {type(exc).__name__}: {exc}") from exc


def cmd_evaluate(args: argparse.Namespace) -> int:
    obs = _load_observations(args.observations)
    project = single_project(f"{obs.subject.get('owner', 'unknown')}/{obs.subject.get('repo', 'unknown')}") if args.derive else None
    snapshot = evaluate(obs, project)
    canonical.write_pretty(args.out, snapshot)
    bands = {item["vital_id"]: item["band"] for item in snapshot["vitals"]}
    print(f"snapshot: {args.out}")
    print(_bands_line(bands))
    return 0


def config_for_repo(args: argparse.Namespace):
    """A one-project configuration built from CLI flags (``run --repo``)."""
    from .config import Config

    project = single_project(args.repo, config_version=getattr(args, "config_version", None) or "cli", **_project_overrides(args))
    return Config(config_version=project.config_version, store_path=args.store or ".", projects=(project,))


def cmd_run(args: argparse.Namespace) -> int:
    try:
        config = config_for_repo(args) if args.repo else load_config(args.config)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    token, source = resolve_token(args.token, config.token_env)
    print(f"token: {source}", file=sys.stderr)
    store = FilesystemHistoryStore(args.store or config.store_path)
    surface_error: str | None = None
    try:
        outcomes = run_all(
            config,
            store,
            token,
            _now(args.now),
            only=(args.project or None) if not args.repo else None,
            user_agent=config.user_agent,
            request_budget=args.request_budget,
            cache_dir=args.cache,
        )
        cache_warning = getattr(outcomes, "cache_warning", None)
    except FleetSurfaceError as exc:
        # The bundles of this run are committed and are reported below; what
        # could not be produced is the fleet surface, and a stale one must not
        # pass for a fresh one, so the run still fails.
        outcomes, surface_error, cache_warning = exc.outcomes, str(exc), exc.cache_warning
    except HistoryStoreError as exc:
        print(f"store error: {exc}", file=sys.stderr)
        return 1
    failed = 0
    for outcome in outcomes:
        if outcome.ok:
            cached = f", {outcome.conditional_hits} unchanged" if outcome.conditional_hits else ""
            print(f"[ok] {outcome.locator}: {outcome.comparison_status} bundle {outcome.bundle_id[:12]} ({outcome.requests} requests{cached})")
            print(f"     {_bands_line(outcome.bands)}")
        else:
            failed += 1
            print(f"[failed] {outcome.locator}: {outcome.error}")
    print(f"store: {store.root}")
    if cache_warning:
        print(f"warning: {cache_warning}", file=sys.stderr)
    if surface_error is not None:
        print(f"store error: fleet surfaces not written: {surface_error}", file=sys.stderr)
        return 1
    return 1 if failed else 0


def cmd_build(args: argparse.Namespace) -> int:
    """Build and persist a bundle from a saved observation set (offline)."""
    from .normalize import derive

    obs = _load_observations(args.observations)
    project = single_project(f"{obs.subject.get('owner', 'unknown')}/{obs.subject.get('repo', 'unknown')}", **_project_overrides(args))
    derive(obs, project)
    store = FilesystemHistoryStore(args.store)
    try:
        bundle = build_from_observations(project, obs, store)
        path = store.commit(bundle)
    except (BundleError, HistoryStoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"bundle {bundle.bundle_id[:12]} ({bundle.manifest['comparison_status']}) written to {path}")
    print(_bands_line(bundle.bands()))
    try:
        write_fleet_index(store)
    except HistoryStoreError as exc:
        # The bundle above is committed; only the fleet surfaces are not.
        print(f"store error: the bundle is committed, the fleet surfaces are not: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    problems = verify_dir(args.bundle)
    if problems:
        for problem in problems:
            print(f"FAIL {problem}")
        return 1
    renderer = report_renderer(args.bundle)
    if renderer == RENDERER_VERSION:
        print("verified: digests, identity preimage, persisted effective config and report reproducibility all match")
    else:
        # A historical renderer is not carried: the report is bound by its
        # digest, but nobody replayed it, and the message must not say so.
        print(
            f"verified: digests, identity preimage and persisted effective config match; report.md was written by {renderer} "
            f"and is bound by its digest but not replayed (this version replays {RENDERER_VERSION})"
        )
    return 0


def _load_members(directory: str) -> dict[str, Any]:
    members = load_bundle_dir(directory)
    missing = [name for name in ("manifest.json", "snapshot.json") if name not in members]
    if missing:
        raise InputError(f"{directory} is not a bundle directory: {', '.join(missing)} missing")
    parsed: dict[str, Any] = {}
    for name, data in members.items():
        if name.endswith(".json"):
            try:
                parsed[name] = canonical.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise InputError(f"{directory}/{name} is not readable: {type(exc).__name__}") from exc
    return parsed


def cmd_render(args: argparse.Namespace) -> int:
    parsed = _load_members(args.bundle)
    display = (parsed.get("effective-config.json") or {}).get("display")
    sys.stdout.write(
        render.render_report(
            parsed["manifest.json"], parsed["snapshot.json"], parsed["delta.json"], parsed.get("activity.json"),
            parsed.get("gauges.json"), parsed.get("demand.json"), display,
        )
    )
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    try:
        path = write_fleet_index(FilesystemHistoryStore(args.store))
    except HistoryStoreError as exc:
        print(f"store error: {exc}", file=sys.stderr)
        return 1
    if path is None:
        print("no projects in store")
        return 0
    print(f"fleet overview: {path}")
    print(f"fleet index:    {path.with_name('index.json')}")
    return 0


def _snapshot_from_args(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (snapshot, parsed members) for --bundle or --snapshot."""
    if args.bundle:
        parsed = _load_members(args.bundle)
        return parsed["snapshot.json"], parsed
    try:
        snapshot = canonical.load_file(args.snapshot)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise InputError(f"{args.snapshot} is not a readable snapshot: {type(exc).__name__}") from exc
    return snapshot, {}


def cmd_gauges(args: argparse.Namespace) -> int:
    """Print the gauges of a bundle (its gauges.json) or compute them from a snapshot."""
    from .gauges import gauges_member

    snapshot, parsed = _snapshot_from_args(args)
    payload = parsed.get("gauges.json") or gauges_member(snapshot)
    sys.stdout.write(canonical.pretty_json(payload))
    if args.card:
        display = (parsed.get("effective-config.json") or {}).get("display")
        sys.stdout.write("\n" + render.render_status_card(snapshot, display, payload) + "\n")
    return 0


def cmd_demand(args: argparse.Namespace) -> int:
    """Print the demand interface of a bundle (its demand.json) or compute it with default mapping."""
    from .config import DEFAULTS
    from .demand import DEFAULT_LEVELS, DEFAULT_MAPPING_VERSION, build_demand
    from .gauges import gauges_for_snapshot

    snapshot, parsed = _snapshot_from_args(args)
    payload = parsed.get("demand.json") or build_demand(snapshot, gauges_for_snapshot(snapshot), {"mapping_version": DEFAULT_MAPPING_VERSION, "levels": DEFAULT_LEVELS})
    if args.order_only:
        for position, entry in enumerate(payload["attention_order"], start=1):
            print(f"{position}. {entry['vital_id']} {entry['level']}")
        return 0
    sys.stdout.write(canonical.pretty_json(payload))
    return 0


def cmd_vectors(args: argparse.Namespace) -> int:
    """Execute conformance vectors. A vector that cannot be loaded fails the run."""
    from .vectors import VectorError, load, run_all

    paths = args.path or [path for path in ("tests/vectors", "examples/vectors") if Path(path).exists()]
    if not paths:
        print("vector error: no --path given and no default corpus in the working directory", file=sys.stderr)
        return 2
    try:
        vectors = load(paths)
    except VectorError as exc:
        print(f"vector error: {exc}", file=sys.stderr)
        return 2
    if args.case:
        wanted = set(args.case)
        vectors = [vector for vector in vectors if vector.case in wanted]
        missing = sorted(wanted - {vector.case for vector in vectors})
        if missing:
            print(f"vector error: no such case: {', '.join(missing)}", file=sys.stderr)
            return 2
    if not vectors:
        print("vector error: no vectors found", file=sys.stderr)
        return 2
    results = run_all(vectors)
    failed = [result for result in results if not result.ok]
    for result in results:
        if not result.ok or not args.quiet:
            print(result.report())
    print(f"{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


def actions_summary_text(parsed: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Job-summary Markdown and step outputs for a bundle (GitHub Actions integration)."""
    manifest = parsed["manifest.json"]
    snapshot = parsed["snapshot.json"]
    demand_doc = parsed.get("demand.json") or {}
    gauges_doc = parsed.get("gauges.json")
    display = (parsed.get("effective-config.json") or {}).get("display")
    locator = manifest["project_identity"]["display_locator"]
    card = render.render_status_card(snapshot, display, gauges_doc)
    bands = {v["vital_id"]: v["band"] for v in snapshot["vitals"]}
    gauges = {g["vital_id"]: g["value"] for g in (gauges_doc or {}).get("gauges", [])}
    levels = {r["vital_id"]: r["level"] for r in demand_doc.get("vitals", [])}
    order = demand_doc.get("attention_order") or []
    lines = [f"## Devostasis: {locator}", "", "```text", card, "```", ""]
    if order:
        lines.append("| Order | Vital | Level | Band | Gauge |")
        lines.append("| --- | --- | --- | --- | --- |")
        for position, entry in enumerate(order, start=1):
            vital_id = entry["vital_id"]
            gauge = gauges.get(vital_id)
            lines.append(f"| {position} | {vital_id} | {entry['level']} | {bands.get(vital_id) or 'UNKNOWN'} | {gauge if gauge is not None else 'n/a'} |")
        lines.append("")
    lines.append(f"Bundle `{manifest['bundle_id']}` ({manifest['comparison_status']}), observed {manifest['observed_at']}. Levels come from mapping `{demand_doc.get('mapping_version', 'n/a')}`; there is no aggregate.")
    lines.append("")
    top = f"{order[0]['vital_id']} {order[0]['level']}" if order else ""
    outputs = {
        "bundle-id": manifest["bundle_id"],
        "observed-at": manifest["observed_at"],
        "comparison-status": manifest["comparison_status"],
        "attention": top,
        "attention-order": canonical.canonical_bytes([{"vital_id": e["vital_id"], "level": e["level"]} for e in order]).decode("utf-8"),
        "levels": canonical.canonical_bytes(levels).decode("utf-8"),
        "bands": canonical.canonical_bytes(bands).decode("utf-8"),
        "gauges": canonical.canonical_bytes(gauges).decode("utf-8"),
    }
    return "\n".join(lines), outputs


def cmd_actions_summary(args: argparse.Namespace) -> int:
    """Write the GitHub Actions job summary and step outputs for a bundle."""
    parsed = _load_members(args.bundle)
    summary, outputs = actions_summary_text(parsed)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    output_path = os.environ.get("GITHUB_OUTPUT")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(summary + "\n")
    else:
        sys.stdout.write(summary + "\n")
    lines = [f"{key}={value}" for key, value in outputs.items()]
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    else:
        sys.stdout.write("\n".join(lines) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devostasis", description="Deterministic, model-free vital signs for software repositories.")
    parser.add_argument("--version", action="version", version=f"devostasis {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    observe_p = sub.add_parser("observe", help="collect a read-only observation set for one repository")
    observe_p.add_argument("--repo", required=True, help="owner/name")
    observe_p.add_argument("--out", default="observations.json")
    observe_p.add_argument("--token")
    observe_p.add_argument("--now", help="observation timestamp (RFC 3339) for reproducible runs")
    _add_rate_flags(observe_p)
    _add_project_flags(observe_p)
    observe_p.set_defaults(func=cmd_observe)

    eval_p = sub.add_parser("evaluate", help="evaluate the seven Vitals from a saved observation set")
    eval_p.add_argument("--observations", required=True)
    eval_p.add_argument("--out", default="snapshot.json")
    eval_p.add_argument("--derive", action="store_true", help="derive aggregates from inventories before evaluating")
    eval_p.set_defaults(func=cmd_evaluate)

    run_p = sub.add_parser("run", help="observe, evaluate, compare and persist bundles for every configured project, or for one --repo")
    target = run_p.add_mutually_exclusive_group(required=True)
    target.add_argument("--config", help="fleet configuration file")
    target.add_argument("--repo", help="owner/name: observe one repository with the flags below instead of a config file")
    run_p.add_argument("--store", help="history store root (defaults to store.path in the config, or '.' with --repo)")
    run_p.add_argument("--token")
    run_p.add_argument("--now")
    run_p.add_argument("--project", action="append", help="limit a --config run to owner/name (repeatable)")
    run_p.add_argument("--config-version", help="provenance label recorded with --repo runs (default 'cli')")
    _add_rate_flags(run_p)
    _add_project_flags(run_p)
    run_p.set_defaults(func=cmd_run)

    build_p = sub.add_parser("build", help="build and persist a bundle from a saved observation set (offline)")
    build_p.add_argument("--observations", required=True)
    build_p.add_argument("--store", required=True)
    _add_project_flags(build_p)
    build_p.set_defaults(func=cmd_build)

    verify_p = sub.add_parser("verify", help="verify digests, identity and report reproducibility of a bundle directory")
    verify_p.add_argument("--bundle", required=True)
    verify_p.set_defaults(func=cmd_verify)

    render_p = sub.add_parser("render", help="re-render report.md from a bundle directory to stdout")
    render_p.add_argument("--bundle", required=True)
    render_p.set_defaults(func=cmd_render)

    index_p = sub.add_parser("index", help="regenerate the fleet overview of a store")
    index_p.add_argument("--store", required=True)
    index_p.set_defaults(func=cmd_index)

    gauges_p = sub.add_parser("gauges", help="print the 0-100 gauges of a bundle or snapshot")
    group = gauges_p.add_mutually_exclusive_group(required=True)
    group.add_argument("--bundle", help="bundle directory")
    group.add_argument("--snapshot", help="snapshot.json path")
    gauges_p.add_argument("--card", action="store_true", help="also print the text status card")
    gauges_p.set_defaults(func=cmd_gauges)

    demand_p = sub.add_parser("demand", help="print the demand interface (levels and attention order) of a bundle or snapshot")
    group = demand_p.add_mutually_exclusive_group(required=True)
    group.add_argument("--bundle", help="bundle directory")
    group.add_argument("--snapshot", help="snapshot.json path")
    demand_p.add_argument("--order-only", action="store_true", help="print only the attention order")
    demand_p.set_defaults(func=cmd_demand)

    vectors_p = sub.add_parser("vectors", help="execute conformance vectors from files or directories")
    vectors_p.add_argument("--path", action="append", default=None, help="vector file or directory (repeatable; default tests/vectors and examples/vectors)")
    vectors_p.add_argument("--case", action="append", help="run only this case id (repeatable)")
    vectors_p.add_argument("--quiet", action="store_true", help="print only failures and the summary")
    vectors_p.set_defaults(func=cmd_vectors)

    summary_p = sub.add_parser("actions-summary", help="write a GitHub Actions job summary and step outputs (attention, levels, bands, gauges) for a bundle")
    summary_p.add_argument("--bundle", required=True, help="bundle directory")
    summary_p.set_defaults(func=cmd_actions_summary)
    from .workscope.cli import add_parser
    add_parser(sub)
    return parser


def _utf8_console() -> None:
    """Reports contain block characters; never let a legacy console encoding crash the CLI."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    except InputError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    except InadmissibleEvidence as exc:
        # Counts that cannot all be true are refused before classification
        # (PV-DIRECTION-INCOMPLETE-001, PV-HORIZON-PARTIAL-001): the saved
        # observation set is invalid input, not a Vital without a band.
        print(f"input error: the observations contradict themselves: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
