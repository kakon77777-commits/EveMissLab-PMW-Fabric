from __future__ import annotations

from copy import deepcopy
import unittest

import jsonschema

from eml_pmw.relations.canonical import object_content_digest, profile_digest
from eml_pmw.relations.policy import ActivationPolicy
from eml_pmw.relations.references import validate_portable_ref
from eml_pmw.relations.temporal import NormalizedInstantEvidence, compare_instants
from eml_pmw.relations.contracts import load_relation_contract
from tests.relation_contract_helpers import (
    assert_relation_error,
    mutate_and_rebind,
    normalized_instant,
    valid_activation_policy,
)


class RelationContractCoreTests(unittest.TestCase):
    def test_profile_digest_is_domain_and_version_bound(self):
        value = {"schema": "fixture/v1", "ref": "entity:fixture:a"}
        expected = (
            "sha256:arcp-relation-contract-json-nfc-codepoint-v1:"
            "a8e75e33a4e7bd3f47d5e88e8cf7a0a23af6f6e499b7d18ac7e5bfb8527c8d1b"
        )

        self.assertEqual(profile_digest(value), expected)

    def test_object_digest_omits_its_own_field(self):
        value = {"schema": "fixture/v1", "ref": "entity:fixture:a", "content_digest": "wrong"}
        self.assertEqual(
            object_content_digest(value),
            profile_digest({"schema": "fixture/v1", "ref": "entity:fixture:a"}),
        )

    def test_portable_reference_rejects_host_paths(self):
        invalid = (
            r"C:\Users\fixture\item.json",
            r"\\host\share\item.json",
            "/var/lib/fixture/item.json",
            "file:///tmp/item.json",
            "package.module:ClassName",
        )
        for value in invalid:
            with self.subTest(value=value):
                with assert_relation_error(self, "portable_ref_invalid"):
                    validate_portable_ref(value, "resolver_source_ref")

        self.assertEqual(
            validate_portable_ref("resident:fixture:a", "party_ref"),
            "resident:fixture:a",
        )

    def test_uncertainty_intervals_compare_without_forging_order(self):
        before = NormalizedInstantEvidence.from_dict(normalized_instant("900", 10))
        left = NormalizedInstantEvidence.from_dict(normalized_instant("1000", 20))
        right = NormalizedInstantEvidence.from_dict(normalized_instant("1030", 20))
        equal = NormalizedInstantEvidence.from_dict(normalized_instant("1000", 20))

        self.assertEqual(compare_instants(before, left), "before")
        self.assertEqual(compare_instants(left, before), "after")
        self.assertEqual(compare_instants(left, right), "overlap")
        self.assertEqual(compare_instants(left, equal), "equal")

    def test_normalized_instant_rejects_unmeasured_or_invalid_numbers(self):
        with assert_relation_error(self, "normalized_instant_invalid"):
            NormalizedInstantEvidence.from_dict(normalized_instant(uncertainty_ns=-1))
        with assert_relation_error(self, "normalized_instant_invalid"):
            NormalizedInstantEvidence.from_dict(normalized_instant(uncertainty_ns=True))
        unmeasured = NormalizedInstantEvidence.from_dict(
            normalized_instant(verification_status="unmeasured")
        )
        with assert_relation_error(self, "temporal_evidence_insufficient"):
            compare_instants(unmeasured, NormalizedInstantEvidence.from_dict(normalized_instant()))

    def test_activation_policy_rejects_r2_and_unbounded_values(self):
        cases = (
            ({"max_risk": "R2"}, "activation_policy_invalid"),
            ({"max_activation_duration_ms": 0}, "activation_policy_invalid"),
            ({"allowed_evaluator_profiles": []}, "activation_policy_invalid"),
            ({"allow_redelegation": True}, "activation_policy_invalid"),
        )
        for updates, code in cases:
            with self.subTest(updates=updates):
                value = mutate_and_rebind(valid_activation_policy(), updates)
                with assert_relation_error(self, code):
                    ActivationPolicy.from_dict(value)

    def test_stale_content_digest_is_distinct_from_semantic_rejection(self):
        stale = deepcopy(valid_activation_policy())
        stale["max_exit_notice_ms"] += 1
        with assert_relation_error(self, "content_digest_mismatch"):
            ActivationPolicy.from_dict(stale)

    def test_packaged_core_schemas_meta_validate_and_accept_controls(self):
        controls = {
            "normalized-instant-evidence-v1.schema.json": normalized_instant(),
            "activation-policy-v1.schema.json": valid_activation_policy(),
        }
        for name, value in controls.items():
            with self.subTest(name=name):
                schema = load_relation_contract(name)
                jsonschema.Draft202012Validator.check_schema(schema)
                jsonschema.validate(value, schema)


if __name__ == "__main__":
    unittest.main()
