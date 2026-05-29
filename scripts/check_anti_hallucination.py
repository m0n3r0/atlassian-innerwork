#!/usr/bin/env python3
"""Anti-hallucination guardrail for compliance-framework claims.

Scans the repository for forbidden compliance buzzwords (SOC2, ISO 27001,
HIPAA, GDPR, PCI-DSS, FedRAMP, ...) so the project never accidentally
claims certification or "compliance" it does not have. Phase 7 trust
hardening adds operator-facing security primitives; it does NOT make this
project compliant with any external framework.

Exit codes::

    0  no forbidden claims found
    1  one or more forbidden claims found
    2  invocation error

Allowlisting is intentional and narrow: the regex matches the framework
names as standalone tokens, so prose like "this is not SOC2-compliant" or
"GDPR is out of scope" will trip the check. That is the desired posture --
either the prose disappears or the file is explicitly excluded via the
ALLOWLIST set below.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Forbidden tokens. Word-boundary anchored. Case-insensitive.
FORBIDDEN_PATTERNS: tuple[str, ...] = (
    r"\bSOC\s*2\b",
    r"\bISO\s*27001\b",
    r"\bHIPAA\b",
    r"\bGDPR\b",
    r"\bPCI[-\s]?DSS\b",
    r"\bFedRAMP\b",
    r"\bCCPA\b",
)

# Files that may legitimately reference these terms (e.g. the script itself
# and the threat-model that explains why we do NOT claim them).
ALLOWLIST: frozenset[str] = frozenset(
    {
        "scripts/check_anti_hallucination.py",
        "docs/threat-model.md",
        "tests/test_threat_model_and_guardrail.py",
    }
)

# File extensions we scan. Keep it narrow to avoid false positives in
# binary or vendored content.
SCAN_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".md", ".rst", ".txt", ".toml", ".yaml", ".yml"}
)

# Directories we skip entirely.
SKIP_DIRS: frozenset[str] = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}
)


def iter_repo_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in SCAN_EXTENSIONS:
            continue
        out.append(path)
    return sorted(out)


def scan(root: Path) -> list[tuple[Path, int, str, str]]:
    compiled = [re.compile(pat, re.IGNORECASE) for pat in FORBIDDEN_PATTERNS]
    findings: list[tuple[Path, int, str, str]] = []
    for path in iter_repo_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in ALLOWLIST:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pat in compiled:
                m = pat.search(line)
                if m:
                    findings.append((path, lineno, m.group(0), line.strip()))
                    break
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to scan (default: cwd)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    findings = scan(root)
    if not findings:
        print("anti-hallucination check: OK (no forbidden compliance claims found)")
        return 0
    print("anti-hallucination check: FAILED", file=sys.stderr)
    for path, lineno, token, line in findings:
        rel = path.relative_to(root).as_posix()
        print(f"  {rel}:{lineno}: {token!r} in: {line}", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
