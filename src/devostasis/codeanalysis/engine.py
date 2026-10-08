"""Pure Python AST and import evidence, evaluated without importing repository code."""

import ast
import base64
from collections import Counter, defaultdict
from copy import deepcopy
import io
import tokenize

from ..canonical import digest
from ..workscope.model import fields, number, path, require, strings
from . import ENGINE, POLICY

RULES = {"DS-PY-SYNTAX": "Python syntax cannot be parsed", "DS-PY-COMPLEXITY": "Function decision count exceeds policy",
         "DS-PY-FUNCTION-SIZE": "Function line span exceeds policy", "DS-PY-FILE-SIZE": "File line count exceeds policy",
         "DS-PY-BARE-EXCEPT": "Bare except also catches process control exceptions", "DS-PY-IMPORT-CYCLE": "Static import cycle"}


def default_policy():
    return {"contract": POLICY, "version": "default-1", "grammar": "PYTHON_3_12", "include": [],
        "exclude": [".venv", "build", "dist", "vendor", "node_modules"], "source_roots": [".", "src"],
        "budget": {"max_files": 2000, "max_file_bytes": 1024 * 1024, "max_total_bytes": 16 * 1024 * 1024, "seconds": 120},
        "limits": {"complexity": 15, "function_lines": 80, "file_lines": 600},
        "history": {"enabled": True, "days": 28, "max_commits": 500}}


def policy(value):
    fields(value, ("contract", "version", "grammar", "include", "exclude", "source_roots", "budget", "limits", "history"))
    require(value["contract"] == POLICY and value["grammar"] == "PYTHON_3_12", "unsupported code policy")
    from ..workscope.model import text
    text(value["version"])
    strings(value["include"], "included roots", paths=True); strings(value["exclude"], "excluded roots", paths=True)
    strings(value["source_roots"], "source roots")
    require(value["source_roots"] and len(value["source_roots"]) <= 100, "source roots required")
    for root in value["source_roots"]:
        if root != ".": path(root)
    fields(value["budget"], ("max_files", "max_file_bytes", "max_total_bytes", "seconds"))
    for key, high in (("max_files", 5000), ("max_file_bytes", 4 * 1024 * 1024), ("max_total_bytes", 64 * 1024 * 1024), ("seconds", 3600)):
        number(value["budget"][key], 1, high)
    require(value["budget"]["max_file_bytes"] <= value["budget"]["max_total_bytes"], "per-file budget exceeds total")
    fields(value["limits"], ("complexity", "function_lines", "file_lines"))
    for v in value["limits"].values(): number(v, 1, 100000)
    fields(value["history"], ("enabled", "days", "max_commits"))
    require(type(value["history"]["enabled"]) is bool, "explicit history enablement required")
    number(value["history"]["days"], 1, 3650); number(value["history"]["max_commits"], 1, 10000)
    return value


def local_nodes(node):
    stack = list(node.body)
    while stack:
        child = stack.pop()
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield child
        stack.extend(ast.iter_child_nodes(child))


def decisions(node):
    result = 1
    for child in local_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler)): result += 1
        elif isinstance(child, ast.BoolOp): result += len(child.values) - 1
        elif isinstance(child, ast.comprehension): result += 1 + len(child.ifs)
        elif isinstance(child, ast.Match): result += max(0, len(child.cases) - 1)
    return result


def module_name(filename, roots):
    eligible = [r for r in roots if r == "." or filename.startswith(r + "/")]
    if not eligible: return None
    root = max(eligible, key=lambda r: 0 if r == "." else len(r))
    name = filename if root == "." else filename[len(root) + 1:]
    parts = name[:-3].split("/")
    if parts[-1] == "__init__": parts.pop()
    return ".".join(parts) if parts and all(p.isidentifier() for p in parts) else None


def cycles(nodes, edges):
    # Iterative reachability avoids recursion limits on repositories with long chains.
    graph, reverse = defaultdict(set), defaultdict(set)
    for edge in edges:
        if edge["status"] == "RESOLVED":
            graph[edge["from"]].add(edge["to"]); reverse[edge["to"]].add(edge["from"])
    visited, order = set(), []
    for start in sorted(nodes):
        if start in visited: continue
        stack = [(start, False)]
        while stack:
            node, done = stack.pop()
            if done: order.append(node); continue
            if node in visited: continue
            visited.add(node); stack.append((node, True))
            stack.extend((n, False) for n in sorted(graph[node], reverse=True) if n not in visited)
    assigned, components = set(), []
    for start in reversed(order):
        if start in assigned: continue
        component, stack = [], [start]
        while stack:
            node = stack.pop()
            if node in assigned: continue
            assigned.add(node); component.append(node); stack.extend(reverse[node] - assigned)
        component.sort()
        if len(component) > 1 or start in graph[start]: components.append(component)
    return sorted(components)


def evaluate(raw, config):
    policy(config)
    output, findings, imports = [], [], []
    entries = {e["path"]: e for e in raw["entries"] if e["path"] is not None}
    module_paths = defaultdict(list)
    for filename in entries:
        if filename.endswith(".py"):
            name = module_name(filename, config["source_roots"])
            if name: module_paths[name].append(filename)

    def finding(rule, filename, symbol, line, end, evidence, related=()):
        findings.append({"id": digest({"rule": rule, "path": filename, "symbol": symbol}), "rule": rule,
            "level": "error" if rule == "DS-PY-SYNTAX" else "warning", "path": filename, "symbol": symbol,
            "line": line, "end_line": end, "message": RULES[rule], "evidence": evidence, "related_paths": sorted(related)})

    for entry in raw["entries"]:
        row = {"path": entry["path"], "object_id": entry["object_id"], "status": entry["status"], "reason": entry["reason"],
               "module": module_name(entry["path"], config["source_roots"]) if entry["path"] and entry["path"].endswith(".py") else None,
               "lines": None, "functions": []}
        output.append(row)
        if entry["status"] != "ADMITTED": continue
        filename = entry["path"]; data = base64.b64decode(raw["sources"][filename], validate=True)
        try:
            encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
            source = data.decode(encoding)
        except (SyntaxError, UnicodeError, LookupError):
            row.update(status="UNAVAILABLE", reason="SOURCE_ENCODING_UNAVAILABLE"); continue
        row["lines"] = len(source.splitlines())
        try: tree = ast.parse(source, filename=filename, feature_version=(3, 12))
        except (SyntaxError, ValueError, RecursionError):
            row.update(status="PARSE_ERROR", reason="PYTHON_3_12_SYNTAX")
            finding("DS-PY-SYNTAX", filename, "<module>", 1, max(1, row["lines"]), {"grammar": config["grammar"]})
            continue
        row.update(status="ANALYZED", reason=None)
        if row["lines"] > config["limits"]["file_lines"]:
            finding("DS-PY-FILE-SIZE", filename, "<module>", 1, row["lines"], {"lines": row["lines"], "limit": config["limits"]["file_lines"]})
        counts = Counter()
        pending = [(tree, "")]
        while pending:
            node, prefix = pending.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                base = prefix + node.name; counts[base] += 1
                name = base + ("#" + str(counts[base]) if counts[base] > 1 else "")
                if not isinstance(node, ast.ClassDef):
                    complexity = decisions(node); lines = node.end_lineno - node.lineno + 1
                    row["functions"].append({"symbol": name, "line": node.lineno, "end_line": node.end_lineno,
                                              "lines": lines, "complexity": complexity, "async": isinstance(node, ast.AsyncFunctionDef)})
                    if complexity > config["limits"]["complexity"]:
                        finding("DS-PY-COMPLEXITY", filename, name, node.lineno, node.end_lineno, {"complexity": complexity, "limit": config["limits"]["complexity"]})
                    if lines > config["limits"]["function_lines"]:
                        finding("DS-PY-FUNCTION-SIZE", filename, name, node.lineno, node.end_lineno, {"lines": lines, "limit": config["limits"]["function_lines"]})
                prefix = name + "."
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                key = prefix + "<bare-except>"; counts[key] += 1
                finding("DS-PY-BARE-EXCEPT", filename, key + "#" + str(counts[key]), node.lineno, node.end_lineno, {"catches": "BaseException"})
            pending.extend((child, prefix) for child in reversed(list(ast.iter_child_nodes(node))))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                package = (row["module"] or "").split(".")
                if not filename.endswith("/__init__.py"): package = package[:-1]
                if node.level:
                    base = ".".join(package[:len(package) - node.level + 1]) if node.level <= len(package) else ""
                    base = ".".join(filter(None, (base, node.module)))
                else: base = node.module or ""
                targets = [base + "." + a.name if base + "." + a.name in module_paths else base for a in node.names]
                if node.level and (row["module"] is None or node.level > len(package)):
                    targets = ["<relative-import-outside-declared-package>"]
            else: continue
            for target in sorted(set(targets)):
                candidates = sorted(module_paths.get(target, []))
                status = "EXTERNAL_OR_UNRESOLVED" if not candidates else "AMBIGUOUS" if len(candidates) > 1 else "RESOLVED" if entries[candidates[0]]["status"] == "ADMITTED" else "UNAVAILABLE"
                imports.append({"from": filename, "to": candidates[0] if len(candidates) == 1 else None, "module": target,
                                "line": node.lineno, "status": status, "candidates": candidates})
    # A parsed source may import a present target whose syntax/encoding cannot be analyzed.
    analyzed = {r["path"] for r in output if r["status"] == "ANALYZED"}
    for edge in imports:
        if edge["status"] == "RESOLVED" and edge["to"] not in analyzed: edge["status"] = "UNAVAILABLE"
    imports.sort(key=lambda e: (e["from"], e["line"], e["module"]))
    components = cycles(analyzed, imports)
    for component in components:
        finding("DS-PY-IMPORT-CYCLE", component[0], "cycle:" + digest(component)[7:], 1, 1, {"paths": component}, component)
    findings.sort(key=lambda f: (f["path"], f["line"], f["rule"], f["symbol"]))
    history = raw["history"]; changes = defaultdict(lambda: {"revisions": set(), "added": 0, "deleted": 0, "binary": 0})
    for commit in history["commits"]:
        for change in commit["changes"]:
            if change["path"] not in entries or entries[change["path"]]["status"] == "OUT_OF_SCOPE": continue
            cell = changes[change["path"]]; cell["revisions"].add(commit["revision"])
            if change["added"] is None: cell["binary"] += 1
            else: cell["added"] += change["added"]; cell["deleted"] += change["deleted"]
    hotspots = [{"path": p, "revisions": len(c["revisions"]), "added": c["added"], "deleted": c["deleted"],
                 "binary_changes": c["binary"], "coverage": history["status"]} for p, c in changes.items()]
    hotspots.sort(key=lambda h: (-h["revisions"], -(h["added"] + h["deleted"]), h["path"]))
    unknown = any(r["status"] in ("UNAVAILABLE", "PARSE_ERROR") for r in output)
    applicable = any(e["status"] == "ADMITTED" or
                     (e["path"] and e["path"].endswith(".py") and e["status"] == "UNAVAILABLE")
                     for e in raw["entries"])
    return {"engine": ENGINE, "subject": deepcopy(raw["subject"]), "observed_at": raw["observed_at"],
            "coverage": "PARTIAL" if unknown else "COMPLETE" if applicable else "NOT_APPLICABLE", "files": output, "findings": findings,
            "imports": imports, "import_cycles": components, "hotspots": hotspots,
            "history": {k: deepcopy(v) for k, v in history.items() if k != "commits"},
            "authority": "STATIC_SOURCE_EVIDENCE; no execution, independent acceptance, health score or merge authority"}
