"""Pure deterministic work projection from admitted inputs and explicit policy."""

from __future__ import annotations

from datetime import timedelta

from ..canonical import digest
from . import CONTRACT
from .evidence import normalize
from .model import QUEUES, ROLES, identity, instant, inventory, policy, require, timestamp


def latest_reviews(change):
    actors = {}
    for r in sorted(change["reviews"]["items"], key=lambda r: (instant(r["at"]), r["id"])):
        if r["state"] != "COMMENTED":
            actors[r["actor"]] = r
    return actors


def merge_reasons(change, config):
    blocked, missing = [], []
    for field, reason in (("draft", "DRAFT"), ("conflict", "CONFLICT")):
        if change[field] is True:
            blocked.append(reason)
        elif change[field] is None:
            missing.append(field.upper() + "_UNKNOWN")
    if change["merge_train"] is True and not config["allow_merge_train"]:
        blocked.append("MERGE_TRAIN_NOT_AUTHORIZED")
    elif change["merge_train"] is None:
        missing.append("MERGE_TRAIN_UNKNOWN")
    for name in ("reviews", "checks", "threads", "files"):
        if change[name]["status"] != "COMPLETE":
            missing.append(name.upper() + "_INCOMPLETE")
    reviews = latest_reviews(change)
    current = [r for r in reviews.values() if r["revision"] == change["head"] and r["actor"] != change["author"]]
    approvals = sum(r["state"] == "APPROVED" for r in current)
    if any(r["state"] == "CHANGES_REQUESTED" for r in reviews.values()):
        blocked.append("CHANGES_REQUESTED")
    if approvals < config["minimum_approvals"]:
        blocked.append("EXACT_HEAD_APPROVAL_REQUIRED")
    checks = {}
    for c in sorted(change["checks"]["items"], key=lambda c: (instant(c["at"]), c["id"])):
        if c["revision"] == change["head"]:
            checks[c["name"]] = c
    for name in config["required_checks"]:
        if name not in checks:
            missing.append("CHECK_MISSING:" + name)
        elif checks[name]["state"] == "UNKNOWN":
            missing.append("CHECK_UNKNOWN:" + name)
        elif checks[name]["state"] != "PASS":
            blocked.append("CHECK_" + checks[name]["state"] + ":" + name)
    if any(not t["resolved"] for t in change["threads"]["items"]):
        blocked.append("UNRESOLVED_DISCUSSION")
    return blocked, missing


def project(inv, config, evidence, at=None):
    inventory(inv); policy(config)
    at = timestamp(at or inv["observed_at"])
    require(instant(at) >= instant(inv["observed_at"]), "scope predates its inventory")
    expired = (instant(at) - instant(inv["observed_at"])).total_seconds() > config["ttl_seconds"]
    inputs = {"inventory": digest(inv), "policy": digest(config), "evidence": digest(evidence)}
    normalized = normalize(evidence, inv["subject"], at, config["ttl_seconds"])
    items, excluded, gaps = [], [], []
    actor = config["actor"]
    allowed = {q for role in config["roles"] for q in ROLES[role]}
    issues = {i["id"]: i for i in inv["issues"]["items"]}
    changes = {c["id"]: c for c in inv["changes"]["items"]}

    def dependencies(refs):
        blocked, missing = [], []
        for ref in refs:
            if ref not in issues:
                missing.append("DEPENDENCY_UNKNOWN:" + ref)
            elif issues[ref]["state"] != "CLOSED":
                blocked.append("DEPENDENCY_OPEN:" + ref)
        return blocked, missing

    def add(queue, source, criterion, revision, title, owner, paths, symbols, acceptance,
            deps=(), blocked=(), missing=(), action=None, continuation=False, refs=(), merge_gate=None):
        seed = {"project": identity(inv["subject"]), "queue": queue, "source": source, "criterion": criterion}
        item_id = digest(seed)
        if queue not in allowed:
            excluded.append({"id": item_id, "source": source, "reason": "ROLE_NOT_ELIGIBLE"}); return
        b, m = dependencies(deps)
        b += list(blocked); m += list(missing)
        if owner and owner != actor:
            b.append("FOREIGN_IMPLEMENTATION_OWNER")
        if expired and action != "recover_evidence":
            m.append("INVENTORY_EXPIRED")
        priority = config["priorities"].get(source, {"rank": 1000, "rationale": "No consumer business priority declared."})
        read_paths = sorted(set(paths))[:config["read_budget"]["max_files"]]
        if len(set(paths)) > len(read_paths):
            m.append("READ_SET_OVERFLOW")
        item = {"id": item_id, "queue": queue, "source": source, "criterion": criterion,
                "subject": inv["subject"], "revision": revision, "title": title,
                "action": action or queue, "implementation_owner": owner, "executor": actor,
                "priority": priority, "continuation": continuation,
                "eligibility": "UNKNOWN" if m else "BLOCKED" if b else "READY",
                "reasons": sorted(set(b + m)), "dependencies": list(deps),
                "read_set": {"paths": read_paths, "symbols": sorted(set(symbols)), "budget": config["read_budget"],
                             "total_paths": len(set(paths))},
                "acceptance": list(acceptance), "evidence": sorted(set(refs) | set(inputs.values()))}
        item["merge_gate"] = merge_gate
        item["fingerprint"] = digest(item)
        items.append(item)

    for name in ("changes", "issues"):
        if inv[name]["status"] != "COMPLETE":
            gaps.append({"source": name, "reason": name.upper() + "_" + inv[name]["status"]})
    needed_issues = {c["issue"] for c in config["criteria"]} | {d for c in config["criteria"] for d in c["dependencies"]} | {d for r in config["requests"] for d in r["dependencies"]}
    for ref in sorted(needed_issues - issues.keys()):
        gaps.append({"source": "issue:" + ref, "reason": "ISSUE_OR_DEPENDENCY_UNKNOWN"})
    for c in inv["changes"]["items"]:
        if c["state"] != "OPEN":
            excluded.append({"source": "change:" + c["id"], "reason": c["state"]}); continue
        src = "change:" + c["id"]
        owner = c["owners"][0] if len(c["owners"]) == 1 else c["author"]
        blocked, missing = merge_reasons(c, config)
        review = latest_reviews(c).get(actor)
        if actor == c["author"]:
            excluded.append({"source": src, "reason": "AUTHOR_CANNOT_INDEPENDENTLY_REVIEW"})
        elif review and review["revision"] == c["head"] and review["state"] in ("APPROVED", "CHANGES_REQUESTED"):
            excluded.append({"source": src, "reason": "EXACT_HEAD_REVIEW_ALREADY_RECORDED"})
        elif c["reviews"]["status"] == "COMPLETE" and actor not in c["reviewers"] and sum(
                r["revision"] == c["head"] and r["actor"] != c["author"] and r["state"] == "APPROVED"
                for r in latest_reviews(c).values()) >= config["minimum_approvals"]:
            excluded.append({"source": src, "reason": "INDEPENDENT_REVIEW_REQUIREMENT_SATISFIED"})
        else:
            review_missing = [name.upper() + "_INCOMPLETE" for name in ("files", "reviews") if c[name]["status"] != "COMPLETE"]
            add("review", src, None, {"head": c["head"], "base": c["base"]}, c["title"], None,
                c["files"]["items"], [], ["Record an independent verdict on this exact head and scope."],
                blocked=["DRAFT"] if c["draft"] else [], missing=review_missing + (["DRAFT_UNKNOWN"] if c["draft"] is None else []))
        if len(c["owners"]) > 1:
            missing.append("IMPLEMENTATION_OWNER_AMBIGUOUS")
        add("finish_merge", src, None, {"head": c["head"], "base": c["base"]}, c["title"], owner,
            c["files"]["items"], [], ["Resolve the listed blockers and recheck this exact head before any authorized merge."],
            blocked=[r for r in blocked if r == "MERGE_TRAIN_NOT_AUTHORIZED"], missing=missing,
            action="merge_train_admission" if c["merge_train"] and not blocked and not missing else "merge" if not blocked and not missing else "rework",
            continuation=owner == actor,
            merge_gate={"status": "UNKNOWN" if missing else "BLOCKED" if blocked else "READY", "reasons": sorted(set(blocked + missing))})
        for name in ("reviews", "checks", "threads", "files"):
            if c[name]["status"] != "COMPLETE":
                gaps.append({"source": src + "/" + name, "reason": name.upper() + "_INCOMPLETE"})
        if any(c[name] is None for name in ("draft", "conflict", "merge_train")):
            gaps.append({"source": src + "/merge_state", "reason": "MERGE_STATE_CAPABILITY_UNKNOWN"})
    for criterion in config["criteria"]:
        src = "issue:" + criterion["issue"]
        issue = issues.get(criterion["issue"])
        if criterion["done"] or issue and issue["state"] == "CLOSED":
            excluded.append({"source": src, "criterion": criterion["id"], "reason": "CRITERION_DONE"}); continue
        active = [changes[r] for r in criterion["implementations"] if r in changes and changes[r]["state"] in ("OPEN", "MERGED")]
        if active:
            excluded.append({"source": src, "criterion": criterion["id"], "reason": "EQUIVALENT_IMPLEMENTATION_EXISTS"}); continue
        missing = []
        if issue is None:
            missing.append("ISSUE_UNKNOWN")
        if any(r not in changes for r in criterion["implementations"]):
            missing.append("IMPLEMENTATION_UNKNOWN")
            for ref in criterion["implementations"]:
                if ref not in changes:
                    gaps.append({"source": "change:" + ref, "reason": "IMPLEMENTATION_UNKNOWN"})
        if not criterion["paths"]:
            missing.append("IMPLEMENTATION_READ_SET_UNDECLARED")
            gaps.append({"source": src + "/" + criterion["id"], "reason": "IMPLEMENTATION_READ_SET_UNDECLARED"})
        if inv["changes"]["status"] != "COMPLETE":
            missing.append("ACTIVE_IMPLEMENTATION_INVENTORY_INCOMPLETE")
        owners = issue["owners"] if issue else []
        if len(owners) > 1:
            missing.append("IMPLEMENTATION_OWNER_AMBIGUOUS")
        add("implement_issue", src, criterion["id"], {"content": inv["subject"]["revision"],
            "issue": digest(issue) if issue else None}, issue["title"] if issue else criterion["id"],
            owners[0] if len(owners) == 1 else None, criterion["paths"], criterion["symbols"],
            criterion["acceptance"], criterion["dependencies"], missing=missing,
            continuation=owners == [actor])
    for request in config["requests"]:
        add(request["queue"], "request:" + request["id"], request["id"], {"content": inv["subject"]["revision"]},
            request["question"], request["owner"], request["paths"], request["symbols"], request["acceptance"], request["dependencies"])
    for finding in normalized["findings"]:
        disposition = next((d for d in config["dispositions"] if d["finding"] == finding["id"] and
                            d["revision"] == finding["revision"] and instant(d["until"]) >= instant(at)), None)
        if disposition and (disposition["state"] == "ACKNOWLEDGED" or disposition["reference"] in changes and
                            changes[disposition["reference"]]["state"] == "OPEN"):
            excluded.append({"source": finding["id"], "reason": "CURRENT_DISPOSITION", "reference": disposition["reference"]}); continue
        add("analyze_code", finding["id"], finding["rule"], {"content": finding["revision"]}, finding["trigger"],
            None, [finding["path"]], [finding["symbol"]] if finding["symbol"] else [], [finding["verification"]],
            refs=[finding["evidence"]], missing=["REPORT_PARTIAL"] if finding["completeness"] != "COMPLETE" else [])
    gaps += normalized["gaps"]
    if expired:
        gaps.append({"source": "inventory", "reason": "INVENTORY_EXPIRED"})
    recovery = {}
    for gap in gaps:
        recovery.setdefault(gap["source"], set()).add(gap["reason"])
    for source in sorted(recovery):
        add("research", "recovery:" + source, None, {"content": inv["subject"]["revision"]},
            "Recover bounded evidence: " + ", ".join(sorted(recovery[source])), None, [], [],
            ["Refresh only this missing source under the declared collection budget; rebuild and verify scope."],
            action="recover_evidence")
    require(len({item["id"] for item in items}) == len(items), "duplicate scope item identity")
    rank = {"READY": 0, "BLOCKED": 1, "UNKNOWN": 2}
    items.sort(key=lambda i: (rank[i["eligibility"]], i["priority"]["rank"], not i["continuation"],
                              config["queue_order"].index(i["queue"]), i["id"]))
    return {"contract": CONTRACT, "kind": "scope", "subject": inv["subject"], "observed_at": inv["observed_at"],
            "planned_at": at, "expires_at": timestamp((instant(inv["observed_at"]) + timedelta(seconds=config["ttl_seconds"])).isoformat()),
            "policy_version": config["version"], "inputs": inputs, "items": items,
            "queues": {q: [i["id"] for i in items if i["queue"] == q] for q in QUEUES},
            "coverage": {k: inv[k]["status"] for k in ("changes", "issues")}, "selection": inv["selection"],
            "excluded": sorted(excluded, key=digest), "gaps": gaps,
            "authority": "Read-only proposal. Recheck source state and consumer authorization before execution."}
