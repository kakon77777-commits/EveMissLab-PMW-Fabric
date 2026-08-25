from __future__ import annotations

from pathlib import Path
import sys
import unittest

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.federation.models import FederatedEvent, FederationConfig
from eml_pmw.integration.contracts import load_local_contract
from tests.federation_helpers import assert_error_code, valid_config, valid_event


class FederationContractTests(unittest.TestCase):
    def test_event_core_digest_binds_causal_and_authority_fields(self):
        first = FederatedEvent.from_dict(valid_event())
        changed = FederatedEvent.from_dict({**valid_event(), "authority_ref": "authority:other"})
        parented = FederatedEvent.from_dict({**valid_event(), "causal_parents": ["event:parent"]})
        self.assertNotEqual(first.core_digest, changed.core_digest)
        self.assertNotEqual(first.core_digest, parented.core_digest)

    def test_delivery_and_host_fields_are_rejected(self):
        for field in ("delivery_id", "pane_id", "runtime_tag"):
            with self.subTest(field=field):
                with assert_error_code(self, "unknown_field"):
                    FederatedEvent.from_dict({**valid_event(), field: "forbidden"})

    def test_registered_time_requires_ctcl_reference(self):
        value = {**valid_event(), "created_time_ref": None, "temporal_evidence_status": "registered_anchor"}
        with assert_error_code(self, "temporal_evidence_mismatch"):
            FederatedEvent.from_dict(value)

    def test_config_requires_authority_kinds_to_be_allowed(self):
        self.assertEqual(FederationConfig.from_dict(valid_config()).local_realm_id, "realm:a")
        with assert_error_code(self, "authority_event_kind_not_allowed"):
            FederationConfig.from_dict(valid_config(authority_required_event_kinds=["pmw.unknown"]))

    def test_event_realm_and_replica_must_match(self):
        replica = {**valid_event()["replica_ref"], "realm_id": "realm:b"}
        with assert_error_code(self, "event_realm_replica_mismatch"):
            FederatedEvent.from_dict(valid_event(replica_ref=replica))

    def test_packaged_schemas_meta_validate_and_accept_controls(self):
        event_schema = load_local_contract("federated-event-v1.schema.json")
        config_schema = load_local_contract("federation-config-v1.schema.json")
        jsonschema.Draft202012Validator.check_schema(event_schema)
        jsonschema.Draft202012Validator.check_schema(config_schema)
        jsonschema.validate(valid_event(), event_schema)
        jsonschema.validate(valid_config(), config_schema)


if __name__ == "__main__":
    unittest.main()
