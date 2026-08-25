from __future__ import annotations

import unittest

import jsonschema

from eml_pmw.relations.contracts import load_relation_contract
from eml_pmw.relations.models_common import PartyEvidencePin
from eml_pmw.relations.models_relation import (
    ContractVersion,
    ExitPath,
    RelationVersion,
    SurvivalClause,
    TerminationTerms,
)
from eml_pmw.relations.policy import ActivationPolicy
from tests.relation_contract_helpers import (
    assert_relation_error,
    mutate_and_rebind,
    valid_activation_policy,
    valid_contract_version,
    valid_exit_path,
    valid_party_pin,
    valid_relation_version,
    valid_survival_clause,
    valid_termination_terms,
)


class RelationContractDomainTests(unittest.TestCase):
    def setUp(self):
        self.policy = ActivationPolicy.from_dict(valid_activation_policy())

    def test_party_pin_is_exact_and_digest_bound(self):
        pin = PartyEvidencePin.from_dict(valid_party_pin())
        self.assertEqual(pin.party_ref, "resident:fixture:a")
        self.assertEqual(pin.adapter_verification_status, "verified")

        unknown = mutate_and_rebind(valid_party_pin(), {"runtime_tag": "runtime:shared"})
        with assert_relation_error(self, "unknown_field"):
            PartyEvidencePin.from_dict(unknown)

    def test_relation_has_no_canonical_reverse_contract_list(self):
        value = mutate_and_rebind(
            valid_relation_version(), {"contract_refs": ["contract:fixture:a"]}
        )
        with assert_relation_error(self, "unknown_field"):
            RelationVersion.from_dict(value)

    def test_descriptive_relation_requires_authority_nonclaim(self):
        valid = mutate_and_rebind(
            valid_relation_version(),
            {"relation_class": "descriptive", "acceptance_rule": "none"},
        )
        self.assertEqual(RelationVersion.from_dict(valid).relation_class, "descriptive")

        invalid = mutate_and_rebind(valid, {"not_claimed": []})
        with assert_relation_error(self, "relation_authority_nonclaim_missing"):
            RelationVersion.from_dict(invalid)

    def test_version_parent_pair_is_consistent(self):
        relation = mutate_and_rebind(
            valid_relation_version(), {"version": 2, "parent_version_digest": None}
        )
        with assert_relation_error(self, "version_parent_invalid"):
            RelationVersion.from_dict(relation)

    def test_contract_requires_exact_relation_pair(self):
        value = mutate_and_rebind(
            valid_contract_version(), {"relation_version_digest": None}
        )
        with assert_relation_error(self, "relation_version_pin_incomplete"):
            ContractVersion.from_dict(value, policy=self.policy)

    def test_contract_requires_exact_activation_policy_digest(self):
        value = mutate_and_rebind(
            valid_contract_version(), {"activation_policy_digest": "sha256:" + "f" * 64}
        )
        with assert_relation_error(self, "activation_policy_digest_mismatch"):
            ContractVersion.from_dict(value, policy=self.policy)

    def test_version_one_boundaries_are_semantic_not_digest_failures(self):
        cases = (
            ("economic_terms_ref", "contract:economics:1"),
            ("residence_impact", "migration-required"),
            ("continuity_impact", "continuity-destructive"),
            ("revocable", False),
            ("redelegable", True),
            ("risk_ceiling", "R2"),
        )
        for field, invalid in cases:
            with self.subTest(field=field):
                value = mutate_and_rebind(valid_contract_version(), {field: invalid})
                with assert_relation_error(self, "contract_v1_boundary_invalid"):
                    ContractVersion.from_dict(value, policy=self.policy)

    def test_every_standing_party_has_bounded_unilateral_exit(self):
        missing = mutate_and_rebind(valid_contract_version(), {"exit_paths": []})
        with assert_relation_error(self, "activation_exit_missing"):
            ContractVersion.from_dict(missing, policy=self.policy)

        too_long = valid_exit_path(
            "resident:fixture:a", notice_duration_ms=self.policy.max_exit_notice_ms + 1
        )
        value = mutate_and_rebind(
            valid_contract_version(),
            {"exit_paths": [too_long, valid_exit_path("resident:fixture:b")]},
        )
        with assert_relation_error(self, "activation_exit_missing"):
            ContractVersion.from_dict(value, policy=self.policy)

    def test_survival_clause_cannot_preserve_future_authority(self):
        value = mutate_and_rebind(valid_survival_clause(), {"future_authority": True})
        with assert_relation_error(self, "survival_future_authority_forbidden"):
            SurvivalClause.from_dict(value)

    def test_contract_positive_control_round_trips(self):
        contract = ContractVersion.from_dict(valid_contract_version(), policy=self.policy)
        self.assertEqual(contract.to_dict(), valid_contract_version())
        self.assertEqual(len(contract.exit_paths), 2)

    def test_packaged_domain_schemas_meta_validate_and_accept_controls(self):
        controls = {
            "party-evidence-pin-v1.schema.json": valid_party_pin(),
            "relation-version-v1.schema.json": valid_relation_version(),
            "exit-path-v1.schema.json": valid_exit_path(),
            "survival-clause-v1.schema.json": valid_survival_clause(),
            "termination-terms-v1.schema.json": valid_termination_terms(),
            "contract-version-v1.schema.json": valid_contract_version(),
        }
        for name, value in controls.items():
            with self.subTest(name=name):
                schema = load_relation_contract(name)
                jsonschema.Draft202012Validator.check_schema(schema)
                jsonschema.validate(value, schema)

    def test_nested_models_reject_unknown_fields(self):
        checks = (
            (ExitPath, mutate_and_rebind(valid_exit_path(), {"unknown": True})),
            (TerminationTerms, mutate_and_rebind(valid_termination_terms(), {"unknown": True})),
        )
        for model, value in checks:
            with self.subTest(model=model.__name__):
                with assert_relation_error(self, "unknown_field"):
                    model.from_dict(value)


if __name__ == "__main__":
    unittest.main()
