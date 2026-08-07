# T012 Spec Review

Status: PASS.

## Requirement Source

- Plan: `SE-Mentor_PLAN_v2_NO_REVIEW_CLOSURE.md`, T012 impact analysis and governance domain data
  model.
- Spec: governance persistence requirements covering impact reports, decisions, rules, rule hits,
  `FR-04`, and `FR-06`.
- Migration policy: `docs/MIGRATION_POLICY.md`.
- User instruction: complete only T012 after confirming/pushing T011; do not start T013+.

## ImpactReport

- Bound to task: yes, required `task_id`.
- Bound to proposal: yes, required `proposal_id`.
- Revision context: yes, optional `base_revision`.
- Impact categories: yes, direct impacts are required; indirect, API, database, test, deployment,
  and uncertainty summaries are persisted as optional JSON text.
- Evidence: yes, required bounded evidence JSON reference field.
- Lifecycle: yes, DB-constrained `CURRENT`/`STALE`/`SUPERSEDED` status.

## GovernanceDecision

- Bound to task: yes, required `task_id`.
- Bound to action: yes, optional `action_id`.
- Bound to impact report: yes, optional `impact_report_id`.
- Proposal identity: yes, required 64-character `proposal_hash`.
- Revision identity: yes, required non-empty `revision`.
- Decision values: yes, DB-constrained `ALLOW`/`WARN`/`BLOCK`.
- Risk level: yes, reused DB-constrained `RiskLevel`.
- Evidence: yes, required evidence JSON.
- Rule set: yes, required `rule_set_version`.
- Lifecycle: yes, DB-constrained `ACTIVE`/`EXPIRED`/`SUPERSEDED`.

## GovernanceRule

- Rule identity: yes, stable `rule_key` plus unique `(rule_key, rule_version)`.
- Version: yes, positive integer `rule_version`.
- Scope: yes, DB-constrained `SYSTEM`/`PROJECT`/`TASK`; optional project FK.
- Effect: yes, DB-constrained `DENY_HARD`/`REQUIRE_APPROVAL`/`ALLOW`.
- Priority: yes, required non-negative integer.
- Patterns and conditions: yes, separate required JSON text fields.
- Override policy: yes, `DENY_HARD` cannot be overridable.

## GovernanceRuleHit

- Decision binding: yes, required decision FK.
- Exact rule-version binding: yes, composite FK from `(rule_id, rule_version)` to
  `governance_rules`.
- Nonexistent rule rejection: yes, covered by FK test.
- Duplicate hit prevention: yes, unique `(decision_id, rule_id, rule_version)`.
- Evidence: yes, required matched evidence JSON.

## Migration

- Revision: `0040_governance`.
- Down revision: `0030_llm_action`.
- Upgrade: PASS.
- Downgrade: PASS.
- Re-upgrade: PASS.
- Single head: PASS.

## Scope

T013 NOT STARTED.
