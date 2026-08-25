from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.federation.visibility import (
    AdapterVisibilityEvidence,
    automatic_replay_allowed,
)
from eml_pmw.integration.contracts import load_local_contract
from tests.federation_helpers import (
    VISIBILITY_BARRIERS,
    assert_error_code,
    valid_visibility_evidence,
)


class AdapterVisibilityEvidenceTests(unittest.TestCase):
    def test_completed_empty_projection_preserves_observed_local_body(self):
        evidence = AdapterVisibilityEvidence.from_dict(valid_visibility_evidence())

        self.assertEqual(evidence.execution_state, "completed")
        self.assertEqual(evidence.adapter_read_outcome, "empty_projection")
        self.assertEqual(evidence.adapter_item_count, 0)
        self.assertEqual(evidence.local_capture_state, "body_observed")
        self.assertEqual(evidence.local_capture_portability, "local_only")
        self.assertEqual(evidence.materialization_state, "verified")
        self.assertEqual(evidence.portable_delivery_state, "not_proven")
        self.assertEqual(evidence.authorship_state, "unmeasured")

    def test_local_only_capture_cannot_promote_portable_delivery(self):
        with assert_error_code(self, "delivery_inference_forbidden"):
            AdapterVisibilityEvidence.from_dict(
                valid_visibility_evidence(
                    portable_delivery_state="acknowledged_structured"
                )
            )

    def test_local_only_capture_cannot_promote_authorship(self):
        with assert_error_code(self, "authorship_inference_forbidden"):
            AdapterVisibilityEvidence.from_dict(
                valid_visibility_evidence(authorship_state="receiver_observed")
            )

    def test_empty_projection_never_authorizes_automatic_replay(self):
        evidence = AdapterVisibilityEvidence.from_dict(valid_visibility_evidence())
        self.assertIs(automatic_replay_allowed(evidence), False)

    def test_all_inference_barriers_are_mandatory(self):
        for removed in VISIBILITY_BARRIERS:
            with self.subTest(removed=removed):
                remaining = [item for item in VISIBILITY_BARRIERS if item != removed]
                with assert_error_code(self, "inference_barrier_missing"):
                    AdapterVisibilityEvidence.from_dict(
                        valid_visibility_evidence(inference_barriers=remaining)
                    )

    def test_evidence_digest_binds_every_other_field(self):
        value = valid_visibility_evidence()
        value["adapter_call_count"] = 3
        with assert_error_code(self, "evidence_digest_mismatch"):
            AdapterVisibilityEvidence.from_dict(value)

    def test_verified_materialization_requires_complete_artifact_evidence(self):
        for field, replacement in (
            ("materialized_artifact_ref", None),
            ("materialized_artifact_sha256", None),
            ("materialized_artifact_bytes", None),
        ):
            with self.subTest(field=field):
                with assert_error_code(self, "materialization_evidence_incomplete"):
                    AdapterVisibilityEvidence.from_dict(
                        valid_visibility_evidence(**{field: replacement})
                    )

    def test_packaged_schema_meta_validates_and_matches_fixture(self):
        schema = load_local_contract("adapter-visibility-evidence-v1.schema.json")
        jsonschema.Draft202012Validator.check_schema(schema)
        fixture = json.loads(
            (ROOT / "examples" / "federation" / "incidents" / "codex-read-thread-empty-items.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.validate(fixture, schema)
        self.assertEqual(fixture, valid_visibility_evidence())


if __name__ == "__main__":
    unittest.main()
