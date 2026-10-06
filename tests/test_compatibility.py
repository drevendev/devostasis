"""Exact source admission and immutable dispatch policy, including COMPAT-21/22."""

from copy import deepcopy

import pytest

from devostasis.compatibility import CompatibilityError, Registry

A, B, C = ({"envelope": x, "payload": "payload.v1"} for x in ("envelope.v1", "envelope.v2", "envelope.v3"))


def registry():
    r = Registry()
    for ref in (A, B, C):
        r.register_lineage(ref, lambda value: isinstance(value, dict) and set(value) == {"count"} and type(value["count"]) is int)
    return r


def edge(r, name="representation", source=A, target=B, precondition=lambda v: True, operations=None):
    body = {"edge_id": name, "edge_version": "opaque-a", "source_lineage": source, "target_lineage": target,
            "operations": operations or ["READ"], "precondition_algorithm": "local.test.v1",
            "projection_algorithm": "local.identity.v1", "unknown_field_policy": "REJECT",
            "semantic_invariance": True, "comparison_compatible": False, "canonical_identity_effect": "NONE"}
    r.register_edge(body, precondition, deepcopy)
    return {"edge_id": name, "edge_version": "opaque-a"}


def test_exact_identity_precedes_edges_but_not_source_validation():
    r = registry()
    assert r.dispatch(A, A, "READ", {"count": 0}, {"invalid": "ignored"})["status"] == "EXACT_IDENTITY"
    with pytest.raises(CompatibilityError, match="SOURCE_SCHEMA_INVALID"):
        r.dispatch(A, A, "READ", {"count": 0, "unexpected": 7})


@pytest.mark.parametrize("ref", [{"envelope": "envelope.v999", "payload": "payload.v1"},
                                {"envelope": "envelope.v0", "payload": "payload.v1"},
                                {"envelope": "envelope.v1.0", "payload": "payload.v1"},
                                {"envelope": "envelope.v1", "payload": "payload.v2"}])
def test_unknown_versions_and_mixed_tuples_never_use_shape_fallback(ref):
    r = registry()
    with pytest.raises(CompatibilityError, match="LINEAGE_MISMATCH"):
        r.dispatch(ref, A, "READ", {"count": 0})


def test_source_validation_precedes_projection_and_no_version_means_no_success():
    r = registry(); ref = edge(r); p = r.register_policy("local", "one", [ref])
    for value in ({"count": False}, {}, {"count": None}):
        with pytest.raises(CompatibilityError, match="SOURCE_SCHEMA_INVALID"):
            r.dispatch(A, B, "READ", value, p)


def test_compatibility_is_asymmetric_nontransitive_and_operation_scoped():
    r = registry(); a = edge(r); b = edge(r, "next", B, C); p = r.register_policy("local", "one", [a, b])
    assert r.dispatch(A, B, "READ", {"count": 0}, p)["result"] == {"count": 0}
    for source, target, op in ((B, A, "READ"), (A, C, "READ"), (A, B, "COMPARE"), (A, B, "PROJECT")):
        with pytest.raises(CompatibilityError, match="NO_DECLARED_COMPATIBILITY"):
            r.dispatch(source, target, op, {"count": 0}, p)


@pytest.mark.parametrize("truth", [False, None, "UNKNOWN", 1])
def test_only_literal_true_preconditions_admit_an_edge(truth):
    r = registry(); ref = edge(r, precondition=lambda v: truth); p = r.register_policy("local", "one", [ref])
    with pytest.raises(CompatibilityError, match="NO_DECLARED_COMPATIBILITY"):
        r.dispatch(A, B, "READ", {"count": 1}, p)


def test_compat_21_recorded_policy_pins_registry_growth_and_replay():
    r = registry(); ref = edge(r); p = r.register_policy("local", "one", [ref])
    record = r.dispatch(A, B, "READ", {"count": 7}, p)
    other = edge(r, "newer equivalent")
    r.register_policy("local", "two", [ref, other])
    assert r.replay(record, {"count": 7}) == record
    for key in ("policy_digest", "policy_version"):
        bad = deepcopy(record); bad["dispatch_policy"][key] = "unavailable"
        with pytest.raises(CompatibilityError, match="RECORDED_POLICY_UNAVAILABLE_OR_CHANGED"):
            r.replay(bad, {"count": 7})
    r.edges.pop((ref["edge_id"], ref["edge_version"]))
    with pytest.raises(CompatibilityError, match="RECORDED_EDGE_UNAVAILABLE"):
        r.replay(record, {"count": 7})


def test_compat_22_ambiguous_edges_do_not_admit_byte_equal_outputs():
    r = registry(); a, b = edge(r), edge(r, "other")
    p = r.register_policy("local", "one", [a, b])
    assert r.register_policy("local", "one", [b, a]) == p
    with pytest.raises(CompatibilityError, match="AMBIGUOUS_COMPATIBILITY_EDGE"):
        r.dispatch(A, B, "READ", {"count": 0}, p)


def test_immutable_registry_identities_cannot_be_replaced():
    r = registry(); a = edge(r); r.register_policy("local", "one", [a])
    with pytest.raises(CompatibilityError, match="EDGE_IDENTITY_COLLISION"):
        edge(r)
    with pytest.raises(CompatibilityError, match="POLICY_IDENTITY_COLLISION"):
        r.register_policy("local", "one", [])
    with pytest.raises(CompatibilityError, match="LINEAGE_IDENTITY_COLLISION"):
        r.register_lineage(A, lambda value: True)


def test_changed_registered_edge_body_cannot_reuse_its_identity():
    r = registry(); a = edge(r); p = r.register_policy("local", "one", [a])
    record = r.dispatch(A, B, "READ", {"count": 1}, p)
    r.edges[(a["edge_id"], a["edge_version"])].body["projection_algorithm"] = "changed.v2"
    with pytest.raises(CompatibilityError, match="EDGE_IDENTITY_COLLISION"):
        r.replay(record, {"count": 1})


def test_replay_binds_result_lineage_selected_edge_and_exact_result():
    r = registry(); a = edge(r); p = r.register_policy("local", "one", [a])
    record = r.dispatch(A, B, "READ", {"count": 7}, p)
    for key, value in (("result", {"count": 8}), ("result_lineage", C), ("selected_edge", a | {"edge_version": "latest"})):
        bad = deepcopy(record); bad[key] = value
        with pytest.raises(CompatibilityError, match="COMPATIBILITY_REPLAY_MISMATCH"):
            r.replay(bad, {"count": 7})
