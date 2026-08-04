"""CLI ergonomics: ``--help`` examples on migration commands + hidden shell completion.

Implements the §7 matrix of ``docs/roadmap_cli_ergonomics_scoping.md``:
parse-validated help examples on the five migration subcommands, the
``RawDescriptionHelpFormatter`` fix for ``doctor``'s epilog, and the
hidden ``innerwork completion bash|zsh|fish`` static scripts (word lists
derived from ``build_parser()`` at emission time).
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from innerwork.cli import build_parser

REPO_ROOT = Path(__file__).resolve().parents[1]

MIGRATION_COMMANDS = ("export", "import", "migrate", "import-markdown", "import-csv")
COMPLETION_SHELLS = ("bash", "zsh", "fish")


def _run_cli(
    *args: str, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
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


def _subparser_names() -> list[str]:
    parser = build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return sorted(subparsers.choices)


def _help_examples(command: str) -> list[list[str]]:
    """Return the argv (without the leading ``innerwork`` prog token) of every
    example line in ``innerwork <command> --help``."""
    result = _run_cli(command, "--help")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    try:
        start = lines.index("examples:")
    except ValueError:
        pytest.fail(f"no 'examples:' block in `innerwork {command} --help`")
    examples: list[list[str]] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("innerwork"):
            continue
        argv = shlex.split(stripped)
        assert argv and argv[0] == "innerwork"
        examples.append(argv[1:])
    return examples


# ----------------------------------------------------------------------
# Help examples on the five migration commands
# ----------------------------------------------------------------------


@pytest.mark.parametrize("command", MIGRATION_COMMANDS)
def test_migration_commands_help_show_examples(command: str):
    result = _run_cli(command, "--help")
    assert result.returncode == 0, result.stderr
    assert "examples:" in result.stdout
    assert any(
        line.lstrip().startswith(f"innerwork {command}")
        for line in result.stdout.splitlines()
    )


@pytest.mark.parametrize("command", MIGRATION_COMMANDS)
def test_every_help_example_parses_through_real_parser(command: str):
    """The load-bearing anti-hallucination gate: every example line must
    parse through the real parser. Unknown flags, missing required
    positionals, and bad choices all raise ``SystemExit(2)`` → failure."""
    parser = build_parser()
    examples = _help_examples(command)
    assert examples, f"no examples parsed from `innerwork {command} --help`"
    for argv in examples:
        parser.parse_args(argv)


def test_help_examples_reference_existing_paths():
    for command in MIGRATION_COMMANDS:
        for argv in _help_examples(command):
            for token in argv:
                if token.startswith("tests/"):
                    assert (REPO_ROOT / token).exists(), f"missing fixture path: {token}"


def test_no_fabricated_space_flag():
    """Regression for scoping §3: the task-body's ``--space`` example was
    fabricated and must never appear in help text."""
    result = _run_cli("import-markdown", "--help")
    assert result.returncode == 0
    assert "--space" not in result.stdout


def test_runnable_examples_exit_zero(tmp_path: Path):
    """The side-effect-conservative subset of the locked examples actually
    runs and exits 0 against fresh ``tmp_path`` stores.

    The checked-in markdown-tree fixture deliberately contains a root-level
    ``root.md`` to exercise the importer's rejection path
    (``test_root_level_md_rejected``), so the dry-run below uses a tmp copy
    without it — the same command shape the ``--help`` example advertises
    (``import-markdown <tree> --database-url ... --dry-run``) against a
    clean target, exactly like ``test_markdown_importer._fixture_copy``.
    """
    md_tree = tmp_path / "markdown_tree"
    shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "markdown_tree", md_tree)
    (md_tree / "root.md").unlink()
    md_db = tmp_path / "md.db"
    r = _run_cli(
        "import-markdown",
        str(md_tree),
        "--database-url",
        f"sqlite:///{md_db}",
        "--dry-run",
    )
    assert r.returncode == 0, r.stderr

    csv_db = tmp_path / "csv.db"
    r = _run_cli(
        "import-csv",
        "tests/fixtures/csv_import/work_items.csv",
        "--database-url",
        f"sqlite:///{csv_db}",
        "--dry-run",
    )
    assert r.returncode == 0, r.stderr

    migrate_db = tmp_path / "migrate.db"
    r = _run_cli(
        "migrate",
        "--source",
        "synthetic",
        "--database-url",
        f"sqlite:///{migrate_db}",
    )
    assert r.returncode == 0, r.stderr

    import_db = tmp_path / "import.db"
    r = _run_cli(
        "import",
        "tests/fixtures/synthetic_migration.json",
        "--database-url",
        f"sqlite:///{import_db}",
    )
    assert r.returncode == 0, r.stderr

    out = tmp_path / "out.json"
    r = _run_cli("export", "--database-url", f"sqlite:///{migrate_db}", "--out", str(out))
    assert r.returncode == 0, r.stderr
    assert out.is_file()


def test_doctor_examples_render_on_separate_lines():
    """Regression for the formatter fix: the old run-on epilog paragraph is
    gone; ``examples:`` is followed by real lines."""
    result = _run_cli("doctor", "--help")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    try:
        start = lines.index("examples:")
    except ValueError:
        pytest.fail("no 'examples:' block in `innerwork doctor --help`")
    example_lines = [
        line for line in lines[start + 1 :] if line.lstrip().startswith("innerwork doctor")
    ]
    assert len(example_lines) >= 2


# ----------------------------------------------------------------------
# Hidden shell completion
# ----------------------------------------------------------------------


@pytest.mark.parametrize("shell", COMPLETION_SHELLS)
def test_completion_smoke(shell: str):
    result = _run_cli("completion", shell)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


def test_completion_bash_shape():
    script = _run_cli("completion", "bash").stdout
    assert "_innerwork" in script
    assert "complete -F" in script


def test_completion_zsh_shape():
    script = _run_cli("completion", "zsh").stdout
    assert script.startswith("#compdef innerwork")


def test_completion_fish_shape():
    script = _run_cli("completion", "fish").stdout
    assert "complete -c innerwork" in script


def test_completion_unknown_shell_exit_2():
    result = _run_cli("completion", "powershell")
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    for shell in COMPLETION_SHELLS:
        assert shell in result.stderr
    assert result.stdout == ""


def test_completion_missing_shell_exit_2():
    result = _run_cli("completion")
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()
    assert result.stdout == ""


def test_completion_hidden_from_top_level_help():
    top = _run_cli("--help")
    assert top.returncode == 0
    assert "completion" not in top.stdout
    callable_ = _run_cli("completion", "--help")
    assert callable_.returncode == 0
    for shell in COMPLETION_SHELLS:
        assert shell in callable_.stdout


@pytest.mark.parametrize("shell", COMPLETION_SHELLS)
def test_completion_covers_all_subcommands(shell: str):
    script = _run_cli("completion", shell).stdout
    for name in _subparser_names():
        assert name in script, f"{shell} script missing subcommand {name!r}"


_BASH_FLAG_ARM = re.compile(r'^        ([a-z0-9-]+)\) flags="([^"]*)" ;;$')
_ZSH_FLAG_ARM = re.compile(r"^        ([a-z0-9-]+)\) _innerwork_flags=\(([^)]*)\) ;;$")


def _script_flags(script: str, shell: str, command: str) -> set[str]:
    if shell == "bash":
        for line in script.splitlines():
            match = _BASH_FLAG_ARM.match(line)
            if match and match.group(1) == command:
                return set(match.group(2).split())
    elif shell == "zsh":
        for line in script.splitlines():
            match = _ZSH_FLAG_ARM.match(line)
            if match and match.group(1) == command:
                return set(shlex.split(match.group(2)))
    else:  # fish
        found: set[str] = set()
        for line in script.splitlines():
            if f"__fish_seen_subcommand_from {command}'" in line:
                for flag in re.findall(r"-l (\S+)", line):
                    found.add(f"--{flag}")
                for flag in re.findall(r"-s (\S+)", line):
                    found.add(f"-{flag}")
        return found
    raise AssertionError(f"no flag arm for {command!r} in {shell} script")


@pytest.mark.parametrize("command", (*MIGRATION_COMMANDS, "doctor"))
def test_completion_flag_lists_match_parser(command: str):
    """Bidirectional anti-drift gate: every flag the script advertises for
    ``command`` exists on the real subparser, and every real option string
    appears in the script — no invented, no missing."""
    parser = build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    expected = set(subparsers.choices[command]._option_string_actions)
    for shell in COMPLETION_SHELLS:
        script = _run_cli("completion", shell).stdout
        found = _script_flags(script, shell, command)
        assert found == expected, f"{shell} flags for {command}: {found} != {expected}"


@pytest.mark.parametrize("shell", COMPLETION_SHELLS)
def test_completion_scripts_are_static_text(shell: str):
    """The scripts are plain static text: no code execution, no command
    substitution, no network, no interpreter/import spawns. ``import`` is a
    real subcommand name and appears in the word lists, but never followed
    by a space (word lists are ordered with ``import`` last)."""
    script = _run_cli("completion", shell).stdout
    for forbidden in ("eval", "exec", "$(", "`", "curl ", "wget ", "import ", "socket"):
        assert forbidden not in script, f"{shell} script contains {forbidden!r}"


def test_completion_stdout_only():
    result = _run_cli("completion", "bash")
    assert result.returncode == 0
    assert result.stderr == ""


def test_migration_guide_documents_best_effort():
    guide = (REPO_ROOT / "docs" / "migration-guide.md").read_text(encoding="utf-8")
    assert "### 2.6" in guide
    assert "best-effort" in guide


def test_existing_cli_suites_stay_green():
    """Regression net (scoping §7): the pre-existing CLI suites pass
    unmodified. Run each as a subprocess so failures name the suite."""
    suites = (
        "tests/test_cli.py",
        "tests/test_domain_cli.py",
        "tests/test_doctor.py",
        "tests/test_migration.py",
    )
    for suite in suites:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", suite],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{suite} failed:\n{result.stdout}\n{result.stderr}"
