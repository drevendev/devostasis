"""Verified, bounded source packets for external consumers. No execution authority."""

import base64
import binascii
import hashlib
from urllib.parse import quote

from ..canonical import canonical_bytes, digest, digest_bytes
from .binding import recheck as recheck_binding, route
from .collect import collect
from .model import fields, identity, instant, path, require, revision
from .planner import project

CONTRACT = "devostasis.work-handoff.v1"


def regular_blob(client, binding, filename):
    """Prove a regular blob in the pinned tree; never dereference a symlink."""
    root = route(client.provider, binding["source_locator"])
    parts = filename.split("/")
    if client.provider == "github":
        tree = binding["revision"]
        for index, name in enumerate(parts):
            raw, _ = client.get(root + "/git/trees/" + tree)
            require(isinstance(raw, dict) and raw.get("truncated") is False and isinstance(raw.get("tree"), list), "SOURCE_TREE_INCOMPLETE")
            matches = [e for e in raw["tree"] if e.get("path") == name]
            require(len(matches) == 1, "SOURCE_PATH_NOT_UNIQUE_OR_MISSING")
            entry = matches[0]; revision(entry["sha"])
            if index + 1 == len(parts):
                require(entry.get("type") == "blob" and entry.get("mode") in ("100644", "100755"), "SOURCE_LINK_REFUSED")
                return entry["sha"]
            require(entry.get("type") == "tree" and entry.get("mode") == "040000", "SOURCE_LINK_REFUSED")
            tree = entry["sha"]
    parent = "/".join(parts[:-1])
    found = []
    for page in range(1, client.max_pages + 1):
        rows, headers = client.get(root + "/repository/tree", {"ref": binding["revision"], "path": parent, "per_page": 100, "page": page})
        require(isinstance(rows, list) and len(rows) <= 100 and all(isinstance(e, dict) for e in rows), "SOURCE_TREE_INVALID")
        found += [e for e in rows if e.get("path") == filename]
        if not headers.get("x-next-page") and len(rows) < 100:
            break
    else:
        require(False, "SOURCE_TREE_PAGE_CAP")
    require(len(found) == 1, "SOURCE_PATH_NOT_UNIQUE_OR_MISSING")
    entry = found[0]
    require(entry.get("type") == "blob" and entry.get("mode") in ("100644", "100755"), "SOURCE_LINK_REFUSED")
    return revision(entry["id"])


def file_bytes(client, binding, filename, remaining):
    path(filename)
    blob_id = regular_blob(client, binding, filename)
    root = route(client.provider, binding["source_locator"])
    endpoint = root + ("/contents/" if client.provider == "github" else "/repository/files/") + quote(filename, safe="")
    raw, _ = client.get(endpoint, {"ref": binding["revision"]})
    require(isinstance(raw, dict) and raw.get("encoding") == "base64", "SOURCE_FILE_UNAVAILABLE_OR_UNSUPPORTED")
    require(raw.get("path" if client.provider == "github" else "file_path") == filename, "SOURCE_FILE_PATH_MISMATCH")
    require(type(raw.get("size")) is int and 0 <= raw["size"] <= remaining, "READ_BYTE_BUDGET_EXCEEDED")
    if client.provider == "github":
        require(raw.get("type") == "file" and not raw.get("submodule_git_url") and not raw.get("target"), "SOURCE_LINK_REFUSED")
    else:
        require(raw.get("commit_id") == binding["revision"], "SOURCE_FILE_REVISION_MISMATCH")
    try:
        encoded = raw["content"]
        require(isinstance(encoded, str) and len(encoded) <= (remaining + 2) // 3 * 4 + 8192,
                "READ_BYTE_BUDGET_EXCEEDED")
        data = base64.b64decode("".join(encoded.split()).encode("ascii"), validate=True)
    except (ValueError, UnicodeError, binascii.Error, KeyError) as exc:
        raise ValueError("SOURCE_FILE_ENCODING_INVALID") from exc
    require(len(data) == raw["size"] and len(data) <= remaining, "SOURCE_FILE_SIZE_MISMATCH")
    hasher = hashlib.sha1 if len(blob_id) == 40 else hashlib.sha256
    require(hasher(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest() == blob_id,
            "SOURCE_BLOB_DIGEST_MISMATCH")
    return data


def prepare(decoded, item_id, client, at, actor, policy_version, expected_project):
    scope, config = decoded["scope.json"], decoded["policy.json"]
    require(identity(scope["subject"]) == expected_project and client.endpoint == expected_project["endpoint"] and
            client.provider == expected_project["provider"], "consumer expected project mismatch")
    require(actor == config["actor"] and policy_version == config["version"], "consumer actor or policy version mismatch")
    require(instant(scope["planned_at"]) <= instant(at) <= instant(scope["expires_at"]), "scope expired or clock predates scope")
    selected = next((i for i in scope["items"] if i["id"] == item_id), None)
    require(selected is not None and selected["eligibility"] == "READY", "selected item is not ready")
    bound = selected.get("source_binding")
    require(bound is not None, "SOURCE_BINDING_REQUIRED_REBUILD_SCOPE")
    target = {**scope["subject"], "revision": bound["revision"], "source_binding": bound,
              "context": "CANONICAL" if bound["kind"] == "DEFAULT_BRANCH" else "CANDIDATE"}
    recheck_binding(client, target)
    original = scope["subject"].get("source_binding")
    require(original is not None, "SOURCE_BINDING_REQUIRED_REBUILD_SCOPE")
    current = collect(client, scope["subject"]["locator"], config, at,
        context=scope["subject"]["context"], selected=selected,
        revision=scope["subject"]["revision"],
        source_ref=original["ref"] if original["kind"] == "BRANCH" else None,
        source_change=original["ref"] if original["kind"] == "CHANGE" else None,
        source_project=original["source_locator"] if original["kind"] == "BRANCH" else None)
    require(identity(current["subject"]) == expected_project, "consumer project changed")
    refreshed = project(current, config, decoded["evidence.json"], at)
    item = next((i for i in refreshed["items"] if i["id"] == item_id), None)
    require(item is not None and item["eligibility"] == "READY" and all(item[k] == selected[k] for k in
            ("revision", "implementation_owner", "action", "acceptance", "read_set", "source_binding")),
            "ITEM_CHANGED_REBUILD_SCOPE")
    read_set = item["read_set"]
    require(len(read_set["paths"]) == read_set["total_paths"] <= read_set["budget"]["max_files"], "READ_FILE_BUDGET_EXCEEDED")
    files, total = [], 0
    for filename in read_set["paths"]:
        data = file_bytes(client, bound, filename, read_set["budget"]["max_bytes"] - total)
        total += len(data)
        files.append({"path": filename, "size": len(data), "digest": digest_bytes(data),
                      "base64": base64.b64encode(data).decode("ascii")})
    recheck_binding(client, target)
    packet = {"contract": CONTRACT, "kind": "handoff", "scope_bundle_id": decoded["manifest.json"]["bundle_id"],
              "scope_digest": digest(scope), "item": selected, "checked_at": at,
              "source_binding": bound, "refreshed_inventory_digest": digest(current),
              "files": files, "total_bytes": total, "authority": scope["authority"]}
    return packet | {"packet_id": digest(packet)}


def verify_packet(packet, decoded, at, actor, policy_version, expected_project):
    fields(packet, ("contract", "kind", "scope_bundle_id", "scope_digest", "item", "checked_at", "source_binding",
                    "refreshed_inventory_digest", "files", "total_bytes", "authority", "packet_id"))
    require(packet["contract"] == CONTRACT and packet["kind"] == "handoff", "unsupported handoff contract")
    require(packet["packet_id"] == digest({k: v for k, v in packet.items() if k != "packet_id"}), "handoff identity mismatch")
    scope, config = decoded["scope.json"], decoded["policy.json"]
    require(packet["scope_bundle_id"] == decoded["manifest.json"]["bundle_id"] and packet["scope_digest"] == digest(scope),
            "handoff scope mismatch")
    require(actor == config["actor"] and policy_version == config["version"] and identity(scope["subject"]) == expected_project,
            "consumer binding mismatch")
    require(instant(scope["planned_at"]) <= instant(packet["checked_at"]) <= instant(at) <= instant(scope["expires_at"]),
            "handoff expired or clock mismatch")
    require(packet["item"] in scope["items"] and packet["item"]["eligibility"] == "READY" and
            packet["source_binding"] == packet["item"].get("source_binding") and packet["authority"] == scope["authority"],
            "handoff item mismatch")
    item = packet["item"]; read_set = item["read_set"]
    require(isinstance(packet["files"], list) and [f["path"] for f in packet["files"]] == read_set["paths"] and
            len(packet["files"]) == read_set["total_paths"] <= read_set["budget"]["max_files"], "handoff read set mismatch")
    total = 0
    for file in packet["files"]:
        fields(file, ("path", "size", "digest", "base64")); path(file["path"])
        require(isinstance(file["base64"], str) and len(file["base64"]) <= (read_set["budget"]["max_bytes"] + 2) // 3 * 4,
                "handoff byte budget exceeded")
        data = base64.b64decode(file["base64"], validate=True)
        require(type(file["size"]) is int and len(data) == file["size"] and digest_bytes(data) == file["digest"], "handoff file digest mismatch")
        total += len(data)
    require(type(packet["total_bytes"]) is int and total == packet["total_bytes"] <= read_set["budget"]["max_bytes"],
            "handoff byte budget exceeded")
    canonical_bytes(packet)
    return packet
