from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib

from eml_wake.canonical import canonical_bytes


PROFILE_CANON = "arcp-relation-contract-json-nfc-codepoint-v1"
PROFILE_DOMAIN = b"ARCP-RELATION-CONTRACT\x00"


def independent_profile_digest(value, digest_field="content_digest"):
    core = {key: item for key, item in value.items() if key != digest_field}
    body = PROFILE_DOMAIN + PROFILE_CANON.encode("ascii") + b"\x00" + canonical_bytes(core)
    return f"sha256:{PROFILE_CANON}:" + hashlib.sha256(body).hexdigest()


def rebind_content_digest(value, digest_field="content_digest"):
    rebound = deepcopy(value)
    rebound[digest_field] = independent_profile_digest(rebound, digest_field)
    return rebound


def mutate_and_rebind(value, updates, digest_field="content_digest"):
    mutated = deepcopy(value)
    mutated.update(deepcopy(updates))
    return rebind_content_digest(mutated, digest_field)


def normalized_instant(value="1000", uncertainty_ns=0, **overrides):
    item = {
        "instant_ref": f"instant:fixture:{value}",
        "clock_profile_id": "clock:fixture:v1",
        "normalized_unix_ns": str(value),
        "uncertainty_ns": uncertainty_ns,
        "verification_status": "verified",
        "source_evidence_refs": [f"evidence:clock:{value}"],
    }
    item.update(deepcopy(overrides))
    return item


def valid_activation_policy(**overrides):
    value = {
        "schema": "arcp/activation-policy/0.1",
        "policy_id": "activation-policy:fixture:v1",
        "policy_version": "1",
        "max_risk": "R1",
        "max_activation_duration_ms": 86_400_000,
        "max_exit_notice_ms": 3_600_000,
        "max_clock_uncertainty_ns": 1_000_000_000,
        "allowed_evaluator_profiles": ["arcp-evaluator:fixture:v1"],
        "allowed_clock_profiles": ["clock:fixture:v1"],
        "require_revocable": True,
        "allow_redelegation": False,
        "allowed_residence_impact": ["none"],
        "allowed_continuity_impact": ["none"],
        "economic_terms_required": None,
        "content_digest": "",
    }
    return mutate_and_rebind(value, overrides)


def valid_party_pin(party="a", **overrides):
    value = {
        "schema": "arcp/party-evidence-pin/0.1",
        "party_ref": f"resident:fixture:{party}",
        "party_kind": "resident",
        "resolver_profile_id": "sedb-ral-public-view:v0.2",
        "resolver_schema_id": "schema:limen-ral-view:v0.2",
        "resolver_source_ref": "repository:sedb-ral",
        "resolver_source_digest": "sha256:" + "1" * 64,
        "state_view_digest": "sha256:" + "2" * 64,
        "state_head_ref": "ral-head:fixture:1",
        "party_status": "active",
        "binding_ref": f"binding:fixture:{party}:1",
        "binding_status": "active",
        "binding_ambiguity": False,
        "adapter_verification_status": "verified",
        "observed_time_ref": "instant:fixture:1000",
        "observed_time_status": "verified",
        "content_digest": "",
    }
    return mutate_and_rebind(value, overrides)


def valid_exit_path(party_ref="resident:fixture:a", **overrides):
    value = {
        "schema": "arcp/exit-path/0.1",
        "exit_path_id": f"exit-path:{party_ref}:notice",
        "authorized_party_refs": [party_ref],
        "trigger_kind": "unilateral_notice",
        "unilateral_allowed": True,
        "notice_duration_ms": 60_000,
        "max_effective_delay_ms": 120_000,
        "required_evidence_refs": [f"evidence:exit:{party_ref}"],
        "effects": "terminate_contract",
        "future_candidate_invalidation": "immediate",
        "content_digest": "",
    }
    return mutate_and_rebind(value, overrides)


def valid_survival_clause(**overrides):
    value = {
        "schema": "arcp/survival-clause/0.1",
        "survival_clause_id": "survival:fixture:audit",
        "class": "audit_retention",
        "scope": ["audit:fixture:contract"],
        "effective_after_termination": True,
        "expires_at": None,
        "future_authority": False,
        "content_digest": "",
    }
    return mutate_and_rebind(value, overrides)


def valid_termination_terms(**overrides):
    value = {
        "schema": "arcp/termination-terms/0.1",
        "terminal_event_kinds": ["contract.expired", "contract.terminated"],
        "terminal_precedence": True,
        "candidate_invalidation": "immediate",
        "preserve_audit_history": True,
        "commitment_disposition": "preserve_named_survival_clauses",
        "allowed_survival_clause_refs": ["survival:fixture:audit"],
        "content_digest": "",
    }
    return mutate_and_rebind(value, overrides)


def valid_relation_version(**overrides):
    value = {
        "schema": "arcp/relation-version/0.1",
        "relation_id": "relation:fixture:collaboration",
        "version": 1,
        "parent_version_digest": None,
        "relation_class": "consensual",
        "relation_type": "collaboration",
        "party_refs": ["resident:fixture:a", "resident:fixture:b"],
        "scope": ["workspace:fixture:shared"],
        "source_evidence_refs": ["evidence:relation:proposal"],
        "acceptance_rule": "all-named-parties",
        "not_claimed": ["relation_grants_authority"],
        "content_digest": "",
    }
    return mutate_and_rebind(value, overrides)


def valid_contract_version(**overrides):
    policy = valid_activation_policy()
    effective = normalized_instant("1000000000", 0)
    expires = normalized_instant("2000000000", 0)
    value = {
        "schema": "arcp/contract-version/0.1",
        "contract_id": "contract:fixture:collaboration",
        "version": 1,
        "parent_version_digest": None,
        "relation_version_ref": "relation:fixture:collaboration:v1",
        "relation_version_digest": valid_relation_version()["content_digest"],
        "party_terms": [
            {
                "party_ref": "resident:fixture:a",
                "role": "collaborator",
                "acceptance_required": True,
                "standing_entity": True,
                "representation_scope": ["contract.accept"],
            },
            {
                "party_ref": "resident:fixture:b",
                "role": "collaborator",
                "acceptance_required": True,
                "standing_entity": True,
                "representation_scope": ["contract.accept"],
            },
        ],
        "scope": ["resource:fixture:shared#read"],
        "commitment_specs": [],
        "authority_candidate_specs": [
            {
                "subject_entity_ref": "resident:fixture:a",
                "requested_resource_scope": ["resource:fixture:shared#read"],
                "requested_action_scope": ["workspace.inspect"],
                "risk": "R1",
            }
        ],
        "constraints": ["offline_only"],
        "risk_ceiling": "R1",
        "activation_policy_ref": policy["policy_id"],
        "activation_policy_digest": policy["content_digest"],
        "approval_mode": "all-named-parties",
        "effective_not_before": effective,
        "expires_at": expires,
        "review_at": None,
        "revocable": True,
        "redelegable": False,
        "termination_terms": valid_termination_terms(),
        "exit_paths": [
            valid_exit_path("resident:fixture:a"),
            valid_exit_path("resident:fixture:b"),
        ],
        "survival_clauses": [valid_survival_clause()],
        "succession_policy": "explicit_acceptance_only",
        "residence_impact": "none",
        "continuity_impact": "none",
        "continuity_precondition": "none",
        "economic_terms_ref": None,
        "content_digest": "",
    }
    return mutate_and_rebind(value, overrides)


def valid_grant_authority_evidence(party="a", **overrides):
    value = {
        "schema": "arcp/grant-authority-evidence/0.1",
        "grant_authority_evidence_id": f"grant-authority-evidence:fixture:{party}",
        "grantor_party_ref": f"resident:fixture:{party}",
        "authority_source_ref": f"authority-root:fixture:{party}",
        "resolver_profile_id": "authority-resolver:fixture:v1",
        "permitted_lifecycle_actions": ["contract.proposed", "contract.party_accepted"],
        "permitted_contract_scope": ["contract:fixture:collaboration"],
        "valid_from": normalized_instant("900", 0),
        "expires_at": normalized_instant("3000", 0),
        "dependency_refs": [],
        "content_digest": "",
    }
    return mutate_and_rebind(value, overrides)


def valid_representation_grant(party="a", **overrides):
    value = {
        "schema": "arcp/representation-grant/0.1",
        "representation_grant_id": f"representation-grant:fixture:{party}:1",
        "principal_party_ref": f"resident:fixture:{party}",
        "representative_ref": f"instance:fixture:{party}:1",
        "representative_kind": "instance",
        "allowed_lifecycle_actions": ["contract.proposed", "contract.party_accepted"],
        "contract_scope": ["contract:fixture:collaboration"],
        "relation_scope": ["relation:fixture:collaboration"],
        "valid_from": normalized_instant("1000", 0),
        "expires_at": normalized_instant("2500", 0),
        "issued_at": normalized_instant("950", 0),
        "revocable": True,
        "redelegable": False,
        "grant_authority_ref": f"grant-authority-evidence:fixture:{party}",
        "acceptance_evidence_refs": [f"evidence:representation:accepted:{party}"],
        "party_evidence_pin_refs": [f"party-evidence-pin:fixture:{party}:1"],
        "content_digest": "",
    }
    return mutate_and_rebind(value, overrides)


def valid_party_acceptance(party="a", **overrides):
    target_kind = overrides.get("target_kind", "contract")
    target_id = (
        "relation:fixture:collaboration"
        if target_kind == "relation"
        else "contract:fixture:collaboration"
    )
    target_digest = (
        valid_relation_version()["content_digest"]
        if target_kind == "relation"
        else valid_contract_version()["content_digest"]
    )
    value = {
        "schema": "arcp/party-acceptance/0.1",
        "acceptance_id": f"acceptance:fixture:{party}:{target_kind}:v1",
        "party_ref": f"resident:fixture:{party}",
        "target_kind": target_kind,
        "target_id": target_id,
        "target_version": 1,
        "target_digest": target_digest,
        "representation_grant_ref": f"representation-grant:fixture:{party}:1",
        "representation_grant_digest": valid_representation_grant(party)["content_digest"],
        "party_evidence_pin_refs": [f"party-evidence-pin:fixture:{party}:1"],
        "acceptance_evidence_refs": [f"evidence:acceptance:{party}:1"],
        "acceptance_evidence_root_refs": [f"evidence-root:acceptance:{party}"],
        "accepted_at": normalized_instant("1100", 0),
        "content_digest": "",
    }
    return mutate_and_rebind(value, overrides)


EVENT_NONCLAIMS = [
    "capability_granted",
    "economic_compensation",
    "global_causal_order",
    "provider_execution",
    "resident_identity_continuity",
]

AUTHORITY_REQUIRED_EVENT_KINDS = {
    "relation.proposed",
    "relation.withdrawn",
    "relation.superseded",
    "contract.proposed",
    "contract.withdrawn",
    "contract.activated",
    "contract.amendment_proposed",
    "contract.suspended",
    "contract.resumed",
    "contract.terminated",
    "contract.corrected",
    "contract.tombstoned",
    "representation.granted",
    "representation.suspended",
    "representation.revoked",
}


def object_ref(value):
    for field in (
        "relation_id",
        "contract_id",
        "acceptance_id",
        "representation_grant_id",
        "commitment_id",
        "candidate_id",
        "receipt_id",
    ):
        if field in value:
            return value[field]
    raise KeyError("fixture object has no reference field")


def generic_profile_object(schema, id_field, identifier, **overrides):
    value = {
        "schema": schema,
        id_field: identifier,
        "content_digest": "",
    }
    return mutate_and_rebind(value, overrides)


def valid_relation_contract_event(
    event_kind,
    object_value,
    *,
    event_id,
    subject_ref=None,
    parents=(),
    authority=None,
    representation_grant=None,
    supersedes_active_head=None,
    **overrides,
):
    if authority is None and event_kind in AUTHORITY_REQUIRED_EVENT_KINDS:
        authority = valid_grant_authority_evidence()
    activation = event_kind == "contract.activated"
    value = {
        "schema": "arcp/relation-contract-event/0.1",
        "event_id": event_id,
        "event_kind": event_kind,
        "subject_ref": subject_ref or object_ref(object_value),
        "object_ref": object_ref(object_value),
        "object_digest": object_value["content_digest"],
        "causal_parents": list(parents),
        "claimed_actor_ref": "actor:fixture:a",
        "representation_grant_ref": (
            None
            if representation_grant is None
            else representation_grant["representation_grant_id"]
        ),
        "representation_grant_digest": (
            None if representation_grant is None else representation_grant["content_digest"]
        ),
        "lifecycle_transition_authority_ref": (
            None if authority is None else authority["grant_authority_evidence_id"]
        ),
        "lifecycle_transition_authority_digest": (
            None if authority is None else authority["content_digest"]
        ),
        "supersedes_active_head": supersedes_active_head,
        "acceptance_set_digest": (
            independent_profile_digest({"set": "acceptance"}) if activation else None
        ),
        "representation_set_digest": (
            independent_profile_digest({"set": "representation"}) if activation else None
        ),
        "party_evidence_set_digest": (
            independent_profile_digest({"set": "party-evidence"}) if activation else None
        ),
        "activation_policy_digest": (
            valid_activation_policy()["content_digest"] if activation else None
        ),
        "created_time": normalized_instant("1200", 0),
        "local_recorded_at": "2026-08-26T01:00:00Z",
        "correction_of": None,
        "withdraws": None,
        "not_claimed": list(EVENT_NONCLAIMS),
    }
    value.update(deepcopy(overrides))
    return value


def fixture_objects(*values):
    result = {}
    for value in values:
        result[value["content_digest"]] = deepcopy(value)
    return result


@contextmanager
def assert_relation_error(testcase, code):
    from eml_pmw.relations.errors import RelationContractError

    with testcase.assertRaises(RelationContractError) as caught:
        yield
    testcase.assertEqual(caught.exception.code, code)
