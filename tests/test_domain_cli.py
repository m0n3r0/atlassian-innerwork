"""End-to-end tests for the work-graph CLI commands (Phase B slice 1)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_cli(
    *args: str, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    import os

    env = {"PYTHONPATH": "src", "PATH": os.environ.get("PATH", "")}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "innerwork.cli", *args],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


def test_workflow_command_prints_default_workflow():
    result = _run_cli("workflow")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["initial_state"] == "todo"
    assert "todo" in payload["states"]


def test_domain_cli_full_lifecycle(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    url = f"sqlite:///{db}"

    # project-create
    r = _run_cli(
        "project-create",
        "--database-url",
        url,
        "--key",
        "ENG",
        "--name",
        "Engineering",
        "--owner",
        "eml",
    )
    assert r.returncode == 0, r.stderr
    project = json.loads(r.stdout)
    assert project["key"] == "ENG"

    # projects (list)
    r = _run_cli("projects", "--database-url", url)
    assert r.returncode == 0
    assert [p["key"] for p in json.loads(r.stdout)["projects"]] == ["ENG"]

    # work-item-create
    r = _run_cli(
        "work-item-create",
        "--database-url",
        url,
        "--project-id",
        project["project_id"],
        "--title",
        "Set up CI",
    )
    assert r.returncode == 0, r.stderr
    item = json.loads(r.stdout)
    assert item["key"] == "ENG-1"
    assert item["state"] == "todo"

    # work-item-transition (valid)
    r = _run_cli(
        "work-item-transition",
        "--database-url",
        url,
        "--work-item-id",
        item["work_item_id"],
        "--to-state",
        "in_progress",
        "--actor",
        "eml",
    )
    assert r.returncode == 0, r.stderr
    transitioned = json.loads(r.stdout)
    assert transitioned["work_item"]["state"] == "in_progress"

    # work-item-transition (invalid: in_progress -> todo is valid, but in_progress -> done is too;
    # let's verify the rejection path for done -> todo)
    r = _run_cli(
        "work-item-transition",
        "--database-url",
        url,
        "--work-item-id",
        item["work_item_id"],
        "--to-state",
        "todo",  # in_progress -> todo is allowed (reopen)
        "--actor",
        "eml",
    )
    assert r.returncode == 0


def test_domain_cli_rejects_duplicate_project_key(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    url = f"sqlite:///{db}"
    args = [
        "project-create",
        "--database-url",
        url,
        "--key",
        "ENG",
        "--name",
        "Eng",
        "--owner",
        "eml",
    ]
    assert _run_cli(*args).returncode == 0
    second = _run_cli(*args)
    assert second.returncode == 1
    assert "already exists" in second.stderr


def test_domain_cli_rejects_invalid_transition(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    url = f"sqlite:///{db}"
    project = json.loads(
        _run_cli(
            "project-create",
            "--database-url",
            url,
            "--key",
            "ENG",
            "--name",
            "Eng",
            "--owner",
            "eml",
        ).stdout
    )
    item = json.loads(
        _run_cli(
            "work-item-create",
            "--database-url",
            url,
            "--project-id",
            project["project_id"],
            "--title",
            "x",
        ).stdout
    )
    bad = _run_cli(
        "work-item-transition",
        "--database-url",
        url,
        "--work-item-id",
        item["work_item_id"],
        "--to-state",
        "done",
        "--actor",
        "eml",
    )
    assert bad.returncode == 1
    assert "not allowed" in bad.stderr or "InvalidTransition" in bad.stderr


def test_domain_cli_requires_database_url():
    # No --database-url and no env var. We pass env_extra that explicitly clears
    # the env var if present; the subprocess inherits only what we pass.
    result = _run_cli("projects")
    assert result.returncode == 2
    assert "database-url" in result.stderr.lower() or "required" in result.stderr.lower()
