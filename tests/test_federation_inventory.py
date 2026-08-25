from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.federation.inventory import build_inventory, diff_inventories
from eml_pmw.federation.models import FederatedEvent, FederationConfig
from eml_pmw.federation.store import FederationStore
from eml_pmw.integration.contracts import load_local_contract
from tests.federation_helpers import PAYLOAD, event_at, valid_config


class FederationInventoryTests(unittest.TestCase):
    def make_store(self, name):
        root = Path(self.temp.name) / name
        return FederationStore(root, FederationConfig.from_dict(valid_config()))

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_inventory_is_payload_free_and_copies_exact_fabric_class(self):
        store = self.make_store("local")
        first = FederatedEvent.from_dict(event_at(1, "event:first"))
        second = FederatedEvent.from_dict(
            event_at(
                2,
                "event:second",
                ["event:first"],
                fabric_payload_class="P1",
            )
        )
        store.submit(first, PAYLOAD, delivery_id="delivery:first")
        store.submit(second, PAYLOAD, delivery_id="delivery:second")

        inventory = build_inventory(store)
        value = inventory.to_dict()

        self.assertEqual(value["causal_heads"], ["event:second"])
        self.assertEqual(
            [record["fabric_payload_class"] for record in value["events"]],
            ["P0", "P1"],
        )
        self.assertEqual(
            value["replica_ranges"],
            [
                {
                    "replica_id": "replica:a",
                    "store_generation": "generation:1",
                    "minimum_sequence": 1,
                    "maximum_sequence": 2,
                    "event_count": 2,
                }
            ],
        )
        def collect_keys(item):
            if isinstance(item, dict):
                return set(item) | {
                    key
                    for child in item.values()
                    for key in collect_keys(child)
                }
            if isinstance(item, list):
                return {
                    key
                    for child in item
                    for key in collect_keys(child)
                }
            return set()

        keys = collect_keys(value)
        for forbidden in (
            "payload_body",
            "bearer",
            "private_memory",
            "resident_identity_verified",
            "claimed_actor_ref",
            "authority_ref",
        ):
            self.assertNotIn(forbidden, keys)
        self.assertNotIn(PAYLOAD, inventory.canonical_bytes)

    def test_inventory_diff_reports_missing_and_digest_mismatch_separately(self):
        local = self.make_store("local")
        remote = self.make_store("remote")
        shared = FederatedEvent.from_dict(event_at(1, "event:shared"))
        remote_only = FederatedEvent.from_dict(event_at(2, "event:remote-only"))
        local.submit(shared, PAYLOAD, delivery_id="delivery:local")
        remote.submit(shared, PAYLOAD, delivery_id="delivery:remote-shared")
        remote.submit(remote_only, PAYLOAD, delivery_id="delivery:remote-only")

        result = diff_inventories(build_inventory(local), build_inventory(remote))

        self.assertEqual(result.missing_from_local, ("event:remote-only",))
        self.assertEqual(result.missing_from_remote, ())
        self.assertEqual(result.digest_mismatches, ())

    def test_inventory_is_byte_deterministic_and_schema_valid(self):
        store = self.make_store("local")
        store.submit(
            FederatedEvent.from_dict(event_at(1, "event:fixture")),
            PAYLOAD,
            delivery_id="delivery:fixture",
        )

        first = build_inventory(store)
        second = build_inventory(store)
        schema = load_local_contract("federation-inventory-v1.schema.json")

        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(first.to_dict(), schema)


if __name__ == "__main__":
    unittest.main()
