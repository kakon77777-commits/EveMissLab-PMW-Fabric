from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import json
from pathlib import Path


FORBIDDEN_IMPORTS = (
    "eml_bridge",
    "eml_pmw.adapters",
    "eml_wake.provider",
    "http.client",
    "requests",
    "socket",
    "subprocess",
    "urllib.request",
)


@dataclass(frozen=True)
class BoundaryFinding:
    code: str
    path: str
    line: int


def _forbidden(module: str) -> str | None:
    for prefix in FORBIDDEN_IMPORTS:
        if module == prefix or module.startswith(prefix + "."):
            return prefix
    return None


def scan_offline_boundary(root: str | Path) -> list[BoundaryFinding]:
    base = Path(root)
    findings: list[BoundaryFinding] = []
    for path in sorted(base.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8", errors="strict")
            tree = ast.parse(source, filename=str(path))
        except (OSError, UnicodeError, SyntaxError):
            findings.append(
                BoundaryFinding(
                    "source_unreadable_or_invalid",
                    path.relative_to(base).as_posix(),
                    0,
                )
            )
            continue
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.append(node.module or "")
            for module in modules:
                forbidden = _forbidden(module)
                if forbidden is not None:
                    findings.append(
                        BoundaryFinding(
                            f"forbidden_import:{forbidden}",
                            path.relative_to(base).as_posix(),
                            getattr(node, "lineno", 0),
                        )
                    )
    return sorted(findings, key=lambda item: (item.path, item.line, item.code))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Reject network, process, and provider effects in federation core"
    )
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args(argv)
    findings = scan_offline_boundary(args.root)
    print(
        json.dumps(
            {
                "findings": [asdict(item) for item in findings],
                "passed": not findings,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
