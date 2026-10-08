"""Public closed successor schemas agree with the runtime-written shapes."""
import json
from pathlib import Path

from devostasis.bundle import MANIFEST_V2_FIELDS, _PREIMAGE_V3
from devostasis.observations import validate_receipt_identity

ROOT = Path(__file__).parents[1]


def test_successor_public_schemas_bind_exact_runtime_shapes():
    manifest = json.loads((ROOT / "schemas/manifest.v2.schema.json").read_text())
    assert set(manifest["required"]) == set(manifest["properties"]) == MANIFEST_V2_FIELDS
    assert manifest["additionalProperties"] is False
    preimage = manifest["properties"]["identity_preimage"]
    assert set(preimage["required"]) == set(preimage["properties"]) == set(_PREIMAGE_V3)
    assert preimage["additionalProperties"] is False
    example = json.loads((ROOT / "examples/sample-bundle/manifest.json").read_text())
    assert set(example) == MANIFEST_V2_FIELDS
    assert validate_receipt_identity(example["receipt_identity"]) == example["receipt_identity"]
    receipt = json.loads((ROOT / "schemas/receipt-identity.schema.json").read_text())
    assert set(receipt["required"]) == set(receipt["properties"]) == set(example["receipt_identity"])
    assert receipt["additionalProperties"] is False
