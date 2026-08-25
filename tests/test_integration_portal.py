from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.integration.contracts import load_contract
from eml_pmw.integration.portal import build_native_portal
from eml_pmw.models import ResourceBinding


def binding():
    return ResourceBinding(
        "rbind-1",
        "pmw-workspace-1",
        "tandem",
        "browser_tab",
        "tab-1",
        "snapshot",
        "inspect",
        None,
        "pmw-task-1",
        None,
        "unprojected",
        "bound",
        {},
        0,
        "2026-08-24T00:00:00Z",
        "2026-08-24T00:00:00Z",
    )


class NativePortalTests(unittest.TestCase):
    def test_native_portal_validates_against_upstream_schema(self):
        portal = build_native_portal(
            binding(),
            canvas_id="root",
            object_id="portal-browser-1",
            geometry={"x": 100, "y": 120, "width": 640, "height": 420, "zIndex": 10},
            now="2026-08-24T00:00:00.000Z",
        )
        jsonschema.validate(
            portal, load_contract("native-resource-portal-v1.schema.json")
        )
        self.assertEqual(
            portal["metadata"]["portal"]["providerResourceId"], "tab-1"
        )

    def test_portal_payload_contains_no_identity_or_token_fields(self):
        portal = build_native_portal(
            binding(),
            canvas_id="root",
            object_id="p1",
            geometry={"x": 0, "y": 0, "width": 1, "height": 1, "zIndex": 0},
            now="2026-08-24T00:00:00.000Z",
        )
        encoded = json.dumps(portal, sort_keys=True).lower()
        self.assertNotIn("authtoken", encoded)
        self.assertNotIn("bearer", encoded)
        self.assertNotIn("ownersemanticagentid", encoded)


if __name__ == "__main__":
    unittest.main()
