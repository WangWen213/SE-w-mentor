# T003 Spec Compliance Review

Status: partial, remains `[-]`.

Reviewed against T003 scope:

- Local quality entry point exists in `scripts/check_all.py`.
- Python checks use the current interpreter via `sys.executable`.
- Frontend checks run from `frontend/` and use `npm.cmd` on Windows.
- Child command failures propagate their non-zero exit code.
- Missing Python tooling reports `QUALITY_ENV_MISSING_PYTHON_TOOL`, current interpreter, expected
  project interpreter, and the canonical command.
- README and PREP_STATUS document the canonical command.
- External ordinary non-admin Vitest and Vite build results are recorded as user-executed evidence.

Remaining gap:

- Full canonical `.\backend\.venv\Scripts\python.exe scripts\check_all.py` still needs an external
  ordinary non-admin run recorded before T003 can be marked `[x]`.
