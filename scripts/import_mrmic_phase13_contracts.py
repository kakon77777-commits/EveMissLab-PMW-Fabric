from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess


COMMIT = "791efb9d98270d4db9c25f257aac805196ba62e8"
EXPECTED = {
    "mrmic-capabilities-v1.schema.json": "a51a8611926bbf322d75308cc17a7c80a6348cbb4629a89da2375d0a2071f73e",
    "native-resource-portal-v1.schema.json": "a6204a402d3fd971f6188c92c385b792da30f457142ff13cc3c69bc389cc6832",
    "secure-canvas-messages-v1.schema.json": "998f3bc1cc10563e1cec416451e427fd860ad07cc956ad0c923537985d14f54c",
    "ephemeral-runtime-presence-v1.schema.json": "5ff2932eb07b69ffb2e4a071017dab33d055eb7f97c6b6bc0bd8d3e31cf2ae5e",
    "live-portal-host-v1.schema.json": "1c9ddf86ae83eae039963fe8ae19ff0b33795f3a886423a99db0f9cd3482b7a6",
}


def import_contracts(source_root: Path, destination: Path) -> None:
    head = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != COMMIT:
        raise SystemExit(f"source_commit_mismatch: expected {COMMIT}, got {head}")
    source_dir = source_root / "contracts" / "phase13"
    verified: list[tuple[Path, Path]] = []
    for name, expected in EXPECTED.items():
        source = source_dir / name
        if not source.is_file():
            raise SystemExit(f"source_contract_missing: {name}")
        actual = sha256(source.read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"source_contract_digest_mismatch: {name}")
        verified.append((source, destination / name))
    destination.mkdir(parents=True, exist_ok=True)
    for source, target in verified:
        shutil.copyfile(source, target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    import_contracts(args.source.resolve(), args.destination.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
