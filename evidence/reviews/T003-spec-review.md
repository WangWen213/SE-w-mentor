# T003 Spec Compliance Review

Status: pass.

Reviewed against T003 scope:

- Local quality entry point exists in `scripts/check_all.py`.
- Python checks use the current interpreter via `sys.executable`.
- Frontend checks run from `frontend/` and use `npm.cmd` on Windows.
- Child command failures propagate their non-zero exit code.
- Missing Python tooling reports `QUALITY_ENV_MISSING_PYTHON_TOOL`, current interpreter, expected
  project interpreter, and the canonical command.
- README and PREP_STATUS document the canonical command.
- External ordinary non-admin Vitest and Vite build results are recorded as user-executed evidence.
- External ordinary non-admin canonical `check_all.py` result is recorded and passed.

Final conclusion:

- Repository quality gate: PASS.
- External ordinary-user execution: PASS.
- Codex sandbox native-child execution: environment-specific limitation.
- Repository defect: NOT PRESENT.
- Privilege escalation: NOT REQUIRED.

DoD confirmed:

1. format command passes.
2. Ruff passes.
3. mypy passes.
4. pytest passes.
5. frontend type-check passes.
6. frontend Vitest passes.
7. `check_all.py` uses `sys.executable`.
8. frontend cwd is explicit.
9. Windows uses `npm.cmd`.
10. child step failure propagates a non-zero exit code.
11. missing Python tooling has actionable preflight output.
12. canonical command passes in an ordinary user environment.

The existing `StarletteDeprecationWarning` is a third-party dependency warning and is not a T003
blocker.
