from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from eml_wake.canonical import canonical_bytes, loads_strict
from eml_wake.errors import WakeError
from eml_pmw.federation.errors import FederationError
from eml_pmw.federation.ral_adapter import RalAdapterManifest, verify_ral_schema_pin


def _parser():
    parser = argparse.ArgumentParser(description="Verify the PMW-to-RAL schema pin")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-schema", required=True, type=Path)
    return parser


def _emit(value):
    print(canonical_bytes(value).decode("utf-8"))


def _load_manifest(path):
    try:
        data = path.read_bytes()
    except OSError as error:
        raise FederationError("manifest_unavailable", str(path)) from error
    try:
        value = loads_strict(data)
    except WakeError as error:
        raise FederationError("manifest_invalid", str(path)) from error
    if not isinstance(value, dict):
        raise FederationError("manifest_invalid", str(path))
    return RalAdapterManifest.from_dict(value)


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        manifest = _load_manifest(args.manifest)
    except FederationError as error:
        _emit({"reason_codes": [error.code], "status": "manifest_invalid"})
        return 1
    try:
        source = args.source_schema.read_bytes()
    except OSError:
        _emit({"reason_codes": ["ral_source_unavailable"], "status": "ral_source_unavailable"})
        return 4
    try:
        verify_ral_schema_pin(manifest, source)
    except FederationError as error:
        _emit({"reason_codes": [error.code], "status": "ral_source_mismatch"})
        return 2
    _emit(
        {
            "source_commit": manifest.source_commit,
            "source_schema_id": manifest.source_schema_id,
            "source_schema_sha256": manifest.source_schema_sha256,
            "status": "verified",
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
