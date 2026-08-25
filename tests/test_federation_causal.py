from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.federation.causal import (
    classify_relation,
    derive_heads,
    validate_graph,
)
from eml_pmw.federation.models import FederatedEvent
from tests.federation_helpers import event_at, event_for_replica


class FederationCausalTests(unittest.TestCase):
    def test_cycle_is_quarantined_not_pending(self):
        events = (
            FederatedEvent.from_dict(event_at(1, "event:a", ["event:b"])),
            FederatedEvent.from_dict(event_at(2, "event:b", ["event:a"])),
        )

        result = validate_graph(events)

        self.assertIs(result.valid, False)
        self.assertEqual(result.code, "causal_cycle")
        self.assertEqual(result.missing_parent_ids, ())

    def test_missing_parent_is_pending_dependency(self):
        events = (
            FederatedEvent.from_dict(event_at(1, "event:child", ["event:missing"])),
        )

        result = validate_graph(events)

        self.assertIs(result.valid, False)
        self.assertEqual(result.code, "pending_dependencies")
        self.assertEqual(result.missing_parent_ids, ("event:missing",))

    def test_heads_and_relations_use_only_causal_edges(self):
        events = (
            FederatedEvent.from_dict(event_at(1, "event:genesis")),
            FederatedEvent.from_dict(event_at(2, "event:child", ["event:genesis"])),
            FederatedEvent.from_dict(event_for_replica("b", 1, "event:parallel")),
        )

        self.assertEqual(derive_heads(events), ("event:child", "event:parallel"))
        self.assertEqual(
            classify_relation(events, "event:genesis", "event:child"), "before"
        )
        self.assertEqual(
            classify_relation(events, "event:child", "event:genesis"), "after"
        )
        self.assertEqual(
            classify_relation(events, "event:child", "event:parallel"), "concurrent"
        )
        self.assertEqual(
            classify_relation(events, "event:child", "event:child"), "same"
        )

    def test_duplicate_replica_sequence_is_graph_invalid(self):
        events = (
            FederatedEvent.from_dict(event_at(4, "event:left")),
            FederatedEvent.from_dict(event_at(4, "event:right")),
        )

        result = validate_graph(events)

        self.assertIs(result.valid, False)
        self.assertEqual(result.code, "replica_sequence_collision")


if __name__ == "__main__":
    unittest.main()
