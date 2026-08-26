from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import unittest

from eml_pmw.relations.models_common import PartyEvidencePin
from eml_pmw.relations.portability import (
    run_portable_conformance,
    scan_portable_profile,
)
from tests.relation_contract_helpers import valid_party_pin


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class FakeRealm:
    realm_kind: str


class FakePartyResolver:
    def resolve(self, party_ref: str) -> PartyEvidencePin:
        party = party_ref.rsplit(":", 1)[-1]
        return PartyEvidencePin.from_dict(valid_party_pin(party))


class SideEffectResolver(FakePartyResolver):
    def __init__(self, root: Path):
        self.root = root
        self.calls = 0

    def resolve(self, party_ref: str) -> PartyEvidencePin:
        self.calls += 1
        (self.root / f"resolver-effect-{self.calls}.txt").write_text(
            party_ref, encoding="utf-8"
        )
        return super().resolve(party_ref)


class RelationContractPortabilityTests(unittest.TestCase):
    def test_portable_profile_has_no_host_private_or_effect_dependencies(self):
        report = scan_portable_profile(ROOT / "src" / "eml_pmw" / "relations")
        self.assertEqual(report.findings, ())

    def test_fake_hdus_and_windows_use_the_same_semantic_contract(self):
        resolver = FakePartyResolver()
        windows = run_portable_conformance(FakeRealm("windows_host"), resolver)
        hdus = run_portable_conformance(FakeRealm("hdus_host"), resolver)
        self.assertEqual(windows.semantic_digest, hdus.semantic_digest)
        self.assertEqual(windows.effect_measurement_status, "unmeasured")
        self.assertIsNone(windows.effect_counts)
        self.assertEqual(windows.effect_counts, hdus.effect_counts)

    def test_side_effecting_resolver_is_never_reported_as_zero_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolver = SideEffectResolver(root)
            result = run_portable_conformance(
                FakeRealm("hdus_host"), resolver
            )
            self.assertEqual(resolver.calls, 2)
            self.assertEqual(len(list(root.glob("resolver-effect-*.txt"))), 2)
            self.assertEqual(result.effect_measurement_status, "unmeasured")
            self.assertIsNone(result.effect_counts)

    def test_injected_module_and_resource_each_turn_portability_red(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = root / "host.py"
            module.write_text("import winreg\n", encoding="utf-8")
            findings = scan_portable_profile(root).findings
            self.assertIn("forbidden_import:winreg", [item.code for item in findings])
            module.unlink()

            resource = root / "fixture.json"
            resource.write_text('{"path":"C:\\\\fixture\\\\private.json"}', encoding="utf-8")
            findings = scan_portable_profile(root).findings
            self.assertIn(
                "forbidden_resource_literal:absolute_windows_path",
                [item.code for item in findings],
            )

    def test_p2_private_and_absolute_posix_resource_markers_turn_red(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "fixture.md").write_text(
                "fabric_payload_class: P2\n/private Residence\n/var/lib/item\n",
                encoding="utf-8",
            )
            codes = [item.code for item in scan_portable_profile(root).findings]
            self.assertIn("forbidden_resource_literal:p2_p3", codes)
            self.assertIn("forbidden_resource_literal:private_residence", codes)
            self.assertIn("forbidden_resource_literal:absolute_posix_path", codes)


if __name__ == "__main__":
    unittest.main()
