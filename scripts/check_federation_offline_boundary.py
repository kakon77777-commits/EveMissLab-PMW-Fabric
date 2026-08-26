from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import json
from pathlib import Path


FORBIDDEN_IMPORTS = (
    "aiohttp",
    "anthropic",
    "azure",
    "boto3",
    "botocore",
    "cloudflare",
    "eml_bridge",
    "eml_pmw.adapters",
    "eml_wake.claude",
    "eml_wake.provider",
    "eml_wake.watchdog",
    "google.cloud",
    "herdr",
    "http.client",
    "httpx",
    "openai",
    "requests",
    "socket",
    "subprocess",
    "urllib.request",
    "urllib3",
)
FORBIDDEN_CALLS = {
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "os.popen",
    "os.startfile",
    "os.system",
}
FORBIDDEN_CALL_PREFIXES = ("os.exec", "os.spawn")


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


def _qualified_call_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        prefix = _qualified_call_name(node.value, aliases)
        return None if prefix is None else f"{prefix}.{node.attr}"
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
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    aliases[alias.asname or alias.name.split(".", 1)[0]] = alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    aliases[alias.asname or alias.name] = (
                        f"{module}.{alias.name}" if module else alias.name
                    )
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
            if not isinstance(node, ast.Call):
                continue
            call_name = _qualified_call_name(node.func, aliases)
            if call_name in {
                "__import__",
                "builtins.__import__",
                "importlib.import_module",
            }:
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
                    node.args[0].value, str
                ):
                    forbidden = _forbidden(node.args[0].value)
                    if forbidden is not None:
                        findings.append(
                            BoundaryFinding(
                                f"forbidden_dynamic_import:{forbidden}",
                                path.relative_to(base).as_posix(),
                                getattr(node, "lineno", 0),
                            )
                        )
            if call_name in FORBIDDEN_CALLS or (
                call_name is not None
                and any(call_name.startswith(prefix) for prefix in FORBIDDEN_CALL_PREFIXES)
            ):
                findings.append(
                    BoundaryFinding(
                        f"forbidden_call:{call_name}",
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
