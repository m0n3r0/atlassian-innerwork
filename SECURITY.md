# Security Policy

## Supported Versions

`atlassian-innerwork` is currently pre-1.0. Until the first stable tag (`v1.0.0`), only the latest commit on `main` and the most recent `0.x` tag (when one exists) receive security attention. There is no service-level agreement on response or patch time.

| Version          | Supported |
|------------------|-----------|
| `0.x` (latest)   | ✅        |
| older `0.x`      | ❌        |

A formal supported-versions table will appear after the first stable release.

## Reporting a Vulnerability

**Please do not file a public issue or pull request for security bugs.** Use **GitHub's private vulnerability reporting** mechanism on this repository:

1. Open the **Security** tab on <https://github.com/m0n3r0/atlassian-innerwork>.
2. Click **Report a vulnerability**.
3. Fill in a clear, minimal reproduction. Include:
   - the affected file and (where possible) commit SHA,
   - steps to reproduce or a short proof-of-concept,
   - what the issue lets an attacker do (impact),
   - any suggested fix you already have in mind.

The maintainers will acknowledge receipt on a best-effort basis. There is no published response SLA.

## What this project does NOT operate

To set honest expectations:

- **No `security@` email address.** All reports go through GitHub private vulnerability reporting.
- **No PGP key** for encrypted email.
- **No bug bounty program.** Reports are accepted gratefully, but there is no monetary reward.
- **No formal embargo policy.** The maintainers will coordinate disclosure on a best-effort basis with the reporter; in general, fixes ship on `main` and the reporter is credited in the release notes unless they ask to remain anonymous.

## Threat model

The project's threat model and the security-sensitive behaviors of the runtime (audit log, field-level ACL, fail-closed validation) are documented in [`docs/threat-model.md`](docs/threat-model.md). Reporters are encouraged to skim it; many "issues" that look like vulnerabilities are documented design choices (e.g. the broker refuses to persist invalid intent rather than partially accepting it).

## Scope

In scope:

- Code under `src/innerwork/`.
- The packaged wheel and sdist produced from this repository.
- Sample configuration in `examples/`.

Out of scope:

- The reference Docker images you build locally from `Dockerfile` / `docker-compose.yml` — these are explicitly demos and have no hardening guarantees.
- Third-party dependencies (report upstream; the maintainers will track once the upstream fix lands).
- Issues that require an attacker who already has shell access on the host.
