# Traceability Matrix

Status: T001 strict DoD candidate. This matrix freezes the required columns and maps all P0 US,
FR, NFR, and AC families to a primary Task, test location, and evidence location.

| requirement | priority | task | test | evidence | status |
| --- | --- | --- | --- | --- | --- |
| US-01 | P0 | T025 | `backend/tests/proposals/test_change_proposal.py` | `evidence/tdd/T025.md` | planned |
| US-02 | P0 | T043 | `backend/tests/impact/test_impact_report.py` | `evidence/tdd/T043.md` | planned |
| US-03 | P0 | T046 | `backend/tests/governance/test_decisions.py` | `evidence/tdd/T046.md` | planned |
| US-04 | P0 | T059 | `backend/tests/tools/test_apply_patch.py` | `evidence/tdd/T059.md` | planned |
| US-05 | P0 | T078 | `backend/tests/validation/test_completion_gate.py` | `evidence/tdd/T078.md` | planned |
| US-06 | P0 | T079 | `backend/tests/knowledge/test_success_update.py` | `evidence/tdd/T079.md` | planned |
| FR-01 | P0 | T019 | `backend/tests/projects/test_registration.py` | `evidence/tdd/T019.md` | planned |
| FR-02 | P0 | T024 | `backend/tests/tasks/test_task_state.py` | `evidence/tdd/T024.md` | planned |
| FR-03 | P0 | T033 | `backend/tests/context/test_context_package.py` | `evidence/tdd/T033.md` | planned |
| FR-04 | P0 | T035 | `backend/tests/knowledge/test_retrieval.py` | `evidence/tdd/T035.md` | planned |
| FR-05 | P0 | T066 | `backend/tests/agent/test_orchestrator.py` | `evidence/tdd/T066.md` | planned |
| FR-06 | P0 | T044 | `backend/tests/governance/test_rules.py` | `evidence/tdd/T044.md` | planned |
| FR-07 | P0 | T057 | `backend/tests/tools/test_dispatcher.py` | `evidence/tdd/T057.md` | planned |
| FR-08 | P0 | T070 | `backend/tests/validation/test_plan.py` | `evidence/tdd/T070.md` | planned |
| FR-09 | P0 | T080 | `backend/tests/knowledge/test_failure_update.py` | `evidence/tdd/T080.md` | planned |
| FR-10 | P0 | T094 | `frontend/src/tasks/task-pages.test.tsx` | `evidence/tdd/T094.md` | planned |
| FR-11 | P0 | T092 | `backend/tests/audit/test_replay.py` | `evidence/tdd/T092.md` | planned |
| FR-12 | P0 | T081 | `backend/tests/e2e/test_offline_loop.py` | `evidence/tdd/T081.md` | planned |
| NFR-PERF | P0 | T102 | `tests/performance/test_resource_limits.py` | `evidence/tdd/T102.md` | planned |
| NFR-SEC | P0 | T006 | `backend/tests/security/test_secret_boundary.py` | `evidence/tdd/T006.md` | planned |
| NFR-CRED | P0 | T104 | `backend/tests/security/test_windows_credential_manager.py` | `evidence/tdd/T104.md` | planned |
| NFR-USA | P0 | T099 | `frontend/src/a11y/a11y.test.tsx` | `evidence/tdd/T099.md` | planned |
| NFR-OBS | P0 | T100 | `backend/tests/observability/test_logging.py` | `evidence/tdd/T100.md` | planned |
| AC-FR | P0 | T115 | `tests/meta/test_acceptance_report.py` | `evidence/tdd/T115.md` | planned |
| AC-PERF | P0 | T103 | `tests/performance/test_degraded_dependencies.py` | `evidence/tdd/T103.md` | planned |
| AC-SEC | P0 | T045 | `backend/tests/governance/test_dangerous_actions.py` | `evidence/tdd/T045.md` | planned |
| AC-CRED | P0 | T110 | `tests/ci/test_secret_scanning.py` | `evidence/tdd/T110.md` | planned |
| AC-USA | P0 | T098 | `frontend/src/replay/replay.test.tsx` | `evidence/tdd/T098.md` | planned |
| AC-OBS | P0 | T101 | `backend/tests/observability/test_metrics.py` | `evidence/tdd/T101.md` | planned |
| AC-CI | P0 | T003 | `tests/meta/test_quality_commands.py` | `evidence/tdd/T003.md` | in_progress |
