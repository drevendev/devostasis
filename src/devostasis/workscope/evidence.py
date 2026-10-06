"""Bounded report profiles. Reports are data and never execution instructions."""

from __future__ import annotations

import base64
import binascii
import json
import re
from decimal import Decimal
from xml.etree import ElementTree

from ..canonical import digest, digest_bytes
from . import CONTRACT
from .model import ScopeError, fields, identity, instant, number, path, require, revision, subject, text

MAX_REPORT_BYTES = 2 * 1024 * 1024
PROFILES = ("sarif.v1", "junit.v1", "cobertura.v1", "performance.v1")


def empty_evidence():
    return {"contract": CONTRACT, "kind": "evidence", "sources": []}


def source(profile, producer, version, project, at, data):
    require(len(data) <= MAX_REPORT_BYTES, "report exceeds byte budget")
    return {"profile": profile, "producer": producer, "version": version, "subject": project,
            "observed_at": at, "status": "COMPLETE", "reason": None,
            "report": {"digest": digest_bytes(data), "base64": base64.b64encode(data).decode("ascii")}}


def _json(data):
    def pairs(entries):
        result = {}
        for key, value in entries:
            require(key not in result, "report contains duplicate JSON members")
            result[key] = value
        return result
    def invalid(value):
        raise ScopeError(f"invalid JSON constant {value}")
    return json.loads(data, object_pairs_hook=pairs, parse_float=Decimal, parse_constant=invalid)


def _xml(data):
    decoded = data.decode("utf-8-sig")
    require(not re.search(r"<!\s*(DOCTYPE|ENTITY)", decoded, re.I), "XML entities/DTD not admitted")
    return ElementTree.fromstring(decoded)


def _finding(profile, producer, rule, location, line, symbol, trigger, verification):
    path(location); text(rule); number(line, 1, 10000000)
    if symbol is not None:
        text(symbol)
    seed = {"profile": profile, "producer": producer, "rule": rule,
            "path": location, "line": line, "symbol": symbol}
    return {"id": digest(seed), **seed, "trigger": trigger, "verification": verification}


def _sarif(data, producer):
    doc = _json(data)
    require(doc.get("version") == "2.1.0" and isinstance(doc.get("runs"), list) and doc["runs"], "SARIF 2.1.0 run required")
    output = []
    for run in doc["runs"]:
        require(isinstance(run.get("results"), list), "SARIF results unavailable")
        for result in run["results"]:
            if result.get("kind", "fail") in ("pass", "notApplicable"):
                continue
            rule = result.get("ruleId")
            require(isinstance(result.get("locations"), list) and result["locations"], "SARIF location required")
            for loc in result["locations"]:
                physical = loc.get("physicalLocation", {})
                artifact = physical.get("artifactLocation", {})
                require(not artifact.get("uriBaseId"), "SARIF uriBaseId requires an explicit resolved repository path")
                output.append(_finding("sarif.v1", producer, rule, artifact.get("uri"),
                                       physical.get("region", {}).get("startLine", 1), None,
                                       "Static analysis reported this rule at this location.",
                                       "Inspect the rule and location; reproduce or disposition the finding, then rerun the producer."))
    return output


def _junit(data, producer):
    root = _xml(data)
    require(root.tag in ("testsuite", "testsuites"), "JUnit testsuite(s) required")
    require(any(True for _ in root.iter("testcase")), "JUnit testcase evidence unavailable")
    output = []
    for test in root.iter("testcase"):
        if not any(test.find(tag) is not None for tag in ("failure", "error", "flakyFailure", "flakyError")):
            continue
        output.append(_finding("junit.v1", producer, "test-failure", test.get("file"),
                               int(test.get("line", "1")), test.get("name"),
                               "A test failure, error or explicit flaky rerun was reported.",
                               "Reproduce this exact test at the recorded revision and verify its expected behavior."))
    return output


def _coverage(data, producer):
    root = _xml(data)
    require(root.tag == "coverage", "Cobertura coverage root required")
    require(root.get("lines-valid") is not None and int(root.get("lines-valid")) > 0,
            "Coverage denominator unavailable")
    output, locations = [], set()
    for cls in root.iter("class"):
        for line in cls.findall("./lines/line"):
            hits = int(line.get("hits", "-1")); require(hits >= 0, "invalid line coverage")
            location = (path(cls.get("filename")), int(line.get("number", "0")))
            number(location[1], 1, 10000000)
            require(location not in locations, "duplicate coverage location")
            locations.add(location)
            if hits == 0:
                output.append(_finding("cobertura.v1", producer, "uncovered-line", cls.get("filename"),
                                       int(line.get("number", "0")), cls.get("name"),
                                       "An instrumented executable line has zero recorded hits.",
                                       "Assess the uncovered behavior and add a meaningful test or record a scoped disposition."))
    require(len(locations) == int(root.get("lines-valid")), "Coverage denominator contradicts line inventory")
    return output


def _performance(data, producer):
    doc = _json(data)
    fields(doc, ("measurements",))
    output = []
    require(isinstance(doc["measurements"], list), "measurements required")
    for m in doc["measurements"]:
        fields(m, ("name", "path", "line", "baseline", "current", "limit_percent", "unit", "baseline_revision"))
        number(m["baseline"], 1, 1000000000); number(m["current"], 0, 1000000000)
        number(m["limit_percent"], 0, 1000); text(m["unit"]); revision(m["baseline_revision"])
        if m["current"] * 100 > m["baseline"] * (100 + m["limit_percent"]):
            output.append(_finding("performance.v1", producer, m["name"], m["path"], m["line"], None,
                                   f"Measured {m['current']} {m['unit']} versus {m['baseline']} at {m['baseline_revision']}; consumer limit {m['limit_percent']} percent.",
                                   "Repeat the measurement under the declared producer profile and inspect the regression."))
    return output


def validate(value):
    fields(value, ("contract", "kind", "sources"))
    require(value["contract"] == CONTRACT and value["kind"] == "evidence", "unsupported evidence contract")
    require(isinstance(value["sources"], list) and len(value["sources"]) <= 100, "invalid evidence sources")
    seen = set()
    for item in value["sources"]:
        fields(item, ("profile", "producer", "version", "subject", "observed_at", "status", "reason", "report"))
        require(item["profile"] in PROFILES, "unsupported report profile")
        text(item["producer"]); text(item["version"]); subject(item["subject"]); instant(item["observed_at"])
        require(item["status"] in ("COMPLETE", "PARTIAL", "UNAVAILABLE"), "invalid report status")
        key = (item["profile"], item["producer"])
        require(key not in seen, "duplicate report producer/profile"); seen.add(key)
        if item["status"] == "UNAVAILABLE":
            require(item["report"] is None, "unavailable report contains data"); text(item["reason"])
        else:
            if item["status"] == "PARTIAL":
                text(item["reason"])
            else:
                require(item["reason"] is None, "complete report has missing evidence")
            fields(item["report"], ("digest", "base64"))
            encoded = item["report"]["base64"]
            require(isinstance(encoded, str) and len(encoded) <= (MAX_REPORT_BYTES + 2) // 3 * 4,
                    "report exceeds byte budget")
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ScopeError("invalid base64 report") from exc
            require(len(raw) <= MAX_REPORT_BYTES and base64.b64encode(raw).decode() == encoded, "noncanonical report encoding")
            require(digest_bytes(raw) == item["report"]["digest"], "report digest mismatch")
    return value


def normalize(value, project, at, ttl):
    validate(value)
    findings, gaps = {}, []
    parsers = dict(zip(PROFILES, (_sarif, _junit, _coverage, _performance)))
    for entry in value["sources"]:
        key = f"{entry['profile']}:{entry['producer']}"
        if entry["status"] != "COMPLETE":
            gaps.append({"source": key, "reason": entry["status"] + ":" + entry["reason"]})
        if entry["status"] == "UNAVAILABLE":
            continue
        if identity(entry["subject"]) != identity(project) or entry["subject"]["revision"] != project["revision"]:
            gaps.append({"source": key, "reason": "REPORT_IDENTITY_OR_REVISION_MISMATCH"}); continue
        age = (instant(at) - instant(entry["observed_at"])).total_seconds()
        if age < 0 or age > ttl:
            gaps.append({"source": key, "reason": "REPORT_EXPIRED_OR_FUTURE"}); continue
        raw = base64.b64decode(entry["report"]["base64"])
        try:
            parsed = parsers[entry["profile"]](raw, entry["producer"])
            require(len(parsed) <= 10000, "finding budget exceeded")
            for finding in parsed:
                require(finding["id"] not in findings, "duplicate finding location")
                findings[finding["id"]] = {**finding, "evidence": entry["report"]["digest"],
                                           "revision": project["revision"], "producer_version": entry["version"],
                                           "completeness": entry["status"]}
        except (ScopeError, ValueError, TypeError, AttributeError, KeyError, UnicodeError, ElementTree.ParseError) as exc:
            # A malformed report cannot partly contribute current findings.
            findings = {k: f for k, f in findings.items() if f["producer"] != entry["producer"] or f["profile"] != entry["profile"]}
            gaps.append({"source": key, "reason": "REPORT_MALFORMED:" + type(exc).__name__})
    return {"findings": [findings[k] for k in sorted(findings)], "gaps": sorted(gaps, key=lambda g: (g["source"], g["reason"]))}
