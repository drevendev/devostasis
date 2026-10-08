"""Explicit consumer bindings and immutable operational audit, outside bundles."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import quote
from uuid import uuid4

from .. import __version__
from ..canonical import canonical_bytes, digest, digest_bytes, loads
from .bundle import MEMBERS, atomic, build, latest, locked, publish, read, verify, verify_content
from .collect import collect
from .evidence import empty_evidence
from .handoff import verify_packet
from .model import fields, identity, instant, number, policy, require, strings, subject, text, timestamp

ADOPTION = "devostasis.work-adoption.v1"
INVOCATION = "devostasis.work-invocation.v1"
RESULT = "devostasis.work-result.v1"
AUDIT = "devostasis.work-history-audit.v1"
MAX_BYTES = 64 * 1024 * 1024
MAX_RECORDS = 2000
AUTHORITY = "CALLER_REPORT_ONLY; no independent acceptance, claim, merge or deployment authority"


def clock():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hash_ref(value):
    require(isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value), "invalid digest reference")
    return value


def no_links(path):
    result = Path(path).absolute()
    require(all(not p.is_symlink() and not (hasattr(p, "is_junction") and p.is_junction())
                for p in (result, *result.parents)), "linked operational store path")
    return result


def project_root(store, expected, section="work"):
    fields(expected, ("provider", "endpoint", "project_id"))
    # Reuse the ordinary exact subject admission without inventing a revision.
    subject({**expected, "locator": "validation", "revision": "0" * 40, "context": "CANONICAL"})
    return no_links(Path(store) / section / digest(expected)[7:])


def binding(value, config=None):
    fields(value, ("contract", "integration_id", "enabled", "engine_version", "project", "policy", "selection", "budget"))
    require(value["contract"] == ADOPTION, "unsupported adoption contract")
    text(value["integration_id"]); require(type(value["enabled"]) is bool, "explicit enabled boolean required")
    text(value["engine_version"])
    fields(value["project"], ("provider", "endpoint", "project_id", "locator"))
    subject({**value["project"], "revision": "0" * 40, "context": "CANONICAL"})
    locator = value["project"]["locator"]
    require(re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", locator) or
            value["project"]["provider"] == "gitlab" and locator.isdigit(), "invalid adoption locator")
    require(all(part not in (".", "..") for part in locator.split("/")), "invalid adoption locator")
    require(value["project"]["provider"] != "github" or len(locator.split("/")) == 2, "invalid GitHub adoption locator")
    fields(value["policy"], ("actor", "version", "digest"))
    text(value["policy"]["actor"]); text(value["policy"]["version"]); hash_ref(value["policy"]["digest"])
    fields(value["selection"], ("mode", "changes"))
    require(value["selection"]["mode"] in ("OPEN_AND_REGISTERED", "REGISTERED", "CHANGES"), "invalid adoption selection")
    strings(value["selection"]["changes"], "selected changes")
    require(len(value["selection"]["changes"]) <= 100 and all(c.isdigit() for c in value["selection"]["changes"]),
            "invalid bounded change selection")
    require((value["selection"]["mode"] == "CHANGES") == bool(value["selection"]["changes"]), "selection mode mismatch")
    fields(value["budget"], ("max_requests", "max_pages", "seconds", "workers"))
    for key, high in (("max_requests", 10000), ("max_pages", 100), ("seconds", 3600), ("workers", 8)):
        number(value["budget"][key], 1, high)
    if config is not None:
        policy(config)
        require(value["policy"] == {"actor": config["actor"], "version": config["version"], "digest": digest(config)},
                "adoption policy binding mismatch")
    canonical_bytes(value)
    return value


def make_binding(project, config, integration_id, enabled=False):
    return binding({"contract": ADOPTION, "integration_id": integration_id, "enabled": enabled,
        "engine_version": __version__, "project": project,
        "policy": {"actor": config["actor"], "version": config["version"], "digest": digest(config)},
        "selection": {"mode": "REGISTERED", "changes": []},
        "budget": {"max_requests": 100, "max_pages": 10, "seconds": 120, "workers": 4}}, config)


def append_record(store, expected, category, filename, record):
    require(category in ("runs", "results") and re.fullmatch(r"[0-9a-f]{32}|[0-9a-f]{64}", filename), "invalid record path")
    root = project_root(store, expected, "operations")
    root.mkdir(parents=True, exist_ok=True); no_links(root)
    with locked(root / ".lock"):
        folder = no_links(root / category); folder.mkdir(exist_ok=True)
        dest = no_links(folder / (filename + ".json"))
        data = canonical_bytes(record)
        require(len(data) <= MAX_BYTES, "operational record byte cap")
        if dest.exists():
            require(dest.is_file() and dest.read_bytes() == data, "immutable operational record collision")
        else:
            atomic(dest, data)
    return dest


def invocation(record, decoded=None):
    fields(record, ("contract", "run_id", "binding", "binding_digest", "started_at", "finished_at",
                   "status", "bundle_id", "manifest_digest", "reasons", "telemetry"))
    require(record["contract"] == INVOCATION and isinstance(record["run_id"], str) and
            re.fullmatch(r"[0-9a-f]{32}", record["run_id"]), "unsupported invocation record")
    binding(record["binding"])
    require(record["binding_digest"] == digest(record["binding"]), "invocation binding digest mismatch")
    require(instant(record["started_at"]) <= instant(record["finished_at"]), "invocation clock mismatch")
    require(record["status"] in ("COMPLETE", "PARTIAL", "FAILED", "DISABLED"), "invalid invocation status")
    strings(record["reasons"], "invocation reasons")
    fields(record["telemetry"], ("requests", "response_bytes", "workers"))
    number(record["telemetry"]["requests"], 0, record["binding"]["budget"]["max_requests"])
    number(record["telemetry"]["response_bytes"], 0, 10000 * 4 * 1024 * 1024)
    require(record["telemetry"]["workers"] == record["binding"]["budget"]["workers"], "invocation worker mismatch")
    success = record["status"] in ("COMPLETE", "PARTIAL")
    if not success:
        require(record["bundle_id"] is None and record["manifest_digest"] is None and record["reasons"], "failure must not claim evidence")
        require((record["status"] == "DISABLED") == (not record["binding"]["enabled"]), "disabled invocation mismatch")
        require(record["status"] != "DISABLED" or
                record["telemetry"]["requests"] == record["telemetry"]["response_bytes"] == 0,
                "disabled invocation claimed network telemetry")
    else:
        require(record["binding"]["enabled"], "disabled invocation claimed a bundle")
        hash_ref(record["bundle_id"]); hash_ref(record["manifest_digest"])
        if decoded is not None:
            scope = decoded["scope.json"]
            require(scope["subject"]["context"] == "CANONICAL" and
                    identity(scope["subject"]) == identity(record["binding"]["project"]) and
                    decoded["manifest.json"]["bundle_id"] == record["bundle_id"] and
                    digest(decoded["manifest.json"]) == record["manifest_digest"], "invocation bundle binding mismatch")
            binding(record["binding"], decoded["policy.json"])
            inv = decoded["inventory.json"]
            require(instant(record["started_at"]) <= instant(scope["observed_at"]) <= instant(record["finished_at"]), "invocation observation clock mismatch")
            selected = record["binding"]["selection"]["mode"] != "OPEN_AND_REGISTERED"
            require((inv["selection"]["changes"] == "SELECTED") == selected, "invocation selection mismatch")
            if selected:
                allowed = set(record["binding"]["selection"]["changes"]) | {
                    ref for criterion in decoded["policy.json"]["criteria"] for ref in criterion["implementations"]}
                require(all(change["id"] in allowed for change in inv["changes"]["items"]),
                        "invocation selected change binding mismatch")
            partial = bool(scope["gaps"]) or any(inv[k]["status"] != "COMPLETE" for k in ("changes", "issues"))
            require(record["status"] == ("PARTIAL" if partial else "COMPLETE"), "invocation coverage mismatch")
    return record


def observe(value, config, store, client_factory, at=None, evidence=None):
    binding(value, config)
    require(value["engine_version"] == __version__, "adoption engine version mismatch")
    project_root(store, identity(value["project"]))
    project_root(store, identity(value["project"]), "operations")
    started = timestamp(at or clock())
    record = {"contract": INVOCATION, "run_id": uuid4().hex, "binding": deepcopy(value), "binding_digest": digest(value),
        "started_at": started, "finished_at": started, "status": "DISABLED", "bundle_id": None,
        "manifest_digest": None, "reasons": ["ADOPTION_DISABLED"],
        "telemetry": {"requests": 0, "response_bytes": 0, "workers": value["budget"]["workers"]}}
    dest, client = None, None
    if value["enabled"]:
        try:
            client = client_factory(value)
            require(client.provider == value["project"]["provider"] and client.endpoint == value["project"]["endpoint"] and
                    client.workers == value["budget"]["workers"] and client.max_requests == value["budget"]["max_requests"] and
                    client.max_pages == value["budget"]["max_pages"] and client.seconds == value["budget"]["seconds"], "adoption client binding mismatch")
            locator = value["project"]["locator"]
            meta, error = client.obj(("/repos/" if client.provider == "github" else "/projects/") + quote(locator, safe="/" if client.provider == "github" else ""))
            require(meta is not None and str(meta.get("id")) == value["project"]["project_id"], error or "ADOPTION_PROJECT_MISMATCH")
            selection = value["selection"]
            refs = None if selection["mode"] == "OPEN_AND_REGISTERED" else selection["changes"]
            inv = collect(client, locator, config, at, change_refs=refs)
            require(identity(inv["subject"]) == identity(value["project"]), "ADOPTION_PROJECT_MISMATCH")
            manifest, content = build(inv, config, evidence or empty_evidence())
            decoded = verify_content(content)
            dest = publish(store, content)
            partial = bool(decoded["scope.json"]["gaps"]) or any(inv[k]["status"] != "COMPLETE" for k in ("changes", "issues"))
            record.update(status="PARTIAL" if partial else "COMPLETE", bundle_id=manifest["bundle_id"],
                          manifest_digest=digest_bytes(content["manifest.json"]), reasons=[])
        except Exception as exc:  # Every failed invocation remains visible, including malformed provider data.
            reason = re.sub(r"[\x00-\x1f]", " ", f"{type(exc).__name__}:{exc}")[:8192]
            record.update(status="FAILED", reasons=[reason])
    record["finished_at"] = timestamp(at or clock())
    if client is not None:
        record["telemetry"].update(requests=client.requests, response_bytes=sum(t["bytes"] for t in client.telemetry))
    invocation(record, verify(dest) if dest else None)
    receipt = append_record(store, identity(value["project"]), "runs", record["run_id"], record)
    return {"status": record["status"], "bundle_id": record["bundle_id"], "path": str(dest.resolve()) if dest else None,
            "invocation": str(receipt.resolve()), "run_id": record["run_id"], "reasons": record["reasons"]}


def result_record(record, decoded):
    fields(record, ("contract", "result_id", "scope_bundle_id", "packet", "claim", "recorded_at", "authority"))
    require(record["contract"] == RESULT and record["result_id"] == digest({k: v for k, v in record.items() if k != "result_id"}), "result identity mismatch")
    require(record["scope_bundle_id"] == decoded["manifest.json"]["bundle_id"] and record["authority"] == AUTHORITY, "result scope or authority mismatch")
    config = decoded["policy.json"]; packet = record["packet"]; claim = record["claim"]
    verify_packet(packet, decoded, packet["checked_at"], config["actor"], config["version"], identity(decoded["scope.json"]["subject"]))
    require(instant(record["recorded_at"]) >= instant(packet["checked_at"]), "result clock predates handoff")
    fields(claim, ("actor", "outcome", "acceptance", "notes"))
    require(claim["actor"] == config["actor"] and claim["outcome"] in ("REPORTED_COMPLETE", "BLOCKED", "ABANDONED"), "result actor or outcome mismatch")
    text(claim["notes"]); require(isinstance(claim["acceptance"], list), "result acceptance must be explicit")
    require([a["criterion"] for a in claim["acceptance"]] == packet["item"]["acceptance"], "result acceptance coverage mismatch")
    for answer in claim["acceptance"]:
        fields(answer, ("criterion", "status", "evidence"))
        require(answer["status"] in ("PASS", "FAIL", "UNKNOWN"), "invalid reported acceptance")
        strings(answer["evidence"], "result evidence references")
        require(answer["status"] != "PASS" or answer["evidence"], "reported pass requires evidence reference")
        require(claim["outcome"] != "REPORTED_COMPLETE" or answer["status"] == "PASS", "incomplete acceptance cannot report completion")
    canonical_bytes(record)
    return record


def record_result(decoded, packet, claim, store, at=None):
    record = {"contract": RESULT, "scope_bundle_id": decoded["manifest.json"]["bundle_id"], "packet": deepcopy(packet),
              "claim": deepcopy(claim), "recorded_at": timestamp(at or clock()), "authority": AUTHORITY}
    record["result_id"] = digest(record)
    result_record(record, decoded)
    project_root(store, identity(decoded["scope.json"]["subject"]))
    # Preserve the referenced generation even when the caller uses another local store.
    _, content = build(decoded["inventory.json"], decoded["policy.json"], decoded["evidence.json"],
                       decoded["scope.json"]["planned_at"], decoded["manifest.json"]["vitals_anchor"])
    publish(store, content)
    dest = append_record(store, identity(decoded["scope.json"]["subject"]), "results", record["result_id"][7:], record)
    return {"result_id": record["result_id"], "path": str(dest.resolve()), "outcome": claim["outcome"], "authority": AUTHORITY}


def snapshot(store, expected, max_bytes=MAX_BYTES):
    """Read and verify the whole selected project; no filesystem extraction."""
    number(max_bytes, 1, 512 * 1024 * 1024)
    root = project_root(store, expected)
    payload, bundles, total = {}, {}, 0
    folders = root / "bundles"
    if folders.exists():
        no_links(folders)
        entries = sorted(folders.iterdir())
        require(len(entries) <= MAX_RECORDS, "history generation cap")
        for directory in entries:
            require(re.fullmatch(r"[0-9a-f]{64}", directory.name), "invalid history generation path")
            no_links(directory)
            require(sum((directory / name).stat().st_size for name in (*MEMBERS, "manifest.json")) <= max_bytes - total,
                    "history byte cap")
            content = read(directory); total += sum(map(len, content.values()))
            require(total <= max_bytes, "history byte cap")
            decoded = verify_content(content); bid = decoded["manifest.json"]["bundle_id"]
            require(bid[7:] == directory.name and identity(decoded["scope.json"]["subject"]) == expected, "history project or path binding mismatch")
            bundles[bid] = decoded
            payload.update({f"bundles/{directory.name}/{name}": data for name, data in content.items()})
    latest_id = None
    canonical_times = {}
    for bid, decoded in bundles.items():
        scope = decoded["scope.json"]
        if scope["subject"]["context"] == "CANONICAL":
            at = instant(scope["observed_at"])
            require(at not in canonical_times or canonical_times[at] == bid, "history same-time canonical collision")
            canonical_times[at] = bid
    if (root / "latest.json").exists():
        decoded = latest(root); latest_id = decoded["manifest.json"]["bundle_id"]
        require(latest_id in bundles, "latest generation absent from history")
        canonical = [v for v in bundles.values() if v["scope.json"]["subject"]["context"] == "CANONICAL"]
        require(instant(decoded["scope.json"]["observed_at"]) == max(instant(v["scope.json"]["observed_at"]) for v in canonical),
                "latest pointer is older than recorded canonical history")
    records = {"runs": [], "results": []}
    for category in records:
        folder = project_root(store, expected, "operations") / category
        if not folder.exists():
            continue
        no_links(folder); entries = sorted(folder.iterdir())
        require(len(entries) <= MAX_RECORDS, "operational record count cap")
        for filename in entries:
            no_links(filename)
            pattern = r"[0-9a-f]{32}\.json" if category == "runs" else r"[0-9a-f]{64}\.json"
            require(re.fullmatch(pattern, filename.name) and filename.is_file() and filename.stat().st_size <= max_bytes - total,
                    "invalid operational record path or byte cap")
            data = filename.read_bytes(); total += len(data); record = loads(data.decode("utf-8"))
            require(data == canonical_bytes(record), "noncanonical operational record")
            if category == "runs":
                decoded = bundles.get(record.get("bundle_id"))
                require(record.get("bundle_id") is None or decoded is not None, "invocation referenced bundle unavailable")
                invocation(record, decoded)
                require(identity(record["binding"]["project"]) == expected and filename.stem == record["run_id"], "invocation project/path mismatch")
            else:
                require(record.get("scope_bundle_id") in bundles, "result referenced bundle unavailable")
                result_record(record, bundles[record["scope_bundle_id"]])
                require(filename.stem == record["result_id"][7:], "result path mismatch")
            records[category].append(record)
            payload[f"{category}/{filename.name}"] = data
    return payload, bundles, records, latest_id


def audit(store, expected, at=None, max_bytes=MAX_BYTES):
    _, bundles, records, latest_id = snapshot(store, expected, max_bytes)
    canonical = [v["scope.json"] for v in bundles.values() if v["scope.json"]["subject"]["context"] == "CANONICAL"]
    times = sorted(instant(s["observed_at"]) for s in canonical)
    now = instant(at or clock()); current = bundles[latest_id]["scope.json"] if latest_id else None
    status = "EMPTY" if not bundles else "LATEST_UNAVAILABLE" if current is None else "FUTURE" if instant(current["planned_at"]) > now else "EXPIRED" if instant(current["expires_at"]) < now else "AVAILABLE"
    return {"contract": AUDIT, "project": expected, "status": status, "latest_bundle_id": latest_id,
        "latest_coverage": current["coverage"] if current else None, "latest_gap_count": len(current["gaps"]) if current else None,
        "bundles": len(bundles), "canonical_generations": len(canonical), "candidate_generations": len(bundles) - len(canonical),
        "utc_calendar_days": len({t.date() for t in times}),
        "first_observed_at": timestamp(times[0].isoformat()) if times else None,
        "last_observed_at": timestamp(times[-1].isoformat()) if times else None,
        "largest_gap_seconds": max((int((b - a).total_seconds()) for a, b in zip(times, times[1:])), default=0),
        "invocations": {s: sum(r["status"] == s for r in records["runs"]) for s in ("COMPLETE", "PARTIAL", "FAILED", "DISABLED")},
        "caller_results": {s: sum(r["claim"]["outcome"] == s for r in records["results"]) for s in ("REPORTED_COMPLETE", "BLOCKED", "ABANDONED")},
        "authority": AUTHORITY}
