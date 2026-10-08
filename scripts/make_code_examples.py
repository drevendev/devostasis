"""Regenerate synthetic native analysis and its analyze_code work queue offline."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from devostasis.canonical import canonical_bytes
from devostasis.codeanalysis.bundle import build, verify_content
from devostasis.codeanalysis.consumer import packet, work_evidence
from devostasis.codeanalysis.engine import default_policy
from devostasis.codeanalysis.git import collect
from devostasis.workscope.bundle import build as build_work, verify_content as verify_work
from devostasis.workscope.collect import complete
from devostasis.workscope.model import default_policy as work_policy

ROOT = Path(__file__).resolve().parents[1]
AT = "2026-10-08T12:00:00Z"


def generate():
    config = default_policy()
    config["limits"]["complexity"] = 1
    with tempfile.TemporaryDirectory(prefix="devostasis-synthetic-code-") as directory:
        repo = Path(directory)
        environment = {**{k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE"}},
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "Synthetic Fixture", "GIT_COMMITTER_NAME": "Synthetic Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_AUTHOR_DATE": AT, "GIT_COMMITTER_DATE": AT}
        def git(*args):
            return subprocess.run(["git", "-c", "commit.gpgSign=false", "-c", "core.autocrlf=false", *args],
                cwd=repo, env=environment, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
        git("init", "--initial-branch=main", "--object-format=sha1")
        files = {"src/widget/__init__.py": "", "src/widget/app.py": "from . import parser\n\ndef choose(value):\n    if value:\n        return 1\n    return 0\n",
            "src/widget/parser.py": "from . import app\n\ndef fallback():\n    try:\n        return 1\n    except:\n        return 0\n", "README.md": "Synthetic source fixture.\n"}
        for filename, data in files.items():
            file = repo / filename; file.parent.mkdir(parents=True, exist_ok=True); file.write_bytes(data.encode("utf-8"))
        git("add", "--all"); git("commit", "-m", "Synthetic offline analysis fixture")
        raw = collect(repo, "HEAD", config, AT)
        _, content = build(raw, config)
    decoded = verify_content(content)
    inv = deepcopy(json.loads((ROOT / "examples/work/inventory.json").read_text(encoding="utf-8")))
    inv["subject"]["revision"] = raw["subject"]["revision"]
    inv["subject"]["source_binding"]["revision"] = raw["subject"]["revision"]
    inv.update(observed_at=AT, changes=complete(), issues=complete(), receipts=[],
               selection={"changes": "OPEN_AND_REGISTERED", "issues": []})
    evidence = work_evidence(decoded, inv)
    consumer_policy = work_policy("worker")
    _, consumer_content = build_work(inv, consumer_policy, evidence)
    scope = verify_work(consumer_content)["scope.json"]
    assert any(item["queue"] == "analyze_code" for item in scope["items"])
    output = {"policy.json": canonical_bytes(config), "packet.json": canonical_bytes(packet(decoded, ["src/widget/app.py"])),
              "inventory.json": canonical_bytes(inv), "work-policy.json": canonical_bytes(consumer_policy),
              "evidence.json": canonical_bytes(evidence)}
    output.update({"bundle/" + name: data for name, data in content.items()})
    output.update({"work-bundle/" + name: data for name, data in consumer_content.items()})
    return output


if __name__ == "__main__":
    destination = ROOT / "examples/code"
    for name, data in generate().items():
        file = destination / name; file.parent.mkdir(parents=True, exist_ok=True); file.write_bytes(data)
    print(destination)
