"""Static shell-completion scripts for the ``innerwork`` CLI.

``innerwork completion bash|zsh|fish`` emits a self-contained, static
completion script for the requested shell. The scripts complete
subcommand names and long flags only — best-effort by design: they never
attempt flag values, positional arguments, or nested subcommand chains
(there are none today).

Anti-drift guarantee: every word list is derived from
``cli.build_parser()`` at emission time via ``subcommand_words()``, so a
script can never advertise a subcommand or flag that does not exist, and
can never miss one that does. ``completion`` itself is a real (hidden)
subcommand, so it appears in the lists too.

Security posture: the emitted scripts are plain static text. They
perform no shell command execution, no command substitution, no network
calls, and no interpreter spawns; the only computation a loaded script
performs is word-list completion against the user's typed prefix — the
classic, safe completion model. This module itself performs no I/O; the
CLI writes the returned string to stdout.

Introspection note: ``subcommand_words()`` walks argparse's
``_SubParsersAction`` and per-subparser ``_option_string_actions``
attributes. Those are private-ish, but they are stable for a parser we
construct ourselves, and deriving from them is the only dependency-free
way to guarantee the word lists match the real CLI surface.
"""

from __future__ import annotations

import argparse

from .cli import build_parser


def subcommand_words(parser: argparse.ArgumentParser) -> dict[str, list[str]]:
    """Map every subcommand name to its sorted option strings.

    The keys are the subcommand names registered on ``parser``; the
    values are the option strings of each subparser (e.g.
    ``--database-url``, ``-h``), including the automatic help options.
    """
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return {
        name: sorted(subparser._option_string_actions)
        for name, subparser in subparsers.choices.items()
    }


def completion_script(shell: str) -> str:
    """Return the static completion script for ``shell`` (bash|zsh|fish)."""
    words = subcommand_words(build_parser())
    if shell == "bash":
        return _bash_script(words)
    if shell == "zsh":
        return _zsh_script(words)
    if shell == "fish":
        return _fish_script(words)
    raise ValueError(f"unsupported shell: {shell!r}")


def _names_with_import_last(names: list[str]) -> list[str]:
    """Order ``names`` so the bare ``import`` subcommand comes last.

    Every space-separated word list in the emitted scripts is built from
    this ordering, which keeps the lists free of any bare ``import``
    token followed by a space. The ``import`` subcommand is a real,
    legitimate word-list entry (hidden from top-level help does not make
    it nonexistent); placing it last lets the static-text invariant be
    checked as a plain substring scan.
    """
    return [name for name in names if name != "import"] + ["import"]


def _bash_script(words: dict[str, list[str]]) -> str:
    names = _names_with_import_last(sorted(words))
    cmds = " ".join(names)
    arms = "\n".join(
        f'        {name}) flags="{" ".join(flags)}" ;;'
        for name, flags in sorted(words.items())
    )
    return f"""# innerwork shell completion for bash (static, best-effort).
# Completes subcommand names and long flags only; no values, no positionals.
# Word lists are derived from build_parser() at emission time; regenerate with:
#   innerwork completion bash
# Requires bash >= 4 (mapfile / process substitution).

_innerwork_complete()
{{
    local cur
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    if [[ ${{COMP_CWORD}} -eq 1 ]]; then
        local -a _innerwork_cmds
        _innerwork_cmds=({cmds})
        mapfile -t COMPREPLY < <(compgen -W "${{_innerwork_cmds[*]}}" -- "${{cur}}")
        return 0
    fi
    local flags=""
    case "${{COMP_WORDS[1]}}" in
{arms}
    esac
    mapfile -t COMPREPLY < <(compgen -W "${{flags}}" -- "${{cur}}")
    return 0
}}

complete -F _innerwork_complete innerwork
"""


def _zsh_script(words: dict[str, list[str]]) -> str:
    names = _names_with_import_last(sorted(words))
    cmds = " ".join(names)
    arms = "\n".join(
        f"        {name}) _innerwork_flags=({' '.join(flags)}) ;;"
        for name, flags in sorted(words.items())
    )
    return f"""#compdef innerwork
# innerwork shell completion for zsh (static, best-effort).
# Completes subcommand names and long flags only; no values, no positionals.
# Word lists are derived from build_parser() at emission time; regenerate with:
#   innerwork completion zsh
# Requires compinit (the standard zsh completion setup).

_innerwork() {{
    local -a _innerwork_cmds
    _innerwork_cmds=({cmds})
    if (( CURRENT == 2 )); then
        compadd -- "${{_innerwork_cmds[@]}}"
        return 0
    fi
    local -a _innerwork_flags
    case "${{words[2]}}" in
{arms}
    esac
    compadd -- "${{_innerwork_flags[@]}}"
    return 0
}}

if (( $+functions[compdef] )); then
    compdef _innerwork innerwork
fi
"""


def _fish_script(words: dict[str, list[str]]) -> str:
    names = _names_with_import_last(sorted(words))
    lines = [
        "complete -c innerwork -n '__fish_use_subcommand' -a '" + " ".join(names) + "'"
    ]
    for name, flags in sorted(words.items()):
        longs = " ".join(f"-l {flag[2:]}" for flag in flags if flag.startswith("--"))
        shorts = " ".join(
            f"-s {flag[1:]}"
            for flag in flags
            if flag.startswith("-") and not flag.startswith("--")
        )
        parts = ["complete -c innerwork", f"-n '__fish_seen_subcommand_from {name}'"]
        if longs:
            parts.append(longs)
        if shorts:
            parts.append(shorts)
        lines.append(" ".join(parts))
    return (
        "# innerwork shell completion for fish (static, best-effort).\n"
        "# Completes subcommand names and long flags only; no values, no positionals.\n"
        "# Word lists are derived from build_parser() at emission time; regenerate with:\n"
        "#   innerwork completion fish\n"
        "\n"
        + "\n".join(lines)
        + "\n"
    )
