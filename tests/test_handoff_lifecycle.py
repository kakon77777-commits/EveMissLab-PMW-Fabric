from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_handoff.errors import HandoffError
from eml_handoff.filesystem import read_source_payload
from eml_handoff.models import HandoffConfig, HandoffEnvelope
from eml_handoff.store import HandoffStore, handoff_key
from tests.test_handoff_contracts import valid_config, valid_envelope


class FakeVerifier:
    def verify_exact_instance(
        self, target_ref, receiver_instance_ref, binding_kind, evidence_ref
    ):
        return (
            target_ref == receiver_instance_ref
            and binding_kind == "codex_thread"
            and evidence_ref == "host:exact-turn"
        )

    def verify_entity(self, target_ref, receiver_entity_ref, evidence_ref):
        return target_ref == receiver_entity_ref and evidence_ref == "ral:verified"


class HandoffLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = self.base / "source"
        self.source.mkdir()
        self.payload = self.source / "message.md"
        self.payload.write_bytes(b"hello lifecycle\n")
        config = valid_config()
        config.update(
            {
                "allowed_source_roots": [str(self.source)],
                "allowed_target_kinds": [
                    "shared_topic",
                    "task",
                    "arcp_entity",
                    "exact_instance",
                ],
            }
        )
        self.config = HandoffConfig.from_dict(config)
        self.store = HandoffStore(self.base / "mailbox", self.config)
        self.snapshot = read_source_payload(self.payload, self.config)
        self.envelope = self.make_envelope("handoff:test:001", "task", "task:test")

    def tearDown(self):
        self.tmp.cleanup()

    def make_envelope(
        self,
        handoff_id: str,
        target_kind: str,
        target_ref: str,
        *,
        reply_to_handoff_id: str | None = None,
        snapshot=None,
    ) -> HandoffEnvelope:
        payload = snapshot or self.snapshot
        raw = valid_envelope()
        raw.update(
            {
                "handoff_id": handoff_id,
                "delivery_id": f"delivery:{handoff_id}",
                "target_kind": target_kind,
                "target_ref": target_ref,
                "payload_ref": f"payloads/{handoff_key(handoff_id)}{payload.extension}",
                "payload_media_type": payload.media_type,
                "payload_sha256": payload.sha256,
                "payload_bytes": payload.byte_count,
                "reply_to_handoff_id": reply_to_handoff_id,
            }
        )
        return HandoffEnvelope.from_dict(raw)

    def claim_task(self, *, receiver="thread:current"):
        return self.store.claim(
            self.envelope.handoff_id,
            receiver_instance_ref=receiver,
            binding_kind="codex_thread",
            claim_authority_ref="principal:neo.k/cross-dialogue",
            evidence_ref="host:exact-turn",
        )

    def test_positive_task_claim_materialize_and_ack(self):
        self.store.submit(self.envelope, self.snapshot)
        self.claim_task()
        materialized = self.store.materialize(
            self.envelope.handoff_id, receiver_instance_ref="thread:current"
        )
        self.assertEqual(materialized.payload_sha256, self.envelope.payload_sha256)
        receipt = self.store.commit_receipt(
            self.envelope.handoff_id,
            decision="ACK",
            receiver_instance_ref="thread:current",
            response_handoff_id=None,
            evidence_refs=["host:exact-turn"],
            recorded_time_ref=None,
        )
        self.assertEqual(receipt.decision, "ACK")
        self.assertEqual(self.store.status(self.envelope.handoff_id)["status"], "acknowledged")

    def test_exact_instance_requires_verifier_and_exact_match(self):
        exact = self.make_envelope(
            "handoff:test:exact", "exact_instance", "thread:target"
        )
        self.store.submit(exact, self.snapshot)
        with self.assertRaises(HandoffError) as caught:
            self.store.claim(
                exact.handoff_id,
                receiver_instance_ref="thread:target",
                binding_kind="codex_thread",
                claim_authority_ref="principal:neo.k/cross-dialogue",
                evidence_ref="host:exact-turn",
            )
        self.assertEqual(caught.exception.code, "host_binding_verifier_unavailable")

        with self.assertRaises(HandoffError) as caught:
            self.store.claim(
                exact.handoff_id,
                receiver_instance_ref="thread:other",
                binding_kind="codex_thread",
                claim_authority_ref="principal:neo.k/cross-dialogue",
                evidence_ref="host:exact-turn",
                verifier=FakeVerifier(),
            )
        self.assertEqual(caught.exception.code, "exact_instance_target_mismatch")

        record = self.store.claim(
            exact.handoff_id,
            receiver_instance_ref="thread:target",
            binding_kind="codex_thread",
            claim_authority_ref="principal:neo.k/cross-dialogue",
            evidence_ref="host:exact-turn",
            verifier=FakeVerifier(),
        )
        self.assertEqual(record.receiver_instance_ref, "thread:target")

    def test_entity_target_requires_verifier_and_entity_match(self):
        entity = self.make_envelope(
            "handoff:test:entity", "arcp_entity", "arcp:agent:example"
        )
        self.store.submit(entity, self.snapshot)
        with self.assertRaises(HandoffError) as caught:
            self.store.claim(
                entity.handoff_id,
                receiver_instance_ref="thread:current",
                binding_kind="codex_thread",
                receiver_entity_ref="arcp:agent:example",
                claim_authority_ref="principal:neo.k/cross-dialogue",
                evidence_ref="ral:verified",
            )
        self.assertEqual(caught.exception.code, "entity_binding_verifier_unavailable")

        record = self.store.claim(
            entity.handoff_id,
            receiver_instance_ref="thread:current",
            binding_kind="codex_thread",
            receiver_entity_ref="arcp:agent:example",
            claim_authority_ref="principal:neo.k/cross-dialogue",
            evidence_ref="ral:verified",
            verifier=FakeVerifier(),
        )
        self.assertEqual(record.receiver_entity_ref, "arcp:agent:example")

    def test_unresolved_task_consumer_can_complete_with_task_authority(self):
        self.store.submit(self.envelope, self.snapshot)
        self.store.claim(
            self.envelope.handoff_id,
            receiver_instance_ref=None,
            binding_kind="unresolved",
            claim_authority_ref="principal:neo.k/cross-dialogue",
            evidence_ref=None,
        )
        self.store.materialize(self.envelope.handoff_id, receiver_instance_ref=None)
        receipt = self.store.commit_receipt(
            self.envelope.handoff_id,
            decision="NO_ACTION",
            receiver_instance_ref=None,
            response_handoff_id=None,
            evidence_refs=["task-authority:fixture"],
            recorded_time_ref=None,
        )
        self.assertEqual(receipt.decision, "NO_ACTION")

    def test_claim_is_exclusive_and_incomplete_claim_is_not_pending(self):
        self.store.submit(self.envelope, self.snapshot)
        self.claim_task()
        with self.assertRaises(HandoffError) as caught:
            self.claim_task(receiver="thread:second")
        self.assertEqual(caught.exception.code, "handoff_already_claimed")
        self.assertEqual(
            self.store.status(self.envelope.handoff_id)["status"],
            "claimed_incomplete",
        )
        self.assertNotIn(
            self.envelope.handoff_id,
            self.store.pending("task", self.envelope.target_ref),
        )

    def test_materialization_requires_claim_and_same_receiver(self):
        self.store.submit(self.envelope, self.snapshot)
        with self.assertRaises(HandoffError) as caught:
            self.store.materialize(
                self.envelope.handoff_id, receiver_instance_ref="thread:current"
            )
        self.assertEqual(caught.exception.code, "handoff_not_claimed")

        self.claim_task()
        with self.assertRaises(HandoffError) as caught:
            self.store.materialize(
                self.envelope.handoff_id, receiver_instance_ref="thread:other"
            )
        self.assertEqual(caught.exception.code, "receiver_instance_mismatch")

    def test_receipt_requires_materialization(self):
        self.store.submit(self.envelope, self.snapshot)
        self.claim_task()
        with self.assertRaises(HandoffError) as caught:
            self.store.commit_receipt(
                self.envelope.handoff_id,
                decision="ACK",
                receiver_instance_ref="thread:current",
                response_handoff_id=None,
                evidence_refs=["host:exact-turn"],
                recorded_time_ref=None,
            )
        self.assertEqual(caught.exception.code, "payload_not_materialized")

    def test_response_handoff_must_exist_and_link_back(self):
        self.store.submit(self.envelope, self.snapshot)
        self.claim_task()
        self.store.materialize(
            self.envelope.handoff_id, receiver_instance_ref="thread:current"
        )
        with self.assertRaises(HandoffError) as caught:
            self.store.commit_receipt(
                self.envelope.handoff_id,
                decision="ACK",
                receiver_instance_ref="thread:current",
                response_handoff_id="handoff:missing",
                evidence_refs=["host:exact-turn"],
                recorded_time_ref=None,
            )
        self.assertEqual(caught.exception.code, "response_handoff_not_found")

        reply_payload = self.source / "reply.md"
        reply_payload.write_text("reply\n", encoding="utf-8")
        reply_snapshot = read_source_payload(reply_payload, self.config)
        reply = self.make_envelope(
            "handoff:test:reply",
            "task",
            "task:test",
            reply_to_handoff_id=self.envelope.handoff_id,
            snapshot=reply_snapshot,
        )
        self.store.submit(reply, reply_snapshot)
        receipt = self.store.commit_receipt(
            self.envelope.handoff_id,
            decision="ACK",
            receiver_instance_ref="thread:current",
            response_handoff_id=reply.handoff_id,
            evidence_refs=["host:exact-turn"],
            recorded_time_ref=None,
        )
        self.assertEqual(receipt.response_handoff_id, reply.handoff_id)


if __name__ == "__main__":
    unittest.main()
