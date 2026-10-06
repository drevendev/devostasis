"""Target markers and contradictory planning evidence (0.2.0).

``PV-AUDIT-TARGET-MARKER-SYNTAX-001`` found the configured marker matched as a
substring, so ``NotTarget: B1`` and ``PreTarget:B1`` linked a change request to
B1. The audit's regressions ``LINK-MARKER-01..08`` are known here only by the
categories its handoff names (exact marker, embedded-prefix negatives, custom
markers, multiple markers, prose without the marker, end-to-end file
planning); these tests cover each category and do not claim the individual
case texts, which never reached this repository.
"""

from __future__ import annotations

import json

import pytest

from devostasis.adapters.github import GitHubAdapter, GitHubClient, marker_target_ids
from devostasis.cli import main
from devostasis.config import single_project
from devostasis.normalize import INV_CRS, derive
from devostasis.observations import ObservationSet
from devostasis.vitals import evaluate_all
from helpers import full_inputs, obs_set
from test_github_adapter import BASE, NOW, FakeTransport, _paged, _pull, _register_route, _routes


def test_an_exact_marker_links_wherever_it_stands_alone():
    for text in ("Target: B1", "Target:B1", "intro\nTarget: B1", "(Target: B1)", "- Target: B1", "done.\tTarget: B1", "Target: B1."):
        assert marker_target_ids(text, "Target:") == ["B1"], text


@pytest.mark.parametrize("text", ["NotTarget: B1", "SubTarget: B1", "PreTarget:B1", "xTarget: B1", "_Target: B1", "2Target: B1", "ЯTarget: B1"])
def test_a_marker_embedded_in_a_larger_token_links_nothing(text):
    assert marker_target_ids(text, "Target:") == []


def test_a_marker_ending_in_a_word_character_needs_a_boundary_after_it_too():
    assert marker_target_ids("Target B1", "Target") == ["B1"]
    assert marker_target_ids("Targeted B1", "Target") == [], "the id would otherwise be read out of the word"
    assert marker_target_ids("Targets: B1", "Target") == []


def test_a_custom_marker_replaces_the_default_and_is_matched_exactly():
    assert marker_target_ids("Goal: release/1.2", "Goal:") == ["release/1.2"]
    assert marker_target_ids("Target: B1", "Goal:") == []
    assert marker_target_ids("SubGoal: B1\nGoal: B2", "Goal:") == ["B2"]
    hash_marker = "#target"
    assert marker_target_ids(f"{hash_marker} B7", hash_marker) == ["B7"]
    assert marker_target_ids(f"x{hash_marker} B7", hash_marker) == []


def test_several_markers_keep_their_order_and_link_each_target_once():
    assert marker_target_ids("Target: B2\nTarget: B1\nTarget: B2", "Target:") == ["B2", "B1"]
    assert marker_target_ids("NotTarget: B9 and Target: B3", "Target:") == ["B3"]


@pytest.mark.parametrize("text", ["target: B1", "TARGET: B1", "targets B1", "Fixes 12", "the target is B1", ""])
def test_prose_without_the_configured_marker_links_nothing(text):
    assert marker_target_ids(text, "Target:") == []


def test_embedded_markers_do_not_link_end_to_end():
    """File planning end to end: only the standalone marker becomes a reference, and Direction counts only it."""
    project = single_project("acme/widget", planning={"source": "file", "path": ".devostasis/targets.json", "link_marker": "Target:"})
    pulls = [_pull(number=7, body="SubTarget: B1\nTarget: B2"), _pull(number=8, body="NotTarget: B1")]
    register = _register_route((("B1", "open"), ("B2", "closed")))
    routes = _routes(**{f"{BASE}/pulls": _paged(pulls), f"{BASE}/contents/.devostasis/targets.json": register})
    obs = GitHubAdapter(GitHubClient(FakeTransport(routes)), NOW).collect(project)
    refs = {item["number"]: item["target_refs"] for item in obs.get(INV_CRS).value}
    assert refs == {7: [{"target_id": "B2", "state": "CLOSED"}], 8: []}
    derive(obs, project)
    direction = {r.vital_id: r for r in evaluate_all(obs)}["direction"]
    assert (direction.band, direction.derived["linked_active_change_count_28d"], direction.derived["unlinked_active_change_count_28d"]) == ("MIXED", 1, 1)


@pytest.mark.parametrize("command", ["evaluate", "build"])
def test_observations_whose_counts_contradict_each_other_are_an_input_error(tmp_path, capsys, command):
    """PV-DIRECTION-INCOMPLETE-001 section 7: L + U + R != N is invalid normalized input, refused before classification."""
    data = full_inputs(obs_set()).to_dict()
    for item in data["observations"]:
        if item["observation_id"] == "planning.linkage.active_change_requests_unresolved_count_28d":
            item["value"] = 5
    path = tmp_path / "observations.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    ObservationSet.load(path)
    if command == "evaluate":
        argv = ["evaluate", "--observations", str(path), "--out", str(tmp_path / "snapshot.json")]
    else:
        argv = ["build", "--observations", str(path), "--store", str(tmp_path / "store")]
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert "input error" in err and "DIRECTION_LINKAGE_COUNTS_INCONSISTENT" in err
