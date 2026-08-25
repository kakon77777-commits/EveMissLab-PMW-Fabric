from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json

from eml_wake.canonical import canonical_bytes

from eml_pmw.federation.errors import FederationError


PAYLOAD = b'{"field":"status","value":"open"}'

VISIBILITY_CANON = "pmw-adapter-visibility-json-nfc-codepoint-v1"
VISIBILITY_DOMAIN = b"PMW-ADAPTER-VISIBILITY\x00"
VISIBILITY_BARRIERS = [
    "turn_completed_does_not_imply_adapter_body_available",
    "empty_projection_does_not_imply_no_response",
    "local_capture_does_not_prove_portable_delivery",
    "materialized_handoff_does_not_prove_original_adapter_delivery",
    "delivery_or_materialization_does_not_prove_authorship_or_identity",
    "no_automatic_resend_from_empty_projection",
]


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
        "fabric_payload_class": "P0",
        "created_time_ref": None,
        "temporal_evidence_status": "unavailable",
        "local_recorded_at": "2026-08-25T00:00:00Z",
        "correction_of": None,
        "withdraws": None,
        "not_claimed": ["actor_authorship_verified", "resident_identity_continuity", "global_causal_order", "remote_adoption", "authority_to_execute", "payload_understood", "conflict_resolved"],
    }
    value.update(deepcopy(overrides))
    return value


def event_at(sequence, event_id, parents=(), **overrides):
    value = valid_event(
        event_id=event_id,
        replica_seq=sequence,
        causal_parents=list(parents),
        **overrides,
    )
    return value


def event_for_replica(replica, sequence, event_id, parents=(), **overrides):
    realm_id = f"realm:{replica}"
    return event_at(
        sequence,
        event_id,
        parents,
        realm_ref={
            "realm_id": realm_id,
            "realm_kind": "fixture",
            "issuer": "fixture",
            "verification_status": "verified",
            "evidence_refs": [f"fixture:realm:{replica}"],
        },
        replica_ref={
            "replica_id": f"replica:{replica}",
            "realm_id": realm_id,
            "store_generation": "generation:1",
            "verification_status": "verified",
            "evidence_refs": [f"fixture:replica:{replica}"],
        },
        **overrides,
    )


def observer(**overrides):
    value = {
        "observer_id": "observer:realm-b:fixture",
        "realm_id": "realm:b",
        "method": "local_file_read",
        "observed_origin": None,
        "observed_time_ref": None,
        "advertised_missing_parent_ids": [],
    }
    value.update(deepcopy(overrides))
    return value


def update_event(replica, value, *, field="status", subject_ref="pmw-task:fixture", event_kind="pmw.task.field_set", authority_ref="authority:fixture"):
    payload = json.dumps(
        {"field": field, "value": value},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    event = event_for_replica(
        replica,
        1,
        f"event:{replica}:{field}:{value}",
        event_kind=event_kind,
        subject_ref=subject_ref,
        authority_ref=authority_ref,
        payload_ref=f"payloads/{replica}-{field}-{value}.json",
        payload_sha256=hashlib.sha256(payload).hexdigest().upper(),
    )
    return event, payload


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


def _visibility_digest(value):
    core = {key: deepcopy(item) for key, item in value.items() if key != "evidence_digest"}
    body = (
        VISIBILITY_DOMAIN
        + VISIBILITY_CANON.encode("ascii")
        + b"\x00"
        + canonical_bytes(core)
    )
    return f"sha256:{VISIBILITY_CANON}:" + hashlib.sha256(body).hexdigest()


def valid_visibility_evidence(**overrides):
    value = {
        "schema": "pmw.adapter-visibility-evidence/0.1",
        "evidence_id": "visibility:codex-read-thread:2026-08-25:01",
        "subject_task_ref": "codex-thread:01a02e70-e100-71b3-8c55-02858d7cc854",
        "subject_turn_ref": "codex-turn:01a038cd-c55d-7003-a327-405cc8392495",
        "adapter_kind": "codex_app.read_thread",
        "adapter_call_count": 2,
        "execution_state": "completed",
        "adapter_read_outcome": "empty_projection",
        "adapter_item_count": 0,
        "adapter_error_code": None,
        "local_capture_state": "body_observed",
        "local_capture_kind": "native_transcript",
        "local_capture_portability": "local_only",
        "materialization_state": "verified",
        "materialized_artifact_ref": "runtime/task-handoffs/2026-08-25_01a02e70_to_019fe51e_orientation-reconciliation.md",
        "materialized_artifact_sha256": "68E066153F96EE8DF61CDBAADEB5A4E393A7DAB44133038E0728432BF5A42CF3",
        "materialized_artifact_bytes": 6552,
        "portable_delivery_state": "not_proven",
        "authorship_state": "unmeasured",
        "reconciliation_state": "locally_reconciled",
        "inference_barriers": deepcopy(VISIBILITY_BARRIERS),
        "observed_time_ref": None,
    }
    value.update(deepcopy(overrides))
    value["evidence_digest"] = _visibility_digest(value)
    return value
