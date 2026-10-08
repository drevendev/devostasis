"""DEV-OPS: repeatable bound observation, portable history and reported outcomes."""

from copy import deepcopy
import json
from pathlib import Path
import stat
from zipfile import ZipFile, ZipInfo, ZIP_STORED, ZIP_DEFLATED

import pytest

from devostasis import __version__
from devostasis.canonical import canonical_bytes, digest
from devostasis.cli import main
from devostasis.workscope.archive import admit_archive, export_history, import_history
from devostasis.workscope.bundle import build, publish, verify, verify_content
from devostasis.workscope.collect import Client
from devostasis.workscope.model import ScopeError, identity
from devostasis.workscope.operations import (AUTHORITY, append_record, audit, binding, make_binding, observe,
                                            invocation, record_result, snapshot)
from test_work_handoff import AT, Transport, fixture, prepare_packet

NEXT = "2026-10-07T12:00:00Z"


def setup(enabled=True):
    decoded, _, _ = fixture()
    config = decoded["policy.json"]
    value = make_binding({**identity(decoded["scope.json"]["subject"]), "locator": "123"}, config, "test-pilot", enabled)
    def factory(b):
        return Client(b["project"]["provider"], b["project"]["endpoint"], transport=Transport(), **b["budget"])
    return value, config, factory


@pytest.mark.parametrize("field,value", [("enabled", None), ("contract", "devostasis.work-adoption.v999"),
    ("engine_version", "future"), ("policy", {"actor": "another", "version": "example-1", "digest": "sha256:" + "0" * 64})])
def test_bad_binding_refuses_network_and_publication(tmp_path, field, value):
    b, p, _ = setup(); b[field] = value
    def forbidden(_):
        pytest.fail("inadmissible binding must not create a network client")
    with pytest.raises(ScopeError):
        observe(b, p, tmp_path, forbidden, AT)
    assert not list(tmp_path.iterdir())


def test_disabled_binding_records_negative_control_without_canonical_write(tmp_path):
    b, p, _ = setup(False)
    result = observe(b, p, tmp_path, lambda _: pytest.fail("disabled caller requested a client"), AT)
    assert result["status"] == "DISABLED" and result["bundle_id"] is None
    assert not (tmp_path / "work").exists()
    assert audit(tmp_path, identity(b["project"]), AT)["invocations"]["DISABLED"] == 1


def test_disabled_receipt_cannot_claim_received_network_bytes(tmp_path):
    b, p, _ = setup(False)
    result = observe(b, p, tmp_path, lambda _: pytest.fail("disabled caller requested a client"), AT)
    receipt = json.loads(Path(result["invocation"]).read_text()); receipt["telemetry"]["response_bytes"] = 1
    with pytest.raises(ScopeError, match="network telemetry"):
        invocation(receipt)


def test_rehashed_binding_cannot_claim_another_selected_change(tmp_path):
    from test_workscope_adapters import Routes, gitlab_routes
    from test_workscope import config
    p = config(); p["criteria"][0]["implementations"] = ["1"]
    b = make_binding({"provider": "gitlab", "endpoint": "https://gitlab.example/api/v4",
        "project_id": "123", "locator": "123"}, p, "selected", True)
    result = observe(b, p, tmp_path, lambda b: Client("gitlab", b["project"]["endpoint"],
        transport=Routes(gitlab_routes()), **b["budget"]), AT)
    receipt = json.loads(Path(result["invocation"]).read_text())
    p = deepcopy(p); p["criteria"][0]["implementations"] = []
    decoded = verify(result["path"])
    _, content = build(decoded["inventory.json"], p, decoded["evidence.json"])
    decoded = verify_content(content)
    receipt["binding"]["policy"]["digest"] = digest(p)
    receipt["binding_digest"] = digest(receipt["binding"])
    receipt["bundle_id"] = decoded["manifest.json"]["bundle_id"]
    receipt["manifest_digest"] = digest(decoded["manifest.json"])
    with pytest.raises(ScopeError, match="selected change binding"):
        invocation(receipt, decoded)


def test_repeated_bound_generations_and_calendar_days_survive_transfer(tmp_path):
    b, p, factory = setup(); expected = identity(b["project"])
    source, dest = tmp_path / "source", tmp_path / "restored"
    first = observe(b, p, source, factory, AT); second = observe(b, p, source, factory, NEXT)
    assert first["status"] == second["status"] == "COMPLETE"
    assert first["bundle_id"] != second["bundle_id"]
    before = audit(source, expected, NEXT)
    assert before["utc_calendar_days"] == 2 and before["largest_gap_seconds"] == 86400
    assert before["latest_bundle_id"] == second["bundle_id"]
    archive = tmp_path / "private.zip"; again = tmp_path / "again.zip"
    export_history(source, expected, archive); export_history(source, expected, again)
    assert archive.read_bytes() == again.read_bytes()
    import_history(archive, expected, dest); import_history(archive, expected, dest)
    assert audit(dest, expected, NEXT) == before
    assert audit(dest, expected, "2026-10-09T12:00:00Z")["status"] == "EXPIRED"
    assert audit(dest, expected, "2026-10-05T12:00:00Z")["status"] == "FUTURE"


def test_backfill_and_candidates_never_move_latest_or_add_canonical_days(tmp_path):
    b, p, factory = setup(); expected = identity(b["project"])
    result = observe(b, p, tmp_path, factory, NEXT)
    observe(b, p, tmp_path, factory, AT)
    decoded = verify(result["path"]); inv = deepcopy(decoded["inventory.json"])
    inv["subject"]["context"] = "CANDIDATE"
    inv["subject"]["source_binding"]["kind"] = "BRANCH"
    _, content = build(inv, p, decoded["evidence.json"])
    publish(tmp_path, content)
    report = audit(tmp_path, expected, NEXT)
    assert report["latest_bundle_id"] == result["bundle_id"] and report["candidate_generations"] == 1
    assert report["utc_calendar_days"] == 2


def test_wrong_immutable_project_stops_before_inventory_and_records_failure(tmp_path):
    b, p, factory = setup(); b["project"]["project_id"] = "999"
    result = observe(b, p, tmp_path, factory, AT)
    assert result["status"] == "FAILED" and result["path"] is None
    receipt = json.loads(Path(result["invocation"]).read_text())
    assert receipt["telemetry"]["requests"] == 1 and "ADOPTION_PROJECT_MISMATCH" in receipt["reasons"][0]
    assert not (tmp_path / "work").exists()


def test_provider_failure_and_partial_collection_are_distinct_audited_states(tmp_path):
    b, p, factory = setup()
    def fail(_):
        raise OSError("provider unavailable")
    failed = observe(b, p, tmp_path, fail, AT)
    assert failed["status"] == "FAILED"
    b["selection"] = {"mode": "CHANGES", "changes": ["99"]}
    class Missing(Transport):
        def request(self, method, url, headers, body, timeout):
            if "/merge" in url or "/merge_trains" in url:
                return 404, {}, b"{}"
            return super().request(method, url, headers, body, timeout)
    partial = observe(b, p, tmp_path, lambda b: Client("gitlab", b["project"]["endpoint"], transport=Missing(), **b["budget"]), NEXT)
    assert partial["status"] == "PARTIAL" and partial["bundle_id"]
    report = audit(tmp_path, identity(b["project"]), NEXT)
    assert report["invocations"]["PARTIAL"] == report["invocations"]["FAILED"] == 1


def claim(packet):
    return {"actor": "executor", "outcome": "REPORTED_COMPLETE", "notes": "Bounded source qualification completed.",
            "acceptance": [{"criterion": c, "status": "PASS", "evidence": ["local:qualification.json"]} for c in packet["item"]["acceptance"]]}


def test_packet_bound_result_remains_caller_report_after_expiry_and_restore(tmp_path):
    decoded, client, _ = fixture(); packet = prepare_packet(decoded, client)
    result = record_result(decoded, packet, claim(packet), tmp_path / "source", NEXT)
    assert result["outcome"] == "REPORTED_COMPLETE" and result["authority"] == AUTHORITY
    expected = identity(decoded["scope.json"]["subject"])
    export_history(tmp_path / "source", expected, tmp_path / "private.zip")
    import_history(tmp_path / "private.zip", expected, tmp_path / "restored")
    assert audit(tmp_path / "restored", expected, NEXT)["caller_results"]["REPORTED_COMPLETE"] == 1


@pytest.mark.parametrize("mutation", ["actor", "missing", "unknown", "evidence", "packet", "clock"])
def test_outcome_cannot_override_binding_acceptance_or_packet(tmp_path, mutation):
    decoded, client, _ = fixture(); packet = prepare_packet(decoded, client); result = claim(packet); at = NEXT
    if mutation == "actor": result["actor"] = "another actor"
    if mutation == "missing": result["acceptance"] = []
    if mutation == "unknown": result["acceptance"][0]["status"] = "UNKNOWN"
    if mutation == "evidence": result["acceptance"][0]["evidence"] = []
    if mutation == "packet": packet["total_bytes"] = 999
    if mutation == "clock": at = "2026-10-05T12:00:00Z"
    with pytest.raises(ScopeError):
        record_result(decoded, packet, result, tmp_path, at)
    assert not list(tmp_path.iterdir())


def alter_archive(original, output, mutation):
    with ZipFile(original) as z:
        members = {i.filename: z.read(i) for i in z.infolist()}
    index = json.loads(members["index.json"])
    if mutation == "foreign":
        index["project"]["project_id"] = "999"; members["index.json"] = canonical_bytes(index)
    if mutation == "digest":
        name = next(k for k in members if k.endswith("report.md")); members[name] += b"forged"
    if mutation == "path": members["../escape"] = b"escape"
    if mutation == "missing": members.pop(next(k for k in members if k.endswith("scope.json")))
    if mutation == "rehashed":
        name = next(k for k in members if k.endswith("scope.json"))
        scope = json.loads(members[name]); scope["authority"] = "merge anything"; members[name] = canonical_bytes(scope)
        index["members"][name] = {"size": len(members[name]), "digest": digest(scope)}
        members["index.json"] = canonical_bytes(index)
    with ZipFile(output, "w") as z:
        for name, data in members.items():
            info = ZipInfo(name); info.create_system = 3
            info.external_attr = (stat.S_IFLNK if mutation == "link" and name.endswith("report.md") else stat.S_IFREG) << 16
            info.compress_type = ZIP_DEFLATED if mutation == "compressed" else ZIP_STORED
            z.writestr(info, data)
        if mutation == "duplicate":
            with pytest.warns(UserWarning): z.writestr(ZipInfo("index.json"), members["index.json"])


@pytest.mark.parametrize("mutation", ["foreign", "digest", "path", "missing", "rehashed", "link", "compressed", "duplicate"])
def test_untrusted_archive_is_fully_refused_before_store_mutation(tmp_path, mutation):
    b, p, factory = setup(); expected = identity(b["project"])
    observe(b, p, tmp_path / "source", factory, AT)
    export_history(tmp_path / "source", expected, tmp_path / "original.zip")
    alter_archive(tmp_path / "original.zip", tmp_path / "bad.zip", mutation)
    with pytest.raises((ScopeError, KeyError, ValueError)):
        import_history(tmp_path / "bad.zip", expected, tmp_path / "target")
    assert not (tmp_path / "target").exists() and not (tmp_path / "escape").exists()


def test_caps_existing_collisions_and_changed_history_fail_closed(tmp_path):
    b, p, factory = setup(); expected = identity(b["project"])
    result = observe(b, p, tmp_path / "source", factory, AT)
    archive = tmp_path / "private.zip"; export_history(tmp_path / "source", expected, archive)
    with pytest.raises(ScopeError, match="byte cap"):
        admit_archive(archive, expected, 1)
    decoded = verify(result["path"]); decoded["policy.json"]["version"] = "different"
    _, conflict = build(decoded["inventory.json"], decoded["policy.json"], decoded["evidence.json"])
    publish(tmp_path / "target", conflict)
    before = snapshot(tmp_path / "target", expected)[0]
    with pytest.raises(ScopeError, match="same-time"):
        import_history(archive, expected, tmp_path / "target")
    assert snapshot(tmp_path / "target", expected)[0] == before
    report = Path(result["path"]) / "report.md"; report.write_bytes(report.read_bytes() + b"forged")
    with pytest.raises(ScopeError):
        export_history(tmp_path / "source", expected, tmp_path / "bad.zip")
    assert not (tmp_path / "bad.zip").exists()


def test_invocation_ids_never_replace_an_existing_record(tmp_path):
    b, p, factory = setup(); result = observe(b, p, tmp_path, factory, AT)
    record = json.loads(Path(result["invocation"]).read_text()); record["status"] = "FAILED"
    with pytest.raises(ScopeError, match="collision"):
        append_record(tmp_path, identity(b["project"]), "runs", record["run_id"], record)


def test_linked_store_ancestor_refuses_network_and_publication(tmp_path, monkeypatch):
    b, p, _ = setup()
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == tmp_path or original(self))
    with pytest.raises(ScopeError, match="linked"):
        observe(b, p, tmp_path / "nested", lambda _: pytest.fail("linked store requested network"), AT)
    assert not list(tmp_path.iterdir())


def test_linked_lock_is_refused_before_open(tmp_path, monkeypatch):
    from devostasis.workscope.bundle import locked
    lock = tmp_path / ".lock"; original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == lock or original(self))
    with pytest.raises(ScopeError, match="linked"):
        with locked(lock):
            pytest.fail("linked lock opened")
    assert not lock.exists()


def test_unbounded_failure_text_remains_a_bounded_visible_receipt(tmp_path):
    b, p, _ = setup()
    def fail(_):
        raise ValueError("line\n" * 10000)
    result = observe(b, p, tmp_path, fail, AT)
    assert result["status"] == "FAILED" and len(result["reasons"][0]) == 8192


def test_public_operation_schemas_and_example_match_written_shapes(tmp_path):
    root = Path(__file__).parents[1]
    b, p, factory = setup(); result = observe(b, p, tmp_path, factory, AT)
    receipt = json.loads(Path(result["invocation"]).read_text())
    decoded, client, _ = fixture(); packet = prepare_packet(decoded, client)
    outcome = record_result(decoded, packet, claim(packet), tmp_path / "result", NEXT)
    record = json.loads(Path(outcome["path"]).read_text())
    for filename, value in (("work-adoption.schema.json", b), ("work-invocation.schema.json", receipt), ("work-result.schema.json", record)):
        schema = json.loads((root / "schemas" / filename).read_text())
        assert set(schema["required"]) == set(schema["properties"]) == set(value)
        assert schema["additionalProperties"] is False
    example = json.loads((root / "examples/work/adoption.json").read_text())
    binding(example, json.loads((root / "examples/work/policy.json").read_text()))
    assert example["engine_version"] == __version__ and not example["enabled"]


def test_operations_cli_provides_offline_binding_audit_transfer_and_outcome(tmp_path, capsys):
    b, p, factory = setup(); expected = identity(b["project"])
    policy_file = tmp_path / "policy.json"; policy_file.write_bytes(canonical_bytes(p))
    binding_file = tmp_path / "binding.json"
    common = ["--provider", "gitlab", "--endpoint", expected["endpoint"], "--expected-project-id", "123"]
    assert main(["work", "bind", *common, "--repo", "123", "--policy", str(policy_file), "--integration-id", "test", "--output", str(binding_file)]) == 0
    assert not json.loads(binding_file.read_text())["enabled"]
    assert main(["work", "observe", "--binding", str(binding_file), "--policy", str(policy_file), "--store", str(tmp_path / "disabled"), "--at", AT]) == 0
    capsys.readouterr()
    observe(b, p, tmp_path / "source", factory, AT)
    assert main(["work", "audit", *common, "--store", str(tmp_path / "source"), "--at", AT]) == 0
    assert json.loads(capsys.readouterr().out)["canonical_generations"] == 1
    archive = str(tmp_path / "private.zip")
    assert main(["work", "export-history", *common, "--store", str(tmp_path / "source"), "--output", archive]) == 0; capsys.readouterr()
    assert main(["work", "verify-history", *common, "--archive", archive]) == 0; capsys.readouterr()
    assert main(["work", "import-history", *common, "--archive", archive, "--store", str(tmp_path / "restored")]) == 0
    assert json.loads(capsys.readouterr().out)["invocations"] == 1
    decoded, client, _ = fixture(); packet = prepare_packet(decoded, client)
    packet_file, claim_file = tmp_path / "packet.json", tmp_path / "claim.json"
    packet_file.write_bytes(canonical_bytes(packet)); claim_file.write_bytes(canonical_bytes(claim(packet)))
    dest = publish(tmp_path / "result-store", build(decoded["inventory.json"], p, decoded["evidence.json"])[1])
    bindings = [*common, "--actor", "executor", "--policy-version", "example-1", "--bundle", str(dest)]
    assert main(["work", "record-result", *bindings, "--packet", str(packet_file), "--result", str(claim_file), "--store", str(tmp_path / "result-store"), "--at", NEXT]) == 0
    record = json.loads(capsys.readouterr().out)
    assert main(["work", "verify-result", *bindings, "--record", record["path"]]) == 0
