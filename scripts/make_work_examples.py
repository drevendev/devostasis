"""Regenerate the public synthetic Evidence to Action example, offline."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from devostasis.canonical import canonical_bytes
from devostasis.workscope import CONTRACT
from devostasis.workscope.bundle import build
from devostasis.workscope.collect import complete
from devostasis.workscope.evidence import empty_evidence, source
from devostasis.workscope.model import default_policy

root = Path(__file__).resolve().parents[1] / "examples" / "work"
root.mkdir(exist_ok=True)
at = "2026-10-02T12:00:00Z"
sha, head, base = "a" * 40, "b" * 40, "c" * 40
subject = {"provider": "github", "endpoint": "https://api.github.com", "project_id": "123456",
           "locator": "acme/widget", "revision": sha, "context": "CANONICAL"}
identity = {k: subject[k] for k in ("provider", "endpoint", "project_id")}
subject["source_binding"] = {"contract": "devostasis.work-source.v1", "kind": "DEFAULT_BRANCH",
    "project": identity, "source_project": identity, "source_locator": "acme/widget", "ref": "main", "revision": sha}
change = {"id": "10", "title": "Add the feature", "state": "OPEN", "author": "worker", "owners": [], "reviewers": [],
          "head": head, "base": base, "updated_at": at, "draft": False, "conflict": False, "merge_train": False,
          "reviews": complete([{"id": "r10", "actor": "reviewer", "revision": head, "state": "APPROVED", "at": at}]),
          "checks": complete([{"id": "c10", "name": "tests", "revision": head, "state": "PASS", "at": at}]),
          "threads": complete(), "files": complete(["src/app.py"])}
other = {**change, "id": "11", "author": "other", "title": "Review the parser", "reviews": complete()}
for record in (change, other):
    record["source_binding"] = {"contract": "devostasis.work-source.v1", "kind": "CHANGE", "project": identity,
        "source_project": identity, "source_locator": "acme/widget", "ref": record["id"], "revision": head}
inv = {"contract": CONTRACT, "kind": "inventory", "subject": subject, "observed_at": at,
       "changes": complete([change, other]), "issues": complete([{"id": "20", "title": "Add validation",
           "state": "OPEN", "owners": ["worker"], "updated_at": at}]), "receipts": [],
       "selection": {"changes": "OPEN_AND_REGISTERED", "issues": ["20"]}}
policy = default_policy("worker")
policy["version"] = "widget-1"
policy["required_checks"] = ["tests"]
policy["priorities"] = {"issue:20": {"rank": 0, "rationale": "Explicit customer acceptance."}}
policy["criteria"] = [{"id": "validation", "issue": "20", "acceptance": ["Reject an invalid input and accept a valid input."],
                       "paths": ["src/app.py"], "symbols": ["validate"], "dependencies": [], "implementations": [], "done": False}]
policy["requests"] = [{"id": "parser-question", "queue": "research", "question": "Which parser rule explains the recorded contradiction?",
                       "paths": ["src/parser.py"], "symbols": ["parse"], "acceptance": ["Record a bounded reproducer and a rule verdict."],
                       "dependencies": [], "owner": None}]
evidence = empty_evidence()
junit = b'<testsuite><testcase file="src/app.py" line="12" name="test_invalid"><failure/></testcase></testsuite>'
evidence["sources"].append(source("junit.v1", "pytest", "8-profile-1", subject, at, junit))
for name, value in (("inventory", inv), ("policy", policy), ("evidence", evidence)):
    (root / f"{name}.json").write_bytes(canonical_bytes(value))
_, content = build(inv, policy, evidence)
destination = root / "bundle"
destination.mkdir(exist_ok=True)
for name, value in content.items():
    (destination / name).write_bytes(value)
print(destination)
