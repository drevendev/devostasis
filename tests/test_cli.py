"""End-to-end CLI paths that need no network."""

import json

from devostasis.cli import main
from helpers import full_inputs, obs_set


def test_build_verify_render_and_index(tmp_path, capsys):
    obs_path = tmp_path / "observations.json"
    full_inputs(obs_set()).save(obs_path)
    store = tmp_path / "store"
    assert main(["build", "--observations", str(obs_path), "--store", str(store)]) == 0
    out = capsys.readouterr().out
    assert "BASELINE" in out and "pulse=STEADY" in out
    latest = store / "projects" / "github.com" / "acme" / "widget" / "latest"
    assert main(["verify", "--bundle", str(latest)]) == 0
    assert "verified" in capsys.readouterr().out
    assert main(["render", "--bundle", str(latest)]) == 0
    rendered = capsys.readouterr().out
    assert rendered.encode("utf-8") == (latest / "report.md").read_bytes()
    assert (store / "projects" / "README.md").exists()
    assert main(["index", "--store", str(store)]) == 0
    index = json.loads((latest.parent / "index.json").read_text("utf-8"))
    assert len(index["bundles"]) == 1
    assert main(["gauges", "--bundle", str(latest), "--card"]) == 0
    gauges_out = capsys.readouterr().out
    assert '"contract": "devostasis.gauge.v1"' in gauges_out and "Horizon" in gauges_out
    assert main(["demand", "--bundle", str(latest), "--order-only"]) == 0
    assert capsys.readouterr().out.startswith("1. ")


def test_actions_summary_writes_step_summary_and_outputs(tmp_path, capsys, monkeypatch):
    obs_path = tmp_path / "observations.json"
    full_inputs(obs_set()).save(obs_path)
    store = tmp_path / "store"
    assert main(["build", "--observations", str(obs_path), "--store", str(store)]) == 0
    capsys.readouterr()
    latest = store / "projects" / "github.com" / "acme" / "widget" / "latest"
    summary = tmp_path / "summary.md"
    outputs = tmp_path / "outputs.txt"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    assert main(["actions-summary", "--bundle", str(latest)]) == 0
    text = summary.read_text("utf-8")
    assert text.startswith("## Devostasis: acme/widget") and "| Order | Vital | Level | Band | Gauge |" in text
    lines = dict(line.split("=", 1) for line in outputs.read_text("utf-8").splitlines() if "=" in line)
    assert lines["comparison-status"] == "BASELINE" and lines["attention"].split(" ")[1] in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "MINIMAL", "UNRESOLVED")
    assert json.loads(lines["levels"])["integrity"] == "MINIMAL" and json.loads(lines["bands"])["pulse"] == "STEADY"
    assert json.loads(lines["attention-order"])[0]["vital_id"] == lines["attention"].split(" ")[0]
    monkeypatch.delenv("GITHUB_STEP_SUMMARY")
    monkeypatch.delenv("GITHUB_OUTPUT")
    assert main(["actions-summary", "--bundle", str(latest)]) == 0
    assert "attention=" in capsys.readouterr().out


def test_run_repo_mode_builds_a_single_project_config():
    from devostasis.cli import build_parser, config_for_repo

    args = build_parser().parse_args(["run", "--repo", "acme/widget", "--store", "s", "--planning", "file", "--planning-path", "plans/targets.json", "--debt-label", "type:debt", "--config-version", "self-v0.1.1"])
    config = config_for_repo(args)
    assert len(config.projects) == 1 and config.store_path == "s" and config.config_version == "self-v0.1.1"
    project = config.projects[0]
    assert project.planning == {"source": "file", "path": "plans/targets.json", "link_marker": "Target:"}
    assert project.debt_mapping == {"source": "labels", "labels": ["type:debt"], "mapping_version": "cli-1"}


def test_evaluate_command(tmp_path, capsys):
    obs_path = tmp_path / "observations.json"
    full_inputs(obs_set()).save(obs_path)
    out_path = tmp_path / "snapshot.json"
    assert main(["evaluate", "--observations", str(obs_path), "--out", str(out_path)]) == 0
    snapshot = json.loads(out_path.read_text("utf-8"))
    assert len(snapshot["vitals"]) == 7
    assert "integrity=CLEAN" in capsys.readouterr().out


def test_run_rejects_invalid_config(tmp_path, capsys):
    config = tmp_path / "devostasis.json"
    config.write_text(json.dumps({"config_version": "1", "projects": [{"repo": "a/b", "theme": "x"}]}), "utf-8")
    assert main(["run", "--config", str(config), "--store", str(tmp_path / "store")]) == 2
    assert "CONFIG_IDENTITY_UNCLASSIFIED" in capsys.readouterr().err


def test_build_refuses_observations_collected_under_another_configuration(tmp_path, capsys):
    """#27: the receipt names the configuration the aggregates were derived under; a build must resolve the same one."""
    from devostasis.config import single_project
    from devostasis.observations import Receipt

    collected_under = single_project("acme/widget", debt={"source": "labels", "labels": ["bug"], "mapping_version": "1"})
    obs = full_inputs(obs_set())
    obs.finalize_receipt(Receipt(run_id="run-test", collector_version="test", target=obs.subject, started_at=obs.observed_at, ended_at=obs.observed_at, config_hash=collected_under.effective_config_digest()))
    obs_path = tmp_path / "observations.json"
    obs.save(obs_path)
    store = tmp_path / "store"

    assert main(["build", "--observations", str(obs_path), "--store", str(store)]) == 1
    err = capsys.readouterr().err
    assert "CONFIG_MISMATCH" in err and "observe again" in err
    assert not (store / "projects").exists(), "nothing was persisted"

    assert main(["build", "--observations", str(obs_path), "--store", str(store), "--debt-label", "bug", "--debt-mapping-version", "1"]) == 0
    assert "BASELINE" in capsys.readouterr().out


def test_build_accepts_a_receipt_that_carries_a_placeholder_instead_of_a_digest(tmp_path, capsys):
    """Fixtures and examples carry no real digest; only a real one is compared."""
    obs_path = tmp_path / "observations.json"
    full_inputs(obs_set()).save(obs_path)
    assert main(["build", "--observations", str(obs_path), "--store", str(tmp_path / "store"), "--debt-label", "anything"]) == 0


def test_verify_does_not_claim_a_replay_it_did_not_perform(tmp_path, capsys):
    """A bundle of an earlier renderer is bound by its digest, not replayed; the message says which."""
    from devostasis import canonical

    obs_path = tmp_path / "observations.json"
    full_inputs(obs_set()).save(obs_path)
    store = tmp_path / "store"
    assert main(["build", "--observations", str(obs_path), "--store", str(store)]) == 0
    latest = store / "projects" / "github.com" / "acme" / "widget" / "latest"
    assert main(["verify", "--bundle", str(latest)]) == 0
    assert "report reproducibility all match" in capsys.readouterr().out

    manifest = json.loads((latest / "manifest.json").read_text("utf-8"))
    manifest["renderer_version"] = manifest["identity_preimage"]["renderer_version"] = "devostasis.render.v3"
    manifest["bundle_id"] = canonical.sha256_hex(canonical.canonical_bytes(manifest["identity_preimage"]))
    (latest / "manifest.json").write_bytes(canonical.pretty_json(manifest).encode("utf-8"))
    assert main(["verify", "--bundle", str(latest)]) == 1
    out = capsys.readouterr().out
    assert "RENDERER_VERSION_NOT_IN_LINEAGE" in out
    assert "reproducibility all match" not in out
