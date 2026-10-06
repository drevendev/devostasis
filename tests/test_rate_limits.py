"""Conditional requests, bounded retries and a request budget (target B4, debt D-2).

Three limits on how evidence is fetched. None of them may change what the
evidence means: a cached run and a fresh run of the same repository must
produce the same observations and the same bundle identity, and a run that
runs out of budget must say so rather than report a shorter list as complete.
"""

from __future__ import annotations

import json

import pytest

from devostasis.adapters.cache import ConditionalCache
from devostasis.adapters.github import (
    BUDGET_EXHAUSTED,
    GitHubAdapter,
    GitHubClient,
    PAGINATION_CAPPED,
    RetryPolicy,
    retry_after_seconds,
)
from devostasis.config import single_project
from devostasis.history import FilesystemHistoryStore
from devostasis.normalize import INV_COMMITS, INV_CRS
from devostasis.observations import AVAILABLE, PARTIAL
from devostasis.runner import build_from_observations
from test_github_adapter import BASE, NOW, FakeTransport, _commit, _paged, _routes


class RecordingTransport(FakeTransport):
    """A transport that answers 304 when the caller returns a tag it already has."""

    def __init__(self, routes, etags=None):
        super().__init__(routes)
        self.etags = etags or {}
        self.conditional = []

    def get(self, path, params=None, headers=None):
        tag = self.etags.get(path)
        if headers and headers.get("If-None-Match") == tag:
            self.conditional.append(path)
            self.calls.append((path, dict(params or {})))
            return 304, {"etag": tag}, None
        status, response_headers, body = super().get(path, params)
        if tag and status == 200:
            response_headers = dict(response_headers, etag=tag)
        return status, response_headers, body


def _collect(client, **project):
    return GitHubAdapter(client, NOW).collect(single_project("acme/widget", **project))


def test_retry_after_is_read_from_either_header():
    assert retry_after_seconds({"retry-after": "7"}) == 7
    assert retry_after_seconds({"retry-after": "1.9"}) == 1
    assert retry_after_seconds({"x-ratelimit-remaining": "0", "x-ratelimit-reset": "160"}, now=100) == 60
    assert retry_after_seconds({"x-ratelimit-remaining": "0", "x-ratelimit-reset": "50"}, now=100) == 0
    assert retry_after_seconds({"x-ratelimit-remaining": "12"}) is None
    assert retry_after_seconds({"retry-after": "soon"}) is None


def test_a_short_wait_is_taken_and_the_call_succeeds():
    attempts = {"n": 0}

    def flaky(_params):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return 429, {"retry-after": "2"}, {"message": "slow down"}
        return 200, {}, []

    slept = []
    client = GitHubClient(FakeTransport(_routes(**{f"{BASE}/releases": flaky})), sleep=slept.append)
    obs = _collect(client)
    assert slept == [2] and client.retries == 1
    assert obs.status_of("forge.releases.inventory") == AVAILABLE


def test_a_long_wait_is_refused_and_becomes_an_explicit_status():
    """A primary rate limit resets on the hour; waiting it out would be a hang."""
    slept = []
    routes = _routes(**{f"{BASE}/releases": (403, {"retry-after": "3600"}, {"message": "API rate limit exceeded"})})
    client = GitHubClient(FakeTransport(routes), sleep=slept.append)
    obs = _collect(client)
    assert slept == [] and client.retries == 0
    assert obs.get("forge.releases.inventory").reason_code == "RATE_LIMITED"


def test_waiting_stops_at_the_total_budget():
    routes = _routes(**{f"{BASE}/releases": (503, {"retry-after": "20"}, {"message": "boom"})})
    slept = []
    policy = RetryPolicy(attempts=5, max_single_wait_seconds=30, total_wait_budget_seconds=25)
    client = GitHubClient(FakeTransport(routes), retry=policy, sleep=slept.append)
    obs = _collect(client)
    assert slept == [20], "the second wait would exceed the run's total waiting budget"
    assert obs.get("forge.releases.inventory").reason_code == "PROVIDER_ERROR"


def test_a_permanent_failure_is_never_retried():
    slept = []
    routes = _routes(**{f"{BASE}/releases": (404, {}, {"message": "Not Found"})})
    client = GitHubClient(FakeTransport(routes), sleep=slept.append)
    _collect(client)
    assert slept == [] and client.retries == 0


def test_the_budget_turns_a_long_enumeration_into_partial_evidence():
    many = [_commit(f"s{i:03d}", "2026-09-01T10:00:00Z") for i in range(400)]
    client = GitHubClient(FakeTransport(_routes(**{f"{BASE}/commits": _paged(many)})), budget=3)
    obs = _collect(client)
    commits = obs.get(INV_COMMITS)
    assert commits.status == PARTIAL and commits.reason_code == BUDGET_EXHAUSTED
    assert client.budget_exhausted and client.billed_count == 3
    assert BUDGET_EXHAUSTED + ":3" in obs.receipt.capability_notes


def test_without_a_budget_a_capped_enumeration_still_says_pagination():
    from devostasis.adapters import github as github_module

    many = [_commit(f"s{i:03d}", "2026-09-01T10:00:00Z") for i in range(400)]
    client = GitHubClient(FakeTransport(_routes(**{f"{BASE}/commits": _paged(many)})))
    original = github_module.MAX_COMMIT_PAGES
    github_module.MAX_COMMIT_PAGES = 2
    try:
        obs = _collect(client)
    finally:
        github_module.MAX_COMMIT_PAGES = original
    assert obs.get(INV_COMMITS).reason_code == PAGINATION_CAPPED
    assert not client.budget_exhausted and obs.receipt.capability_notes.count(BUDGET_EXHAUSTED) == 0


def test_a_budget_that_is_never_reached_changes_nothing():
    plain = _collect(GitHubClient(FakeTransport(_routes())))
    bounded_client = GitHubClient(FakeTransport(_routes()), budget=1000)
    bounded = _collect(bounded_client)
    assert plain.to_dict() == bounded.to_dict()
    assert not bounded_client.budget_exhausted


def test_a_conditional_hit_replays_the_body_and_costs_no_quota(tmp_path):
    etags = {path: f'"tag-{index}"' for index, path in enumerate(_routes())}
    cache = ConditionalCache(tmp_path / "etags.json")

    first_transport = RecordingTransport(_routes(), etags)
    first_client = GitHubClient(first_transport, cache=cache)
    first = _collect(first_client)
    assert first_client.conditional_hits == 0 and first_client.billed_count > 0
    cache.save()

    second_transport = RecordingTransport(_routes(), etags)
    second_client = GitHubClient(second_transport, cache=ConditionalCache(tmp_path / "etags.json"))
    second = _collect(second_client)

    assert second_client.conditional_hits > 0
    assert second_client.billed_count < first_client.billed_count
    assert second_transport.conditional, "the second run sent If-None-Match"
    assert first.to_dict() == second.to_dict(), "a replayed body is the same evidence"


def test_a_cached_run_produces_the_same_bundle_identity(tmp_path):
    """The whole point: enabling the cache must not move a bundle id."""
    etags = {path: f'"tag-{index}"' for index, path in enumerate(_routes())}
    cache_path = tmp_path / "etags.json"
    project = single_project("acme/widget", config_version="1")

    warm = GitHubClient(RecordingTransport(_routes(), etags), cache=ConditionalCache(cache_path))
    fresh_obs = _collect(warm)
    warm.cache.save()
    cached_client = GitHubClient(RecordingTransport(_routes(), etags), cache=ConditionalCache(cache_path))
    cached_obs = _collect(cached_client)
    assert cached_client.conditional_hits > 0

    fresh = build_from_observations(project, fresh_obs, FilesystemHistoryStore(tmp_path / "a"))
    cached = build_from_observations(project, cached_obs, FilesystemHistoryStore(tmp_path / "b"))
    assert fresh.bundle_id == cached.bundle_id
    for name in sorted(set(fresh.members) - {"manifest.json"}):
        assert fresh.members[name] == cached.members[name], name


def test_the_receipt_records_what_was_asked_not_how_it_was_fetched(tmp_path):
    obs = _collect(GitHubClient(FakeTransport(_routes())))
    receipt = obs.receipt.to_dict()
    assert receipt["schema"] == "devostasis.receipt.v2"
    assert "request_count" not in receipt and "conditional_hits" not in receipt
    assert receipt["requested_keys"] and receipt["per_key"]


def test_run_meta_keeps_the_fetching_provenance(tmp_path):
    from devostasis.runner import run_project

    class OneShot(FakeTransport):
        pass

    client = GitHubClient(OneShot(_routes()))
    outcome = run_project(single_project("acme/widget", config_version="1"), FilesystemHistoryStore(tmp_path), client, NOW)
    assert outcome.ok
    manifest = json.loads((FilesystemHistoryStore(tmp_path).project_dir("github.com/acme/widget") / "latest" / "manifest.json").read_text("utf-8"))
    assert "run_meta" not in manifest
    run_meta = outcome.execution_receipt["run_meta"]
    assert run_meta["requests"] == client.request_count and run_meta["billed_requests"] == client.billed_count
    assert run_meta["conditional_hits"] == 0 and run_meta["retries"] == 0
    assert "run_meta" not in manifest["identity_preimage"]


def test_failed_collection_retains_external_invocation_audit(tmp_path):
    from devostasis.runner import run_project
    routes = _routes(); routes[BASE] = (403, {}, {"message": "Forbidden"})
    client = GitHubClient(FakeTransport(routes))
    outcome = run_project(single_project("acme/widget"), FilesystemHistoryStore(tmp_path), client, NOW)
    assert not outcome.ok and outcome.execution_receipt["run_id"]
    assert outcome.execution_receipt["result_bundle_id"] is None
    assert outcome.execution_receipt["receipt_identity"] is None
    assert outcome.execution_receipt["diagnostics"]
    assert not list(tmp_path.rglob("manifest.json"))


def test_a_missing_or_corrupt_cache_costs_requests_never_correctness(tmp_path):
    corrupt = tmp_path / "etags.json"
    corrupt.write_text("{ not json", encoding="utf-8")
    cache = ConditionalCache(corrupt)
    assert len(cache) == 0
    client = GitHubClient(FakeTransport(_routes()), cache=cache)
    obs = _collect(client)
    assert client.conditional_hits == 0
    assert obs.to_dict() == _collect(GitHubClient(FakeTransport(_routes()))).to_dict()


def test_the_cache_survives_a_round_trip_and_evicts_by_use(tmp_path):
    path = tmp_path / "etags.json"
    cache = ConditionalCache(path, max_entries=2)
    for index, key in enumerate(["a", "b", "c"]):
        cache.store(key, f'"{key}"', {"n": index})
    cache.body_for("b")
    cache.save()

    reloaded = ConditionalCache(path)
    assert len(reloaded) == 2
    assert reloaded.etag_for("b") == '"b"' and reloaded.etag_for("c") == '"c"'
    assert reloaded.etag_for("a") is None
    assert reloaded.body_for("c") == {"n": 2}


def test_a_body_too_large_to_cache_is_simply_not_cached(tmp_path):
    cache = ConditionalCache(tmp_path / "etags.json", max_entry_bytes=32)
    cache.store("small", '"s"', {"a": 1})
    cache.store("large", '"l"', {"a": "x" * 200})
    assert cache.etag_for("small") == '"s"' and cache.etag_for("large") is None


def test_an_entry_without_a_tag_is_not_stored(tmp_path):
    cache = ConditionalCache(tmp_path / "etags.json")
    cache.store("k", None, {"a": 1})
    assert len(cache) == 0


def test_a_304_without_a_cached_body_refetches_instead_of_failing(tmp_path):
    """The provider says nothing changed but our copy is gone; ask again rather than guess."""
    cache = ConditionalCache(tmp_path / "etags.json")
    cache.store(ConditionalCache.key(f"{BASE}/releases", {"per_page": 100, "page": 1}), '"tag"', [{"tag_name": "v1"}])
    cache._entries[ConditionalCache.key(f"{BASE}/releases", {"per_page": 100, "page": 1})].pop("body")
    client = GitHubClient(RecordingTransport(_routes(), {f"{BASE}/releases": '"tag"'}), cache=cache)
    obs = _collect(client)
    assert obs.status_of("forge.releases.inventory") == AVAILABLE


@pytest.mark.parametrize("budget", [1, 2, 5])
def test_the_budget_never_reports_a_shorter_list_as_complete(budget):
    many = [_commit(f"s{i:03d}", "2026-09-01T10:00:00Z") for i in range(400)]
    client = GitHubClient(FakeTransport(_routes(**{f"{BASE}/commits": _paged(many)})), budget=budget)
    obs = _collect(client)
    for key in (INV_COMMITS, INV_CRS):
        item = obs.get(key)
        if item is not None and item.status == AVAILABLE:
            assert (item.coverage or {}).get("complete") is not False
    assert client.billed_count <= budget
