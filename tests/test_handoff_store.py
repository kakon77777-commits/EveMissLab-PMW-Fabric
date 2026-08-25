from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest import mock
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_handoff.errors import HandoffError
from eml_handoff.filesystem import read_source_payload
from eml_handoff.models import HandoffConfig, HandoffEnvelope
import eml_handoff.store as store_module
from eml_handoff.store import HandoffStore, handoff_key
from tests.test_handoff_contracts import valid_config, valid_envelope


class HandoffStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source_root = self.base / "source"
        self.source_root.mkdir()
        self.payload = self.source_root / "message.md"
        self.payload.write_bytes(b"hello handoff\n")
        self.config = HandoffConfig.from_dict(
            {**valid_config(), "allowed_source_roots": [str(self.source_root)]}
        )
        self.snapshot = read_source_payload(self.payload, self.config)
        raw = valid_envelope()
        raw.update(
            {
                "payload_ref": f"payloads/{handoff_key(raw['handoff_id'])}.md",
                "payload_sha256": self.snapshot.sha256,
                "payload_bytes": self.snapshot.byte_count,
            }
        )
        self.envelope = HandoffEnvelope.from_dict(raw)
        self.store = HandoffStore(self.base / "mailbox", self.config)

    def tearDown(self):
        self.tmp.cleanup()

    def test_submit_publishes_exact_payload_and_retrievable_envelope(self):
        result = self.store.submit(self.envelope, self.snapshot)
        self.assertEqual(result.kind, "created")
        self.assertEqual(
            self.store.get_envelope(self.envelope.handoff_id), self.envelope
        )
        self.assertEqual(
            self.store.payload_path(self.envelope).read_bytes(),
            self.payload.read_bytes(),
        )

    def test_same_core_new_delivery_is_duplicate_not_new_handoff(self):
        self.store.submit(self.envelope, self.snapshot)
        duplicate = HandoffEnvelope.from_dict(
            {**self.envelope.to_dict(), "delivery_id": "delivery:test:002"}
        )
        result = self.store.submit(duplicate, self.snapshot)
        self.assertEqual(result.kind, "duplicate")
        self.assertEqual(len(list(self.store.envelopes_dir.glob("*.json"))), 1)
        self.assertEqual(len(list(self.store.duplicates_dir.rglob("*.json"))), 1)

    def test_simultaneous_same_core_submissions_are_created_once_and_deduplicated(self):
        second = HandoffEnvelope.from_dict(
            {**self.envelope.to_dict(), "delivery_id": "delivery:test:002"}
        )
        real_publish_bytes = store_module._publish_bytes
        payload_race = threading.Barrier(2)

        def synchronized_payload_publish(path, data):
            payload_race.wait(timeout=5)
            return real_publish_bytes(path, data)

        with mock.patch(
            "eml_handoff.store._publish_bytes",
            side_effect=synchronized_payload_publish,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(self.store.submit, envelope, self.snapshot)
                    for envelope in (self.envelope, second)
                ]
                kinds = sorted(future.result(timeout=10).kind for future in futures)

        self.assertEqual(kinds, ["created", "duplicate"])
        self.assertEqual(len(list(self.store.envelopes_dir.glob("*.json"))), 1)
        self.assertEqual(len(list(self.store.duplicates_dir.rglob("*.json"))), 1)

    def test_same_id_different_core_is_quarantined_without_payload_text(self):
        self.store.submit(self.envelope, self.snapshot)
        collision = HandoffEnvelope.from_dict(
            {**self.envelope.to_dict(), "target_ref": "task:other"}
        )
        with self.assertRaises(HandoffError) as caught:
            self.store.submit(collision, self.snapshot)
        self.assertEqual(caught.exception.code, "handoff_content_collision")
        records = list(self.store.quarantine_dir.glob("*.json"))
        self.assertEqual(len(records), 1)
        self.assertNotIn("hello handoff", records[0].read_text(encoding="utf-8"))

    def test_source_outside_root_rejects(self):
        outside = self.base / "outside.md"
        outside.write_text("outside", encoding="utf-8")
        with self.assertRaises(HandoffError) as caught:
            read_source_payload(outside, self.config)
        self.assertEqual(caught.exception.code, "payload_outside_allowlist")

    def test_extension_and_size_are_single_factor_refusals(self):
        binary = self.source_root / "bad.bin"
        binary.write_bytes(b"x")
        with self.assertRaises(HandoffError) as caught:
            read_source_payload(binary, self.config)
        self.assertEqual(caught.exception.code, "payload_extension_unsupported")

        tiny = HandoffConfig.from_dict(
            {**self.config.to_dict(), "default_max_payload_bytes": 4}
        )
        with self.assertRaises(HandoffError) as caught:
            read_source_payload(self.payload, tiny)
        self.assertEqual(caught.exception.code, "payload_too_large")

    def test_allowed_text_extensions_reject_binary_content(self):
        cases = {
            "invalid-utf8.txt": b"\x00\xff",
            "nul-control.md": b"valid prefix\x00hidden suffix\n",
        }
        for name, data in cases.items():
            with self.subTest(name=name):
                path = self.source_root / name
                path.write_bytes(data)
                with self.assertRaises(HandoffError) as caught:
                    read_source_payload(path, self.config)
                self.assertEqual(caught.exception.code, "payload_binary_unsupported")

        self.assertEqual(read_source_payload(self.payload, self.config).data, b"hello handoff\n")

    def test_envelope_digest_size_media_and_ref_must_match_snapshot(self):
        mutations = (
            (replace(self.envelope, payload_sha256="B" * 64), "payload_integrity_failed"),
            (replace(self.envelope, payload_bytes=1), "payload_size_mismatch"),
            (replace(self.envelope, payload_media_type="text/plain"), "payload_media_mismatch"),
            (replace(self.envelope, payload_ref="payloads/wrong.md"), "payload_ref_mismatch"),
        )
        for envelope, code in mutations:
            with self.subTest(code=code):
                with self.assertRaises(HandoffError) as caught:
                    self.store.submit(envelope, self.snapshot)
                self.assertEqual(caught.exception.code, code)

    def test_reparse_guard_failure_is_preserved(self):
        with mock.patch(
            "eml_handoff.filesystem._verify_no_reparse",
            side_effect=HandoffError("payload_reparse_refused", "fixture"),
        ):
            with self.assertRaises(HandoffError) as caught:
                read_source_payload(self.payload, self.config)
        self.assertEqual(caught.exception.code, "payload_reparse_refused")

    def test_real_symlink_or_junction_root_is_rejected_before_resolution(self):
        real_root = self.base / "real-source"
        real_root.mkdir()
        real_payload = real_root / "message.md"
        real_payload.write_text("linked payload\n", encoding="utf-8")
        linked_root = self.base / "linked-source"
        try:
            os.symlink(real_root, linked_root, target_is_directory=True)
        except OSError as error:
            if os.name != "nt":
                self.skipTest(f"symlink creation unavailable: {error}")
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(linked_root), str(real_root)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                self.skipTest(f"junction creation unavailable: {result.stderr}")
        try:
            linked_payload = linked_root / "message.md"
            config = HandoffConfig.from_dict(
                {**valid_config(), "allowed_source_roots": [str(linked_root)]}
            )
            with self.assertRaises(HandoffError) as caught:
                read_source_payload(linked_payload, config)
            self.assertEqual(caught.exception.code, "payload_reparse_refused")
        finally:
            if linked_root.is_symlink():
                linked_root.unlink()
            elif linked_root.exists():
                os.rmdir(linked_root)

    def test_real_in_root_symlink_is_rejected_before_resolution(self):
        in_root_link = self.source_root / "linked-message.md"
        try:
            os.symlink(self.payload, in_root_link)
        except OSError as error:
            self.skipTest(f"file symlink creation unavailable: {error}")
        with self.assertRaises(HandoffError) as caught:
            read_source_payload(in_root_link, self.config)
        self.assertEqual(caught.exception.code, "payload_reparse_refused")

    def test_envelope_publish_failure_leaves_only_orphan_payload_and_retry_succeeds(self):
        with mock.patch(
            "eml_handoff.store.publish_no_replace",
            side_effect=HandoffError("immutable_publish_failed", "fixture"),
        ):
            with self.assertRaises(HandoffError):
                self.store.submit(self.envelope, self.snapshot)
        self.assertTrue(self.store.payload_path(self.envelope).is_file())
        self.assertFalse(self.store.envelope_path(self.envelope.handoff_id).exists())

        result = self.store.submit(self.envelope, self.snapshot)
        self.assertEqual(result.kind, "created")

    def test_handoff_key_is_windows_safe_and_deterministic(self):
        first = handoff_key("handoff:test:001")
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertNotIn(":", first)
        self.assertEqual(first, handoff_key("handoff:test:001"))
        self.assertNotEqual(first, handoff_key("handoff:test:002"))


if __name__ == "__main__":
    unittest.main()
