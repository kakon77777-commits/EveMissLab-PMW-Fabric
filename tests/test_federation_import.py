from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.federation.importer import import_event
from eml_pmw.federation.models import FederatedEvent, FederationConfig
from eml_pmw.federation.store import FederationStore
from tests.federation_helpers import (
    PAYLOAD,
    assert_error_code,
    event_at,
    observer,
    valid_config,
)


class FederationImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = FederationStore(
            Path(self.temp.name), FederationConfig.from_dict(valid_config())
        )

    def test_valid_import_writes_receiver_observation_after_event(self):
        event = FederatedEvent.from_dict(event_at(1, "event:imported"))

        result = import_event(
            self.store, event.canonical_bytes, PAYLOAD, observer()
        )

        self.assertEqual(result.status, "imported")
        self.assertEqual(self.store.get_event(event.event_id), event)
        self.assertTrue(
            self.store.observation_path(event.event_id, observer()["observer_id"]).is_file()
        )

    def test_payload_mutation_quarantines_before_observation(self):
        event = FederatedEvent.from_dict(event_at(1, "event:mutated"))

        with assert_error_code(self, "payload_integrity_failed"):
            import_event(
                self.store, event.canonical_bytes, PAYLOAD + b"x", observer()
            )

        self.assertFalse(
            self.store.observation_path(event.event_id, observer()["observer_id"]).exists()
        )
        self.assertEqual(self.store.events(), ())

    def test_noncanonical_event_bytes_fail_before_store(self):
        event = FederatedEvent.from_dict(event_at(1, "event:pretty"))
        pretty = json.dumps(event.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")

        with assert_error_code(self, "event_not_canonical"):
            import_event(self.store, pretty, PAYLOAD, observer())

        self.assertEqual(self.store.events(), ())

    def test_missing_parent_requires_inventory_advertisement(self):
        event = FederatedEvent.from_dict(
            event_at(2, "event:child", ["event:missing"])
        )

        with assert_error_code(self, "missing_parent_not_advertised"):
            import_event(self.store, event.canonical_bytes, PAYLOAD, observer())

        accepted = import_event(
            self.store,
            event.canonical_bytes,
            PAYLOAD,
            observer(advertised_missing_parent_ids=["event:missing"]),
        )
        self.assertEqual(accepted.status, "pending_dependencies")
        self.assertEqual(accepted.missing_parent_ids, ("event:missing",))

    def test_cycle_is_quarantined_without_receiver_observation(self):
        left = FederatedEvent.from_dict(
            event_at(1, "event:left", ["event:right"])
        )
        right = FederatedEvent.from_dict(
            event_at(2, "event:right", ["event:left"])
        )
        import_event(
            self.store,
            left.canonical_bytes,
            PAYLOAD,
            observer(advertised_missing_parent_ids=["event:right"]),
        )

        with assert_error_code(self, "causal_cycle"):
            import_event(self.store, right.canonical_bytes, PAYLOAD, observer())

        self.assertFalse(
            self.store.observation_path(right.event_id, observer()["observer_id"]).exists()
        )
        self.assertEqual(len(list(self.store.quarantine_dir.glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
