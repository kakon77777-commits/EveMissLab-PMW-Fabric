from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest

from eml_wake.canonical import canonical_bytes, loads_strict
from eml_pmw.cli import main
from eml_pmw.relations.events import RelationContractEvent
from eml_pmw.relations.store import RelationContractStore
from scripts.check_federation_offline_boundary import scan_offline_boundary
from tests.relation_contract_helpers import (
    mutate_and_rebind,
    normalized_instant,
    valid_activation_policy,
    valid_contract_version,
    valid_relation_contract_event,
    valid_relation_version,
)
from test_relation_contract_lifecycle import active_v1_sequence


KIND_BY_SCHEMA = {
    "arcp/activation-policy/0.1": "activation_policy",
    "arcp/party-evidence-pin/0.1": "party_evidence",
    "arcp/relation-version/0.1": "relation",
    "arcp/contract-version/0.1": "contract",
    "arcp/grant-authority-evidence/0.1": "grant_authority",
    "arcp/representation-grant/0.1": "representation_grant",
    "arcp/party-acceptance/0.1": "acceptance",
    "arcp/commitment/0.1": "commitment",
    "arcp/authority-candidate/0.1": "authority_candidate",
    "arcp/authority-evaluation-receipt/0.1": "authority_evaluation",
}


def write_json(path: Path, value: dict) -> None:
    path.write_bytes(canonical_bytes(value))


def run_cli(argv):
    output = io.StringIO()
    with redirect_stdout(output):
        code = main(argv)
    raw = output.getvalue().encode("utf-8")
    return code, loads_strict(raw), raw


def put_objects(store: RelationContractStore, objects) -> None:
    for value in objects:
        store.put_object(KIND_BY_SCHEMA[value["schema"]], value)


def build_active_store(root: Path) -> tuple[RelationContractStore, dict]:
    store = RelationContractStore(root)
    contract, _, event_values, objects = active_v1_sequence()
    put_objects(store, objects.values())
    for value in event_values:
        store.append_event(RelationContractEvent.from_dict(value))
    return store, contract


def build_conflicted_store(root: Path) -> RelationContractStore:
    store = RelationContractStore(root)
    contract, authority, event_values, objects = active_v1_sequence()
    put_objects(store, objects.values())
    for value in event_values[:-1]:
        store.append_event(RelationContractEvent.from_dict(value))
    for side in ("left", "right"):
        event = valid_relation_contract_event(
            "contract.activated",
            contract,
            event_id=f"event:contract:activate:{side}",
            parents=("event:contract:accept:b:v1",),
            authority=authority,
            representation_grant=objects[
                next(
                    digest
                    for digest, item in objects.items()
                    if item.get("representation_grant_id")
                    == "representation-grant:fixture:a:1"
                )
            ],
        )
        store.append_event(RelationContractEvent.from_dict(event))
    return store


class RelationContractCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.good = self.root / "contract.json"
        self.policy = self.root / "policy.json"
        self.schema_bad = self.root / "schema-bad.json"
        good = valid_contract_version()
        bad = dict(good)
        bad.pop("scope")
        write_json(self.good, good)
        write_json(self.policy, valid_activation_policy())
        write_json(self.schema_bad, bad)

    def test_cli_exit_contract_keeps_five_outcomes_distinct(self):
        conflict_root = self.root / "conflicted"
        build_conflicted_store(conflict_root)
        cases = (
            (
                [
                    "relation-contract-validate",
                    str(self.good),
                    "--kind",
                    "contract",
                    "--policy",
                    str(self.policy),
                ],
                0,
                "valid",
            ),
            (
                [
                    "relation-contract-validate",
                    str(self.schema_bad),
                    "--kind",
                    "contract",
                ],
                2,
                "rejected",
            ),
            (
                ["relation-contract-project", "--root", str(conflict_root)],
                3,
                "conflicted",
            ),
            (
                ["relation-contract-project", "--root", str(self.root / "empty")],
                4,
                "indeterminate",
            ),
            (
                [
                    "relation-contract-validate",
                    str(self.root / "missing.json"),
                    "--kind",
                    "contract",
                ],
                1,
                "error",
            ),
        )
        for argv, expected_code, expected_status in cases:
            with self.subTest(argv=argv):
                code, value, _ = run_cli(argv)
                self.assertEqual(code, expected_code)
                self.assertEqual(value["status"], expected_status)

    def test_append_project_explain_and_verify_are_typed_and_canonical(self):
        store_root = self.root / "active"
        store, contract = build_active_store(store_root)
        commands = (
            (
                ["relation-contract-verify", "--root", str(store_root)],
                "internally_consistent",
            ),
            (
                ["relation-contract-project", "--root", str(store_root)],
                "projected",
            ),
            (
                [
                    "relation-contract-explain",
                    "--root",
                    str(store_root),
                    contract["contract_id"],
                ],
                "explained",
            ),
        )
        for argv, expected_status in commands:
            with self.subTest(argv=argv):
                code, value, raw = run_cli(argv)
                self.assertEqual(code, 0)
                self.assertEqual(value["status"], expected_status)
                self.assertEqual(raw, canonical_bytes(value) + b"\n")

        relation = valid_relation_version(
            relation_id="relation:fixture:cli-append",
            relation_class="descriptive",
            acceptance_rule="none",
        )
        event = valid_relation_contract_event(
            "relation.recorded", relation, event_id="event:relation:cli-append"
        )
        object_file = self.root / "relation.json"
        event_file = self.root / "event.json"
        write_json(object_file, relation)
        write_json(event_file, event)
        code, value, _ = run_cli(
            [
                "relation-contract-append",
                "--root",
                str(self.root / "append"),
                "--object",
                str(object_file),
                "--event",
                str(event_file),
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(value["status"], "created")

    def test_strict_json_failures_are_typed_without_traceback(self):
        duplicate = self.root / "duplicate.json"
        duplicate.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
        code, value, raw = run_cli(
            ["relation-contract-validate", str(duplicate), "--kind", "contract"]
        )
        self.assertEqual(code, 2)
        self.assertEqual(value["status"], "rejected")
        self.assertEqual(value["reason_codes"], ["duplicate_key"])
        self.assertNotIn(b"Traceback", raw)

    def test_contract_validation_requires_exact_policy_and_full_semantics(self):
        code, value, _ = run_cli(
            ["relation-contract-validate", str(self.good), "--kind", "contract"]
        )
        self.assertEqual(code, 4)
        self.assertEqual(value["status"], "indeterminate")
        self.assertEqual(value["reason_codes"], ["contract_policy_unavailable"])

        stale = valid_contract_version()
        stale["scope"] = ["resource:fixture:stale#read"]
        other_policy = mutate_and_rebind(
            valid_activation_policy(), {"policy_version": "2"}
        )
        mismatched_policy = mutate_and_rebind(
            valid_contract_version(),
            {"activation_policy_digest": other_policy["content_digest"]},
        )
        risk = mutate_and_rebind(
            valid_contract_version(), {"risk_ceiling": "R0"}
        )
        clock = deepcopy(valid_contract_version())
        clock["effective_not_before"]["clock_profile_id"] = "clock:other:v1"
        clock = mutate_and_rebind(clock, {})
        uncertainty = deepcopy(valid_contract_version())
        uncertainty["effective_not_before"]["uncertainty_ns"] = 1_000_000_001
        uncertainty = mutate_and_rebind(uncertainty, {})
        duration = mutate_and_rebind(
            valid_contract_version(),
            {"expires_at": normalized_instant("100000000000000", 0)},
        )
        cases = (
            ("stale", stale, "content_digest_mismatch"),
            ("policy-mismatch", mismatched_policy, "activation_policy_digest_mismatch"),
            ("risk", risk, "contract_v1_boundary_invalid"),
            ("clock", clock, "contract_time_invalid"),
            ("uncertainty", uncertainty, "contract_time_invalid"),
            ("duration", duration, "contract_time_invalid"),
        )
        for label, contract, expected_reason in cases:
            with self.subTest(label=label):
                path = self.root / f"{label}.json"
                write_json(path, contract)
                code, value, _ = run_cli(
                    [
                        "relation-contract-validate",
                        str(path),
                        "--kind",
                        "contract",
                        "--policy",
                        str(self.policy),
                    ]
                )
                self.assertEqual(code, 2)
                self.assertEqual(value["status"], "rejected")
                self.assertEqual(value["reason_codes"], [expected_reason])

    def test_project_wrong_event_object_kind_is_typed_rejection(self):
        root = self.root / "wrong-kind"
        store = RelationContractStore(root)
        relation = valid_relation_version(
            relation_class="descriptive", acceptance_rule="none"
        )
        store.put_object("relation", relation)
        event = RelationContractEvent.from_dict(
            valid_relation_contract_event(
                "contract.drafted", relation, event_id="event:cli:wrong-kind"
            )
        )
        event_path = store._event_path(event.event_id)
        event_path.write_bytes(canonical_bytes(store._event_bundle(event)))
        index_path = store._event_index_path(event.event_digest)
        index_path.write_bytes(canonical_bytes(store._event_index(event, event_path)))

        code, value, raw = run_cli(
            ["relation-contract-project", "--root", str(root)]
        )
        self.assertEqual(code, 2)
        self.assertEqual(value["status"], "rejected")
        self.assertEqual(value["reason_codes"], ["event_object_kind_mismatch"])
        self.assertNotIn(b"Traceback", raw)

    def test_append_rejects_unrelated_object_event_pair_before_mutation(self):
        root = self.root / "pair-mismatch"
        store = RelationContractStore(root)
        contract = valid_contract_version()
        store.put_object("contract", contract)
        relation = valid_relation_version(
            relation_id="relation:fixture:unrelated",
            relation_class="descriptive",
            acceptance_rule="none",
        )
        event = valid_relation_contract_event(
            "contract.drafted",
            contract,
            event_id="event:cli:pair-mismatch",
        )
        object_file = self.root / "unrelated-relation.json"
        event_file = self.root / "contract-event.json"
        write_json(object_file, relation)
        write_json(event_file, event)
        before = (len(store.objects_by_digest()), len(store.events()))

        code, value, _ = run_cli(
            [
                "relation-contract-append",
                "--root",
                str(root),
                "--object",
                str(object_file),
                "--event",
                str(event_file),
            ]
        )

        self.assertEqual(code, 2)
        self.assertEqual(value["reason_codes"], ["event_object_pair_mismatch"])
        reopened = RelationContractStore(root)
        self.assertEqual(
            (len(reopened.objects_by_digest()), len(reopened.events())), before
        )

    def test_relations_package_has_no_send_surface_and_injection_turns_red(self):
        package = Path(__file__).resolve().parents[1] / "src" / "eml_pmw" / "relations"
        self.assertEqual(scan_offline_boundary(package), [])
        cases = {
            "socket.py": ("import socket\nsocket.create_connection(('example.test', 443))\n", "forbidden_import:socket"),
            "httpx.py": ("import httpx\nhttpx.post('https://example.test')\n", "forbidden_import:httpx"),
            "urllib3.py": ("import urllib3\nurllib3.request('GET', 'https://example.test')\n", "forbidden_import:urllib3"),
            "aiohttp.py": ("import aiohttp\naiohttp.ClientSession()\n", "forbidden_import:aiohttp"),
            "boto3.py": ("import boto3\nboto3.client('s3')\n", "forbidden_import:boto3"),
            "google_cloud.py": ("from google.cloud import storage\n", "forbidden_import:google.cloud"),
            "azure.py": ("from azure.identity import DefaultAzureCredential\n", "forbidden_import:azure"),
            "provider.py": ("from eml_wake.claude import ClaudeCLIAdapter\n", "forbidden_import:eml_wake.claude"),
            "bridge.py": ("import eml_bridge\n", "forbidden_import:eml_bridge"),
            "dynamic.py": ("import importlib\nimportlib.import_module('httpx')\n", "forbidden_dynamic_import:httpx"),
            "dunder.py": ("__import__('socket')\n", "forbidden_dynamic_import:socket"),
            "process.py": ("import os\nos.system('provider')\n", "forbidden_call:os.system"),
            "process_alias.py": ("from os import system as run\nrun('provider')\n", "forbidden_call:os.system"),
        }
        with tempfile.TemporaryDirectory() as temporary:
            injected = Path(temporary)
            for name, (source, expected) in cases.items():
                path = injected / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    self.assertIn(
                        expected,
                        [item.code for item in scan_offline_boundary(injected)],
                    )
                path.unlink()


if __name__ == "__main__":
    unittest.main()
