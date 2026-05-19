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


def test_cli_serve_prints_uvicorn_command_without_starting_server(tmp_path: Path):
    state_file = tmp_path / "innerwork-state.json"
    database_url = f"sqlite:///{tmp_path / 'innerwork.db'}"

    result = _run_cli(
        "serve",
        "--state",
        str(state_file),
        "--database-url",
        database_url,
        "--dry-run",
        "--host",
        "0.0.0.0",
        "--port",
        "9000",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "command": [
            sys.executable,
            "-m",
            "uvicorn",
            "innerwork.app:app",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
        ],
        "environment": {
            "INNERWORK_DATABASE_URL": database_url,
            "INNERWORK_STATE_PATH": str(state_file),
        },
    }
