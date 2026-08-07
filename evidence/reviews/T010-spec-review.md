# T010 Spec Review

Status: PASS.

## Requirement Source

- Plan: `SE-Mentor_PLAN_v2_NO_REVIEW_CLOSURE.md`, T010 task-domain data model.
- Spec: `SPEC.问题陈述.md`, sections 6.6 and 6.15.
- Migration policy: `docs/MIGRATION_POLICY.md`.
- User instruction: start and complete only T010, do not start T011+.

## Coverage

- `ChangeTask`: project FK, original request, base revision/hash, frozen task status values,
  active reference fields, counters, lifecycle timestamps, failure fields, optimistic version, and
  DB constraints.
- `ChangeProposal`: task FK, positive version, structured JSON text fields, completeness/status
  enums, creator type enum, supersedes relation, and unique `(task_id, version)` index.
- `TaskIteration`: task FK, positive iteration number, phase/result enums, token count metadata,
  timestamps, progress score, and unique `(task_id, iteration_number)` index.
- Relationships: `Project -> ChangeTask`, `ChangeTask -> ChangeProposal`,
  `ChangeTask -> TaskIteration`, and `ChangeProposal -> supersedes ChangeProposal`.
- Migration: `0020_task_domain` revises `0010_project_domain` and preserves one Alembic head.

## Scope Controls

No task service, repository abstraction, REST API, CLI, agent loop, planner/executor/reviewer,
approval workflow, patch generation, test orchestration, memory retrieval, risk evaluation, or LLM
integration was added.

## Deferred By Design

- Automatic proposal confirmation/superseding is a workflow/service responsibility.
- Single current confirmed proposal and one unfinished iteration are future workflow invariants not
  enforced here because T010 is persistence-only and the user asked not to invent workflow logic.
- `active_proposal_id`, `active_policy_id`, `workspace_lock_id`, and `transaction_id` remain stored
  references until their owner domains land.

## Result

T010 persistence requirements are covered without starting T011.
