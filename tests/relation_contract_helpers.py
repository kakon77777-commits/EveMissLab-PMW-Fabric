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


@contextmanager
def assert_relation_error(testcase, code):
    from eml_pmw.relations.errors import RelationContractError

    with testcase.assertRaises(RelationContractError) as caught:
        yield
    testcase.assertEqual(caught.exception.code, code)
