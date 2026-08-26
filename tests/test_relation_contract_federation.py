from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from eml_wake.canonical import canonical_bytes, loads_strict
from eml_pmw.federation.models import (
    FederatedEvent,
    FederationConfig,
    RealmRef,
    ReplicaRef,
)
from eml_pmw.federation.store import FederationStore
from eml_pmw.relations.events import (
    AUTHORITY_REQUIRED_KINDS,
    EVENT_KINDS,
    RelationContractEvent,
)
from eml_pmw.relations.federation_adapter import (
    ExplicitRelationAdoptionReceipt,
    ImportedRelationObservation,
    adopt_relation_event,
    inspect_imported_relation_event,
    verify_adoption_history,
    wrap_relation_event,
)
from eml_pmw.relations.reducer import reduce_events
from eml_pmw.relations.store import RelationContractStore
from tests.federation_helpers import valid_config, valid_event
from tests.relation_contract_helpers import (
    assert_relation_error,
    valid_relation_contract_event,
    valid_relation_version,
)
from test_relation_contract_lifecycle import active_v1_sequence


def realm_and_replica():
    value = valid_event()
    return (
        RealmRef.from_dict(value["realm_ref"]),
        ReplicaRef.from_dict(value["replica_ref"]),
    )


def relation_config(root: Path) -> FederationConfig:
    return FederationConfig.from_dict(
        valid_config(
            allowed_source_roots=[str(root)],
            allowed_event_kinds=sorted(EVENT_KINDS),
            authority_required_event_kinds=sorted(AUTHORITY_REQUIRED_KINDS),
            allowed_authority_refs=["grant-authority-evidence:fixture:a"],
        )
    )


def observation_for(event: RelationContractEvent, *, sequence=1, payload_class="P0"):
    realm, replica = realm_and_replica()
    envelope, payload = wrap_relation_event(
        event,
        realm_ref=realm,
        replica_ref=replica,
        replica_seq=sequence,
        payload_class=payload_class,
    )
    return envelope, payload, inspect_imported_relation_event(envelope, payload)


def adoption_receipt(
    observation: ImportedRelationObservation,
    adoption_id: str,
) -> ExplicitRelationAdoptionReceipt:
    value = {
        "schema": "arcp/relation-event-adoption-receipt/0.1",
        "adoption_id": adoption_id,
        "event_id": observation.relation_event.event_id,
        "envelope_digest": observation.envelope_digest,
        "relation_event_digest": observation.relation_event.event_digest,
        "payload_sha256": observation.payload_sha256,
        "receiver_realm_id": "realm:receiver",
        "decision": "adopted",
        "receiver_observation_refs": ["observation:fixture:receiver"],
        "not_claimed": [
            "acceptance_created",
            "authority_granted",
            "execution_observed",
            "resident_identity_continuity",
        ],
        "receipt_digest": "",
    }
    value["receipt_digest"] = ExplicitRelationAdoptionReceipt.digest_for(value)
    return ExplicitRelationAdoptionReceipt.from_dict(value)


class RelationContractFederationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_delivery_and_explicit_adoption_do_not_create_acceptance(self):
        relation = valid_relation_version(
            relation_class="descriptive", acceptance_rule="none"
        )
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "relation.recorded",
                relation,
                event_id="event:federation:relation-recorded",
            )
        )
        envelope, payload, observation = observation_for(event)
        transport = FederationStore(
            self.root / "transport", relation_config(self.root)
        )
        transport.submit(envelope, payload, delivery_id="delivery:fixture:1")

        local = RelationContractStore(self.root / "relations")
        self.assertEqual(local.events(), ())
        local.put_object("relation", relation)
        result = adopt_relation_event(
            observation,
            adoption_receipt(observation, "adoption:fixture:relation"),
            local,
        )

        self.assertEqual(result.status, "adopted")
        projection = reduce_events(local.events(), local.objects_by_digest())
        self.assertEqual(projection.acceptances, {})
        self.assertEqual(
            projection.relation_states[relation["relation_id"]], "observed"
        )

    def test_child_before_parent_retains_pending_then_adopts_once(self):
        relation = valid_relation_version(
            relation_class="descriptive", acceptance_rule="none"
        )
        parent = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "relation.recorded",
                relation,
                event_id="event:federation:parent",
            )
        )
        child = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "relation.disputed",
                relation,
                event_id="event:federation:child",
                parents=(parent.event_id,),
            )
        )
        _, _, parent_observation = observation_for(parent, sequence=1)
        _, _, child_observation = observation_for(child, sequence=2)
        local = RelationContractStore(self.root / "pending-relations")
        local.put_object("relation", relation)
        child_receipt = adoption_receipt(
            child_observation, "adoption:fixture:child"
        )

        first = adopt_relation_event(child_observation, child_receipt, local)
        self.assertEqual(first.status, "pending_dependencies")
        self.assertEqual(first.missing_parent_ids, (parent.event_id,))
        self.assertEqual(local.events(), ())
        self.assertEqual(len(list(local.adoptions_pending_dir.glob("*.json"))), 1)

        adopted_parent = adopt_relation_event(
            parent_observation,
            adoption_receipt(parent_observation, "adoption:fixture:parent"),
            local,
        )
        self.assertEqual(adopted_parent.status, "adopted")
        second = adopt_relation_event(child_observation, child_receipt, local)
        self.assertEqual(second.status, "adopted")
        third = adopt_relation_event(child_observation, child_receipt, local)
        self.assertEqual(third.status, "adopted")
        self.assertEqual(
            len([item for item in local.events() if item.event_id == child.event_id]),
            1,
        )
        self.assertEqual(len(list(local.adoptions_pending_dir.glob("*.json"))), 1)
        self.assertEqual(len(list(local.adoptions_adopted_dir.glob("*.json"))), 2)
        self.assertEqual(local.verify().status, "internally_consistent")
        history = verify_adoption_history(local)
        self.assertEqual(history.status, "verified")
        self.assertEqual(history.pending_count, 1)
        self.assertEqual(history.adopted_count, 2)

    def test_changed_adoption_identity_and_integrity_failure_quarantine(self):
        relation = valid_relation_version(
            relation_class="descriptive", acceptance_rule="none"
        )
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "relation.recorded",
                relation,
                event_id="event:federation:quarantine",
            )
        )
        _, _, observation = observation_for(event)
        local = RelationContractStore(self.root / "quarantine-relations")
        local.put_object("relation", relation)
        receipt = adoption_receipt(observation, "adoption:fixture:quarantine")
        tampered = replace(observation, payload_sha256="0" * 64)

        result = adopt_relation_event(tampered, receipt, local)
        self.assertEqual(result.status, "quarantined")
        self.assertEqual(local.events(), ())
        self.assertEqual(
            len(list(local.adoptions_quarantine_dir.glob("*.json"))), 1
        )

        adopted = adopt_relation_event(observation, receipt, local)
        self.assertEqual(adopted.status, "adopted")
        changed_value = receipt.to_dict()
        changed_value["receiver_realm_id"] = "realm:other"
        changed_value["receipt_digest"] = ExplicitRelationAdoptionReceipt.digest_for(
            changed_value
        )
        changed = ExplicitRelationAdoptionReceipt.from_dict(changed_value)
        with assert_relation_error(self, "adoption_id_collision"):
            adopt_relation_event(observation, changed, local)

    def test_wrap_and_inspect_are_exact_p0_p1_and_reject_other_classes(self):
        relation = valid_relation_version(
            relation_class="descriptive", acceptance_rule="none"
        )
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "relation.recorded",
                relation,
                event_id="event:federation:wrap",
            )
        )
        controls = []
        for payload_class in ("P0", "P1"):
            envelope, payload, observation = observation_for(
                event, payload_class=payload_class
            )
            self.assertEqual(observation.relation_event, event)
            self.assertEqual(envelope.fabric_payload_class, payload_class)
            self.assertEqual(envelope.event_id, event.event_id)
            controls.append((envelope.core_digest, payload))
        self.assertEqual(controls[0][1], controls[1][1])

        with assert_relation_error(self, "fabric_payload_class_invalid"):
            observation_for(event, payload_class="P2")
        envelope, payload, _ = observation_for(event)
        changed = replace(envelope, payload_sha256="A" * 64)
        with assert_relation_error(self, "relation_envelope_payload_mismatch"):
            inspect_imported_relation_event(changed, payload)

    def test_adoption_history_tamper_is_not_hidden_by_core_store_verification(self):
        relation = valid_relation_version(
            relation_class="descriptive", acceptance_rule="none"
        )
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "relation.recorded",
                relation,
                event_id="event:federation:history-tamper",
            )
        )
        _, _, observation = observation_for(event)
        local = RelationContractStore(self.root / "history-tamper")
        local.put_object("relation", relation)
        adopt_relation_event(
            observation,
            adoption_receipt(observation, "adoption:fixture:history-tamper"),
            local,
        )
        path = next(local.adoptions_adopted_dir.glob("*.json"))
        value = loads_strict(path.read_bytes())
        value["event_id"] = "event:tampered"
        path.write_bytes(canonical_bytes(value))

        self.assertEqual(local.verify().status, "internally_consistent")
        verification = verify_adoption_history(local)
        self.assertEqual(verification.status, "invalid")
        self.assertIn("adoption_record_invalid", verification.error_codes)

    def test_two_federated_sibling_activations_remain_conflicted_heads(self):
        local = RelationContractStore(self.root / "conflict-relations")
        contract, authority, event_values, objects = active_v1_sequence()
        kind_by_schema = {
            "arcp/activation-policy/0.1": "activation_policy",
            "arcp/party-evidence-pin/0.1": "party_evidence",
            "arcp/relation-version/0.1": "relation",
            "arcp/contract-version/0.1": "contract",
            "arcp/grant-authority-evidence/0.1": "grant_authority",
            "arcp/representation-grant/0.1": "representation_grant",
            "arcp/party-acceptance/0.1": "acceptance",
        }
        for value in objects.values():
            local.put_object(kind_by_schema[value["schema"]], value)
        for value in event_values[:-1]:
            local.append_event(RelationContractEvent.from_dict(value))
        grant = next(
            value
            for value in objects.values()
            if value.get("representation_grant_id")
            == "representation-grant:fixture:a:1"
        )
        for sequence, side in enumerate(("left", "right"), start=7):
            event = RelationContractEvent.from_dict(
                valid_relation_contract_event(
                    "contract.activated",
                    contract,
                    event_id=f"event:federation:activate:{side}",
                    parents=("event:contract:accept:b:v1",),
                    authority=authority,
                    representation_grant=grant,
                )
            )
            _, _, observation = observation_for(event, sequence=sequence)
            result = adopt_relation_event(
                observation,
                adoption_receipt(
                    observation, f"adoption:fixture:activate:{side}"
                ),
                local,
            )
            self.assertEqual(result.status, "adopted")

        projection = reduce_events(local.events(), local.objects_by_digest())
        self.assertEqual(
            projection.contract_states[contract["contract_id"]],
            "conflicted_heads",
        )
        self.assertEqual(projection.acceptances[contract["content_digest"]], (
            "resident:fixture:a",
            "resident:fixture:b",
        ))


if __name__ == "__main__":
    unittest.main()
