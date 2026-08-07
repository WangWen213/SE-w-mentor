# P0 Decisions

Status: frozen for P0 unless the change process in this file is followed.

## Global Frozen Decisions

- Product name: `SE-Mentor`.
- Python package name: `se_mentor`.
- Repository, CLI, and Docker service name: `se-mentor`.
- Deprecated spelling: `sementor`; do not introduce it in new code, docs, migration IDs, or service names.
- T002, T003, T007, and T008 are covered by a one-time Bootstrap TDD exception.
- From T000 onward, new implementation work must follow strict red-green TDD.
- T009 and later feature work is paused until T000-T008 satisfy strict DoD and T114 first
  cold-start PASS is recorded.

## Bootstrap TDD exception

T002, T003, T007, and T008 received scaffold implementation before strict red-green TDD evidence.
This exception is one-time and cannot be reused for later Tasks. Do not fabricate red evidence.
Already-green tests must be recorded as `PRE_EXISTING_GREEN`; real failures must be preserved as
red evidence.

## Change Process For P0 Decisions

1. Open a decision-change proposal that names the affected OQ IDs.
2. Add or update failing document/contract tests that capture the proposed new rule.
3. Update this file, `docs/TRACEABILITY_MATRIX.md`, and affected evidence paths.
4. Run Spec Compliance Review and Code Quality Review.
5. Commit the accepted change with evidence.

## OQ Decisions

### OQ-01: P0 OpenAI model selection

- **Final decision**: Use configurable Responses API models: default `gpt-5.6-terra`, high-complexity `gpt-5.6-sol`, and fast low-cost `gpt-5.6-luna`.
- **Decision rationale**: Model availability and cost can change, so model names belong in provider configuration rather than domain logic.
- **Impact modules**: `llm`, `config`, `tests`, provider adapters.
- **P0 acceptance rule**: Domain enums, migrations, and core Agent orchestration do not hard-code provider model names; unit tests use Mock Provider.
- **Change process**: Update provider defaults and config tests through the P0 decision-change process.
- **Current status**: FROZEN.
- **External dependencies**: OpenAI Responses API availability and configured API credentials.

### OQ-02: P0 supported project languages

- **Final decision**: P0 primarily supports Python repositories and uses TypeScript support for SE-Mentor frontend and lightweight project detection.
- **Decision rationale**: Python-first scope keeps indexing, validation, and repair behavior achievable within P0.
- **Impact modules**: project registration, language detection, indexing, validation planning, documentation.
- **P0 acceptance rule**: Python projects receive full P0 path; non-Python projects are allowed only when operations remain language-agnostic or explicitly marked limited.
- **Change process**: Expanding first-class language support requires new index, validation, and E2E evidence.
- **Current status**: FROZEN.
- **External dependencies**: Local Python and optional Node/npm toolchains.

### OQ-03: P0 repository scale

- **Final decision**: Enforce explicit file count, file size, output size, and token budget limits before indexing or LLM calls.
- **Decision rationale**: Bounded local execution avoids resource exhaustion and unreviewable context packages.
- **Impact modules**: project scanning, context manager, code index, shell/tool output capture, configuration.
- **P0 acceptance rule**: Oversized repositories or outputs pause with actionable diagnostics instead of silently truncating critical evidence.
- **Change process**: Limit changes require performance evidence and config version update.
- **Current status**: FROZEN.
- **External dependencies**: Host disk, memory, and configured budget limits.

### OQ-04: Shell command boundary

- **Final decision**: P0 allows only program-plus-argument commands or predefined command templates; arbitrary shell strings are not a trusted tool interface.
- **Decision rationale**: Argument-array execution is auditable and reduces injection and path-escape risk.
- **Impact modules**: shell tool, governance, policy enforcer, validation adapters, audit logging.
- **P0 acceptance rule**: Dangerous shell features are blocked or require explicit approval; command, args, cwd, env, timeout, and policy result are logged.
- **Change process**: Any broader shell capability requires security review, new BLOCK/WARN tests, and updated governance rules.
- **Current status**: FROZEN.
- **External dependencies**: OS shell behavior and installed project tools.

### OQ-05: Agent test modification policy

- **Final decision**: Agent modifications to tests require approval unless the task explicitly asks for test changes or the change is a narrow approved fixture update.
- **Decision rationale**: Silent test weakening can invalidate validation evidence.
- **Impact modules**: governance, patch tool, validation, approval, audit.
- **P0 acceptance rule**: Test-file writes are classified separately and cannot be used to bypass failing product code validation.
- **Change process**: Relaxing the policy requires governance review and validation-evasion tests.
- **Current status**: FROZEN.
- **External dependencies**: Project test layout detection.

### OQ-06: Failed-task change retention

- **Final decision**: Successful in-scope modifications are retained; failed or canceled tasks keep recoverable transaction state and may roll back only through explicit policy or user request.
- **Decision rationale**: Users need inspectable diffs while still having recovery guarantees.
- **Impact modules**: transaction manager, backup manager, rollback API, WebUI diff, audit.
- **P0 acceptance rule**: Every write task has backups, file-change records, and a clear final transaction state.
- **Change process**: Retention behavior changes require transaction and recovery E2E updates.
- **Current status**: FROZEN.
- **External dependencies**: Filesystem write permissions and available backup storage.

### OQ-07: Knowledge VERIFIED conditions

- **Final decision**: Engineering knowledge may become VERIFIED only when supported by code evidence plus passing validation, or explicit human review.
- **Decision rationale**: Memory that is promoted too easily pollutes later impact analysis.
- **Impact modules**: knowledge repository, freshness checker, validation, audit.
- **P0 acceptance rule**: Knowledge records preserve source evidence, confidence, freshness state, and invalidation rules.
- **Change process**: New promotion paths require tests for stale, conflicting, and unsupported knowledge.
- **Current status**: FROZEN.
- **External dependencies**: Availability of repository evidence, validation results, or reviewer decision.

### OQ-08: P0 identity system

- **Final decision**: Local P0 does not implement a multi-user identity system; cloud demo uses only basic access restrictions.
- **Decision rationale**: Full identity management is outside P0 and would distract from harness governance.
- **Impact modules**: WebUI, deployment, audit actor fields, approval UI.
- **P0 acceptance rule**: Local actions may use system/user labels, and public demo access must prevent arbitrary unauthenticated use.
- **Change process**: Multi-user auth moves to post-P0 architecture review.
- **Current status**: FROZEN.
- **External dependencies**: Deployment ingress and access-control configuration.

### OQ-09: Public demo LLM usage

- **Final decision**: CLOUD_DEMO uses Mock Provider by default and does not expose real LLM calls.
- **Decision rationale**: Public real LLM access creates cost, data, and abuse risks.
- **Impact modules**: config profiles, LLM provider, cloud deployment, demo data.
- **P0 acceptance rule**: CLOUD_DEMO rejects real provider configuration unless a later approved decision explicitly changes this rule.
- **Change process**: Enabling real LLM in demo requires cost controls, data controls, abuse controls, and deployment review.
- **Current status**: FROZEN.
- **External dependencies**: Cloud deployment profile and demo environment variables.

### OQ-10: Public demo data reset

- **Final decision**: Public demo data is reset per task or at least daily, with no user-supplied repository persistence.
- **Decision rationale**: Resetting reduces data retention and abuse impact.
- **Impact modules**: cloud storage, task cleanup, audit retention, deployment operations.
- **P0 acceptance rule**: Demo state has automated cleanup and no durable real-user repository data.
- **Change process**: Longer retention requires documented privacy and storage review.
- **Current status**: FROZEN.
- **External dependencies**: Cloud scheduler or service startup cleanup.

### OQ-11: Local network access

- **Final decision**: LOCAL_FULL allows network only for approved providers and explicitly approved dependency/tool operations; CLOUD_DEMO blocks arbitrary outbound network use.
- **Decision rationale**: Network access is high-risk and must be tied to purpose and profile.
- **Impact modules**: shell policy, provider adapters, dependency installation, deployment profile, audit.
- **P0 acceptance rule**: Network use is governed, logged, and never silently inherited by project subprocesses.
- **Change process**: New network categories require governance rule and profile updates.
- **Current status**: FROZEN.
- **External dependencies**: Host firewall, package registries, provider endpoints.

### OQ-12: Windows keyring failure

- **Final decision**: If OS credential storage fails, P0 permits session-only credentials and forbids plaintext persistence.
- **Decision rationale**: A failed credential backend must degrade safely rather than leak secrets.
- **Impact modules**: credential service, process env filtering, redaction, settings UI.
- **P0 acceptance rule**: API keys never enter SQLite, logs, prompts, child environments, or committed files.
- **Change process**: Alternative storage requires security review and leak tests.
- **Current status**: FROZEN.
- **External dependencies**: Windows Credential Manager or equivalent OS keyring.

### OQ-13: Semantic progress measurement

- **Final decision**: P0 uses deterministic progress rules; semantic similarity scoring is P1.
- **Decision rationale**: Rule-based progress is testable offline and avoids model-dependent completion claims.
- **Impact modules**: progress monitor, stop policy, feedback controller, task timeline.
- **P0 acceptance rule**: Repeated non-progress actions trigger replanning, pause, or budget stop using deterministic evidence.
- **Change process**: Model-based scoring requires new metrics, fixtures, and E2E acceptance.
- **Current status**: FROZEN.
- **External dependencies**: None for P0 beyond recorded action and validation data.

### OQ-14: Automatic dependency installation

- **Final decision**: Dependency installation is WARN and requires approval unless already authorized by local policy.
- **Decision rationale**: Installation changes host state and may execute untrusted package code.
- **Impact modules**: shell tool, dependency detection, approval, audit, onboarding docs.
- **P0 acceptance rule**: Dependency install commands are visible, approved, logged, and never run silently.
- **Change process**: Policy relaxation requires supply-chain risk review.
- **Current status**: FROZEN.
- **External dependencies**: Package indexes, network access, and host permissions.

### OQ-15: Automatic Git commit

- **Final decision**: P0 does not automatically commit task changes unless the user explicitly asks for a commit.
- **Decision rationale**: Commits are project history changes and require user intent.
- **Impact modules**: Git tool, completion gate, audit, documentation.
- **P0 acceptance rule**: Git writes are gated separately from file writes and recorded with command evidence.
- **Change process**: Any automatic commit flow requires explicit product decision and E2E coverage.
- **Current status**: FROZEN.
- **External dependencies**: Git installation and repository state.

### OQ-16: Dirty worktree support

- **Final decision**: P0 must support pre-existing user changes and protect them from rollback or overwrite.
- **Decision rationale**: Real repositories are often dirty, and the agent must not destroy user work.
- **Impact modules**: Git baseline, transaction manager, patch tool, rollback, diff UI.
- **P0 acceptance rule**: Baseline diff is recorded before writes; rollback only reverts task-owned changes.
- **Change process**: Any ownership-rule change requires dirty-worktree E2E tests.
- **Current status**: FROZEN.
- **External dependencies**: Git status availability or filesystem fallback.

### OQ-17: Missing validation tools

- **Final decision**: A task cannot be marked complete when required validators are missing; result is INCONCLUSIVE or PAUSED.
- **Decision rationale**: Completion without necessary validation is misleading.
- **Impact modules**: validation planner, completion gate, WebUI status, feedback controller.
- **P0 acceptance rule**: Missing required validators produce actionable diagnostics and block `[x]` task completion.
- **Change process**: Validator downgrade rules require acceptance criteria updates.
- **Current status**: FROZEN.
- **External dependencies**: Project toolchain installation.

### OQ-18: Vector database need

- **Final decision**: P0 does not require a vector database; deterministic relational/file-based retrieval is sufficient.
- **Decision rationale**: P0 focuses on governance and traceable evidence, not semantic memory scale.
- **Impact modules**: knowledge repository, retrieval, deployment, dependencies.
- **P0 acceptance rule**: Knowledge retrieval remains deterministic and explainable without external vector services.
- **Change process**: Vector storage is P1 and requires migration, cost, and retrieval-quality review.
- **Current status**: FROZEN.
- **External dependencies**: None for P0.

### OQ-19: Aliyun deployment shape

- **Final decision**: P0 cloud demo uses a single ECS instance and single service/container shape.
- **Decision rationale**: Single-instance deployment keeps operations and cost manageable.
- **Impact modules**: Docker, deployment scripts, persistence, Nginx, CI/CD.
- **P0 acceptance rule**: CLOUD_DEMO runs under a constrained profile and does not require distributed coordination.
- **Change process**: Multi-instance design requires architecture review and database/storage redesign.
- **Current status**: FROZEN.
- **External dependencies**: Aliyun ECS, ACR, DNS/HTTPS if enabled.

### OQ-20: Public demo repository uploads

- **Final decision**: P0 public demo does not allow users to upload arbitrary repositories.
- **Decision rationale**: Arbitrary repository upload would expose code, storage, execution, and abuse risks.
- **Impact modules**: WebUI, project registration, cloud demo profile, shell policy, storage cleanup.
- **P0 acceptance rule**: CLOUD_DEMO uses curated demo repositories or synthetic fixtures only.
- **Change process**: User uploads require separate security, privacy, sandbox, and cost review.
- **Current status**: FROZEN.
- **External dependencies**: Demo fixture hosting and deployment configuration.
