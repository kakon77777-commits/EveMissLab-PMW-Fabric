from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import tempfile
import unittest

import jsonschema

from eml_wake.canonical import canonical_bytes, loads_strict
from eml_pmw.relations.contracts import load_relation_contract
from eml_pmw.relations.errors import RelationContractError
from eml_pmw.relations.events import RelationContractEvent
from eml_pmw.relations.projector import (
    explain_subject,
    projection_digest,
    rebuild_projection,
)
from eml_pmw.relations.store import RelationContractStore
from tests.relation_contract_helpers import (
    assert_relation_error,
    mutate_and_rebind,
    valid_authority_candidate,
    valid_evaluation_receipt,
    valid_relation_contract_event,
    valid_relation_version,
)
from test_relation_contract_lifecycle import active_v1_sequence


KIND_BY_SCHEMA = {
    "arcp/activation-policy/0.1": "activation_policy",
    "arcp/party-evidence-pin/0.1": "party_evidence",
    "arcp/relation-version/0.1": "relation",
    "arcp/contract-version/0.1": "contract",
    "arcp/grant-authority-evidence/0.1": "grant_authority",
    "arcp/representation-grant/0.1": "representation_grant",
    "arcp/party-acceptance/0.1": "acceptance",
    "arcp/commitment/0.1": "commitment",
    "arcp/authority-candidate/0.1": "authority_candidate",
    "arcp/authority-evaluation-receipt/0.1": "authority_evaluation",
}


def put_objects(store, values):
    for value in values:
        store.put_object(KIND_BY_SCHEMA[value["schema"]], value)


def evaluation_event(receipt, parent_id, contract_id):
    candidate = valid_authority_candidate()
    value = valid_relation_contract_event(
        "authority_candidate.created",
        candidate,
        event_id="event:evaluation:template",
        subject_ref=contract_id,
        parents=(parent_id,),
    )
    value.update(
        {
            "event_id": "event:evaluation:recorded",
            "event_kind": "authority_evaluation.recorded",
            "object_ref": receipt["receipt_digest"],
            "object_digest": receipt["receipt_digest"],
        }
    )
    return RelationContractEvent.from_dict(value)


def active_store(root, *, include_candidate=True, include_receipt=True):
    store = RelationContractStore(root)
    contract, _, event_values, objects = active_v1_sequence()
    relation = valid_relation_version()
    put_objects(store, [*objects.values(), relation])
    for value in event_values:
        store.append_event(RelationContractEvent.from_dict(value))
    parent = "event:contract:activate:v1"
    candidate = valid_authority_candidate()
    if include_candidate:
        store.put_object("authority_candidate", candidate)
        candidate_event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "authority_candidate.created",
                candidate,
                event_id="event:candidate:projection",
                subject_ref=contract["contract_id"],
                parents=(parent,),
            )
        )
        store.append_event(candidate_event)
        parent = candidate_event.event_id
    if include_receipt:
        receipt = valid_evaluation_receipt()
        store.put_object("authority_evaluation", receipt)
        store.append_event(evaluation_event(receipt, parent, contract["contract_id"]))
    return store, contract, relation, candidate


class ProjectionFixtureSource:
    def __init__(self, events, objects):
        self._events = tuple(events)
        self._objects = dict(objects)

    def verify(self):
        return type("Verification", (), {"status": "internally_consistent"})()

    def events(self):
        return self._events

    def objects_by_digest(self):
        return dict(self._objects)


class RelationContractProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_rebuild_is_byte_identical_for_opposite_concurrent_insertion_order(self):
        relation_a = mutate_and_rebind(
            valid_relation_version(),
            {
                "relation_id": "relation:fixture:a",
                "relation_class": "descriptive",
                "acceptance_rule": "none",
            },
        )
        relation_b = mutate_and_rebind(
            valid_relation_version(),
            {
                "relation_id": "relation:fixture:b",
                "relation_class": "descriptive",
                "acceptance_rule": "none",
            },
        )
        event_a = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "relation.recorded", relation_a, event_id="event:relation:a"
            )
        )
        event_b = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "relation.recorded", relation_b, event_id="event:relation:b"
            )
        )
        outputs = []
        for name, objects, events in (
            ("left", (relation_a, relation_b), (event_a, event_b)),
            ("right", (relation_b, relation_a), (event_b, event_a)),
        ):
            store = RelationContractStore(self.root / name)
            put_objects(store, objects)
            for event in events:
                store.append_event(event)
            outputs.append(rebuild_projection(store))
        self.assertEqual(outputs[0], outputs[1])

    def test_relation_reverse_contract_index_is_derived_only(self):
        store, _, relation, _ = active_store(self.root / "reverse")
        value = loads_strict(rebuild_projection(store))
        projected = value["relations"][relation["relation_id"]]
        self.assertEqual(
            projected["derived_contract_refs"],
            ["contract:fixture:collaboration"],
        )
        self.assertNotIn(
            "contract_refs", store.get_object(relation["content_digest"])
        )

    def test_explain_keeps_acceptance_representation_authority_and_execution_separate(self):
        store, contract, _, _ = active_store(self.root / "explain")
        value = explain_subject(store, contract["contract_id"])
        self.assertEqual(value["execution_status"], "not_observed")
        self.assertIsNotNone(value["acceptance_set_digest"])
        self.assertIsNotNone(value["representation_set_digest"])
        self.assertIsNotNone(value["authority_candidate_digest"])
        self.assertIsNotNone(value["authority_evaluation_receipt_digest"])
        self.assertNotIn("authorized", value)

    def test_explain_does_not_upgrade_object_only_candidate_or_receipt(self):
        candidate_store, contract, _, candidate = active_store(
            self.root / "object-only-candidate",
            include_candidate=False,
            include_receipt=False,
        )
        candidate_store.put_object("authority_candidate", candidate)
        candidate_explain = explain_subject(
            candidate_store, contract["contract_id"]
        )
        self.assertEqual(
            candidate_explain["authority_candidate_selection_status"], "none"
        )
        self.assertIsNone(candidate_explain["authority_candidate_digest"])

        receipt_store, contract, _, _ = active_store(
            self.root / "object-only-receipt",
            include_candidate=True,
            include_receipt=False,
        )
        receipt = valid_evaluation_receipt()
        receipt_store.put_object("authority_evaluation", receipt)
        inventory = loads_strict(rebuild_projection(receipt_store))[
            "authority_evaluations"
        ][receipt["receipt_digest"]]
        self.assertEqual(inventory["projection_state"], "unobserved")
        self.assertEqual(inventory["receipt_currency"], "unobserved")
        receipt_explain = explain_subject(receipt_store, contract["contract_id"])
        self.assertEqual(
            receipt_explain["authority_evaluation_selection_status"], "none"
        )
        self.assertIsNone(
            receipt_explain["authority_evaluation_receipt_digest"]
        )
        self.assertIsNone(receipt_explain["receipt_currency"])

    def test_explain_marks_multiple_recorded_candidates_ambiguous(self):
        store, contract, _, first = active_store(
            self.root / "ambiguous-candidates",
            include_candidate=True,
            include_receipt=False,
        )
        second = mutate_and_rebind(
            first,
            {
                "candidate_id": "candidate:fixture:inspect:2",
                "action_intent_ref": "action:fixture:inspect:2",
            },
        )
        store.put_object("authority_candidate", second)
        store.append_event(
            RelationContractEvent.from_dict(
                valid_relation_contract_event(
                    "authority_candidate.created",
                    second,
                    event_id="event:candidate:projection:2",
                    subject_ref=contract["contract_id"],
                    parents=("event:candidate:projection",),
                )
            )
        )

        value = explain_subject(store, contract["contract_id"])
        self.assertEqual(
            value["authority_candidate_selection_status"], "ambiguous"
        )
        self.assertIsNone(value["authority_candidate_digest"])
        self.assertEqual(
            value["authority_evaluation_selection_status"], "none"
        )

    def test_evaluation_event_uses_receipt_digest_as_object_identity(self):
        store, contract, _, _ = active_store(self.root / "evaluation")
        value = loads_strict(rebuild_projection(store))
        receipts = value["authority_evaluations"]
        self.assertEqual(len(receipts), 1)
        receipt_digest = next(iter(receipts))
        self.assertTrue(receipt_digest.startswith("sha256:"))
        self.assertEqual(
            receipts[receipt_digest]["candidate_ref"],
            valid_evaluation_receipt()["candidate_ref"],
        )

    def test_projection_rejects_event_object_digest_without_matching_object(self):
        contract, _, events, objects = active_v1_sequence()
        parsed = [RelationContractEvent.from_dict(value) for value in events]
        changed = replace(
            parsed[-1],
            object_digest="sha256:arcp-relation-contract-json-nfc-codepoint-v1:"
            + "f" * 64,
        )
        source = ProjectionFixtureSource([*parsed[:-1], changed], objects)
        with assert_relation_error(self, "object_digest_mismatch"):
            rebuild_projection(source)

    def test_projection_types_event_object_kind_mismatch(self):
        relation = mutate_and_rebind(
            valid_relation_version(),
            {"relation_class": "descriptive", "acceptance_rule": "none"},
        )
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                relation,
                event_id="event:projection:wrong-object-kind",
            )
        )
        source = ProjectionFixtureSource(
            [event], {relation["content_digest"]: relation}
        )
        with assert_relation_error(self, "event_object_kind_mismatch"):
            rebuild_projection(source)

    def test_projection_schema_meta_validates_and_digest_omits_itself(self):
        store, _, _, _ = active_store(self.root / "schema")
        raw = rebuild_projection(store)
        value = loads_strict(raw)
        schema = load_relation_contract("relation-contract-projection-v1.schema.json")
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(value, schema)
        self.assertEqual(value["projection_digest"], projection_digest(value))

    def test_invalid_or_repairable_store_is_not_projected(self):
        store, _, _, _ = active_store(self.root / "invalid")
        first_index = next((store.root / "indexes" / "object-digests").glob("*.json"))
        first_index.unlink()
        with assert_relation_error(self, "store_not_projectable"):
            rebuild_projection(store)


if __name__ == "__main__":
    unittest.main()
