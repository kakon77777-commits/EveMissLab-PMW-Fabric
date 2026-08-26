from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from eml_wake.canonical import canonical_bytes, loads_strict
from eml_pmw.relations.errors import RelationContractError
from eml_pmw.relations.events import RelationContractEvent
from eml_pmw.relations.store import RelationContractStore
from tests.relation_contract_helpers import (
    assert_relation_error,
    mutate_and_rebind,
    valid_contract_version,
    valid_relation_contract_event,
    valid_relation_version,
)


def _concurrent_put(args):
    root, value = args
    try:
        return RelationContractStore(root).put_object("contract", value).status
    except RelationContractError as error:
        if error.code == "object_identity_collision":
            return "quarantined"
        return f"error:{error.code}"


def fail_after_object_bundle(stage):
    if stage == "after_object_bundle":
        raise RelationContractError(
            "index_publication_interrupted", "injected after object bundle"
        )


class RelationContractStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "store"

    def tearDown(self):
        self.temporary.cleanup()

    def test_same_version_identity_different_digest_is_quarantined_not_replaced(self):
        store = RelationContractStore(self.root)
        first_value = valid_contract_version()
        first = store.put_object("contract", first_value)
        changed = mutate_and_rebind(
            first_value, {"scope": ["resource:other#read"]}
        )

        with assert_relation_error(self, "object_identity_collision"):
            store.put_object("contract", changed)

        self.assertEqual(store.get_object(first.content_digest), first_value)
        self.assertEqual(len(store.objects_by_digest()), 1)
        self.assertEqual(len(list((self.root / "quarantine").glob("*.json"))), 1)

    def test_new_contract_version_is_a_distinct_identity(self):
        store = RelationContractStore(self.root)
        first = valid_contract_version()
        second = mutate_and_rebind(
            first,
            {"version": 2, "parent_version_digest": first["content_digest"]},
        )
        self.assertEqual(store.put_object("contract", first).status, "created")
        self.assertEqual(store.put_object("contract", second).status, "created")
        self.assertEqual(len(store.objects_by_digest()), 2)

    def test_concurrent_same_identity_different_digest_has_one_winner(self):
        first = mutate_and_rebind(
            valid_contract_version(), {"scope": ["resource:a#read"]}
        )
        second = mutate_and_rebind(
            valid_contract_version(), {"scope": ["resource:b#read"]}
        )
        with ProcessPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    _concurrent_put,
                    ((str(self.root), first), (str(self.root), second)),
                )
            )
        self.assertEqual(sorted(results), ["created", "quarantined"])
        self.assertEqual(len(RelationContractStore(self.root).objects_by_digest()), 1)

    def test_dynamic_object_kind_parent_exists_before_safe_publication_check(self):
        class ParentFirstStore(RelationContractStore):
            def _safe_store_path(self, path, *, must_exist):
                if (
                    not must_exist
                    and path.parent.parent == self.objects_dir
                    and not path.parent.is_dir()
                ):
                    raise RelationContractError(
                        "storage_path_refused", "object kind parent missing"
                    )
                return super()._safe_store_path(path, must_exist=must_exist)

        store = ParentFirstStore(self.root)
        result = store.put_object("contract", valid_contract_version())
        self.assertEqual(result.status, "created")

    def test_missing_parent_fails_before_event_publication(self):
        store = RelationContractStore(self.root)
        contract = valid_contract_version()
        store.put_object("contract", contract)
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                contract,
                event_id="event:store:missing-parent",
                parents=("event:missing",),
            )
        )
        with assert_relation_error(self, "contract_parent_missing"):
            store.append_event(event)
        self.assertEqual(store.events(), ())

    def test_event_kind_must_match_referenced_object_before_publication(self):
        store = RelationContractStore(self.root)
        relation = valid_relation_version(
            relation_class="descriptive", acceptance_rule="none"
        )
        store.put_object("relation", relation)
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                relation,
                event_id="event:store:wrong-object-kind",
            )
        )

        with assert_relation_error(self, "event_object_kind_mismatch"):
            store.append_event(event)
        self.assertEqual(store.events(), ())

    def test_verify_rejects_persisted_event_object_kind_mismatch(self):
        store = RelationContractStore(self.root)
        relation = valid_relation_version(
            relation_class="descriptive", acceptance_rule="none"
        )
        store.put_object("relation", relation)
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                relation,
                event_id="event:store:persisted-wrong-kind",
            )
        )
        event_path = store._event_path(event.event_id)
        event_path.write_bytes(canonical_bytes(store._event_bundle(event)))
        index_path = store._event_index_path(event.event_digest)
        index_path.write_bytes(canonical_bytes(store._event_index(event, event_path)))

        verification = store.verify()
        self.assertEqual(verification.status, "invalid")
        self.assertIn("event_object_kind_mismatch", verification.error_codes)

    def test_event_id_collision_quarantines_loser_and_duplicate_is_idempotent(self):
        store = RelationContractStore(self.root)
        contract = valid_contract_version()
        store.put_object("contract", contract)
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted", contract, event_id="event:store:draft"
            )
        )
        self.assertEqual(store.append_event(event).status, "created")
        self.assertEqual(store.append_event(event).status, "existing")
        duplicate_paths = list((self.root / "duplicates").glob("*.json"))
        self.assertEqual(len(duplicate_paths), 1)
        first_duplicate = duplicate_paths[0].read_bytes()
        duplicate = loads_strict(first_duplicate)
        self.assertEqual(
            duplicate["schema"],
            "arcp/relation-contract-duplicate-delivery/0.1",
        )
        self.assertEqual(duplicate["event_id"], event.event_id)
        self.assertEqual(duplicate["event_digest"], event.event_digest)
        self.assertEqual(store.append_event(event).status, "existing")
        self.assertEqual(duplicate_paths[0].read_bytes(), first_duplicate)

        changed = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                contract,
                event_id="event:store:draft",
                local_recorded_at="2026-08-26T02:00:00Z",
            )
        )
        with assert_relation_error(self, "event_id_collision"):
            store.append_event(changed)
        self.assertEqual(len(store.events()), 1)

    def test_tampered_duplicate_evidence_turns_verification_red(self):
        store = RelationContractStore(self.root)
        contract = valid_contract_version()
        store.put_object("contract", contract)
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted", contract, event_id="event:store:duplicate-tamper"
            )
        )
        store.append_event(event)
        store.append_event(event)
        duplicate_path = next((self.root / "duplicates").glob("*.json"))
        value = loads_strict(duplicate_path.read_bytes())
        value["event_digest"] = "sha256:wrong"
        duplicate_path.write_bytes(canonical_bytes(value))

        self.assertIn("duplicate_evidence_invalid", store.verify().error_codes)
        with assert_relation_error(self, "duplicate_evidence_invalid"):
            store.append_event(event)

    def test_corrupt_parent_is_rejected_before_child_publication(self):
        store = RelationContractStore(self.root)
        contract = valid_contract_version()
        store.put_object("contract", contract)
        parent = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted", contract, event_id="event:store:parent-corrupt"
            )
        )
        parent_result = store.append_event(parent)
        Path(parent_result.bundle_path).write_text("{not-json", encoding="utf-8")
        child = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                contract,
                event_id="event:store:child-after-corrupt",
                parents=(parent.event_id,),
            )
        )
        with assert_relation_error(self, "event_parent_invalid"):
            store.append_event(child)
        child_path = (
            self.root
            / "events"
            / f"{hashlib.sha256(child.event_id.encode('utf-8')).hexdigest()}.json"
        )
        self.assertFalse(child_path.exists())

    def test_crash_after_bundle_before_index_is_repairable(self):
        store = RelationContractStore(
            self.root, fault_injector=fail_after_object_bundle
        )
        value = valid_contract_version()
        with assert_relation_error(self, "index_publication_interrupted"):
            store.put_object("contract", value)

        reopened = RelationContractStore(self.root)
        self.assertEqual(reopened.verify().status, "repairable_index_gap")
        repaired = reopened.repair_indexes()
        self.assertEqual(repaired.created_indexes, 1)
        self.assertEqual(reopened.verify().status, "internally_consistent")
        self.assertEqual(reopened.get_object(value["content_digest"]), value)

    def test_object_index_cannot_escape_store_root(self):
        store = RelationContractStore(self.root)
        contract = valid_contract_version()
        result = store.put_object("contract", contract)
        outside = self.root.parent / "outside"
        outside.mkdir()
        outside_bundle = outside / Path(result.bundle_path).name
        shutil.copyfile(result.bundle_path, outside_bundle)
        Path(result.bundle_path).unlink()
        index = loads_strict(Path(result.index_path).read_bytes())
        index["bundle_path"] = f"../outside/{outside_bundle.name}"
        Path(result.index_path).write_bytes(canonical_bytes(index))

        with assert_relation_error(self, "storage_path_refused"):
            store.get_object(contract["content_digest"])
        self.assertIn("object_index_invalid", store.verify().error_codes)

    def test_object_index_path_must_be_canonical_relative_posix(self):
        store = RelationContractStore(self.root)
        contract = valid_contract_version()
        result = store.put_object("contract", contract)
        index = loads_strict(Path(result.index_path).read_bytes())
        index["bundle_path"] = index["bundle_path"].replace(
            "objects/", "objects//", 1
        )
        Path(result.index_path).write_bytes(canonical_bytes(index))

        with assert_relation_error(self, "storage_path_refused"):
            store.get_object(contract["content_digest"])

    def test_post_construction_reparse_swap_is_refused(self):
        store = RelationContractStore(self.root)
        contract = valid_contract_version()
        result = store.put_object("contract", contract)
        contract_dir = Path(result.bundle_path).parent
        outside = self.root.parent / "reparse-target"
        contract_dir.rename(outside)
        try:
            contract_dir.symlink_to(outside, target_is_directory=True)
        except OSError:
            outside.rename(contract_dir)
            self.skipTest("directory symlink creation is not permitted")

        with assert_relation_error(self, "storage_path_refused"):
            store.get_object(contract["content_digest"])

    def test_external_head_distinguishes_internal_consistency_from_checkpoint(self):
        store = RelationContractStore(self.root)
        contract = valid_contract_version()
        store.put_object("contract", contract)
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted", contract, event_id="event:store:head"
            )
        )
        store.append_event(event)
        head = store.head_digest()
        self.assertEqual(store.verify().status, "internally_consistent")
        self.assertFalse(store.verify().valid)
        self.assertEqual(store.verify(expected_head=head).status, "checkpoint_verified")
        self.assertTrue(store.verify(expected_head=head).valid)
        self.assertEqual(store.verify(expected_head="sha256:wrong").status, "invalid")

    def test_root_file_git_marker_and_symlink_are_refused(self):
        file_root = Path(self.temporary.name) / "root-file"
        file_root.write_text("not a directory", encoding="utf-8")
        git_root = Path(self.temporary.name) / "git-root"
        (git_root / ".git").mkdir(parents=True)
        for root in (file_root, git_root):
            with self.subTest(root=root):
                with assert_relation_error(self, "storage_root_refused"):
                    RelationContractStore(root)

        target = Path(self.temporary.name) / "target"
        target.mkdir()
        link = Path(self.temporary.name) / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlink creation is not permitted")
        with assert_relation_error(self, "storage_root_refused"):
            RelationContractStore(link)

    def test_verifier_detects_noncanonical_bundle_missing_parent_and_bad_index(self):
        store = RelationContractStore(self.root)
        contract = valid_contract_version()
        object_result = store.put_object("contract", contract)
        parent = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted", contract, event_id="event:store:parent"
            )
        )
        child = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted",
                contract,
                event_id="event:store:child",
                parents=(parent.event_id,),
            )
        )
        parent_result = store.append_event(parent)
        store.append_event(child)

        Path(parent_result.bundle_path).unlink()
        self.assertIn("event_parent_missing", store.verify().error_codes)

        # Restore in a fresh root, then corrupt an index and a bundle independently.
        other = RelationContractStore(Path(self.temporary.name) / "other")
        object_result = other.put_object("contract", contract)
        Path(object_result.index_path).write_text(
            json.dumps({"wrong": True}, separators=(",", ":")), encoding="utf-8"
        )
        self.assertIn("object_index_invalid", other.verify().error_codes)

        third = RelationContractStore(Path(self.temporary.name) / "third")
        object_result = third.put_object("contract", contract)
        value = json.loads(Path(object_result.bundle_path).read_text(encoding="utf-8"))
        Path(object_result.bundle_path).write_text(
            json.dumps(value, indent=2), encoding="utf-8"
        )
        self.assertIn("stored_record_not_canonical", third.verify().error_codes)


if __name__ == "__main__":
    unittest.main()
