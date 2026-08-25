from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.federation.models import FederatedEvent, FederationConfig
from eml_pmw.federation.authority import AuthorityVerification
from eml_pmw.federation.reconcile import detect_conflict, reconcile_event
from eml_pmw.federation.store import FederationStore
from tests.federation_helpers import (
    PAYLOAD,
    event_at,
    update_event,
    valid_config,
)


class FederationReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = FederationStore(
            Path(self.temp.name), FederationConfig.from_dict(valid_config())
        )

    @staticmethod
    def verifier():
        class VerifiedFixture:
            def verify(self, *, authority_ref, action, subject_ref):
                return AuthorityVerification(
                    status="verified",
                    authority_ref=authority_ref,
                    action=action,
                    subject_ref=subject_ref,
                    evidence_ref="evidence:authority:fixture",
                )

        return VerifiedFixture()

    def test_concurrent_field_updates_preserve_both_and_create_conflict(self):
        left_value, left_payload = update_event("a", "left")
        right_value, right_payload = update_event("b", "right")
        left = FederatedEvent.from_dict(left_value)
        right = FederatedEvent.from_dict(right_value)

        result = detect_conflict(left, left_payload, right, right_payload)

        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.conflict_class, "field_value_conflict")
        self.assertEqual(
            result.member_event_ids,
            tuple(sorted((left.event_id, right.event_id))),
        )

    def test_seven_conflict_classes_are_distinguishable(self):
        left_value, left_payload = update_event("a", "left")
        left = FederatedEvent.from_dict(left_value)
        cases = []

        other_field_value, other_field_payload = update_event("b", "right", field="owner")
        cases.append(("concurrent_nonexclusive", other_field_value, other_field_payload))

        field_value, field_payload = update_event("b", "right")
        cases.append(("field_value_conflict", field_value, field_payload))

        state_value, state_payload = update_event(
            "b", "closed", event_kind="pmw.task.state_transition"
        )
        cases.append(("state_transition_conflict", state_value, state_payload))

        authority_value, authority_payload = update_event(
            "b", "left", authority_ref="authority:other"
        )
        cases.append(("authority_conflict", authority_value, authority_payload))

        identity_value, identity_payload = update_event(
            "b", "resident:other", event_kind="ral.identity.binding"
        )
        cases.append(("identity_reference_conflict", identity_value, identity_payload))

        causal_value, causal_payload = update_event("b", "left")
        causal_value["causal_parents"] = ["event:missing"]
        cases.append(("causal_history_conflict", causal_value, causal_payload))

        collision_value = {**left_value, "claimed_actor_ref": "actor:other"}
        cases.append(("content_collision", collision_value, left_payload))

        for expected, right_value, right_payload in cases:
            with self.subTest(expected=expected):
                actual = detect_conflict(
                    left,
                    left_payload,
                    FederatedEvent.from_dict(right_value),
                    right_payload,
                )
                self.assertEqual(actual.conflict_class, expected)

    def test_reconcile_persists_conflict_without_rewriting_member_events(self):
        left_value, left_payload = update_event("a", "left")
        right_value, right_payload = update_event("b", "right")
        left = FederatedEvent.from_dict(left_value)
        right = FederatedEvent.from_dict(right_value)
        self.store.submit(left, left_payload, delivery_id="delivery:left")
        self.store.submit(right, right_payload, delivery_id="delivery:right")
        before = {
            event.event_id: self.store.event_path(event).read_bytes()
            for event in (left, right)
        }

        result = reconcile_event(
            self.store, right.event_id, verifier=self.verifier()
        )

        self.assertEqual(result.status, "conflict")
        self.assertTrue(self.store.conflict_path(result.conflict_id).is_file())
        self.assertEqual(
            before,
            {
                event.event_id: self.store.event_path(event).read_bytes()
                for event in (left, right)
            },
        )

    def test_required_authority_without_verifier_is_unmeasured(self):
        event = FederatedEvent.from_dict(event_at(1, "event:authority-unmeasured"))
        self.store.submit(event, PAYLOAD, delivery_id="delivery:fixture")

        result = reconcile_event(self.store, event.event_id)

        self.assertEqual(result.status, "unmeasured")
        self.assertEqual(result.reason_codes, ("authority_unmeasured",))


if __name__ == "__main__":
    unittest.main()
