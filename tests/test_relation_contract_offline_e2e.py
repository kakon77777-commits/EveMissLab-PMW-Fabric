from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import tempfile
import unittest

from eml_wake.canonical import loads_strict
from eml_pmw.federation.models import RealmRef, ReplicaRef
from eml_pmw.relations.activation import (
    build_authority_candidate,
    evaluate_activation,
)
from eml_pmw.relations.arcp_adapter import (
    DeterministicAuthorityEvaluator,
    OfflineEvaluatorGrant,
)
from eml_pmw.relations.events import RelationContractEvent
from eml_pmw.relations.federation_adapter import (
    inspect_imported_relation_event,
    wrap_relation_event,
)
from eml_pmw.relations.models_authority import (
    PartyAcceptance,
    RepresentationGrant,
)
from eml_pmw.relations.models_common import PartyEvidencePin
from eml_pmw.relations.models_relation import ContractVersion
from eml_pmw.relations.policy import ActivationPolicy
from eml_pmw.relations.portability import run_portable_conformance
from eml_pmw.relations.projector import rebuild_projection
from eml_pmw.relations.reducer import reduce_events
from eml_pmw.relations.store import RelationContractStore
from tests.relation_contract_helpers import (
    mutate_and_rebind,
    valid_activation_policy,
    valid_commitment,
    valid_grant_authority_evidence,
    valid_party_acceptance,
    valid_party_pin,
    valid_relation_contract_event,
    valid_relation_version,
    valid_representation_grant,
)
from test_relation_contract_activation import current_inputs
from test_relation_contract_lifecycle import (
    acceptance_for,
    active_v1_sequence,
    contract_v2,
)


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


@dataclass(frozen=True)
class FakeRealm:
    realm_kind: str


class FakePartyResolver:
    def resolve(self, party_ref: str) -> PartyEvidencePin:
        return PartyEvidencePin.from_dict(
            valid_party_pin(party_ref.rsplit(":", 1)[-1])
        )


def evaluation_event(receipt, candidate, parent_id, contract_id):
    value = valid_relation_contract_event(
        "authority_candidate.created",
        candidate.to_dict(),
        event_id="event:e2e:evaluation:template",
        subject_ref=contract_id,
        parents=(parent_id,),
    )
    value.update(
        {
            "event_id": "event:e2e:evaluation",
            "event_kind": "authority_evaluation.recorded",
            "object_ref": receipt.receipt_digest,
            "object_digest": receipt.receipt_digest,
        }
    )
    return RelationContractEvent.from_dict(value)


class RelationContractOfflineE2ETests(unittest.TestCase):
    def test_two_ai_contract_lifecycle_remains_offline_auditable_and_portable(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = RelationContractStore(Path(temporary) / "relations")
            contract1, authority, event_values, objects = active_v1_sequence()
            relation = valid_relation_version()
            relation_grants = []
            relation_authorities = []
            relation_acceptances = []
            for party in ("a", "b"):
                grant_id = f"representation-grant:fixture:{party}:relation"
                relation_authority = mutate_and_rebind(
                    valid_grant_authority_evidence(party),
                    {
                        "grant_authority_evidence_id": f"grant-authority-evidence:fixture:{party}:relation",
                        "permitted_lifecycle_actions": [
                            "representation.granted",
                            "relation.proposed",
                        ],
                        "permitted_contract_scope": [
                            grant_id,
                            relation["relation_id"],
                        ],
                    },
                )
                relation_grant = mutate_and_rebind(
                    valid_representation_grant(party),
                    {
                        "representation_grant_id": grant_id,
                        "allowed_lifecycle_actions": [
                            "relation.proposed",
                            "relation.party_accepted",
                        ],
                        "contract_scope": [],
                        "relation_scope": [relation["relation_id"]],
                        "grant_authority_ref": relation_authority[
                            "grant_authority_evidence_id"
                        ],
                    },
                )
                relation_acceptance = mutate_and_rebind(
                    valid_party_acceptance(party, target_kind="relation"),
                    {
                        "representation_grant_ref": grant_id,
                        "representation_grant_digest": relation_grant[
                            "content_digest"
                        ],
                    },
                )
                relation_authorities.append(relation_authority)
                relation_grants.append(relation_grant)
                relation_acceptances.append(relation_acceptance)
            for value in objects.values():
                store.put_object(KIND_BY_SCHEMA[value["schema"]], value)
            for value in (
                relation,
                *relation_authorities,
                *relation_grants,
                *relation_acceptances,
            ):
                store.put_object(KIND_BY_SCHEMA[value["schema"]], value)
            base_events = [
                RelationContractEvent.from_dict(value) for value in event_values
            ]
            for event in base_events[:2]:
                store.append_event(event)
            relation_event_values = [
                valid_relation_contract_event(
                    "representation.granted",
                    relation_grants[0],
                    event_id="event:e2e:relation-grant:a",
                    parents=(base_events[1].event_id,),
                    authority=relation_authorities[0],
                ),
                valid_relation_contract_event(
                    "representation.granted",
                    relation_grants[1],
                    event_id="event:e2e:relation-grant:b",
                    parents=("event:e2e:relation-grant:a",),
                    authority=relation_authorities[1],
                ),
                valid_relation_contract_event(
                    "relation.proposed",
                    relation,
                    event_id="event:e2e:relation-proposed",
                    parents=("event:e2e:relation-grant:b",),
                    authority=relation_authorities[0],
                    representation_grant=relation_grants[0],
                ),
                valid_relation_contract_event(
                    "relation.party_accepted",
                    relation_acceptances[0],
                    event_id="event:e2e:relation-accept:a",
                    subject_ref=relation["relation_id"],
                    parents=("event:e2e:relation-proposed",),
                    representation_grant=relation_grants[0],
                ),
                valid_relation_contract_event(
                    "relation.party_accepted",
                    relation_acceptances[1],
                    event_id="event:e2e:relation-accept:b",
                    subject_ref=relation["relation_id"],
                    parents=("event:e2e:relation-accept:a",),
                    representation_grant=relation_grants[1],
                ),
            ]
            for value in relation_event_values:
                store.append_event(RelationContractEvent.from_dict(value))
            contract_events = list(base_events[2:])
            contract_events[0] = replace(
                contract_events[0],
                causal_parents=("event:e2e:relation-accept:b",),
            )
            for event in contract_events:
                store.append_event(event)

            inputs = current_inputs()
            decision = evaluate_activation(inputs)
            self.assertEqual(decision.status, "eligible")
            candidate = build_authority_candidate(inputs, decision)
            evaluator = DeterministicAuthorityEvaluator(
                candidate.evaluator_policy_version,
                (
                    OfflineEvaluatorGrant(
                        "evaluator-grant:e2e",
                        candidate.subject_entity_ref,
                        candidate.requested_resource_scope,
                        candidate.requested_action_scope,
                        "R1",
                        "verified",
                        "active",
                        ("none",),
                    ),
                ),
            )
            receipt = evaluator.evaluate(candidate, inputs.now)
            commitment = valid_commitment()
            for kind, value in (
                ("authority_candidate", candidate.to_dict()),
                ("authority_evaluation", receipt.to_dict()),
                ("commitment", commitment),
            ):
                store.put_object(kind, value)
            candidate_event = RelationContractEvent.from_dict(
                valid_relation_contract_event(
                    "authority_candidate.created",
                    candidate.to_dict(),
                    event_id="event:e2e:candidate",
                    subject_ref=contract1["contract_id"],
                    parents=("event:contract:activate:v1",),
                )
            )
            store.append_event(candidate_event)
            receipt_event = evaluation_event(
                receipt,
                candidate,
                candidate_event.event_id,
                contract1["contract_id"],
            )
            store.append_event(receipt_event)
            commitment_event = RelationContractEvent.from_dict(
                valid_relation_contract_event(
                    "commitment.created",
                    commitment,
                    event_id="event:e2e:commitment",
                    subject_ref=contract1["contract_id"],
                    parents=(receipt_event.event_id,),
                )
            )
            store.append_event(commitment_event)

            contract2 = contract_v2(contract1)
            accept_a2 = acceptance_for(contract2, "a")
            accept_b2 = acceptance_for(contract2, "b")
            for value in (contract2, accept_a2, accept_b2):
                store.put_object(KIND_BY_SCHEMA[value["schema"]], value)
            grant_a = next(
                RepresentationGrant.from_dict(value)
                for value in objects.values()
                if value.get("representation_grant_id")
                == "representation-grant:fixture:a:1"
            )
            grant_b = next(
                RepresentationGrant.from_dict(value)
                for value in objects.values()
                if value.get("representation_grant_id")
                == "representation-grant:fixture:b:1"
            )
            amendment_values = [
                valid_relation_contract_event(
                    "contract.amendment_proposed",
                    contract2,
                    event_id="event:e2e:amend:v2",
                    parents=(commitment_event.event_id,),
                    authority=authority,
                    representation_grant=grant_a.to_dict(),
                ),
                valid_relation_contract_event(
                    "contract.party_accepted",
                    accept_a2,
                    event_id="event:e2e:accept:a:v2",
                    subject_ref=contract2["contract_id"],
                    parents=("event:e2e:amend:v2",),
                    representation_grant=grant_a.to_dict(),
                ),
                valid_relation_contract_event(
                    "contract.party_accepted",
                    accept_b2,
                    event_id="event:e2e:accept:b:v2",
                    subject_ref=contract2["contract_id"],
                    parents=("event:e2e:accept:a:v2",),
                    representation_grant=grant_b.to_dict(),
                ),
                valid_relation_contract_event(
                    "contract.activated",
                    contract2,
                    event_id="event:e2e:activate:v2",
                    parents=("event:e2e:accept:b:v2",),
                    authority=authority,
                    representation_grant=grant_a.to_dict(),
                    supersedes_active_head="event:contract:activate:v1",
                ),
                valid_relation_contract_event(
                    "contract.terminated",
                    contract2,
                    event_id="event:e2e:terminate:v2",
                    parents=("event:e2e:activate:v2",),
                    authority=authority,
                    representation_grant=grant_a.to_dict(),
                ),
            ]
            amendment_events = [
                RelationContractEvent.from_dict(value)
                for value in amendment_values
            ]
            for event in amendment_events:
                store.append_event(event)

            lifecycle = reduce_events(store.events(), store.objects_by_digest())
            self.assertEqual(
                lifecycle.relation_states[relation["relation_id"]], "accepted"
            )
            self.assertIn(
                candidate.content_digest,
                lifecycle.invalidated_candidate_digests,
            )
            future_inputs = replace(
                inputs,
                contract=ContractVersion.from_dict(
                    contract2,
                    policy=ActivationPolicy.from_dict(valid_activation_policy()),
                ),
                lifecycle_projection=lifecycle,
                acceptances=(
                    PartyAcceptance.from_dict(accept_a2),
                    PartyAcceptance.from_dict(accept_b2),
                ),
            )
            future = evaluate_activation(future_inputs)
            self.assertNotEqual(future.status, "eligible")

            projection = loads_strict(rebuild_projection(store))
            contract_projection = projection["contracts"][contract1["contract_id"]]
            self.assertEqual(contract_projection["state"], "terminated")
            self.assertEqual(
                contract_projection["execution_status"], "not_observed"
            )
            self.assertTrue(projection["audit_history_retained"])
            self.assertGreaterEqual(len(projection["source_event_digests"]), 10)
            self.assertEqual(commitment["execution_refs"], [])

            termination = amendment_events[-1]
            payloads = []
            relation_digests = []
            for realm_kind in ("windows_host", "hdus_host"):
                realm = RealmRef.from_dict(
                    {
                        "realm_id": f"realm:{realm_kind}",
                        "realm_kind": realm_kind,
                        "issuer": "fixture",
                        "verification_status": "verified",
                        "evidence_refs": [f"evidence:realm:{realm_kind}"],
                    }
                )
                replica = ReplicaRef.from_dict(
                    {
                        "replica_id": f"replica:{realm_kind}",
                        "realm_id": realm.realm_id,
                        "store_generation": "generation:1",
                        "verification_status": "verified",
                        "evidence_refs": [f"evidence:replica:{realm_kind}"],
                    }
                )
                envelope, payload = wrap_relation_event(
                    termination,
                    realm_ref=realm,
                    replica_ref=replica,
                    replica_seq=1,
                    payload_class="P0",
                )
                inspected = inspect_imported_relation_event(envelope, payload)
                payloads.append(payload)
                relation_digests.append(inspected.relation_event.event_digest)
            self.assertEqual(payloads[0], payloads[1])
            self.assertEqual(relation_digests[0], relation_digests[1])

            resolver = FakePartyResolver()
            windows = run_portable_conformance(FakeRealm("windows_host"), resolver)
            hdus = run_portable_conformance(FakeRealm("hdus_host"), resolver)
            self.assertEqual(windows.semantic_digest, hdus.semantic_digest)
            self.assertEqual(windows.effect_measurement_status, "unmeasured")
            self.assertIsNone(windows.effect_counts)


if __name__ == "__main__":
    unittest.main()
