from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any

from eml_wake.canonical import canonical_bytes, loads_strict

from .errors import FederationError
from .models import FederatedEvent, RealmRef, ReplicaRef, REQUIRED_NONCLAIMS


ADAPTER_CANON = "pmw-ral-adapter-json-nfc-codepoint-v1"
ADAPTER_DOMAIN = b"PMW-RAL-ADAPTER\x00"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64_LOWER = re.compile(r"^[0-9a-f]{64}$")
ADAPTER_DIGEST = re.compile(
    rf"^sha256:{re.escape(ADAPTER_CANON)}:[0-9a-f]{{64}}$"
)
RAL_DIGEST = re.compile(r"^sha256:sedb-ral-json-nfc-codepoint-v1:[0-9a-f]{64}$")
FIELDS = {
    "schema",
    "adapter_profile_id",
    "source_manifest_schema",
    "source_manifest_digest",
    "source_schema_id",
    "source_schema_version",
    "source_repository",
    "source_commit",
    "source_schema_bytes",
    "source_schema_sha256",
    "source_profile_ref",
    "carrier_event_kind",
    "subject_mapping",
    "ral_disclosure_class",
    "fabric_payload_class",
    "correction_mapping",
    "tombstone_mapping",
    "not_claimed",
    "manifest_digest",
}
NOT_CLAIMED = (
    "ral_schema_vendored",
    "ral_authority_activated",
    "ral_head_mutated",
    "private_access",
)


def ral_adapter_digest(value: dict[str, Any]) -> str:
    core = {key: item for key, item in value.items() if key != "manifest_digest"}
    body = (
        ADAPTER_DOMAIN
        + ADAPTER_CANON.encode("ascii")
        + b"\x00"
        + canonical_bytes(core)
    )
    return f"sha256:{ADAPTER_CANON}:" + hashlib.sha256(body).hexdigest()


@dataclass(frozen=True)
class RalAdapterManifest:
    schema: str
    adapter_profile_id: str
    source_manifest_schema: str
    source_manifest_digest: str
    source_schema_id: str
    source_schema_version: str
    source_repository: str
    source_commit: str
    source_schema_bytes: int
    source_schema_sha256: str
    source_profile_ref: str
    carrier_event_kind: str
    subject_mapping: dict[str, str]
    ral_disclosure_class: str
    fabric_payload_class: str
    correction_mapping: str
    tombstone_mapping: str
    not_claimed: tuple[str, ...]
    manifest_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RalAdapterManifest":
        if not isinstance(value, dict):
            raise FederationError("contract_type_invalid", "RAL adapter manifest")
        unknown = sorted(set(value) - FIELDS)
        missing = sorted(FIELDS - set(value))
        if unknown:
            raise FederationError("unknown_field", unknown[0])
        if missing:
            raise FederationError("missing_field", missing[0])
        item = cls(
            value["schema"],
            value["adapter_profile_id"],
            value["source_manifest_schema"],
            value["source_manifest_digest"],
            value["source_schema_id"],
            value["source_schema_version"],
            value["source_repository"],
            value["source_commit"],
            value["source_schema_bytes"],
            value["source_schema_sha256"],
            value["source_profile_ref"],
            value["carrier_event_kind"],
            value["subject_mapping"],
            value["ral_disclosure_class"],
            value["fabric_payload_class"],
            value["correction_mapping"],
            value["tombstone_mapping"],
            tuple(value["not_claimed"]),
            value["manifest_digest"],
        )
        item._validate()
        return item

    def _validate(self) -> None:
        strings = (
            self.adapter_profile_id,
            self.source_manifest_schema,
            self.source_schema_id,
            self.source_schema_version,
            self.source_repository,
            self.source_profile_ref,
            self.carrier_event_kind,
        )
        if any(not isinstance(value, str) or not value for value in strings):
            raise FederationError("manifest_field_invalid", self.adapter_profile_id)
        if self.schema != "pmw.ral-public-projection-adapter/v1":
            raise FederationError("schema_version_unsupported", self.schema)
        if not RAL_DIGEST.fullmatch(self.source_manifest_digest):
            raise FederationError("source_manifest_digest_invalid", self.adapter_profile_id)
        if not HEX40.fullmatch(self.source_commit):
            raise FederationError("source_commit_invalid", self.source_commit)
        if (
            isinstance(self.source_schema_bytes, bool)
            or not isinstance(self.source_schema_bytes, int)
            or self.source_schema_bytes < 1
        ):
            raise FederationError("source_schema_bytes_invalid", self.adapter_profile_id)
        if not HEX64_LOWER.fullmatch(self.source_schema_sha256):
            raise FederationError("source_schema_digest_invalid", self.adapter_profile_id)
        if self.subject_mapping != {
            "source_field": "view_id",
            "target_template": "ral-public-view:{realm_id}:{view_id}",
        }:
            raise FederationError("subject_mapping_unsupported", self.adapter_profile_id)
        if self.ral_disclosure_class != "public":
            raise FederationError("ral_disclosure_not_public", self.adapter_profile_id)
        if self.fabric_payload_class != "P0":
            raise FederationError("fabric_payload_class_invalid", self.fabric_payload_class)
        if self.correction_mapping != "source_semantics_preserved" or self.tombstone_mapping != "source_semantics_preserved":
            raise FederationError("source_semantics_mapping_invalid", self.adapter_profile_id)
        if self.not_claimed != NOT_CLAIMED:
            raise FederationError("not_claimed_incomplete", self.adapter_profile_id)
        if not isinstance(self.manifest_digest, str) or not ADAPTER_DIGEST.fullmatch(self.manifest_digest):
            raise FederationError("manifest_digest_invalid", self.adapter_profile_id)
        if self.manifest_digest != ral_adapter_digest(self.to_dict()):
            raise FederationError("manifest_digest_mismatch", self.adapter_profile_id)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["not_claimed"] = list(self.not_claimed)
        return value


def verify_ral_schema_pin(
    manifest: RalAdapterManifest, schema_bytes: bytes
) -> dict[str, Any]:
    if len(schema_bytes) != manifest.source_schema_bytes or hashlib.sha256(
        schema_bytes
    ).hexdigest() != manifest.source_schema_sha256:
        raise FederationError("ral_schema_digest_mismatch", manifest.source_schema_id)
    try:
        value = loads_strict(schema_bytes)
    except Exception as error:
        raise FederationError("ral_schema_invalid", manifest.source_schema_id) from error
    if not isinstance(value, dict) or value.get("$id") != manifest.source_schema_id:
        raise FederationError("ral_schema_id_mismatch", manifest.source_schema_id)
    return value


def ral_view_to_event(
    manifest: RalAdapterManifest,
    view_bytes: bytes,
    realm_ref: RealmRef,
    replica_ref: ReplicaRef,
    replica_seq: int,
) -> FederatedEvent:
    try:
        view = loads_strict(view_bytes)
    except Exception as error:
        raise FederationError("ral_view_invalid", manifest.adapter_profile_id) from error
    if not isinstance(view, dict) or view_bytes != canonical_bytes(view):
        raise FederationError("ral_view_not_canonical", manifest.adapter_profile_id)
    if view.get("schema") != "limen.ral-view/0.2" or not isinstance(
        view.get("view_id"), str
    ) or not view["view_id"]:
        raise FederationError("ral_view_contract_mismatch", manifest.adapter_profile_id)
    if "ledger_head" not in view or "not_claimed" not in view:
        raise FederationError("ral_view_contract_mismatch", manifest.adapter_profile_id)
    payload_hash = hashlib.sha256(view_bytes).hexdigest()
    subject_ref = manifest.subject_mapping["target_template"].format(
        realm_id=realm_ref.realm_id,
        view_id=view[manifest.subject_mapping["source_field"]],
    )
    return FederatedEvent.from_dict(
        {
            "schema": "pmw-federated-event/v1",
            "event_id": f"event:ral-public-view:{payload_hash}",
            "event_kind": manifest.carrier_event_kind,
            "subject_ref": subject_ref,
            "realm_ref": {
                **asdict(realm_ref),
                "evidence_refs": list(realm_ref.evidence_refs),
            },
            "replica_ref": {
                **asdict(replica_ref),
                "evidence_refs": list(replica_ref.evidence_refs),
            },
            "replica_seq": replica_seq,
            "causal_parents": [],
            "claimed_actor_ref": None,
            "claimed_instance_ref": None,
            "authority_ref": None,
            "payload_ref": f"payloads/{payload_hash}.json",
            "payload_sha256": payload_hash.upper(),
            "payload_media_type": "application/json",
            "fabric_payload_class": manifest.fabric_payload_class,
            "created_time_ref": None,
            "temporal_evidence_status": "unmeasured",
            "local_recorded_at": "unmeasured",
            "correction_of": None,
            "withdraws": None,
            "not_claimed": sorted(REQUIRED_NONCLAIMS),
        }
    )
