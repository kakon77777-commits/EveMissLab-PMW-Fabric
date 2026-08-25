from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.adapters.mrmic_phase13 import MRMICPhase13Adapter
from eml_pmw.core import PMWFabric
from eml_pmw.errors import ProviderUnavailableError
from eml_pmw.integration.errors import IntegrationContractError
from eml_pmw.journal import FabricJournal
from eml_pmw.models import ResourceBinding


VALID_CAPABILITIES = {
    "schema": "mrmic-capabilities/v1",
    "mrmicVersion": "0.14.0",
    "canvasSchemaVersion": "mrmic-canvas/0.14",
    "mcpProtocolProfile": {
        "protocolVersion": "2025-11-25",
        "profile": "stateful-streamable-http-subset",
    },
    "projectionModes": ["compat_frame_v0", "native_resource_portal_v1"],
    "authModes": ["legacy_local", "bearer_principal_v1"],
    "resourcePortal": {"supported": True, "schemaVersion": "native_resource_portal_v1"},
    "runtimePresence": {"supported": True, "schemaVersion": "ephemeral_runtime_presence_v1", "durable": False},
    "livePortalHost": {"supported": True, "stateVersion": "live_portal_host_v1"},
}


def binding():
    return ResourceBinding(
        "rbind-1", "pmw-workspace-1", "tandem", "browser_tab", "tab-1",
        "snapshot", "inspect", None, "pmw-task-1", None, "unprojected",
        "bound", {}, 0, "2026-08-24T00:00:00Z", "2026-08-24T00:00:00Z",
    )


class FakePhase13Adapter(MRMICPhase13Adapter):
    def __init__(self):
        super().__init__("https://invalid.local", bearer_token="fixture-token-value")
        self.calls = []
        self.capabilities = VALID_CAPABILITIES

    def _request_json(self, path, *, method="GET", body=None, authenticated=False):
        self.calls.append((path, method, body, authenticated))
        if path == "/api/capabilities":
            return self.capabilities
        if path == "/api/state":
            return {"canvas": {"id": "root", "revision": 7}}
        if path == "/api/transaction":
            return {"ok": True, "revision": 8}
        raise AssertionError(path)


class Phase13AdapterTests(unittest.TestCase):
    def test_bearer_adapter_requires_https_base_url(self):
        with self.assertRaises(IntegrationContractError) as caught:
            MRMICPhase13Adapter(
                "http://example.invalid", bearer_token="fixture-token-value"
            )
        self.assertEqual(caught.exception.code, "mrmic_https_required")

    def test_adapter_negotiates_before_authenticated_mutation(self):
        adapter = FakePhase13Adapter()
        result = adapter.project_portal(binding(), x=1, y=2, width=3, height=4)
        self.assertEqual(
            [call[0] for call in adapter.calls],
            ["/api/capabilities", "/api/state", "/api/transaction"],
        )
        self.assertTrue(adapter.calls[-1][3])
        self.assertNotIn("fixture-token-value", json.dumps(result))

    def test_incompatible_capabilities_stop_before_state_or_mutation(self):
        adapter = FakePhase13Adapter()
        adapter.capabilities = {**VALID_CAPABILITIES, "authModes": ["legacy_local"]}
        with self.assertRaises(IntegrationContractError) as caught:
            adapter.project_portal(binding(), x=1, y=2, width=3, height=4)
        self.assertEqual(caught.exception.code, "mrmic_profile_incompatible")
        self.assertEqual([call[0] for call in adapter.calls], ["/api/capabilities"])

    def test_adapter_satisfies_existing_fabric_projection_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = FabricJournal(Path(tmp) / "pmw.sqlite3")
            try:
                journal.upsert_agent("user:fixture", kind="human", display_name="Fixture")
                journal.create_workspace(
                    "W", "user:fixture", pmw_workspace_id="pmw-workspace-1"
                )
                resource = journal.bind_resource(
                    "pmw-workspace-1",
                    provider="tandem",
                    resource_kind="browser_tab",
                    provider_resource_id="tab-1",
                )
                projected = PMWFabric(journal).project_resource(
                    resource.binding_id,
                    FakePhase13Adapter(),
                    x=1,
                    y=2,
                    width=3,
                    height=4,
                    projection_mode="native_resource_portal_v1",
                )
                self.assertEqual(
                    projected.projection_mode, "native_resource_portal_v1"
                )
            finally:
                journal.close()

    @patch("eml_pmw.adapters.mrmic_phase13.urlopen")
    def test_bearer_appears_only_in_authorization_header(self, mocked_open):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"ok":true}'

        mocked_open.return_value = Response()
        adapter = MRMICPhase13Adapter(
            "https://example.invalid", bearer_token="fixture-token-value"
        )
        adapter._request_json(
            "/api/transaction", method="POST", body={"value": 1}, authenticated=True
        )
        request = mocked_open.call_args.args[0]
        self.assertEqual(
            request.get_header("Authorization"), "Bearer fixture-token-value"
        )
        self.assertNotIn(b"fixture-token-value", request.data)

    @patch("eml_pmw.adapters.mrmic_phase13.urlopen")
    def test_provider_cannot_echo_bearer_into_result(self, mocked_open):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"echo":"fixture-token-value"}'

        mocked_open.return_value = Response()
        adapter = MRMICPhase13Adapter(
            "https://example.invalid", bearer_token="fixture-token-value"
        )
        with self.assertRaises(ProviderUnavailableError) as caught:
            adapter._request_json(
                "/api/transaction", method="POST", body={"value": 1}, authenticated=True
            )
        self.assertNotIn("fixture-token-value", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
