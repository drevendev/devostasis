"""Named mutable source resolution; an old SHA is never a fallback."""

import re
from urllib.parse import quote

from .model import binding, identity, require, revision, text


def route(provider, locator):
    require(isinstance(locator, str), "SOURCE_PROJECT_INVALID")
    if provider == "github":
        require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", locator) and
                all(p not in (".", "..") for p in locator.split("/")), "SOURCE_PROJECT_INVALID")
        return "/repos/" + locator
    require(locator.isdigit(), "SOURCE_PROJECT_INVALID")
    return "/projects/" + locator


def obj(client, url):
    result, error = client.obj(url)
    require(result is not None, "SOURCE_UNAVAILABLE:" + (error or "UNKNOWN"))
    return result


def resolve(client, target, kind, ref=None, source_locator=None):
    require(client.provider == target["provider"] and client.endpoint == target["endpoint"], "SOURCE_ENDPOINT_MISMATCH")
    target_route = route(client.provider, target["locator"])
    target_meta = obj(client, target_route)
    require(str(target_meta["id"]) == target["project_id"], "SOURCE_TARGET_PROJECT_CHANGED")
    if kind == "DEFAULT_BRANCH":
        ref = target_meta["default_branch"]
        source_locator = target["locator"]
    text(ref, "source ref")
    if kind == "CHANGE":
        require(ref.isdigit(), "SOURCE_CHANGE_INVALID")
        change = obj(client, target_route + ("/pulls/" if client.provider == "github" else "/merge_requests/") + ref)
        if client.provider == "github":
            require(change["state"] == "open" and str(change["base"]["repo"]["id"]) == target["project_id"],
                    "SOURCE_CHANGE_CLOSED_OR_WRONG_PROJECT")
            head = change["head"]; sha = head["sha"]
            source_locator = head["repo"]["full_name"]
            source_id = str(head["repo"]["id"])
        else:
            require(change["state"] == "opened" and str(change["target_project_id"]) == target["project_id"],
                    "SOURCE_CHANGE_CLOSED_OR_WRONG_PROJECT")
            source_locator = str(change["source_project_id"])
            source_id, sha = source_locator, change["sha"]
    else:
        require(kind in ("BRANCH", "DEFAULT_BRANCH"), "SOURCE_KIND_UNSUPPORTED")
        source_locator = source_locator or target["locator"]
        source_meta = obj(client, route(client.provider, source_locator))
        source_id = str(source_meta["id"])
        branch = obj(client, route(client.provider, source_locator) +
                     ("/branches/" if client.provider == "github" else "/repository/branches/") + quote(ref, safe=""))
        sha = branch["commit"]["sha" if client.provider == "github" else "id"]
    revision(sha)
    source_meta = obj(client, route(client.provider, source_locator))
    require(str(source_meta["id"]) == source_id, "SOURCE_PROJECT_CHANGED")
    commit = obj(client, route(client.provider, source_locator) +
                 ("/commits/" if client.provider == "github" else "/repository/commits/") + sha)
    require(commit["sha" if client.provider == "github" else "id"] == sha, "SOURCE_COMMIT_NOT_IN_PROJECT")
    result = {"contract": "devostasis.work-source.v1", "kind": kind, "project": identity(target),
              "source_project": {**identity(target), "project_id": source_id}, "source_locator": source_locator,
              "ref": ref, "revision": sha}
    binding(result, {**target, "revision": sha})
    return result


def recheck(client, target):
    recorded = target.get("source_binding")
    require(recorded is not None, "SOURCE_BINDING_REQUIRED")
    current = resolve(client, target, recorded["kind"], recorded["ref"], recorded["source_locator"])
    require(current == recorded, "SOURCE_MOVED_REBUILD_SCOPE")
    return current
