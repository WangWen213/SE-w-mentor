# Traceability Matrix

Status: frozen/current. This matrix freezes required columns and maps atomic P0 US acceptance criteria, FR sub-requirements, NFR requirements, AC families, and foundation governance rows to primary ownership, tests, and evidence.

## 1. Current Implementation And Acceptance View

本节以当前 Repository 与最新 Architecture、README、Runbook、Reflection 为正式基线。这里的
`Implementation Status` 表示能力是否已经形成当前产品实现；`Final Verification` 单独表示最终
回归、目标环境或外部验收证据是否已经收齐。两者不得互相替代。

| Requirement | Task | Component | Implementation Status | Evidence | Final Verification |
| --- | --- | --- | --- | --- | --- |
| Project registration | T019-T023 | Project lifecycle | IMPLEMENTED | Architecture、README、Plan/evidence | TO BE VERIFIED — final full regression |
| Project Bootstrap | T024 | Bootstrap / index entry | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final full regression |
| Project understanding | T028-T043 | Index / Git / Knowledge | IMPLEMENTED | Architecture、README、existing evidence | TO BE VERIFIED — final full regression |
| Proposal | T025-T027 | Proposal service | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final full regression |
| User Confirmation | T027, T043-T052 | Proposal lifecycle / Governance entry | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final full regression |
| ContextPackage | T053-T057 | Context / Provider boundary | IMPLEMENTED | Architecture、README | TO BE VERIFIED — final full regression |
| Impact Analysis | T040-T043 | Impact analyzer | IMPLEMENTED | Architecture、README | TO BE VERIFIED — final full regression |
| Governance | T044-T052 | Governance engine | IMPLEMENTED | Architecture、README、Runbook、existing evidence | TO BE VERIFIED — final governance regression |
| ALLOW | T044-T052, T081 | Governance decision | IMPLEMENTED | Rules/decision baseline、Demo contract | TO BE VERIFIED — final scenario regression |
| REQUIRE_APPROVAL | T047-T052, T082 | Governance / Approval | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final scenario regression |
| BLOCK / DENY_HARD | T044-T052, T083 | Governance precedence | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final security regression |
| Approval | T047-T050 | Approval service | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final regression |
| ExecutionPolicy | T049-T052 | Policy compiler / repository | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final security regression |
| PolicyEnforcer double enforcement | T058-T067 | Governance + runtime enforcement | IMPLEMENTED | Architecture、README | TO BE VERIFIED — final security regression |
| Dispatcher | T058-T067 | Runtime dispatcher | IMPLEMENTED | Architecture、README | TO BE VERIFIED — final full regression |
| Tool boundary | T058-T067 | File / Patch / Shell / Git / Validation tools | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final security regression |
| WRITE Lock | T020, T060-T067 | Project write coordination | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final concurrency regression |
| Transaction | T061-T067 | Transaction manager / manifest | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final recovery regression |
| Shell safety | T058-T067 | Shell tool / policy | IMPLEMENTED | Architecture、Runbook、security baseline | TO BE VERIFIED — final security regression |
| Git safety | T031-T034, T058-T067 | Git service / tool policy | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final security regression |
| Validation | T068-T080 | Validation plan / runner | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final full regression |
| Feedback | T070-T076 | Failure classification / feedback | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final scenario regression |
| Auto repair | T071-T076, T084 | Repair loop | IMPLEMENTED | Architecture、README、Demo contract | TO BE VERIFIED — final scenario regression |
| Stagnation / Replan | T073-T076, T084 | Progress / loop control | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final scenario regression |
| CompletionGate | T078 | Completion gate | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final full regression |
| Cancel | T064-T067, T079 | Runtime / safe-point cancellation | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final recovery regression |
| Keep | T079-T080 | Post-cancel disposition | IMPLEMENTED | README、Runbook | TO BE VERIFIED — final scenario regression |
| Rollback | T061-T067, T080, T085 | Transaction rollback | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final recovery regression |
| Crash Recovery | T061-T067, T080 | Recovery coordinator | IMPLEMENTED | Architecture、README、Runbook | TO BE VERIFIED — final recovery regression |
| Engineering Knowledge | T035-T043, T079 | Knowledge subsystem | IMPLEMENTED | Architecture、README、Memory contract | TO BE VERIFIED — final full regression |
| Knowledge Freshness | T038-T043, T085 | Freshness checker | IMPLEMENTED | Architecture、README、Runbook、Demo contract | TO BE VERIFIED — final scenario regression |
| WebUI | T086-T099 | React WebUI / FastAPI API | IMPLEMENTED | README、Runbook、Architecture | TO BE VERIFIED — final browser regression |
| Tasks page | T093-T099 | Tasks UI / task API | IMPLEMENTED | README、Runbook | TO BE VERIFIED — final browser regression |
| Memory page | T093-T099 | Memory UI / knowledge API | IMPLEMENTED | README、Architecture | TO BE VERIFIED — final browser regression |
| Governance page/history | T093-T099 | Governance UI / history API | IMPLEMENTED | README、Runbook | TO BE VERIFIED — final browser regression |
| Evaluation page | T093-T099 | Evaluation UI / validation API | IMPLEMENTED | README、Architecture | TO BE VERIFIED — final browser regression |
| Settings | T093-T104 | Settings / provider configuration | IMPLEMENTED | README、Runbook | TO BE VERIFIED — final browser regression |
| Credential boundary | T006, T104, T110 | Local/Online credential services | IMPLEMENTED | Decisions、README、Runbook、existing evidence | TO BE VERIFIED — final Secret scan |
| Windows packaging | T105-T106 | PyInstaller onedir distribution | IMPLEMENTED | README、Runbook、packaging baseline | EXTERNAL ACCEPTANCE REQUIRED — clean Windows machine |
| Formal Online WebUI | T107-T109 | Online product / API / WebUI | IMPLEMENTED / CURRENT PRODUCT | README、Runbook、ONLINE_SAFE readiness | EXTERNAL ACCEPTANCE REQUIRED — public real-provider flow |
| Online user/workspace isolation | T107-T109 | Session / ownership / workspace / persistence | IMPLEMENTED | ONLINE_SAFE readiness、security baseline | EXTERNAL ACCEPTANCE REQUIRED — production ONLINE_SAFE |
| Mechanism Demo | T113 | Mock provider / three deterministic Harness scenarios | IMPLEMENTED | `scripts/demo_harness.py`、focused tests、`demo/README.md` | VERIFIED — 3 tests and 3/3 CLI scenarios |
| Docker | T107-T109, T112 | Compose / images / persistent volume | IMPLEMENTED | `deploy/docker-compose*.yml`、deployment guide | EXTERNAL ACCEPTANCE REQUIRED — target host smoke |
| Nginx / SSE | T108-T109, T112 | Gateway / reverse proxy / event stream | IMPLEMENTED | `deploy/nginx/`、ONLINE_SAFE readiness | EXTERNAL ACCEPTANCE REQUIRED — public HTTPS/SSE smoke |
| Deployment | T107-T112 | Formal Online and Demo deployment | IMPLEMENTED | `deploy/README.md`、Production CD Runbook | EXTERNAL ACCEPTANCE REQUIRED |
| Observability / replay | T086-T101 | Events / REST state / SSE / evidence | IMPLEMENTED | Architecture、README、Runbook、evidence layout | TO BE VERIFIED — final full regression |
| Secret handling | T006, T104, T110 | Redaction / credential / build & export boundary | IMPLEMENTED | Decisions、README、ONLINE_SAFE readiness、existing evidence | TO BE VERIFIED — final Secret scan |

Current traceability conclusion:

```text
IMPLEMENTATION SUBSTANTIALLY COMPLETE
BUGFIX / STABILIZATION IN PROGRESS
FINAL ACCEPTANCE EVIDENCE PARTIALLY PENDING
```

## 2. Atomic P0 Contract Ownership Baseline (Preserved)

下表保留原始 134 项原子 US / FR / NFR / AC ownership、测试与 evidence 映射，供严格契约追踪和
历史工具兼容使用。其旧 `status` 列记录的是该映射建立时的原子任务计划状态，不应取代上表的
当前产品 `Implementation Status` 或 `Final Verification` 结论。

| requirement | requirement anchor | priority | primary task | supporting tasks | test | evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US-01-AC-01 | US-01-AC-01 | P0 | T025 | T001 | `tests/acceptance/US-01-AC-01.py` | `evidence/tdd/T025.md` | planned |
| US-01-AC-02 | US-01-AC-02 | P0 | T025 | T001 | `tests/acceptance/US-01-AC-02.py` | `evidence/tdd/T025.md` | planned |
| US-01-AC-03 | US-01-AC-03 | P0 | T025 | T001 | `tests/acceptance/US-01-AC-03.py` | `evidence/tdd/T025.md` | planned |
| US-02-AC-01 | US-02-AC-01 | P0 | T043 | T001 | `tests/acceptance/US-02-AC-01.py` | `evidence/tdd/T043.md` | planned |
| US-02-AC-02 | US-02-AC-02 | P0 | T043 | T001 | `tests/acceptance/US-02-AC-02.py` | `evidence/tdd/T043.md` | planned |
| US-02-AC-03 | US-02-AC-03 | P0 | T043 | T001 | `tests/acceptance/US-02-AC-03.py` | `evidence/tdd/T043.md` | planned |
| US-02-AC-04 | US-02-AC-04 | P0 | T043 | T001 | `tests/acceptance/US-02-AC-04.py` | `evidence/tdd/T043.md` | planned |
| US-03-AC-01 | US-03-AC-01 | P0 | T046 | T001 | `tests/acceptance/US-03-AC-01.py` | `evidence/tdd/T046.md` | planned |
| US-03-AC-02 | US-03-AC-02 | P0 | T046 | T001 | `tests/acceptance/US-03-AC-02.py` | `evidence/tdd/T046.md` | planned |
| US-03-AC-03 | US-03-AC-03 | P0 | T046 | T001 | `tests/acceptance/US-03-AC-03.py` | `evidence/tdd/T046.md` | planned |
| US-03-AC-04 | US-03-AC-04 | P0 | T046 | T001 | `tests/acceptance/US-03-AC-04.py` | `evidence/tdd/T046.md` | planned |
| US-04-AC-01 | US-04-AC-01 | P0 | T059 | T001 | `tests/acceptance/US-04-AC-01.py` | `evidence/tdd/T059.md` | planned |
| US-04-AC-02 | US-04-AC-02 | P0 | T059 | T001 | `tests/acceptance/US-04-AC-02.py` | `evidence/tdd/T059.md` | planned |
| US-04-AC-03 | US-04-AC-03 | P0 | T059 | T001 | `tests/acceptance/US-04-AC-03.py` | `evidence/tdd/T059.md` | planned |
| US-04-AC-04 | US-04-AC-04 | P0 | T059 | T001 | `tests/acceptance/US-04-AC-04.py` | `evidence/tdd/T059.md` | planned |
| US-05-AC-01 | US-05-AC-01 | P0 | T078 | T001 | `tests/acceptance/US-05-AC-01.py` | `evidence/tdd/T078.md` | planned |
| US-05-AC-02 | US-05-AC-02 | P0 | T078 | T001 | `tests/acceptance/US-05-AC-02.py` | `evidence/tdd/T078.md` | planned |
| US-05-AC-03 | US-05-AC-03 | P0 | T078 | T001 | `tests/acceptance/US-05-AC-03.py` | `evidence/tdd/T078.md` | planned |
| US-05-AC-04 | US-05-AC-04 | P0 | T078 | T001 | `tests/acceptance/US-05-AC-04.py` | `evidence/tdd/T078.md` | planned |
| US-06-AC-01 | US-06-AC-01 | P0 | T079 | T001 | `tests/acceptance/US-06-AC-01.py` | `evidence/tdd/T079.md` | planned |
| US-06-AC-02 | US-06-AC-02 | P0 | T079 | T001 | `tests/acceptance/US-06-AC-02.py` | `evidence/tdd/T079.md` | planned |
| US-06-AC-03 | US-06-AC-03 | P0 | T079 | T001 | `tests/acceptance/US-06-AC-03.py` | `evidence/tdd/T079.md` | planned |
| US-06-AC-04 | US-06-AC-04 | P0 | T079 | T001 | `tests/acceptance/US-06-AC-04.py` | `evidence/tdd/T079.md` | planned |
| FR-01-01 | FR-01-01 | P0 | T019 | T001,T009 | `tests/requirements/FR-01-01.py` | `evidence/tdd/T019.md` | planned |
| FR-01-02 | FR-01-02 | P0 | T021 | T001,T009 | `tests/requirements/FR-01-02.py` | `evidence/tdd/T021.md` | planned |
| FR-01-03 | FR-01-03 | P0 | T022 | T001,T009 | `tests/requirements/FR-01-03.py` | `evidence/tdd/T022.md` | planned |
| FR-01-04 | FR-01-04 | P0 | T023 | T001,T009 | `tests/requirements/FR-01-04.py` | `evidence/tdd/T023.md` | planned |
| FR-02-01 | FR-02-01 | P0 | T024 | T001 | `tests/requirements/FR-02-01.py` | `evidence/tdd/T024.md` | planned |
| FR-02-02 | FR-02-02 | P0 | T025 | T001 | `tests/requirements/FR-02-02.py` | `evidence/tdd/T025.md` | planned |
| FR-02-03 | FR-02-03 | P0 | T026 | T001 | `tests/requirements/FR-02-03.py` | `evidence/tdd/T026.md` | planned |
| FR-02-04 | FR-02-04 | P0 | T027 | T001 | `tests/requirements/FR-02-04.py` | `evidence/tdd/T027.md` | planned |
| FR-03-01 | FR-03-01 | P0 | T028 | T001 | `tests/requirements/FR-03-01.py` | `evidence/tdd/T028.md` | planned |
| FR-03-02 | FR-03-02 | P0 | T029 | T001 | `tests/requirements/FR-03-02.py` | `evidence/tdd/T029.md` | planned |
| FR-03-03 | FR-03-03 | P0 | T033 | T001 | `tests/requirements/FR-03-03.py` | `evidence/tdd/T033.md` | planned |
| FR-03-04 | FR-03-04 | P0 | T034 | T001 | `tests/requirements/FR-03-04.py` | `evidence/tdd/T034.md` | planned |
| FR-04-01 | FR-04-01 | P0 | T035 | T001,T012 | `tests/requirements/FR-04-01.py` | `evidence/tdd/T035.md` | planned |
| FR-04-02 | FR-04-02 | P0 | T036 | T001,T012 | `tests/requirements/FR-04-02.py` | `evidence/tdd/T036.md` | planned |
| FR-04-03 | FR-04-03 | P0 | T040 | T001,T012 | `tests/requirements/FR-04-03.py` | `evidence/tdd/T040.md` | planned |
| FR-04-04 | FR-04-04 | P0 | T041 | T001,T012 | `tests/requirements/FR-04-04.py` | `evidence/tdd/T041.md` | planned |
| FR-04-05 | FR-04-05 | P0 | T043 | T001,T012 | `tests/requirements/FR-04-05.py` | `evidence/tdd/T043.md` | planned |
| FR-05-01 | FR-05-01 | P0 | T053 | T001 | `tests/requirements/FR-05-01.py` | `evidence/tdd/T053.md` | planned |
| FR-05-02 | FR-05-02 | P0 | T056 | T001 | `tests/requirements/FR-05-02.py` | `evidence/tdd/T056.md` | planned |
| FR-05-03 | FR-05-03 | P0 | T066 | T001 | `tests/requirements/FR-05-03.py` | `evidence/tdd/T066.md` | planned |
| FR-05-04 | FR-05-04 | P0 | T068 | T001 | `tests/requirements/FR-05-04.py` | `evidence/tdd/T068.md` | planned |
| FR-05-05 | FR-05-05 | P0 | T069 | T001 | `tests/requirements/FR-05-05.py` | `evidence/tdd/T069.md` | planned |
| FR-05-06 | FR-05-06 | P0 | T078 | T001 | `tests/requirements/FR-05-06.py` | `evidence/tdd/T078.md` | planned |
| FR-06-01 | FR-06-01 | P0 | T044 | T001,T012 | `tests/requirements/FR-06-01.py` | `evidence/tdd/T044.md` | planned |
| FR-06-02 | FR-06-02 | P0 | T046 | T001,T012 | `tests/requirements/FR-06-02.py` | `evidence/tdd/T046.md` | planned |
| FR-06-03 | FR-06-03 | P0 | T047 | T001,T012 | `tests/requirements/FR-06-03.py` | `evidence/tdd/T047.md` | planned |
| FR-06-04 | FR-06-04 | P0 | T048 | T001,T012 | `tests/requirements/FR-06-04.py` | `evidence/tdd/T048.md` | planned |
| FR-06-05 | FR-06-05 | P0 | T049 | T001,T012 | `tests/requirements/FR-06-05.py` | `evidence/tdd/T049.md` | planned |
| FR-07-01 | FR-07-01 | P0 | T058 | T001 | `tests/requirements/FR-07-01.py` | `evidence/tdd/T058.md` | planned |
| FR-07-02 | FR-07-02 | P0 | T029 | T001 | `tests/requirements/FR-07-02.py` | `evidence/tdd/T029.md` | planned |
| FR-07-03 | FR-07-03 | P0 | T029 | T001 | `tests/requirements/FR-07-03.py` | `evidence/tdd/T029.md` | planned |
| FR-07-04 | FR-07-04 | P0 | T059 | T001 | `tests/requirements/FR-07-04.py` | `evidence/tdd/T059.md` | planned |
| FR-07-05 | FR-07-05 | P0 | T060 | T001 | `tests/requirements/FR-07-05.py` | `evidence/tdd/T060.md` | planned |
| FR-07-06 | FR-07-06 | P0 | T061 | T001 | `tests/requirements/FR-07-06.py` | `evidence/tdd/T061.md` | planned |
| FR-07-07 | FR-07-07 | P0 | T062 | T001 | `tests/requirements/FR-07-07.py` | `evidence/tdd/T062.md` | planned |
| FR-07-08 | FR-07-08 | P0 | T064 | T001 | `tests/requirements/FR-07-08.py` | `evidence/tdd/T064.md` | planned |
| FR-07-09 | FR-07-09 | P0 | T065 | T001 | `tests/requirements/FR-07-09.py` | `evidence/tdd/T065.md` | planned |
| FR-08-01 | FR-08-01 | P0 | T070 | T001 | `tests/requirements/FR-08-01.py` | `evidence/tdd/T070.md` | planned |
| FR-08-02 | FR-08-02 | P0 | T071 | T001 | `tests/requirements/FR-08-02.py` | `evidence/tdd/T071.md` | planned |
| FR-08-03 | FR-08-03 | P0 | T072 | T001 | `tests/requirements/FR-08-03.py` | `evidence/tdd/T072.md` | planned |
| FR-08-04 | FR-08-04 | P0 | T073 | T001 | `tests/requirements/FR-08-04.py` | `evidence/tdd/T073.md` | planned |
| FR-08-05 | FR-08-05 | P0 | T076 | T001 | `tests/requirements/FR-08-05.py` | `evidence/tdd/T076.md` | planned |
| FR-08-06 | FR-08-06 | P0 | T075 | T001 | `tests/requirements/FR-08-06.py` | `evidence/tdd/T075.md` | planned |
| FR-08-07 | FR-08-07 | P0 | T078 | T001 | `tests/requirements/FR-08-07.py` | `evidence/tdd/T078.md` | planned |
| FR-09-01 | FR-09-01 | P0 | T079 | T001 | `tests/requirements/FR-09-01.py` | `evidence/tdd/T079.md` | planned |
| FR-09-02 | FR-09-02 | P0 | T036 | T001 | `tests/requirements/FR-09-02.py` | `evidence/tdd/T036.md` | planned |
| FR-09-03 | FR-09-03 | P0 | T039 | T001 | `tests/requirements/FR-09-03.py` | `evidence/tdd/T039.md` | planned |
| FR-09-04 | FR-09-04 | P0 | T038 | T001 | `tests/requirements/FR-09-04.py` | `evidence/tdd/T038.md` | planned |
| FR-10-01 | FR-10-01 | P0 | T094 | T001 | `tests/requirements/FR-10-01.py` | `evidence/tdd/T094.md` | planned |
| FR-10-02 | FR-10-02 | P0 | T096 | T001 | `tests/requirements/FR-10-02.py` | `evidence/tdd/T096.md` | planned |
| FR-10-03 | FR-10-03 | P0 | T097 | T001 | `tests/requirements/FR-10-03.py` | `evidence/tdd/T097.md` | planned |
| FR-11-01 | FR-11-01 | P0 | T100 | T001 | `tests/requirements/FR-11-01.py` | `evidence/tdd/T100.md` | planned |
| FR-11-02 | FR-11-02 | P0 | T092 | T001 | `tests/requirements/FR-11-02.py` | `evidence/tdd/T092.md` | planned |
| FR-12-01 | FR-12-01 | P0 | T053 | T001 | `tests/requirements/FR-12-01.py` | `evidence/tdd/T053.md` | planned |
| FR-12-02 | FR-12-02 | P0 | T081 | T001 | `tests/requirements/FR-12-02.py` | `evidence/tdd/T081.md` | planned |
| FR-12-03 | FR-12-03 | P0 | T085 | T001 | `tests/requirements/FR-12-03.py` | `evidence/tdd/T085.md` | planned |
| NFR-PERF-01 | NFR-PERF-01 | P0 | T102 | T001 | `tests/nfr/NFR-PERF-01.py` | `evidence/tdd/T102.md` | planned |
| NFR-PERF-02 | NFR-PERF-02 | P0 | T102 | T001 | `tests/nfr/NFR-PERF-02.py` | `evidence/tdd/T102.md` | planned |
| NFR-PERF-03 | NFR-PERF-03 | P0 | T102 | T001 | `tests/nfr/NFR-PERF-03.py` | `evidence/tdd/T102.md` | planned |
| NFR-PERF-04 | NFR-PERF-04 | P0 | T102 | T001 | `tests/nfr/NFR-PERF-04.py` | `evidence/tdd/T102.md` | planned |
| NFR-PERF-05 | NFR-PERF-05 | P0 | T102 | T001 | `tests/nfr/NFR-PERF-05.py` | `evidence/tdd/T102.md` | planned |
| NFR-PERF-06 | NFR-PERF-06 | P0 | T102 | T001 | `tests/nfr/NFR-PERF-06.py` | `evidence/tdd/T102.md` | planned |
| NFR-PERF-07 | NFR-PERF-07 | P0 | T102 | T001 | `tests/nfr/NFR-PERF-07.py` | `evidence/tdd/T102.md` | planned |
| NFR-SEC-01 | NFR-SEC-01 | P0 | T045 | T001 | `tests/nfr/NFR-SEC-01.py` | `evidence/tdd/T045.md` | planned |
| NFR-SEC-02 | NFR-SEC-02 | P0 | T045 | T001 | `tests/nfr/NFR-SEC-02.py` | `evidence/tdd/T045.md` | planned |
| NFR-SEC-03 | NFR-SEC-03 | P0 | T045 | T001 | `tests/nfr/NFR-SEC-03.py` | `evidence/tdd/T045.md` | planned |
| NFR-SEC-04 | NFR-SEC-04 | P0 | T045 | T001 | `tests/nfr/NFR-SEC-04.py` | `evidence/tdd/T045.md` | planned |
| NFR-SEC-05 | NFR-SEC-05 | P0 | T045 | T001 | `tests/nfr/NFR-SEC-05.py` | `evidence/tdd/T045.md` | planned |
| NFR-SEC-06 | NFR-SEC-06 | P0 | T045 | T001 | `tests/nfr/NFR-SEC-06.py` | `evidence/tdd/T045.md` | planned |
| NFR-SEC-07 | NFR-SEC-07 | P0 | T045 | T001 | `tests/nfr/NFR-SEC-07.py` | `evidence/tdd/T045.md` | planned |
| NFR-SEC-08 | NFR-SEC-08 | P0 | T045 | T001 | `tests/nfr/NFR-SEC-08.py` | `evidence/tdd/T045.md` | planned |
| NFR-SEC-09 | NFR-SEC-09 | P0 | T045 | T001 | `tests/nfr/NFR-SEC-09.py` | `evidence/tdd/T045.md` | planned |
| NFR-SEC-10 | NFR-SEC-10 | P0 | T045 | T001 | `tests/nfr/NFR-SEC-10.py` | `evidence/tdd/T045.md` | planned |
| NFR-CRED-01 | NFR-CRED-01 | P0 | T104 | T001 | `tests/nfr/NFR-CRED-01.py` | `evidence/tdd/T104.md` | planned |
| NFR-CRED-02 | NFR-CRED-02 | P0 | T104 | T001 | `tests/nfr/NFR-CRED-02.py` | `evidence/tdd/T104.md` | planned |
| NFR-CRED-03 | NFR-CRED-03 | P0 | T104 | T001 | `tests/nfr/NFR-CRED-03.py` | `evidence/tdd/T104.md` | planned |
| NFR-CRED-04 | NFR-CRED-04 | P0 | T104 | T001 | `tests/nfr/NFR-CRED-04.py` | `evidence/tdd/T104.md` | planned |
| NFR-CRED-05 | NFR-CRED-05 | P0 | T104 | T001 | `tests/nfr/NFR-CRED-05.py` | `evidence/tdd/T104.md` | planned |
| NFR-CRED-06 | NFR-CRED-06 | P0 | T104 | T001 | `tests/nfr/NFR-CRED-06.py` | `evidence/tdd/T104.md` | planned |
| NFR-CRED-07 | NFR-CRED-07 | P0 | T104 | T001 | `tests/nfr/NFR-CRED-07.py` | `evidence/tdd/T104.md` | planned |
| NFR-CRED-08 | NFR-CRED-08 | P0 | T104 | T001 | `tests/nfr/NFR-CRED-08.py` | `evidence/tdd/T104.md` | planned |
| NFR-CRED-09 | NFR-CRED-09 | P0 | T104 | T001 | `tests/nfr/NFR-CRED-09.py` | `evidence/tdd/T104.md` | planned |
| NFR-CRED-10 | NFR-CRED-10 | P0 | T104 | T001 | `tests/nfr/NFR-CRED-10.py` | `evidence/tdd/T104.md` | planned |
| NFR-USA-01 | NFR-USA-01 | P0 | T099 | T001 | `tests/nfr/NFR-USA-01.py` | `evidence/tdd/T099.md` | planned |
| NFR-USA-02 | NFR-USA-02 | P0 | T099 | T001 | `tests/nfr/NFR-USA-02.py` | `evidence/tdd/T099.md` | planned |
| NFR-USA-03 | NFR-USA-03 | P0 | T099 | T001 | `tests/nfr/NFR-USA-03.py` | `evidence/tdd/T099.md` | planned |
| NFR-USA-04 | NFR-USA-04 | P0 | T099 | T001 | `tests/nfr/NFR-USA-04.py` | `evidence/tdd/T099.md` | planned |
| NFR-USA-05 | NFR-USA-05 | P0 | T099 | T001 | `tests/nfr/NFR-USA-05.py` | `evidence/tdd/T099.md` | planned |
| NFR-USA-06 | NFR-USA-06 | P0 | T099 | T001 | `tests/nfr/NFR-USA-06.py` | `evidence/tdd/T099.md` | planned |
| NFR-USA-07 | NFR-USA-07 | P0 | T099 | T001 | `tests/nfr/NFR-USA-07.py` | `evidence/tdd/T099.md` | planned |
| NFR-USA-08 | NFR-USA-08 | P0 | T099 | T001 | `tests/nfr/NFR-USA-08.py` | `evidence/tdd/T099.md` | planned |
| NFR-USA-09 | NFR-USA-09 | P0 | T099 | T001 | `tests/nfr/NFR-USA-09.py` | `evidence/tdd/T099.md` | planned |
| NFR-USA-10 | NFR-USA-10 | P0 | T099 | T001 | `tests/nfr/NFR-USA-10.py` | `evidence/tdd/T099.md` | planned |
| NFR-OBS-01 | NFR-OBS-01 | P0 | T100 | T001 | `tests/nfr/NFR-OBS-01.py` | `evidence/tdd/T100.md` | planned |
| NFR-OBS-02 | NFR-OBS-02 | P0 | T100 | T001 | `tests/nfr/NFR-OBS-02.py` | `evidence/tdd/T100.md` | planned |
| NFR-OBS-03 | NFR-OBS-03 | P0 | T100 | T001 | `tests/nfr/NFR-OBS-03.py` | `evidence/tdd/T100.md` | planned |
| NFR-OBS-04 | NFR-OBS-04 | P0 | T100 | T001 | `tests/nfr/NFR-OBS-04.py` | `evidence/tdd/T100.md` | planned |
| NFR-OBS-05 | NFR-OBS-05 | P0 | T100 | T001 | `tests/nfr/NFR-OBS-05.py` | `evidence/tdd/T100.md` | planned |
| NFR-OBS-06 | NFR-OBS-06 | P0 | T100 | T001 | `tests/nfr/NFR-OBS-06.py` | `evidence/tdd/T100.md` | planned |
| NFR-OBS-07 | NFR-OBS-07 | P0 | T100 | T001 | `tests/nfr/NFR-OBS-07.py` | `evidence/tdd/T100.md` | planned |
| NFR-OBS-08 | NFR-OBS-08 | P0 | T100 | T001 | `tests/nfr/NFR-OBS-08.py` | `evidence/tdd/T100.md` | planned |
| NFR-OBS-09 | NFR-OBS-09 | P0 | T100 | T001 | `tests/nfr/NFR-OBS-09.py` | `evidence/tdd/T100.md` | planned |
| NFR-OBS-10 | NFR-OBS-10 | P0 | T100 | T001 | `tests/nfr/NFR-OBS-10.py` | `evidence/tdd/T100.md` | planned |
| NFR-OBS-11 | NFR-OBS-11 | P0 | T100 | T001 | `tests/nfr/NFR-OBS-11.py` | `evidence/tdd/T100.md` | planned |
| AC-FR | AC-FR | P0 | T115 | T001 | `tests/acceptance/AC-FR.py` | `evidence/tdd/T115.md` | planned |
| AC-PERF | AC-PERF | P0 | T102 | T001 | `tests/acceptance/AC-PERF.py` | `evidence/tdd/T102.md` | planned |
| AC-SEC | AC-SEC | P0 | T045 | T001 | `tests/acceptance/AC-SEC.py` | `evidence/tdd/T045.md` | planned |
| AC-CRED | AC-CRED | P0 | T110 | T001 | `tests/acceptance/AC-CRED.py` | `evidence/tdd/T110.md` | planned |
| AC-USA | AC-USA | P0 | T099 | T001 | `tests/acceptance/AC-USA.py` | `evidence/tdd/T099.md` | planned |
| AC-OBS | AC-OBS | P0 | T101 | T001 | `tests/acceptance/AC-OBS.py` | `evidence/tdd/T101.md` | planned |
| AC-CI | AC-CI | P0 | T003 | T001 | `tests/acceptance/AC-CI.py` | `evidence/tdd/T003.md` | planned |
| GOV-MIGRATION-01 | Alembic migration ownership and single-head gate | P0 | T008 | T001,T003,T007 | `tests/meta/test_migration_policy.py` | `evidence/tdd/T008.md` | verified |
