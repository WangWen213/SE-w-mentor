# Data Retention

Phase 1 data model retention keeps audit, governance, and decision traceability intact while
allowing runtime artifacts to be pruned through controlled artifact references.

## Core History

The following tables are core history and must not be physically deleted by normal cleanup:

- `audit_events`
- `governance_decisions`
- `governance_rule_hits`
- `approval_requests`
- `approval_decisions`
- `execution_policies`
- `task_transactions`
- `validation_plans`
- `validation_runs`
- `engineering_knowledge`
- `knowledge_relations`

`audit_events` are append-only. Updates and deletes are rejected by database triggers in the P0
SQLite runtime.

## Runtime Artifacts

Large runtime outputs stay outside the database behind controlled artifact references. Cleanup may
remove expired artifact files only when doing so does not break core history or evidence references.

Cleanup-eligible examples:

- validation log artifacts
- backup artifact files after their task and retention window are closed
- temporary tool output artifacts
- code index rebuild scratch files

The database stores summaries and artifact references, not raw prompts, secrets, complete source
dumps, unbounded logs, or backup file contents.

## Traceability Rule

Retention must not break audit, governance, approval, execution, validation, or knowledge
traceability. If an artifact is removed, the retention job must keep enough metadata to explain why
the artifact was eligible for cleanup and which immutable history row referenced it.
