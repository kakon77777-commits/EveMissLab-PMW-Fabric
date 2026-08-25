from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.integration.errors import IntegrationContractError
from eml_pmw.integration.references import ParticipantBindingV1, parse_arcp_agent_id


VALID = {
    "schema": "pmw-participant-binding/v1",
    "bindingId": "participant:fixture-agent",
    "pmwWorkspaceId": "pmw-workspace-fixture-1",
    "displayLabel": "Example Agent",
    "entityRef": {
        "value": "arcp:agent:example:11111111-1111-4111-8111-111111111111",
        "identifierKind": "arcp_agent",
        "issuer": "arcp://example",
        "verificationStatus": "verified",
        "evidenceRefs": ["ral:attestation:fixture-1"],
    },
    "instanceRef": {
        "value": "thread-fixture-0001",
        "identifierKind": "codex_thread",
        "issuer": "test-host",
        "verificationStatus": "observed",
        "evidenceRefs": ["host-observation:fixture-1"],
    },
    "providerPrincipalRef": None,
}


class ParticipantReferenceTests(unittest.TestCase):
    def test_valid_binding_keeps_entity_and_instance_separate(self):
        binding = ParticipantBindingV1.from_dict(VALID)
        self.assertEqual(binding.entity_ref.identifier_kind, "arcp_agent")
        self.assertEqual(binding.instance_ref.identifier_kind, "codex_thread")
        self.assertEqual(
            parse_arcp_agent_id(binding.entity_ref.value),
            ("example", "11111111-1111-4111-8111-111111111111"),
        )

    def test_runtime_tag_cannot_become_entity_reference(self):
        value = deepcopy(VALID)
        value["entityRef"]["identifierKind"] = "runtime_tag"
        with self.assertRaises(IntegrationContractError) as caught:
            ParticipantBindingV1.from_dict(value)
        self.assertEqual(caught.exception.code, "forbidden_entity_identifier_kind")

    def test_verified_reference_requires_evidence(self):
        value = deepcopy(VALID)
        value["entityRef"]["evidenceRefs"] = []
        with self.assertRaises(IntegrationContractError) as caught:
            ParticipantBindingV1.from_dict(value)
        self.assertEqual(caught.exception.code, "participant_binding_schema_invalid")

    def test_observed_instance_requires_observation_evidence(self):
        value = deepcopy(VALID)
        value["instanceRef"]["evidenceRefs"] = []
        with self.assertRaises(IntegrationContractError) as caught:
            ParticipantBindingV1.from_dict(value)
        self.assertEqual(caught.exception.code, "participant_binding_schema_invalid")

    def test_display_label_is_never_used_as_reference(self):
        binding = ParticipantBindingV1.from_dict(VALID)
        self.assertNotEqual(binding.display_label, binding.entity_ref.value)
        self.assertNotEqual(binding.display_label, binding.instance_ref.value)

    def test_arcp_agent_identifier_requires_real_uuid_shape(self):
        value = deepcopy(VALID)
        value["entityRef"]["value"] = "arcp:agent:example:------------------------------------"
        with self.assertRaises(IntegrationContractError) as caught:
            ParticipantBindingV1.from_dict(value)
        self.assertEqual(caught.exception.code, "invalid_arcp_agent_id")


if __name__ == "__main__":
    unittest.main()
