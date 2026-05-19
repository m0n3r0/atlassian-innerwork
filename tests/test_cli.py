import json
import subprocess
import sys
from pathlib import Path


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "innerwork.cli", *args],
        check=False,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "src"},
    )


def test_cli_catalog_prints_osb_shaped_catalog():
    result = _run_cli("catalog")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["services"][0]["id"] == "innerwork-edge-service"


def test_cli_validate_accepts_example_manifest():
    result = _run_cli("validate", "examples/edge-service.yaml")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["service"]["service_id"] == "jira-web"


def test_cli_render_outputs_snapshot_for_example_manifest():
    result = _run_cli("render", "examples/edge-service.yaml")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["clusters"] == [{"name": "jira", "port": 8080}]
    assert payload["listeners"][0]["filters"] == [
        "http_connection_manager",
        "access_logs",
        "external_auth",
        "rate_limit",
    ]


def test_cli_validate_rejects_invalid_manifest(tmp_path: Path):
    manifest = tmp_path / "invalid.yaml"
    manifest.write_text(
        """
spec:
  service_id: bad
  owner: edge-team
  product_family: teamwork_core
  edge_profile: web_app_api
  domains: []
  routes: []
""".strip(),
        encoding="utf-8",
    )

    result = _run_cli("validate", str(manifest))

    assert result.returncode != 0
    assert "ValueError" in result.stderr or "at least one domain" in result.stderr
