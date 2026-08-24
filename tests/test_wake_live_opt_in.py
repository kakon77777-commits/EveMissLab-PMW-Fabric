from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid


@unittest.skipUnless(os.environ.get("EML_WAKE_LIVE") == "1", "set EML_WAKE_LIVE=1 for real Claude/CTCL probe")
class LiveWakeTests(unittest.TestCase):
    def test_fresh_haiku_worker_commits_retrievable_ack(self):
        from eml_wake.claude import ClaudeCLIAdapter
        from eml_wake.models import WakeConfig, WakeRequest
        from eml_wake.provider import NullNotifier
        from eml_wake.store import WakeStore
        from eml_wake.temporal import CtclHttpTemporalProvider
        from eml_wake.watchdog import WakeWatchdog

        live_parent = os.environ.get("EML_WAKE_LIVE_ROOT")
        claude_binary = os.environ.get("EML_WAKE_CLAUDE_BIN", "claude")
        if not live_parent:
            self.fail("EML_WAKE_LIVE_ROOT is required")
        expected_result = "80235"
        with tempfile.TemporaryDirectory(dir=live_parent) as tmp:
            base = Path(tmp)
            payload_root = base / "payloads"
            payload_root.mkdir()
            payload = payload_root / "message.md"
            payload.write_text("Calculate 12345 + 67890. Reply with the decimal sum only.\n", encoding="utf-8")
            config = WakeConfig.from_dict(
                {
                    "schema_version": "eml-wake/config-0.1",
                    "allowed_payload_roots": [str(payload_root)],
                    "allowed_context_roots": [],
                    "allowed_target_kinds": ["generic_worker"],
                    "allowed_models": ["claude-haiku-4-5-20251001"],
                    "allowed_tools_by_policy": {"no_tools": []},
                    "permission_modes": ["dontAsk"],
                    "maximum_budget_microusd": 100000,
                    "maximum_timeout_ms": 180000,
                    "claude_binary": claude_binary,
                    "poll_interval_ms": 500,
                    "ctcl_endpoint": "https://commoninstant.org/v1/instants",
                    "strict_reparse_checks": True,
                }
            )
            created = CtclHttpTemporalProvider().register(
                "EML live wake request",
                {"task_kind": "arithmetic_control", "expected_result": expected_result},
            )
            self.assertEqual(created.status, "registered_anchor")
            now = datetime.now(timezone.utc)
            request_raw = {
                    "schema_version": "eml-wake/request-0.1",
                    "wake_id": f"wake:live:{uuid.uuid4()}",
                    "delivery_id": f"delivery:live:{uuid.uuid4()}",
                    "created_time_ref": created.instant_id,
                    "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
                    "sender_claim": "agent://evemisslab/line/zhiyu",
                    "target_kind": "generic_worker",
                    "target_ref": "worker:claude:live-probe",
                    "spawn_allowed": True,
                    "authority_ref": "principal:neo.k/cross-dialogue-completion",
                    "payload_ref": str(payload),
                    "payload_sha256": hashlib.sha256(payload.read_bytes()).hexdigest().upper(),
                    "context_package_ref": None,
                    "reply_policy": "durable_ack_only",
                    "provider": "claude",
                    "model": "claude-haiku-4-5-20251001",
                    "allowed_tools": [],
                    "permission_mode": "dontAsk",
                    "max_budget_microusd": 100000,
                    "timeout_ms": 180000,
                    "requested_output_format": "json",
                    "not_claimed": ["resident continuity", "exact interactive instance"],
                }
            request = WakeRequest.from_dict(request_raw)
            store = WakeStore(base / "wake", config)
            store.submit(request)
            adapter = ClaudeCLIAdapter(binary=claude_binary)
            watchdog = WakeWatchdog(
                store,
                adapter,
                NullNotifier(),
                "watchdog:live-test",
                temporal=CtclHttpTemporalProvider(),
            )
            result = watchdog.process(request.wake_id)
            self.assertEqual(result.status, "acknowledged")
            ack = store.status(request.wake_id)["record"]
            self.assertEqual(ack["result_text"].strip(), expected_result)
            self.assertRegex(ack["provider_session_id"], r"^[0-9a-f-]{36}$")
            self.assertEqual(ack["model"], request.model)
            self.assertGreater(ack["cost_microusd"], 0)
            self.assertGreater(ack["duration_ms"], 0)
            self.assertEqual(ack["payload_sha256"], request.payload_sha256)
            self.assertEqual(ack["temporal_evidence_status"], "registered_anchor")
            self.assertTrue(ack["temporal_instant_id"].startswith("ctcl:instant:"))

            first_ack = dict(ack)
            for suffix in ("duplicate-2", "duplicate-3"):
                duplicate_raw = dict(request_raw)
                duplicate_raw["delivery_id"] = f"delivery:live:{suffix}:{uuid.uuid4()}"
                self.assertEqual(store.submit(WakeRequest.from_dict(duplicate_raw)).kind, "duplicate")
            self.assertEqual(watchdog.run_once(), [])
            self.assertEqual(store.status(request.wake_id)["record"], first_ack)
            self.assertEqual(len(list(store.duplicates_dir.rglob("*.json"))), 2)

            exact_raw = dict(request_raw)
            exact_raw.update(
                {
                    "wake_id": f"wake:live:exact:{uuid.uuid4()}",
                    "delivery_id": f"delivery:live:exact:{uuid.uuid4()}",
                    "target_kind": "exact_instance",
                    "target_ref": "session:does-not-exist",
                    "spawn_allowed": False,
                }
            )
            exact = WakeRequest.from_dict(exact_raw)
            store.submit(exact)
            exact_result = watchdog.process(exact.wake_id)
            self.assertEqual(exact_result.status, "exact_instance_spawn_refused")

            evidence = {
                "schema_version": "eml-wake/live-evidence-0.1",
                "wake_id": request.wake_id,
                "expected_result": expected_result,
                "ack": first_ack,
                "duplicate_delivery_count": 2,
                "duplicate_provider_replay_observed": False,
                "exact_instance_result": exact_result.status,
                "exact_instance_provider_spawned": False,
            }
            evidence_path = Path(live_parent) / f"wake-live-evidence-{request.wake_id.rsplit(':', 1)[-1]}.json"
            evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
            print(f"LIVE_EVIDENCE={evidence_path}")


if __name__ == "__main__":
    unittest.main()
