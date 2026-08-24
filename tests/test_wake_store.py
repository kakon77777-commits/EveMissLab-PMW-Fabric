from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from unittest import mock
import unittest

from tests.test_wake_contracts import valid_config, valid_request


def store_api():
    try:
        from eml_wake.errors import WakeError
        from eml_wake.filesystem import publish_no_replace, read_allowlisted_payload
        from eml_wake.models import WakeConfig, WakeRequest
        from eml_wake.store import WakeStore, wake_key
    except ModuleNotFoundError as exc:
        raise AssertionError("eml_wake durable store is not implemented") from exc
    return WakeConfig, WakeRequest, WakeStore, WakeError, publish_no_replace, read_allowlisted_payload, wake_key


class WakeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.payload_root = self.root / "payloads"
        self.payload_root.mkdir()
        self.payload = self.payload_root / "message.md"
        self.payload.write_bytes(b"durable payload\n")

        WakeConfig, _, WakeStore, _, _, _, _ = store_api()
        config_raw = valid_config()
        config_raw["allowed_payload_roots"] = [str(self.payload_root)]
        self.config = WakeConfig.from_dict(config_raw)
        self.store = WakeStore(self.root / "wake", self.config)

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, *, delivery_id: str = "delivery:test:001", **changes):
        _, WakeRequest, _, _, _, _, _ = store_api()
        raw = valid_request()
        raw.update(
            {
                "delivery_id": delivery_id,
                "payload_ref": str(self.payload),
                "payload_sha256": hashlib.sha256(self.payload.read_bytes()).hexdigest().upper(),
            }
        )
        raw.update(changes)
        return WakeRequest.from_dict(raw)

    def test_three_delivery_paths_create_one_request_and_two_duplicate_observations(self):
        first = self.store.submit(self.request(delivery_id="delivery:1"))
        second = self.store.submit(self.request(delivery_id="delivery:2"))
        third = self.store.submit(self.request(delivery_id="delivery:3"))

        self.assertEqual(first.kind, "created")
        self.assertEqual(second.kind, "duplicate")
        self.assertEqual(third.kind, "duplicate")
        self.assertEqual(len(list(self.store.requests_dir.glob("*.json"))), 1)
        self.assertEqual(len(list(self.store.duplicates_dir.rglob("*.json"))), 2)

    def test_same_wake_with_changed_payload_is_a_collision(self):
        _, _, _, WakeError, _, _, _ = store_api()
        self.store.submit(self.request(delivery_id="delivery:1"))
        other = self.payload_root / "other.md"
        other.write_bytes(b"different\n")
        with self.assertRaises(WakeError) as caught:
            self.store.submit(
                self.request(
                    delivery_id="delivery:2",
                    payload_ref=str(other),
                    payload_sha256=hashlib.sha256(other.read_bytes()).hexdigest().upper(),
                )
            )
        self.assertEqual(caught.exception.code, "wake_content_collision")

    def test_claim_is_exclusive(self):
        _, _, _, WakeError, _, _, _ = store_api()
        self.store.submit(self.request())
        claim = self.store.claim("wake:test:001", "watchdog:one")
        self.assertEqual(claim["watchdog_id"], "watchdog:one")
        with self.assertRaises(WakeError) as caught:
            self.store.claim("wake:test:001", "watchdog:two")
        self.assertEqual(caught.exception.code, "wake_already_claimed")

    def test_status_distinguishes_pending_claimed_acknowledged_and_failed(self):
        self.store.submit(self.request())
        self.assertEqual(self.store.status("wake:test:001")["status"], "pending")
        self.store.claim("wake:test:001", "watchdog:one")
        self.assertEqual(self.store.status("wake:test:001")["status"], "claimed_incomplete")
        self.store.commit_ack(
            "wake:test:001",
            {"schema_version": "eml-wake/ack-0.1", "wake_id": "wake:test:001", "status": "acknowledged"},
        )
        self.assertEqual(self.store.status("wake:test:001")["status"], "acknowledged")

        other_raw = valid_request()
        other_raw.update(
            {
                "wake_id": "wake:test:002",
                "delivery_id": "delivery:test:002",
                "payload_ref": str(self.payload),
                "payload_sha256": hashlib.sha256(self.payload.read_bytes()).hexdigest().upper(),
            }
        )
        _, WakeRequest, _, _, _, _, _ = store_api()
        self.store.submit(WakeRequest.from_dict(other_raw))
        self.store.record_failure(
            "wake:test:002",
            {"schema_version": "eml-wake/failure-0.1", "wake_id": "wake:test:002", "code": "refused"},
        )
        self.assertEqual(self.store.status("wake:test:002")["status"], "failed")

    def test_ack_and_failure_publication_are_no_replace(self):
        _, _, _, WakeError, _, _, _ = store_api()
        self.store.submit(self.request())
        self.store.claim("wake:test:001", "watchdog:one")
        ack = {"schema_version": "eml-wake/ack-0.1", "wake_id": "wake:test:001", "status": "acknowledged"}
        self.store.commit_ack("wake:test:001", ack)
        with self.assertRaises(WakeError) as caught:
            self.store.commit_ack("wake:test:001", {**ack, "status": "changed"})
        self.assertEqual(caught.exception.code, "immutable_file_exists")

    def test_payload_outside_allowlist_is_rejected(self):
        _, _, _, WakeError, _, read_allowlisted_payload, _ = store_api()
        outside = self.root / "outside.md"
        outside.write_bytes(b"outside")
        request = self.request(
            payload_ref=str(outside),
            payload_sha256=hashlib.sha256(outside.read_bytes()).hexdigest().upper(),
        )
        with self.assertRaises(WakeError) as caught:
            read_allowlisted_payload(request, self.config)
        self.assertEqual(caught.exception.code, "payload_outside_allowlist")

    def test_payload_digest_mismatch_is_rejected(self):
        _, _, _, WakeError, _, read_allowlisted_payload, _ = store_api()
        request = self.request(payload_sha256="B" * 64)
        with self.assertRaises(WakeError) as caught:
            read_allowlisted_payload(request, self.config)
        self.assertEqual(caught.exception.code, "payload_integrity_failed")

    def test_wake_key_is_windows_safe_and_deterministic(self):
        _, _, _, _, _, _, wake_key = store_api()
        first = wake_key("wake:test:001")
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertNotIn(":", first)
        self.assertEqual(first, wake_key("wake:test:001"))
        self.assertNotEqual(first, wake_key("wake:test:002"))

    def test_injected_publish_failure_leaves_no_final_and_retry_succeeds(self):
        _, _, _, WakeError, publish_no_replace, _, _ = store_api()
        final = self.root / "published" / "record.json"
        with mock.patch("eml_wake.filesystem.os.link", side_effect=OSError(5, "injected")):
            with self.assertRaises(WakeError) as caught:
                publish_no_replace(final, {"value": 1})
        self.assertEqual(caught.exception.code, "immutable_publish_failed")
        self.assertFalse(final.exists())
        self.assertEqual(list(final.parent.glob(".record.json.*.tmp")), [])

        publish_no_replace(final, {"value": 1})
        self.assertTrue(final.exists())


if __name__ == "__main__":
    unittest.main()
