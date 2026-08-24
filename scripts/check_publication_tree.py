from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Iterable, TextIO


_FORBIDDEN_TOP_LEVEL = {
    ".claude",
    ".venv",
    ".worktrees",
    "build",
    "dist",
    "recovery",
    "reference",
    "runtime",
    "upstream",
}
_FORBIDDEN_GENERATED_SUFFIXES = {
    ".db",
    ".pid",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".whl",
    ".zip",
}
_TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}
_LOCAL_PATH_PATTERNS = (
    re.compile(r"C:[\\/]Users[\\/]", re.IGNORECASE),
    re.compile(r"[A-Z]:[\\/]AI_RESIDENCE(?:[\\/]|\b)", re.IGNORECASE),
    re.compile(r"[A-Z]:[\\/]Ai[\\/]work together(?:[\\/]|\b)", re.IGNORECASE),
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"\b(?P<field>api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password)\b"
    r"\s*[:=]\s*[\"']?(?P<value>[^\s\"',}\]]{8,})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    line: int | None
    detail: str


def _normalize_path(raw: str) -> tuple[str, bool]:
    value = raw.strip().replace("\\", "/")
    if not value:
        return value, True
    unsafe = value.startswith("/") or re.match(r"^[A-Za-z]:/", value) is not None
    parts = PurePosixPath(value).parts
    if any(part in {"", ".", ".."} for part in parts):
        unsafe = True
    return value, unsafe


def _path_finding(path: str) -> Finding | None:
    parts = PurePosixPath(path).parts
    top = parts[0]
    if top in _FORBIDDEN_TOP_LEVEL:
        return Finding("forbidden_path", path, None, f"top_level={top}")
    if top == "evidence" and (len(parts) < 2 or parts[1] != "release"):
        return Finding("forbidden_path", path, None, "evidence_scope=release_only")
    if top == "docs" and len(parts) >= 2 and parts[1] == "superpowers":
        return Finding("forbidden_path", path, None, "docs_scope=public_only")
    if any(part == "__pycache__" or part.endswith(".egg-info") for part in parts):
        return Finding("generated_path", path, None, "generated_component")
    name = parts[-1].lower()
    if any(name.endswith(suffix) for suffix in _FORBIDDEN_GENERATED_SUFFIXES):
        return Finding("generated_path", path, None, "generated_suffix")
    if name.endswith(".pid.json"):
        return Finding("generated_path", path, None, "pid_record")
    return None


def _inspect_text(root: Path, relative: str) -> list[Finding]:
    path = root.joinpath(*PurePosixPath(relative).parts)
    if not path.is_file():
        return [Finding("missing_file", relative, None, "manifest_entry_missing")]
    if path.suffix.lower() not in _TEXT_SUFFIXES and path.name not in {"LICENSE", ".gitignore"}:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError):
        return [Finding("text_unreadable", relative, None, "utf8_required")]
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for pattern in _LOCAL_PATH_PATTERNS:
            if pattern.search(line):
                findings.append(Finding("local_path", relative, line_number, "machine_specific_path"))
        credential = _CREDENTIAL_ASSIGNMENT.search(line)
        if credential:
            findings.append(
                Finding(
                    "credential_assignment",
                    relative,
                    line_number,
                    f"field={credential.group('field').lower()}",
                )
            )
    return findings


def check_publication_tree(root: Path, paths: Iterable[str]) -> list[Finding]:
    root = Path(root)
    findings: list[Finding] = []
    for raw in paths:
        relative, unsafe = _normalize_path(str(raw))
        if not relative:
            continue
        if unsafe:
            findings.append(Finding("unsafe_manifest_path", relative, None, "repository_relative_required"))
            continue
        path_finding = _path_finding(relative)
        if path_finding is not None:
            findings.append(path_finding)
            continue
        findings.extend(_inspect_text(root, relative))
    return sorted(findings, key=lambda item: (item.path, item.line or 0, item.code, item.detail))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate an EveMissLab public repository manifest")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    return parser


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None, stdin: TextIO | None = None) -> int:
    args = _parser().parse_args(argv)
    source = stdin or sys.stdin
    if args.manifest is not None:
        try:
            paths = args.manifest.read_text(encoding="utf-8", errors="strict").splitlines()
        except (OSError, UnicodeError):
            findings = [Finding("manifest_unreadable", str(args.manifest), None, "utf8_required")]
        else:
            findings = check_publication_tree(args.root, paths)
    else:
        findings = check_publication_tree(args.root, source.read().splitlines())
    payload = {"findings": [asdict(item) for item in findings], "passed": not findings}
    stream = stdout or sys.stdout
    stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
