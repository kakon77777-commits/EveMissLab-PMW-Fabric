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
    normalized_instant,
    valid_contract_version,
    valid_commitment,
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


def granted_representation_event(authority, grant, event_id, parents=()):
    return RelationContractEvent.from_dict(
        valid_relation_contract_event(
            "representation.granted",
            grant,
            event_id=event_id,
            parents=parents,
            authority=authority,
        )
    )


def active_v1_sequence():
    authority = valid_grant_authority_evidence("a")
    authority_b = valid_grant_authority_evidence("b")
    grant_a = valid_representation_grant("a")
    grant_b = valid_representation_grant("b")
    contract = valid_contract_version()
    accept_a = acceptance_for(contract, "a")
    accept_b = acceptance_for(contract, "b")
    events = [
        valid_relation_contract_event(
            "representation.granted",
            grant_a,
            event_id="event:representation:grant:a",
            authority=authority,
        ),
        valid_relation_contract_event(
            "representation.granted",
            grant_b,
            event_id="event:representation:grant:b",
            parents=("event:representation:grant:a",),
            authority=authority_b,
        ),
        valid_relation_contract_event(
            "contract.drafted",
            contract,
            event_id="event:contract:draft:v1",
            parents=("event:representation:grant:b",),
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
    objects = fixture_objects(
        authority, authority_b, grant_a, grant_b, contract, accept_a, accept_b
    )
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
        issuer = valid_grant_authority_evidence("a")
        authority = mutate_and_rebind(
            issuer,
            {"grant_authority_evidence_id": "grant-authority-evidence:transition"},
        )
        grant_a = valid_representation_grant("a")
        grant_event = granted_representation_event(
            issuer, grant_a, "event:contract:grant:authority-digest"
        )
        draft = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                contract,
                event_id="event:contract:draft:authority-digest",
                parents=(grant_event.event_id,),
            )
        )
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.proposed",
                contract,
                event_id="event:contract:propose:v1",
                parents=(draft.event_id,),
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
                [grant_event, draft, event],
                fixture_objects(contract, issuer, changed, grant_a),
            )

    def test_absent_contract_cannot_jump_directly_to_proposed(self):
        contract = valid_contract_version()
        authority = valid_grant_authority_evidence()
        grant = valid_representation_grant("a")
        grant_event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "representation.granted",
                grant,
                event_id="event:precondition:grant",
                authority=authority,
            )
        )
        proposed = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.proposed",
                contract,
                event_id="event:precondition:proposed",
                parents=(grant_event.event_id,),
                authority=authority,
                representation_grant=grant,
            )
        )
        with assert_relation_error(self, "lifecycle_transition_invalid"):
            reduce_events(
                [grant_event, proposed], fixture_objects(contract, authority, grant)
            )

    def test_draft_cannot_jump_to_suspended(self):
        contract = valid_contract_version()
        authority = valid_grant_authority_evidence()
        draft = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted", contract, event_id="event:precondition:draft"
            )
        )
        suspended = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.suspended",
                contract,
                event_id="event:precondition:suspend",
                parents=(draft.event_id,),
                authority=authority,
            )
        )
        with assert_relation_error(self, "lifecycle_transition_invalid"):
            reduce_events(
                [draft, suspended], fixture_objects(contract, authority)
            )

    def test_active_contract_cannot_be_drafted_again(self):
        contract, _, events, objects = active_v1_sequence()
        drafted_again = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                contract,
                event_id="event:precondition:redraft",
                parents=("event:contract:activate:v1",),
            )
        )
        with assert_relation_error(self, "lifecycle_transition_invalid"):
            reduce_events(
                [RelationContractEvent.from_dict(item) for item in events]
                + [drafted_again],
                objects,
            )

    def test_representation_cannot_revoke_from_absent(self):
        authority = valid_grant_authority_evidence()
        grant = valid_representation_grant("a")
        revoked = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "representation.revoked",
                grant,
                event_id="event:precondition:revoke",
                authority=authority,
            )
        )
        with assert_relation_error(self, "lifecycle_transition_invalid"):
            reduce_events([revoked], fixture_objects(authority, grant))

    def test_commitment_cannot_change_status_before_creation(self):
        commitment = valid_commitment(status="satisfied")
        changed = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "commitment.status_changed",
                commitment,
                event_id="event:precondition:commitment-change",
            )
        )
        with assert_relation_error(self, "lifecycle_transition_invalid"):
            reduce_events([changed], fixture_objects(commitment))

    def test_transition_authority_must_cover_action_and_subject_scope(self):
        contract = valid_contract_version()
        issuer = valid_grant_authority_evidence("a")
        authority = mutate_and_rebind(
            issuer,
            {
                "grant_authority_evidence_id": "grant-authority-evidence:wrong-scope",
                "permitted_lifecycle_actions": ["contract.suspended"],
                "permitted_contract_scope": ["contract:other"],
            },
        )
        grant = valid_representation_grant("a")
        grant_event = granted_representation_event(
            issuer, grant, "event:authority:grant"
        )
        draft = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                contract,
                event_id="event:authority:draft",
                parents=(grant_event.event_id,),
            )
        )
        proposed = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.proposed",
                contract,
                event_id="event:authority:proposed",
                parents=(draft.event_id,),
                authority=authority,
                representation_grant=grant,
            )
        )
        with assert_relation_error(self, "transition_authority_scope_mismatch"):
            reduce_events(
                [grant_event, draft, proposed],
                fixture_objects(contract, issuer, authority, grant),
            )

    def test_representation_must_cover_action_scope_and_claimed_actor(self):
        contract = valid_contract_version()
        authority = valid_grant_authority_evidence()
        grant = mutate_and_rebind(
            valid_representation_grant("a"),
            {
                "allowed_lifecycle_actions": ["contract.activated"],
                "contract_scope": ["contract:other"],
            },
        )
        grant_event = granted_representation_event(
            authority, grant, "event:representation:grant"
        )
        draft = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                contract,
                event_id="event:representation:draft",
                parents=(grant_event.event_id,),
            )
        )
        proposed = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.proposed",
                contract,
                event_id="event:representation:proposed",
                parents=(draft.event_id,),
                authority=authority,
                representation_grant=grant,
                claimed_actor_ref="instance:fixture:wrong",
            )
        )
        with assert_relation_error(self, "representation_scope_mismatch"):
            reduce_events(
                [grant_event, draft, proposed],
                fixture_objects(contract, authority, grant),
            )

    def test_acceptance_grant_principal_must_equal_accepting_party(self):
        contract = valid_contract_version()
        authority = valid_grant_authority_evidence("a")
        authority_b = valid_grant_authority_evidence("b")
        grant_a = valid_representation_grant("a")
        grant_b = valid_representation_grant("b")
        acceptance = mutate_and_rebind(
            acceptance_for(contract, "a"),
            {
                "representation_grant_ref": grant_b["representation_grant_id"],
                "representation_grant_digest": grant_b["content_digest"],
            },
        )
        grant_event_a = granted_representation_event(
            authority, grant_a, "event:principal:grant:a"
        )
        grant_event_b = granted_representation_event(
            authority_b,
            grant_b,
            "event:principal:grant:b",
            (grant_event_a.event_id,),
        )
        draft = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                contract,
                event_id="event:principal:draft",
                parents=(grant_event_b.event_id,),
            )
        )
        proposed = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.proposed",
                contract,
                event_id="event:principal:proposed",
                parents=(draft.event_id,),
                authority=authority,
                representation_grant=grant_a,
            )
        )
        accepted = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.party_accepted",
                acceptance,
                subject_ref=contract["contract_id"],
                event_id="event:principal:accepted",
                parents=(proposed.event_id,),
                representation_grant=grant_b,
            )
        )
        with assert_relation_error(self, "representation_principal_mismatch"):
            reduce_events(
                [grant_event_a, grant_event_b, draft, proposed, accepted],
                fixture_objects(
                    contract,
                    authority,
                    authority_b,
                    grant_a,
                    grant_b,
                    acceptance,
                ),
            )

    def test_transition_authority_must_resolve_external_ancestry(self):
        contract = valid_contract_version()
        issuer = valid_grant_authority_evidence("a")
        authority = mutate_and_rebind(
            issuer,
            {
                "grant_authority_evidence_id": "grant-authority-evidence:descendant",
                "authority_source_ref": contract["contract_id"],
            },
        )
        grant = valid_representation_grant("a")
        grant_event = granted_representation_event(
            issuer, grant, "event:ancestry:grant"
        )
        draft = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                contract,
                event_id="event:ancestry:draft",
                parents=(grant_event.event_id,),
            )
        )
        proposed = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.proposed",
                contract,
                event_id="event:ancestry:proposed",
                parents=(draft.event_id,),
                authority=authority,
                representation_grant=grant,
            )
        )
        with assert_relation_error(self, "representation_authority_descendant"):
            reduce_events(
                [grant_event, draft, proposed],
                fixture_objects(contract, issuer, authority, grant),
            )

    def test_transition_authority_must_be_current_at_event_time(self):
        cases = (
            (
                "not-yet-valid",
                {
                    "valid_from": normalized_instant("1300000000", 0),
                    "expires_at": normalized_instant("3000000000", 0),
                },
                "transition_authority_inactive",
            ),
            (
                "expired",
                {
                    "valid_from": normalized_instant("900000000", 0),
                    "expires_at": normalized_instant("1100000000", 0),
                },
                "transition_authority_inactive",
            ),
            (
                "expiry-overlap",
                {
                    "valid_from": normalized_instant("900000000", 0),
                    "expires_at": normalized_instant("1200000000", 20),
                },
                "transition_authority_time_indeterminate",
            ),
        )
        for label, time_updates, code in cases:
            with self.subTest(label=label):
                contract = valid_contract_version()
                issuer = valid_grant_authority_evidence("a")
                authority = mutate_and_rebind(
                    issuer,
                    {
                        "grant_authority_evidence_id": f"grant-authority-evidence:{label}",
                        **time_updates,
                    },
                )
                grant = valid_representation_grant("a")
                grant_event = granted_representation_event(
                    issuer, grant, f"event:authority-time:{label}:grant"
                )
                draft = RelationContractEvent.from_dict(
                    valid_relation_contract_event(
                        "contract.drafted",
                        contract,
                        event_id=f"event:authority-time:{label}:draft",
                        parents=(grant_event.event_id,),
                    )
                )
                proposed = RelationContractEvent.from_dict(
                    valid_relation_contract_event(
                        "contract.proposed",
                        contract,
                        event_id=f"event:authority-time:{label}:proposed",
                        parents=(draft.event_id,),
                        authority=authority,
                        representation_grant=grant,
                    )
                )
                with assert_relation_error(self, code):
                    reduce_events(
                        [grant_event, draft, proposed],
                        fixture_objects(contract, issuer, authority, grant),
                    )

    def test_required_party_acceptances_derive_accepted_contract(self):
        contract = valid_contract_version()
        authority = valid_grant_authority_evidence("a")
        authority_b = valid_grant_authority_evidence("b")
        grant_a = valid_representation_grant("a")
        grant_b = valid_representation_grant("b")
        accept_a = acceptance_for(contract, "a")
        accept_b = acceptance_for(contract, "b")
        events = [
            RelationContractEvent.from_dict(
                valid_relation_contract_event(
                    "representation.granted",
                    grant_a,
                    event_id="event:required:grant:a",
                    authority=authority,
                )
            ),
            RelationContractEvent.from_dict(
                valid_relation_contract_event(
                    "representation.granted",
                    grant_b,
                    event_id="event:required:grant:b",
                    parents=("event:required:grant:a",),
                    authority=authority_b,
                )
            ),
            RelationContractEvent.from_dict(
                valid_relation_contract_event(
                    "contract.drafted",
                    contract,
                    event_id="event:draft",
                    parents=("event:required:grant:b",),
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
                contract,
                authority,
                authority_b,
                grant_a,
                grant_b,
                accept_a,
                accept_b,
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
        contract, authority, events, objects = active_v1_sequence()
        grant = valid_representation_grant("a")
        candidate = generic_profile_object(
            "arcp/authority-candidate/0.1",
            "candidate_id",
            "candidate:fixture:generic",
            contract_ref=contract["contract_id"],
            contract_digest=contract["content_digest"],
            active_lifecycle_head="event:contract:activate:v1",
        )
        events.extend(
            [
            valid_relation_contract_event(
                "authority_candidate.created",
                candidate,
                subject_ref=contract["contract_id"],
                event_id="event:candidate:created",
                parents=("event:contract:activate:v1",),
            ),
            valid_relation_contract_event(
                "representation.revoked",
                grant,
                event_id="event:representation:revoked",
                parents=("event:candidate:created",),
                authority=authority,
            ),
            ]
        )
        objects.update(fixture_objects(candidate))
        projection = reduce_events(
            [RelationContractEvent.from_dict(item) for item in events],
            objects,
        )
        self.assertEqual(
            projection.representation_states[grant["representation_grant_id"]],
            "revoked",
        )
        self.assertIn(candidate["content_digest"], projection.invalidated_candidate_digests)

    def test_relation_withdrawal_or_supersession_invalidates_relation_candidates(self):
        for kind in ("relation.withdrawn", "relation.superseded"):
            with self.subTest(kind=kind):
                contract, _, base_events, base_objects = active_v1_sequence()
                relation = mutate_and_rebind(
                    valid_relation_version(),
                    {"relation_class": "descriptive", "acceptance_rule": "none"},
                )
                grant = mutate_and_rebind(
                    valid_representation_grant("a"),
                    {
                        "representation_grant_id": "representation-grant:fixture:a:relation",
                        "allowed_lifecycle_actions": [kind],
                        "contract_scope": [],
                        "relation_scope": [relation["relation_id"]],
                    },
                )
                grant_authority = mutate_and_rebind(
                    valid_grant_authority_evidence(),
                    {
                        "grant_authority_evidence_id": "grant-authority-evidence:relation-grant",
                        "permitted_lifecycle_actions": ["representation.granted"],
                        "permitted_contract_scope": [grant["representation_grant_id"]],
                    },
                )
                relation_authority = mutate_and_rebind(
                    valid_grant_authority_evidence(),
                    {
                        "grant_authority_evidence_id": "grant-authority-evidence:relation-transition",
                        "permitted_lifecycle_actions": [kind],
                        "permitted_contract_scope": [relation["relation_id"]],
                    },
                )
                grant = mutate_and_rebind(
                    grant,
                    {"grant_authority_ref": grant_authority["grant_authority_evidence_id"]},
                )
                candidate = generic_profile_object(
                    "arcp/authority-candidate/0.1",
                    "candidate_id",
                    f"candidate:fixture:relation:{kind}",
                    contract_ref=contract["contract_id"],
                    contract_digest=contract["content_digest"],
                    active_lifecycle_head="event:contract:activate:v1",
                    relation_refs=[relation["relation_id"]],
                )
                grant_event = valid_relation_contract_event(
                    "representation.granted",
                    grant,
                    event_id=f"event:{kind}:grant",
                    parents=("event:contract:activate:v1",),
                    authority=grant_authority,
                )
                relation_event = valid_relation_contract_event(
                    "relation.recorded",
                    relation,
                    event_id=f"event:{kind}:recorded",
                    parents=(grant_event["event_id"],),
                )
                candidate_event = valid_relation_contract_event(
                    "authority_candidate.created",
                    candidate,
                    subject_ref=contract["contract_id"],
                    event_id=f"event:{kind}:candidate",
                    parents=(relation_event["event_id"],),
                )
                terminal_event = valid_relation_contract_event(
                    kind,
                    relation,
                    event_id=f"event:{kind}:terminal",
                    parents=(candidate_event["event_id"],),
                    authority=relation_authority,
                    representation_grant=grant,
                )
                events = [
                    RelationContractEvent.from_dict(item)
                    for item in base_events
                    + [grant_event, relation_event, candidate_event, terminal_event]
                ]
                objects = {
                    **base_objects,
                    **fixture_objects(
                        relation,
                        grant,
                        grant_authority,
                        relation_authority,
                        candidate,
                    ),
                }
                projection = reduce_events(events, objects)
                self.assertIn(
                    candidate["content_digest"],
                    projection.invalidated_candidate_digests,
                )


if __name__ == "__main__":
    unittest.main()
