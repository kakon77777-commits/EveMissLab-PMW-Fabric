from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.integration.capabilities import load_integration_profile, negotiate_mrmic


VALID = {
    "schema": "mrmic-capabilities/v1",
    "mrmicVersion": "0.14.0",
    "canvasSchemaVersion": "mrmic-canvas/0.14",
    "mcpProtocolProfile": {
        "protocolVersion": "2025-11-25",
        "profile": "stateful-streamable-http-subset",
    },
    "projectionModes": ["compat_frame_v0", "native_resource_portal_v1"],
    "authModes": ["legacy_local", "bearer_principal_v1"],
    "resourcePortal": {
        "supported": True,
        "schemaVersion": "native_resource_portal_v1",
    },
    "runtimePresence": {
        "supported": True,
        "schemaVersion": "ephemeral_runtime_presence_v1",
        "durable": False,
    },
    "livePortalHost": {"supported": True, "stateVersion": "live_portal_host_v1"},
}


class CapabilityNegotiationTests(unittest.TestCase):
    def test_packaged_profile_validates_its_exact_pins(self):
        profile = load_integration_profile()
        self.assertEqual(
            profile["arcp"]["sourceCommit"],
            "c47300c961b20eac0878ac8c94df95d0df34e688",
        )
        self.assertEqual(profile["arcp"]["hashBasis"], "git_blob_bytes")
        self.assertEqual(
            profile["arcp"]["idsSha256"],
            "60a4a7991f90254e178010c937ffbf390c1db2e9da8b15c0c3ae104f0a4d0717",
        )
        self.assertEqual(
            profile["mrmic"]["sourceCommit"],
            "791efb9d98270d4db9c25f257aac805196ba62e8",
        )

    def test_exact_phase13_surface_is_compatible(self):
        self.assertEqual(negotiate_mrmic(VALID).status, "compatible")

    def test_durable_presence_claim_is_incompatible(self):
        value = deepcopy(VALID)
        value["runtimePresence"]["durable"] = True
        result = negotiate_mrmic(value)
        self.assertEqual(result.status, "incompatible")
        self.assertIn("runtime_presence_must_be_ephemeral", result.reason_codes)

    def test_every_required_term_is_a_sole_deciding_factor(self):
        cases = (
            (lambda v: v.__setitem__("mrmicVersion", "0.13.0"), "mrmic_version_mismatch"),
            (lambda v: v.__setitem__("canvasSchemaVersion", "mrmic-canvas/0.13"), "canvas_schema_mismatch"),
            (lambda v: v["mcpProtocolProfile"].__setitem__("protocolVersion", "unknown"), "mcp_protocol_version_mismatch"),
            (lambda v: v["mcpProtocolProfile"].__setitem__("profile", "unknown"), "mcp_profile_mismatch"),
            (lambda v: v.__setitem__("projectionModes", ["compat_frame_v0"]), "required_projection_mode_missing"),
            (lambda v: v.__setitem__("authModes", ["legacy_local"]), "required_auth_mode_missing"),
            (lambda v: v["resourcePortal"].__setitem__("supported", False), "native_portal_not_supported"),
            (lambda v: v["resourcePortal"].__setitem__("schemaVersion", "wrong"), "portal_schema_mismatch"),
            (lambda v: v["runtimePresence"].__setitem__("supported", False), "runtime_presence_not_supported"),
            (lambda v: v["runtimePresence"].__setitem__("schemaVersion", "wrong"), "runtime_presence_schema_mismatch"),
            (lambda v: v["livePortalHost"].__setitem__("supported", False), "live_host_not_supported"),
            (lambda v: v["livePortalHost"].__setitem__("stateVersion", "wrong"), "live_host_state_mismatch"),
        )
        for mutate, reason in cases:
            with self.subTest(reason=reason):
                value = deepcopy(VALID)
                mutate(value)
                result = negotiate_mrmic(value)
                self.assertEqual(result.status, "incompatible")
                self.assertIn(reason, result.reason_codes)

    def test_non_object_input_is_unmeasured_not_compatible(self):
        result = negotiate_mrmic(None)
        self.assertEqual(result.status, "unmeasured")
        self.assertEqual(result.reason_codes, ("capability_document_unmeasured",))

    def test_credential_key_is_identified_before_schema_rejection(self):
        value = deepcopy(VALID)
        value["resourcePortal"]["authToken"] = "fixture-not-a-real-token"
        result = negotiate_mrmic(value)
        self.assertEqual(result.status, "incompatible")
        self.assertEqual(
            result.reason_codes, ("capability_document_contains_credential",)
        )


if __name__ == "__main__":
    unittest.main()
