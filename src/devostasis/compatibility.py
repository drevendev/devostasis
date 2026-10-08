"""Exact-token, operation-scoped compatibility (PV-COMPAT-001/002).

Source validation always precedes compatibility. Production has no accepted
nonidentity edges; callers may install explicitly versioned local contracts.
Policies pin their entire finite edge set, so registry growth cannot change replay.
"""

from copy import deepcopy
from dataclasses import dataclass

from .canonical import canonical_bytes, digest

CONTRACT = "devostasis.contract-compatibility.v1"
POLICY_CONTRACT = "devostasis.compatibility-dispatch-policy.v1"
SELECTION = "EXACT_UNIQUE_OR_AMBIGUOUS.v1"
OPERATIONS = frozenset({"READ", "VERIFY_CURRENT", "COMPARE", "PROJECT", "RENDER_INPUT"})


class CompatibilityError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise CompatibilityError(message)


def lineage(value):
    require(isinstance(value, dict) and value and all(isinstance(k, str) and k and
            isinstance(v, str) and v for k, v in value.items()), "LINEAGE_INVALID")
    return digest(value)


@dataclass(frozen=True)
class Edge:
    body: dict
    body_digest: str
    precondition: object
    projection: object


class Registry:
    def __init__(self):
        self.validators, self.edges, self.policies = {}, {}, {}

    def register_lineage(self, ref, validator):
        key = lineage(ref)
        require(key not in self.validators, "LINEAGE_IDENTITY_COLLISION")
        self.validators[key] = (deepcopy(ref), validator)

    def validate(self, ref, value):
        key = lineage(ref)
        require(key in self.validators, "LINEAGE_MISMATCH")
        # Validate the source without a projection, current policy or target registry.
        result = self.validators[key][1](deepcopy(value))
        require(result is True, "SOURCE_SCHEMA_INVALID")

    def register_edge(self, body, precondition, projection):
        fields = {"edge_id", "edge_version", "source_lineage", "target_lineage", "operations",
                  "precondition_algorithm", "projection_algorithm", "unknown_field_policy",
                  "semantic_invariance", "comparison_compatible", "canonical_identity_effect"}
        require(isinstance(body, dict) and set(body) == fields, "EDGE_SCHEMA_INVALID")
        require(all(isinstance(body[k], str) and body[k] for k in
                    ("edge_id", "edge_version", "precondition_algorithm", "projection_algorithm")), "EDGE_SCHEMA_INVALID")
        lineage(body["source_lineage"]); lineage(body["target_lineage"])
        require(body["source_lineage"] != body["target_lineage"], "EXACT_IDENTITY_CANNOT_BE_SHADOWED")
        require(isinstance(body["operations"], list) and body["operations"] and
                all(isinstance(op, str) and op in OPERATIONS for op in body["operations"]) and
                len(set(body["operations"])) == len(body["operations"]), "EDGE_OPERATION_INVALID")
        require(body["canonical_identity_effect"] == "NONE" and
                type(body["semantic_invariance"]) is bool and type(body["comparison_compatible"]) is bool and
                body["unknown_field_policy"] in ("REJECT", "EXPLICIT_EXTENSION"), "EDGE_SCHEMA_INVALID")
        key = (body["edge_id"], body["edge_version"])
        require(key not in self.edges, "EDGE_IDENTITY_COLLISION")
        self.edges[key] = Edge(deepcopy(body), digest(body), precondition, projection)

    def register_policy(self, policy_id, policy_version, eligible_edges):
        require(isinstance(policy_id, str) and policy_id and isinstance(policy_version, str) and policy_version,
                "POLICY_SCHEMA_INVALID")
        require(isinstance(eligible_edges, list), "POLICY_SCHEMA_INVALID")
        for ref in eligible_edges:
            require(isinstance(ref, dict) and set(ref) == {"edge_id", "edge_version"} and
                    all(isinstance(v, str) and v for v in ref.values()), "POLICY_SCHEMA_INVALID")
        ordered = sorted(deepcopy(eligible_edges), key=canonical_bytes)
        require(len({digest(e) for e in ordered}) == len(ordered), "POLICY_DUPLICATE_EDGE")
        body = {"policy_contract": POLICY_CONTRACT, "policy_id": policy_id, "policy_version": policy_version,
                "eligible_edges": ordered, "selection_rule": SELECTION}
        key = (policy_id, policy_version)
        require(key not in self.policies or self.policies[key] == body, "POLICY_IDENTITY_COLLISION")
        self.policies[key] = body
        return {k: body[k] for k in ("policy_contract", "policy_id", "policy_version")} | {"policy_digest": digest(body)}

    def policy(self, ref):
        require(isinstance(ref, dict) and set(ref) == {"policy_contract", "policy_id", "policy_version", "policy_digest"},
                "POLICY_REFERENCE_INVALID")
        require(ref["policy_contract"] == POLICY_CONTRACT, "POLICY_REFERENCE_INVALID")
        body = self.policies.get((ref["policy_id"], ref["policy_version"]))
        require(body is not None and digest(body) == ref["policy_digest"], "RECORDED_POLICY_UNAVAILABLE_OR_CHANGED")
        edges = []
        for item in body["eligible_edges"]:
            edge = self.edges.get((item["edge_id"], item["edge_version"]))
            require(edge is not None, "RECORDED_EDGE_UNAVAILABLE")
            require(digest(edge.body) == edge.body_digest and all(edge.body[k] == item[k] for k in item),
                    "EDGE_IDENTITY_COLLISION")
            edges.append(edge)
        return edges

    def dispatch(self, source, target, operation, value, policy_ref=None):
        self.validate(source, value)
        require(operation in OPERATIONS, "OPERATION_UNSUPPORTED")
        lineage(target)
        provenance = {"contract": CONTRACT, "source_lineage": deepcopy(source), "target_lineage": deepcopy(target),
                      "operation": operation, "dispatch_policy": None, "selected_edge": None,
                      "result_lineage": deepcopy(target)}
        if source == target:
            return provenance | {"status": "EXACT_IDENTITY", "result": deepcopy(value)}
        require(policy_ref is not None, "NO_DECLARED_COMPATIBILITY")
        candidates = []
        for edge in self.policy(policy_ref):
            b = edge.body
            if b["source_lineage"] == source and b["target_lineage"] == target and operation in b["operations"]:
                if operation == "COMPARE" and not (b["semantic_invariance"] and b["comparison_compatible"]):
                    continue
                if edge.precondition(deepcopy(value)) is True:
                    candidates.append(edge)
        require(candidates, "NO_DECLARED_COMPATIBILITY")
        require(len(candidates) == 1, "AMBIGUOUS_COMPATIBILITY_EDGE")
        edge = candidates[0]
        result = edge.projection(deepcopy(value))
        self.validate(target, result)
        provenance["dispatch_policy"] = deepcopy(policy_ref)
        provenance["selected_edge"] = {k: edge.body[k] for k in ("edge_id", "edge_version")}
        return provenance | {"status": "DECLARED_COMPATIBILITY", "result": result}

    def replay(self, record, value):
        expected = self.dispatch(record["source_lineage"], record["target_lineage"], record["operation"],
                                 value, record["dispatch_policy"])
        require(expected == record, "COMPATIBILITY_REPLAY_MISMATCH")
        return expected
