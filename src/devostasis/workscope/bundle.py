"""Self-contained replayable bundles and atomic append-only publication."""

from __future__ import annotations

import base64
import contextlib
import os
import re
from pathlib import Path
import shutil
import tempfile

from ..canonical import canonical_bytes, digest, digest_bytes, loads
from . import CONTRACT, CONTRACTS, ENGINES
from .model import ROLES, ScopeError, fields, identity, instant, number, require
from .planner import project

MEMBERS = ("inventory.json", "policy.json", "evidence.json", "scope.json", "report.md")
MAX_MEMBER_BYTES = 300 * 1024 * 1024


def escape(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\n", " ").replace("\r", " ").replace("`", "&#96;")


def render(scope):
    rows = ["# Devostasis work scope", "", f"Observed: {scope['observed_at']} · expires: {scope['expires_at']}",
            "", escape(scope["authority"]), "", "| Queue | Eligibility | Source | Action | Reasons |", "| --- | --- | --- | --- | --- |"]
    for item in scope["items"]:
        rows.append("| " + " | ".join(escape(v) for v in (item["queue"], item["eligibility"], item["source"],
                                                         item["action"], ", ".join(item["reasons"]))) + " |")
    rows += ["", "Coverage: " + ", ".join(f"{k}={v}" for k, v in scope["coverage"].items()),
             f"Excluded: {len(scope['excluded'])}; evidence gaps: {len(scope['gaps'])}.", ""]
    return "\n".join(rows).encode("utf-8")


def build(inv, config, evidence, at=None, anchor=None):
    scope = project(inv, config, evidence, at)
    if anchor is not None:
        fields(anchor, ("bundle_id", "manifest_digest"))
        require(isinstance(anchor["bundle_id"], str) and re.fullmatch(r"[0-9a-f]{64}", anchor["bundle_id"]) and
                isinstance(anchor["manifest_digest"], str) and re.fullmatch(r"sha256:[0-9a-f]{64}", anchor["manifest_digest"]), "invalid Vitals anchor")
    content = {name: canonical_bytes(value) for name, value in zip(MEMBERS, (inv, config, evidence, scope))}
    content["report.md"] = render(scope)
    preimage = {"contract": inv["contract"], "kind": "bundle", "engine": ENGINES[inv["contract"]],
                "members": {k: digest_bytes(v) for k, v in content.items()}, "vitals_anchor": anchor}
    manifest = {**preimage, "bundle_id": digest(preimage)}
    content["manifest.json"] = canonical_bytes(manifest)
    return manifest, content


def read(path):
    root = Path(path)
    require(root.is_dir() and not root.is_symlink(), "bundle directory unavailable or linked")
    require({p.name for p in root.iterdir()} == set(MEMBERS) | {"manifest.json"}, "bundle has missing or extra members")
    output = {}
    for name in (*MEMBERS, "manifest.json"):
        member = root / name
        require(member.is_file() and not member.is_symlink() and member.stat().st_size <= MAX_MEMBER_BYTES,
                "bundle member invalid or exceeds byte budget")
        output[name] = member.read_bytes()
    return output


def verify_content(content):
    require(set(content) == set(MEMBERS) | {"manifest.json"}, "bundle member set mismatch")
    decoded = {k: loads(v.decode("utf-8")) for k, v in content.items() if k.endswith(".json")}
    for name, value in decoded.items():
        require(content[name] == canonical_bytes(value), "bundle member is not canonical")
    m = decoded["manifest.json"]
    fields(m, ("contract", "kind", "engine", "members", "vitals_anchor", "bundle_id"))
    require(m["contract"] in CONTRACTS and m["kind"] == "bundle" and m["engine"] == ENGINES[m["contract"]],
            "unsupported bundle contract or replay engine")
    require(set(m["members"]) == set(MEMBERS), "manifest member set mismatch")
    require(all(digest_bytes(content[k]) == m["members"][k] for k in MEMBERS), "bundle member digest mismatch")
    expected, replay = build(decoded["inventory.json"], decoded["policy.json"], decoded["evidence.json"],
                             decoded["scope.json"]["planned_at"], m["vitals_anchor"])
    require(expected == m and replay == content, "bundle does not replay from its admitted inputs")
    return decoded


def verify(path):
    return verify_content(read(path))


@contextlib.contextmanager
def locked(path):
    # OS locks release after process death; a leftover lock file is harmless.
    path = Path(path).absolute()
    require(all(not p.is_symlink() and not (hasattr(p, "is_junction") and p.is_junction())
                for p in (path, *path.parents)), "linked store lock path")
    handle = open(path, "a+b")
    if os.name == "nt":
        import msvcrt
        if handle.seek(0, 2) == 0:
            handle.write(b"0"); handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            handle.close(); raise ScopeError("scope store is locked by another publisher") from exc
        unlock = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close(); raise ScopeError("scope store is locked by another publisher") from exc
        unlock = lambda: fcntl.flock(handle, fcntl.LOCK_UN)
    try:
        yield
    finally:
        handle.seek(0); unlock(); handle.close()


def atomic(path, data):
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def publish(store, content):
    decoded = verify_content(content)
    scope = decoded["scope.json"]
    bundle_id = decoded["manifest.json"]["bundle_id"]
    key = digest(identity(scope["subject"]))[7:]
    root = Path(store) / "work" / key
    root.mkdir(parents=True, exist_ok=True)
    require(not root.is_symlink() and not root.parent.is_symlink(), "linked store project directory")
    dest = root / "bundles" / bundle_id[7:]
    with locked(root / ".lock"):
        dest.parent.mkdir(exist_ok=True)
        require(not dest.parent.is_symlink(), "linked immutable bundle directory")
        if dest.exists():
            require(read(dest) == content, "immutable bundle collision")
        else:
            stage = Path(tempfile.mkdtemp(prefix=".pending-", dir=dest.parent))
            try:
                for name, data in content.items():
                    with open(stage / name, "wb") as stream:
                        stream.write(data); stream.flush(); os.fsync(stream.fileno())
                verify(stage)
                os.rename(stage, dest)
            finally:
                if stage.exists():
                    require(stage.resolve().parent == dest.parent.resolve() and not stage.is_symlink(), "unsafe staging cleanup path")
                    shutil.rmtree(stage)
        # Candidate snapshots are preserved, but never become canonical latest.
        if scope["subject"]["context"] == "CANONICAL":
            pointer = root / "latest.json"
            if pointer.exists():
                old = latest(root)
                promote = instant(scope["observed_at"]) > instant(old["scope.json"]["observed_at"])
                if instant(scope["observed_at"]) == instant(old["scope.json"]["observed_at"]):
                    require(bundle_id == old["manifest.json"]["bundle_id"], "same-time canonical publication collision")
            else:
                promote = True
            if promote:
                atomic(pointer, canonical_bytes({"contract": decoded["manifest.json"]["contract"], "bundle_id": bundle_id,
                    "manifest_digest": digest_bytes(content["manifest.json"]), "project": identity(scope["subject"])}))
    return dest


def latest(root):
    pointer = Path(root) / "latest.json"
    require(pointer.is_file() and not pointer.is_symlink() and pointer.stat().st_size < 8192, "latest pointer unavailable")
    data = loads(pointer.read_text(encoding="utf-8"))
    fields(data, ("contract", "bundle_id", "manifest_digest", "project"))
    require(data["contract"] in CONTRACTS and isinstance(data["bundle_id"], str) and
            len(data["bundle_id"]) == 71 and all(c in "0123456789abcdef" for c in data["bundle_id"][7:])
            and data["bundle_id"].startswith("sha256:"), "invalid latest pointer")
    dest = Path(root) / "bundles" / data["bundle_id"][7:]
    content = read(dest); decoded = verify_content(content)
    require(digest_bytes(content["manifest.json"]) == data["manifest_digest"] and
            decoded["manifest.json"]["bundle_id"] == data["bundle_id"] and
            identity(decoded["scope.json"]["subject"]) == data["project"] and
            decoded["scope.json"]["subject"]["context"] == "CANONICAL", "latest pointer binding mismatch")
    return decoded


def slice_scope(scope, role="all", limit=20, cursor=None, at=None):
    require(role in ROLES, "unknown consumer role"); number(limit, 1, 1000)
    binding = {"scope": digest(scope), "role": role}
    offset = 0
    if cursor:
        require(isinstance(cursor, str) and len(cursor) < 4096, "invalid cursor")
        try:
            raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
            token = loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise ScopeError("invalid cursor") from exc
        fields(token, ("scope", "role", "offset"))
        require({k: token[k] for k in binding} == binding and canonical_bytes(token) == raw,
                "cursor belongs to another scope or role")
        offset = number(token["offset"], 0, 100000)
    if at is not None and instant(at) > instant(scope["expires_at"]):
        return {**binding, "status": "EXPIRED", "items": [{"id": digest({"recovery": identity(scope["subject"])}),
                "queue": "research", "action": "recover_evidence", "source": "inventory",
                "acceptance": ["Collect, rebuild and verify a fresh bounded scope before selecting work."]}],
                "cursor": None, "overflow": 0, "total": 1, "excluded": scope["excluded"]}
    items = [i for i in scope["items"] if i["queue"] in ROLES[role]]
    require(offset <= len(items), "cursor offset exceeds scope")
    end = min(offset + limit, len(items))
    token = base64.urlsafe_b64encode(canonical_bytes({**binding, "offset": end})).decode("ascii") if end < len(items) else None
    return {**binding, "status": "INCOMPLETE" if scope["gaps"] else "EMPTY" if not items else "AVAILABLE",
            "items": items[offset:end], "cursor": token, "overflow": len(items) - end,
            "total": len(items), "excluded": scope["excluded"], "coverage": scope["coverage"]}
