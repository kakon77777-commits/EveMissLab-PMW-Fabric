from __future__ import annotations

from dataclasses import replace
import unittest

import jsonschema

from eml_pmw.relations.activation import (
    ActivationInputs,
    build_authority_candidate,
    evaluate_activation,
    receipt_is_current,
)
from eml_pmw.relations.contracts import load_relation_contract
from eml_pmw.relations.models_authority import (
    AuthorityCandidate,
    AuthorityEvaluationReceipt,
    CommitmentRecord,
    GrantAuthorityEvidence,
    PartyAcceptance,
    RepresentationGrant,
)
from eml_pmw.relations.models_common import PartyEvidencePin
from eml_pmw.relations.models_relation import ContractVersion
from eml_pmw.relations.policy import ActivationPolicy
from eml_pmw.relations.reducer import reduce_events
from eml_pmw.relations.events import RelationContractEvent
from eml_pmw.relations.temporal import NormalizedInstantEvidence
from tests.relation_contract_helpers import (
    assert_relation_error,
    mutate_and_rebind,
    normalized_instant,
    valid_action_intent,
    valid_activation_policy,
    valid_authority_candidate,
    valid_authority_resolution,
    valid_commitment,
    valid_contract_version,
    valid_evaluation_receipt,
    valid_grant_authority_evidence,
    valid_party_acceptance,
    valid_party_pin,
    valid_representation_grant,
)
from test_relation_contract_lifecycle import active_v1_sequence


def current_inputs(*, evaluator_policy_version="policy:fixture:v1", now=None):
    contract_value, _, events, objects = active_v1_sequence()
    projection = reduce_events(
        [RelationContractEvent.from_dict(item) for item in events], objects
    )
    contract = ContractVersion.from_dict(
        contract_value, policy=ActivationPolicy.from_dict(valid_activation_policy())
    )
    acceptances = tuple(
        PartyAcceptance.from_dict(value)
        for value in objects.values()
        if value.get("schema") == "arcp/party-acceptance/0.1"
    )
    pins = tuple(
        PartyEvidencePin.from_dict(valid_party_pin(party)) for party in ("a", "b")
    )
    grants = tuple(
        RepresentationGrant.from_dict(valid_representation_grant(party))
        for party in ("a", "b")
    )
    authorities = {
        item.grant_authority_evidence_id: item
        for item in (
            GrantAuthorityEvidence.from_dict(valid_grant_authority_evidence("a")),
            GrantAuthorityEvidence.from_dict(valid_grant_authority_evidence("b")),
        )
    }
    return ActivationInputs(
        contract=contract,
        lifecycle_projection=projection,
        acceptances=acceptances,
        party_pins=pins,
        current_ledger_heads={
            "resident:fixture:a": "ral-head:fixture:1",
            "resident:fixture:b": "ral-head:fixture:1",
        },
        current_view_digests={
            "resident:fixture:a": "sha256:" + "2" * 64,
            "resident:fixture:b": "sha256:" + "2" * 64,
        },
        representation_grants=grants,
        grant_authority_evidence=authorities,
        action_intent=valid_action_intent(),
        now=NormalizedInstantEvidence.from_dict(
            now or normalized_instant("1500000000", 0)
        ),
        policy=ActivationPolicy.from_dict(valid_activation_policy()),
        evaluator_profile_id="arcp-evaluator:fixture:v1",
        evaluator_policy_version=evaluator_policy_version,
        transition_authority_actions=("contract.activated",),
    )


def receipt_for_candidate(candidate):
    resolution = valid_authority_resolution(
        run_id=candidate.run_ref,
        action_id=candidate.action_intent_ref,
        action_hash=candidate.action_intent_digest,
        subject_entity_ref=candidate.subject_entity_ref,
        resource_scope=list(candidate.requested_resource_scope),
        relation_refs=list(candidate.relation_refs),
        contract_refs=[candidate.contract_ref],
        expires_at=candidate.expires_at.to_dict(),
    )
    value = mutate_and_rebind(
        valid_evaluation_receipt(),
        {
            "candidate_ref": candidate.candidate_id,
            "candidate_digest": candidate.content_digest,
            "evaluator_profile_id": candidate.evaluator_profile_id,
            "evaluator_policy_version": candidate.evaluator_policy_version,
            "evaluated_evidence_set_digest": candidate.party_evidence_set_digest,
            "authority_resolution": resolution,
        },
        digest_field="receipt_digest",
    )
    return AuthorityEvaluationReceipt.from_dict(value)


class RelationContractActivationTests(unittest.TestCase):
    def test_transition_authority_does_not_cover_candidate_action_scope(self):
        inputs = current_inputs()
        decision = evaluate_activation(inputs)
        self.assertEqual(decision.status, "eligible")
        candidate = build_authority_candidate(inputs, decision)

        self.assertEqual(candidate.requested_action_scope, ("workspace.inspect",))
        self.assertEqual(inputs.transition_authority_actions, ("contract.activated",))
        self.assertNotIn("workspace.inspect", inputs.transition_authority_actions)

    def test_expiry_overlap_is_indeterminate(self):
        inputs = current_inputs(now=normalized_instant("2000000000", 20))
        decision = evaluate_activation(inputs)
        self.assertEqual(decision.status, "indeterminate")
        self.assertIn("activation_time_indeterminate", decision.reason_codes)

    def test_missing_or_stale_party_pin_blocks_candidate(self):
        inputs = current_inputs()
        stale_pin = PartyEvidencePin.from_dict(
            mutate_and_rebind(inputs.party_pins[0].to_dict(), {"state_head_ref": "ral-head:fixture:2"})
        )
        decision = evaluate_activation(
            replace(inputs, party_pins=(stale_pin, inputs.party_pins[1]))
        )
        self.assertEqual(decision.status, "blocked")
        self.assertIn("party_binding_inactive", decision.reason_codes)

    def test_commitment_is_versioned_and_has_no_execution_claim(self):
        item = CommitmentRecord.from_dict(valid_commitment(execution_refs=[]))
        self.assertEqual(item.version, 1)
        self.assertEqual(item.execution_refs, ())

    def test_old_receipt_is_historical_after_policy_or_head_advance(self):
        inputs = current_inputs()
        candidate = build_authority_candidate(inputs, evaluate_activation(inputs))
        receipt = receipt_for_candidate(candidate)
        current = receipt_is_current(receipt, inputs=inputs)
        self.assertTrue(current.current)

        policy_changed = receipt_is_current(
            receipt,
            inputs=replace(inputs, evaluator_policy_version="policy:fixture:v2"),
        )
        self.assertFalse(policy_changed.current)
        self.assertEqual(policy_changed.reason_code, "authority_resolution_stale")

        advanced_pin = PartyEvidencePin.from_dict(
            mutate_and_rebind(inputs.party_pins[0].to_dict(), {"state_head_ref": "ral-head:fixture:2"})
        )
        head_changed = receipt_is_current(
            receipt,
            inputs=replace(inputs, party_pins=(advanced_pin, inputs.party_pins[1])),
        )
        self.assertFalse(head_changed.current)
        self.assertEqual(head_changed.reason_code, "authority_resolution_stale")

    def test_old_candidate_argument_is_not_part_of_currency_api(self):
        inputs = current_inputs()
        candidate = build_authority_candidate(inputs, evaluate_activation(inputs))
        receipt = receipt_for_candidate(candidate)
        with self.assertRaises(TypeError):
            receipt_is_current(receipt, inputs=inputs, fresh_candidate=candidate)

    def test_candidate_model_rejects_authorized_as_fabric_status(self):
        value = mutate_and_rebind(
            valid_authority_candidate(), {"candidate_status": "authorized"}
        )
        with assert_relation_error(self, "authority_candidate_invalid"):
            AuthorityCandidate.from_dict(value)

    def test_packaged_activation_schemas_meta_validate_and_accept_controls(self):
        controls = {
            "commitment-v1.schema.json": valid_commitment(),
            "authority-candidate-v1.schema.json": valid_authority_candidate(),
            "authority-evaluation-receipt-v1.schema.json": valid_evaluation_receipt(),
        }
        for name, value in controls.items():
            with self.subTest(name=name):
                schema = load_relation_contract(name)
                jsonschema.Draft202012Validator.check_schema(schema)
                jsonschema.validate(value, schema)


if __name__ == "__main__":
    unittest.main()
