from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.cli import main
from eml_pmw.federation.authority import AuthorityVerification
from eml_pmw.federation.models import FederatedEvent, FederationConfig
from eml_pmw.federation.reconcile import reconcile_event
from eml_pmw.federation.store import FederationStore
from tests.federation_helpers import (
    event_for_replica,
    observer,
    update_event,
    valid_config,
    valid_event,
)


def write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def run_cli(argv):
    output = io.StringIO()
    with redirect_stdout(output):
        code = main(argv)
    text = output.getvalue()
    return code, json.loads(text), text.encode("utf-8")


class FederationCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "store"
        self.payload = self.root / "payload.json"
        self.payload.write_text('{"field":"status","value":"open"}', encoding="utf-8")
        self.config = self.root / "config.json"
        write_json(
            self.config,
            valid_config(allowed_source_roots=[str(self.root.resolve())]),
        )
        self.realm = self.root / "realm.json"
        self.replica = self.root / "replica.json"
        event = valid_event()
        write_json(self.realm, event["realm_ref"])
        write_json(self.replica, event["replica_ref"])

    def create_args(self, *, event_id="event:cli:1", kind="pmw.task.field_set"):
        return [
            "event-create",
            "--root",
            str(self.store),
            "--config",
            str(self.config),
            "--payload",
            str(self.payload),
            "--kind",
            kind,
            "--subject-ref",
            "pmw-task:fixture",
            "--realm-ref",
            str(self.realm),
            "--replica-ref",
            str(self.replica),
            "--event-id",
            event_id,
            "--replica-seq",
            "1",
            "--authority-ref",
            "authority:fixture",
            "--claimed-actor-ref",
            "actor:fixture",
            "--claimed-instance-ref",
            "instance:fixture",
            "--payload-class",
            "P0",
            "--local-recorded-at",
            "2026-08-25T00:00:00Z",
            "--delivery-id",
            f"delivery:{event_id}",
        ]

    def test_create_inventory_and_status_are_deterministic(self):
        created = run_cli(self.create_args())
        self.assertEqual(created[0], 0)
        self.assertEqual(created[1]["status"], "created")

        inventory_args = [
            "event-inventory",
            "--root",
            str(self.store),
            "--config",
            str(self.config),
        ]
        first = run_cli(inventory_args)
        second = run_cli(inventory_args)
        self.assertEqual(first[0], 0)
        self.assertEqual(first[1]["schema"], "pmw-federation-inventory/v1")
        self.assertEqual(first[2], second[2])

        status = run_cli(
            ["sync-status", "--root", str(self.store), "--config", str(self.config)]
        )
        self.assertEqual(status[:2], (0, {"conflicts": 0, "events": 1, "pending_dependencies": 0, "resolutions": 0, "status": "ready"}))

    def test_exit_classes_keep_input_rejection_conflict_and_unmeasured_separate(self):
        missing = run_cli(
            [
                "event-inventory",
                "--root",
                str(self.store),
                "--config",
                str(self.root / "missing.json"),
            ]
        )
        self.assertEqual(missing[0], 1)
        self.assertEqual(missing[1]["reason_codes"], ["input_unreadable"])

        rejected = run_cli(self.create_args(kind="pmw.not_allowed"))
        self.assertEqual(rejected[0], 2)
        self.assertEqual(rejected[1]["reason_codes"], ["event_kind_not_allowed"])

        run_cli(self.create_args(event_id="event:unmeasured"))
        unmeasured = run_cli(
            [
                "event-reconcile",
                "event:unmeasured",
                "--root",
                str(self.store),
                "--config",
                str(self.config),
            ]
        )
        self.assertEqual(unmeasured[0], 4)
        self.assertEqual(unmeasured[1]["status"], "unmeasured")

    def test_duplicate_key_config_is_typed_input_error(self):
        duplicate = self.root / "duplicate.json"
        duplicate.write_text(
            '{"schema":"pmw-federation-config/v1","schema":"duplicate"}',
            encoding="utf-8",
        )

        result = run_cli(
            [
                "event-inventory",
                "--root",
                str(self.store),
                "--config",
                str(duplicate),
            ]
        )

        self.assertEqual(result[0], 1)
        self.assertEqual(result[1]["reason_codes"], ["input_duplicate_key"])

    def test_event_diff_and_import_complete_inventory_pull_flow(self):
        run_cli(self.create_args(event_id="event:source"))
        source_inventory = run_cli(
            ["event-inventory", "--root", str(self.store), "--config", str(self.config)]
        )[1]
        target_root = self.root / "target-store"
        target_inventory = run_cli(
            ["event-inventory", "--root", str(target_root), "--config", str(self.config)]
        )[1]
        source_file = self.root / "source-inventory.json"
        target_file = self.root / "target-inventory.json"
        write_json(source_file, source_inventory)
        write_json(target_file, target_inventory)

        difference = run_cli(["event-diff", str(target_file), str(source_file)])
        self.assertEqual(difference[0], 0)
        self.assertEqual(difference[1]["missing_from_local"], ["event:source"])

        source_store = FederationStore(
            self.store, FederationConfig.from_dict(_read_json(self.config))
        )
        event = source_store.get_event("event:source")
        event_file = source_store.event_path(event)
        observer_file = self.root / "observer.json"
        write_json(observer_file, observer(observer_id="observer:cli:import"))
        imported = run_cli(
            [
                "event-import",
                "--root",
                str(target_root),
                "--config",
                str(self.config),
                "--event",
                str(event_file),
                "--payload",
                str(self.payload),
                "--observer",
                str(observer_file),
            ]
        )
        self.assertEqual(imported[:2], (0, {"event_id": "event:source", "missing_parent_ids": [], "status": "imported"}))

    def test_conflict_show_and_resolve_preserve_original_record(self):
        config_file = self.root / "resolution-config.json"
        config_value = valid_config(
            allowed_source_roots=[str(self.root.resolve())],
            allowed_event_kinds=["pmw.task.field_set", "pmw.conflict.resolution"],
            authority_required_event_kinds=["pmw.task.field_set", "pmw.conflict.resolution"],
        )
        write_json(config_file, config_value)
        store = FederationStore(
            self.root / "resolution-store",
            FederationConfig.from_dict(config_value),
        )
        left_value, left_payload = update_event("a", "left")
        right_value, right_payload = update_event("b", "right")
        left = FederatedEvent.from_dict(left_value)
        right = FederatedEvent.from_dict(right_value)
        store.submit(left, left_payload, delivery_id="delivery:left")
        store.submit(right, right_payload, delivery_id="delivery:right")

        class VerifiedFixture:
            def verify(self, *, authority_ref, action, subject_ref):
                return AuthorityVerification(
                    "verified", authority_ref, action, subject_ref, "evidence:authority:fixture"
                )

        conflict = reconcile_event(store, right.event_id, verifier=VerifiedFixture())
        conflict_before = store.conflict_path(conflict.conflict_id).read_bytes()
        shown = run_cli(
            [
                "conflict-show",
                conflict.conflict_id,
                "--root",
                str(store.root),
                "--config",
                str(config_file),
            ]
        )
        self.assertEqual(shown[0], 0)
        self.assertEqual(shown[1]["conflict_id"], conflict.conflict_id)

        members = sorted((left.event_id, right.event_id))
        resolution_payload = json.dumps(
            {
                "conflict_id": conflict.conflict_id,
                "member_event_ids": members,
                "selected_event_id": left.event_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        resolution = FederatedEvent.from_dict(
            event_for_replica(
                "resolver",
                1,
                "event:resolution:cli",
                parents=members,
                event_kind="pmw.conflict.resolution",
                subject_ref=conflict.conflict_id,
                payload_ref="payloads/resolution-cli.json",
                payload_sha256=hashlib.sha256(resolution_payload).hexdigest().upper(),
            )
        )
        event_file = self.root / "resolution-event.json"
        payload_file = self.root / "resolution-payload.json"
        authority_file = self.root / "resolution-authority.json"
        event_file.write_bytes(resolution.canonical_bytes)
        payload_file.write_bytes(resolution_payload)
        write_json(
            authority_file,
            {
                "status": "verified",
                "authority_ref": resolution.authority_ref,
                "action": "resolve_conflict",
                "subject_ref": conflict.conflict_id,
                "evidence_ref": "evidence:authority:fixture",
            },
        )

        resolved = run_cli(
            [
                "conflict-resolve",
                conflict.conflict_id,
                "--root",
                str(store.root),
                "--config",
                str(config_file),
                "--event",
                str(event_file),
                "--payload",
                str(payload_file),
                "--authority-verification",
                str(authority_file),
            ]
        )
        self.assertEqual(resolved[0], 0)
        self.assertEqual(resolved[1]["status"], "resolved")
        self.assertEqual(store.conflict_path(conflict.conflict_id).read_bytes(), conflict_before)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
