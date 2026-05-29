# Atlassian Innerwork — Threat Model

> **Status:** Phase 7 trust hardening, additive-only. This document explicitly
> does **not** claim conformance with SOC 2, ISO 27001, HIPAA, GDPR, PCI-DSS,
> FedRAMP, CCPA, or any other external compliance framework. References to
> those frameworks below appear only to clarify what this project does *not*
> certify. The anti-hallucination guardrail (`scripts/check_anti_hallucination.py`)
> allowlists this file precisely so the disclaimers above can be written.

## 1. Scope

In scope:

- The Innerwork work-graph SQLite store (`domain_store.py`).
- Notification dispatch (`notify.py`) — `mention` surface only.
- Portability export/import (`portability.py`).
- Phase 7 additions: append-only audit log (`audit.py`), field-level ACL
  (`field_acl.py`), backup/restore scripts.

Out of scope (currently):

- Network transport security; the store is in-process and assumes a trusted
  host.
- Multi-tenant isolation. The current store is single-tenant per file.
- Identity providers / SSO / token rotation.

## 2. Assets

| ID | Asset | Sensitivity |
|----|----|----|
| A1 | Work item content (titles, descriptions, comments) | medium |
| A2 | Page content (versions, comments) | medium |
| A3 | User PII (handles, display names, email-shaped identifiers) | high |
| A4 | Audit log rows | high (integrity) |
| A5 | Portability snapshots | high (full content + PII) |

## 3. Trust boundaries

```
+--- operator host -----------------------------+
|                                               |
|  +-- innerwork process ---------------------+ |
|  |                                          | |
|  |  DomainStore  ----+                      | |
|  |  Notifier     ----+--> AuditSink (file)  | |
|  |  Portability  ----+                      | |
|  |                                          | |
|  +------------------------------------------+ |
|                                               |
|  SQLite files (domain.db, audit.db, ...)      |
+-----------------------------------------------+
```

The trust boundary is the **operator host filesystem**. All audit, domain,
and portability data is at rest on local SQLite files; encryption-at-rest
is the operator's responsibility (e.g., LUKS, FileVault, SED) — the project
does not encrypt files itself.

## 4. STRIDE-lite mitigation matrix

Mitigation status legend: **planned** (designed, not yet wired), **partial**
(wired for one or more surfaces but not all), **implemented** (fully wired
and exercised by tests).

| Threat | Surface | Mitigation | Status |
|----|----|----|----|
| **S**poofing of actor identity | audit log entries | `actor` string + `actor_kind` enum stored with every event; operator wires upstream identity | partial |
| **T**ampering with audit log | audit DB | append-only triggers (`RAISE(ABORT)`) on UPDATE/DELETE; documented as soft guard, not a security boundary (DBA can drop triggers) | implemented |
| **T**ampering with domain DB | sqlite files | filesystem permissions (operator); `chmod 0o600` on backup output | partial |
| **R**epudiation | audit log | append-only event log covers `jira_workflow`, `confluence_page`, `mention`, `permission_change`, `portability_export`, `portability_import` surfaces | partial (permission_change wiring deferred) |
| **I**nformation disclosure (PII in exports) | portability export | `field_acl.py` `redact_for` helper + `PRIVACY_FIELDS` constant for downstream serializers | partial (operator must invoke) |
| **I**nformation disclosure (reads) | audit log | read events deliberately NOT logged (cost/noise tradeoff) | by design |
| **D**enial of service | notify rate limiter | per-user token bucket already in `notify.py` | implemented |
| **E**levation of privilege | field ACL | flat policy table + `system` actor bypass; default-allow when no policy registered | partial |

## 5. Known gaps

These are gaps documented for honesty; they are not silent omissions.

- **`permissions.grant` / `permissions.revoke` helpers do not exist** in the
  current codebase. The audit `permission_change` surface is reserved in
  the schema/enum but not yet wired. When the helpers land, they must call
  `store._audit(surface="permission_change", ...)` at the point where the
  permission row is mutated.
- **`knowledge.publish_version` does not exist** as a separate helper; page
  version audit is wired directly at `create_page` / `update_page`.
- **`notify.notify_mention` does not exist**; mention audit is wired in
  `Notifier.dispatch` at the per-recipient delivery point.
- **Append-only triggers are not a security boundary.** A DBA with write
  access can drop the triggers or rewrite rows. They prevent *application
  bugs* from rewriting history. For forensic-grade non-repudiation, an
  external WORM store (e.g., S3 Object Lock) is required.
- **Backup/restore scripts do not verify integrity** beyond what SQLite's
  page checksums provide. No HMAC, no signed manifest.
- **Field ACL is best-effort serialization redaction**, not a kernel-level
  access control. Code paths that bypass `redact_for` see raw values.

## 6. Operator responsibilities

The project ships primitives. The operator must:

1. Wire `DomainStore.audit_sink` and `Notifier.audit_sink` to a real
   `SqliteAuditSink` (or compatible sink) before production traffic.
2. Set restrictive filesystem permissions on the audit DB.
3. Run `scripts/backup.py` on a schedule and store output off-host.
4. Run `scripts/check_anti_hallucination.py` in CI to catch accidental
   compliance claims in docs.
5. Decide what constitutes `PRIVACY_FIELDS` for their deployment and wire
   `FieldACL.redact_for` into any serializer that crosses a trust boundary.

## 7. What we explicitly do NOT promise

- Conformance with SOC 2, ISO 27001, HIPAA, GDPR, PCI-DSS, FedRAMP, CCPA,
  or any other framework. The terms appear above only to make the negative
  claim explicit.
- Encryption at rest or in transit.
- Cryptographic non-repudiation.
- Multi-tenant isolation.
- Forensic chain-of-custody.

If a downstream system needs any of those properties, it must add them on
top of the primitives this project provides.
