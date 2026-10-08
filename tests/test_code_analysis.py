"""DEV-CODE: real offline Git evidence, conservative deltas and work integration."""

import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess

import pytest

from devostasis.canonical import canonical_bytes, digest
from devostasis.cli import main
from devostasis.codeanalysis.bundle import admit, build, publish, read, verify, verify_content
from devostasis.codeanalysis.consumer import compare, packet, verify_packet, work_evidence
from devostasis.codeanalysis.engine import default_policy, policy
from devostasis.codeanalysis.git import Git, collect

AT = "2026-10-08T12:00:00Z"
NEXT = "2026-10-09T12:00:00Z"


def git(repo, *args, data=None, at=AT):
    return subprocess.run(["git", "-c", "commit.gpgSign=false", *args], cwd=repo, input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        env={**{k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE"}},
             "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
             "GIT_AUTHOR_NAME": "Synthetic Fixture", "GIT_COMMITTER_NAME": "Synthetic Fixture",
             "GIT_AUTHOR_EMAIL": "fixture@example.invalid", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
             "GIT_AUTHOR_DATE": at, "GIT_COMMITTER_DATE": at}).stdout


def commit(repo, files, at=AT):
    for name, value in files.items():
        destination = repo / name
        if value is None:
            destination.unlink(); continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(value.encode("utf-8") if isinstance(value, str) else value)
    git(repo, "add", "--all"); git(repo, "commit", "-m", "synthetic source", at=at)
    return git(repo, "rev-parse", "HEAD").strip().decode()


def repository(tmp_path, files=None):
    repo = tmp_path / "repository"; repo.mkdir()
    git(repo, "init", "--initial-branch=main", "--object-format=sha1")
    commit(repo, files or {"src/pkg/__init__.py": "", "src/pkg/a.py": "from . import b\n\ndef choose(x):\n    if x:\n        return 1\n    return 0\n",
                          "src/pkg/b.py": "from . import a\n\ndef fallback():\n    try:\n        return 1\n    except:\n        return 0\n", "README.md": "fixture"})
    return repo


def analyze(repo, config=None, at=AT, ref="HEAD"):
    config = deepcopy(config or default_policy())
    config["limits"]["complexity"] = 1
    raw = collect(repo, ref, config, at)
    manifest, members = build(raw, config)
    return raw, config, manifest, members, verify_content(members)


def test_code_real_git_to_byte_identical_offline_bundle_without_source_execution(tmp_path):
    repo = repository(tmp_path)
    marker = tmp_path / "executed"
    commit(repo, {"danger.py": f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"}, NEXT)
    a = analyze(repo, at=NEXT); b = analyze(repo, at=NEXT)
    assert a[2:] == b[2:] and not marker.exists()
    root = publish(tmp_path / "analysis", a[3]); publish(root, a[3])
    git(repo, "checkout", "--detach", "HEAD~1")
    assert verify(root)["manifest.json"] == a[2] and not marker.exists()
    assert a[4]["analysis.json"]["import_cycles"] == [["src/pkg/a.py", "src/pkg/b.py"]]
    assert {f["rule"] for f in a[4]["analysis.json"]["findings"]} >= {"DS-PY-COMPLEXITY", "DS-PY-BARE-EXCEPT", "DS-PY-IMPORT-CYCLE"}


@pytest.mark.parametrize("mutation", ["blob", "commit", "tree", "inventory_path", "inventory_oid", "foreign_source", "missing_tree", "unknown_field", "finding", "report", "policy_version", "engine"])
def test_code_rehashed_or_changed_bundle_cannot_bypass_source_proof_and_replay(tmp_path, mutation):
    _, _, _, members, decoded = analyze(repository(tmp_path))
    changed = dict(members)
    if mutation in ("finding", "report", "engine"):
        if mutation == "report": changed["report.md"] += b"false verdict"
        elif mutation == "engine":
            manifest = deepcopy(decoded["manifest.json"]); manifest["engine"] = "unrecognized"
            changed["manifest.json"] = canonical_bytes(manifest)
        else:
            result = deepcopy(decoded["analysis.json"]); result["findings"] = []
            changed["analysis.json"] = canonical_bytes(result)
    else:
        raw = deepcopy(decoded["inputs.json"])
        if mutation == "blob": raw["sources"]["src/pkg/a.py"] = base64.b64encode(b"forged bytes").decode()
        if mutation == "commit": raw["proof"]["commit"] = base64.b64encode(b"tree " + raw["subject"]["tree"].encode() + b"\n\nforged").decode()
        if mutation == "tree": raw["proof"]["trees"][raw["subject"]["tree"]] = ""
        if mutation == "inventory_path": raw["entries"][0]["path"] = "elsewhere.py"
        if mutation == "inventory_oid": raw["entries"][0]["object_id"] = "0" * 40
        if mutation == "foreign_source": raw["sources"]["outside.py"] = ""
        if mutation == "missing_tree": raw["proof"]["trees"].pop(raw["subject"]["tree"])
        if mutation == "unknown_field": raw["ignored"] = True
        changed["inputs.json"] = canonical_bytes(raw)
        if mutation == "policy_version":
            config = deepcopy(decoded["policy.json"]); config["grammar"] = "latest"
            changed["policy.json"] = canonical_bytes(config)
    # Updating member digests and the outer id is insufficient to admit a lie.
    manifest = json.loads(changed["manifest.json"])
    manifest["members"] = {k: digest(json.loads(v)) if k != "report.md" else "sha256:" + __import__("hashlib").sha256(v).hexdigest()
                           for k, v in changed.items() if k != "manifest.json"}
    manifest["bundle_id"] = digest({k: v for k, v in manifest.items() if k != "bundle_id"})
    changed["manifest.json"] = canonical_bytes(manifest)
    with pytest.raises((ValueError, KeyError)): verify_content(changed)


@pytest.mark.parametrize("budget,value,reason", [("max_files", 1, "FILE_COUNT_CAP"), ("max_file_bytes", 20, "FILE_BYTE_CAP"), ("max_total_bytes", 100, "TOTAL_BYTE_CAP")])
def test_code_read_caps_are_explicit_and_never_become_empty_success(tmp_path, budget, value, reason):
    repo = repository(tmp_path); config = default_policy(); config["budget"][budget] = value
    if budget == "max_total_bytes": config["budget"]["max_file_bytes"] = value
    raw, _, _, _, decoded = analyze(repo, config)
    assert decoded["analysis.json"]["coverage"] == "PARTIAL"
    assert reason in {e["reason"] for e in raw["entries"]}
    assert all(e["path"] not in raw["sources"] for e in raw["entries"] if e["status"] != "ADMITTED")


def test_code_syntax_encoding_unsupported_and_policy_exclusion_have_distinct_states(tmp_path):
    repo = repository(tmp_path, {"broken.py": "def invalid(:\n", "encoding.py": b"# coding: utf-8\n\xff", "script.js": "throw 1;",
                                 "vendor/a.py": "if x:\n    pass\n", "valid.py": "def fine():\n    return 1\n"})
    decoded = analyze(repo)[4]; files = {r["path"]: r for r in decoded["analysis.json"]["files"]}
    assert files["broken.py"]["status"] == "PARSE_ERROR"
    assert files["encoding.py"]["status"] == "UNAVAILABLE" and files["encoding.py"]["functions"] == []
    assert files["script.js"]["status"] == "UNSUPPORTED" and files["script.js"]["lines"] is None
    assert files["vendor/a.py"]["status"] == "OUT_OF_SCOPE"
    assert files["valid.py"]["status"] == "ANALYZED"
    assert any(f["rule"] == "DS-PY-SYNTAX" for f in decoded["analysis.json"]["findings"])


def test_code_non_utf8_python_cookie_is_analyzed_without_rewriting_blob_bytes(tmp_path):
    data = b"# coding: latin-1\nname = '\xe9'\n"
    decoded = analyze(repository(tmp_path, {"latin.py": data}))[4]
    assert decoded["analysis.json"]["files"][0]["status"] == "ANALYZED"
    assert base64.b64decode(decoded["inputs.json"]["sources"]["latin.py"]) == data


def test_code_git_link_and_submodule_are_not_followed(tmp_path):
    repo = repository(tmp_path, {"safe.py": "pass\n"})
    blob = git(repo, "hash-object", "-w", "--stdin", data=b"../private.py").strip().decode()
    head = git(repo, "rev-parse", "HEAD").strip().decode()
    git(repo, "update-index", "--add", "--cacheinfo", f"120000,{blob},linked.py")
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head},submodule")
    git(repo, "commit", "-m", "synthetic linked objects", at=NEXT)
    raw = analyze(repo, at=NEXT)[0]
    assert {e["path"] for e in raw["entries"] if e["reason"] == "SOURCE_LINK_OR_SUBMODULE"} == {"linked.py", "submodule"}
    assert set(raw["sources"]) == {"safe.py"}


def test_code_import_ambiguity_and_missing_target_never_form_proven_cycles(tmp_path):
    repo = repository(tmp_path, {"a.py": "import b\nimport external\n", "b.py": "import a\n", "src/b.py": "import a\n"})
    result = analyze(repo)[4]["analysis.json"]
    assert any(e["status"] == "AMBIGUOUS" and e["module"] == "b" for e in result["imports"])
    assert any(e["status"] == "EXTERNAL_OR_UNRESOLVED" and e["module"] == "external" for e in result["imports"])
    assert result["import_cycles"] == []


def test_code_nested_function_decisions_are_not_double_counted_and_finding_ids_survive_line_moves(tmp_path):
    code = "def outer(x):\n    def inner(y):\n        if y and x:\n            return y\n        return 0\n    return inner(x)\n"
    repo = repository(tmp_path, {"a.py": code})
    before = analyze(repo)[4]
    functions = {f["symbol"]: f for f in before["analysis.json"]["files"][0]["functions"]}
    assert functions["outer"]["complexity"] == 1 and functions["outer.inner"]["complexity"] == 3
    commit(repo, {"a.py": "\n\n" + code}, NEXT)
    after = analyze(repo, at=NEXT)[4]
    assert before["analysis.json"]["findings"][0]["id"] == after["analysis.json"]["findings"][0]["id"]
    assert compare(before, after)["findings"][0]["state"] == "CHANGED"


def test_code_partial_history_counts_are_labeled_and_time_window_excludes_future_commits(tmp_path):
    repo = repository(tmp_path, {"a.py": "x = 1\n"})
    commit(repo, {"a.py": "x = 2\n"}, NEXT)
    commit(repo, {"a.py": "x = 3\n"}, "2026-10-10T12:00:00Z")
    config = default_policy(); config["history"]["max_commits"] = 1
    result = analyze(repo, config, at=NEXT)[4]["analysis.json"]
    assert result["history"]["status"] == "PARTIAL" and result["hotspots"][0]["coverage"] == "PARTIAL"
    assert result["hotspots"][0]["revisions"] == 1


def test_code_missing_source_cannot_resolve_a_finding_and_deleted_source_can(tmp_path):
    repo = repository(tmp_path, {"b.py": "def choose(x):\n    if x:\n        return 1\n    return 0\n"})
    config = default_policy(); config["budget"]["max_files"] = 1
    before = analyze(repo, config)[4]
    commit(repo, {"a.py": "pass\n"}, NEXT)
    after = analyze(repo, config, at=NEXT)[4]
    assert compare(before, after)["findings"][0]["state"] == "UNOBSERVED"
    commit(repo, {"b.py": None}, "2026-10-10T12:00:00Z")
    deleted = analyze(repo, config, at="2026-10-10T12:00:00Z")[4]
    assert compare(before, deleted)["findings"][0]["state"] == "RESOLVED"


def test_code_changed_policy_or_unrelated_root_identity_is_incomparable(tmp_path):
    repo = repository(tmp_path); before = analyze(repo)[4]
    config = default_policy(); config["version"] = "other"
    assert compare(before, analyze(repo, config)[4])["reasons"] == ["ANALYSIS_POLICY_CHANGED"]
    other = tmp_path / "other"; other.mkdir()
    unrelated = repository(other, {"unique.py": "pass\n"})
    assert compare(before, analyze(unrelated)[4])["reasons"] == ["LOCAL_REPOSITORY_IDENTITY_CHANGED"]


@pytest.mark.parametrize("mutation", ["bytes", "path", "subject", "budget", "authority", "duplicates"])
def test_code_offline_source_packets_reject_tampering_and_enforce_declared_limits(tmp_path, mutation):
    decoded = analyze(repository(tmp_path))[4]
    value = packet(decoded, ["src/pkg/a.py"])
    assert verify_packet(value, decoded) == value
    with pytest.raises(ValueError): packet(decoded, ["src/pkg/a.py"], max_bytes=1)
    if mutation == "bytes": value["files"][0]["base64"] = base64.b64encode(b"forged").decode()
    if mutation == "path": value["files"][0]["path"] = "../escape"
    if mutation == "subject": value["subject"]["revision"] = "0" * 40
    if mutation == "budget": value["budget"]["max_bytes"] = 1
    if mutation == "authority": value["authority"] = "permission to merge"
    if mutation == "duplicates": value["files"].append(deepcopy(value["files"][0]))
    value["packet_id"] = digest({k: v for k, v in value.items() if k != "packet_id"})
    with pytest.raises(ValueError): verify_packet(value, decoded)


def test_code_cli_offline_end_to_end_and_admitted_work_evidence(tmp_path, capsys):
    from test_work_handoff import fixture
    repo = repository(tmp_path); output = tmp_path / "analysis"
    assert main(["code", "analyze", "--repo", str(repo), "--output", str(output), "--at", AT]) == 0
    result = json.loads(capsys.readouterr().out)
    assert main(["code", "verify", "--bundle", str(output)]) == 0; capsys.readouterr()
    assert main(["code", "sarif", "--bundle", str(output), "--output", str(tmp_path / "report.sarif")]) == 0
    assert main(["code", "packet", "--bundle", str(output), "--path", "src/pkg/a.py", "--output", str(tmp_path / "packet.json")]) == 0
    assert main(["code", "verify-packet", "--bundle", str(output), "--packet", str(tmp_path / "packet.json")]) == 0; capsys.readouterr()
    assert main(["code", "compare", "--before", str(output), "--after", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "COMPARABLE"
    inv = deepcopy(fixture()[0]["inventory.json"])
    inv["subject"]["revision"] = verify(output)["analysis.json"]["subject"]["revision"]
    inv["subject"]["source_binding"]["revision"] = inv["subject"]["revision"]
    data = work_evidence(verify(output), inv)
    assert data["sources"][0]["subject"] == inv["subject"] and data["sources"][0]["profile"] == "sarif.v1"
    inv["subject"]["revision"] = "0" * 40; inv["subject"]["source_binding"]["revision"] = "0" * 40
    with pytest.raises(ValueError, match="revision mismatch"): work_evidence(verify(output), inv)
    assert result["bundle_id"] == verify(output)["manifest.json"]["bundle_id"]


def test_code_repository_strings_are_escaped_in_the_report_and_foreign_outputs_are_preserved(tmp_path):
    name = "![badge](x).py"
    repo = repository(tmp_path, {name: "def choose(x):\n    if x:\n        return 1\n    return 0\n"})
    members = analyze(repo)[3]
    assert b"![badge](x)" not in members["report.md"]
    foreign = tmp_path / "foreign"; foreign.mkdir(); (foreign / "keep.txt").write_text("keep")
    with pytest.raises(ValueError): publish(foreign, members)
    assert (foreign / "keep.txt").read_text() == "keep"


@pytest.mark.parametrize("field,value", [("grammar", "latest"), ("unknown", True), ("include", ["../outside"]), ("source_roots", []), ("history", {"enabled": 1, "days": 28, "max_commits": 500})])
def test_code_policy_rejects_unknown_or_unbounded_inputs(field, value):
    config = default_policy(); config[field] = value
    with pytest.raises(ValueError): policy(config)


def test_code_no_python_scope_is_not_applicable_and_syntax_only_scope_is_partial(tmp_path):
    repo = repository(tmp_path, {"script.js": "throw 1;"})
    assert analyze(repo)[4]["analysis.json"]["coverage"] == "NOT_APPLICABLE"
    commit(repo, {"broken.py": "def invalid(:\n"}, NEXT)
    assert analyze(repo, at=NEXT)[4]["analysis.json"]["coverage"] == "PARTIAL"


def test_code_shallow_history_retains_explicit_partial_coverage(tmp_path):
    repo = repository(tmp_path); commit(repo, {"a.py": "pass\n"}, NEXT)
    clone = tmp_path / "shallow"
    git(tmp_path, "clone", "--depth=1", repo.as_uri(), str(clone))
    result = analyze(clone, at=NEXT)[4]["analysis.json"]
    assert result["history"]["status"] == "PARTIAL"
    assert "SHALLOW_HISTORY" in result["history"]["reasons"]


def test_code_sha256_repository_proofs_replay_with_explicit_object_format(tmp_path):
    repo = tmp_path / "sha256"; repo.mkdir()
    git(repo, "init", "--initial-branch=main", "--object-format=sha256")
    commit(repo, {"a.py": "def simple():\n    return 1\n"})
    decoded = analyze(repo)[4]
    assert decoded["analysis.json"]["subject"]["object_format"] == "sha256"
    assert len(decoded["analysis.json"]["subject"]["revision"]) == 64


def test_code_relative_import_outside_declared_package_is_unresolved(tmp_path):
    repo = repository(tmp_path, {"src/pkg/a.py": "from ... import b\n", "src/b.py": "import pkg.a\n"})
    result = analyze(repo)[4]["analysis.json"]
    assert result["import_cycles"] == []
    assert result["imports"][1]["status"] == "EXTERNAL_OR_UNRESOLVED"


def test_code_git_caps_and_option_like_revisions_fail_explicitly(tmp_path):
    repo = repository(tmp_path); reader = Git(repo)
    with pytest.raises(ValueError, match="BYTE_CAP"):
        reader.run(["cat-file", "commit", "HEAD"], cap=1)
    with pytest.raises(ValueError, match="invalid Git revision"):
        reader.resolve("--all")
    reader.deadline = 0
    with pytest.raises(ValueError, match="TIME_CAP"):
        reader.run(["rev-parse", "HEAD"])


def test_code_work_export_preserves_gaps_and_age_and_produces_analysis_queue(tmp_path):
    from test_work_handoff import fixture
    from devostasis.workscope.bundle import build as work_build, verify_content as work_verify
    from devostasis.workscope.collect import complete
    from devostasis.workscope.model import default_policy as work_policy
    repo = repository(tmp_path, {"a.py": "def choose(x):\n    if x:\n        return 1\n    return 0\n", "broken.py": "def invalid(:\n"})
    decoded = analyze(repo)[4]
    inv = deepcopy(fixture()[0]["inventory.json"])
    inv["subject"]["revision"] = decoded["analysis.json"]["subject"]["revision"]
    inv["subject"]["source_binding"]["revision"] = inv["subject"]["revision"]
    inv.update(observed_at=AT, changes=complete(), issues=complete(), receipts=[], selection={"changes": "OPEN_AND_REGISTERED", "issues": []})
    evidence = work_evidence(decoded, inv)
    entry = evidence["sources"][0]
    assert entry["status"] == "PARTIAL" and entry["observed_at"] == AT
    with pytest.raises(ValueError, match="observation time"):
        work_evidence(decoded, inv, NEXT)
    _, content = work_build(inv, work_policy("worker"), evidence)
    result = work_verify(content)["scope.json"]
    assert any(i["queue"] == "analyze_code" for i in result["items"])
    assert any("CODE_SOURCE_COVERAGE_PARTIAL" in gap["reason"] for gap in result["gaps"])
    inv["observed_at"] = "2026-10-20T12:00:00Z"
    _, stale = work_build(inv, work_policy("worker"), evidence)
    stale_scope = work_verify(stale)["scope.json"]
    assert all(item["action"] == "recover_evidence" for item in stale_scope["items"])
    assert any(gap["reason"] == "REPORT_EXPIRED_OR_FUTURE" for gap in stale_scope["gaps"])


def test_code_frozen_native_and_work_examples_replay_with_admitted_source_packet():
    from devostasis.workscope.bundle import verify as verify_work
    root = Path(__file__).resolve().parents[1] / "examples/code"
    decoded = verify(root / "bundle")
    verify_packet(json.loads((root / "packet.json").read_text()), decoded)
    work = verify_work(root / "work-bundle")
    assert any(i["queue"] == "analyze_code" for i in work["scope.json"]["items"])
    for name, value in (("code-manifest", decoded["manifest.json"]),
                        ("code-policy", decoded["policy.json"]),
                        ("code-packet", json.loads((root / "packet.json").read_text()))):
        schema = json.loads((root.parents[1] / "schemas" / (name + ".schema.json")).read_text())
        assert schema["additionalProperties"] is False
        assert set(value) == set(schema["required"]) == set(schema["properties"])


def test_code_sarif_uri_encoding_and_legacy_work_paths_are_bound_to_real_filenames(tmp_path):
    from devostasis.codeanalysis.bundle import sarif
    from test_work_handoff import fixture
    name = "space # name.py"
    decoded = analyze(repository(tmp_path, {name: "def choose(x):\n    if x:\n        return 1\n    return 0\n"}))[4]
    report = sarif(decoded["analysis.json"])
    assert report["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "space%20%23%20name.py"
    inv = deepcopy(fixture()[0]["inventory.json"])
    inv["subject"]["revision"] = decoded["analysis.json"]["subject"]["revision"]
    inv["subject"]["source_binding"]["revision"] = inv["subject"]["revision"]
    evidence = work_evidence(decoded, inv)
    exported = json.loads(base64.b64decode(evidence["sources"][0]["report"]["base64"]))
    assert exported["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == name


def test_code_function_counts_exclude_definition_time_decisions_and_missing_root_packages(tmp_path):
    repo = repository(tmp_path, {"src/__init__.py": "from . import app\n",
        "src/app.py": "@(left if condition else right)\ndef choose(value=1 if condition else 0):\n    return value\n"})
    result = analyze(repo)[4]["analysis.json"]
    row = next(f for f in result["files"] if f["path"] == "src/app.py")
    assert row["functions"][0]["complexity"] == 1
    assert result["imports"][0]["status"] == "EXTERNAL_OR_UNRESOLVED"


def test_code_git_inherited_repository_and_secret_environment_cannot_override_selected_source(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    other_root = tmp_path / "other"; other_root.mkdir()
    other = repository(other_root, {"foreign.py": "pass\n"})
    expected = git(repo, "rev-parse", "HEAD").strip().decode()
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("PRIVATE_CREDENTIAL_SENTINEL", "synthetic-never-forward")
    original = subprocess.Popen
    environments = []
    def capture(*args, **kwargs):
        environments.append(kwargs["env"])
        return original(*args, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", capture)
    result = analyze(repo)[4]["analysis.json"]
    assert result["subject"]["revision"] == expected
    assert all(not ({"GIT_DIR", "GIT_WORK_TREE", "PRIVATE_CREDENTIAL_SENTINEL"} & set(env)) for env in environments)
