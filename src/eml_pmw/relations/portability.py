from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Protocol

from .canonical import profile_digest
from .errors import RelationContractError
from .models_common import PartyEvidencePin


FORBIDDEN_IMPORTS = (
    "aiohttp", "anthropic", "azure", "boto3", "botocore", "cloudflare",
    "eml_bridge", "eml_pmw.adapters", "eml_wake.claude", "eml_wake.provider",
    "eml_wake.watchdog", "google.cloud", "herdr", "http.client", "httpx",
    "openai", "requests", "sedb_ral", "socket", "subprocess", "urllib.request",
    "urllib3", "win32api", "win32file", "win32security", "winreg",
)
FORBIDDEN_CALLS = {
    "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell",
    "ctypes.windll", "os.popen", "os.startfile", "os.system",
}
FORBIDDEN_CALL_PREFIXES = ("os.exec", "os.spawn")
WINDOWS_PATH = re.compile(r"(?i)^[a-z]:[\\/]|^\\\\")
POSIX_PATH = re.compile(r"^/(?:home|var|etc|Users|private)(?:/|\s|$)")
PYTHON_CLASS_PATH = re.compile(
    r"^(?:[A-Za-z_]\w*\.)+[A-Za-z_]\w*:[A-Za-z_]\w*$"
)
RESOURCE_PATTERNS = (
    ("absolute_windows_path", re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\)")),
    ("absolute_posix_path", re.compile(r"/(?:home|var|etc|Users|private)(?:/|\s|$)")),
    ("file_uri", re.compile(r"(?i)file://")),
    ("python_class_path", re.compile(r"(?:[A-Za-z_]\w*\.)+[A-Za-z_]\w*:[A-Za-z_]\w*")),
    ("private_residence", re.compile(r"(?i)(?:AI_RESIDENCE|private[ _-]*Residence)")),
    ("p2_p3", re.compile(r"(?i)fabric_payload_class\s*[:=]\s*[\"']?P[23]\b")),
)
EFFECT_COUNTS = {
    "network_calls": 0,
    "private_reads": 0,
    "production_registry_writes": 0,
    "provider_calls": 0,
    "real_contracts": 0,
}


@dataclass(frozen=True)
class PortabilityFinding:
    code: str
    path: str
    line: int


@dataclass(frozen=True)
class PortabilityReport:
    findings: tuple[PortabilityFinding, ...]


@dataclass(frozen=True)
class ConformanceResult:
    realm_kind: str
    semantic_digest: str
    effect_counts: dict[str, int]


class PartyResolver(Protocol):
    def resolve(self, party_ref: str) -> PartyEvidencePin: ...


def _forbidden_import(module: str) -> str | None:
    for prefix in FORBIDDEN_IMPORTS:
        if module == prefix or module.startswith(prefix + "."):
            return prefix
    return None


def _qualified_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value, aliases)
        return None if prefix is None else f"{prefix}.{node.attr}"
    return None


def _python_findings(path: Path, root: Path) -> list[PortabilityFinding]:
    relative = path.relative_to(root).as_posix()
    try:
        source = path.read_text(encoding="utf-8", errors="strict")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return [PortabilityFinding("source_unreadable_or_invalid", relative, 0)]
    aliases: dict[str, str] = {}
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
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
    findings: list[PortabilityFinding] = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
        for module in modules:
            forbidden = _forbidden_import(module)
            if forbidden is not None:
                findings.append(PortabilityFinding(
                    f"forbidden_import:{forbidden}", relative,
                    getattr(node, "lineno", 0),
                ))
        if isinstance(node, ast.Call):
            call = _qualified_name(node.func, aliases)
            if call in FORBIDDEN_CALLS or (
                call is not None
                and any(call.startswith(prefix) for prefix in FORBIDDEN_CALL_PREFIXES)
            ):
                findings.append(PortabilityFinding(
                    f"forbidden_call:{call}", relative,
                    getattr(node, "lineno", 0),
                ))
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            ancestor = parents.get(node)
            validation_literal = False
            while ancestor is not None and not isinstance(ancestor, ast.stmt):
                if isinstance(ancestor, ast.Call):
                    call = _qualified_name(ancestor.func, aliases)
                    if call in {
                        "re.compile",
                        "re.fullmatch",
                        "re.match",
                        "re.search",
                    } or (
                        isinstance(ancestor.func, ast.Attribute)
                        and ancestor.func.attr in {"endswith", "startswith"}
                    ):
                        validation_literal = True
                        break
                ancestor = parents.get(ancestor)
            if validation_literal:
                continue
            value = node.value
            code = None
            if WINDOWS_PATH.search(value):
                code = "absolute_windows_path"
            elif POSIX_PATH.search(value):
                code = "absolute_posix_path"
            elif value.lower().startswith("file://"):
                code = "file_uri"
            elif PYTHON_CLASS_PATH.fullmatch(value):
                code = "python_class_path"
            if code is not None:
                findings.append(PortabilityFinding(
                    f"forbidden_source_literal:{code}", relative,
                    getattr(node, "lineno", 0),
                ))
    return findings


def _resource_findings(path: Path, root: Path) -> list[PortabilityFinding]:
    relative = path.relative_to(root).as_posix()
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError):
        return [PortabilityFinding("resource_unreadable", relative, 0)]
    findings = []
    for code, pattern in RESOURCE_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(PortabilityFinding(
                f"forbidden_resource_literal:{code}", relative,
                text.count("\n", 0, match.start()) + 1,
            ))
    return findings


def scan_portable_profile(root: str | Path) -> PortabilityReport:
    base = Path(root)
    findings: list[PortabilityFinding] = []
    for path in sorted(base.rglob("*")):
        if path.suffix == ".py":
            findings.extend(_python_findings(path, base))
        elif path.suffix.lower() in {".json", ".md"}:
            findings.extend(_resource_findings(path, base))
    return PortabilityReport(tuple(sorted(
        findings, key=lambda item: (item.path, item.line, item.code)
    )))


def run_portable_conformance(
    realm: object, party_resolver: PartyResolver
) -> ConformanceResult:
    realm_kind = getattr(realm, "realm_kind", None)
    if realm_kind not in {
        "windows_host", "cloud_host", "hdus_host", "embodied_host", "fixture",
    }:
        raise RelationContractError("realm_kind_invalid", str(realm_kind))
    pins = tuple(
        party_resolver.resolve(party)
        for party in ("resident:fixture:a", "resident:fixture:b")
    )
    if any(
        not isinstance(pin, PartyEvidencePin)
        or pin.adapter_verification_status != "verified"
        or pin.party_status != "active"
        or pin.binding_status != "active"
        or pin.binding_ambiguity
        for pin in pins
    ):
        raise RelationContractError(
            "portable_party_evidence_insufficient", str(realm_kind)
        )
    semantic_digest = profile_digest({
        "schema": "arcp/portable-conformance-result/0.1",
        "party_pin_digests": sorted(pin.content_digest for pin in pins),
        "relation_class": "consensual",
        "contract_risk": "R1",
        "execution_status": "not_observed",
        "not_claimed": ["host_identity", "provider_execution", "real_contract"],
    })
    return ConformanceResult(str(realm_kind), semantic_digest, dict(EFFECT_COUNTS))
