"""Admission rules shared by collection, offline replay and consumer handoff."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from ..canonical import canonical_bytes, digest
from . import CONTRACT, CONTRACTS

QUEUES = ("review", "finish_merge", "implement_issue", "research", "analyze_code")
STATUSES = ("COMPLETE", "PARTIAL", "UNAVAILABLE")
ROLES = {"reviewer": ("review",), "developer": ("finish_merge", "implement_issue"),
         "researcher": ("research",), "analyst": ("analyze_code",), "all": QUEUES}


class ScopeError(ValueError):
    """An input or persisted consumer contract is inadmissible."""


def require(condition, message):
    if not condition:
        raise ScopeError(message)


def fields(value, required, optional=(), label="object"):
    require(isinstance(value, dict), f"{label}: expected object")
    require(set(required) <= value.keys() <= set(required) | set(optional),
            f"{label}: missing or unknown fields")


def text(value, label="text"):
    require(isinstance(value, str) and 0 < len(value) <= 8192 and
            not any(ord(c) < 32 for c in value), f"{label}: invalid text")
    return value


def number(value, low=0, high=100000, label="integer"):
    require(type(value) is int and low <= value <= high, f"{label}: invalid integer")
    return value


def instant(value):
    require(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value),
        "timestamp: timezone-qualified RFC3339 instant required")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise ScopeError("timestamp: invalid instant") from exc


def timestamp(value):
    return instant(value).isoformat().replace("+00:00", "Z")


def path(value):
    text(value, "repository path")
    decoded = unquote(value)
    parts = decoded.split("/")
    require(not decoded.startswith("/") and "\\" not in decoded and ":" not in decoded
            and all(p not in ("", ".", "..") for p in parts)
            and str(PurePosixPath(decoded)) == decoded, "path: must be repository relative")
    require(decoded == value, "path: encoded paths are not admitted")
    return value


def strings(value, label, paths=False):
    require(isinstance(value, list) and len(value) <= 10000, f"{label}: expected bounded list")
    for item in value:
        (path if paths else text)(item)
    require(len(set(value)) == len(value), f"{label}: duplicates")


def revision(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value),
            "revision: full immutable commit id required")
    return value


def subject(value):
    fields(value, ("provider", "endpoint", "project_id", "locator", "revision", "context"), ("source_binding",))
    require(value["provider"] in ("github", "gitlab"), "provider: unsupported")
    parsed = urlsplit(value["endpoint"])
    require(parsed.scheme == "https" and parsed.hostname and not parsed.username and
            not parsed.password and not parsed.query and not parsed.fragment and
            not value["endpoint"].endswith("/"), "endpoint: HTTPS API base required")
    text(value["project_id"]); require(value["project_id"].isdigit(), "numeric immutable project id required")
    text(value["locator"]); revision(value["revision"])
    require(value["context"] in ("CANONICAL", "CANDIDATE"), "context: unsupported")
    if "source_binding" in value:
        binding(value["source_binding"], value)
    return value


def binding(value, target):
    fields(value, ("contract", "kind", "project", "source_project", "source_locator", "ref", "revision"))
    require(value["contract"] == "devostasis.work-source.v1" and value["kind"] in
            ("DEFAULT_BRANCH", "BRANCH", "CHANGE"), "source binding: unsupported lineage")
    require(value["project"] == identity(target), "source binding: target project mismatch")
    fields(value["source_project"], ("provider", "endpoint", "project_id"))
    require(value["source_project"]["provider"] == target["provider"] and
            value["source_project"]["endpoint"] == target["endpoint"] and
            isinstance(value["source_project"]["project_id"], str) and
            value["source_project"]["project_id"].isdigit(), "source binding: wrong source project")
    text(value["source_locator"]); text(value["ref"]); revision(value["revision"])
    require(value["revision"] == target["revision"], "source binding: revision mismatch")
    require((value["kind"] == "DEFAULT_BRANCH") == (target["context"] == "CANONICAL"),
            "source binding: context mismatch")
    if value["kind"] == "CHANGE":
        require(value["ref"].isdigit(), "source binding: numeric change ref required")


def identity(value):
    return {k: value[k] for k in ("provider", "endpoint", "project_id")}


def collection(value, validator):
    fields(value, ("status", "items", "reasons"))
    require(value["status"] in STATUSES, "collection: invalid status")
    strings(value["reasons"], "collection reasons")
    require(isinstance(value["items"], list) and len(value["items"]) <= 10000,
            "collection: invalid items")
    require(value["status"] != "COMPLETE" or not value["reasons"], "complete collection has gaps")
    require(value["status"] == "COMPLETE" or value["reasons"], "incomplete collection requires reasons")
    require(value["status"] != "UNAVAILABLE" or not value["items"], "unavailable collection has items")
    seen = set()
    for item in value["items"]:
        validator(item)
        key = item.get("id", digest(item)) if isinstance(item, dict) else item
        require(key not in seen, "collection: duplicate identity")
        seen.add(key)


def issue(value):
    fields(value, ("id", "title", "state", "owners", "updated_at"))
    text(value["id"]); text(value["title"]); strings(value["owners"], "owners")
    require(value["state"] in ("OPEN", "CLOSED"), "issue: invalid state")
    instant(value["updated_at"])


def review(value):
    fields(value, ("id", "actor", "revision", "state", "at"))
    text(value["id"]); text(value["actor"]); revision(value["revision"]); instant(value["at"])
    require(value["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED", "COMMENTED"),
            "review: invalid state")


def check(value):
    fields(value, ("id", "name", "revision", "state", "at"))
    text(value["id"]); text(value["name"]); revision(value["revision"]); instant(value["at"])
    require(value["state"] in ("PASS", "FAIL", "PENDING", "MANUAL", "UNKNOWN"), "check: invalid state")


def thread(value):
    fields(value, ("id", "resolved"))
    text(value["id"]); require(type(value["resolved"]) is bool, "thread: resolved must be boolean")


def change(value):
    fields(value, ("id", "title", "state", "author", "owners", "reviewers", "head", "base", "updated_at",
                   "draft", "conflict", "merge_train", "reviews", "checks", "threads", "files"), ("source_binding",))
    text(value["id"]); text(value["title"]); text(value["author"])
    strings(value["owners"], "owners"); revision(value["head"]); revision(value["base"])
    strings(value["reviewers"], "requested reviewers")
    instant(value["updated_at"])
    require(value["state"] in ("OPEN", "CLOSED", "MERGED"), "change: invalid state")
    for key in ("draft", "conflict", "merge_train"):
        require(type(value[key]) is bool or value[key] is None, f"change {key}: boolean or unknown required")
    for key, validator in (("reviews", review), ("checks", check), ("threads", thread), ("files", path)):
        collection(value[key], validator)


def inventory(value):
    fields(value, ("contract", "kind", "subject", "observed_at", "changes", "issues", "receipts", "selection"))
    require(value["contract"] in CONTRACTS and value["kind"] == "inventory", "inventory: unsupported contract")
    require(value["contract"] != "devostasis.work.v1" or "source_binding" not in value["subject"], "legacy inventory cannot carry source binding")
    subject(value["subject"]); observed = instant(value["observed_at"])
    collection(value["changes"], change); collection(value["issues"], issue)
    fields(value["selection"], ("changes", "issues"))
    require(value["selection"]["changes"] in ("OPEN_AND_REGISTERED", "SELECTED"), "invalid change inventory scope")
    strings(value["selection"]["issues"], "issue selection")
    require(isinstance(value["receipts"], list) and len(value["receipts"]) <= 10000, "invalid receipts")
    for obj in value["changes"]["items"] + value["issues"]["items"]:
        require(instant(obj["updated_at"]) <= observed, "object changed after observation")
        if "reviews" in obj:
            if "source_binding" in obj:
                require(value["contract"] != "devostasis.work.v1", "legacy change cannot carry source binding")
                binding(obj["source_binding"], {**value["subject"], "context": "CANDIDATE", "revision": obj["head"]})
            for entry in obj["reviews"]["items"] + obj["checks"]["items"]:
                require(instant(entry["at"]) <= observed, "evidence arrived after observation")
    canonical_bytes(value)
    return value


def policy(value):
    fields(value, ("contract", "kind", "version", "actor", "roles", "ttl_seconds", "queue_order",
                   "required_checks", "minimum_approvals", "allow_merge_train", "read_budget",
                   "priorities", "criteria", "requests", "dispositions"))
    require(value["contract"] in CONTRACTS and value["kind"] == "policy", "policy: unsupported contract")
    text(value["version"]); text(value["actor"])
    strings(value["roles"], "roles"); require(set(value["roles"]) <= ROLES.keys(), "unknown role")
    number(value["ttl_seconds"], 1, 86400); number(value["minimum_approvals"], 1, 100)
    require(type(value["allow_merge_train"]) is bool, "merge train policy: boolean required")
    require(isinstance(value["queue_order"], list) and len(value["queue_order"]) == 5 and
            set(value["queue_order"]) == set(QUEUES), "queue order: five queues exactly once")
    strings(value["required_checks"], "required checks")
    fields(value["read_budget"], ("max_files", "max_bytes"))
    number(value["read_budget"]["max_files"], 1, 1000); number(value["read_budget"]["max_bytes"], 1, 10000000)
    require(isinstance(value["priorities"], dict), "priorities: object required")
    for key, entry in value["priorities"].items():
        text(key); fields(entry, ("rank", "rationale")); number(entry["rank"], 0, 1000); text(entry["rationale"])
    for category in ("criteria", "requests", "dispositions"):
        require(isinstance(value[category], list) and len(value[category]) <= 10000, f"invalid {category}")
    ids = set()
    for item in value["criteria"]:
        fields(item, ("id", "issue", "acceptance", "paths", "symbols", "dependencies", "implementations", "done"))
        text(item["id"]); text(item["issue"]); require(item["issue"].isdigit(), "issue id must be numeric")
        strings(item["acceptance"], "acceptance")
        require(item["acceptance"], "criterion requires explicit acceptance")
        strings(item["paths"], "paths", True); strings(item["symbols"], "symbols")
        strings(item["dependencies"], "dependencies"); strings(item["implementations"], "implementations")
        require(all(r.isdigit() for r in item["dependencies"] + item["implementations"]), "source ids must be numeric")
        require(type(item["done"]) is bool, "criterion done: boolean required")
        require(item["id"] not in ids, "duplicate criterion id"); ids.add(item["id"])
    ids = set()
    for item in value["requests"]:
        fields(item, ("id", "queue", "question", "paths", "symbols", "acceptance", "dependencies", "owner"))
        text(item["id"]); text(item["question"])
        require(item["queue"] in ("research", "analyze_code"), "invalid request queue")
        strings(item["paths"], "paths", True); strings(item["symbols"], "symbols")
        strings(item["acceptance"], "acceptance"); strings(item["dependencies"], "dependencies")
        require(all(r.isdigit() for r in item["dependencies"]), "dependency ids must be numeric")
        require(item["acceptance"], "request requires expected output")
        require(item["queue"] != "analyze_code" or item["paths"], "analysis requires named paths")
        require(item["owner"] is None or isinstance(item["owner"], str), "invalid request owner")
        if item["owner"] is not None:
            text(item["owner"], "request owner")
        require(item["id"] not in ids, "duplicate request id"); ids.add(item["id"])
    ids = set()
    for item in value["dispositions"]:
        fields(item, ("finding", "revision", "until", "state", "reference"))
        text(item["finding"]); revision(item["revision"]); instant(item["until"]); text(item["reference"])
        require(item["state"] in ("ACKNOWLEDGED", "IMPLEMENTING"), "invalid disposition")
        require(item["finding"] not in ids, "duplicate disposition"); ids.add(item["finding"])
    canonical_bytes(value)
    return value


def default_policy(actor):
    return {"contract": CONTRACT, "kind": "policy", "version": "example-1", "actor": actor,
            "roles": ["all"], "ttl_seconds": 3600, "queue_order": list(QUEUES),
            "required_checks": [], "minimum_approvals": 1, "allow_merge_train": False,
            "read_budget": {"max_files": 20, "max_bytes": 200000}, "priorities": {},
            "criteria": [], "requests": [], "dispositions": []}
