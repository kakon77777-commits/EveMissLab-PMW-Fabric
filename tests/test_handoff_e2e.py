from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_handoff.cli import main
from eml_handoff.filesystem import read_source_payload
from eml_handoff.models import HandoffConfig, HandoffEnvelope
from eml_handoff.store import HandoffStore
from eml_wake.temporal import FakeTemporalProvider, TemporalReceipt
from tests.test_handoff_contracts import valid_config


class HandoffEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "mailbox"
        self.source = self.base / "source"
        self.source.mkdir()
        self.payload = self.source / "request.md"
        self.payload.write_text("Review the local handoff.\n", encoding="utf-8")
        self.reply_payload = self.source / "reply.md"
        self.reply_payload.write_text("ACK from local mailbox.\n", encoding="utf-8")
        config = {**valid_config(), "allowed_source_roots": [str(self.source)]}
        self.config_file = self.base / "config.json"
        self.config_file.write_text(json.dumps(config), encoding="utf-8")
        self.config = HandoffConfig.from_dict(config)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *tail, temporal=None):
        output = io.StringIO()
        code = main(
            ["--root", str(self.root), "--config", str(self.config_file), *tail],
            temporal=temporal,
            stdout=output,
        )
        return code, json.loads(output.getvalue())

    def unavailable_temporal(self, count=1):
        temporal = FakeTemporalProvider()
        for index in range(count):
            temporal.queue(
                TemporalReceipt("unavailable", None, None, f"fixture-{index}")
            )
        return temporal

    def test_three_delivery_paths_produce_one_claim_receipt_and_linked_reply(self):
        code, created = self.run_cli(
            "create",
            "--payload",
            str(self.payload),
            "--sender",
            "claim:sender",
            "--sender-instance",
            "claim:instance",
            "--target-kind",
            "task",
            "--target-ref",
            "task:pmw-local-handoff-v0.1",
            "--authority",
            "principal:neo.k/cross-dialogue",
            temporal=self.unavailable_temporal(),
        )
        self.assertEqual(code, 0)
        handoff_id = created["handoff_id"]
        store = HandoffStore(self.root, self.config)
        envelope = store.get_envelope(handoff_id)
        snapshot = read_source_payload(self.payload, self.config)

        for delivery_id in ("delivery:bridge", "delivery:monitor"):
            duplicate = HandoffEnvelope.from_dict(
                {**envelope.to_dict(), "delivery_id": delivery_id}
            )
            self.assertEqual(store.submit(duplicate, snapshot).kind, "duplicate")

        notifications = (
            ("notification:file", "file", "accepted", None),
            ("notification:bridge", "bridge", "uncertain", "transport_uncertain"),
            ("notification:monitor", "monitor", "failed", "receiver_idle"),
        )
        for notification_id, route, status, error in notifications:
            store.record_notification(
                handoff_id,
                notification_id=notification_id,
                route_kind=route,
                status=status,
                error_code=error,
                ephemeral_route_ref=None,
            )

        store.claim(
            handoff_id,
            receiver_instance_ref="thread:current",
            binding_kind="codex_thread",
            claim_authority_ref="principal:neo.k/cross-dialogue",
            evidence_ref="host:exact-turn",
        )
        store.materialize(handoff_id, receiver_instance_ref="thread:current")

        code, reply = self.run_cli(
            "reply",
            handoff_id,
            "--payload",
            str(self.reply_payload),
            "--sender",
            "claim:receiver",
            "--sender-instance",
            "thread:current",
            "--target-kind",
            "task",
            "--target-ref",
            "task:pmw-local-handoff-v0.1",
            "--authority",
            "principal:neo.k/cross-dialogue",
            "--receiver-instance",
            "thread:current",
            "--evidence",
            "host:exact-turn",
            temporal=self.unavailable_temporal(2),
        )
        self.assertEqual(code, 0)
        self.assertEqual(reply["response"]["reply_to_handoff_id"], handoff_id)
        self.assertEqual(store.status(handoff_id)["status"], "acknowledged")
        self.assertEqual(len(list(store.envelopes_dir.glob("*.json"))), 2)
        self.assertEqual(len(list(store.duplicates_dir.rglob("*.json"))), 2)
        self.assertEqual(len(list(store.notifications_dir.rglob("*.json"))), 3)
        self.assertEqual(len(list(store.claims_dir.glob("*.json"))), 1)
        self.assertEqual(len(list(store.materializations_dir.glob("*.json"))), 1)
        self.assertEqual(len(list(store.receipts_dir.glob("*.json"))), 1)

        encoded = "".join(
            path.read_text(encoding="utf-8")
            for directory in (store.envelopes_dir, store.claims_dir, store.receipts_dir)
            for path in directory.glob("*.json")
        )
        self.assertNotIn("Review the local handoff", encoded)
        self.assertNotIn("ACK from local mailbox", encoded)


if __name__ == "__main__":
    unittest.main()
