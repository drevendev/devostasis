"""Provider-backed, bounded consumer packets and mutable-ref invalidation."""

import base64
from copy import deepcopy
import hashlib
import json
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from devostasis.canonical import canonical_bytes, digest
from devostasis.workscope.binding import resolve, recheck
from devostasis.workscope.bundle import build, verify_content
from devostasis.workscope.collect import Client, collect
from devostasis.workscope.evidence import empty_evidence
from devostasis.workscope.handoff import prepare, verify_packet
from devostasis.workscope.model import ScopeError, default_policy, identity

AT = "2026-10-06T12:00:00Z"
SHA = "a" * 40
NEW = "b" * 40
DATA = b"source bytes\n"
BLOB = hashlib.sha1(b"blob " + str(len(DATA)).encode() + b"\0" + DATA).hexdigest()


class Transport:
    def __init__(self, mutate=None):
        self.calls, self.branches, self.mutate = [], 0, mutate

    def request(self, method, url, headers, body, timeout):
        assert method == "GET" and body is None
        parsed = urlsplit(url); p = unquote(parsed.path); q = parse_qs(parsed.query)
        self.calls.append((p, q))
        if p in ("/api/v4/projects/acme/widget", "/api/v4/projects/123"):
            value = {"id": 123, "default_branch": "main"}
        elif "/repository/branches/" in p:
            self.branches += 1
            value = {"commit": {"id": NEW if self.mutate == "moved" and self.branches > 1 else SHA}}
            if self.mutate == "deleted":
                return 404, {}, b"{}"
        elif "/repository/commits/" in p:
            value = {"id": p.rsplit("/", 1)[1] if p.rsplit("/", 1)[1] in (SHA, NEW) else SHA}
            if self.mutate == "wrong_commit":
                value = {"id": NEW}
        elif p.endswith("/repository/tree"):
            value = [{"path": "src/app.py", "id": BLOB, "type": "blob",
                      "mode": "120000" if self.mutate == "symlink" else "100644"}]
        elif "/repository/files/" in p:
            value = {"file_path": "src/app.py", "encoding": "base64", "size": len(DATA),
                     "content": base64.b64encode(DATA if self.mutate != "wrong_bytes" else b"FORGED bytes\n").decode(),
                     "commit_id": NEW if self.mutate == "wrong_file_revision" else SHA}
        else:
            raise AssertionError(p)
        return 200, {}, canonical_bytes(value)


def fixture(transport=None):
    transport = transport or Transport()
    client = Client("gitlab", "https://gitlab.example/api/v4", transport=transport)
    policy = default_policy("executor")
    policy["requests"] = [{"id": "qualification", "queue": "research", "question": "Qualify the declared source boundary.",
        "paths": ["src/app.py"], "symbols": [], "acceptance": ["Return a pinned qualification result."], "dependencies": [], "owner": None}]
    inv = collect(client, "acme/widget", policy, AT, change_refs=[])
    _, content = build(inv, policy, empty_evidence())
    decoded = verify_content(content)
    return decoded, client, transport


def prepare_packet(decoded, client):
    selected = next(i for i in decoded["scope.json"]["items"] if i["source"] == "request:qualification")
    return prepare(decoded, selected["id"], client, AT, "executor", "example-1", identity(decoded["scope.json"]["subject"]))


def test_real_provider_path_to_bounded_offline_verified_packet():
    decoded, client, transport = fixture()
    packet = prepare_packet(decoded, client)
    assert packet["total_bytes"] == len(DATA) and len(packet["files"]) == 1
    assert base64.b64decode(packet["files"][0]["base64"]) == DATA
    assert not any(p.endswith("/merge_requests") for p, _ in transport.calls)
    assert all(q.get("ref", [SHA])[0] == SHA for _, q in transport.calls)
    assert verify_packet(packet, decoded, AT, "executor", "example-1", identity(decoded["scope.json"]["subject"])) == packet


@pytest.mark.parametrize("failure,reason", [("moved", "SOURCE_MOVED"), ("deleted", "SOURCE_UNAVAILABLE"),
    ("wrong_commit", "SOURCE_COMMIT_NOT_IN_PROJECT"), ("symlink", "SOURCE_LINK_REFUSED"),
    ("wrong_bytes", "SOURCE_BLOB_DIGEST_MISMATCH"), ("wrong_file_revision", "SOURCE_FILE_REVISION_MISMATCH")])
def test_source_races_links_and_wrong_evidence_never_produce_a_packet(failure, reason):
    decoded, client, transport = fixture()
    transport.mutate = failure
    with pytest.raises((ScopeError, ValueError), match=reason):
        prepare_packet(decoded, client)


def test_file_budget_is_checked_before_source_bytes_are_read():
    decoded, client, transport = fixture()
    inv, policy = decoded["inventory.json"], decoded["policy.json"]
    policy["read_budget"]["max_bytes"] = 1
    _, content = build(inv, policy, empty_evidence()); decoded = verify_content(content)
    with pytest.raises(ScopeError, match="READ_BYTE_BUDGET_EXCEEDED"):
        prepare_packet(decoded, client)


@pytest.mark.parametrize("key,value", [("packet_id", "sha256:" + "0" * 64), ("total_bytes", 999),
    ("authority", "merge anything"), ("scope_bundle_id", "another scope")])
def test_offline_handoff_verifier_rejects_tampering(key, value):
    decoded, client, _ = fixture(); packet = prepare_packet(decoded, client)
    packet[key] = value
    if key != "packet_id":
        packet["packet_id"] = digest({k: v for k, v in packet.items() if k != "packet_id"})
    with pytest.raises((ScopeError, ValueError)):
        verify_packet(packet, decoded, AT, "executor", "example-1", identity(decoded["scope.json"]["subject"]))


def test_candidate_requires_named_source_and_validates_commit_membership():
    decoded, _, _ = fixture()
    policy = decoded["policy.json"]
    with pytest.raises(ScopeError, match="named source"):
        collect(Client("gitlab", "https://gitlab.example/api/v4", transport=Transport()), "123", policy, AT,
                context="CANDIDATE", revision=SHA, change_refs=[])
    i = collect(Client("gitlab", "https://gitlab.example/api/v4", transport=Transport()), "123", policy, AT,
                context="CANDIDATE", source_ref="feature", revision=SHA, change_refs=[])
    assert i["subject"]["source_binding"]["kind"] == "BRANCH"


def test_legacy_work_example_still_replays():
    from pathlib import Path
    from devostasis.workscope.bundle import verify
    assert verify(Path(__file__).parents[1] / "examples/legacy/work-v1")["manifest.json"]["contract"] == "devostasis.work.v1"


@pytest.mark.parametrize("provider", ["github", "gitlab"])
def test_fork_change_binding_moves_and_retains_immutable_source_project(provider):
    from devostasis.workscope.binding import resolve, recheck
    host = "https://api.github.com" if provider == "github" else "https://gitlab.example/api/v4"
    target = {"provider": provider, "endpoint": host, "project_id": "123", "locator": "acme/widget" if provider == "github" else "123",
              "context": "CANDIDATE", "revision": SHA}
    class Fork:
        moved = False
        def request(self, method, url, headers, body, timeout):
            p = urlsplit(url).path
            if p.endswith("/pulls/7"):
                value = {"state": "open", "base": {"repo": {"id": 123}},
                         "head": {"sha": NEW if self.moved else SHA, "repo": {"id": 999, "full_name": "fork/widget"}}}
            elif p.endswith("/merge_requests/7"):
                value = {"state": "opened", "target_project_id": 123, "source_project_id": 999,
                         "sha": NEW if self.moved else SHA}
            elif "/commits/" in p:
                value = {"sha" if provider == "github" else "id": p.rsplit("/", 1)[1]}
            else:
                value = {"id": 999 if p.endswith("/999") or p.endswith("/fork/widget") else 123}
            return 200, {}, canonical_bytes(value)
    transport = Fork(); client = Client(provider, host, transport=transport)
    bound = resolve(client, target, "CHANGE", "7")
    assert bound["source_project"]["project_id"] == "999" and bound["project"]["project_id"] == "123"
    target["source_binding"] = bound
    assert recheck(client, target) == bound
    transport.moved = True
    with pytest.raises(ScopeError, match="SOURCE_MOVED"):
        recheck(client, target)
