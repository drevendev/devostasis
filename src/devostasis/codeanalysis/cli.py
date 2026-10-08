"""Offline code analysis commands. Source bytes remain in the chosen local output."""

from pathlib import Path
import sys

from ..canonical import canonical_bytes, loads
from ..workscope.model import require
from .bundle import MAX_BUNDLE_BYTES, build, publish, verify
from .consumer import compare, packet, verify_packet, work_evidence
from .engine import default_policy
from .git import collect


def json_file(filename):
    file = Path(filename)
    require(file.is_file() and file.stat().st_size <= MAX_BUNDLE_BYTES, "analysis input missing or byte cap")
    return loads(file.read_text(encoding="utf-8"))


def emit(value, filename=None):
    data = canonical_bytes(value)
    if filename:
        from ..workscope.operations import no_links
        file = no_links(filename); file.parent.mkdir(parents=True, exist_ok=True); no_links(file)
        from ..workscope.bundle import atomic
        atomic(file, data)
    else: print(data.decode("utf-8"))


def cmd(args):
    try:
        if args.operation == "policy": emit(default_policy(), args.output); return 0
        if args.operation == "analyze":
            config = json_file(args.policy) if args.policy else default_policy()
            from .engine import policy
            policy(config)
            raw = collect(args.repo, args.revision, config, args.at)
            manifest, members = build(raw, config); root = publish(args.output, members)
            emit({"status": "PUBLISHED", "bundle_id": manifest["bundle_id"], "path": str(root.resolve()),
                  "coverage": verify(root)["analysis.json"]["coverage"]})
            return 0
        if args.operation == "compare":
            emit(compare(verify(args.before), verify(args.after)), args.output); return 0
        decoded = verify(args.bundle)
        if args.operation == "verify": emit({"status": "VERIFIED", "bundle_id": decoded["manifest.json"]["bundle_id"]})
        elif args.operation == "show": emit(decoded["analysis.json"], args.output)
        elif args.operation == "sarif": emit(decoded["findings.sarif"], args.output)
        elif args.operation == "packet": emit(packet(decoded, args.path, args.max_files, args.max_bytes), args.output)
        elif args.operation == "verify-packet":
            value = verify_packet(json_file(args.packet), decoded); emit({"status": "VERIFIED", "packet_id": value["packet_id"]})
        elif args.operation == "work-evidence": emit(work_evidence(decoded, json_file(args.inventory), args.at), args.output)
        return 0
    except (ValueError, KeyError, TypeError, OSError, RecursionError, OverflowError) as exc:
        print(f"code: {type(exc).__name__}: {exc}", file=sys.stderr); return 2


def add_parser(parent):
    root = parent.add_parser("code", help="offline revision-bound Python analysis, Git history and source packets")
    commands = root.add_subparsers(dest="operation", required=True)
    for operation in ("policy", "analyze", "verify", "show", "sarif", "compare", "packet", "verify-packet", "work-evidence"):
        parser = commands.add_parser(operation); parser.set_defaults(func=cmd)
        if operation not in ("policy", "analyze", "compare"): parser.add_argument("--bundle", required=True)
        if operation == "analyze":
            parser.add_argument("--repo", default="."); parser.add_argument("--revision", default="HEAD")
            parser.add_argument("--policy"); parser.add_argument("--at")
        if operation == "compare": parser.add_argument("--before", required=True); parser.add_argument("--after", required=True)
        if operation == "packet":
            parser.add_argument("--path", action="append", required=True)
            parser.add_argument("--max-files", type=int, default=20); parser.add_argument("--max-bytes", type=int, default=1024 * 1024)
        if operation == "verify-packet": parser.add_argument("--packet", required=True)
        if operation == "work-evidence": parser.add_argument("--inventory", required=True); parser.add_argument("--at")
        if operation not in ("verify", "verify-packet"): parser.add_argument("--output", required=operation == "analyze")
