"""Canonical analysis artifacts with exact offline replay and Git source proofs."""

import base64
from copy import deepcopy
from datetime import timedelta
import html
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import quote

from ..canonical import canonical_bytes, digest, digest_bytes, loads
from ..workscope.bundle import locked
from ..workscope.model import fields, instant, number, path, require, revision, strings, timestamp
from ..workscope.operations import no_links
from . import CONTRACT, ENGINE
from .engine import RULES, evaluate, policy
from .git import object_digest

MEMBERS = ("inputs.json", "policy.json", "analysis.json", "findings.sarif", "report.md")
MAX_BUNDLE_BYTES = 128 * 1024 * 1024


def decode(value, cap):
    require(isinstance(value, str) and len(value) <= (cap + 2) // 3 * 4, "source encoding byte cap")
    try: data = base64.b64decode(value, validate=True)
    except ValueError as exc: raise ValueError("source base64 unavailable") from exc
    require(len(data) <= cap and base64.b64encode(data).decode("ascii") == value, "noncanonical source base64")
    return data


def admit(raw, config):
    policy(config)
    fields(raw, ("subject", "observed_at", "entries", "sources", "history", "proof"))
    subject = raw["subject"]
    fields(subject, ("kind", "object_format", "roots", "repository_id", "revision", "tree"))
    require(subject["kind"] == "LOCAL_GIT" and subject["object_format"] in ("sha1", "sha256"), "unsupported local source identity")
    width = 40 if subject["object_format"] == "sha1" else 64
    for ref in (subject["revision"], subject["tree"]):
        revision(ref); require(len(ref) == width, "Git object format mismatch")
    strings(subject["roots"], "root commits")
    require(0 < len(subject["roots"]) <= 256 and subject["roots"] == sorted(subject["roots"]), "noncanonical root identity")
    for ref in subject["roots"]: revision(ref); require(len(ref) == width, "root format mismatch")
    require(subject["repository_id"] == digest({"object_format": subject["object_format"], "roots": subject["roots"]}), "repository identity mismatch")
    instant(raw["observed_at"])
    fields(raw["proof"], ("commit", "trees"))
    commit = decode(raw["proof"]["commit"], 1024 * 1024)
    require(object_digest(commit, subject["object_format"], "commit") == subject["revision"], "commit proof mismatch")
    tree_headers = [line[5:] for line in commit.split(b"\n\n", 1)[0].splitlines() if line.startswith(b"tree ")]
    require(tree_headers == [subject["tree"].encode("ascii")], "commit tree binding mismatch")
    trees = raw["proof"]["trees"]
    require(isinstance(trees, dict) and 0 < len(trees) <= 10000, "tree proof unavailable")
    tree_bytes, total = {}, 0
    for oid, encoded in trees.items():
        revision(oid); require(len(oid) == width, "tree format mismatch")
        data = decode(encoded, 8 * 1024 * 1024); total += len(data)
        require(total <= 8 * 1024 * 1024 and object_digest(data, subject["object_format"], "tree") == oid, "tree proof mismatch or byte cap")
        tree_bytes[oid] = data
    expected, visited = {}, set()
    stack = [(subject["tree"], b"", frozenset())]
    while stack:
        oid, prefix, parents = stack.pop()
        require(oid in tree_bytes and oid not in parents, "tree proof missing or cyclic")
        visited.add(oid); data = tree_bytes[oid]; offset = 0
        while offset < len(data):
            space = data.find(b" ", offset); end = data.find(b"\0", space)
            require(space > offset and end > space + 1 and end + 1 + width // 2 <= len(data), "tree entry malformed")
            mode, name = data[offset:space], data[space + 1:end]
            require(b"/" not in name and name not in (b".", b".."), "tree name malformed")
            child = data[end + 1:end + 1 + width // 2].hex(); offset = end + 1 + width // 2
            filename = prefix + name
            if mode == b"40000":
                stack.append((child, filename + b"/", parents | {oid}))
            else:
                require(mode in (b"100644", b"100755", b"120000", b"160000") and filename not in expected, "tree entry mode or duplicate path")
                expected[filename] = (mode.decode("ascii"), "commit" if mode == b"160000" else "blob", child)
        require(len(expected) <= 100000 and len(stack) <= 10000, "tree expansion cap")
    require(visited == set(trees), "unused tree proof")
    require(isinstance(raw["entries"], list) and len(raw["entries"]) == len(expected), "source inventory incomplete")
    require(isinstance(raw["sources"], dict), "source map unavailable")
    seen, admitted, source_total = [], set(), 0
    for entry in raw["entries"]:
        fields(entry, ("path", "path_base64", "mode", "kind", "object_id", "size", "status", "reason"))
        filename = decode(entry["path_base64"], 65536); seen.append(filename)
        require(filename in expected and (entry["mode"], entry["kind"], entry["object_id"]) == expected[filename], "inventory tree binding mismatch")
        safe = None
        try: safe = path(filename.decode("utf-8"))
        except (ValueError, UnicodeError): pass
        require(entry["path"] == safe, "inventory path decoding mismatch")
        require(entry["status"] in ("ADMITTED", "UNAVAILABLE", "UNSUPPORTED", "OUT_OF_SCOPE"), "inventory availability unknown")
        if entry["kind"] == "blob": number(entry["size"], 0, 2**63 - 1)
        else: require(entry["size"] is None, "submodule must not claim blob size")
        included = safe is not None and (not config["include"] or any(safe == p or safe.startswith(p + "/") for p in config["include"]))
        excluded = safe is not None and any(safe == p or safe.startswith(p + "/") for p in config["exclude"])
        if entry["status"] == "ADMITTED":
            require(included and not excluded and safe.endswith(".py") and entry["mode"] in ("100644", "100755") and entry["reason"] is None, "source scope mismatch")
            require(safe in raw["sources"], "admitted source missing")
            data = decode(raw["sources"][safe], config["budget"]["max_file_bytes"])
            require(len(data) == entry["size"] and object_digest(data, subject["object_format"]) == entry["object_id"], "source blob binding mismatch")
            admitted.add(safe); source_total += len(data)
        elif entry["status"] == "OUT_OF_SCOPE": require(safe is not None and (not included or excluded) and entry["reason"] == "POLICY_EXCLUSION", "unjustified scope exclusion")
        elif entry["status"] == "UNSUPPORTED": require(included and not excluded and not safe.endswith(".py") and entry["mode"] in ("100644", "100755") and entry["reason"] == "LANGUAGE_UNSUPPORTED", "unsupported source mismatch")
        else:
            require(entry["reason"] in ("UNSAFE_PATH", "SOURCE_LINK_OR_SUBMODULE", "FILE_BYTE_CAP", "FILE_COUNT_CAP", "TOTAL_BYTE_CAP"), "unavailable source reason unknown")
    require(seen == sorted(set(seen)) and set(raw["sources"]) == admitted, "duplicate, unordered or foreign source")
    require(len(admitted) <= config["budget"]["max_files"] and source_total <= config["budget"]["max_total_bytes"], "source budget exceeded")
    history = raw["history"]
    fields(history, ("status", "reasons", "start", "end", "commits")); strings(history["reasons"], "history reasons")
    require(instant(history["end"]) == instant(raw["observed_at"]) and instant(history["start"]) == instant(history["end"]) - timedelta(days=config["history"]["days"]), "history window mismatch")
    require(history["status"] in ("COMPLETE", "PARTIAL", "UNAVAILABLE", "NOT_REQUESTED"), "history availability unknown")
    require((history["status"] == "NOT_REQUESTED") == (not config["history"]["enabled"]), "history enablement mismatch")
    require(isinstance(history["commits"], list) and len(history["commits"]) <= config["history"]["max_commits"], "history commit cap")
    require((history["status"] in ("PARTIAL", "UNAVAILABLE")) == bool(history["reasons"]), "history availability reason mismatch")
    require(history["status"] not in ("UNAVAILABLE", "NOT_REQUESTED") or not history["commits"], "unavailable history claims commits")
    refs = []
    for row in history["commits"]:
        fields(row, ("revision", "committed_at", "changes")); revision(row["revision"]); refs.append(row["revision"])
        require(len(row["revision"]) == width and instant(history["start"]) <= instant(row["committed_at"]) <= instant(history["end"]), "history revision/time mismatch")
        require(isinstance(row["changes"], list) and len(row["changes"]) <= 100000, "history change cap")
        paths = []
        for change in row["changes"]:
            fields(change, ("path", "added", "deleted")); path(change["path"]); paths.append(change["path"])
            require((change["added"] is None) == (change["deleted"] is None), "binary change mismatch")
            if change["added"] is not None:
                number(change["added"], 0, 2**63 - 1); number(change["deleted"], 0, 2**63 - 1)
        require(paths == sorted(set(paths)), "duplicate history paths")
    require(len(refs) == len(set(refs)) and history["commits"] == sorted(history["commits"], key=lambda c: (c["committed_at"], c["revision"])), "duplicate or unordered history")
    return raw


def escape(value):
    return re.sub(r"([\\`*_{}\[\]()#+.!|])", r"\\\1", html.escape(str(value), quote=True))


def sarif(analysis, *, encode_paths=True):
    return {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json", "runs": [{
        "tool": {"driver": {"name": "Devostasis Code Analysis", "version": ENGINE,
                            "rules": [{"id": r, "shortDescription": {"text": m}} for r, m in sorted(RULES.items())]}},
        "versionControlProvenance": [{"revisionId": analysis["subject"]["revision"]}],
        "properties": {"sourceCoverage": analysis["coverage"], "historyCoverage": analysis["history"]["status"], "authority": analysis["authority"]},
        "results": [{"ruleId": f["rule"], "level": f["level"], "message": {"text": f["message"]},
                     "partialFingerprints": {"devostasisFindingId": f["id"]},
                     "locations": [{"physicalLocation": {"artifactLocation": {"uri": quote(f["path"], safe="/") if encode_paths else f["path"]},
                                   "region": {"startLine": f["line"], "endLine": f["end_line"]}}}],
                     "properties": {"symbol": f["symbol"], "evidence": f["evidence"], "relatedPaths": f["related_paths"]}}
                    for f in analysis["findings"]]}]}


def render(analysis):
    counts = {s: sum(f["status"] == s for f in analysis["files"]) for s in
              ("ANALYZED", "PARSE_ERROR", "UNAVAILABLE", "UNSUPPORTED", "OUT_OF_SCOPE")}
    lines = ["# Offline repository analysis", "", "Revision: `" + analysis["subject"]["revision"] + "`",
        "", "Python grammar: 3.12. Static evidence only; repository code was not executed.",
        "", "Python source coverage: " + analysis["coverage"] + "; history: " + analysis["history"]["status"] + ".",
        "", "Unsupported and unavailable inputs do not establish an absence of findings.", "",
        "| Source status | Files |", "| --- | ---: |", *[f"| {s} | {n} |" for s, n in counts.items()],
        "", "## Findings", "", "| Path | Line | Rule | Symbol | Evidence |", "| --- | ---: | --- | --- | --- |"]
    lines += [f"| {escape(f['path'])} | {f['line']} | {f['rule']} | {escape(f['symbol'])} | {escape(canonical_bytes(f['evidence']).decode('utf-8'))} |" for f in analysis["findings"][:100]]
    lines += ["", f"Showing {min(100, len(analysis['findings']))} of {len(analysis['findings'])} findings; analysis.json and findings.sarif retain every finding.",
        "", "## Source gaps", "", "| Path | Status | Reason |", "| --- | --- | --- |"]
    gaps = [f for f in analysis["files"] if f["status"] in ("UNAVAILABLE", "PARSE_ERROR")]
    lines += [f"| {escape(f['path'] or '[unsafe path]')} | {f['status']} | {f['reason']} |" for f in gaps[:100]]
    lines += ["", f"Showing {min(100, len(gaps))} of {len(gaps)} source gaps.",
        "", "## Recent change evidence", "", "Non-merge commits in [" + analysis["history"]["start"] + ", " + analysis["history"]["end"] + "].",
        "", "Counts under PARTIAL history are observed counts, not complete totals or productivity.", "",
        "| Path | Revisions | Added | Deleted | Coverage |", "| --- | ---: | ---: | ---: | --- |"]
    lines += [f"| {escape(h['path'])} | {h['revisions']} | {h['added']} | {h['deleted']} | {h['coverage']} |" for h in analysis["hotspots"][:20]]
    lines += ["", f"Showing {min(20, len(analysis['hotspots']))} of {len(analysis['hotspots'])} paths.", "", analysis["authority"], ""]
    return "\n".join(lines).encode("utf-8")


def build(raw, config):
    admit(raw, config); analysis = evaluate(raw, config)
    content = {"inputs.json": canonical_bytes(raw), "policy.json": canonical_bytes(config), "analysis.json": canonical_bytes(analysis),
               "findings.sarif": canonical_bytes(sarif(analysis)), "report.md": render(analysis)}
    manifest = {"contract": CONTRACT, "engine": ENGINE, "subject": deepcopy(raw["subject"]),
                "members": {name: digest_bytes(data) for name, data in sorted(content.items())}}
    manifest["bundle_id"] = digest(manifest); content["manifest.json"] = canonical_bytes(manifest)
    require(sum(map(len, content.values())) <= MAX_BUNDLE_BYTES, "analysis bundle byte cap")
    return manifest, content


def verify_content(content):
    require(set(content) == set(MEMBERS) | {"manifest.json"} and sum(map(len, content.values())) <= MAX_BUNDLE_BYTES, "analysis member set/byte cap")
    decoded = {name: loads(data.decode("utf-8")) for name, data in content.items() if name != "report.md"}
    require(all(canonical_bytes(value) == content[name] for name, value in decoded.items()), "analysis member is not canonical")
    manifest = decoded["manifest.json"]
    fields(manifest, ("contract", "engine", "subject", "members", "bundle_id"))
    require(manifest["contract"] == CONTRACT and manifest["engine"] == ENGINE, "unsupported analysis lineage")
    expected, replay = build(decoded["inputs.json"], decoded["policy.json"])
    require(expected == manifest and replay == content, "analysis bundle does not replay")
    return decoded


def read(root):
    root = no_links(root)
    require(root.is_dir() and {p.name for p in root.iterdir()} == set(MEMBERS) | {"manifest.json"}, "analysis bundle directory/member mismatch")
    total, content = 0, {}
    for name in (*MEMBERS, "manifest.json"):
        file = no_links(root / name)
        require(file.is_file(), "analysis member is not a regular file")
        total += file.stat().st_size; require(total <= MAX_BUNDLE_BYTES, "analysis bundle byte cap")
        content[name] = file.read_bytes()
    return content


def verify(root):
    return verify_content(read(root))


def publish(root, content):
    verify_content(content); root = no_links(root)
    root.parent.mkdir(parents=True, exist_ok=True); no_links(root.parent)
    with locked(root.parent / ("." + root.name + ".code-lock")):
        if root.exists():
            require(read(root) == content, "analysis destination immutable collision")
            return root
        pending = Path(tempfile.mkdtemp(prefix="." + root.name + ".pending-", dir=root.parent))
        try:
            for name, data in content.items(): (pending / name).write_bytes(data)
            os.replace(pending, root)
        finally:
            if pending.exists():
                require(pending.resolve().parent == root.parent.resolve(), "pending cleanup outside output parent")
                shutil.rmtree(pending)
    return root
