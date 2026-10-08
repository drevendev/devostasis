"""Bounded, deterministic private history transfer; never extract archive paths."""

from io import BytesIO
from pathlib import Path
import re
import stat
from zipfile import BadZipFile, ZIP_STORED, ZipFile, ZipInfo

from ..canonical import canonical_bytes, digest, digest_bytes, loads
from .bundle import MEMBERS, atomic, publish, verify_content
from .model import fields, identity, instant, number, require
from .operations import MAX_BYTES, MAX_RECORDS, append_record, hash_ref, invocation, no_links, result_record, snapshot

CONTRACT = "devostasis.work-history-archive.v1"


def export_history(store, expected, output, max_bytes=MAX_BYTES):
    payload, _, _, latest_id = snapshot(store, expected, max_bytes)
    index = {"contract": CONTRACT, "project": expected, "latest_bundle_id": latest_id,
             "members": {name: {"digest": digest_bytes(data), "size": len(data)} for name, data in sorted(payload.items())}}
    payload["index.json"] = canonical_bytes(index)
    stream = BytesIO()
    with ZipFile(stream, "w", compression=ZIP_STORED) as archive:
        for name, data in sorted(payload.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3; info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, data)
    data = stream.getvalue()
    require(len(data) <= max_bytes, "history archive byte cap")
    dest = no_links(output); dest.parent.mkdir(parents=True, exist_ok=True); no_links(dest)
    atomic(dest, data)
    return {"contract": CONTRACT, "archive_digest": digest_bytes(data), "index_digest": digest(index),
            "members": len(index["members"]), "bytes": len(data), "path": str(dest)}


def admit_archive(filename, expected, max_bytes=MAX_BYTES):
    number(max_bytes, 1, 512 * 1024 * 1024)
    filename = no_links(filename)
    require(filename.is_file() and filename.stat().st_size <= max_bytes, "archive file unavailable or byte cap")
    try:
        with ZipFile(filename) as archive:
            infos = archive.infolist()
            require(1 <= len(infos) <= MAX_RECORDS * 8 + 1, "archive member count cap")
            names = [i.filename for i in infos]
            require(len(set(names)) == len(names) and "index.json" in names, "archive duplicate or missing index")
            require(sum(i.file_size for i in infos) <= max_bytes, "archive expanded byte cap")
            for info in infos:
                mode = info.external_attr >> 16
                require(info.compress_type == ZIP_STORED and not info.flag_bits & 1 and
                        stat.S_IFMT(mode) == stat.S_IFREG and not info.is_dir(), "archive member type or compression refused")
                require(info.filename == "index.json" or re.fullmatch(
                    r"bundles/[0-9a-f]{64}/(?:inventory\.json|policy\.json|evidence\.json|scope\.json|report\.md|manifest\.json)|runs/[0-9a-f]{32}\.json|results/[0-9a-f]{64}\.json",
                    info.filename), "archive path refused")
            payload = {i.filename: archive.read(i) for i in infos}
    except (BadZipFile, RuntimeError) as exc:
        raise ValueError("archive integrity unavailable") from exc
    index_bytes = payload.pop("index.json")
    index = loads(index_bytes.decode("utf-8"))
    fields(index, ("contract", "project", "latest_bundle_id", "members"))
    require(index["contract"] == CONTRACT and index["project"] == expected, "archive project or contract mismatch")
    # Validate the expected project even for a deliberately empty archive.
    from .operations import project_root
    project_root(filename.parent, expected)
    require(canonical_bytes(index) == index_bytes, "archive index is not canonical")
    require(isinstance(index["members"], dict) and set(index["members"]) == set(payload), "archive index member mismatch")
    for name, data in payload.items():
        descriptor = index["members"][name]; fields(descriptor, ("digest", "size"))
        require(type(descriptor["size"]) is int and descriptor["size"] == len(data) and descriptor["digest"] == digest_bytes(data),
                "archive member digest or size mismatch")
    bundles, content = {}, {}
    for prefix in sorted({name.split("/")[1] for name in payload if name.startswith("bundles/")}):
        members = {name: payload[f"bundles/{prefix}/{name}"] for name in (*MEMBERS, "manifest.json")}
        decoded = verify_content(members); bid = decoded["manifest.json"]["bundle_id"]
        require(bid == "sha256:" + prefix and identity(decoded["scope.json"]["subject"]) == expected, "archive bundle binding mismatch")
        bundles[bid], content[bid] = decoded, members
    require(len(bundles) <= MAX_RECORDS, "archive generation cap")
    canonical = [b for b in bundles.values() if b["scope.json"]["subject"]["context"] == "CANONICAL"]
    if index["latest_bundle_id"] is not None:
        hash_ref(index["latest_bundle_id"])
        require(index["latest_bundle_id"] in bundles and bundles[index["latest_bundle_id"]] in canonical, "archive latest binding mismatch")
        require(instant(bundles[index["latest_bundle_id"]]["scope.json"]["observed_at"]) ==
                max(instant(b["scope.json"]["observed_at"]) for b in canonical), "archive latest is not newest")
    records = {"runs": [], "results": []}
    for name, data in sorted(payload.items()):
        category = name.split("/", 1)[0]
        if category not in records:
            continue
        record = loads(data.decode("utf-8")); require(data == canonical_bytes(record), "archive record is not canonical")
        if category == "runs":
            require(record.get("bundle_id") is None or record["bundle_id"] in bundles, "archive invocation bundle unavailable")
            invocation(record, bundles.get(record["bundle_id"]))
            require(identity(record["binding"]["project"]) == expected and name == f"runs/{record['run_id']}.json", "archive invocation binding mismatch")
        else:
            require(record.get("scope_bundle_id") in bundles, "archive result bundle unavailable")
            result_record(record, bundles[record["scope_bundle_id"]])
            require(name == f"results/{record['result_id'][7:]}.json", "archive result binding mismatch")
        records[category].append(record)
    require(all(len(values) <= MAX_RECORDS for values in records.values()), "archive operational record cap")
    # Reject equal-time different canonical generations before any store mutation.
    seen = {}
    for b in canonical:
        at = instant(b["scope.json"]["observed_at"])
        bid = b["manifest.json"]["bundle_id"]
        require(at not in seen or seen[at] == bid, "archive same-time canonical collision")
        seen[at] = bid
    return content, records, index


def import_history(filename, expected, store, max_bytes=MAX_BYTES):
    content, records, index = admit_archive(filename, expected, max_bytes)
    # Verify the destination as well, and preflight collisions before appending.
    from .operations import project_root
    root = project_root(store, expected); root.mkdir(parents=True, exist_ok=True)
    from .bundle import locked
    # This import lock serializes importers; the ordinary per-bundle publisher
    # still owns writer locking and monotonic latest promotion.
    with locked(root / ".import-lock"):
        old, existing, _, _ = snapshot(store, expected, max_bytes)
        combined = dict(old)
        for bid, members in content.items():
            for name, data in members.items():
                key = f"bundles/{bid[7:]}/{name}"
                require(key not in old or old[key] == data, "history import immutable collision")
                combined[key] = data
        for category, values in records.items():
            for record in values:
                ref = record["run_id"] if category == "runs" else record["result_id"][7:]
                key = f"{category}/{ref}.json"
                require(key not in old or old[key] == canonical_bytes(record), "history import record collision")
                combined[key] = canonical_bytes(record)
        require(sum(map(len, combined.values())) <= max_bytes, "combined history byte cap")
        for category in ("bundles", "runs", "results"):
            require(len({k.split("/")[1] for k in combined if k.startswith(category + "/")}) <= MAX_RECORDS,
                    "combined history record cap")
        seen = {}
        for bid, m in {**existing, **{bid: verify_content(m) for bid, m in content.items()}}.items():
            scope = m["scope.json"]
            if scope["subject"]["context"] == "CANONICAL":
                at = instant(scope["observed_at"])
                require(at not in seen or seen[at] == bid, "destination same-time canonical collision")
                seen[at] = bid
        ordered = sorted(content.values(), key=lambda m: (instant(loads(m["scope.json"].decode())["observed_at"]), digest_bytes(m["manifest.json"])))
        for members in ordered:
            publish(store, members)
        for category, values in records.items():
            for record in values:
                ref = record["run_id"] if category == "runs" else record["result_id"][7:]
                append_record(store, expected, category, ref, record)
    return {"contract": CONTRACT, "status": "IMPORTED", "index_digest": digest(index), "bundles": len(content),
            "invocations": len(records["runs"]), "caller_results": len(records["results"])}
