"""Conservative comparisons, bounded source packets and explicit forge binding."""

import base64
from copy import deepcopy

from ..canonical import canonical_bytes, digest
from ..workscope.model import fields, instant, number, path, require, strings
from . import COMPARISON, ENGINE, PACKET
from .bundle import decode, sarif


def compare(before, after):
    a, b = before["analysis.json"], after["analysis.json"]
    reasons = []
    if a["subject"]["repository_id"] != b["subject"]["repository_id"]: reasons.append("LOCAL_REPOSITORY_IDENTITY_CHANGED")
    if before["policy.json"] != after["policy.json"]: reasons.append("ANALYSIS_POLICY_CHANGED")
    result = {"contract": COMPARISON, "before": before["manifest.json"]["bundle_id"], "after": after["manifest.json"]["bundle_id"],
              "status": "INCOMPARABLE" if reasons else "COMPARABLE", "reasons": reasons, "findings": [], "files": [],
              "authority": "STATIC_FINDING_TRANSITIONS; no health, productivity, improvement or acceptance judgement"}
    if reasons: return result
    old_files = {f["path"]: f for f in a["files"] if f["path"] is not None}
    new_files = {f["path"]: f for f in b["files"] if f["path"] is not None}
    old = {f["id"]: f for f in a["findings"]}; new = {f["id"]: f for f in b["findings"]}
    def known(files, finding):
        return all(p not in files or files[p]["status"] == "ANALYZED" for p in [finding["path"], *finding["related_paths"]])
    for fid in sorted(set(old) | set(new)):
        if fid in old and fid in new:
            state = "PERSISTING" if old[fid] == new[fid] else "CHANGED"
        elif fid in new:
            state = "NEW" if known(old_files, new[fid]) else "FIRST_OBSERVED"
        else:
            state = "RESOLVED" if known(new_files, old[fid]) else "UNOBSERVED"
        result["findings"].append({"id": fid, "state": state, "before": old.get(fid), "after": new.get(fid)})
    for filename in sorted(set(old_files) | set(new_files)):
        old_file, new_file = old_files.get(filename), new_files.get(filename)
        state = "ADDED" if old_file is None else "REMOVED" if new_file is None else "UNCHANGED" if old_file["object_id"] == new_file["object_id"] else "CHANGED"
        result["files"].append({"path": filename, "state": state, "before_status": old_file["status"] if old_file else "ABSENT",
                                "after_status": new_file["status"] if new_file else "ABSENT"})
    return result


def packet(decoded, paths, max_files=20, max_bytes=1024 * 1024):
    strings(paths, "packet paths", paths=True)
    number(max_files, 1, 1000); number(max_bytes, 1, 64 * 1024 * 1024)
    require(0 < len(paths) <= max_files, "source packet file budget")
    raw = decoded["inputs.json"]; entries = {e["path"]: e for e in raw["entries"] if e["path"] is not None}
    files, total = [], 0
    for filename in sorted(paths):
        require(filename in raw["sources"] and entries[filename]["status"] == "ADMITTED", "source packet path unavailable")
        data = decode(raw["sources"][filename], max_bytes); total += len(data)
        require(total <= max_bytes, "source packet byte budget")
        files.append({"path": filename, "object_id": entries[filename]["object_id"], "size": len(data), "base64": raw["sources"][filename]})
    value = {"contract": PACKET, "analysis_bundle_id": decoded["manifest.json"]["bundle_id"], "subject": deepcopy(raw["subject"]),
             "budget": {"max_files": max_files, "max_bytes": max_bytes}, "files": files, "total_bytes": total,
             "authority": "PINNED_LOCAL_SOURCE_ONLY; no live freshness, independent acceptance or execution authority"}
    value["packet_id"] = digest(value)
    return value


def verify_packet(value, decoded):
    fields(value, ("contract", "analysis_bundle_id", "subject", "budget", "files", "total_bytes", "authority", "packet_id"))
    fields(value["budget"], ("max_files", "max_bytes"))
    require(isinstance(value["files"], list), "packet files unavailable")
    for file in value["files"]: fields(file, ("path", "object_id", "size", "base64")); path(file["path"])
    expected = packet(decoded, [f["path"] for f in value["files"]], **value["budget"])
    require(value == expected, "source packet does not match admitted analysis")
    return value


def work_evidence(decoded, inventory, at=None):
    from ..workscope.evidence import empty_evidence, source, validate
    from ..workscope.model import inventory as admit_inventory
    admit_inventory(inventory)
    require(decoded["analysis.json"]["subject"]["revision"] == inventory["subject"]["revision"], "analysis/work revision mismatch")
    # The caller supplies an already admitted forge inventory. Local roots or a
    # remote URL never stand in for an immutable provider project identity.
    analysis = decoded["analysis.json"]
    observed = analysis["observed_at"]
    require(at is None or instant(at) == instant(observed), "export cannot change analysis observation time")
    # Existing sarif.v1 admission defines URI strings as repository-relative
    # source paths. Preserve that historical profile, while the standalone
    # SARIF artifact uses encoded URI references for external consumers.
    report = canonical_bytes(sarif(analysis, encode_paths=False))
    value = empty_evidence()
    entry = source("sarif.v1", ENGINE, "1", deepcopy(inventory["subject"]), observed, report)
    if analysis["coverage"] != "COMPLETE":
        entry.update(status="PARTIAL", reason="CODE_SOURCE_COVERAGE_" + analysis["coverage"])
    value["sources"].append(entry)
    validate(value)
    return value
