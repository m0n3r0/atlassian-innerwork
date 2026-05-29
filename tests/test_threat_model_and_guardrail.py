"""Tests for threat-model presence and anti-hallucination check."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_threat_model_exists() -> None:
    doc = REPO_ROOT / "docs" / "threat-model.md"
    assert doc.exists(), "docs/threat-model.md must ship with phase 7"
    text = doc.read_text(encoding="utf-8")
    assert "Threat Model" in text
    assert "Phase 7" in text
    # Must explicitly disclaim compliance frameworks.
    assert "do" in text.lower() and "not" in text.lower()


def test_threat_model_lists_required_sections() -> None:
    text = (REPO_ROOT / "docs" / "threat-model.md").read_text(encoding="utf-8")
    for heading in ("Scope", "Assets", "Trust boundaries", "Known gaps"):
        assert heading in text, f"threat-model.md missing section: {heading}"


def test_anti_hallucination_script_passes() -> None:
    """Running the guardrail against the repo itself must succeed."""
    script = REPO_ROOT / "scripts" / "check_anti_hallucination.py"
    assert script.exists()
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"anti-hallucination check failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )


def test_anti_hallucination_detects_forbidden_term(tmp_path: Path) -> None:
    """The guardrail must trip on a freshly-planted forbidden token."""
    script = REPO_ROOT / "scripts" / "check_anti_hallucination.py"
    bad = tmp_path / "claim.md"
    bad.write_text("This project is SOC 2 compliant.\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "SOC" in result.stderr
