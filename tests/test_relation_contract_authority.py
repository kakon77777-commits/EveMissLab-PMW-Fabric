from __future__ import annotations

import unittest

import jsonschema

from eml_pmw.relations.authority import ral_pin_sufficient, validate_grant_authority
from eml_pmw.relations.contracts import load_relation_contract
from eml_pmw.relations.models_authority import (
    GrantAuthorityEvidence,
    PartyAcceptance,
    RepresentationGrant,
)
from eml_pmw.relations.models_common import PartyEvidencePin
from tests.relation_contract_helpers import (
    assert_relation_error,
    mutate_and_rebind,
    valid_contract_version,
    valid_grant_authority_evidence,
    valid_party_acceptance,
    valid_party_pin,
    valid_representation_grant,
)


class RelationContractAuthorityTests(unittest.TestCase):
    def test_grant_authority_rejects_self_cycle(self):
        value = mutate_and_rebind(
            valid_grant_authority_evidence(),
            {
                "grant_authority_evidence_id": "grant-authority-evidence:cycle:a",
                "dependency_refs": ["grant-authority-evidence:cycle:a"],
            },
        )
        root = GrantAuthorityEvidence.from_dict(value)
        with assert_relation_error(self, "representation_authority_circular"):
            validate_grant_authority(
                root.grant_authority_evidence_id,
                {root.grant_authority_evidence_id: root},
                set(),
                set(),
            )

    def test_contract_cannot_bootstrap_its_own_representation(self):
        root = GrantAuthorityEvidence.from_dict(
            mutate_and_rebind(
                valid_grant_authority_evidence(),
                {"authority_source_ref": "contract:fixture:collaboration"},
            )
        )
        with assert_relation_error(self, "representation_authority_descendant"):
            validate_grant_authority(
                root.grant_authority_evidence_id,
                {root.grant_authority_evidence_id: root},
                {"contract:fixture:collaboration"},
                {valid_contract_version()["content_digest"]},
            )

    def test_missing_grant_dependency_is_distinct_from_cycle(self):
        root = GrantAuthorityEvidence.from_dict(
            mutate_and_rebind(
                valid_grant_authority_evidence(),
                {"dependency_refs": ["grant-authority-evidence:missing"]},
            )
        )
        with assert_relation_error(self, "representation_authority_missing"):
            validate_grant_authority(
                root.grant_authority_evidence_id,
                {root.grant_authority_evidence_id: root},
                set(),
                set(),
            )

    def test_acyclic_grant_returns_deterministic_ancestor_order(self):
        parent = GrantAuthorityEvidence.from_dict(
            mutate_and_rebind(
                valid_grant_authority_evidence(),
                {"grant_authority_evidence_id": "grant-authority-evidence:parent"},
            )
        )
        child = GrantAuthorityEvidence.from_dict(
            mutate_and_rebind(
                valid_grant_authority_evidence(),
                {
                    "grant_authority_evidence_id": "grant-authority-evidence:child",
                    "dependency_refs": [parent.grant_authority_evidence_id],
                },
            )
        )
        self.assertEqual(
            validate_grant_authority(
                child.grant_authority_evidence_id,
                {
                    parent.grant_authority_evidence_id: parent,
                    child.grant_authority_evidence_id: child,
                },
                set(),
                set(),
            ),
            (
                "grant-authority-evidence:child",
                "grant-authority-evidence:parent",
            ),
        )

    def test_acceptance_target_kind_is_digest_bound(self):
        accepted = PartyAcceptance.from_dict(valid_party_acceptance(target_kind="relation"))
        self.assertEqual(accepted.target_kind, "relation")

        invalid = mutate_and_rebind(
            valid_party_acceptance(target_kind="contract"),
            {"target_id": "relation:fixture:collaboration"},
        )
        with assert_relation_error(self, "acceptance_target_kind_mismatch"):
            PartyAcceptance.from_dict(invalid)

    def test_acceptance_evidence_roots_cannot_duplicate(self):
        value = mutate_and_rebind(
            valid_party_acceptance(),
            {
                "acceptance_evidence_root_refs": [
                    "evidence-root:acceptance:a",
                    "evidence-root:acceptance:a",
                ]
            },
        )
        with assert_relation_error(self, "field_type_invalid"):
            PartyAcceptance.from_dict(value)

    def test_observed_or_claimed_ral_pin_is_never_sufficient(self):
        for status in ("observed", "claimed", "unmeasured", "rejected"):
            with self.subTest(status=status):
                pin = PartyEvidencePin.from_dict(
                    mutate_and_rebind(
                        valid_party_pin(), {"adapter_verification_status": status}
                    )
                )
                self.assertFalse(
                    ral_pin_sufficient(
                        pin,
                        current_ledger_head="ral-head:fixture:1",
                        current_view_digest="sha256:" + "2" * 64,
                    )
                )

    def test_verified_current_unique_ral_pin_is_sufficient(self):
        pin = PartyEvidencePin.from_dict(valid_party_pin())
        self.assertTrue(
            ral_pin_sufficient(
                pin,
                current_ledger_head="ral-head:fixture:1",
                current_view_digest="sha256:" + "2" * 64,
            )
        )
        advanced = PartyEvidencePin.from_dict(
            mutate_and_rebind(valid_party_pin(), {"state_head_ref": "ral-head:fixture:2"})
        )
        self.assertFalse(
            ral_pin_sufficient(
                advanced,
                current_ledger_head="ral-head:fixture:1",
                current_view_digest="sha256:" + "2" * 64,
            )
        )
        ambiguous = PartyEvidencePin.from_dict(
            mutate_and_rebind(valid_party_pin(), {"binding_ambiguity": True})
        )
        self.assertFalse(
            ral_pin_sufficient(
                ambiguous,
                current_ledger_head="ral-head:fixture:1",
                current_view_digest="sha256:" + "2" * 64,
            )
        )

    def test_representation_is_bounded_and_non_redelegable(self):
        grant = RepresentationGrant.from_dict(valid_representation_grant())
        self.assertFalse(grant.redelegable)
        for updates in (
            {"redelegable": True},
            {"revocable": False},
            {"allowed_lifecycle_actions": []},
        ):
            with self.subTest(updates=updates):
                value = mutate_and_rebind(valid_representation_grant(), updates)
                with assert_relation_error(self, "representation_grant_invalid"):
                    RepresentationGrant.from_dict(value)

    def test_packaged_authority_schemas_meta_validate_and_accept_controls(self):
        controls = {
            "grant-authority-evidence-v1.schema.json": valid_grant_authority_evidence(),
            "representation-grant-v1.schema.json": valid_representation_grant(),
            "party-acceptance-v1.schema.json": valid_party_acceptance(),
        }
        for name, value in controls.items():
            with self.subTest(name=name):
                schema = load_relation_contract(name)
                jsonschema.Draft202012Validator.check_schema(schema)
                jsonschema.validate(value, schema)


if __name__ == "__main__":
    unittest.main()
