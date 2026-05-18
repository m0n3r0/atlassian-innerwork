# Atlassian Innerwork Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Grow the reference design into a production-grade self-service edge platform.

**Architecture:** Start from an executable broker/control-plane nucleus, then add real API contracts, durable state, queue workers, xDS rendering, progressive rollout, sidecars, infrastructure automation, and operations evidence.

**Tech Stack:** Python/FastAPI or Rust for broker and sidecars, Postgres/DynamoDB-style durable state, queue workers, Envoy xDS, Packer, Terraform/CloudFormation, CI, OpenAPI.

---

## Task 1: Stabilize API schema

**Objective:** Make `EdgeService` a versioned contract with CI validation.

**Files:**

- Modify: `spec/openapi.yaml`
- Create: `src/innerwork/schema.py`
- Test: `tests/test_schema.py`

**Steps:**

1. Add failing tests for valid and invalid edge-service specs.
2. Implement schema validation.
3. Ensure duplicate domains and invalid prefixes fail with actionable errors.
4. Run `uvx pytest -q`.

## Task 2: Add durable operation state

**Objective:** Replace in-memory operation state with a repository abstraction.

**Files:**

- Create: `src/innerwork/store.py`
- Modify: `src/innerwork/broker.py`
- Test: `tests/test_store.py`

**Steps:**

1. Add failing tests for restart-safe operation lookup.
2. Implement repository interface and SQLite adapter.
3. Preserve current broker behavior.
4. Run `uvx pytest -q`.

## Task 3: Add real xDS validation fixture

**Objective:** Prove rendered resources can be accepted by Envoy tooling.

**Files:**

- Create: `src/innerwork/xds.py`
- Create: `tests/fixtures/envoy-bootstrap.yaml`
- Test: `tests/test_xds_rendering.py`

**Steps:**

1. Add failing snapshot serialization tests.
2. Implement typed resource rendering.
3. Add optional Envoy binary validation command.
4. Run unit tests and document Envoy validation setup.

## Task 4: Add rollout model

**Objective:** Gate snapshot publication by region/fleet health.

**Files:**

- Create: `src/innerwork/rollout.py`
- Test: `tests/test_rollout.py`

**Steps:**

1. Add failing tests for canary stop and rollback.
2. Implement rollout state transitions.
3. Add health gate inputs for NACKs, 5xx, latency, and sidecar failures.
4. Run `uvx pytest -q`.

## Task 5: Add sidecar contracts

**Objective:** Define local authn/authz/rate-limit sidecar APIs.

**Files:**

- Create: `spec/sidecar-auth.yaml`
- Create: `spec/sidecar-ratelimit.yaml`
- Test: contract examples under `tests/contracts/`

**Steps:**

1. Write contract examples first.
2. Define request/response schemas.
3. Document fail-open/fail-closed semantics.
4. Add runbook entries for sidecar outages.

## Task 6: Add infrastructure blueprint

**Objective:** Provide deployable-but-safe IaC skeletons.

**Files:**

- Create: `infra/terraform/README.md`
- Create: `infra/packer/README.md`

**Steps:**

1. Document required cloud resources.
2. Add variable contracts and security constraints.
3. Do not add live credentials or provider-specific secrets.
4. Add CI checks for formatting once real IaC exists.
