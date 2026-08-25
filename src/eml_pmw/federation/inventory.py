from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any

from eml_wake.canonical import canonical_bytes

from .store import FederationStore


INVENTORY_CANON = "pmw-federation-inventory-json-nfc-codepoint-v1"
INVENTORY_DOMAIN = b"PMW-FEDERATION-INVENTORY\x00"
INVENTORY_NONCLAIMS = (
    "payload_body_included",
    "bearer_token_included",
    "private_memory_included",
    "resident_identity_verified",
    "global_causal_order",
    "remote_adoption",
)


def _digest(value: dict[str, Any]) -> str:
    body = (
        INVENTORY_DOMAIN
        + INVENTORY_CANON.encode("ascii")
        + b"\x00"
        + canonical_bytes(value)
    )
    return f"sha256:{INVENTORY_CANON}:" + hashlib.sha256(body).hexdigest()


@dataclass(frozen=True)
class InventoryEventRecord:
    event_id: str
    event_digest: str
    replica_id: str
    store_generation: str
    replica_seq: int
    causal_parents: tuple[str, ...]
    payload_sha256: str
    payload_bytes: int
    fabric_payload_class: str
    availability: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["causal_parents"] = list(self.causal_parents)
        return value


@dataclass(frozen=True)
class ReplicaRange:
    replica_id: str
    store_generation: str
    minimum_sequence: int
    maximum_sequence: int
    event_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FederationInventory:
    schema: str
    inventory_id: str
    generated_by_realm_id: str
    events: tuple[InventoryEventRecord, ...]
    replica_ranges: tuple[ReplicaRange, ...]
    causal_heads: tuple[str, ...]
    not_claimed: tuple[str, ...]
    inventory_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "inventory_id": self.inventory_id,
            "generated_by_realm_id": self.generated_by_realm_id,
            "events": [record.to_dict() for record in self.events],
            "replica_ranges": [record.to_dict() for record in self.replica_ranges],
            "causal_heads": list(self.causal_heads),
            "not_claimed": list(self.not_claimed),
            "inventory_digest": self.inventory_digest,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())


@dataclass(frozen=True)
class InventoryDiff:
    missing_from_local: tuple[str, ...]
    missing_from_remote: tuple[str, ...]
    digest_mismatches: tuple[str, ...]


def build_inventory(store: FederationStore) -> FederationInventory:
    events = store.events()
    records: list[InventoryEventRecord] = []
    ranges: dict[tuple[str, str], list[int]] = {}
    parent_ids: set[str] = set()
    for event in events:
        payload_path = store.payload_path(event)
        available = payload_path.is_file()
        size = payload_path.stat().st_size if available else 0
        records.append(
            InventoryEventRecord(
                event_id=event.event_id,
                event_digest=event.core_digest,
                replica_id=event.replica_ref.replica_id,
                store_generation=event.replica_ref.store_generation,
                replica_seq=event.replica_seq,
                causal_parents=event.causal_parents,
                payload_sha256=event.payload_sha256,
                payload_bytes=size,
                fabric_payload_class=event.fabric_payload_class,
                availability="available" if available else "unavailable",
            )
        )
        ranges.setdefault(
            (event.replica_ref.replica_id, event.replica_ref.store_generation), []
        ).append(event.replica_seq)
        parent_ids.update(event.causal_parents)

    range_records = tuple(
        ReplicaRange(
            replica_id=replica_id,
            store_generation=generation,
            minimum_sequence=min(sequences),
            maximum_sequence=max(sequences),
            event_count=len(sequences),
        )
        for (replica_id, generation), sequences in sorted(ranges.items())
    )
    heads = tuple(sorted(event.event_id for event in events if event.event_id not in parent_ids))
    base = {
        "schema": "pmw-federation-inventory/v1",
        "generated_by_realm_id": store.config.local_realm_id,
        "events": [record.to_dict() for record in records],
        "replica_ranges": [record.to_dict() for record in range_records],
        "causal_heads": list(heads),
        "not_claimed": list(INVENTORY_NONCLAIMS),
    }
    identity_digest = _digest(base).rsplit(":", 1)[-1]
    with_id = {**base, "inventory_id": f"inventory:sha256:{identity_digest}"}
    digest = _digest(with_id)
    return FederationInventory(
        schema=base["schema"],
        inventory_id=with_id["inventory_id"],
        generated_by_realm_id=base["generated_by_realm_id"],
        events=tuple(records),
        replica_ranges=range_records,
        causal_heads=heads,
        not_claimed=INVENTORY_NONCLAIMS,
        inventory_digest=digest,
    )


def diff_inventories(
    local: FederationInventory, remote: FederationInventory
) -> InventoryDiff:
    local_records = {record.event_id: record for record in local.events}
    remote_records = {record.event_id: record for record in remote.events}
    shared = set(local_records) & set(remote_records)
    return InventoryDiff(
        missing_from_local=tuple(sorted(set(remote_records) - set(local_records))),
        missing_from_remote=tuple(sorted(set(local_records) - set(remote_records))),
        digest_mismatches=tuple(
            sorted(
                event_id
                for event_id in shared
                if local_records[event_id].event_digest
                != remote_records[event_id].event_digest
            )
        ),
    )
