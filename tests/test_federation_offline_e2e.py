from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.federation.authority import AuthorityVerification
from eml_pmw.federation.importer import import_event
from eml_pmw.federation.inventory import build_inventory, diff_inventories
from eml_pmw.federation.models import FederatedEvent, FederationConfig
from eml_pmw.federation.projector import rebuild_json
from eml_pmw.federation.reconcile import reconcile_event, resolve_conflict
from eml_pmw.federation.store import FederationStore
from tests.federation_helpers import event_for_replica, observer, update_event, valid_config


class VerifiedFixture:
    def verify(self, *, authority_ref, action, subject_ref):
        return AuthorityVerification(
            "verified", authority_ref, action, subject_ref, "evidence:authority:fixture"
        )


class FederationOfflineE2ETests(unittest.TestCase):
    def test_two_realms_preserve_conflict_then_converge_by_resolution(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            allowed = [
                "pmw.task.field_set",
                "pmw.conflict.resolution",
            ]
            config_a = FederationConfig.from_dict(
                valid_config(
                    local_realm_id="realm:a",
                    local_replica_id="replica:a",
                    allowed_event_kinds=allowed,
                    authority_required_event_kinds=allowed,
                )
            )
            config_b = FederationConfig.from_dict(
                valid_config(
                    local_realm_id="realm:b",
                    local_replica_id="replica:b",
                    allowed_event_kinds=allowed,
                    authority_required_event_kinds=allowed,
                )
            )
            realm_a = FederationStore(root / "realm-a", config_a)
            realm_b = FederationStore(root / "realm-b", config_b)

            genesis_payload = b'{"field":"status","value":"genesis"}'
            genesis = FederatedEvent.from_dict(
                event_for_replica(
                    "seed",
                    1,
                    "event:genesis",
                    payload_ref="payloads/genesis.json",
                    payload_sha256=hashlib.sha256(genesis_payload).hexdigest().upper(),
                )
            )
            for realm in (realm_a, realm_b):
                realm.submit(genesis, genesis_payload, delivery_id=f"seed:{realm.config.local_realm_id}")

            a_status_value, a_status_payload = update_event("a", "left")
            b_status_value, b_status_payload = update_event("b", "right")
            a_owner_value, a_owner_payload = update_event("a2", "neo", field="owner")
            b_priority_value, b_priority_payload = update_event("b2", "high", field="priority")
            all_values = (
                (a_status_value, a_status_payload),
                (b_status_value, b_status_payload),
                (a_owner_value, a_owner_payload),
                (b_priority_value, b_priority_payload),
            )
            for value, _ in all_values:
                value["causal_parents"] = [genesis.event_id]
            a_status = FederatedEvent.from_dict(a_status_value)
            b_status = FederatedEvent.from_dict(b_status_value)
            a_owner = FederatedEvent.from_dict(a_owner_value)
            b_priority = FederatedEvent.from_dict(b_priority_value)
            realm_a.submit(a_status, a_status_payload, delivery_id="offline:a-status")
            realm_a.submit(a_owner, a_owner_payload, delivery_id="offline:a-owner")
            realm_b.submit(b_status, b_status_payload, delivery_id="offline:b-status")
            realm_b.submit(b_priority, b_priority_payload, delivery_id="offline:b-priority")

            diff_a = diff_inventories(build_inventory(realm_a), build_inventory(realm_b))
            diff_b = diff_inventories(build_inventory(realm_b), build_inventory(realm_a))
            self.assertEqual(set(diff_a.missing_from_local), {b_status.event_id, b_priority.event_id})
            self.assertEqual(set(diff_b.missing_from_local), {a_status.event_id, a_owner.event_id})

            import_event(realm_a, b_status.canonical_bytes, b_status_payload, observer(observer_id="observer:a:b-status", realm_id="realm:a"))
            import_event(realm_a, b_priority.canonical_bytes, b_priority_payload, observer(observer_id="observer:a:b-priority", realm_id="realm:a"))
            import_event(realm_b, a_status.canonical_bytes, a_status_payload, observer(observer_id="observer:b:a-status", realm_id="realm:b"))
            import_event(realm_b, a_owner.canonical_bytes, a_owner_payload, observer(observer_id="observer:b:a-owner", realm_id="realm:b"))

            verifier = VerifiedFixture()
            conflict_a = reconcile_event(realm_a, b_status.event_id, verifier=verifier)
            conflict_b = reconcile_event(realm_b, a_status.event_id, verifier=verifier)
            self.assertEqual(conflict_a.status, "conflict")
            record_a = realm_a.get_conflict(conflict_a.conflict_id)
            record_b = realm_b.get_conflict(conflict_b.conflict_id)
            self.assertEqual(record_a["member_event_ids"], sorted((a_status.event_id, b_status.event_id)))
            self.assertEqual(record_b["member_event_ids"], sorted((a_status.event_id, b_status.event_id)))
            self.assertEqual(record_a["conflict_class"], "field_value_conflict")
            self.assertEqual(record_b["conflict_class"], "field_value_conflict")
            self.assertEqual(record_a["subject_ref"], record_b["subject_ref"])
            self.assertEqual(record_a["member_event_digests"], record_b["member_event_digests"])
            self.assertEqual(conflict_a.conflict_id, conflict_b.conflict_id)
            self.assertEqual(reconcile_event(realm_a, b_priority.event_id, verifier=verifier).status, "adopted")
            self.assertEqual(reconcile_event(realm_b, a_owner.event_id, verifier=verifier).status, "adopted")

            conflict_bytes_a = realm_a.conflict_path(conflict_a.conflict_id).read_bytes()
            conflict_bytes_b = realm_b.conflict_path(conflict_b.conflict_id).read_bytes()
            self.assertEqual(conflict_bytes_a, conflict_bytes_b)

            members = sorted((a_status.event_id, b_status.event_id))
            resolution_payload = json.dumps(
                {
                    "conflict_id": conflict_a.conflict_id,
                    "member_event_ids": members,
                    "selected_event_id": a_status.event_id,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            resolution = FederatedEvent.from_dict(
                event_for_replica(
                    "resolver",
                    1,
                    "event:resolution:e2e",
                    parents=members,
                    event_kind="pmw.conflict.resolution",
                    subject_ref=conflict_a.conflict_id,
                    payload_ref="payloads/resolution-e2e.json",
                    payload_sha256=hashlib.sha256(resolution_payload).hexdigest().upper(),
                )
            )
            resolve_conflict(realm_a, conflict_a.conflict_id, resolution, resolution_payload, verifier=verifier)
            import_event(realm_b, resolution.canonical_bytes, resolution_payload, observer(observer_id="observer:b:resolution", realm_id="realm:b"))
            resolve_conflict(realm_b, conflict_b.conflict_id, resolution, resolution_payload, verifier=verifier)

            self.assertEqual(rebuild_json(realm_a), rebuild_json(realm_b))
            projection = json.loads(rebuild_json(realm_a))
            self.assertEqual(
                projection["subjects"]["pmw-task:fixture"]["fields"]["status"]["value"],
                "left",
            )
            self.assertEqual(
                realm_a.event_path(a_status).read_bytes(),
                realm_b.event_path(a_status).read_bytes(),
            )
            self.assertEqual(
                realm_a.event_path(b_status).read_bytes(),
                realm_b.event_path(b_status).read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
