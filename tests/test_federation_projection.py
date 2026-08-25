from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.federation.authority import AuthorityVerification
from eml_pmw.federation.models import FederatedEvent, FederationConfig
from eml_pmw.federation.projector import (
    compare_projection,
    rebuild_json,
    rebuild_sqlite,
)
from eml_pmw.federation.reconcile import reconcile_event, resolve_conflict
from eml_pmw.federation.store import FederationStore
from tests.federation_helpers import event_at, event_for_replica, update_event, valid_config


class VerifiedFixture:
    def verify(self, *, authority_ref, action, subject_ref):
        return AuthorityVerification(
            "verified",
            authority_ref,
            action,
            subject_ref,
            "evidence:authority:fixture",
        )


def snapshot_rows(path):
    connection = sqlite3.connect(path)
    try:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        return {
            name: connection.execute(f'SELECT * FROM "{name}" ORDER BY 1').fetchall()
            for name in names
        }
    finally:
        connection.close()


class FederationProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config = valid_config(
            allowed_event_kinds=["pmw.task.field_set", "pmw.conflict.resolution"],
            authority_required_event_kinds=["pmw.task.field_set", "pmw.conflict.resolution"],
        )
        self.config = FederationConfig.from_dict(config)

    def make_store(self, name):
        return FederationStore(Path(self.temp.name) / name, self.config)

    def populate_conflict(self, store):
        left_value, left_payload = update_event("a", "left")
        right_value, right_payload = update_event("b", "right")
        left = FederatedEvent.from_dict(left_value)
        right = FederatedEvent.from_dict(right_value)
        store.submit(left, left_payload, delivery_id="delivery:left")
        store.submit(right, right_payload, delivery_id="delivery:right")
        conflict = reconcile_event(store, right.event_id, verifier=VerifiedFixture())
        return left, right, conflict

    def resolve_left(self, store, left, right, conflict):
        members = sorted((left.event_id, right.event_id))
        payload = json.dumps(
            {
                "conflict_id": conflict.conflict_id,
                "member_event_ids": members,
                "selected_event_id": left.event_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        event = FederatedEvent.from_dict(
            event_for_replica(
                "resolver",
                1,
                "event:resolution:projection",
                parents=members,
                event_kind="pmw.conflict.resolution",
                subject_ref=conflict.conflict_id,
                payload_ref="payloads/resolution-projection.json",
                payload_sha256=hashlib.sha256(payload).hexdigest().upper(),
            )
        )
        resolve_conflict(
            store,
            conflict.conflict_id,
            event,
            payload,
            verifier=VerifiedFixture(),
        )

    def test_unresolved_conflict_is_visible_and_does_not_choose_a_value(self):
        store = self.make_store("unresolved")
        _, _, conflict = self.populate_conflict(store)

        value = json.loads(rebuild_json(store))

        subject = value["subjects"]["pmw-task:fixture"]
        self.assertEqual(subject["fields"], {})
        self.assertEqual(subject["unresolved_conflict_ids"], [conflict.conflict_id])

    def test_resolution_selects_value_without_removing_conflict_history(self):
        store = self.make_store("resolved")
        left, right, conflict = self.populate_conflict(store)
        self.resolve_left(store, left, right, conflict)

        value = json.loads(rebuild_json(store))

        subject = value["subjects"]["pmw-task:fixture"]
        self.assertEqual(
            subject["fields"]["status"],
            {"source_event_id": left.event_id, "value": "left"},
        )
        self.assertEqual(subject["unresolved_conflict_ids"], [])
        self.assertEqual(value["conflicts"][0]["conflict_id"], conflict.conflict_id)

    def test_correction_then_withdrawal_derives_blank_without_rewrite(self):
        store = self.make_store("correction")
        base_payload = b'{"field":"status","value":"open"}'
        correction_payload = b'{"field":"status","value":"closed"}'
        withdrawal_payload = b'{"reason":"withdraw fixture"}'
        base = FederatedEvent.from_dict(
            event_at(
                1,
                "event:base",
                payload_ref="payloads/base.json",
                payload_sha256=hashlib.sha256(base_payload).hexdigest().upper(),
            )
        )
        correction = FederatedEvent.from_dict(
            event_at(
                2,
                "event:correction",
                [base.event_id],
                correction_of=base.event_id,
                payload_ref="payloads/correction.json",
                payload_sha256=hashlib.sha256(correction_payload).hexdigest().upper(),
            )
        )
        withdrawal = FederatedEvent.from_dict(
            event_at(
                3,
                "event:withdrawal",
                [correction.event_id],
                withdraws=correction.event_id,
                payload_ref="payloads/withdrawal.json",
                payload_sha256=hashlib.sha256(withdrawal_payload).hexdigest().upper(),
            )
        )
        store.submit(base, base_payload, delivery_id="delivery:base")
        store.submit(correction, correction_payload, delivery_id="delivery:correction")
        corrected = json.loads(rebuild_json(store))
        self.assertEqual(
            corrected["subjects"]["pmw-task:fixture"]["fields"]["status"]["value"],
            "closed",
        )

        store.submit(withdrawal, withdrawal_payload, delivery_id="delivery:withdrawal")
        withdrawn = json.loads(rebuild_json(store))
        self.assertEqual(
            withdrawn["subjects"]["pmw-task:fixture"]["fields"], {}
        )

    def test_two_rebuilds_are_byte_and_row_identical_across_submit_order(self):
        first_store = self.make_store("first")
        second_store = self.make_store("second")
        first_value, first_payload = update_event("a", "open", field="status")
        second_value, second_payload = update_event("b", "neo", field="owner")
        records = [
            (FederatedEvent.from_dict(first_value), first_payload),
            (FederatedEvent.from_dict(second_value), second_payload),
        ]
        for index, (event, payload) in enumerate(records):
            first_store.submit(event, payload, delivery_id=f"first:{index}")
        for index, (event, payload) in enumerate(reversed(records)):
            second_store.submit(event, payload, delivery_id=f"second:{index}")

        first_json = rebuild_json(first_store)
        second_json = rebuild_json(second_store)
        first_db = rebuild_sqlite(first_store, Path(self.temp.name) / "first.sqlite")
        second_db = rebuild_sqlite(second_store, Path(self.temp.name) / "second.sqlite")

        self.assertEqual(first_json, second_json)
        self.assertEqual(snapshot_rows(first_db), snapshot_rows(second_db))

    def test_projection_comparison_distinguishes_extra_from_contradiction(self):
        expected = {"subject": {"field": "open"}}

        self.assertEqual(
            compare_projection(expected, expected).status, "expected_by_mapping"
        )
        self.assertEqual(
            compare_projection(expected, {**expected, "extra": 1}).status,
            "unmapped",
        )
        self.assertEqual(
            compare_projection(expected, {"subject": {"field": "closed"}}).status,
            "contradiction",
        )


if __name__ == "__main__":
    unittest.main()
