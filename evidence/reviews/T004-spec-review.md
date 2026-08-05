# T004 Spec Review

Status: passed.

## Scope Checked

- String enums are defined for action types, tool status, feedback kind/severity, event types,
  stable error codes, and trust levels.
- `EvidenceRef`, `AgentAction`, `ToolResult`, and `FeedbackSignal` exist.
- Unknown actions, extra fields, and invalid enum values are rejected by Pydantic validation.
- JSON Schema snapshots are generated for AgentAction and ToolResult.
- EvidenceRef, ToolResult, FeedbackSignal, and StableError round-trip behavior is tested.
- All six AgentAction variants are tested.
- Snapshot drift is tested by comparing a modified schema against the checked-in snapshot.
- Frontend ActionType and TrustLevel mirrors are checked against backend enum values.
- Provider model names are not introduced into domain enums or migrations.

## Result

T004 satisfies the shared contract freeze scope for downstream worktrees.
