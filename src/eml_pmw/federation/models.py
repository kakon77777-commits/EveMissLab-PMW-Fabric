from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from eml_wake.canonical import canonical_bytes

from .canonical import event_digest
from .errors import FederationError

CTCL = re.compile(r"^ctcl:instant:[0-9a-f-]{36}$", re.IGNORECASE)
HEX64 = re.compile(r"^[0-9A-F]{64}$")
EVENT_FIELDS = {
    "schema", "event_id", "event_kind", "subject_ref", "realm_ref", "replica_ref",
    "replica_seq", "causal_parents", "claimed_actor_ref", "claimed_instance_ref",
    "authority_ref", "payload_ref", "payload_sha256", "payload_media_type",
    "created_time_ref", "temporal_evidence_status", "local_recorded_at",
    "correction_of", "withdraws", "not_claimed",
}
REQUIRED_NONCLAIMS = {
    "actor_authorship_verified", "resident_identity_continuity", "global_causal_order",
    "remote_adoption", "authority_to_execute", "payload_understood", "conflict_resolved",
}
CONFIG_FIELDS = {
    "schema", "local_realm_id", "local_replica_id", "allowed_source_roots",
    "allowed_event_kinds", "authority_required_event_kinds", "allowed_authority_refs",
    "default_max_payload_bytes", "hard_max_payload_bytes", "strict_reparse_checks",
}


def _exact(value: dict[str, Any], fields: set[str]) -> None:
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown:
        raise FederationError("unknown_field", unknown[0])
    if missing:
        raise FederationError("missing_field", missing[0])


def _unique_strings(value, field):
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise FederationError("field_type_invalid", field)
    if len(value) != len(set(value)):
        raise FederationError("duplicate_list_item", field)
    return tuple(value)


@dataclass(frozen=True)
class FederationConfig:
    schema: str
    local_realm_id: str
    local_replica_id: str
    allowed_source_roots: tuple[str, ...]
    allowed_event_kinds: tuple[str, ...]
    authority_required_event_kinds: tuple[str, ...]
    allowed_authority_refs: tuple[str, ...]
    default_max_payload_bytes: int
    hard_max_payload_bytes: int
    strict_reparse_checks: bool

    @classmethod
    def from_dict(cls, value):
        _exact(value, CONFIG_FIELDS)
        item = cls(
            value["schema"], value["local_realm_id"], value["local_replica_id"],
            _unique_strings(value["allowed_source_roots"], "allowed_source_roots"),
            _unique_strings(value["allowed_event_kinds"], "allowed_event_kinds"),
            _unique_strings(value["authority_required_event_kinds"], "authority_required_event_kinds"),
            _unique_strings(value["allowed_authority_refs"], "allowed_authority_refs"),
            value["default_max_payload_bytes"], value["hard_max_payload_bytes"],
            value["strict_reparse_checks"],
        )
        if item.schema != "pmw-federation-config/v1":
            raise FederationError("schema_version_unsupported", item.schema)
        if not set(item.authority_required_event_kinds) <= set(item.allowed_event_kinds):
            raise FederationError("authority_event_kind_not_allowed", "config")
        if isinstance(item.default_max_payload_bytes, bool) or isinstance(item.hard_max_payload_bytes, bool) or not isinstance(item.default_max_payload_bytes, int) or not isinstance(item.hard_max_payload_bytes, int) or not 0 < item.default_max_payload_bytes <= item.hard_max_payload_bytes <= 4_194_304:
            raise FederationError("payload_limit_invalid", "config")
        if not isinstance(item.strict_reparse_checks, bool):
            raise FederationError("field_type_invalid", "strict_reparse_checks")
        return item

    def to_dict(self):
        value = asdict(self)
        for field in ("allowed_source_roots", "allowed_event_kinds", "authority_required_event_kinds", "allowed_authority_refs"):
            value[field] = list(value[field])
        return value


@dataclass(frozen=True)
class RealmRef:
    realm_id: str
    realm_kind: str
    issuer: str
    verification_status: str
    evidence_refs: tuple[str, ...]

    @classmethod
    def from_dict(cls, value):
        expected = {"realm_id", "realm_kind", "issuer", "verification_status", "evidence_refs"}
        _exact(value, expected)
        item = cls(value["realm_id"], value["realm_kind"], value["issuer"], value["verification_status"], tuple(value["evidence_refs"]))
        if item.realm_kind not in {"windows_host", "cloud_host", "hdus_host", "embodied_host", "fixture"}:
            raise FederationError("realm_kind_invalid", item.realm_kind)
        if item.verification_status in {"verified", "observed"} and not item.evidence_refs:
            raise FederationError("reference_evidence_missing", item.realm_id)
        return item


@dataclass(frozen=True)
class ReplicaRef:
    replica_id: str
    realm_id: str
    store_generation: str
    verification_status: str
    evidence_refs: tuple[str, ...]

    @classmethod
    def from_dict(cls, value):
        expected = {"replica_id", "realm_id", "store_generation", "verification_status", "evidence_refs"}
        _exact(value, expected)
        item = cls(value["replica_id"], value["realm_id"], value["store_generation"], value["verification_status"], tuple(value["evidence_refs"]))
        if item.verification_status in {"verified", "observed"} and not item.evidence_refs:
            raise FederationError("reference_evidence_missing", item.replica_id)
        return item


@dataclass(frozen=True)
class FederatedEvent:
    schema: str
    event_id: str
    event_kind: str
    subject_ref: str
    realm_ref: RealmRef
    replica_ref: ReplicaRef
    replica_seq: int
    causal_parents: tuple[str, ...]
    claimed_actor_ref: str | None
    claimed_instance_ref: str | None
    authority_ref: str | None
    payload_ref: str
    payload_sha256: str
    payload_media_type: str
    created_time_ref: str | None
    temporal_evidence_status: str
    local_recorded_at: str
    correction_of: str | None
    withdraws: str | None
    not_claimed: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]):
        _exact(value, EVENT_FIELDS)
        item = cls(
            value["schema"], value["event_id"], value["event_kind"], value["subject_ref"],
            RealmRef.from_dict(value["realm_ref"]), ReplicaRef.from_dict(value["replica_ref"]),
            value["replica_seq"], tuple(value["causal_parents"]), value["claimed_actor_ref"],
            value["claimed_instance_ref"], value["authority_ref"], value["payload_ref"],
            value["payload_sha256"], value["payload_media_type"], value["created_time_ref"],
            value["temporal_evidence_status"], value["local_recorded_at"], value["correction_of"],
            value["withdraws"], tuple(value["not_claimed"]),
        )
        if item.schema != "pmw-federated-event/v1":
            raise FederationError("schema_version_unsupported", item.schema)
        if isinstance(item.replica_seq, bool) or not isinstance(item.replica_seq, int) or item.replica_seq < 1:
            raise FederationError("replica_seq_invalid", str(item.replica_seq))
        if item.realm_ref.realm_id != item.replica_ref.realm_id:
            raise FederationError("event_realm_replica_mismatch", item.event_id)
        if len(set(item.causal_parents)) != len(item.causal_parents) or item.event_id in item.causal_parents:
            raise FederationError("causal_parents_invalid", item.event_id)
        if not HEX64.fullmatch(item.payload_sha256):
            raise FederationError("payload_digest_invalid", item.payload_sha256)
        if not item.payload_ref.startswith("payloads/") or ".." in item.payload_ref or "\\" in item.payload_ref:
            raise FederationError("payload_ref_invalid", item.payload_ref)
        if item.payload_media_type not in {"application/json", "text/markdown", "text/plain"}:
            raise FederationError("payload_media_type_invalid", item.payload_media_type)
        if item.temporal_evidence_status == "registered_anchor":
            if not isinstance(item.created_time_ref, str) or not CTCL.fullmatch(item.created_time_ref):
                raise FederationError("temporal_evidence_mismatch", item.event_id)
        elif item.temporal_evidence_status in {"unavailable", "unmeasured"}:
            if item.created_time_ref is not None:
                raise FederationError("temporal_evidence_mismatch", item.event_id)
        else:
            raise FederationError("temporal_evidence_status_invalid", item.temporal_evidence_status)
        if not REQUIRED_NONCLAIMS <= set(item.not_claimed):
            raise FederationError("not_claimed_incomplete", item.event_id)
        return item

    def to_dict(self):
        value = asdict(self)
        value["causal_parents"] = list(self.causal_parents)
        value["not_claimed"] = list(self.not_claimed)
        value["realm_ref"]["evidence_refs"] = list(self.realm_ref.evidence_refs)
        value["replica_ref"]["evidence_refs"] = list(self.replica_ref.evidence_refs)
        return value

    @property
    def core_digest(self):
        return event_digest(self.to_dict())

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())
