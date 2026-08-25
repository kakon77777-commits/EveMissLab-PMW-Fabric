from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.federation.authority import AuthorityVerification
from eml_pmw.federation.models import FederatedEvent, FederationConfig
from eml_pmw.federation.reconcile import reconcile_event, resolve_conflict
from eml_pmw.federation.store import FederationStore
from tests.federation_helpers import (
    assert_error_code,
    event_for_replica,
    update_event,
    valid_config,
)


class FixtureVerifier:
    def __init__(self, status):
        self.status = status

    def verify(self, *, authority_ref, action, subject_ref):
        return AuthorityVerification(
            status=self.status,
            authority_ref=authority_ref,
            action=action,
            subject_ref=subject_ref,
            evidence_ref="evidence:authority:fixture" if self.status == "verified" else None,
        )


class FederationResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config = valid_config(
            allowed_event_kinds=["pmw.task.field_set", "pmw.conflict.resolution"],
            authority_required_event_kinds=["pmw.task.field_set", "pmw.conflict.resolution"],
        )
        self.store = FederationStore(
            Path(self.temp.name), FederationConfig.from_dict(config)
        )
        left_value, left_payload = update_event("a", "left")
        right_value, right_payload = update_event("b", "right")
        self.left = FederatedEvent.from_dict(left_value)
        self.right = FederatedEvent.from_dict(right_value)
        self.store.submit(self.left, left_payload, delivery_id="delivery:left")
        self.store.submit(self.right, right_payload, delivery_id="delivery:right")
        self.conflict = reconcile_event(
            self.store,
            self.right.event_id,
            verifier=FixtureVerifier("verified"),
        )

    def resolution(self):
        members = sorted((self.left.event_id, self.right.event_id))
        payload = json.dumps(
            {
                "conflict_id": self.conflict.conflict_id,
                "member_event_ids": members,
                "selected_event_id": self.left.event_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        value = event_for_replica(
            "resolver",
            1,
            "event:resolution:fixture",
            parents=members,
            event_kind="pmw.conflict.resolution",
            subject_ref=self.conflict.conflict_id,
            payload_ref="payloads/resolution-fixture.json",
            payload_sha256=hashlib.sha256(payload).hexdigest().upper(),
        )
        return FederatedEvent.from_dict(value), payload

    def test_resolution_without_receiver_verifiable_authority_fails_closed(self):
        event, payload = self.resolution()

        with assert_error_code(self, "resolution_authority_unverified"):
            resolve_conflict(
                self.store,
                self.conflict.conflict_id,
                event,
                payload,
                verifier=None,
            )

        self.assertFalse(self.store.event_index_path(event.event_id).exists())

    def test_verified_resolution_is_new_event_and_preserves_conflict(self):
        event, payload = self.resolution()
        conflict_before = self.store.conflict_path(self.conflict.conflict_id).read_bytes()

        result = resolve_conflict(
            self.store,
            self.conflict.conflict_id,
            event,
            payload,
            verifier=FixtureVerifier("verified"),
        )

        self.assertEqual(result.status, "resolved")
        self.assertEqual(self.store.get_event(event.event_id), event)
        self.assertEqual(
            self.store.conflict_path(self.conflict.conflict_id).read_bytes(),
            conflict_before,
        )
        self.assertTrue(
            self.store.resolution_path(self.conflict.conflict_id, event.event_id).is_file()
        )

    def test_resolution_must_name_every_conflict_member(self):
        event, payload = self.resolution()
        incomplete_payload = json.dumps(
            {
                "conflict_id": self.conflict.conflict_id,
                "member_event_ids": [self.left.event_id],
                "selected_event_id": self.left.event_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        incomplete_value = {
            **event.to_dict(),
            "payload_sha256": hashlib.sha256(incomplete_payload).hexdigest().upper(),
        }

        with assert_error_code(self, "conflict_members_incomplete"):
            resolve_conflict(
                self.store,
                self.conflict.conflict_id,
                FederatedEvent.from_dict(incomplete_value),
                incomplete_payload,
                verifier=FixtureVerifier("verified"),
            )


if __name__ == "__main__":
    unittest.main()
