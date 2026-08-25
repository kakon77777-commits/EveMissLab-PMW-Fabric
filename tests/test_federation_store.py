from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.federation.models import FederatedEvent, FederationConfig
from eml_pmw.federation.store import FederationStore
from tests.federation_helpers import (
    PAYLOAD,
    assert_error_code,
    event_at,
    valid_config,
    valid_event,
)


class FederationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = FederationStore(
            Path(self.temp.name), FederationConfig.from_dict(valid_config())
        )

    def test_payload_first_submit_is_retrievable_and_canonical(self):
        event = FederatedEvent.from_dict(valid_event())

        result = self.store.submit(event, PAYLOAD, delivery_id="delivery:one")

        self.assertEqual(result.kind, "created")
        self.assertEqual(self.store.get_event(event.event_id), event)
        self.assertEqual(Path(result.payload_path).read_bytes(), PAYLOAD)
        self.assertEqual(Path(result.event_path).read_bytes(), event.canonical_bytes)

    def test_simultaneous_same_event_commits_once(self):
        event = FederatedEvent.from_dict(event_at(1, "event:concurrent"))

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda delivery: self.store.submit(
                        event, PAYLOAD, delivery_id=delivery
                    ),
                    ("delivery:one", "delivery:two"),
                )
            )

        self.assertEqual(sorted(item.kind for item in results), ["created", "duplicate"])
        self.assertEqual(len(self.store.events()), 1)

    def test_independent_store_instances_recover_same_event_publish_race(self):
        event = FederatedEvent.from_dict(event_at(1, "event:cross-store-race"))
        other = FederationStore(self.store.root, self.store.config)
        barrier = threading.Barrier(2)
        real_validate = FederationStore._validate_submission

        def synchronized_validate(candidate, submitted_event, data):
            real_validate(candidate, submitted_event, data)
            barrier.wait(timeout=5)

        with mock.patch.object(
            FederationStore,
            "_validate_submission",
            autospec=True,
            side_effect=synchronized_validate,
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(
                        candidate.submit,
                        event,
                        PAYLOAD,
                        delivery_id=f"delivery:{index}",
                    )
                    for index, candidate in enumerate((self.store, other), start=1)
                ]
                results = [future.result() for future in futures]

        self.assertEqual(sorted(item.kind for item in results), ["created", "duplicate"])
        self.assertEqual(len(self.store.events()), 1)

    def test_same_event_id_with_different_core_is_quarantined(self):
        first = FederatedEvent.from_dict(event_at(1, "event:collision"))
        changed = FederatedEvent.from_dict(
            event_at(1, "event:collision", claimed_actor_ref="actor:other")
        )
        self.store.submit(first, PAYLOAD, delivery_id="delivery:one")

        with assert_error_code(self, "event_content_collision"):
            self.store.submit(changed, PAYLOAD, delivery_id="delivery:two")

        self.assertEqual(len(list(self.store.quarantine_dir.glob("*.json"))), 1)

    def test_same_replica_sequence_with_different_event_is_quarantined(self):
        first = FederatedEvent.from_dict(event_at(2, "event:sequence-a"))
        changed = FederatedEvent.from_dict(event_at(2, "event:sequence-b"))
        self.store.submit(first, PAYLOAD, delivery_id="delivery:one")

        with assert_error_code(self, "replica_sequence_collision"):
            self.store.submit(changed, PAYLOAD, delivery_id="delivery:two")

        self.assertEqual(len(self.store.events()), 1)
        self.assertEqual(len(list(self.store.quarantine_dir.glob("*.json"))), 1)

    def test_payload_digest_mismatch_fails_before_event_commit(self):
        event = FederatedEvent.from_dict(valid_event())

        with assert_error_code(self, "payload_integrity_failed"):
            self.store.submit(event, PAYLOAD + b"x", delivery_id="delivery:one")

        self.assertEqual(self.store.events(), ())


if __name__ == "__main__":
    unittest.main()
