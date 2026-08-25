from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib

from eml_pmw.federation.errors import FederationError


PAYLOAD = b'{"field":"status","value":"open"}'


@contextmanager
def assert_error_code(testcase, code):
    with testcase.assertRaises(FederationError) as caught:
        yield
    testcase.assertEqual(caught.exception.code, code)


def valid_event(**overrides):
    value = {
        "schema": "pmw-federated-event/v1",
        "event_id": "event:fixture:1",
        "event_kind": "pmw.task.field_set",
        "subject_ref": "pmw-task:fixture",
        "realm_ref": {"realm_id": "realm:a", "realm_kind": "fixture", "issuer": "fixture", "verification_status": "verified", "evidence_refs": ["fixture:realm"]},
        "replica_ref": {"replica_id": "replica:a", "realm_id": "realm:a", "store_generation": "generation:1", "verification_status": "verified", "evidence_refs": ["fixture:replica"]},
        "replica_seq": 1,
        "causal_parents": [],
        "claimed_actor_ref": "actor:fixture",
        "claimed_instance_ref": "instance:fixture",
        "authority_ref": "authority:fixture",
        "payload_ref": "payloads/fixture.json",
        "payload_sha256": hashlib.sha256(PAYLOAD).hexdigest().upper(),
        "payload_media_type": "application/json",
        "created_time_ref": None,
        "temporal_evidence_status": "unavailable",
        "local_recorded_at": "2026-08-25T00:00:00Z",
        "correction_of": None,
        "withdraws": None,
        "not_claimed": ["actor_authorship_verified", "resident_identity_continuity", "global_causal_order", "remote_adoption", "authority_to_execute", "payload_understood", "conflict_resolved"],
    }
    value.update(deepcopy(overrides))
    return value


def valid_config(**overrides):
    value = {
        "schema": "pmw-federation-config/v1",
        "local_realm_id": "realm:a",
        "local_replica_id": "replica:a",
        "allowed_source_roots": ["C:/fixture/shared"],
        "allowed_event_kinds": ["pmw.task.field_set", "pmw.observation"],
        "authority_required_event_kinds": ["pmw.task.field_set"],
        "allowed_authority_refs": ["authority:fixture"],
        "default_max_payload_bytes": 1048576,
        "hard_max_payload_bytes": 4194304,
        "strict_reparse_checks": True,
    }
    value.update(deepcopy(overrides))
    return value
