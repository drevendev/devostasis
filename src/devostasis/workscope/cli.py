"""Consumer commands; network commands never claim or execute tasks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import shutil
from pathlib import Path
import sys

from ..canonical import canonical_bytes, digest, digest_bytes, loads
from .bundle import build, latest, publish, slice_scope, verify
from .collect import Client, collect
from .evidence import empty_evidence, source, validate
from .model import ScopeError, default_policy, identity, instant, require
from .planner import project


def read_json(path):
    member = Path(path)
    require(member.is_file() and member.stat().st_size <= 300 * 1024 * 1024, "input missing or too large")
    return loads(member.read_text(encoding="utf-8"))


def emit(value, output=None):
    data = canonical_bytes(value)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(data)
    else:
        print(data.decode("utf-8"))


def clock():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def client(args, provider=None, endpoint=None):
    provider = provider or args.provider
    endpoint = endpoint or args.endpoint or ("https://api.github.com" if provider == "github" else "https://gitlab.com/api/v4")
    token = os.getenv(args.token_env or ("DEVOSTASIS_GITHUB_TOKEN" if provider == "github" else "DEVOSTASIS_GITLAB_TOKEN"))
    if provider == "github" and not token:
        from ..cli import resolve_token
        token, _ = resolve_token(None)
    transport = None
    if provider == "gitlab" and not token and not args.token_env and shutil.which("glab"):
        from .glab import GlabTransport
        require(not args.cache, "glab credential bridge requires cache disabled; use token-env for partitioned caching")
        transport = GlabTransport(endpoint)
    return Client(provider, endpoint, token, transport=transport, max_requests=args.max_requests, max_pages=args.max_pages,
                  seconds=args.seconds, cache=args.cache)


def recheck(decoded, current, at, *, actor, policy_version, expected_project):
    scope, config = decoded["scope.json"], decoded["policy.json"]
    require(identity(scope["subject"]) == expected_project, "consumer expected project mismatch")
    require(actor == config["actor"] and policy_version == config["version"], "consumer actor or policy version mismatch")
    require(instant(at) <= instant(scope["expires_at"]), "scope expired; recover evidence first")
    require(instant(at) >= instant(current["observed_at"]), "recheck clock predates refreshed inventory")
    require(identity(current["subject"]) == identity(scope["subject"]), "recheck project mismatch")
    require(current["subject"]["context"] == scope["subject"]["context"], "recheck context mismatch")


def cmd(args):
    try:
        if args.operation == "policy":
            emit(default_policy(args.actor), args.output); return 0
        if args.operation == "import":
            evidence = read_json(args.evidence) if args.evidence else empty_evidence()
            inv = read_json(args.inventory)
            evidence["sources"].append(source(args.profile, args.producer, args.producer_version,
                inv["subject"], args.at or inv["observed_at"], Path(args.report).read_bytes()))
            validate(evidence); emit(evidence, args.output); return 0
        if args.operation in ("collect", "run"):
            inv = collect(client(args), args.repo, read_json(args.policy), args.at,
                          revision=args.revision, context=args.context, source_ref=args.source_ref,
                          source_change=args.source_change, source_project=args.source_project,
                          change_refs=[] if args.registered_only else args.change)
            if args.operation == "collect":
                emit(inv, args.output); return 0
        if args.operation in ("build", "run"):
            inv = inv if args.operation == "run" else read_json(args.inventory)
            config = read_json(args.policy)
            evidence = read_json(args.evidence) if args.evidence else empty_evidence()
            anchor = None
            if args.vitals_bundle:
                from ..bundle import verify_dir
                require(not verify_dir(Path(args.vitals_bundle)), "Vitals bundle did not verify")
                manifest_path = Path(args.vitals_bundle) / "manifest.json"
                manifest = read_json(manifest_path)
                anchor = {"bundle_id": manifest["bundle_id"], "manifest_digest": digest_bytes(manifest_path.read_bytes())}
            manifest, content = build(inv, config, evidence, args.at, anchor)
            dest = publish(args.store, content)
            emit({"bundle_id": manifest["bundle_id"], "path": str(dest.resolve())}); return 0
        decoded = latest(args.latest) if args.latest else verify(args.bundle)
        scope = decoded["scope.json"]
        if args.operation in ("handoff", "verify-handoff"):
            from .handoff import prepare, verify_packet
            at = args.at or clock()
            expected = {"provider": args.provider, "endpoint": args.endpoint or
                        ("https://api.github.com" if args.provider == "github" else "https://gitlab.com/api/v4"),
                        "project_id": args.expected_project_id}
            if args.operation == "handoff":
                require(digest(read_json(args.policy)) == scope["inputs"]["policy"], "consumer policy digest mismatch")
                packet = prepare(decoded, args.item, client(args), at, args.actor, args.policy_version, expected)
                emit(packet, args.output)
            else:
                verify_packet(read_json(args.packet), decoded, at, args.actor, args.policy_version, expected)
                emit({"status": "VERIFIED", "authority": scope["authority"]}, args.output)
            return 0
        if args.operation in ("verify", "replay"):
            emit({"status": "VERIFIED", "bundle_id": decoded["manifest.json"]["bundle_id"]}); return 0
        if args.operation == "slice":
            emit(slice_scope(scope, args.role, args.limit, args.cursor, args.at or clock()), args.output); return 0
        item = next((i for i in scope["items"] if i["id"] == args.item), None)
        require(item is not None, "item not in verified scope")
        if args.operation == "explain":
            emit(item, args.output); return 0
        now = args.at or clock()
        require(digest(read_json(args.policy)) == scope["inputs"]["policy"], "consumer policy digest mismatch")
        require(args.actor == decoded["policy.json"]["actor"] and args.policy_version == decoded["policy.json"]["version"],
                "consumer actor or policy version mismatch")
        require(instant(now) <= instant(scope["expires_at"]), "scope expired; recover evidence first")
        expected = {"provider": args.provider, "endpoint": args.endpoint or
                    ("https://api.github.com" if args.provider == "github" else "https://gitlab.com/api/v4"),
                    "project_id": args.expected_project_id}
        require(identity(scope["subject"]) == expected, "consumer expected project mismatch")
        bound = scope["subject"].get("source_binding")
        require(scope["subject"]["context"] != "CANDIDATE" or bound or item["source"].startswith("change:") or args.inventory,
                "candidate content recheck requires a freshly attested --inventory; no mutable source ref was recorded")
        current = read_json(args.inventory) if args.inventory else collect(
            client(args, scope["subject"]["provider"], scope["subject"]["endpoint"]), scope["subject"]["locator"],
            decoded["policy.json"], args.at, context=scope["subject"]["context"],
            revision=scope["subject"]["revision"] if scope["subject"]["context"] == "CANDIDATE" else None, selected=item,
            source_ref=bound["ref"] if bound and bound["kind"] == "BRANCH" else None,
            source_change=bound["ref"] if bound and bound["kind"] == "CHANGE" else None,
            source_project=bound["source_locator"] if bound and bound["kind"] == "BRANCH" else None)
        now = args.at or clock()
        recheck(decoded, current, now, actor=args.actor, policy_version=args.policy_version, expected_project=expected)
        refreshed = project(current, decoded["policy.json"], decoded["evidence.json"], now)
        selected = next((i for i in refreshed["items"] if i["id"] == item["id"]), None)
        changed = selected is None or selected["revision"] != item["revision"] or selected["implementation_owner"] != item["implementation_owner"]
        reasons = ["ITEM_REVISION_OR_OWNER_CHANGED"] if changed else selected["reasons"]
        ready = not changed and selected["eligibility"] == "READY" and selected["action"] == item["action"]
        if not changed and selected["action"] != item["action"]:
            reasons = ["ACTION_CHANGED_REBUILD_SCOPE"]
        emit({"item": item["id"], "status": "RECHECKED" if ready else "INVALIDATED", "reasons": reasons,
              "current": selected, "authority": scope["authority"]}, args.output)
        return 0 if ready else 3
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"work: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def add_parser(parser):
    work = parser.add_parser("work", help="Evidence to Action: bounded read-only work scopes")
    operations = work.add_subparsers(dest="operation", required=True)
    for operation in ("policy", "import", "collect", "build", "run", "verify", "replay", "slice", "explain", "recheck", "handoff", "verify-handoff"):
        p = operations.add_parser(operation)
        p.set_defaults(func=cmd)
        if operation == "policy":
            p.add_argument("--actor", required=True)
        if operation == "import":
            p.add_argument("--report", required=True); p.add_argument("--profile", required=True, choices=("sarif.v1", "junit.v1", "cobertura.v1", "performance.v1"))
            p.add_argument("--producer", required=True); p.add_argument("--producer-version", required=True)
        if operation in ("policy", "import", "collect", "slice", "explain", "recheck", "handoff", "verify-handoff"):
            p.add_argument("--output")
        if operation in ("import", "build", "recheck"):
            p.add_argument("--inventory", required=operation != "recheck")
        if operation in ("import", "build", "run"):
            p.add_argument("--evidence")
        if operation in ("collect", "build", "run", "recheck", "handoff"):
            p.add_argument("--policy", required=True)
        if operation in ("build", "run"):
            p.add_argument("--store", required=True); p.add_argument("--vitals-bundle")
        if operation in ("collect", "run", "recheck", "handoff", "verify-handoff"):
            p.add_argument("--provider", choices=("github", "gitlab"), default="github")
            p.add_argument("--endpoint"); p.add_argument("--token-env"); p.add_argument("--cache")
            p.add_argument("--max-requests", type=int, default=100); p.add_argument("--max-pages", type=int, default=10)
            p.add_argument("--seconds", type=int, default=120)
        if operation in ("collect", "run"):
            p.add_argument("--repo", required=True); p.add_argument("--revision")
            p.add_argument("--context", choices=("CANONICAL", "CANDIDATE"), default="CANONICAL")
            source = p.add_mutually_exclusive_group()
            source.add_argument("--source-ref", help="named candidate branch, resolved live")
            source.add_argument("--source-change", help="candidate PR/MR number, including fork source")
            p.add_argument("--source-project", help="candidate branch source project (fork locator or numeric GitLab ID)")
            selection = p.add_mutually_exclusive_group()
            selection.add_argument("--change", action="append", help="collect only these PR/MR numbers (repeatable); explicit selected inventory scope")
            selection.add_argument("--registered-only", action="store_true", help="collect only policy-registered implementations; skip the open-change listing")
        if operation in ("verify", "replay", "slice", "explain", "recheck", "handoff", "verify-handoff"):
            loc = p.add_mutually_exclusive_group(required=True)
            loc.add_argument("--bundle"); loc.add_argument("--latest")
        if operation == "slice":
            p.add_argument("--role", choices=("all", "reviewer", "developer", "researcher", "analyst"), default="all")
            p.add_argument("--limit", type=int, default=20); p.add_argument("--cursor")
        if operation in ("explain", "recheck", "handoff"):
            p.add_argument("--item", required=True)
        if operation in ("recheck", "handoff", "verify-handoff"):
            p.add_argument("--actor", required=True); p.add_argument("--policy-version", required=True)
            p.add_argument("--expected-project-id", required=True)
        if operation == "verify-handoff":
            p.add_argument("--packet", required=True)
        if operation in ("import", "collect", "build", "run", "slice", "recheck", "handoff", "verify-handoff"):
            p.add_argument("--at", help="explicit RFC3339 clock for fixtures/offline replay")
