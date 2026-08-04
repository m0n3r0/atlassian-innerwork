# Roadmap item: cli-ergonomics — friendlier `--help` examples + hidden shell completion — PM scoping

**Status:** PM scoping (pre-implementation). Source: `docs/roadmap.md` → "Directional next" → CLI ergonomics (`slug=cli-ergonomics`): "*Friendlier `--help` examples on the migration commands*" and "*Optional shell completion (bash, zsh, fish) emitted by a hidden CLI subcommand*".
**Parent:** post-launch backlog item; no phase number. Implementation task `t_75de6f68` branches from `main` on `feat/cli-ergonomics` and is **DO NOT MERGE** (QA gate first).
**Audience:** the implementation worker (atlassianeng). Read this end-to-end before touching files.

---

## §0 Honest baseline (what the repo has, today, verified)

Verified against `main` at commit `149ae46` on 2026-08-05 by reading source **and** running the real CLI (`uv run python -m innerwork.cli --help` and per-subcommand `--help`). No guessed commands, flags, or paths anywhere in this doc.

| Asset | Present? | Path / facts |
|---|---|---|
| CLI subcommand registry | ✅ | `src/innerwork/cli.py:43` `build_parser()` — **19 subcommands** via `parser.add_subparsers(dest="command", required=True)`: `catalog, products, phases, validate, render, serve, workflow, projects, project-create, work-items, work-item-create, work-item-transition, export, import, migrate, metrics, import-markdown, import-csv, doctor`. |
| Migration/import/export commands | ✅ 5 | The locked set for this roadmap item: **`export`, `import`, `migrate`, `import-markdown`, `import-csv`** (all five dispatch through `_domain_dispatch`, `cli.py:519`). **None of the five currently has any usage example in `--help`** (verified by running each `--help`). |
| `innerwork doctor` help example precedent | ✅ | `cli.py:292-301` — `doctor` has an `epilog=` with an `examples:` block (added by the innerwork-doctor feature, PR #55). **Formatting bug:** the top-level parser uses the default `HelpFormatter`, which collapses newlines — the epilog renders as one run-on paragraph ("examples: innerwork doctor validate the configured store (INNERWORK_DATABASE_URL) innerwork doctor data/innerwork.db validate a…"). Same bug would hit every new epilog. Fix: `formatter_class=argparse.RawDescriptionHelpFormatter` on the affected subparsers. `tests/test_doctor.py:122` only asserts `"examples:" in result.stdout` + tokens `--json`/`--integrity-check`/`--audit-log` — safe under the formatter change. |
| Real fixture paths for examples | ✅ | `tests/fixtures/markdown_tree/docs/` (+ `eng/`) — markdown-tree fixture (used by `test_markdown_importer.py`); `tests/fixtures/csv_import/work_items.csv` / `work_items.tsv` / `edge_cases.csv`; `tests/fixtures/synthetic_migration.json` — a real v1 portability envelope (the synthetic migration fixture). Examples can reference these truthfully. |
| Shell completion subcommand | ❌ | No `completion` symbol anywhere in `src/`, `tests/`, `docs/` (verified by grep). Greenfield. |
| Stale help prose found | ⚠️ | `docs/migration-guide.md:79` — §2 intro still says "Phase 10 adds **three** subcommands to `innerwork`" while §2.1–2.5 now document five sections (`export-domain`/`import-domain`/`migrate`/`metrics`/`doctor`). The intro sentence is stale and misleading; fix in the same PR (§1 row 6). Also `import-markdown`'s help text (cli.py:225-248) is accurate — but see §3: the roadmap task body's illustrative example uses a flag that does **not** exist. |
| Test conventions | ✅ | `tests/test_domain_cli.py:11` `_run_cli(*args, env_extra=...)` subprocess helper (`python -m innerwork.cli`, `PYTHONPATH=src`); `tests/test_doctor.py` extends the same pattern. New suite `tests/test_cli_ergonomics.py` reuses it. |
| CI parity | ✅ | `.github/workflows/ci.yml` runs `uv run ruff check .`, `uv run pyright`, `uv run pytest -q`; `pyproject.toml` `[tool.ruff] line-length = 100`, `target-version = "py310"`, lint select `E,F,I,UP,B`. |
| Compliance guardrail | ✅ | `scripts/check_anti_hallucination.py` scans the repo for forbidden compliance buzzwords; must keep exiting 0. New files must not trip it (they won't — no compliance vocabulary). |
| Dependencies | ✅ | argparse is stdlib; `argparse.SUPPRESS` and `RawDescriptionHelpFormatter` work on all supported Pythons (≥3.10). **No new dependency, no CI change, no network access anywhere in this feature.** |

**Implication.** A contained, additive slice: (a) add an `epilog=` examples block to the **five** migration subparsers and switch those subparsers (plus `doctor`) to `RawDescriptionHelpFormatter` so the examples render as real lines; (b) one new `src/innerwork/completion.py` module emitting static best-effort completion scripts, one hidden `completion` subcommand registered with `help=argparse.SUPPRESS`; (c) one new test suite `tests/test_cli_ergonomics.py`; (d) doc/CHANGELOG updates. No changes to any existing dispatch branch, no schema/domain code, no new dependencies.

---

## §1 Exact files to write or modify

Implementation worker MUST touch exactly the files in this table, in this order. Anything else is scope creep.

| # | Path | Action | Rough size | Notes |
|---|---|---|---|---|
| 1 | `docs/roadmap_cli_ergonomics_scoping.md` | (this file) | n/a | Exists at PM-scoping time. Implementation worker does not modify. |
| 2 | `src/innerwork/completion.py` | **new** | ~180 lines | `completion_script(shell: str) -> str` returning the static script for `bash`/`zsh`/`fish`; subcommand + long-flag word lists derived from `build_parser()` at emission time (§4). Stdlib only (`argparse, textwrap, typing`). No I/O except returning a string; the CLI writes it to stdout. |
| 3 | `src/innerwork/cli.py` | **edit** | +~90/−0 | (i) Add `formatter_class=argparse.RawDescriptionHelpFormatter` to the `export`, `import`, `migrate`, `import-markdown`, `import-csv`, and `doctor` subparsers. (ii) Add the locked `epilog=` examples block (§2) to each of the five migration subparsers. (iii) Register hidden `completion = subcommands.add_parser("completion", help=argparse.SUPPRESS, ...)` with positional `shell` (`choices=("bash","zsh","fish")`). (iv) Add `if args.command == "completion": return _completion_dispatch(args)` to `main()` and the tiny `_completion_dispatch` helper (write `completion_script(args.shell)` to stdout, return 0). No changes to any existing branch. |
| 4 | `tests/test_cli_ergonomics.py` | **new** | ~300 lines | Full suite per §7, reusing the `_run_cli` subprocess pattern. |
| 5 | `docs/migration-guide.md` | **edit** | +~45/−3 | New `### 2.6 Help examples and shell completion`: examples contract (parse-validated, real flags/paths), `innerwork completion bash|zsh|fish` shape, hidden-mechanism note (`argparse.SUPPRESS` — hidden from top-level help on purpose), best-effort scope (subcommands + long flags only, no values/positionals), per-shell install one-liners (bash `source <(innerwork completion bash)`, zsh `source <(innerwork completion zsh)`, fish `innerwork completion fish | source`), static-text/security guarantee, exit codes (0 ok, 2 unknown shell). Fix the stale §2 intro sentence (see row 6). |
| 6 | `docs/migration-guide.md` §2 intro | **edit (part of row 5)** | ±1 line | Replace "Phase 10 adds **three** subcommands…" with an accurate enumeration: the §2.1–2.5 commands plus a pointer that §2.6 documents help examples and completion. Honest-help criterion. |
| 7 | `CHANGELOG.md` | **edit** | +~8 lines | Under `[Unreleased]`, a `### Added — CLI ergonomics (help examples + shell completion)` subsection: five migration commands now ship runnable `--help` examples (parse-validated by tests), hidden `innerwork completion bash|zsh|fish` (static, best-effort, no deps), `doctor`/migration help now render examples on separate lines (formatter fix), no version bump, no new dependency. |
| 8 | `docs/roadmap.md` | **edit (optional, recommended)** | −2/+3 lines | After the implementation PR merges, move the two "CLI ergonomics" bullets from "Directional next" into the shipped list. Same PR, tiny diff. |

**Files that LOOK like they should be touched but MUST NOT be touched.**

| Path | Why not |
|---|---|
| `src/innerwork/domain_store.py`, `portability.py`, `analytics.py`, `markdown_importer.py`, `csv_importer.py`, `doctor.py`, `app.py`, `model.py`, `serialization.py` | Pure help-text/completion work touches none of the domain logic. The examples reference the existing CLI surface; nothing in these modules changes. |
| `tests/test_cli.py`, `tests/test_domain_cli.py`, `tests/test_doctor.py`, `tests/fixtures/*`, all other suites | Existing suites stay untouched and must stay green — they are the regression net. `test_doctor.py:122` (`test_help_lists_doctor_with_example`) is expected to keep passing under the formatter change (it asserts tokens, not the run-on shape). No new fixtures: every example path already exists (§0). |
| `pyproject.toml`, `.github/workflows/*` | No new dependency (argparse stdlib suffices), no CI change. |
| `scripts/check_anti_hallucination.py` | Not touched; the feature just must not trip it (§9). |

---

## §2 Locked help-example content (per migration command)

**Format rule (locked).** Each of the five migration subparsers gets `formatter_class=argparse.RawDescriptionHelpFormatter` and an `epilog=` string of the exact shape (note: `examples:` on its own line, then one example per line, each starting with the `innerwork` prog name — the parse-validity test in §7 keys off this shape). **No `%` characters anywhere in an epilog** (argparse `%`-formatting footgun — it would be interpolated or crash). **No `--space`, no invented flags** (see §3). All paths below exist in the repo (§0) or are the documented generic local convention (`data/...`, `sqlite:///.innerwork/innerwork.db` — the latter is already the example URL in every `--database-url` help string, so it is an established public convention, not an internal path).

Locked epilogs (implementation worker copies verbatim):

**`export`** (flags: `--database-url`, `--out`, `--include-audit`, `--audit-log`, `--progress`):
```
examples:
  innerwork export --database-url sqlite:///.innerwork/innerwork.db
  innerwork export --database-url sqlite:///.innerwork/innerwork.db --out data/export.json
  innerwork export --database-url sqlite:///.innerwork/innerwork.db --include-audit --audit-log data/audit.db --out data/export.json
```

**`import`** (positional `input`; flags: `--database-url`, `--audit-log`):
```
examples:
  innerwork import tests/fixtures/synthetic_migration.json --database-url sqlite:///.innerwork/innerwork.db
  innerwork import data/export.json --database-url sqlite:///.innerwork/innerwork.db --audit-log data/audit.db
```

**`migrate`** (flags: `--database-url`, `--audit-log`, `--source` choices `synthetic`):
```
examples:
  innerwork migrate --database-url sqlite:///.innerwork/innerwork.db
  innerwork migrate --source synthetic --database-url sqlite:///.innerwork/innerwork.db --audit-log data/audit.db
```

**`import-markdown`** (positional `dir`; flags: `--database-url`, `--audit-log`, `--author`, `--dry-run` — **no `--space`**):
```
examples:
  innerwork import-markdown tests/fixtures/markdown_tree/docs --database-url sqlite:///.innerwork/innerwork.db --dry-run
  innerwork import-markdown tests/fixtures/markdown_tree --author eml --database-url sqlite:///.innerwork/innerwork.db
```

**`import-csv`** (positional `file`; flags: `--database-url`, `--audit-log`, `--owner`, `--delimiter` choices `auto/comma/tab`, `--dry-run`, `--allow-populated`):
```
examples:
  innerwork import-csv tests/fixtures/csv_import/work_items.csv --database-url sqlite:///.innerwork/innerwork.db --dry-run
  innerwork import-csv tests/fixtures/csv_import/work_items.tsv --delimiter tab --owner eml --database-url sqlite:///.innerwork/innerwork.db
```

**Example-design rules (locked, these are what make the examples honest and runnable):**
1. **Real flags only** — every flag/positional in every example exists on that subparser today. Enforced by the parse-validity test (§7, row `test_every_help_example_parses_through_real_parser`), not by review.
2. **Real paths** — repo-relative paths point at fixtures that exist (`tests/fixtures/...`); generic paths (`data/export.json`, `data/audit.db`, `sqlite:///.innerwork/innerwork.db`) are documented local conventions, never `/home/...`, `/Users/...`, credentials, or env-specific values (SEC gate).
3. **Side-effect-conservative first example** — importers lead with `--dry-run` where the command supports it; `export` examples are read-only or `--out`-targeted; the first `migrate`/`import` examples target the documented scratch URL. The end-to-end runnability subset (§7) executes the dry-run/`--out`/scratch examples for real against `tmp_path` stores.
4. **`doctor` keeps its existing epilog** — only the formatter changes so it renders as lines; its examples are already parse-valid (verified: `doctor data/innerwork.db --json`, `--integrity-check --audit-log data/audit.db` all match `doctor`'s registered flags).

**Out-of-scope commands (decision, documented):** `metrics` is analytics, not migration/import/export — the roadmap acceptance criterion names "migration/import/export subcommands", so `metrics` gets no examples in this slice (its `--window-*` flags are documented in its help text already). `serve`, `validate`, `render`, `catalog`, `products`, `phases`, `workflow`, `projects`/`project-create`/`work-items`/`work-item-create`/`work-item-transition` are not migration commands either — untouched. `doctor` is included only for the formatter fix, not for new examples.

---

## §3 Anti-hallucination call-out: the roadmap task-body example is fabricated

The roadmap task body's illustrative example — `innerwork import-markdown ./fixtures/docs --space eng` — **is not runnable and must never appear in help text**:

- `--space` **does not exist** on `import-markdown` (verified: cli.py:225-248 registers only `dir` positional + `--database-url`/`--audit-log`/`--author`/`--dry-run`). A `--space` example would fail the parse-validity gate immediately.
- `./fixtures/docs` **does not exist** (the real markdown-tree fixture is `tests/fixtures/markdown_tree/docs/`).
- The `--space eng` semantics the task body implies (target-space override) are not a feature of the markdown importer; spaces are derived from immediate subdirectories (migration-guide §4.2).

The parse-validity test (§7) exists precisely so this class of error is caught mechanically. The implementation worker MUST NOT "fix" the example by inventing a `--space` flag to make it work — adding a flag to satisfy an example is the reverse of this roadmap item. If a future roadmap item genuinely wants target-space selection, it gets its own scoping.

---

## §4 Completion subcommand design (locked)

### 4.1 Shape and exit codes

```
innerwork completion bash|zsh|fish
```

- Positional `shell` with `choices=("bash", "zsh", "fish")` — argparse rejects anything else: **exit 2** with the standard "invalid choice" stderr, stdout empty. Missing positional: argparse usage error, exit 2. **No other shells ship** — anti-hallucination: nothing is claimed for PowerShell, tcsh, nushell, etc.
- Success: the static script is written to **stdout**, nothing to stderr, **exit 0**. The script is self-contained static text: no network, no runtime dependencies, no `eval`/`exec` of user input at generation or load time (§6).

### 4.2 Hiding mechanism (decide-and-document)

**Decision: `help=argparse.SUPPRESS` on the subparser.** `completion` is then absent from `innerwork --help`'s subcommand listing while remaining fully callable (`innerwork completion --help` works). This is the stdlib argparse hiding mechanism — zero code, no third-party dependency, works on all supported Pythons. **Alternative considered and rejected:** a top-level `--all` flag to reveal hidden commands — adds parser complexity and a second concept for zero user value, because the command is documented in `docs/migration-guide.md` §2.6 and in `CHANGELOG.md` (the two places operators actually look). The hiding is deliberate, not secret: the doc explicitly says the command exists and is hidden from top-level help on purpose.

### 4.3 `src/innerwork/completion.py` interface (locked)

```python
def completion_script(shell: str) -> str: ...   # shell ∈ {"bash","zsh","fish"}
def subcommand_words(parser: argparse.ArgumentParser) -> dict[str, list[str]]: ...
    # {subcommand_name: [long_option, ...]} derived from build_parser() at emission time
```

- **Word lists are derived from `build_parser()`, never hand-maintained.** Walk the parser's subparsers action (the `_SubParsersAction` among `parser._actions`), then each subparser's `_option_string_actions` keys. This is the anti-drift guarantee: the completion scripts cannot advertise a subcommand or flag that does not exist, and cannot miss one that does (locked by test rows `test_completion_covers_all_subcommands` / `test_completion_flag_lists_match_parser`, §7). Using argparse's introspection surface is honest and dependency-free; it is our own parser, so the private-ish attribute access is stable (documented in the module docstring).
- The emitted script embeds those word lists as **literal static text** (e.g. `compgen -W 'export import migrate import-markdown import-csv …'` / zsh `_describe` array / fish `complete -a '…'`). No command substitution, no external commands at load time.
- `completion` itself is a real subcommand, so it appears in the word lists (hidden ≠ nonexistent); completing it is honest.
- Templates per shell (implementation detail, exact script text is the implementer's, but the coverage contract is fixed):
  - **bash:** `_innerwork_complete()` reading `COMP_WORDS`/`COMP_CWORD`; completes subcommands when `COMP_CWORD == 1`, otherwise completes long flags for the current subcommand; `complete -F _innerwork_complete innerwork`.
  - **zsh:** `#compdef innerwork` + a `_innerwork` function using `_arguments`/`compadd` with the same word lists.
  - **fish:** one `complete -c innerwork` line per subcommand using `-n '__fish_seen_subcommand_from <cmd>'` guards and `-l <flag>` entries.

### 4.4 Best-effort scope (documented honestly)

The scripts complete **subcommand names** and **long flags** only. They do **not** complete: flag values (paths, `sqlite:///` URLs, delimiter choices), positional arguments, short-flag clustering, or nested subcommand chains (there are none today). §2.6 of the migration guide states this explicitly — "best-effort, not exhaustive for every flag" per the roadmap item. No performance or adoption metrics are claimed anywhere.

### 4.5 Dispatch

`_completion_dispatch(args)` in `cli.py`: `sys.stdout.write(completion_script(args.shell))`; return 0. Placed before the domain-dispatch set in `main()` (it constructs nothing, like `doctor`'s branch — must never build a `DomainStore`).

---

## §5 Honest gap calls (decide-and-document, locked for v1)

| Topic | Decision | Rationale |
|---|---|---|
| Hidden-mechanism | `help=argparse.SUPPRESS` (§4.2) | Stdlib, zero code, works on 3.10+; `--all`-flag alternative rejected (complexity for no user value). |
| Script source | Static templates; word lists derived from `build_parser()` at emission time | Anti-drift + anti-hallucination: completion can never advertise a nonexistent subcommand/flag, and never misses a real one. Emitted artifact is plain static text. |
| Completion coverage | Subcommands + long flags only; no values/positionals/choices | Honest best-effort per roadmap item; §2.6 documents the boundary so users are not surprised. |
| Shells shipped | bash, zsh, fish only | Matches the roadmap item exactly. No PowerShell/etc. — nothing claimed that is not implemented. |
| Formatter change | `RawDescriptionHelpFormatter` on the 5 migration subparsers + `doctor` | Default `HelpFormatter` collapses epilog newlines into a run-on paragraph (verified on `doctor` today). RawDescription preserves the `examples:` line structure. Only subparser help blocks change; top-level help layout is unchanged; `test_doctor.py:122` stays green. |
| `metrics` excluded | No examples added | It is analytics, not a migration/import/export command; the acceptance criterion names migration/import/export. Documented in §2 so nobody "fixes" it by adding examples (or worse, flags). |
| Task-body `--space` example | Rejected and replaced (§3) | Flag does not exist; the parse-validity test would fail it. Adding a flag to satisfy an example is out of scope. |
| Stale migration-guide §2 intro | Fixed in the same PR (§1 row 6) | "Phase 10 adds three subcommands" is false today; honest-help criterion covers docs prose adjacent to help. |
| New dependencies / CI / network | None / no change / none | argparse stdlib; scripts are static text; no benchmark or usage numbers anywhere. |
| `completion` in word lists | Yes, included | It is a real callable subcommand; hidden from top-level help ≠ nonexistent. |

---

## §6 Security posture (from the task's SEC gate)

1. **Static text only.** The emitted scripts contain literal word lists; they perform no command substitution, no `eval`, no `exec`, no external process spawn, no network I/O at generation **or** load time. The only computation a loaded script does is word-list completion against the user's typed prefix — the classic, safe completion model.
2. **No shell-injection surface.** User input (the typed prefix) is only ever compared against static word lists; nothing user-controlled is ever interpolated into a command string, evaluated, or written back. The bash script must use `compgen -W '<static list>'` against the typed word — never `eval "$words"`.
3. **No embedded secrets/environment data.** Help examples and completion scripts contain no `/home/...` paths, no absolute machine paths, no credentials, no tokens, no URLs beyond the documented `sqlite:///.innerwork/innerwork.db` convention. Enforced by the §8 grep checklist.
4. **Generation-side safety.** `completion.py` imports only stdlib and `cli.build_parser`; it performs no I/O (the CLI writes its return value to stdout). No audit sink, no store construction — it never touches a database.

---

## §7 Test plan

`tests/test_cli_ergonomics.py` (new). Reuse the `_run_cli(*args, env_extra=...)` subprocess pattern from `tests/test_domain_cli.py`. All end-to-end runs use `tmp_path` stores; no new fixtures (every example path already exists in-repo). Parse-validity uses `build_parser().parse_args()` in-process (import from `src` via the same `PYTHONPATH=src` convention the suite already uses in-process where needed — prefer subprocess for CLI-behavior tests, in-process only for parser-level checks).

| Test | Asserts |
|---|---|
| `test_migration_commands_help_show_examples` (parametrized over the 5 commands) | `innerwork <cmd> --help` exit 0; stdout contains `examples:` and ≥1 line starting with `innerwork <cmd>`. |
| `test_every_help_example_parses_through_real_parser` (parametrized over the 5 commands) | For every example line in the help output (lines after the `examples:` marker that start with `innerwork`), `shlex.split` the line, drop the leading `innerwork` prog token, and call `build_parser().parse_args(argv)` — **must not raise `SystemExit`**. Unknown flags, missing required positionals, or bad choices all raise `SystemExit(2)` → test failure. This is the load-bearing anti-hallucination test. |
| `test_help_examples_reference_existing_paths` | Every path token in every example argv that starts with `tests/` exists on disk relative to the repo root (fixture paths are real). |
| `test_no_fabricated_space_flag` | `innerwork import-markdown --help` stdout does **not** contain `--space` (regression for §3). |
| `test_runnable_examples_exit_zero` (parametrized subset) | Actually execute the side-effect-conservative examples against `tmp_path`: `import-markdown … --dry-run`; `import-csv … --dry-run`; `migrate --source synthetic` into a fresh tmp store; `import tests/fixtures/synthetic_migration.json` into a fresh tmp store; `export` of the migrated tmp store with `--out <tmp>/out.json` (file exists, exit 0). Each asserts rc 0. |
| `test_doctor_examples_render_on_separate_lines` | `innerwork doctor --help` exit 0; the `examples:` block spans ≥2 lines each starting with `innerwork doctor` (regression for the formatter fix; the old run-on paragraph is gone). |
| `test_completion_bash_smoke` / `test_completion_zsh_smoke` / `test_completion_fish_smoke` | `innerwork completion <shell>` exit 0, stdout non-empty; bash contains `_innerwork` and `complete -F`; zsh starts with `#compdef innerwork`; fish contains `complete -c innerwork`. |
| `test_completion_unknown_shell_exit_2` | `innerwork completion powershell` → exit 2, stderr mentions `invalid choice` and the three valid shells, stdout empty. |
| `test_completion_missing_shell_exit_2` | `innerwork completion` (no arg) → exit 2, usage error on stderr. |
| `test_completion_hidden_from_top_level_help` | `innerwork --help` exit 0 and stdout does **not** contain `completion`; `innerwork completion --help` exit 0 (callable despite being hidden). |
| `test_completion_covers_all_subcommands` | Each shell script's stdout contains all 19 real subcommand names (derived from `build_parser()` in the test, so the expectation can never drift). |
| `test_completion_flag_lists_match_parser` | For each of the 5 migration commands (+ `doctor`): every flag string appearing in the completion script for that subcommand is in `build_parser()`'s option strings for that subparser, and every parser option string appears in the script (no invented, no missing). |
| `test_completion_scripts_are_static_text` | Each shell script contains none of: `eval`, `exec`, `$(`, backtick, `curl `, `wget `, `import `, `socket` (i.e. no code execution, no network, no interpreter spawn). |
| `test_completion_stdout_only` | `innerwork completion bash` writes nothing to stderr on success (script-friendly; matches the rest of the CLI). |
| `test_migration_guide_documents_best_effort` | `docs/migration-guide.md` §2.6 exists and contains the string `best-effort` (documentation-honesty regression; the roadmap item requires the scripts be documented as best-effort). |
| `test_existing_cli_suites_stay_green` | `tests/test_cli.py`, `tests/test_domain_cli.py`, `tests/test_doctor.py`, `tests/test_migration.py` pass **unmodified** (regression net). |

---

## §8 Anti-hallucination checklist

Implementation worker MUST run each check and quote the (empty / verified) output in the PR description.

| Check | Command |
|---|---|
| No invented flag anywhere | `uv run pytest tests/test_cli_ergonomics.py -k "example or parse" -q` passes (every example parses through the real parser). |
| No `--space` | `grep -RIn -- "--space" src/innerwork/ tests/test_cli_ergonomics.py` returns nothing. |
| Completion shells locked to 3 | `grep -n 'choices=("bash", "zsh", "fish")' src/innerwork/cli.py` present; `grep -RInE "powershell|nushell|tcsh|elvish" src/innerwork/completion.py src/innerwork/cli.py` returns nothing. |
| Word lists are parser-derived (no drift) | `grep -RInE "'export'|'import-markdown'|subcommand_words" src/innerwork/completion.py` shows derivation from `build_parser()`; `test_completion_flag_lists_match_parser` + `test_completion_covers_all_subcommands` pass. |
| Scripts are static text | `grep -RInE "\beval\b|\bexec\b|\$\(|`\|curl \|wget \|subprocess" src/innerwork/completion.py` returns nothing. |
| Stdlib only | `grep -RInE "^(import|from) " src/innerwork/completion.py` shows only stdlib modules (+ `from .cli import build_parser`). |
| No secrets/internal paths in help | `grep -RInE "/home/|/Users/|BEGIN .*PRIVATE|api[_-]?key|token" src/innerwork/cli.py` returns nothing (review any hit by hand). |
| No fabricated metrics | `grep -RInE "[0-9]+%|[0-9]+ ms|benchmark" docs/roadmap_cli_ergonomics_scoping.md docs/migration-guide.md CHANGELOG.md` — no performance/usage claims (or each hit is an explicitly labeled rule/threshold, not a measured claim). |
| Files-touched boundary | `git diff --stat main` shows exactly the §1 files. |
| Domain/schema code untouched | `git diff main -- src/innerwork/domain_store.py src/innerwork/portability.py src/innerwork/analytics.py src/innerwork/doctor.py` is empty. |
| Compliance | `uv run python scripts/check_anti_hallucination.py` exits 0. |

---

## §9 Acceptance gates (must hold before opening PR)

| Gate | Verification |
|---|---|
| Help examples | §7 matrix passes: every migration command's `--help` shows the locked `examples:` block; every example parses through the real parser (no invented flags); doctor's epilog renders as lines. |
| Completion | `innerwork completion bash|zsh|fish` each exit 0 with non-empty static stdout; hidden from `innerwork --help`; unknown/missing shell → exit 2; `test_completion_*` rows all pass. |
| Static-text security | `test_completion_scripts_are_static_text` passes; §8 greps empty and quoted in the PR. |
| Honest docs | migration-guide §2.6 documents the command, hiding mechanism, best-effort scope, install one-liners; §2 intro staleness fixed; CHANGELOG entry present. |
| Regression | `tests/test_doctor.py` (incl. `test_help_lists_doctor_with_example`) and all other suites pass unmodified. |
| CI parity | `uv run pytest -x`, `uv run ruff check .`, `uv run pyright` all green — exactly what `.github/workflows/ci.yml` runs. **Never push a branch with red pyright** (2026-05-29 phase-7 incident). |
| Compliance guardrail | `uv run python scripts/check_anti_hallucination.py` exits 0. |

---

## §10 Exit criteria (done definition for the implementation task)

Per the roadmap item and child task `t_75de6f68`:

1. `innerwork export|import|migrate|import-markdown|import-csv --help` each show at least one concrete, RUNNABLE usage example; the examples use only flags/subcommands that exist and paths that exist (or documented generic conventions).
2. Every example in help text is parse-validated by `test_every_help_example_parses_through_real_parser`; no `--space` or other fabricated flag anywhere; the task-body's hallucinated example is documented as rejected (§3).
3. `innerwork completion bash|zsh|fish` each emit a static completion script to stdout and exit 0; the subcommand is hidden from top-level help via `argparse.SUPPRESS` and documented in migration-guide §2.6; unknown/missing shell exits 2.
4. Completion scripts are static text — no network, no runtime dependencies, no eval/exec of user input — documented as best-effort (subcommands + long flags, not values/positionals); only bash/zsh/fish are claimed.
5. Stale/misleading help fixed: doctor's epilog renders on separate lines (formatter fix), migration-guide §2 intro no longer claims "three subcommands".
6. `tests/test_cli_ergonomics.py` green (parse-validity + completion smoke + static-text + regression rows); the full existing CLI suite stays green.
7. `uv run pytest -x && uv run ruff check . && uv run pyright` all green before push; `scripts/check_anti_hallucination.py` exits 0.
8. PR opened against `main` on `feat/cli-ergonomics`, **DO NOT MERGE** — end with `kanban_block(reason="qa-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")` per the child task's mandate.

---

## §11 Handoff checklist for the implementation worker (atlassianeng)

1. Branch from `main` at the current HEAD: `git checkout -b feat/cli-ergonomics` (child task `t_75de6f68` pins this branch name; worktree workspace at `/home/eml/atlassian/atlassian-innerwork`).
2. Write files in §1 order. The scoping doc (this file) is not modified.
3. Edit `src/innerwork/cli.py`: add `formatter_class=argparse.RawDescriptionHelpFormatter` + the locked §2 `epilog=` to the five migration subparsers, and the same formatter to `doctor` (its epilog stays as-is); register `completion` (`help=argparse.SUPPRESS`, positional `shell` with `choices=("bash", "zsh", "fish")`); add `_completion_dispatch` + the `main()` branch. Copy the epilog strings **verbatim** from §2 — do not "improve" flags.
4. Write `src/innerwork/completion.py` per §4: `completion_script(shell)` + `subcommand_words(parser)`, word lists derived from `build_parser()`, static templates per shell, stdlib only. No I/O in the module; no eval/exec/command-substitution in the emitted scripts.
5. Add `tests/test_cli_ergonomics.py` per §7 (all rows), including the parser-level parse-validity gate, the runnable-subset exit-0 runs against `tmp_path`, the completion smoke/static/hidden tests, and the parser-matching flag tests.
6. Update `docs/migration-guide.md` (§2.6 + §2 intro fix), `CHANGELOG.md` (`### Added — CLI ergonomics (help examples + shell completion)`); optionally move the roadmap bullets (§1 row 8).
7. Run the CI-parity gate exactly as GitHub Actions does: `uv run pytest -x`, `uv run ruff check .`, `uv run pyright`. **All three must be green before push.**
8. Run the §8 grep checks and quote results in the PR body.
9. Push via SSH remote (`git@github-personal:m0n3r0/atlassian-innerwork.git`), open PR titled `feat(cli): friendlier --help examples + hidden shell completion (bash/zsh/fish)` against `main`. **DO NOT MERGE.**
10. `kanban_block(reason="qa-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")`.
