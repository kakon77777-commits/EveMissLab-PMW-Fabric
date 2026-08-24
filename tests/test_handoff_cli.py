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
from eml_wake.temporal import FakeTemporalProvider, TemporalReceipt
from tests.test_handoff_contracts import valid_config


class HandoffCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "mailbox"
        self.source = self.base / "source"
        self.source.mkdir()
        self.payload = self.source / "message.md"
        self.payload.write_text("hello from CLI\n", encoding="utf-8")
        config = {**valid_config(), "allowed_source_roots": [str(self.source)]}
        self.config = self.base / "config.json"
        self.config.write_text(json.dumps(config), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def unavailable_temporal(self):
        temporal = FakeTemporalProvider()
        temporal.queue(TemporalReceipt("unavailable", None, None, "fixture"))
        return temporal

    def run_cli(self, *tail, temporal=None, verifier=None):
        output = io.StringIO()
        try:
            code = main(
                ["--root", str(self.root), "--config", str(self.config), *tail],
                temporal=temporal,
                verifier=verifier,
                stdout=output,
            )
        except SystemExit as error:
            self.fail(f"CLI parser rejected implemented command: {error.code}")
        raw = output.getvalue()
        self.assertTrue(raw.endswith("\n"))
        self.assertFalse(raw.endswith("\n\n"))
        return code, json.loads(raw), raw.encode("utf-8")

    def create_pending(self):
        return self.run_cli(
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
            "task:test",
            "--authority",
            "principal:neo.k/cross-dialogue",
            temporal=self.unavailable_temporal(),
        )

    def test_create_list_claim_materialize_ack_status_without_network(self):
        code, created, _ = self.create_pending()
        self.assertEqual(code, 0)
        self.assertIsNone(created["envelope"]["created_time_ref"])
        self.assertEqual(
            created["envelope"]["temporal_evidence_status"], "unavailable"
        )
        handoff_id = created["handoff_id"]

        code, listed, _ = self.run_cli(
            "list", "--target-kind", "task", "--target-ref", "task:test"
        )
        self.assertEqual(code, 0)
        self.assertEqual(listed["handoff_ids"], [handoff_id])

        code, _, _ = self.run_cli(
            "claim",
            handoff_id,
            "--receiver-instance",
            "thread:current",
            "--binding-kind",
            "codex_thread",
            "--authority",
            "principal:neo.k/cross-dialogue",
            "--evidence",
            "host:exact-turn",
        )
        self.assertEqual(code, 0)

        code, materialized, _ = self.run_cli(
            "materialize",
            handoff_id,
            "--receiver-instance",
            "thread:current",
        )
        self.assertEqual(code, 0)
        self.assertNotIn("hello from CLI", json.dumps(materialized))
        self.assertEqual(materialized["payload_bytes"], self.payload.stat().st_size)

        code, _, _ = self.run_cli(
            "ack",
            handoff_id,
            "--receiver-instance",
            "thread:current",
            "--decision",
            "ACK",
            "--evidence",
            "host:exact-turn",
            temporal=self.unavailable_temporal(),
        )
        self.assertEqual(code, 0)

        code, status, _ = self.run_cli("status", handoff_id)
        self.assertEqual(code, 0)
        self.assertEqual(status["status"], "acknowledged")

    def test_exit_codes_distinguish_io_refusal_pending_and_complete(self):
        code, error, _ = self.run_cli(
            "create",
            "--payload",
            str(self.base / "missing.md"),
            "--sender",
            "claim:sender",
            "--sender-instance",
            "claim:instance",
            "--target-kind",
            "task",
            "--target-ref",
            "task:test",
            "--authority",
            "principal:neo.k/cross-dialogue",
            temporal=FakeTemporalProvider(),
        )
        self.assertEqual(code, 1)
        self.assertEqual(error["error"]["code"], "input_unreadable")

        code, refused, _ = self.run_cli(
            "create",
            "--payload",
            str(self.payload),
            "--sender",
            "claim:sender",
            "--sender-instance",
            "claim:instance",
            "--target-kind",
            "exact_instance",
            "--target-ref",
            "thread:target",
            "--authority",
            "principal:neo.k/cross-dialogue",
            temporal=FakeTemporalProvider(),
        )
        self.assertEqual(code, 2)
        self.assertEqual(refused["error"]["code"], "target_kind_not_allowed")

        _, created, _ = self.create_pending()
        code, pending, _ = self.run_cli("status", created["handoff_id"])
        self.assertEqual(code, 3)
        self.assertEqual(pending["status"], "pending")

    def test_same_status_output_is_byte_deterministic(self):
        _, created, _ = self.create_pending()
        handoff_id = created["handoff_id"]
        first = self.run_cli("status", handoff_id)
        second = self.run_cli("status", handoff_id)
        self.assertEqual(first[0], 3)
        self.assertEqual(first[2], second[2])

    def test_reply_creates_linked_handoff_and_acknowledges_original(self):
        _, created, _ = self.create_pending()
        handoff_id = created["handoff_id"]
        self.run_cli(
            "claim",
            handoff_id,
            "--receiver-instance",
            "thread:current",
            "--binding-kind",
            "codex_thread",
            "--authority",
            "principal:neo.k/cross-dialogue",
            "--evidence",
            "host:exact-turn",
        )
        self.run_cli(
            "materialize", handoff_id, "--receiver-instance", "thread:current"
        )
        reply_payload = self.source / "reply.md"
        reply_payload.write_text("reply body\n", encoding="utf-8")
        temporal = FakeTemporalProvider()
        temporal.queue(TemporalReceipt("unavailable", None, None, "request-fixture"))
        temporal.queue(TemporalReceipt("unavailable", None, None, "receipt-fixture"))
        code, value, _ = self.run_cli(
            "reply",
            handoff_id,
            "--payload",
            str(reply_payload),
            "--sender",
            "claim:receiver",
            "--sender-instance",
            "thread:current",
            "--target-kind",
            "task",
            "--target-ref",
            "task:test",
            "--authority",
            "principal:neo.k/cross-dialogue",
            "--receiver-instance",
            "thread:current",
            "--evidence",
            "host:exact-turn",
            temporal=temporal,
        )
        self.assertEqual(code, 0)
        self.assertEqual(value["response"]["reply_to_handoff_id"], handoff_id)
        self.assertEqual(
            value["receipt"]["response_handoff_id"],
            value["response"]["handoff_id"],
        )
        self.assertEqual(self.run_cli("status", handoff_id)[1]["status"], "acknowledged")

    def test_malformed_and_duplicate_key_config_are_typed_input_errors(self):
        self.config.write_text("{not-json", encoding="utf-8")
        code, value, _ = self.run_cli("status", "handoff:none")
        self.assertEqual(code, 1)
        self.assertEqual(value["error"]["code"], "invalid_json")

        self.config.write_text(
            '{"schema_version":"eml-handoff/config-0.1","schema_version":"changed"}',
            encoding="utf-8",
        )
        code, value, _ = self.run_cli("status", "handoff:none")
        self.assertEqual(code, 2)
        self.assertEqual(value["error"]["code"], "duplicate_key")


if __name__ == "__main__":
    unittest.main()
