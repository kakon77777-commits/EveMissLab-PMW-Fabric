from __future__ import annotations

import unittest

import jsonschema

from eml_pmw.relations.contracts import load_relation_contract
from eml_pmw.relations.events import EVENT_KINDS, EVENT_RULES, RelationContractEvent
from eml_pmw.relations.reducer import reduce_events
from tests.relation_contract_helpers import (
    assert_relation_error,
    fixture_objects,
    generic_profile_object,
    mutate_and_rebind,
    valid_contract_version,
    valid_grant_authority_evidence,
    valid_party_acceptance,
    valid_relation_contract_event,
    valid_relation_version,
    valid_representation_grant,
)


def contract_v2(contract_v1):
    return mutate_and_rebind(
        contract_v1,
        {"version": 2, "parent_version_digest": contract_v1["content_digest"]},
    )


def acceptance_for(contract, party):
    return mutate_and_rebind(
        valid_party_acceptance(party),
        {
            "acceptance_id": f"acceptance:fixture:{party}:contract:v{contract['version']}",
            "target_version": contract["version"],
            "target_digest": contract["content_digest"],
        },
    )


def active_v1_sequence():
    authority = valid_grant_authority_evidence()
    grant_a = valid_representation_grant("a")
    grant_b = valid_representation_grant("b")
    contract = valid_contract_version()
    accept_a = acceptance_for(contract, "a")
    accept_b = acceptance_for(contract, "b")
    events = [
        valid_relation_contract_event(
            "contract.drafted", contract, event_id="event:contract:draft:v1"
        ),
        valid_relation_contract_event(
            "contract.proposed",
            contract,
            event_id="event:contract:propose:v1",
            parents=("event:contract:draft:v1",),
            authority=authority,
            representation_grant=grant_a,
        ),
        valid_relation_contract_event(
            "contract.party_accepted",
            accept_a,
            subject_ref=contract["contract_id"],
            event_id="event:contract:accept:a:v1",
            parents=("event:contract:propose:v1",),
            representation_grant=grant_a,
        ),
        valid_relation_contract_event(
            "contract.party_accepted",
            accept_b,
            subject_ref=contract["contract_id"],
            event_id="event:contract:accept:b:v1",
            parents=("event:contract:accept:a:v1",),
            representation_grant=grant_b,
        ),
        valid_relation_contract_event(
            "contract.activated",
            contract,
            event_id="event:contract:activate:v1",
            parents=("event:contract:accept:b:v1",),
            authority=authority,
            representation_grant=grant_a,
        ),
    ]
    objects = fixture_objects(authority, grant_a, grant_b, contract, accept_a, accept_b)
    return contract, authority, events, objects


class RelationContractLifecycleTests(unittest.TestCase):
    def test_every_declared_event_kind_has_one_effect_handler(self):
        self.assertEqual(EVENT_KINDS, frozenset(EVENT_RULES))
        self.assertEqual(len(EVENT_KINDS), 30)
        self.assertTrue(all(callable(rule.effect_handler) for rule in EVENT_RULES.values()))

    def test_event_schema_meta_validates_and_accepts_control(self):
        contract = valid_contract_version()
        event = valid_relation_contract_event(
            "contract.drafted", contract, event_id="event:contract:draft:v1"
        )
        schema = load_relation_contract("relation-contract-event-v1.schema.json")
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(event, schema)
        self.assertEqual(RelationContractEvent.from_dict(event).to_dict(), event)

    def test_delivery_or_adoption_kind_is_not_profile_acceptance(self):
        contract = valid_contract_version()
        event = valid_relation_contract_event(
            "federation.adopted", contract, event_id="event:federation:adopted"
        )
        with assert_relation_error(self, "event_kind_not_allowed"):
            RelationContractEvent.from_dict(event)

    def test_transition_authority_ref_cannot_hide_changed_evidence(self):
        contract = valid_contract_version()
        authority = valid_grant_authority_evidence()
        grant_a = valid_representation_grant("a")
        grant_b = valid_representation_grant("b")
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.proposed",
                contract,
                event_id="event:contract:propose:v1",
                authority=authority,
                representation_grant=grant_a,
            )
        )
        changed = mutate_and_rebind(
            authority,
            {"permitted_lifecycle_actions": ["contract.suspended"]},
        )
        with assert_relation_error(self, "transition_authority_digest_mismatch"):
            reduce_events(
                [event],
                fixture_objects(contract, changed, grant_a),
            )

    def test_required_party_acceptances_derive_accepted_contract(self):
        contract = valid_contract_version()
        authority = valid_grant_authority_evidence()
        grant_a = valid_representation_grant("a")
        grant_b = valid_representation_grant("b")
        accept_a = acceptance_for(contract, "a")
        accept_b = acceptance_for(contract, "b")
        events = [
            RelationContractEvent.from_dict(
                valid_relation_contract_event(
                    "contract.drafted", contract, event_id="event:draft"
                )
            ),
            RelationContractEvent.from_dict(
                valid_relation_contract_event(
                    "contract.proposed",
                    contract,
                    event_id="event:proposed",
                    parents=("event:draft",),
                    authority=authority,
                    representation_grant=grant_a,
                )
            ),
            RelationContractEvent.from_dict(
                valid_relation_contract_event(
                    "contract.party_accepted",
                    accept_a,
                    subject_ref=contract["contract_id"],
                    event_id="event:accept:a",
                    parents=("event:proposed",),
                    representation_grant=grant_a,
                )
            ),
            RelationContractEvent.from_dict(
                valid_relation_contract_event(
                    "contract.party_accepted",
                    accept_b,
                    subject_ref=contract["contract_id"],
                    event_id="event:accept:b",
                    parents=("event:accept:a",),
                    representation_grant=grant_b,
                )
            ),
        ]
        projection = reduce_events(
            events,
            fixture_objects(
                contract, authority, grant_a, grant_b, accept_a, accept_b
            ),
        )
        self.assertEqual(
            projection.contract_version_states[contract["content_digest"]],
            "accepted",
        )

    def test_activation_atomically_supersedes_old_head_and_invalidates_candidate(self):
        contract1, authority, events, objects = active_v1_sequence()
        candidate = generic_profile_object(
            "arcp/authority-candidate/0.1",
            "candidate_id",
            "candidate:fixture:v1",
            contract_ref=contract1["contract_id"],
            contract_digest=contract1["content_digest"],
            active_lifecycle_head="event:contract:activate:v1",
        )
        candidate_event = valid_relation_contract_event(
            "authority_candidate.created",
            candidate,
            subject_ref=contract1["contract_id"],
            event_id="event:candidate:v1",
            parents=("event:contract:activate:v1",),
        )
        contract2 = contract_v2(contract1)
        grant_a = valid_representation_grant("a")
        grant_b = valid_representation_grant("b")
        accept_a2 = acceptance_for(contract2, "a")
        accept_b2 = acceptance_for(contract2, "b")
        events.extend(
            [
                candidate_event,
                valid_relation_contract_event(
                    "contract.amendment_proposed",
                    contract2,
                    event_id="event:contract:amend:v2",
                    parents=("event:candidate:v1",),
                    authority=authority,
                    representation_grant=grant_a,
                ),
                valid_relation_contract_event(
                    "contract.party_accepted",
                    accept_a2,
                    subject_ref=contract2["contract_id"],
                    event_id="event:contract:accept:a:v2",
                    parents=("event:contract:amend:v2",),
                    representation_grant=grant_a,
                ),
                valid_relation_contract_event(
                    "contract.party_accepted",
                    accept_b2,
                    subject_ref=contract2["contract_id"],
                    event_id="event:contract:accept:b:v2",
                    parents=("event:contract:accept:a:v2",),
                    representation_grant=grant_b,
                ),
                valid_relation_contract_event(
                    "contract.activated",
                    contract2,
                    event_id="event:contract:activate:v2",
                    parents=("event:contract:accept:b:v2",),
                    authority=authority,
                    representation_grant=grant_a,
                    supersedes_active_head="event:contract:activate:v1",
                ),
            ]
        )
        objects.update(
            fixture_objects(candidate, contract2, accept_a2, accept_b2)
        )
        projection = reduce_events(
            [RelationContractEvent.from_dict(item) for item in reversed(events)],
            objects,
        )
        self.assertEqual(
            projection.active_heads,
            {contract1["contract_id"]: "event:contract:activate:v2"},
        )
        self.assertIn(candidate["content_digest"], projection.invalidated_candidate_digests)

    def test_terminal_contract_rejects_resume_and_amendment(self):
        contract, authority, events, objects = active_v1_sequence()
        terminated = valid_relation_contract_event(
            "contract.terminated",
            contract,
            event_id="event:contract:terminate:v1",
            parents=("event:contract:activate:v1",),
            authority=authority,
            representation_grant=valid_representation_grant("a"),
        )
        base = [RelationContractEvent.from_dict(item) for item in events + [terminated]]
        for kind in ("contract.resumed", "contract.amendment_proposed"):
            with self.subTest(kind=kind):
                later = RelationContractEvent.from_dict(
                    valid_relation_contract_event(
                        kind,
                        contract,
                        event_id=f"event:forbidden:{kind}",
                        parents=("event:contract:terminate:v1",),
                        authority=authority,
                        representation_grant=valid_representation_grant("a"),
                    )
                )
                with assert_relation_error(self, "terminal_transition_forbidden"):
                    reduce_events(base + [later], objects)

    def test_concurrent_activation_heads_are_conflict_not_selection(self):
        contract, authority, events, objects = active_v1_sequence()
        events = events[:-1]
        first = valid_relation_contract_event(
            "contract.activated",
            contract,
            event_id="event:activate:left",
            parents=("event:contract:accept:b:v1",),
            authority=authority,
            representation_grant=valid_representation_grant("a"),
        )
        second = valid_relation_contract_event(
            "contract.activated",
            contract,
            event_id="event:activate:right",
            parents=("event:contract:accept:b:v1",),
            authority=authority,
            representation_grant=valid_representation_grant("a"),
        )
        projection = reduce_events(
            [RelationContractEvent.from_dict(item) for item in events + [first, second]],
            objects,
        )
        self.assertEqual(
            projection.contract_states[contract["contract_id"]],
            "conflicted_heads",
        )
        self.assertNotIn(contract["contract_id"], projection.active_heads)

    def test_representation_revoke_and_generic_effect_handlers_project(self):
        authority = valid_grant_authority_evidence()
        grant = valid_representation_grant()
        candidate = generic_profile_object(
            "arcp/authority-candidate/0.1",
            "candidate_id",
            "candidate:fixture:generic",
            contract_ref="contract:fixture:collaboration",
            contract_digest=valid_contract_version()["content_digest"],
            active_lifecycle_head="event:active:fixture",
        )
        events = [
            valid_relation_contract_event(
                "representation.granted",
                grant,
                event_id="event:representation:granted",
                authority=authority,
            ),
            valid_relation_contract_event(
                "authority_candidate.created",
                candidate,
                subject_ref="contract:fixture:collaboration",
                event_id="event:candidate:created",
                parents=("event:representation:granted",),
            ),
            valid_relation_contract_event(
                "representation.revoked",
                grant,
                event_id="event:representation:revoked",
                parents=("event:candidate:created",),
                authority=authority,
            ),
        ]
        projection = reduce_events(
            [RelationContractEvent.from_dict(item) for item in events],
            fixture_objects(authority, grant, candidate),
        )
        self.assertEqual(
            projection.representation_states[grant["representation_grant_id"]],
            "revoked",
        )
        self.assertIn(candidate["content_digest"], projection.invalidated_candidate_digests)


if __name__ == "__main__":
    unittest.main()
