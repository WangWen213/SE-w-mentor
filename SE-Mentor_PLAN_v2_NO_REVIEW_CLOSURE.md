# SE-Mentor 完整实施计划（PLAN v2）

> 状态：**前置骨架和本地环境准备已开始；严格 DoD 状态以各 Task 状态行和 `PREP_STATUS.md` 为准。**  
> 依据：`SPEC.问题陈述.md`、上一版 PLAN 审查报告。  
> 原则：每个 Task 由一个新鲜 subagent 在一次会话内完成；严格 TDD；所有 P0 结果必须有自动化测试和证据。

## 0. 状态图例

- `[ ] 未开始`：计划已定义，但没有实现、测试或 commit。
- `[-] 进行中`：已有 worktree 和失败测试，尚未满足 DoD。
- `[x] 已完成`：失败测试先红、实现转绿、回归通过、双阶段评审通过，并已填写 commit/evidence。
- `[!] 阻塞`：依赖外部环境、前置决策或未完成任务。
- `[~] P1 延后`：不属于 P0 发布条件，但必须保留原因和重新评审入口。

**本文件生成时：117 个 P0 Task 均未完成；其中 Windows、阿里云和最终发布 Task 含外部阻塞。**

**当前执行策略：暂停 T009 及之后功能开发；先完成 T000～T008 合规回填。工程环境准备度单独记录在 `PREP_STATUS.md`，本 PLAN 只记录严格 DoD 状态。**

## 1. Task 完成定义

1. 先提交指定失败测试并记录红色原因；
1. 只实现本 Task 的最小范围，不顺手完成后续 Task；
1. 当前测试、相关回归、Lint、类型检查全部通过；
1. 先做 Spec Compliance Review，再做 Code Quality Review；
1. 更新 `TRACEABILITY_MATRIX.md`、`AGENT_LOG.md`、Task 状态、commit 和 evidence；
1. `git status` 干净，禁止 `git add .`；
1. 如发现规约歧义，标记 `[!]` 并暂停，不自行猜测。

## 2. Worktree、所有权与合并规则

|Worktree|Task|唯一职责|
|---|---|---|
|`wt-spec-contracts`|T000～T007|规约、追踪、共享 Contract、配置、凭据边界、DB 基线|
|`wt-schema`|T008～T018|唯一正式 migration owner；其他 worktree 禁止创建 Alembic revision|
|`wt-project`|T019～T027|项目、锁、任务、提案|
|`wt-index`|T028～T034|路径、索引、Git、上下文、Token|
|`wt-knowledge`|T035～T043|知识、签名、新鲜度、影响|
|`wt-governance`|T044～T052|规则、决策、审批、策略、再治理|
|`wt-runtime`|T053～T067|Provider、Prompt 边界、工具、事务、Agent Runtime|
|`wt-validation`|T068～T080|进展、验证、反馈、修正、完成门禁、知识更新|
|`wt-e2e`|T081～T085|离线确定性核心场景|
|`wt-api`|T086～T092|REST/SSE/回放 API|
|`wt-web`|T093～T099|React WebUI 与浏览器 E2E|
|`wt-delivery`|T100～T116|NFR、分发、部署、文档、验收与发布|

### 2.1 共享文件所有权

|共享文件|Owner|规则|
|---|---|---|
|`backend/src/se_mentor/contracts/**`|`wt-spec-contracts`|仅通过契约变更 PR 修改；所有业务分支只消费|
|`backend/migrations/**`|`wt-schema`|唯一 migration owner；CI 强制单 Head|
|`backend/src/se_mentor/models/**`|`wt-schema`|按领域文件拆分，业务分支不得直接加列|
|`backend/pyproject.toml`|`wt-spec-contracts`|依赖变更由 owner 合并；业务分支提交依赖申请|
|`frontend/package.json`|`wt-web`|交付分支不直接修改|
|`backend/src/se_mentor/main.py`|`wt-api`|日志/静态资源集成通过扩展函数，避免多人直接改入口|
|`Makefile / .gitlab-ci.yml`|`wt-spec-contracts / wt-delivery`|本地命令 owner 与 CI owner 分离，变更需双审|
|`PLAN.md / TRACEABILITY_MATRIX.md`|`wt-spec-contracts`|完成任务仅更新状态/commit/evidence，结构变更需 plan review|

### 2.2 并行门禁

- T000～T008 完成并通过首次冷启动复读后，才允许大规模并行。
- `wt-schema` 合并 T018 且 Alembic 单 Head 后，项目、索引、知识、治理可并行。
- T004 的共享 Contract 未冻结时，禁止各分支建立私有 stub。
- T049～T052 完成前，Runtime 只允许只读工具集成，不允许写工具进入主循环。
- T085 离线 E2E 通过后冻结 OpenAPI；随后 API 与 WebUI 并行。
- 每个 PR 标明 Task ID、红/绿测试、依赖、影响共享文件、Spec Review 和 Code Review。

## 3. 关键依赖链

```text
T000-T008 规约/契约/迁移门禁
  ├─ T009-T018 数据模型
  ├─ T019-T027 项目、锁、任务、提案
  ├─ T028-T034 索引、Git、上下文、Token
  ├─ T035-T043 知识与影响
  ├─ T044-T052 治理、审批、ExecutionPolicy
  ├─ T053-T067 LLM、工具、事务、Agent Runtime
  ├─ T068-T080 验证、反馈、修正、CompletionGate
  ├─ T081-T085 离线 E2E
  ├─ T086-T099 API 与 WebUI
  └─ T100-T116 NFR、分发、部署、验收与发布
```

# Phase 0 规约与契约

## T000 — 冻结 P0 未决问题并修正规约章节

- **状态**：[x] 已完成
- **阻塞说明**：无
- **Worktree**：`wt-spec-contracts`
- **覆盖需求**：`OQ-01～OQ-20`, `审查 P0-10`, `SPEC 章节完整性`
- **目标**：把 20 个未决问题的建议答案转成正式 P0 决策，并补齐凭据与分发章节编号缺口；任何后续 subagent 不得自行改变这些基础决策。
- **涉及文件**：
  - `docs/DECISIONS_P0.md`
  - `SPEC.md`
  - `SPEC_PROCESS.md`
- **预期实现要点**：
  - 逐项记录决策、理由、影响模块和可变更流程
  - 明确 Python 主支持、TypeScript 辅助、Shell 参数数组、测试修改需审批、P0 不自动 commit、云端只用 Mock 且不上传仓库
  - 为仍需账号、域名或机器验证的事项标记 EXTERNAL_PENDING
- **将要先写的失败测试**：
  - 文档契约测试 `test_T000_all_OQ_have_decision_and_owner` 先因缺失 OQ 决策表失败。
- **验证步骤**：
  1. 运行文档检查脚本，确认 OQ-01～OQ-20 各出现一次且有状态
  2. 人工复核 SPEC 的章节编号和交叉引用
  3. 另一名新鲜 subagent 仅凭决策文件复述 P0 边界，无需额外口头说明
- **依赖**：无
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T000.xml
  - evidence/diffs/T000.patch
  - `AGENT_LOG.md` 中的 T000 记录
- **Commit**：implementation `2d13b49679d52cdc77079d3f9dd6ecb757be34f2`; integration metadata `f4dde68b36c7eeeedb45b0052c6244f994aa6af2`; final metadata recorded in the containing integration commit

## T001 — 建立需求—Task—测试—证据追踪矩阵

- **状态**：[x] 已完成
- **阻塞说明**：无
- **Worktree**：`wt-spec-contracts`
- **覆盖需求**：`US-01～US-06`, `FR-01～FR-12`, `NFR-PERF/SEC/CRED/USA/OBS`, `AC-FR/AC-PERF/AC-SEC/AC-USA/AC-OBS`
- **目标**：为每项需求建立唯一 Task、测试和证据映射，防止完成全部代码却无法证明满足规约。
- **涉及文件**：
  - `docs/TRACEABILITY_MATRIX.md`
  - `scripts/check_traceability.py`
  - `tests/meta/test_traceability.py`
- **预期实现要点**：
  - 矩阵列必须包含 requirement、priority、task、test、evidence、status
  - P0 需求不允许出现空 task 或空 test
  - 发布门禁读取同一矩阵，不维护第二份手工清单
- **将要先写的失败测试**：
  - `test_T001_all_p0_requirements_have_task_test_evidence` 先因矩阵不存在失败。
- **验证步骤**：
  1. 执行 `python scripts/check_traceability.py`
  2. 确认所有 P0 条目覆盖且无重复主责任 Task
  3. 随机抽查 US-04、FR-06-05、NFR-CRED-08 可反向追踪到实现与证据
- **依赖**：T000
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T001.xml
  - evidence/diffs/T001.patch
  - `AGENT_LOG.md` 中的 T001 记录
- **Commit**：implementation `e9b540bcca244e3822aaff292259e366668bf375`; merge `957c3af6e2ab79ca706c663d7cbf8de745c6d0a8`; semantic correction `1184c7beca606a38769ef58cb66d5a453323c294`; final metadata recorded in the containing integration commit

## T002 — 建立 monorepo 与最小可运行应用

- **状态**：[x] 已完成
- **阻塞说明**：无
- **Worktree**：`wt-spec-contracts`
- **覆盖需求**：`技术选型`, `FR-10 基础`, `AC-CI 基础`
- **目标**：建立 Python/FastAPI、React/TypeScript、部署、脚本和证据目录，使最小后端与前端可启动。
- **涉及文件**：
  - `backend/pyproject.toml`
  - `backend/src/se_mentor/main.py`
  - `frontend/package.json`
  - `frontend/src/main.tsx`
  - `Makefile`
  - `.gitignore`
- **预期实现要点**：
  - FastAPI 使用 `create_app()` 避免导入副作用
  - React 使用 TypeScript strict
  - 创建 `evidence/` 标准目录并忽略运行时敏感产物
- **将要先写的失败测试**：
  - `test_T002_health_and_frontend_shell_exist` 先因应用入口不存在失败。
- **验证步骤**：
  1. 后端 `/health` 返回 200
  2. 前端 smoke test 渲染根节点
  3. 确认 `.env`、数据库、备份、日志和真实证据大文件未进入 Git
- **依赖**：T000
- **可并行性**：可与 T001 并行
- **预期证据**：
  - evidence/test-reports/T002.xml
  - evidence/diffs/T002.patch
  - `AGENT_LOG.md` 中的 T002 记录
- **Commit**：bootstrap implementation predates strict TDD; DoD/evidence closure recorded in the containing T002/T003 environment evidence commit

## T003 — 统一格式、Lint、类型检查和测试命令

- **状态**：[-] 进行中；质量入口专项测试已完成，外部普通权限 Vitest/build 已通过；等待外部普通权限 canonical check-all 结果。
- **阻塞说明**：Codex 沙箱内 Vitest/esbuild 原生子进程失败已分类为 `CODEX_SANDBOX_NATIVE_CHILD_RESTRICTION`，非仓库缺陷；T003 最终 `[x]` 仍需记录 `.\backend\.venv\Scripts\python.exe scripts\check_all.py` 的外部普通非管理员 PowerShell 结果。
- **Worktree**：`wt-spec-contracts`
- **覆盖需求**：`AC-CI`, `系统级 Definition of Done`
- **目标**：提供本地和 CI 完全一致的单命令质量门禁。
- **涉及文件**：
  - `backend/pyproject.toml`
  - `frontend/package.json`
  - `Makefile`
  - `scripts/check_all.py`
  - `tests/meta/test_quality_commands.py`
- **预期实现要点**：
  - 配置 Ruff、mypy、pytest、Vitest、Playwright 入口
  - 任何子命令失败必须向上传递非零退出码
  - 区分 unit、integration、frontend、security、performance、e2e
- **将要先写的失败测试**：
  - `test_T003_make_test_propagates_failure` 先通过临时失败测试证明当前命令无法正确失败。
- **验证步骤**：
  1. `make format-check lint type-check unit-test` 全部可执行
  2. 人为制造格式与测试错误，命令均返回非零
  3. 恢复后 `make test` 通过
- **依赖**：T002
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T003.xml
  - evidence/diffs/T003.patch
  - `AGENT_LOG.md` 中的 T003 记录
- **Commit**：quality entrypoint/evidence update recorded in the containing T002/T003 environment evidence commit

## T004 — 冻结共享领域契约与错误码

- **状态**：[x] 已完成
- **阻塞说明**：无
- **Worktree**：`wt-spec-contracts`
- **覆盖需求**：`FR-05-02`, `FR-11`, `审查共享契约问题`
- **目标**：在并行 worktree 启动前冻结枚举、EvidenceRef、ToolResult、FeedbackSignal、AgentAction 联合类型、事件类型和稳定错误码。
- **涉及文件**：
  - `backend/src/se_mentor/contracts/enums.py`
  - `backend/src/se_mentor/contracts/evidence.py`
  - `backend/src/se_mentor/contracts/actions.py`
  - `backend/src/se_mentor/contracts/results.py`
  - `backend/src/se_mentor/contracts/errors.py`
  - `backend/tests/contracts/`
- **预期实现要点**：
  - Schema 禁止额外字段并使用显式字符串枚举
  - 错误码不依赖英文异常文本
  - 仓库内容、LLM 输出和工具输入分别标记信任级别
- **将要先写的失败测试**：
  - `test_T004_unknown_action_and_extra_field_are_rejected` 先因共享契约不存在失败。
- **验证步骤**：
  1. 生成 JSON Schema 快照并纳入变更审查
  2. 后端 round-trip 测试通过
  3. 导出前端 TypeScript 类型草案并验证无重复枚举
- **依赖**：T002
- **可并行性**：可与 T003 并行
- **预期证据**：
  - evidence/test-reports/T004.xml
  - evidence/diffs/T004.patch
  - `AGENT_LOG.md` 中的 T004 记录
- **Commit**：initial implementation `7b839c1`; expanded tests and enum mirror `fd3e775`; evidence refresh `920fbd4`; merge `251170637434c1b8919edd154cad225542cbfaf6`; integration metadata `4d9dd2e30a16b7999fe5758659a8c24b5dc6e35e`; provenance audit recorded in the containing commit. Note: `1184c7beca606a38769ef58cb66d5a453323c294` is the T001 semantic correction and later T004 branch HEAD after rebase, not a T004 implementation commit.

## T005 — 实现分层配置、配置版本与运行 Profile

- **状态**：[-] branch complete in `codex/T005-config-profiles`; awaiting main merge and project-level regression before `[x]`
- **阻塞说明**：无
- **Worktree**：`wt-spec-contracts`
- **覆盖需求**：`FR-01-02`, `NFR-PERF-04`, `NFR-PERF-06`, `OQ-09`, `OQ-19`, `OQ-20`
- **目标**：实现系统级、项目级、任务级配置合并，并冻结任务创建时的有效配置版本；支持 LOCAL_FULL 与 CLOUD_DEMO Profile。
- **涉及文件**：
  - `backend/src/se_mentor/config/schema.py`
  - `backend/src/se_mentor/config/loader.py`
  - `backend/src/se_mentor/config/profiles.py`
  - `backend/tests/config/test_loader.py`
- **预期实现要点**：
  - 更严格规则优先且任务配置不能覆盖 DENY_HARD
  - 未知配置项拒绝或显式警告
  - 运行中配置变化不静默改变当前任务权限
- **将要先写的失败测试**：
  - `test_T005_task_config_cannot_relax_system_deny_rule` 先因无配置合并器失败。
- **验证步骤**：
  1. 覆盖默认、项目、任务三层合并
  2. 配置变化生成新版本且旧任务仍引用旧版本
  3. CLOUD_DEMO 自动禁用任意仓库路径、真实 Shell 和真实 LLM
- **依赖**：T004
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T005.xml
  - evidence/diffs/T005.patch
  - `AGENT_LOG.md` 中的 T005 记录
- **Commit**：branch implementation commit to be reported after commit creation

## T006 — 实现凭据边界、脱敏与最小子进程环境

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-spec-contracts`
- **覆盖需求**：`NFR-CRED-01～10`, `NFR-SEC-09`, `AC-SEC-05`
- **目标**：在正式凭据存储实现前建立统一 Secret 类型、脱敏器和最小环境白名单，确保 Key 不进入日志、Prompt、DB 或项目子进程。
- **涉及文件**：
  - `backend/src/se_mentor/security/secrets.py`
  - `backend/src/se_mentor/security/redaction.py`
  - `backend/src/se_mentor/security/process_env.py`
  - `backend/tests/security/test_secret_boundary.py`
  - `.env.example`
- **预期实现要点**：
  - 统一识别 OpenAI、阿里云和通用 token 形态
  - LLM Provider 通过回调读取凭据，不把值注入 AgentContext
  - 子进程只继承允许变量
- **将要先写的失败测试**：
  - `test_AC_SEC_05_child_process_cannot_read_llm_key` 与 `test_T006_secret_never_in_repr_log_or_json` 先失败。
- **验证步骤**：
  1. 扫描测试日志、异常、数据库 dump 和 API 响应
  2. 验证 `.env.example` 仅有占位符
  3. 确认脱敏异常本身会产生安全错误而非回显原值
- **依赖**：T004
- **可并行性**：可与 T005 并行
- **预期证据**：
  - evidence/test-reports/T006.xml
  - evidence/diffs/T006.patch
  - `AGENT_LOG.md` 中的 T006 记录
- **Commit**：`未填写`

## T007 — 建立 SQLAlchemy、SQLite 与 Alembic 基线

- **状态**：[-] 进行中；SQLAlchemy、SQLite、Alembic 空基线与事务/外键基线测试已通过，尚未满足 T007 完整 DoD。
- **阻塞说明**：依赖 T005 正式完成；尚缺并发读写 smoke 证据、完整 evidence、评审与 commit。
- **Worktree**：`wt-spec-contracts`
- **覆盖需求**：`数据模型 6.2～6.4`, `NFR-SEC-04`
- **目标**：建立支持事务、外键、WAL、busy timeout 和临时测试数据库的数据层。
- **涉及文件**：
  - `backend/src/se_mentor/db/base.py`
  - `backend/src/se_mentor/db/session.py`
  - `backend/alembic.ini`
  - `backend/migrations/env.py`
  - `backend/tests/db/test_session.py`
- **预期实现要点**：
  - SQLAlchemy 2.0 typed models
  - 异常自动 rollback
  - SQLite foreign_keys、WAL 和 busy_timeout 在每个连接生效
- **将要先写的失败测试**：
  - `test_T007_transaction_rolls_back_and_foreign_key_is_enforced` 先失败。
- **验证步骤**：
  1. Alembic `upgrade head`/`downgrade base` 可执行
  2. 事务异常后无脏数据
  3. 并发读写 smoke test 无数据库锁死
- **依赖**：T002,T005
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T007.xml
  - evidence/diffs/T007.patch
  - `AGENT_LOG.md` 中的 T007 记录
- **Commit**：`未填写`

## T008 — 建立迁移所有权与单一 Head 门禁

- **状态**：[-] 进行中；迁移策略文档和单 Head 检查脚本已建立并通过当前基线验证，尚未满足 T008 完整 DoD。
- **阻塞说明**：依赖 T007 正式完成；尚缺双 Head fixture 测试、矩阵引用、完整 evidence、评审与 commit。
- **Worktree**：`wt-schema`
- **覆盖需求**：`审查 Migration 冲突问题`, `AC-CI`
- **目标**：规定只有 wt-schema 生成正式 Alembic migration，其他 worktree 仅修改独立模型文件；CI 阻止多 Head。
- **涉及文件**：
  - `docs/MIGRATION_POLICY.md`
  - `scripts/check_alembic_heads.py`
  - `tests/meta/test_migration_policy.py`
- **预期实现要点**：
  - 为领域分配迁移编号区间和 owner
  - 检查共享模型文件所有权
  - 合并前要求重新生成或 rebase migration
- **将要先写的失败测试**：
  - `test_T008_alembic_has_exactly_one_head` 先在构造双 head fixture 时失败。
- **验证步骤**：
  1. 脚本能识别双 Head
  2. 文档列出共享文件 owner
  3. 后续所有 schema Task 在矩阵中引用本策略
- **依赖**：T007
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T008.xml
  - evidence/diffs/T008.patch
  - `AGENT_LOG.md` 中的 T008 记录
- **Commit**：`未填写`

# Phase 1 数据模型

## T009 — 项目域数据模型

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-schema`
- **覆盖需求**：`Project`, `ProjectConfig`, `CredentialProfile`, `FR-01`
- **目标**：实现项目、配置版本和凭据 Profile 元数据模型，不保存凭据明文。
- **涉及文件**：
  - `backend/src/se_mentor/models/project.py`
  - `backend/migrations/versions/0010_project_domain.py`
  - `backend/tests/models/test_project_models.py`
- **预期实现要点**：
  - 项目根路径规范化并唯一
  - ProjectConfig 保留版本和生效范围
  - CredentialProfile 只保存 provider、keyring 标识和配置状态
- **将要先写的失败测试**：
  - `test_T009_duplicate_project_path_and_plain_secret_are_rejected` 先失败。
- **验证步骤**：
  1. 模型 round-trip
  2. 唯一约束与索引存在
  3. 数据库导出中不存在 fake secret
- **依赖**：T008
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T009.xml
  - evidence/diffs/T009.patch
  - `AGENT_LOG.md` 中的 T009 记录
- **Commit**：`未填写`

## T010 — 任务与提案域数据模型

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-schema`
- **覆盖需求**：`ChangeTask`, `ChangeProposal`, `TaskIteration`, `FR-02`, `FR-05`
- **目标**：实现任务状态、提案版本和迭代记录。
- **涉及文件**：
  - `backend/src/se_mentor/models/task.py`
  - `backend/migrations/versions/0020_task_domain.py`
  - `backend/tests/models/test_task_models.py`
- **预期实现要点**：
  - ChangeTask 保存 baseRevision、计数、预算和活动 proposalId
  - ChangeProposal 不可原地覆盖，使用 version/supersedes
  - TaskIteration 保存输入摘要、输出和进展状态
- **将要先写的失败测试**：
  - `test_T010_proposal_v1_cannot_be_overwritten_and_negative_counts_fail` 先失败。
- **验证步骤**：
  1. 非法状态与负计数被拒绝
  2. V2 激活时 V1 保留为 SUPERSEDED
  3. 索引覆盖 projectId/status/createdAt
- **依赖**：T009
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T010.xml
  - evidence/diffs/T010.patch
  - `AGENT_LOG.md` 中的 T010 记录
- **Commit**：`未填写`

## T011 — LLM 与动作域数据模型

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-schema`
- **覆盖需求**：`LLMCall`, `AgentAction`, `FR-05-01`, `NFR-OBS-05`
- **目标**：持久化每次 Provider 调用和结构化动作解析状态。
- **涉及文件**：
  - `backend/src/se_mentor/models/llm.py`
  - `backend/migrations/versions/0030_llm_action.py`
  - `backend/tests/models/test_llm_action_models.py`
- **预期实现要点**：
  - LLMCall 记录模型、provider、token、耗时、错误和解析状态
  - AgentAction 绑定 iteration、类型、参数摘要、状态
  - 不保存完整 Secret 或无界 Prompt
- **将要先写的失败测试**：
  - `test_T011_llm_call_requires_model_token_and_parse_status` 先失败。
- **验证步骤**：
  1. round-trip 与外键测试
  2. Prompt 仅保存脱敏摘要或 artifact 引用
  3. 同一 iteration 动作顺序唯一
- **依赖**：T010
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T011.xml
  - evidence/diffs/T011.patch
  - `AGENT_LOG.md` 中的 T011 记录
- **Commit**：`未填写`

## T012 — 影响分析与治理域数据模型

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-schema`
- **覆盖需求**：`ImpactReport`, `GovernanceDecision`, `GovernanceRule`, `GovernanceRuleHit`, `FR-04`, `FR-06`
- **目标**：实现影响报告、规则、命中和不可覆盖的治理决策记录。
- **涉及文件**：
  - `backend/src/se_mentor/models/governance.py`
  - `backend/migrations/versions/0040_governance.py`
  - `backend/tests/models/test_governance_models.py`
- **预期实现要点**：
  - 规则包含 effect、priority、patterns、conditions、overridable、version
  - Decision 绑定 proposalHash、revision、规则版本和 evidence
  - RuleHit 不允许引用不存在规则
- **将要先写的失败测试**：
  - `test_T012_deny_hard_rule_cannot_be_overridable` 先失败。
- **验证步骤**：
  1. 约束和索引测试
  2. Decision 历史不可更新
  3. evidence 引用完整性测试
- **依赖**：T011
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T012.xml
  - evidence/diffs/T012.patch
  - `AGENT_LOG.md` 中的 T012 记录
- **Commit**：`未填写`

## T013 — 审批与执行策略域数据模型

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-schema`
- **覆盖需求**：`ApprovalRequest`, `ApprovalDecision`, `ExecutionPolicy`, `FR-06-03～05`
- **目标**：实现真实审批记录、临时授权和可执行策略数据结构。
- **涉及文件**：
  - `backend/src/se_mentor/models/approval.py`
  - `backend/migrations/versions/0050_approval_policy.py`
  - `backend/tests/models/test_approval_policy_models.py`
- **预期实现要点**：
  - ApprovalRequest 绑定 task/action/decisionVersion/proposalHash
  - ApprovalDecision 追加写入并记录 approver、范围、期限
  - ExecutionPolicy 保存 read/write/protected paths、命令、网络、资源上限和失效条件
- **将要先写的失败测试**：
  - `test_T013_approval_for_old_proposal_cannot_attach_to_new_policy` 先失败。
- **验证步骤**：
  1. 审批与策略外键测试
  2. 过期时间和作用域约束
  3. BLOCK 决策无法关联 ACTIVE 策略
- **依赖**：T012
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T013.xml
  - evidence/diffs/T013.patch
  - `AGENT_LOG.md` 中的 T013 记录
- **Commit**：`未填写`

## T014 — 工具、事务、备份、文件变化与锁模型

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-schema`
- **覆盖需求**：`ToolExecution`, `TaskTransaction`, `BackupEntry`, `FileChange`, `WorkspaceLock`, `FR-07`, `NFR-SEC-03～04`
- **目标**：为受控工具和可恢复写入建立完整持久化模型。
- **涉及文件**：
  - `backend/src/se_mentor/models/execution.py`
  - `backend/migrations/versions/0060_execution_transaction.py`
  - `backend/tests/models/test_execution_models.py`
- **预期实现要点**：
  - 事务状态 PREPARED/APPLYING/COMMITTED/ROLLED_BACK/CONFLICT
  - BackupEntry 保存原 hash、备份路径和文件类型
  - FileChange 区分 CREATE/MODIFY/DELETE 并绑定 AgentAction
- **将要先写的失败测试**：
  - `test_T014_committed_transaction_requires_manifest_and_active_write_lock` 先失败。
- **验证步骤**：
  1. 跨实体约束测试
  2. 同项目只允许一个活动 WRITE 锁
  3. 文件变化可反向追到 ToolExecution 和 AgentAction
- **依赖**：T013
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T014.xml
  - evidence/diffs/T014.patch
  - `AGENT_LOG.md` 中的 T014 记录
- **Commit**：`未填写`

## T015 — 验证、反馈与进展模型

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-schema`
- **覆盖需求**：`ValidationPlan`, `ValidationRun`, `FeedbackSignal`, `ProgressEvent`, `FR-08`, `NFR-OBS-07`
- **目标**：实现验证计划、每次执行、统一反馈和语义进展事件。
- **涉及文件**：
  - `backend/src/se_mentor/models/validation.py`
  - `backend/migrations/versions/0070_validation_feedback.py`
  - `backend/tests/models/test_validation_models.py`
- **预期实现要点**：
  - ValidationPlan 版本化并绑定 proposal/policy
  - ValidationRun 记录命令、退出码、类型、失败类别和日志引用
  - FeedbackSignal 与 ProgressEvent 使用共享枚举
- **将要先写的失败测试**：
  - `test_T015_passed_validation_requires_zero_exit_and_no_required_failure` 先失败。
- **验证步骤**：
  1. 合法/非法状态矩阵
  2. 同一计划运行顺序稳定
  3. 失败类别和 raw log 采用受控 artifact 路径
- **依赖**：T014
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T015.xml
  - evidence/diffs/T015.patch
  - `AGENT_LOG.md` 中的 T015 记录
- **Commit**：`未填写`

## T016 — 工程知识域数据模型

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-schema`
- **覆盖需求**：`EngineeringKnowledge`, `KnowledgeSignature`, `KnowledgeSource`, `KnowledgeRelation`, `FR-09`
- **目标**：实现有来源、版本、状态、适用范围和冲突关系的软件演化知识。
- **涉及文件**：
  - `backend/src/se_mentor/models/knowledge.py`
  - `backend/migrations/versions/0080_knowledge.py`
  - `backend/tests/models/test_knowledge_models.py`
- **预期实现要点**：
  - 支持 CANDIDATE/VERIFIED/REVIEWED/FAILED_EXPERIENCE/CONFLICTING/DEPRECATED/STALE
  - 签名、来源、关系独立建模
  - 禁止跨项目关系和静默覆盖
- **将要先写的失败测试**：
  - `test_T016_unverified_llm_summary_cannot_be_verified_without_evidence` 先失败。
- **验证步骤**：
  1. 状态机约束
  2. supersedes/conflicts_with 关系测试
  3. 默认检索索引覆盖 project/type/status
- **依赖**：T015
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T016.xml
  - evidence/diffs/T016.patch
  - `AGENT_LOG.md` 中的 T016 记录
- **Commit**：`未填写`

## T017 — 代码索引域数据模型

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-schema`
- **覆盖需求**：`CodeIndex`, `CodeSymbol`, `FR-03-01`
- **目标**：实现 P0 文件与符号级索引及依赖关系存储。
- **涉及文件**：
  - `backend/src/se_mentor/models/code_index.py`
  - `backend/migrations/versions/0090_code_index.py`
  - `backend/tests/models/test_code_index_models.py`
- **预期实现要点**：
  - CodeIndex 绑定 project/revision/language/status
  - CodeSymbol 保存 module/class/function/method/API/DTO/table/test 等 kind
  - 关系保存 IMPORTS/CALLS/TESTS/SERIALIZES/READS_TABLE/WRITES_TABLE
- **将要先写的失败测试**：
  - `test_T017_symbol_relation_cannot_cross_project_or_revision` 先失败。
- **验证步骤**：
  1. 唯一约束和索引
  2. 同 revision 重建幂等
  3. 删除旧索引不删除审计和历史报告引用
- **依赖**：T016
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T017.xml
  - evidence/diffs/T017.patch
  - `AGENT_LOG.md` 中的 T017 记录
- **Commit**：`未填写`

## T018 — 审计、告警与保留策略模型

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-schema`
- **覆盖需求**：`AuditEvent`, `NFR-OBS-10～11`, `数据删除与保留策略`
- **目标**：实现追加写入审计、告警事件和不可物理删除的核心数据保留规则。
- **涉及文件**：
  - `backend/src/se_mentor/models/audit.py`
  - `backend/migrations/versions/0100_audit_alert.py`
  - `backend/tests/models/test_audit_models.py`
  - `docs/DATA_RETENTION.md`
- **预期实现要点**：
  - AuditEvent 绑定 task/correlation/actor/type/payload 摘要
  - P0 使用 append-only 与应用层/数据库权限保护；Hash 链列为 P1 可选增强
  - AlertEvent 记录级别、处置状态和 evidence
- **将要先写的失败测试**：
  - `test_T018_audit_update_delete_is_rejected_and_alert_requires_task_or_system_scope` 先失败。
- **验证步骤**：
  1. 尝试更新/删除审计记录应失败
  2. 保留策略覆盖不可删与可清理数据
  3. Alembic 最终只有一个 Head
- **依赖**：T017
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T018.xml
  - evidence/diffs/T018.patch
  - `AGENT_LOG.md` 中的 T018 记录
- **Commit**：`未填写`

# Phase 2 项目与提案

## T019 — 项目路径授权与注册服务

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-project`
- **覆盖需求**：`FR-01-01`, `NFR-SEC-01`, `AC-FR01-01`
- **目标**：只允许注册存在、可读、明确授权且不能通过符号链接逃逸的 Git 项目。
- **涉及文件**：
  - `backend/src/se_mentor/projects/project_service.py`
  - `backend/src/se_mentor/projects/project_repository.py`
  - `backend/tests/projects/test_project_registration.py`
- **预期实现要点**：
  - 规范化绝对路径并解析 realpath
  - 检查 Git 仓库和当前 revision
  - 注册过程不写入用户仓库
- **将要先写的失败测试**：
  - `test_AC_FR01_01_rejects_non_git_outside_and_duplicate_project` 先失败。
- **验证步骤**：
  1. 临时 Git 仓库注册成功
  2. 非 Git、不可读、重复和符号链接逃逸失败
  3. 数据库记录的 baseRevision 正确
- **依赖**：T009,T018
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T019.xml
  - evidence/diffs/T019.patch
  - `AGENT_LOG.md` 中的 T019 记录
- **Commit**：`未填写`

## T020 — 识别语言、构建工具和测试框架

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-project`
- **覆盖需求**：`FR-01-01`, `OQ-02`, `OQ-03`
- **目标**：P0 确定性识别 Python 主项目和 TypeScript 辅助项目的工具链，不自动执行未知命令。
- **涉及文件**：
  - `backend/src/se_mentor/projects/toolchain_detector.py`
  - `backend/tests/projects/test_toolchain_detector.py`
- **预期实现要点**：
  - 检测 pyproject/requirements/package.json/pytest/vitest 等
  - 输出置信度和未确认项
  - 未知工具链要求用户配置而非猜测
- **将要先写的失败测试**：
  - `test_T020_unknown_toolchain_is_reported_not_executed` 先失败。
- **验证步骤**：
  1. Python、TypeScript、混合和未知 fixture
  2. 大型仓库上限产生明确状态
  3. 检测过程只读且不联网
- **依赖**：T019
- **可并行性**：可与 T021 并行
- **预期证据**：
  - evidence/test-reports/T020.xml
  - evidence/diffs/T020.patch
  - `AGENT_LOG.md` 中的 T020 记录
- **Commit**：`未填写`

## T021 — 计算并持久化项目有效配置

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-project`
- **覆盖需求**：`FR-01-02`, `AC-FR01-02`
- **目标**：把系统、运行 Profile、项目和任务配置合成为可审计的 effective config。
- **涉及文件**：
  - `backend/src/se_mentor/projects/config_service.py`
  - `backend/tests/projects/test_effective_config.py`
- **预期实现要点**：
  - 保存 config version 与 hash
  - 冲突采用更严格值并记录来源
  - 必要配置缺失时项目可注册但任务不可启动
- **将要先写的失败测试**：
  - `test_AC_FR01_02_more_restrictive_config_wins_and_missing_required_blocks_task` 先失败。
- **验证步骤**：
  1. 配置来源可解释
  2. 任务引用创建时版本
  3. CLOUD_DEMO 配置无法被项目文件放宽
- **依赖**：T005,T009,T019
- **可并行性**：可与 T020 并行
- **预期证据**：
  - evidence/test-reports/T021.xml
  - evidence/diffs/T021.patch
  - `AGENT_LOG.md` 中的 T021 记录
- **Commit**：`未填写`

## T022 — 原子获取项目 READ/WRITE 锁

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-project`
- **覆盖需求**：`FR-01-03`, `NFR-SEC-03`, `AC-FR01-03`
- **目标**：以数据库事务原子获取锁，保证同项目同一时间最多一个活动写任务。
- **涉及文件**：
  - `backend/src/se_mentor/workspace/lock_service.py`
  - `backend/tests/workspace/test_lock_acquire.py`
- **预期实现要点**：
  - WRITE 与任何 ACTIVE 锁冲突，READ 可共享
  - 记录 ownerInstance、taskId、heartbeat、version
  - 锁获取失败不得创建执行事务
- **将要先写的失败测试**：
  - `test_AC_FR01_03_two_concurrent_writers_only_one_succeeds` 先失败。
- **验证步骤**：
  1. 并发测试
  2. READ/WRITE 组合矩阵
  3. 锁冲突返回稳定错误码
- **依赖**：T014,T019
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T022.xml
  - evidence/diffs/T022.patch
  - `AGENT_LOG.md` 中的 T022 记录
- **Commit**：`未填写`

## T023 — 锁心跳、过期、释放与强制恢复

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-project`
- **覆盖需求**：`FR-01-04`, `AC-FR01-04～05`, `NFR-USA-08`
- **目标**：维护锁生命周期，并在异常过期时阻止新写任务直到完成恢复判断。
- **涉及文件**：
  - `backend/src/se_mentor/workspace/lock_maintenance.py`
  - `backend/tests/workspace/test_lock_lifecycle.py`
- **预期实现要点**：
  - 心跳使用乐观锁版本
  - 正常终态释放锁
  - 过期锁生成告警并进入 RECOVERY_REQUIRED，不直接无条件删除
- **将要先写的失败测试**：
  - `test_T023_expired_lock_with_unfinished_transaction_blocks_new_writer` 先失败。
- **验证步骤**：
  1. 心跳更新和版本冲突
  2. 异常终止场景
  3. 强制释放必须记录 actor、理由和审计
- **依赖**：T022,T018
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T023.xml
  - evidence/diffs/T023.patch
  - `AGENT_LOG.md` 中的 T023 记录
- **Commit**：`未填写`

## T024 — 创建任务与严格状态机

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-project`
- **覆盖需求**：`FR-02-01`, `FR-05-06`, `数据模型任务执行约束`
- **目标**：实现任务创建、预算初始化和从 CREATED 到各阶段/终态的合法迁移。
- **涉及文件**：
  - `backend/src/se_mentor/tasks/state_machine.py`
  - `backend/src/se_mentor/tasks/task_service.py`
  - `backend/tests/tasks/test_task_state_machine.py`
- **预期实现要点**：
  - LLM 和工具不能直接改状态
  - BLOCK、WARN_PENDING、PAUSED、STAGNATED、INCONCLUSIVE、RECOVERY_REQUIRED 使用不同状态
  - 每次迁移写审计
- **将要先写的失败测试**：
  - `test_T024_created_cannot_jump_to_completed_and_blocked_cannot_execute` 先失败。
- **验证步骤**：
  1. 覆盖合法迁移表
  2. 非法迁移无副作用
  3. 重复命令幂等
- **依赖**：T010,T018,T021
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T024.xml
  - evidence/diffs/T024.patch
  - `AGENT_LOG.md` 中的 T024 记录
- **Commit**：`未填写`

## T025 — 生成结构化 Change Proposal

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-project`
- **覆盖需求**：`FR-02-02`, `US-01 AC-01`
- **目标**：把自然语言请求转为目标、当前问题、预期行为、范围、非目标、假设、风险、验收和执行边界。
- **涉及文件**：
  - `backend/src/se_mentor/proposals/generator.py`
  - `backend/src/se_mentor/llm/prompts/proposal.py`
  - `backend/tests/proposals/test_proposal_generation.py`
- **预期实现要点**：
  - LLM 输出通过严格 Schema
  - 推测与用户事实分开
  - 生成阶段不能调用写工具或 Shell
- **将要先写的失败测试**：
  - `test_AC_FR02_01_generates_required_proposal_fields_without_side_effects` 先失败。
- **验证步骤**：
  1. Mock LLM 确定性测试
  2. 非法 JSON/未知字段进入可诊断解析失败
  3. 提案生成不改变工作区 hash
- **依赖**：T010,T053,T056
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T025.xml
  - evidence/diffs/T025.patch
  - `AGENT_LOG.md` 中的 T025 记录
- **Commit**：`未填写`

## T026 — 评估提案完整性并进入 NEEDS_INFORMATION

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-project`
- **覆盖需求**：`FR-02-03`, `US-01 AC-02`, `AC-FR02-02`
- **目标**：检测目标行为、范围、关键约束和验收条件缺失，阻止不完整提案进入影响分析或高风险执行。
- **涉及文件**：
  - `backend/src/se_mentor/proposals/completeness.py`
  - `backend/tests/proposals/test_completeness.py`
- **预期实现要点**：
  - 使用确定性必填规则加可解释缺口列表
  - 缺口包含影响和建议补充内容
  - 不能用 LLM 自信度替代完整性
- **将要先写的失败测试**：
  - `test_AC_FR02_02_incomplete_proposal_cannot_enter_analysis` 先失败。
- **验证步骤**：
  1. 完整/不完整表驱动测试
  2. 任务状态进入 NEEDS_INFORMATION
  3. 补充信息后可创建新 proposal version
- **依赖**：T025
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T026.xml
  - evidence/diffs/T026.patch
  - `AGENT_LOG.md` 中的 T026 记录
- **Commit**：`未填写`

## T027 — 提案审查、修改、确认与版本失效

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-project`
- **覆盖需求**：`FR-02-04`, `US-01 AC-03`, `AC-FR02-03`
- **目标**：支持用户确认、修改、拒绝提案；V2 激活后 V1 保留并使旧影响报告、治理、策略、审批和验证计划失效。
- **涉及文件**：
  - `backend/src/se_mentor/proposals/review_service.py`
  - `backend/tests/proposals/test_proposal_versioning.py`
- **预期实现要点**：
  - 确认动作记录 actor 和时间
  - 修改只能创建新版本
  - 拒绝提案终止或返回任务编辑态
- **将要先写的失败测试**：
  - `test_AC_FR02_03_v2_supersedes_v1_and_invalidates_downstream_artifacts` 先失败。
- **验证步骤**：
  1. 检查所有下游对象失效
  2. V1 数据不可更新覆盖
  3. 未确认提案不可启动写执行
- **依赖**：T026,T012,T013,T015
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T027.xml
  - evidence/diffs/T027.patch
  - `AGENT_LOG.md` 中的 T027 记录
- **Commit**：`未填写`

# Phase 3 索引与上下文

## T028 — 安全文件清单与路径策略

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-index`
- **覆盖需求**：`FR-03-01`, `NFR-SEC-01`, `NFR-SEC-08`
- **目标**：构建受 `.gitignore` 和敏感文件规则约束的项目文件清单。
- **涉及文件**：
  - `backend/src/se_mentor/indexing/file_inventory.py`
  - `backend/src/se_mentor/security/path_policy.py`
  - `backend/tests/indexing/test_file_inventory.py`
- **预期实现要点**：
  - 排除凭据、二进制、备份、大文件和项目外 realpath
  - 保存相对路径、大小、mtime、hash、Git 状态
  - 限制文件数和总大小
- **将要先写的失败测试**：
  - `test_T028_dotenv_binary_large_and_symlink_escape_are_excluded` 先失败。
- **验证步骤**：
  1. 临时仓库清单测试
  2. 单文件变化只更新对应 hash
  3. 性能 fixture 达上限时返回明确限制而非崩溃
- **依赖**：T019,T020
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T028.xml
  - evidence/diffs/T028.patch
  - `AGENT_LOG.md` 中的 T028 记录
- **Commit**：`未填写`

## T029 — 实现 LIST_DIRECTORY、READ_FILE 与 SEARCH_CODE 核心

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-index`
- **覆盖需求**：`FR-03-02`, `FR-07-02`, `FR-07-03`
- **目标**：提供稳定、截断、带行号和证据引用的只读能力。
- **涉及文件**：
  - `backend/src/se_mentor/readers/file_reader.py`
  - `backend/src/se_mentor/readers/code_search.py`
  - `backend/tests/readers/`
- **预期实现要点**：
  - 所有输入先过 PathPolicy
  - 二进制只返回元数据
  - 搜索结果稳定排序并限制结果数、字符数
- **将要先写的失败测试**：
  - `test_T029_read_search_reject_sensitive_and_return_line_evidence` 先失败。
- **验证步骤**：
  1. 路径与截断测试
  2. 搜索重复运行顺序一致
  3. 返回 EvidenceRef 可被影响报告引用
- **依赖**：T028,T004
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T029.xml
  - evidence/diffs/T029.patch
  - `AGENT_LOG.md` 中的 T029 记录
- **Commit**：`未填写`

## T030 — 建立 Python 文件与符号索引

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-index`
- **覆盖需求**：`FR-03-01`, `CodeIndex`, `CodeSymbol`
- **目标**：P0 使用 Python AST 提取模块、类、函数、方法、装饰器 API、导入和测试符号；TypeScript 仅文件级辅助索引。
- **涉及文件**：
  - `backend/src/se_mentor/indexing/python_indexer.py`
  - `backend/src/se_mentor/indexing/index_service.py`
  - `backend/tests/indexing/test_python_indexer.py`
- **预期实现要点**：
  - 语法错误降级为文件索引并记录错误
  - 索引绑定 Git revision
  - 同 revision 重建幂等
- **将要先写的失败测试**：
  - `test_T030_extracts_symbols_api_and_tests_and_handles_syntax_error` 先失败。
- **验证步骤**：
  1. fixture 覆盖类、函数、FastAPI route、pytest test
  2. 数据库关系正确
  3. TypeScript 文件明确标为 FILE_LEVEL
- **依赖**：T017,T028
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T030.xml
  - evidence/diffs/T030.patch
  - `AGENT_LOG.md` 中的 T030 记录
- **Commit**：`未填写`

## T031 — 提取 P0 依赖关系与测试关联

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-index`
- **覆盖需求**：`FR-04-03`, `FR-04-04`, `ImpactNode 关系`
- **目标**：从 Python AST 和约定提取 IMPORTS、CALLS、TESTS、SERIALIZES、READS_TABLE、WRITES_TABLE 的确定性关系。
- **涉及文件**：
  - `backend/src/se_mentor/indexing/relation_extractor.py`
  - `backend/tests/indexing/test_relations.py`
- **预期实现要点**：
  - 无法确定的关系不伪造，保存 certainty
  - 跨文件符号解析失败时保留 unresolved edge
  - P1 全语言图不纳入 P0 完成条件
- **将要先写的失败测试**：
  - `test_T031_direct_import_call_and_test_edges_are_created_without_false_cross_project_edges` 先失败。
- **验证步骤**：
  1. 关系 fixture
  2. 未解析边可查询
  3. 影响分析可按一跳/多跳读取
- **依赖**：T030
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T031.xml
  - evidence/diffs/T031.patch
  - `AGENT_LOG.md` 中的 T031 记录
- **Commit**：`未填写`

## T032 — Git 基线、状态、Diff、历史与外部变化检测

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-index`
- **覆盖需求**：`Git 反馈`, `FR-07`, `OQ-15`, `OQ-16`
- **目标**：提供只读 Git 能力，区分用户原有修改、Agent 修改和外部变化；P0 不 commit/push。
- **涉及文件**：
  - `backend/src/se_mentor/git/git_service.py`
  - `backend/tests/git/test_git_service.py`
- **预期实现要点**：
  - 记录 base revision、初始 status 和文件 hash
  - 生成 scoped diff 与指定文件历史
  - 检测任务期间外部变化
- **将要先写的失败测试**：
  - `test_T032_preserves_preexisting_changes_and_detects_external_modification` 先失败。
- **验证步骤**：
  1. 干净与脏工作区 fixture
  2. 未跟踪文件处理
  3. 确认没有 commit/push/rebase 方法
- **依赖**：T019,T028
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T032.xml
  - evidence/diffs/T032.patch
  - `AGENT_LOG.md` 中的 T032 记录
- **Commit**：`未填写`

## T033 — 构建最小充分 ContextPackage

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-index`
- **覆盖需求**：`FR-03-03`, `AC-FR03-01`, `NFR-SEC-09`
- **目标**：按目标、策略、代码、知识、最近反馈和未确认项组装最小上下文，不灌入整个仓库。
- **涉及文件**：
  - `backend/src/se_mentor/context/context_builder.py`
  - `backend/tests/context/test_context_builder.py`
- **预期实现要点**：
  - 预算分区并优先保留 DENY_HARD、ExecutionPolicy 和当前错误
  - 仓库内容标记为 UNTRUSTED_DATA
  - 记录被丢弃项和理由
- **将要先写的失败测试**：
  - `test_AC_FR03_01_context_is_minimal_and_preserves_governance_content` 先失败。
- **验证步骤**：
  1. 大量无关文件 fixture
  2. Secret 扫描
  3. 上下文摘要可审计但不含完整敏感源码
- **依赖**：T029,T035,T049
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T033.xml
  - evidence/diffs/T033.patch
  - `AGENT_LOG.md` 中的 T033 记录
- **Commit**：`未填写`

## T034 — Provider 前 Token 估算、压缩与 PAUSED

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-index`
- **覆盖需求**：`FR-03-04`, `AC-FR03-02～03`, `NFR-PERF-04`
- **目标**：每次 Provider 调用前计算输入、输出预留和安全余量；超限时去重、摘要、裁剪，关键内容仍超限则暂停。
- **涉及文件**：
  - `backend/src/se_mentor/context/token_budget.py`
  - `backend/tests/context/test_token_budget.py`
- **预期实现要点**：
  - Mock 和真实 Provider 均走同一预算接口
  - 压缩顺序固定且可解释
  - 超限时绝不发送 Provider 请求
- **将要先写的失败测试**：
  - `test_AC_FR03_03_over_budget_pauses_before_provider_call` 先失败。
- **验证步骤**：
  1. spy 断言 Provider 未调用
  2. LLMCall 保存估算与实际 token
  3. 关键规则、策略、最近错误始终保留
- **依赖**：T033,T053
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T034.xml
  - evidence/diffs/T034.patch
  - `AGENT_LOG.md` 中的 T034 记录
- **Commit**：`未填写`

# Phase 4 知识与影响

## T035 — 工程知识仓储与确定性检索

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-knowledge`
- **覆盖需求**：`FR-04-01`, `AC-FR04-01～02`
- **目标**：按项目、类型、状态、路径、关键词和证据重合检索工程知识。
- **涉及文件**：
  - `backend/src/se_mentor/knowledge/repository.py`
  - `backend/src/se_mentor/knowledge/retrieval.py`
  - `backend/tests/knowledge/test_retrieval.py`
- **预期实现要点**：
  - 项目隔离
  - active/fresh 优先，stale 降权
  - 返回命中原因，不只给分数
- **将要先写的失败测试**：
  - `test_T035_direct_path_verified_knowledge_ranks_before_stale_keyword_match` 先失败。
- **验证步骤**：
  1. 固定数据重复排序一致
  2. 跨项目查询为空
  3. 失败经验可检索但不能当成功规则
- **依赖**：T016,T030
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T035.xml
  - evidence/diffs/T035.patch
  - `AGENT_LOG.md` 中的 T035 记录
- **Commit**：`未填写`

## T036 — 生成文件、符号与 AST 知识签名

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-knowledge`
- **覆盖需求**：`FR-09-02`, `KnowledgeSignature`
- **目标**：为代码相关知识生成 revision、文件 hash、symbol hash 和可选 AST hash。
- **涉及文件**：
  - `backend/src/se_mentor/knowledge/signature.py`
  - `backend/tests/knowledge/test_signature.py`
- **预期实现要点**：
  - 空白/注释变化不改变 AST 结构签名
  - 语义结构变化改变签名
  - 解析失败明确降级为内容 hash
- **将要先写的失败测试**：
  - `test_T036_comment_only_change_keeps_ast_signature_but_logic_change_does_not` 先失败。
- **验证步骤**：
  1. Python fixture
  2. 不存在 symbol 返回 MISSING
  3. 签名不读取项目外文件
- **依赖**：T030,T035
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T036.xml
  - evidence/diffs/T036.patch
  - `AGENT_LOG.md` 中的 T036 记录
- **Commit**：`未填写`

## T037 — 知识新鲜度与重建队列

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-knowledge`
- **覆盖需求**：`FR-04-02`, `AC-FR04-03`, `E2E-08`
- **目标**：将知识分类为 FRESH、DRIFTED、STALE、MISSING、UNKNOWN，并在失效时进入重建队列。
- **涉及文件**：
  - `backend/src/se_mentor/knowledge/freshness.py`
  - `backend/src/se_mentor/knowledge/refresh_queue.py`
  - `backend/tests/knowledge/test_freshness.py`
- **预期实现要点**：
  - STALE 不能支持自动 ALLOW
  - 无关文件变化不误伤
  - 失效产生告警
- **将要先写的失败测试**：
  - `test_T037_changed_symbol_marks_knowledge_stale_and_blocks_auto_allow` 先失败。
- **验证步骤**：
  1. 所有 freshness 状态覆盖
  2. 重建队列幂等
  3. 告警和审计记录存在
- **依赖**：T036,T018
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T037.xml
  - evidence/diffs/T037.patch
  - `AGENT_LOG.md` 中的 T037 记录
- **Commit**：`未填写`

## T038 — 知识冲突检测与状态转换

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-knowledge`
- **覆盖需求**：`FR-09-04`, `US-06 AC-03`, `审查 P0-09`
- **目标**：检测新旧知识在同一适用范围内的矛盾，禁止静默覆盖。
- **涉及文件**：
  - `backend/src/se_mentor/knowledge/conflicts.py`
  - `backend/tests/knowledge/test_conflicts.py`
- **预期实现要点**：
  - 冲突创建 KnowledgeRelation(CONFLICTS_WITH)
  - 旧知识转 CONFLICTING/DEPRECATED/SUPERSEDED 需证据
  - 高风险治理遇冲突默认 WARN 或 BLOCK
- **将要先写的失败测试**：
  - `test_T038_conflicting_new_knowledge_does_not_overwrite_old_record` 先失败。
- **验证步骤**：
  1. 冲突、替代、无关三类 fixture
  2. 历史版本可查询
  3. 人工审核后状态迁移合法
- **依赖**：T035,T037
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T038.xml
  - evidence/diffs/T038.patch
  - `AGENT_LOG.md` 中的 T038 记录
- **Commit**：`未填写`

## T039 — 候选知识提取与可信度晋级

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-knowledge`
- **覆盖需求**：`FR-09-01`, `FR-09-03`, `US-06 AC-01/04`
- **目标**：从任务结果提取候选知识，并仅在代码证据、通过验证或人工审核满足决策条件时晋级。
- **涉及文件**：
  - `backend/src/se_mentor/knowledge/extractor.py`
  - `backend/src/se_mentor/knowledge/promotion.py`
  - `backend/tests/knowledge/test_promotion.py`
- **预期实现要点**：
  - LLM 总结默认 CANDIDATE
  - 回滚任务不生成 active 架构事实
  - VERIFIED 条件按 T000 决策编码
- **将要先写的失败测试**：
  - `test_T039_llm_candidate_without_evidence_cannot_be_verified` 先失败。
- **验证步骤**：
  1. 成功、未验证、回滚和人工审核场景
  2. 来源任务与证据完整
  3. 敏感内容过滤
- **依赖**：T038,T053
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T039.xml
  - evidence/diffs/T039.patch
  - `AGENT_LOG.md` 中的 T039 记录
- **Commit**：`未填写`

## T040 — 确定性直接影响分析

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-knowledge`
- **覆盖需求**：`FR-04-03`, `US-02 AC-02`
- **目标**：根据候选文件、符号索引、Git diff 和提案范围识别直接受影响文件、符号、API、DTO、表和测试。
- **涉及文件**：
  - `backend/src/se_mentor/impact/direct.py`
  - `backend/tests/impact/test_direct_impact.py`
- **预期实现要点**：
  - 事实与 hypothesis 分开
  - 每项直接影响有 EvidenceRef
  - 未知语言只提供文件级结果
- **将要先写的失败测试**：
  - `test_T040_field_change_identifies_direct_dto_api_table_and_test_evidence` 先失败。
- **验证步骤**：
  1. 跨层 fixture
  2. 不存在证据不得输出 confirmed
  3. 结果排序稳定
- **依赖**：T027,T031,T032
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T040.xml
  - evidence/diffs/T040.patch
  - `AGENT_LOG.md` 中的 T040 记录
- **Commit**：`未填写`

## T041 — 确定性间接影响扩展

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-knowledge`
- **覆盖需求**：`FR-04-04`, `US-02 AC-02`
- **目标**：沿索引关系和已验证知识扩展上游调用、下游依赖、配置、部署和文档影响。
- **涉及文件**：
  - `backend/src/se_mentor/impact/indirect.py`
  - `backend/tests/impact/test_indirect_impact.py`
- **预期实现要点**：
  - 限制深度和节点数量
  - 循环依赖不无限遍历
  - DRIFTED/STALE 知识只作为辅助并标注
- **将要先写的失败测试**：
  - `test_T041_dependency_cycle_terminates_and_marks_uncertain_edges` 先失败。
- **验证步骤**：
  1. 一跳、多跳、循环和无关系场景
  2. 记录为何扩展该节点
  3. 超限时报告 truncated 和 unknowns
- **依赖**：T037,T040
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T041.xml
  - evidence/diffs/T041.patch
  - `AGENT_LOG.md` 中的 T041 记录
- **Commit**：`未填写`

## T042 — 组装统一 EvidenceBundle

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-knowledge`
- **覆盖需求**：`治理证据包`, `FR-06`
- **目标**：把当前代码、Git、知识、验证、用户授权、任务范围、未确认假设和外部变化组装为可校验证据包。
- **涉及文件**：
  - `backend/src/se_mentor/evidence/bundle.py`
  - `backend/tests/evidence/test_bundle.py`
- **预期实现要点**：
  - 所有引用必须存在并绑定 revision
  - 证据携带 freshness、confidence、verified
  - 缺关键证据显式列入 unresolved assumptions
- **将要先写的失败测试**：
  - `test_T042_bundle_rejects_missing_or_cross_revision_evidence` 先失败。
- **验证步骤**：
  1. 完整性测试
  2. 序列化脱敏
  3. 同输入 hash 稳定
- **依赖**：T040,T041,T037
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T042.xml
  - evidence/diffs/T042.patch
  - `AGENT_LOG.md` 中的 T042 记录
- **Commit**：`未填写`

## T043 — 生成可追溯 ImpactReport

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-knowledge`
- **覆盖需求**：`FR-04-05`, `US-02 AC-01～04`
- **目标**：将直接/间接影响、历史知识、风险假设和未知项生成结构化报告；LLM 只辅助解释，不创造无证据事实。
- **涉及文件**：
  - `backend/src/se_mentor/impact/report_service.py`
  - `backend/src/se_mentor/llm/prompts/impact.py`
  - `backend/tests/impact/test_report.py`
- **预期实现要点**：
  - 事实、推断、未知项分区
  - 报告 evidence id 全部可解析
  - 输入变化生成新版本并使旧治理失效
- **将要先写的失败测试**：
  - `test_T043_report_rejects_hallucinated_evidence_and_preserves_unknowns` 先失败。
- **验证步骤**：
  1. Mock LLM schema 测试
  2. 跨层示例报告
  3. 旧报告失效测试
- **依赖**：T042,T053,T056
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T043.xml
  - evidence/diffs/T043.patch
  - `AGENT_LOG.md` 中的 T043 记录
- **Commit**：`未填写`

# Phase 5 治理与策略

## T044 — 治理规则仓储、配置合并与版本

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-governance`
- **覆盖需求**：`FR-06-01`, `GovernanceRule`, `NFR-SEC-06`
- **目标**：加载系统、Profile 和项目规则，按更严格优先原则形成任务规则快照。
- **涉及文件**：
  - `backend/src/se_mentor/governance/rule_repository.py`
  - `backend/src/se_mentor/governance/rule_loader.py`
  - `backend/tests/governance/test_rule_loader.py`
- **预期实现要点**：
  - DENY_HARD 不可由项目配置关闭
  - 规则版本与任务绑定
  - 非法 pattern/condition 阻止任务开始
- **将要先写的失败测试**：
  - `test_T044_project_rule_cannot_disable_system_deny_hard` 先失败。
- **验证步骤**：
  1. 合并优先级测试
  2. 规则版本快照
  3. 配置错误返回可操作信息
- **依赖**：T012,T021
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T044.xml
  - evidence/diffs/T044.patch
  - `AGENT_LOG.md` 中的 T044 记录
- **Commit**：`未填写`

## T045 — 危险动作与验证规避预分类

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-governance`
- **覆盖需求**：`FR-06-02`, `NFR-SEC-05`, `FR-08-06`
- **目标**：对路径、命令、网络、凭据、测试、认证、Schema、依赖和部署动作进行确定性风险分类。
- **涉及文件**：
  - `backend/src/se_mentor/governance/action_classifier.py`
  - `backend/tests/governance/test_action_classifier.py`
- **预期实现要点**：
  - SAFE/REQUIRE_APPROVAL/DENY_HARD
  - 支持 PowerShell 和参数化命令变体
  - `|| true`、删断言、批量 skip、缩小测试范围单独标记 VALIDATION_EVASION
- **将要先写的失败测试**：
  - `test_T045_outside_path_recursive_delete_and_validation_bypass_are_deny_or_warn` 先失败。
- **验证步骤**：
  1. 危险命令语料表驱动测试
  2. 正常 pytest/ruff 不误报
  3. 命中规则有解释
- **依赖**：T044,T004
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T045.xml
  - evidence/diffs/T045.patch
  - `AGENT_LOG.md` 中的 T045 记录
- **Commit**：`未填写`

## T046 — ALLOW/WARN/BLOCK 决策与 Deny Override

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-governance`
- **覆盖需求**：`FR-06-02`, `US-03`, `AC-FR06-01～02/05`
- **目标**：结合规则、影响、知识新鲜度、未知项和动作风险生成可解释治理决策。
- **涉及文件**：
  - `backend/src/se_mentor/governance/decision_engine.py`
  - `backend/tests/governance/test_decision_engine.py`
- **预期实现要点**：
  - DENY_HARD 永远优先
  - 知识冲突/关键未知/公共 API 等按规则 WARN
  - ALLOW 必须给出有限范围而非全仓权限
- **将要先写的失败测试**：
  - `test_AC_FR06_05_deny_hard_overrides_llm_allow_and_user_warn` 先失败。
- **验证步骤**：
  1. 三类决策表驱动测试
  2. 相同输入稳定
  3. 规则、证据、解除条件完整
- **依赖**：T043,T045,T038
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T046.xml
  - evidence/diffs/T046.patch
  - `AGENT_LOG.md` 中的 T046 记录
- **Commit**：`未填写`

## T047 — 创建人工审批请求

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-governance`
- **覆盖需求**：`FR-06-03`, `US-03 AC-02`, `E2E-03`
- **目标**：把 WARN 风险转成绑定具体动作、路径、命令、期限和替代方案的审批请求。
- **涉及文件**：
  - `backend/src/se_mentor/approvals/request_service.py`
  - `backend/tests/approvals/test_request.py`
- **预期实现要点**：
  - BLOCK 不创建普通审批
  - 请求绑定 proposalHash、revision、decisionVersion
  - 同动作同版本只存在一个活动请求
- **将要先写的失败测试**：
  - `test_T047_block_creates_no_approval_and_warn_request_is_scope_bound` 先失败。
- **验证步骤**：
  1. 重复创建幂等
  2. 过期时间合法
  3. WebUI 所需摘要字段完整
- **依赖**：T013,T046
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T047.xml
  - evidence/diffs/T047.patch
  - `AGENT_LOG.md` 中的 T047 记录
- **Commit**：`未填写`

## T048 — 处理审批结果与真实性约束

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-governance`
- **覆盖需求**：`FR-06-04`, `NFR-SEC-07`
- **目标**：记录批准、拒绝和撤销；禁止伪造 approver、过期审批和跨任务复用。
- **涉及文件**：
  - `backend/src/se_mentor/approvals/decision_service.py`
  - `backend/tests/approvals/test_decision.py`
- **预期实现要点**：
  - 审批追加写入
  - Deny Hard 永不可批准
  - proposal/revision/decision 变化后审批失效
- **将要先写的失败测试**：
  - `test_T048_fake_expired_or_cross_task_approval_is_rejected` 先失败。
- **验证步骤**：
  1. 批准/拒绝/撤销矩阵
  2. 重复请求幂等
  3. 审计含审批人和范围
- **依赖**：T047,T018
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T048.xml
  - evidence/diffs/T048.patch
  - `AGENT_LOG.md` 中的 T048 记录
- **Commit**：`未填写`

## T049 — 编译 ExecutionPolicy

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-governance`
- **覆盖需求**：`FR-06-05`, `审查 P0-05`, `US-04`
- **目标**：将 GovernanceDecision 和有效审批编译为机器可执行的路径、命令、网络、工具、资源和期限策略。
- **涉及文件**：
  - `backend/src/se_mentor/policy/compiler.py`
  - `backend/tests/policy/test_compiler.py`
- **预期实现要点**：
  - BLOCK 不生成 ACTIVE 策略
  - WARN 未审批的 write/command scope 为空
  - ALLOW 也只开放决策批准范围
- **将要先写的失败测试**：
  - `test_T049_warn_without_approval_produces_no_write_grant` 先失败。
- **验证步骤**：
  1. read/write/protected path 组合
  2. 网络与资源上限
  3. 策略绑定 proposalHash/revision/ruleVersion
- **依赖**：T046,T048,T013
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T049.xml
  - evidence/diffs/T049.patch
  - `AGENT_LOG.md` 中的 T049 记录
- **Commit**：`未填写`

## T050 — 生成并管理 TemporaryGrant

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-governance`
- **覆盖需求**：`临时权限`, `FR-06-04～05`
- **目标**：把批准结果转换为仅适用于当前 task/action 的有限临时授权。
- **涉及文件**：
  - `backend/src/se_mentor/policy/grants.py`
  - `backend/tests/policy/test_grants.py`
- **预期实现要点**：
  - 默认单动作、任务结束失效
  - 不能扩展超过审批请求
  - 代码或提案变化自动失效
- **将要先写的失败测试**：
  - `test_T050_grant_cannot_expand_scope_or_survive_revision_change` 先失败。
- **验证步骤**：
  1. 时效与范围测试
  2. 撤销后立即失效
  3. 不允许覆盖 protected_paths
- **依赖**：T048,T049
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T050.xml
  - evidence/diffs/T050.patch
  - `AGENT_LOG.md` 中的 T050 记录
- **Commit**：`未填写`

## T051 — 工具层 PolicyEnforcer 二次强制检查

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-governance`
- **覆盖需求**：`FR-06-05`, `US-03 AC-04`, `US-04 AC-02～04`
- **目标**：在每次实际工具执行前重新检查工具、参数、路径、命令、网络、锁、事务和临时授权。
- **涉及文件**：
  - `backend/src/se_mentor/policy/enforcer.py`
  - `backend/tests/policy/test_enforcer.py`
- **预期实现要点**：
  - 不信任 Orchestrator 已检查的结论
  - 参数归一化后再匹配策略
  - 拒绝结果结构化并回到治理/重新规划
- **将要先写的失败测试**：
  - `test_T051_dispatcher_cannot_execute_outside_policy_even_if_orchestrator_marks_allowed` 先失败。
- **验证步骤**：
  1. spy 证明 handler 未调用
  2. 路径/命令编码变体
  3. 策略过期实时拒绝
- **依赖**：T049,T050,T022
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T051.xml
  - evidence/diffs/T051.patch
  - `AGENT_LOG.md` 中的 T051 记录
- **Commit**：`未填写`

## T052 — 再治理触发器与下游失效

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-governance`
- **覆盖需求**：`再治理 0.9.5`, `FR-06`, `FR-08`
- **目标**：在范围扩大、外部修改、修正涉及新模块、知识失效、验证发现新影响或审批过期时暂停并重新治理。
- **涉及文件**：
  - `backend/src/se_mentor/governance/regovernance.py`
  - `backend/tests/governance/test_regovernance.py`
- **预期实现要点**：
  - 失效 ImpactReport/Decision/Policy/Grant/ValidationPlan
  - 不得沿用旧写权限
  - 记录触发原因和证据
- **将要先写的失败测试**：
  - `test_T052_new_file_scope_invalidates_policy_before_write` 先失败。
- **验证步骤**：
  1. 所有触发条件表驱动
  2. 无实质变化不重复治理
  3. 任务状态正确进入 ANALYSIS_REQUIRED
- **依赖**：T027,T037,T050,T051
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T052.xml
  - evidence/diffs/T052.patch
  - `AGENT_LOG.md` 中的 T052 记录
- **Commit**：`未填写`

# Phase 6 Harness 与工具

## T053 — LLM Provider 接口与 MockLLMProvider

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`FR-05-01`, `FR-12-01`, `OQ-01`
- **目标**：提供可替换、可取消、记录 usage 的 Provider 接口和脚本化离线 Mock。
- **涉及文件**：
  - `backend/src/se_mentor/llm/base.py`
  - `backend/src/se_mentor/llm/mock.py`
  - `backend/tests/llm/test_mock_provider.py`
- **预期实现要点**：
  - 模型 ID 完全配置化
  - Mock 按调用序号/匹配条件返回
  - 未定义调用明确失败，不静默空响应
- **将要先写的失败测试**：
  - `test_T053_undefined_mock_call_fails_and_script_is_deterministic` 先失败。
- **验证步骤**：
  1. 重复执行一致
  2. usage 写入 LLMCall
  3. 取消和超时接口可 fake
- **依赖**：T011,T006,T034
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T053.xml
  - evidence/diffs/T053.patch
  - `AGENT_LOG.md` 中的 T053 记录
- **Commit**：`未填写`

## T054 — OpenAI Responses API Provider

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`真实 LLM Provider`, `技术选型`
- **目标**：适配 OpenAI Responses API，不让 SDK 细节进入 Agent 核心。
- **涉及文件**：
  - `backend/src/se_mentor/llm/openai_provider.py`
  - `backend/tests/llm/test_openai_provider.py`
- **预期实现要点**：
  - 默认/高复杂度模型通过配置路由
  - 401/429/timeout/invalid response 映射稳定领域错误
  - 测试 mock SDK，不访问公网
- **将要先写的失败测试**：
  - `test_T054_provider_maps_auth_rate_limit_timeout_and_records_usage` 先失败。
- **验证步骤**：
  1. 无真实 Key 单测
  2. 请求前经过 token budget
  3. 发送内容已脱敏且最小化
- **依赖**：T053,T006
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T054.xml
  - evidence/diffs/T054.patch
  - `AGENT_LOG.md` 中的 T054 记录
- **Commit**：`未填写`

## T055 — Prompt Injection 与不可信仓库内容隔离

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`NFR-CRED-08`, `R-LLM-04`, `审查 Prompt Injection 缺口`
- **目标**：把 README、注释、Issue、测试输出等标为不可信数据，确保文本不能生成权限、审批或改变系统规则。
- **涉及文件**：
  - `backend/src/se_mentor/security/prompt_boundary.py`
  - `backend/src/se_mentor/llm/prompts/system.py`
  - `backend/tests/security/test_prompt_injection.py`
- **预期实现要点**：
  - 系统策略和 ExecutionPolicy 通过独立结构通道提供
  - 仓库文本不能覆盖 system message
  - 命令式注入特征产生风险事件但不直接删除内容
- **将要先写的失败测试**：
  - `test_T055_repository_instruction_cannot_grant_shell_or_reveal_secret` 先失败。
- **验证步骤**：
  1. 恶意 README/注释/测试输出 fixture
  2. 即使 Mock LLM 被诱导，PolicyEnforcer 仍阻止副作用
  3. AgentContext 不含凭据
- **依赖**：T051,T053,T033
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T055.xml
  - evidence/diffs/T055.patch
  - `AGENT_LOG.md` 中的 T055 记录
- **Commit**：`未填写`

## T056 — 严格解析 AgentAction

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`FR-05-02`, `FR-12`
- **目标**：只接受共享联合类型：READ_FILE、LIST_DIRECTORY、SEARCH_CODE、GET_GIT_STATUS、GET_DIFF、CREATE_FILE、APPLY_PATCH、DELETE_FILE、RUN_COMMAND、RUN_VALIDATION、REQUEST_APPROVAL、REQUEST_REPLAN、REQUEST_COMPLETE。
- **涉及文件**：
  - `backend/src/se_mentor/agent/action_parser.py`
  - `backend/tests/agent/test_action_parser.py`
- **预期实现要点**：
  - 未知动作/额外字段/非法路径参数拒绝
  - 解析错误形成 FeedbackSignal
  - 自由文本 Shell 不进入工具层
- **将要先写的失败测试**：
  - `test_T056_free_text_shell_unknown_action_and_extra_fields_are_rejected` 先失败。
- **验证步骤**：
  1. 合法动作 round-trip
  2. 恶意嵌套 payload
  3. 连续格式错误计数和告警
- **依赖**：T004,T053
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T056.xml
  - evidence/diffs/T056.patch
  - `AGENT_LOG.md` 中的 T056 记录
- **Commit**：`未填写`

## T057 — 工具注册表与统一 Dispatcher

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`工具原则`, `FR-07`, `FR-11-02`
- **目标**：建立所有工具的唯一调用入口，声明输入 Schema、风险、事务需求、超时和可用 Profile。
- **涉及文件**：
  - `backend/src/se_mentor/tools/registry.py`
  - `backend/src/se_mentor/tools/dispatcher.py`
  - `backend/tests/tools/test_dispatcher.py`
- **预期实现要点**：
  - 先 PolicyEnforcer，后 handler
  - 工具异常统一 ToolResult
  - 每次调用持久化 ToolExecution 与审计
- **将要先写的失败测试**：
  - `test_T057_unregistered_or_denied_tool_never_calls_handler` 先失败。
- **验证步骤**：
  1. spy 验证调用顺序
  2. 超时/异常结果
  3. CLOUD_DEMO 工具集更小
- **依赖**：T051,T056,T014
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T057.xml
  - evidence/diffs/T057.patch
  - `AGENT_LOG.md` 中的 T057 记录
- **Commit**：`未填写`

## T058 — 创建任务事务与备份目录

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`FR-07-01`, `NFR-SEC-04`
- **目标**：在首次副作用前创建事务、基线 manifest 和任务专属备份目录。
- **涉及文件**：
  - `backend/src/se_mentor/transactions/manager.py`
  - `backend/tests/transactions/test_prepare.py`
- **预期实现要点**：
  - 验证 WRITE 锁和 baseRevision
  - 记录用户原有未提交修改
  - 备份目录权限受限且不位于目标仓库可提交路径
- **将要先写的失败测试**：
  - `test_T058_side_effect_requires_active_lock_transaction_and_baseline_manifest` 先失败。
- **验证步骤**：
  1. 干净/脏工作区
  2. 无锁时拒绝
  3. 备份目录与 manifest 一致
- **依赖**：T014,T022,T032,T057
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T058.xml
  - evidence/diffs/T058.patch
  - `AGENT_LOG.md` 中的 T058 记录
- **Commit**：`未填写`

## T059 — 原子 APPLY_PATCH 工具

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`FR-07-04`, `AC-FR07`
- **目标**：对现有文件应用结构化补丁，检查预期 hash、备份、临时文件校验和原子替换。
- **涉及文件**：
  - `backend/src/se_mentor/tools/apply_patch.py`
  - `backend/tests/tools/test_apply_patch.py`
- **预期实现要点**：
  - patch mismatch 或外部变化停止
  - 崩溃前原文件完整
  - 记录 before/after hash 和 diff
- **将要先写的失败测试**：
  - `test_T059_hash_conflict_and_pre_replace_crash_preserve_original_file` 先失败。
- **验证步骤**：
  1. 成功/冲突/编码错误
  2. FileChange 与 BackupEntry
  3. 越界策略拒绝
- **依赖**：T058,T051
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T059.xml
  - evidence/diffs/T059.patch
  - `AGENT_LOG.md` 中的 T059 记录
- **Commit**：`未填写`

## T060 — 受控 CREATE_FILE 工具

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`FR-07-05`
- **目标**：只在批准路径创建不存在的新文件，并保证取消/回滚时可删除。
- **涉及文件**：
  - `backend/src/se_mentor/tools/create_file.py`
  - `backend/tests/tools/test_create_file.py`
- **预期实现要点**：
  - 父目录策略检查
  - 已存在文件不覆盖
  - 原子创建并记录 CREATE manifest
- **将要先写的失败测试**：
  - `test_T060_create_existing_or_unapproved_file_is_rejected` 先失败。
- **验证步骤**：
  1. 新文件成功
  2. 并发创建冲突
  3. 回滚 manifest 可用
- **依赖**：T058,T051
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T060.xml
  - evidence/diffs/T060.patch
  - `AGENT_LOG.md` 中的 T060 记录
- **Commit**：`未填写`

## T061 — 受控 DELETE_FILE 工具

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`FR-07-06`, `危险动作审批`
- **目标**：删除文件前要求 WARN 审批或明确策略，并保存可恢复备份。
- **涉及文件**：
  - `backend/src/se_mentor/tools/delete_file.py`
  - `backend/tests/tools/test_delete_file.py`
- **预期实现要点**：
  - 目录递归删除不属于 P0 工具
  - 不存在文件幂等但记录结果
  - 测试、迁移、配置等高风险路径需独立审批
- **将要先写的失败测试**：
  - `test_T061_delete_without_matching_grant_is_blocked_and_file_unchanged` 先失败。
- **验证步骤**：
  1. 批准/拒绝/过期授权
  2. 备份可恢复
  3. 不允许删除项目根或备份目录
- **依赖**：T058,T050,T051
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T061.xml
  - evidence/diffs/T061.patch
  - `AGENT_LOG.md` 中的 T061 记录
- **Commit**：`未填写`

## T062 — Shell 沙箱与命令策略

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`FR-07-07`, `NFR-SEC-05`, `OQ-04/11/14`
- **目标**：使用程序+参数数组执行允许命令，限制 cwd、环境、网络、时间、输出和资源。
- **涉及文件**：
  - `backend/src/se_mentor/tools/shell.py`
  - `backend/tests/tools/test_shell.py`
- **预期实现要点**：
  - `shell=False`
  - 默认无网络且仅 LLM Provider 可联网
  - 安装依赖和高资源命令 WARN 审批
- **将要先写的失败测试**：
  - `test_T062_shell_injection_env_secret_cwd_escape_and_timeout_are_blocked` 先失败。
- **验证步骤**：
  1. PowerShell/Unix 参数变体
  2. 超时清理进程树
  3. stdout/stderr 截断并保存 artifact
- **依赖**：T006,T045,T051,T057
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T062.xml
  - evidence/diffs/T062.patch
  - `AGENT_LOG.md` 中的 T062 记录
- **Commit**：`未填写`

## T063 — 注册只读 Git 工具动作

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`Git Tool`, `FR-07`
- **目标**：把 status、revision、diff、history 和外部变化检测作为只读工具注册；P0 无 commit/push。
- **涉及文件**：
  - `backend/src/se_mentor/tools/git_tools.py`
  - `backend/tests/tools/test_git_tools.py`
- **预期实现要点**：
  - 只接受项目内 pathspec
  - 输出结构化摘要和 artifact
  - 工具不可修改 index 或 HEAD
- **将要先写的失败测试**：
  - `test_T063_git_tool_has_no_commit_push_or_write_side_effect` 先失败。
- **验证步骤**：
  1. 命令前后 Git 状态一致
  2. diff 行数限制
  3. Dispatcher 审计完整
- **依赖**：T032,T057
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T063.xml
  - evidence/diffs/T063.patch
  - `AGENT_LOG.md` 中的 T063 记录
- **Commit**：`未填写`

## T064 — 显式回滚任务修改

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`FR-07-08`, `E2E-06`
- **目标**：按 manifest 逆序恢复修改、删除新建文件并恢复删除文件，不覆盖用户任务前修改。
- **涉及文件**：
  - `backend/src/se_mentor/transactions/rollback.py`
  - `backend/tests/transactions/test_rollback.py`
- **预期实现要点**：
  - 回滚前检查当前 hash 是否仍是 Agent 产生状态
  - 冲突时停止并要求人工介入
  - 重复回滚幂等
- **将要先写的失败测试**：
  - `test_AC_FR07_10_rollback_preserves_existing_changes` 先失败。
- **验证步骤**：
  1. CREATE/MODIFY/DELETE 混合
  2. 外部变化冲突
  3. 回滚后 Git 状态仅保留原有修改
- **依赖**：T059,T060,T061,T032
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T064.xml
  - evidence/diffs/T064.patch
  - `AGENT_LOG.md` 中的 T064 记录
- **Commit**：`未填写`

## T065 — 异常中断事务恢复

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`FR-07-09`, `E2E-07`, `NFR-USA-08`
- **目标**：启动时发现 PREPARED/APPLYING 事务并生成恢复选择，恢复完成前阻止新写任务。
- **涉及文件**：
  - `backend/src/se_mentor/transactions/recovery.py`
  - `backend/tests/transactions/test_recovery.py`
- **预期实现要点**：
  - 10 秒内扫描
  - 安全可判定时自动建议回滚，存在外部变化时人工处理
  - 恢复完成后释放或重建锁
- **将要先写的失败测试**：
  - `test_T065_restart_detects_unfinished_transaction_and_blocks_new_writer` 先失败。
- **验证步骤**：
  1. 半写入 fixture
  2. Web API 所需恢复摘要
  3. 恢复审计和告警
- **依赖**：T023,T064,T018
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T065.xml
  - evidence/diffs/T065.patch
  - `AGENT_LOG.md` 中的 T065 记录
- **Commit**：`未填写`

## T066 — 自研 Agent 单轮编排器

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`FR-05-03`, `自研 Harness`
- **目标**：实现构建上下文→预算→Provider→解析→治理→Dispatcher→反馈的单轮，不使用现成 Agent Runner。
- **涉及文件**：
  - `backend/src/se_mentor/agent/iteration.py`
  - `backend/tests/agent/test_iteration.py`
- **预期实现要点**：
  - 每轮创建 TaskIteration/LLMCall/AgentAction
  - WARN/BLOCK 在工具前暂停
  - ToolResult 和解析错误统一回灌
- **将要先写的失败测试**：
  - `test_T066_read_action_flows_through_context_llm_parser_governance_dispatcher` 先失败。
- **验证步骤**：
  1. Mock LLM 单轮
  2. BLOCK handler 未调用
  3. 所有对象可按 taskId 追踪
- **依赖**：T034,T046,T057,T053,T056
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T066.xml
  - evidence/diffs/T066.patch
  - `AGENT_LOG.md` 中的 T066 记录
- **Commit**：`未填写`

## T067 — Agent 运行状态、取消与安全点

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-runtime`
- **覆盖需求**：`FR-05-03`, `NFR-USA-06`, `E2E-06`
- **目标**：实现多轮运行控制、用户取消、Provider 取消和子进程终止；写入临界区只在安全点停止。
- **涉及文件**：
  - `backend/src/se_mentor/agent/runtime.py`
  - `backend/tests/agent/test_cancellation.py`
- **预期实现要点**：
  - 取消后不再发起新 LLM 调用
  - 终止可终止子进程
  - 取消后用户可选择保留或回滚
- **将要先写的失败测试**：
  - `test_T067_cancel_stops_future_llm_calls_and_reaches_safe_state` 先失败。
- **验证步骤**：
  1. 读取阶段取消
  2. Shell 阶段取消
  3. 原子 replace 临界区取消
- **依赖**：T066,T062,T064
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T067.xml
  - evidence/diffs/T067.patch
  - `AGENT_LOG.md` 中的 T067 记录
- **Commit**：`未填写`

# Phase 7 验证与反馈

## T068 — 实质进展检测

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`FR-05-04`, `OQ-13`, `NFR-USA-07`
- **目标**：按新证据、范围收敛、补丁、失败减少、审批和测试改善判断进展。
- **涉及文件**：
  - `backend/src/se_mentor/progress/monitor.py`
  - `backend/tests/progress/test_monitor.py`
- **预期实现要点**：
  - 动作和结果归一化
  - 仅措辞变化不算进展
  - 输出 ProgressEvent 和理由
- **将要先写的失败测试**：
  - `test_T068_rephrased_same_plan_is_not_progress_but_new_evidence_is` 先失败。
- **验证步骤**：
  1. 正负样例表
  2. 固定输入结果稳定
  3. 进展事件进入时间线
- **依赖**：T015,T066
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T068.xml
  - evidence/diffs/T068.patch
  - `AGENT_LOG.md` 中的 T068 记录
- **Commit**：`未填写`

## T069 — 停滞、重新规划与预算终止

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`FR-05-05`, `E2E-05`, `NFR-OBS-11`
- **目标**：重复动作且无新证据达到阈值时触发 STAGNATION_WARNING，要求新计划；恢复失败后暂停或失败。
- **涉及文件**：
  - `backend/src/se_mentor/progress/stagnation.py`
  - `backend/tests/progress/test_stagnation.py`
- **预期实现要点**：
  - 最大轮次、token、时间和修正预算独立
  - 重复读取不同文件不误判
  - 达到上限后不再调用 Provider
- **将要先写的失败测试**：
  - `test_AC_FR05_05_detects_semantic_stagnation` 先失败。
- **验证步骤**：
  1. 重复 READ 场景
  2. 一次重新规划成功/失败
  3. 告警和状态正确
- **依赖**：T068,T034,T067
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T069.xml
  - evidence/diffs/T069.patch
  - `AGENT_LOG.md` 中的 T069 记录
- **Commit**：`未填写`

## T070 — 根据影响生成 ValidationPlan

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`FR-08-01`, `审查 ValidationPlanner 缺口`
- **目标**：根据变更文件、符号、API、Schema、认证、配置和项目工具链选择必要验证。
- **涉及文件**：
  - `backend/src/se_mentor/validation/planner.py`
  - `backend/tests/validation/test_planner.py`
- **预期实现要点**：
  - 公共 API 增加契约检查
  - Schema 增加空库/旧库迁移检查
  - 测试或验证配置变化增加规避检查
- **将要先写的失败测试**：
  - `test_T070_api_schema_change_generates_contract_migration_and_unit_checks` 先失败。
- **验证步骤**：
  1. 不同变更类型矩阵
  2. 缺少验证器时标记 INCONCLUSIVE 预条件
  3. 计划绑定当前 policy/proposal/revision
- **依赖**：T020,T043,T052,T015
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T070.xml
  - evidence/diffs/T070.patch
  - `AGENT_LOG.md` 中的 T070 记录
- **Commit**：`未填写`

## T071 — 执行验证并记录客观结果

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`FR-08-02`, `NFR-OBS-07`
- **目标**：按 ValidationPlan 调用 build、unit、integration、lint、type、contract 和 migration 命令。
- **涉及文件**：
  - `backend/src/se_mentor/validation/executor.py`
  - `backend/src/se_mentor/tools/run_validation.py`
  - `backend/tests/validation/test_executor.py`
- **预期实现要点**：
  - 失败不是系统异常
  - 记录 exit code、duration、stdout/stderr artifact、test counts
  - 必需检查全部通过才是 PASSED
- **将要先写的失败测试**：
  - `test_T071_required_nonzero_exit_makes_plan_failed_and_records_artifact` 先失败。
- **验证步骤**：
  1. 成功/失败/超时/缺工具
  2. 通过 Dispatcher 和 PolicyEnforcer
  3. 命令范围与计划一致
- **依赖**：T062,T070,T057
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T071.xml
  - evidence/diffs/T071.patch
  - `AGENT_LOG.md` 中的 T071 记录
- **Commit**：`未填写`

## T072 — 分类验证失败

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`FR-08-03`, `审查 FailureClassifier 缺口`
- **目标**：分类 COMPILE_ERROR、UNIT_TEST_FAILURE、INTEGRATION_TEST_FAILURE、CONTRACT_FAILURE、MIGRATION_FAILURE、ENVIRONMENT_FAILURE、FLAKY_TEST、VALIDATION_EVASION、INCONCLUSIVE。
- **涉及文件**：
  - `backend/src/se_mentor/validation/failure_classifier.py`
  - `backend/tests/validation/test_failure_classifier.py`
- **预期实现要点**：
  - 基于结构化输出与解析器，不只关键词
  - 未知格式返回 UNKNOWN/INCONCLUSIVE
  - 分类保存置信度和依据
- **将要先写的失败测试**：
  - `test_T072_distinguishes_code_failure_environment_failure_and_inconclusive` 先失败。
- **验证步骤**：
  1. 各类 fixture
  2. 错误格式不崩溃
  3. 分类与原始日志可追踪
- **依赖**：T071
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T072.xml
  - evidence/diffs/T072.patch
  - `AGENT_LOG.md` 中的 T072 记录
- **Commit**：`未填写`

## T073 — 统一 FeedbackSignal 与反馈压缩

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`FR-08-04`, `FeedbackController`
- **目标**：把工具、验证、治理、Git 和进展结果转成下一轮可用的统一反馈，完整日志留在 artifact。
- **涉及文件**：
  - `backend/src/se_mentor/feedback/controller.py`
  - `backend/tests/feedback/test_controller.py`
- **预期实现要点**：
  - 只发送失败测试名、类别、关键堆栈、断言差异、文件位置和最近 diff
  - 敏感输出脱敏
  - retryable 明确
- **将要先写的失败测试**：
  - `test_T073_feedback_is_compact_actionable_and_secret_free` 先失败。
- **验证步骤**：
  1. 长日志压缩
  2. 不同 source_type
  3. ContextPackage 可直接消费
- **依赖**：T072,T006,T015
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T073.xml
  - evidence/diffs/T073.patch
  - `AGENT_LOG.md` 中的 T073 记录
- **Commit**：`未填写`

## T074 — Flaky Test 检测

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`FR-08`, `测试经验`, `审查 Flaky 缺口`
- **目标**：在相同 revision、相同环境和无代码变化条件下有限重试，识别结果波动。
- **涉及文件**：
  - `backend/src/se_mentor/validation/flaky.py`
  - `backend/tests/validation/test_flaky.py`
- **预期实现要点**：
  - 重试次数受限
  - FLAKY_TEST 不直接驱动代码 Patch
  - 保存测试名和波动证据
- **将要先写的失败测试**：
  - `test_T074_same_revision_alternating_result_is_flaky_not_code_failure` 先失败。
- **验证步骤**：
  1. 稳定失败、稳定成功、波动三类
  2. 无代码变化校验
  3. 标记为测试经验候选
- **依赖**：T071,T072,T032
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T074.xml
  - evidence/diffs/T074.patch
  - `AGENT_LOG.md` 中的 T074 记录
- **Commit**：`未填写`

## T075 — 验证规避检测

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`FR-08-06`, `US-05 AC-04`, `NFR-SEC-05`
- **目标**：检测删断言、批量 skip、测试数下降、关闭 lint/type、`|| true`、伪造报告和缩小测试集合。
- **涉及文件**：
  - `backend/src/se_mentor/validation/evasion.py`
  - `backend/tests/validation/test_evasion.py`
- **预期实现要点**：
  - 比较基线与当前验证计划/测试统计/diff
  - 测试文件修改默认 WARN
  - 明确恶意规避按规则 BLOCK
- **将要先写的失败测试**：
  - `test_T075_removed_assertions_skips_and_or_true_are_detected_before_completion` 先失败。
- **验证步骤**：
  1. 各规避 fixture
  2. 正常新增测试不误报
  3. 结果进入 Governance 再评估
- **依赖**：T045,T070,T071,T032
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T075.xml
  - evidence/diffs/T075.patch
  - `AGENT_LOG.md` 中的 T075 记录
- **Commit**：`未填写`

## T076 — 有限自动修正循环

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`FR-08-05`, `US-05 AC-02～03`, `E2E-02`
- **目标**：将分类后的反馈回灌并允许有限次不同修正，达到上限或无进展后停止。
- **涉及文件**：
  - `backend/src/se_mentor/agent/repair_loop.py`
  - `backend/tests/agent/test_repair_loop.py`
- **预期实现要点**：
  - repairCount 独立计数
  - 下一补丁必须重新走治理、策略和事务
  - 相同失败连续出现触发停滞
- **将要先写的失败测试**：
  - `test_T076_first_patch_fails_second_patch_passes_with_two_distinct_diffs` 先失败。
- **验证步骤**：
  1. 成功修正
  2. 达到上限
  3. 相同补丁/相同失败
- **依赖**：T067,T069,T073,T059
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T076.xml
  - evidence/diffs/T076.patch
  - `AGENT_LOG.md` 中的 T076 记录
- **Commit**：`未填写`

## T077 — 修正动作再治理与范围扩展暂停

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`再治理`, `US-04 AC-04`
- **目标**：修正若涉及新文件、测试、Schema、API 或更高风险命令，先失效旧策略并重新分析治理。
- **涉及文件**：
  - `backend/src/se_mentor/agent/repair_governance.py`
  - `backend/tests/agent/test_repair_governance.py`
- **预期实现要点**：
  - 原范围内低风险修正可复用仍有效策略
  - 新范围一律暂停
  - 审批不能自动扩展
- **将要先写的失败测试**：
  - `test_T077_repair_touching_new_test_file_pauses_before_write` 先失败。
- **验证步骤**：
  1. 原范围/新范围
  2. 过期审批
  3. 知识新鲜度变化
- **依赖**：T052,T076,T075
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T077.xml
  - evidence/diffs/T077.patch
  - `AGENT_LOG.md` 中的 T077 记录
- **Commit**：`未填写`

## T078 — CompletionGate 与 StopPolicy

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`FR-05-06`, `FR-08-07`, `数据模型任务完成约束`, `OQ-17`
- **目标**：独立于 LLM 的 REQUEST_COMPLETE，检查实际变化、批准范围、必需验证、风险、审批、事务、Diff、审计和锁。
- **涉及文件**：
  - `backend/src/se_mentor/agent/completion_gate.py`
  - `backend/tests/agent/test_completion_gate.py`
- **预期实现要点**：
  - 缺验证器时 INCONCLUSIVE 不完成
  - 验证失败或待审批不完成
  - 只读分析任务可按单独条件完成
- **将要先写的失败测试**：
  - `test_T078_llm_complete_cannot_bypass_failed_validation_or_pending_approval` 先失败。
- **验证步骤**：
  1. 所有完成条件逐项失败测试
  2. 完成后事务提交和锁释放
  3. 最终结果说明是否修改、备份、回滚
- **依赖**：T071,T075,T077,T018,T023
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T078.xml
  - evidence/diffs/T078.patch
  - `AGENT_LOG.md` 中的 T078 记录
- **Commit**：`未填写`

## T079 — 成功任务的知识更新

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`FR-09-01～03`, `US-06 AC-01`
- **目标**：任务完成后提取最终方案、实际范围、验证事实、设计决策和约束，并生成当前签名。
- **涉及文件**：
  - `backend/src/se_mentor/knowledge/update_success.py`
  - `backend/tests/knowledge/test_update_success.py`
- **预期实现要点**：
  - 只从最终 committed diff 和通过验证提取
  - 自动知识默认 CANDIDATE，满足晋级规则才 VERIFIED
  - 关联 task、file、symbol、validation
- **将要先写的失败测试**：
  - `test_T079_success_knowledge_uses_committed_diff_and_passed_validation` 先失败。
- **验证步骤**：
  1. 正常完成
  2. 只读任务
  3. 部分可复用信息
- **依赖**：T039,T078,T036
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T079.xml
  - evidence/diffs/T079.patch
  - `AGENT_LOG.md` 中的 T079 记录
- **Commit**：`未填写`

## T080 — 失败、取消与回滚任务的经验更新

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-validation`
- **覆盖需求**：`FR-09`, `US-06 AC-02/04`
- **目标**：保存失败方案、失败条件、尝试和证据，但不把未落地内容标为有效架构事实。
- **涉及文件**：
  - `backend/src/se_mentor/knowledge/update_failure.py`
  - `backend/tests/knowledge/test_update_failure.py`
- **预期实现要点**：
  - FAILED_EXPERIENCE 与 CANDIDATE 区分
  - 回滚后不创建 active implementation fact
  - 可供相似任务检索
- **将要先写的失败测试**：
  - `test_T080_rolled_back_task_creates_failure_experience_not_verified_fact` 先失败。
- **验证步骤**：
  1. 失败/取消/停滞/回滚
  2. 敏感日志不进入知识
  3. 与旧知识冲突时进入 T038
- **依赖**：T038,T064,T076,T078
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T080.xml
  - evidence/diffs/T080.patch
  - `AGENT_LOG.md` 中的 T080 记录
- **Commit**：`未填写`

# Phase 8 离线 E2E

## T081 — E2E-01 正常闭环与 E2E-02 自动修正

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-e2e`
- **覆盖需求**：`E2E-01`, `E2E-02`, `FR-12-02～03`
- **目标**：使用临时 Git 仓库和 Mock LLM 验证安全修改成功及第一次失败、第二次修正成功。
- **涉及文件**：
  - `backend/tests/e2e/test_E2E_01_02.py`
  - `backend/tests/fixtures/e2e/basic_fix/`
- **预期实现要点**：
  - 完全离线
  - 验证 diff、备份、锁、审计、repairCount 和知识更新
  - 两次补丁必须不同
- **将要先写的失败测试**：
  - `test_E2E_01_normal_change_loop` 与 `test_E2E_02_failed_then_repaired` 初始全红。
- **验证步骤**：
  1. 禁止网络访问
  2. 重复执行结果一致
  3. 所有证据写入 evidence/test-reports
- **依赖**：T019～T080
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T081.xml
  - evidence/diffs/T081.patch
  - `AGENT_LOG.md` 中的 T081 记录
- **Commit**：`未填写`

## T082 — E2E-03 高风险审批与 E2E-04 危险动作阻止

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-e2e`
- **覆盖需求**：`E2E-03`, `E2E-04`
- **目标**：验证 WARN 在审批前无文件变化、批准后仅有限范围；DENY_HARD 不进入审批且无副作用。
- **涉及文件**：
  - `backend/tests/e2e/test_E2E_03_04.py`
  - `backend/tests/fixtures/e2e/governance/`
- **预期实现要点**：
  - 公共 API/测试文件触发 WARN
  - 项目外读取或递归删除触发 BLOCK
  - 审计时间线完整
- **将要先写的失败测试**：
  - `test_E2E_03_warn_approval_scope` 与 `test_E2E_04_deny_hard` 初始全红。
- **验证步骤**：
  1. 审批批准/拒绝
  2. handler spy
  3. 文件与系统 hash 不变
- **依赖**：T081
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T082.xml
  - evidence/diffs/T082.patch
  - `AGENT_LOG.md` 中的 T082 记录
- **Commit**：`未填写`

## T083 — E2E-05 停滞与 E2E-06 取消回滚

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-e2e`
- **覆盖需求**：`E2E-05`, `E2E-06`
- **目标**：验证重复读取触发重新规划与停止，以及多文件修改后取消和回滚。
- **涉及文件**：
  - `backend/tests/e2e/test_E2E_05_06.py`
  - `backend/tests/fixtures/e2e/resilience/`
- **预期实现要点**：
  - 轮次不超限
  - 取消停止 LLM/子进程
  - 原有未提交修改保留
- **将要先写的失败测试**：
  - `test_E2E_05_stagnation` 与 `test_E2E_06_cancel_rollback` 初始全红。
- **验证步骤**：
  1. 状态、锁、事务、文件内容
  2. 新建文件被删除
  3. 时间线含取消和回滚
- **依赖**：T082
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T083.xml
  - evidence/diffs/T083.patch
  - `AGENT_LOG.md` 中的 T083 记录
- **Commit**：`未填写`

## T084 — E2E-07 崩溃恢复与 E2E-08 知识保鲜

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-e2e`
- **覆盖需求**：`E2E-07`, `E2E-08`
- **目标**：验证进程重启后发现未完成事务，以及知识在代码变化后变为 DRIFTED/STALE。
- **涉及文件**：
  - `backend/tests/e2e/test_E2E_07_08.py`
  - `backend/tests/fixtures/e2e/recovery_memory/`
- **预期实现要点**：
  - 恢复前禁止新写任务
  - 恢复摘要可供 UI
  - 第三任务不能基于 stale 知识自动 ALLOW
- **将要先写的失败测试**：
  - `test_E2E_07_crash_recovery` 与 `test_E2E_08_knowledge_freshness` 初始全红。
- **验证步骤**：
  1. 10 秒恢复发现
  2. 三次任务链
  3. 数据库与文件状态一致
- **依赖**：T083
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T084.xml
  - evidence/diffs/T084.patch
  - `AGENT_LOG.md` 中的 T084 记录
- **Commit**：`未填写`

## T085 — 全离线确定性与网络封锁测试

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-e2e`
- **覆盖需求**：`FR-12`, `发布门禁`
- **目标**：证明 Mock 模式不需要真实 Key、网络或外部服务，且相同脚本生成相同事件序列。
- **涉及文件**：
  - `backend/tests/e2e/test_offline_determinism.py`
  - `scripts/run_offline_e2e.py`
- **预期实现要点**：
  - 测试进程禁用 socket
  - 固定时钟、UUID 和 Mock 响应
  - 比较归一化审计时间线 hash
- **将要先写的失败测试**：
  - `test_T085_mock_harness_makes_zero_network_calls_and_is_deterministic` 先失败。
- **验证步骤**：
  1. 断网环境执行
  2. 无环境 Key
  3. 五次重复结果一致
- **依赖**：T084
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T085.xml
  - evidence/diffs/T085.patch
  - `AGENT_LOG.md` 中的 T085 记录
- **Commit**：`未填写`

# Phase 9 API

## T086 — 项目、配置、锁、任务与提案 API

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-api`
- **覆盖需求**：`FR-01`, `FR-02`, `FR-10`
- **目标**：提供注册项目、查看有效配置、锁状态、创建任务、生成/补充/确认/拒绝提案的 REST API。
- **涉及文件**：
  - `backend/src/se_mentor/api/projects.py`
  - `backend/src/se_mentor/api/tasks.py`
  - `backend/src/se_mentor/api/proposals.py`
  - `backend/tests/api/test_project_task_proposal_api.py`
- **预期实现要点**：
  - 统一错误 envelope
  - 创建任务不自动写代码
  - API 不泄露不必要绝对路径或配置 Secret
- **将要先写的失败测试**：
  - `test_T086_project_task_proposal_routes_initially_404` 先失败。
- **验证步骤**：
  1. 201/400/404/409
  2. 提案版本和失效
  3. OpenAPI Schema 快照
- **依赖**：T027,T023,T100
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T086.xml
  - evidence/diffs/T086.patch
  - `AGENT_LOG.md` 中的 T086 记录
- **Commit**：`未填写`

## T087 — 影响分析与治理 API

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-api`
- **覆盖需求**：`FR-04`, `FR-06-01～02`, `FR-10`
- **目标**：提供索引、分析、ImpactReport、治理决策、规则命中和 evidence 查询。
- **涉及文件**：
  - `backend/src/se_mentor/api/analysis.py`
  - `backend/src/se_mentor/api/governance.py`
  - `backend/tests/api/test_analysis_governance_api.py`
- **预期实现要点**：
  - 未确认提案返回冲突
  - 分析幂等并按输入创建版本
  - BLOCK 响应不提供绕过执行入口
- **将要先写的失败测试**：
  - `test_T087_unconfirmed_proposal_cannot_run_governance` 先失败。
- **验证步骤**：
  1. ALLOW/WARN/BLOCK Mock 场景
  2. 证据链接有效
  3. 无 system prompt/Secret 泄漏
- **依赖**：T043,T046,T086
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T087.xml
  - evidence/diffs/T087.patch
  - `AGENT_LOG.md` 中的 T087 记录
- **Commit**：`未填写`

## T088 — 审批、ExecutionPolicy 与执行 API

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-api`
- **覆盖需求**：`FR-06-03～05`, `FR-07`
- **目标**：提供审批请求、批准/拒绝、查看策略和启动受控执行的命令接口。
- **涉及文件**：
  - `backend/src/se_mentor/api/approvals.py`
  - `backend/src/se_mentor/api/execution.py`
  - `backend/tests/api/test_approval_execution_api.py`
- **预期实现要点**：
  - 重复命令幂等
  - 执行前重新检查 policy/revision/lock
  - DENY_HARD 返回不可审批错误
- **将要先写的失败测试**：
  - `test_T088_blocked_task_execute_returns_conflict_and_no_tool_call` 先失败。
- **验证步骤**：
  1. 审批过期
  2. 策略范围响应
  3. 执行命令审计
- **依赖**：T049,T050,T067,T087
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T088.xml
  - evidence/diffs/T088.patch
  - `AGENT_LOG.md` 中的 T088 记录
- **Commit**：`未填写`

## T089 — 取消、回滚与恢复 API

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-api`
- **覆盖需求**：`FR-07-08～09`, `NFR-USA-06/08`
- **目标**：提供取消、选择保留/回滚、恢复列表、恢复详情和执行恢复操作。
- **涉及文件**：
  - `backend/src/se_mentor/api/recovery.py`
  - `backend/tests/api/test_recovery_api.py`
- **预期实现要点**：
  - 恢复冲突返回人工介入
  - 恢复完成前不能启动新写任务
  - 错误信息说明文件是否已修改/备份/回滚
- **将要先写的失败测试**：
  - `test_T089_recovery_required_blocks_execute_until_resolved` 先失败。
- **验证步骤**：
  1. 取消与回滚
  2. 半事务恢复
  3. 重复恢复幂等
- **依赖**：T065,T067,T088
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T089.xml
  - evidence/diffs/T089.patch
  - `AGENT_LOG.md` 中的 T089 记录
- **Commit**：`未填写`

## T090 — SSE 实时任务事件

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-api`
- **覆盖需求**：`NFR-PERF-05`, `FR-10-01`, `NFR-OBS-09`
- **目标**：推送状态、动作、治理、审批、验证、修正、停滞、恢复和终态事件。
- **涉及文件**：
  - `backend/src/se_mentor/api/events.py`
  - `backend/src/se_mentor/events/bus.py`
  - `backend/tests/api/test_sse.py`
- **预期实现要点**：
  - 事件递增 id
  - 支持 Last-Event-ID 重连
  - 慢客户端不阻塞主循环
- **将要先写的失败测试**：
  - `test_T090_sse_reconnects_without_missing_persisted_events` 先失败。
- **验证步骤**：
  1. 断线重连
  2. 队列溢出告警
  3. payload 脱敏
- **依赖**：T018,T066,T086
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T090.xml
  - evidence/diffs/T090.patch
  - `AGENT_LOG.md` 中的 T090 记录
- **Commit**：`未填写`

## T091 — 知识、凭据状态与项目设置 API

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-api`
- **覆盖需求**：`FR-09`, `NFR-CRED-06`, `FR-10`
- **目标**：提供知识筛选、冲突审核、凭据配置状态和非敏感设置查询。
- **涉及文件**：
  - `backend/src/se_mentor/api/knowledge.py`
  - `backend/src/se_mentor/api/settings.py`
  - `backend/tests/api/test_knowledge_settings_api.py`
- **预期实现要点**：
  - 凭据只返回 configured/provider/source
  - 知识显式显示 freshness/status/conflicts
  - 不能通过 API 读取 key
- **将要先写的失败测试**：
  - `test_T091_settings_response_never_contains_key_and_stale_is_visible` 先失败。
- **验证步骤**：
  1. 分页筛选
  2. 冲突审核权限
  3. Secret 扫描
- **依赖**：T038,T039,T104,T086
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T091.xml
  - evidence/diffs/T091.patch
  - `AGENT_LOG.md` 中的 T091 记录
- **Commit**：`未填写`

## T092 — Diff、审计、告警与任务回放 API

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-api`
- **覆盖需求**：`FR-10-03`, `FR-11`, `NFR-OBS-09～11`
- **目标**：提供 scoped diff、验证报告、审计查询、反向追踪、告警和完整任务回放。
- **涉及文件**：
  - `backend/src/se_mentor/api/audit.py`
  - `backend/src/se_mentor/api/replay.py`
  - `backend/src/se_mentor/api/diffs.py`
  - `backend/tests/api/test_replay_api.py`
- **预期实现要点**：
  - 任一 FileChange 可反向到 AgentAction、Decision、Policy、ToolExecution 和 Approval
  - 审计只读并可脱敏导出
  - 回放按时间稳定排序
- **将要先写的失败测试**：
  - `test_T092_file_change_reverse_trace_and_full_replay_are_complete` 先失败。
- **验证步骤**：
  1. 分页和导出
  2. 篡改/缺链引用诊断
  3. Diff 标出批准范围内外
- **依赖**：T018,T032,T071,T090
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T092.xml
  - evidence/diffs/T092.patch
  - `AGENT_LOG.md` 中的 T092 记录
- **Commit**：`未填写`

# Phase 10 WebUI

## T093 — React 基线、Open Design 记录与 Design Token

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-web`
- **覆盖需求**：`技术选型 Open Design linear-app/dashboard`, `NFR-USA-10`
- **目标**：建立 React/TypeScript/Vite、基础组件、SE-Mentor Design Token 和设计来源记录。
- **涉及文件**：
  - `frontend/src/app/`
  - `frontend/src/styles/tokens.css`
  - `frontend/src/components/`
  - `docs/DESIGN_PROCESS.md`
  - `frontend/tests/smoke.test.tsx`
- **预期实现要点**：
  - ALLOW/WARN/BLOCK 不只依赖颜色
  - 键盘可操作
  - 记录 linear-app 与 dashboard 的采用和偏离理由
- **将要先写的失败测试**：
  - `test_T093_app_shell_and_accessible_status_badge_exist` 先失败。
- **验证步骤**：
  1. Vitest smoke
  2. 基础 a11y
  3. build 通过
- **依赖**：T086
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T093.xml
  - evidence/diffs/T093.patch
  - `AGENT_LOG.md` 中的 T093 记录
- **Commit**：`未填写`

## T094 — 项目、任务与提案审查页面

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-web`
- **覆盖需求**：`FR-10-01`, `US-01`, `NFR-USA-01/02`
- **目标**：支持注册项目、查看配置/锁、创建任务、补充信息和确认/修改/拒绝提案。
- **涉及文件**：
  - `frontend/src/pages/ProjectsPage.tsx`
  - `frontend/src/pages/NewTaskPage.tsx`
  - `frontend/src/pages/ProposalReviewPage.tsx`
  - `frontend/tests/proposal_flow.test.tsx`
- **预期实现要点**：
  - 明确提示先分析治理、不会立即修改
  - 错误说明下一步
  - 重复提交防抖和幂等
- **将要先写的失败测试**：
  - `test_T094_incomplete_proposal_shows_missing_information_and_no_execute` 先失败。
- **验证步骤**：
  1. 成功/错误/冲突
  2. V1/V2 显示
  3. 键盘表单
- **依赖**：T086,T093
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T094.xml
  - evidence/diffs/T094.patch
  - `AGENT_LOG.md` 中的 T094 记录
- **Commit**：`未填写`

## T095 — 影响分析与治理决策页面

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-web`
- **覆盖需求**：`FR-10-01`, `US-02`, `US-03`
- **目标**：展示事实、推断、未知项、证据、影响范围、规则命中及 ALLOW/WARN/BLOCK。
- **涉及文件**：
  - `frontend/src/pages/AnalysisPage.tsx`
  - `frontend/src/components/ImpactReport.tsx`
  - `frontend/src/components/GovernanceDecision.tsx`
  - `frontend/tests/analysis_page.test.tsx`
- **预期实现要点**：
  - 证据可定位文件/行
  - BLOCK 不渲染执行入口
  - WARN 显示风险、范围、期限和替代方案
- **将要先写的失败测试**：
  - `test_T095_block_has_no_execute_button_and_unknowns_are_explicit` 先失败。
- **验证步骤**：
  1. 三种决策
  2. 证据展开
  3. stale/conflicting 知识警示
- **依赖**：T087,T093
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T095.xml
  - evidence/diffs/T095.patch
  - `AGENT_LOG.md` 中的 T095 记录
- **Commit**：`未填写`

## T096 — 审批、执行时间线与取消页面

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-web`
- **覆盖需求**：`FR-10-02`, `NFR-USA-03/05/06`
- **目标**：支持审批确认、启动任务、SSE 时间线、取消和终态操作。
- **涉及文件**：
  - `frontend/src/pages/ExecutionPage.tsx`
  - `frontend/src/hooks/useTaskEvents.ts`
  - `frontend/src/components/ExecutionTimeline.tsx`
  - `frontend/tests/execution_page.test.tsx`
- **预期实现要点**：
  - 高风险批准二次确认
  - WARN 未批执行按钮禁用
  - SSE 断线重连且终态禁用重复操作
- **将要先写的失败测试**：
  - `test_T096_warn_cannot_start_before_explicit_approval` 先失败。
- **验证步骤**：
  1. 批准/拒绝
  2. 断线重连
  3. 取消安全提示
- **依赖**：T088,T090,T093
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T096.xml
  - evidence/diffs/T096.patch
  - `AGENT_LOG.md` 中的 T096 记录
- **Commit**：`未填写`

## T097 — Diff、验证报告与恢复交互

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-web`
- **覆盖需求**：`FR-10-03`, `NFR-USA-04/08`, `E2E-07`
- **目标**：可读展示行级 Diff、批准范围标记、验证结果、失败类别和恢复选择。
- **涉及文件**：
  - `frontend/src/pages/TaskResultPage.tsx`
  - `frontend/src/pages/RecoveryPage.tsx`
  - `frontend/src/components/DiffViewer.tsx`
  - `frontend/src/components/ValidationReport.tsx`
  - `frontend/tests/result_recovery.test.tsx`
- **预期实现要点**：
  - 指出代码是否修改/备份/回滚
  - 范围外变化高亮
  - 恢复冲突不提供危险一键覆盖
- **将要先写的失败测试**：
  - `test_T097_error_view_states_modified_backed_up_rolled_back_and_next_action` 先失败。
- **验证步骤**：
  1. 成功/失败/回滚/恢复冲突
  2. 大 Diff 分块
  3. 可访问性
- **依赖**：T089,T092,T093
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T097.xml
  - evidence/diffs/T097.patch
  - `AGENT_LOG.md` 中的 T097 记录
- **Commit**：`未填写`

## T098 — 知识、审计、设置、告警与回放页面

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-web`
- **覆盖需求**：`FR-09`, `FR-11`, `NFR-OBS-09`
- **目标**：展示知识状态/冲突、凭据状态、审计、告警和完整任务回放。
- **涉及文件**：
  - `frontend/src/pages/KnowledgePage.tsx`
  - `frontend/src/pages/AuditPage.tsx`
  - `frontend/src/pages/SettingsPage.tsx`
  - `frontend/src/pages/ReplayPage.tsx`
  - `frontend/tests/knowledge_audit.test.tsx`
- **预期实现要点**：
  - 永不显示 key
  - 可从文件变化反向追踪
  - 告警含建议处置
- **将要先写的失败测试**：
  - `test_T098_secret_never_enters_dom_and_replay_contains_all_event_types` 先失败。
- **验证步骤**：
  1. 筛选分页
  2. 冲突审核
  3. 脱敏审计导出入口
- **依赖**：T091,T092,T093
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T098.xml
  - evidence/diffs/T098.patch
  - `AGENT_LOG.md` 中的 T098 记录
- **Commit**：`未填写`

## T099 — 浏览器 E2E、可访问性与可操作错误

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-web`
- **覆盖需求**：`AC-FR10-01～08`, `AC-USA-01～09`
- **目标**：使用 Mock 后端覆盖项目→提案→分析→审批→执行→验证→回放和恢复。
- **涉及文件**：
  - `frontend/tests/e2e/full_flow.spec.ts`
  - `frontend/playwright.config.ts`
  - `scripts/start_test_stack.py`
- **预期实现要点**：
  - 错误必须包含状态、是否已修改、是否备份/回滚和下一步
  - 键盘完成核心路径
  - 失败保存截图和 trace
- **将要先写的失败测试**：
  - `test_T099_playwright_full_allow_warn_block_and_recovery_flows` 初始失败。
- **验证步骤**：
  1. 完全离线
  2. axe 基础检查
  3. CI artifact
- **依赖**：T085,T094～T098
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T099.xml
  - evidence/diffs/T099.patch
  - `AGENT_LOG.md` 中的 T099 记录
- **Commit**：`未填写`

# Phase 11 NFR 与交付

## T100 — 结构化日志、Correlation ID 与可操作错误模型

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-delivery`
- **覆盖需求**：`NFR-USA-02`, `NFR-OBS-01～07`, `审查 P0-10`
- **目标**：统一 API、Agent、LLM、治理、工具和验证日志，并保证错误说明当前副作用状态和下一步。
- **涉及文件**：
  - `backend/src/se_mentor/observability/logging.py`
  - `backend/src/se_mentor/core/error_mapper.py`
  - `backend/tests/observability/test_logging_errors.py`
- **预期实现要点**：
  - 所有事件含 taskId/correlationId
  - 日志分类和级别统一
  - Secret、完整 Prompt 和无界源码不进入日志
- **将要先写的失败测试**：
  - `test_T100_error_reports_side_effect_state_without_secret_and_all_logs_correlate` 先失败。
- **验证步骤**：
  1. 日志扫描
  2. 错误码稳定
  3. 跨模块 correlation
- **依赖**：T006,T018,T073
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T100.xml
  - evidence/diffs/T100.patch
  - `AGENT_LOG.md` 中的 T100 记录
- **Commit**：`未填写`

## T101 — 核心指标、告警服务与任务回放构建器

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-delivery`
- **覆盖需求**：`NFR-OBS-08～11`, `OBS-A01～09`
- **目标**：实现任务数、耗时、token、工具失败、治理命中、停滞、锁冲突、回滚失败和知识失效指标与告警。
- **涉及文件**：
  - `backend/src/se_mentor/observability/metrics.py`
  - `backend/src/se_mentor/observability/alerts.py`
  - `backend/src/se_mentor/observability/replay.py`
  - `backend/tests/observability/`
- **预期实现要点**：
  - 告警去重和处置状态
  - 回放包含规定的 12 类事件
  - P0 使用进程内/SQLite 指标，P1 再接外部系统
- **将要先写的失败测试**：
  - `test_T101_required_alerts_and_complete_replay_are_emitted` 先失败。
- **验证步骤**：
  1. 锁/事务/停滞/凭据/知识场景
  2. 指标可按 task 查询
  3. 回放稳定排序
- **依赖**：T018,T100
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T101.xml
  - evidence/diffs/T101.patch
  - `AGENT_LOG.md` 中的 T101 记录
- **Commit**：`未填写`

## T102 — 性能、资源、成本和大型输出验收

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-delivery`
- **覆盖需求**：`NFR-PERF-01～07`, `AC-PERF-01～08`
- **目标**：建立可重复性能基准，验证 WebUI、本地治理、检索、Token、长任务进度、资源上限和大型输出处理。
- **涉及文件**：
  - `backend/tests/performance/`
  - `frontend/tests/performance/`
  - `scripts/run_performance.py`
  - `evidence/performance/.gitkeep`
- **预期实现要点**：
  - 阈值从 SPEC/DECISIONS_P0 读取
  - 超限安全终止或截断
  - 记录环境与统计方法
- **将要先写的失败测试**：
  - `test_T102_performance_contracts_initially_fail_without_metrics` 先失败。
- **验证步骤**：
  1. 生成 JSON/Markdown 报告
  2. 大型仓库 fixture
  3. 结果进入 ACCEPTANCE_REPORT
- **依赖**：T034,T069,T090,T099
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T102.xml
  - evidence/diffs/T102.patch
  - `AGENT_LOG.md` 中的 T102 记录
- **Commit**：`未填写`

## T103 — 依赖不可用时的安全降级

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-delivery`
- **覆盖需求**：`NFR-USA-09`, `OQ-17`
- **目标**：定义 LLM、知识库、索引、验证器、Keyring 或网络不可用时的降级，禁止假装完成。
- **涉及文件**：
  - `backend/src/se_mentor/resilience/degradation.py`
  - `backend/tests/resilience/test_degradation.py`
- **预期实现要点**：
  - LLM 不可用可保留只读分析结果
  - 知识不可用显式降低证据等级
  - 必要验证器缺失进入 INCONCLUSIVE
- **将要先写的失败测试**：
  - `test_T103_missing_required_validator_never_completes_task` 先失败。
- **验证步骤**：
  1. 各依赖故障注入
  2. 错误可操作
  3. 无未经授权副作用
- **依赖**：T078,T100
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T103.xml
  - evidence/diffs/T103.patch
  - `AGENT_LOG.md` 中的 T103 记录
- **Commit**：`未填写`

## T104 — Windows Credential Manager 凭据生命周期

- **状态**：[!] 实现未开始；实机验收外部阻塞
- **阻塞说明**：需要 Windows 10/11 x64 干净测试环境
- **Worktree**：`wt-delivery`
- **覆盖需求**：`NFR-CRED-04～10`, `OQ-12`
- **目标**：实现 set/status/update/clear 和 Keyring 失败时仅会话临时 Key，不落明文。
- **涉及文件**：
  - `backend/src/se_mentor/credentials/store.py`
  - `backend/src/se_mentor/cli/credentials.py`
  - `backend/tests/credentials/test_store.py`
- **预期实现要点**：
  - 隐藏输入、不回显
  - 数据库只存 profile 标识
  - 清除后 Provider 立即不可用
- **将要先写的失败测试**：
  - `test_T104_set_update_clear_never_persists_or_prints_secret` 先失败。
- **验证步骤**：
  1. 内存 keyring 单测
  2. Windows 实机验收脚本
  3. 构建目录 Secret 扫描
- **依赖**：T006,T009,T054
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T104.xml
  - evidence/diffs/T104.patch
  - `AGENT_LOG.md` 中的 T104 记录
- **Commit**：`未填写`

## T105 — PyInstaller onedir Windows 分发

- **状态**：[!] 实现未开始；实机验收外部阻塞
- **阻塞说明**：需要 Windows x64 构建/验收 Runner
- **Worktree**：`wt-delivery`
- **覆盖需求**：`AC-DIST-WIN`, `技术选型`
- **目标**：打包后端、前端静态文件、迁移和启动器；不包含数据库、日志、备份或凭据。
- **涉及文件**：
  - `packaging/se-mentor.spec`
  - `scripts/build_windows.ps1`
  - `scripts/smoke_windows.ps1`
  - `evidence/windows-package/.gitkeep`
- **预期实现要点**：
  - onedir 而非 onefile
  - 首次启动初始化数据库
  - 分发包支持 Mock 模式无网络运行
- **将要先写的失败测试**：
  - `test_T105_distribution_manifest_excludes_secret_runtime_data` 先失败。
- **验证步骤**：
  1. Windows 干净目录启动
  2. 运行 E2E-01 Mock
  3. 字符串与文件 Secret 扫描
- **依赖**：T099,T104,T110
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T105.xml
  - evidence/diffs/T105.patch
  - `AGENT_LOG.md` 中的 T105 记录
- **Commit**：`未填写`

## T106 — LOCAL_FULL 与 CLOUD_DEMO 强隔离 Profile

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-delivery`
- **覆盖需求**：`OQ-08～11/19/20`, `公共云演示风险`
- **目标**：在代码层强制区分本地完整版本和云端 Mock 演示。
- **涉及文件**：
  - `backend/src/se_mentor/runtime/profiles.py`
  - `backend/tests/security/test_runtime_profiles.py`
  - `deploy/demo-workspace/`
- **预期实现要点**：
  - CLOUD_DEMO 仅预置仓库、Mock LLM、只允许演示工具集
  - 禁止上传仓库和任意 Shell
  - 数据按任务或每日重置
- **将要先写的失败测试**：
  - `test_T106_cloud_demo_cannot_register_host_path_use_real_llm_or_arbitrary_shell` 先失败。
- **验证步骤**：
  1. Profile 绕过测试
  2. 宿主敏感目录不可见
  3. 重置脚本幂等
- **依赖**：T005,T057,T085
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T106.xml
  - evidence/diffs/T106.patch
  - `AGENT_LOG.md` 中的 T106 记录
- **Commit**：`未填写`

## T107 — Docker 镜像、Compose 与持久化

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-delivery`
- **覆盖需求**：`阿里云部署基础`, `NFR-SEC`
- **目标**：构建非 root 多阶段镜像和本地 Compose，持久化 SQLite、备份和必要日志。
- **涉及文件**：
  - `backend/Dockerfile`
  - `frontend/Dockerfile`
  - `deploy/docker-compose.yml`
  - `deploy/scripts/smoke_compose.sh`
- **预期实现要点**：
  - 镜像不可含开发者 Key
  - FastAPI 内部端口不直接公网暴露
  - 重启后数据和知识保留
- **将要先写的失败测试**：
  - `test_T107_image_and_compose_secret_scan_and_persistence` 先失败。
- **验证步骤**：
  1. 本地 compose health
  2. 重启持久化
  3. 容器只挂载预置演示工作区
- **依赖**：T106,T099,T110
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T107.xml
  - evidence/diffs/T107.patch
  - `AGENT_LOG.md` 中的 T107 记录
- **Commit**：`未填写`

## T108 — Nginx、SSE、HTTPS 与安全头

- **状态**：[ ] 未开始；HTTPS 最终证据待外部环境
- **阻塞说明**：最终证书与域名由 T109 外部资源提供
- **Worktree**：`wt-delivery`
- **覆盖需求**：`AC-DEPLOY-ALIYUN`, `NFR-PERF-05`
- **目标**：配置反向代理、SSE 不缓冲、HTTPS、安全头和合理超时/请求限制。
- **涉及文件**：
  - `deploy/nginx/se-mentor.conf`
  - `deploy/nginx/README.md`
  - `deploy/tests/test_nginx_config.py`
- **预期实现要点**：
  - 仅开放 80/443，应用端口内部
  - SSE keep-alive 和 proxy_buffering off
  - 证书路径不进 Git
- **将要先写的失败测试**：
  - `test_T108_nginx_sse_and_security_contract` 先失败。
- **验证步骤**：
  1. nginx config test
  2. SSE 断线重连
  3. HTTPS smoke 需部署后证据
- **依赖**：T090,T107
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T108.xml
  - evidence/diffs/T108.patch
  - `AGENT_LOG.md` 中的 T108 记录
- **Commit**：`未填写`

## T109 — ACR、ECS 部署、健康检查与版本回滚

- **状态**：[!] 实现未开始；云端验收外部阻塞
- **阻塞说明**：需要阿里云 ACR/ECS、受限 RAM 凭据、域名和证书
- **Worktree**：`wt-delivery`
- **覆盖需求**：`AC-DEPLOY-ALIYUN`, `AC-CI`, `发布门禁`
- **目标**：使用非主账号受限凭据推送不可变镜像，部署单实例 ECS，健康失败恢复上一镜像。
- **涉及文件**：
  - `deploy/scripts/build_push_acr.sh`
  - `deploy/scripts/deploy_ecs.sh`
  - `deploy/scripts/rollback_ecs.sh`
  - `evidence/aliyun-deployment/.gitkeep`
- **预期实现要点**：
  - 安全组只开放必要端口
  - CI 凭据为 protected/masked
  - 云端无开发者 LLM Key
- **将要先写的失败测试**：
  - `test_T109_deploy_script_uses_immutable_tag_health_check_and_rollback` 先失败。
- **验证步骤**：
  1. 脚本静态测试
  2. ECS 实际 health/HTTPS/SSE
  3. 部署失败回滚证据
- **依赖**：T108,T110
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T109.xml
  - evidence/diffs/T109.patch
  - `AGENT_LOG.md` 中的 T109 记录
- **Commit**：`未填写`

## T110 — GitLab CI、Secret 扫描与受保护部署

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-delivery`
- **覆盖需求**：`AC-CI`, `发布门禁`
- **目标**：建立明确名为 `unit-test` 的 Job，并运行后端、前端、E2E、安全、迁移、Secret 和构建检查。
- **涉及文件**：
  - `.gitlab-ci.yml`
  - `scripts/ci/`
  - `tests/meta/test_ci_contract.py`
- **预期实现要点**：
  - 测试失败阻止 pipeline
  - 只有受保护分支/Tag 部署
  - 镜像使用不可变 tag，health 失败触发 rollback
- **将要先写的失败测试**：
  - `test_T110_ci_has_unit_test_and_blocks_on_secret_or_failed_test` 先失败。
- **验证步骤**：
  1. CI YAML 契约
  2. 本地模拟关键 Jobs
  3. 最后 pipeline 链接写入验收报告
- **依赖**：T003,T008,T085,T099
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T110.xml
  - evidence/diffs/T110.patch
  - `AGENT_LOG.md` 中的 T110 记录
- **Commit**：`未填写`

## T111 — 架构、安全边界与模块偏离文档

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-delivery`
- **覆盖需求**：`架构设计`, `审查目录漂移问题`
- **目标**：记录最终模块边界、数据流、信任边界、ExecutionPolicy 双层强制和任何对 SPEC 目录结构的批准偏离。
- **涉及文件**：
  - `docs/ARCHITECTURE.md`
  - `docs/SECURITY_BOUNDARIES.md`
  - `docs/ARCHITECTURE_DECISIONS.md`
- **预期实现要点**：
  - 每个偏离包含理由、影响和批准记录
  - 图示本地/云端边界
  - 明确自研 Harness 与禁止依赖现成 Agent Runner
- **将要先写的失败测试**：
  - `test_T111_required_architecture_and_security_sections_exist` 先失败。
- **验证步骤**：
  1. 文档契约
  2. 代码路径抽查
  3. 冷启动 subagent 可定位组件
- **依赖**：T057,T078,T106
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T111.xml
  - evidence/diffs/T111.patch
  - `AGENT_LOG.md` 中的 T111 记录
- **Commit**：`未填写`

## T112 — README、运行、凭据、恢复与部署说明

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-delivery`
- **覆盖需求**：`README 交付`, `AC-DIST-WIN`, `AC-DEPLOY-ALIYUN`
- **目标**：让陌生用户可按文档安装、Mock 运行、配置/清除 Key、恢复、打包和部署。
- **涉及文件**：
  - `README.md`
  - `docs/RUNBOOK.md`
  - `deploy/README.md`
- **预期实现要点**：
  - 命令与实际一致
  - 明确已知限制和 P1 延后项
  - 错误恢复与回滚步骤可操作
- **将要先写的失败测试**：
  - `test_T112_readme_contract_and_commands_exist` 先失败。
- **验证步骤**：
  1. 从干净 clone 按文档运行 Mock
  2. 链接和命令检查
  3. Windows/阿里云外部步骤标出前置资源
- **依赖**：T105,T109,T111
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T112.xml
  - evidence/diffs/T112.patch
  - `AGENT_LOG.md` 中的 T112 记录
- **Commit**：`未填写`

## T113 — 可复现机制演示场景

- **状态**：[ ] 未开始
- **阻塞说明**：无
- **Worktree**：`wt-delivery`
- **覆盖需求**：`课程演示`, `FR-12`, `US 闭环`
- **目标**：提供 ALLOW、WARN、BLOCK、自动修正、停滞、回滚和知识保鲜的演示入口。
- **涉及文件**：
  - `demo/run_demo.py`
  - `demo/scenarios/`
  - `demo/README.md`
- **预期实现要点**：
  - 每场景从干净 Git 状态开始
  - 输出决策、证据、策略、diff、验证和知识摘要
  - 默认 Mock 离线
- **将要先写的失败测试**：
  - `test_T113_demo_scenarios_are_repeatable_and_match_expected_outcomes` 先失败。
- **验证步骤**：
  1. 重复运行
  2. 退出码
  3. 录屏脚本说明
- **依赖**：T085,T099
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T113.xml
  - evidence/diffs/T113.patch
  - `AGENT_LOG.md` 中的 T113 记录
- **Commit**：`未填写`

## T114 — 陌生智能体冷启动验证与二次修订

- **状态**：[ ] 首轮未执行；最终复跑未执行
- **阻塞说明**：需在计划冻结后立即执行首轮，发布前执行第二轮
- **Worktree**：`wt-delivery`
- **覆盖需求**：`审查 Cold Start`, `SPEC_PROCESS`
- **目标**：分别在核心实现前后让不同新鲜 subagent 仅凭 SPEC/PLAN 实施指定 Task，记录歧义和修订。
- **涉及文件**：
  - `docs/COLD_START_REPORT.md`
  - `SPEC_PROCESS.md`
  - `PLAN.md`
- **预期实现要点**：
  - 不提供历史对话
  - 遇不确定必须暂停
  - 每个问题必须落到 SPEC/PLAN diff 并由另一 subagent 复读
- **将要先写的失败测试**：
  - 本 Task 的失败测试是冷启动 subagent 产生的暂停点或错误实现记录；若无实际记录则任务失败。
- **验证步骤**：
  1. 至少两次不同类型 subagent
  2. 修订前后对比
  3. 未解决歧义标 [!] 并阻止对应实现
- **依赖**：T001,T004
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T114.xml
  - evidence/diffs/T114.patch
  - `AGENT_LOG.md` 中的 T114 记录
- **Commit**：`未填写`

## T115 — 生成验收证据、ACCEPTANCE_REPORT 与 Release Gate

- **状态**：[!] 未开始；依赖全部 P0 与外部验收
- **阻塞说明**：Windows 与阿里云证据尚未产生
- **Worktree**：`wt-delivery`
- **覆盖需求**：`9.2～9.22`, `ACCEPTANCE_REPORT.md`, `evidence/`, `发布门禁`
- **目标**：自动汇总 P0 功能、8 个 E2E、性能、安全、凭据、Windows、阿里云、CI、回放、未完成项和证据索引。
- **涉及文件**：
  - `scripts/collect_evidence.py`
  - `scripts/release_gate.py`
  - `ACCEPTANCE_REPORT.md`
  - `evidence/`
- **预期实现要点**：
  - 任一 P0 requirement 无证据即失败
  - 检查 commit、测试、single Alembic head、Secret、外部验收
  - 所有未完成/阻塞/P1 条目显式列出
- **将要先写的失败测试**：
  - `test_T115_release_gate_fails_on_missing_evidence_unfinished_task_or_secret` 先失败。
- **验证步骤**：
  1. 从 TRACEABILITY_MATRIX 生成报告
  2. 证据路径存在性和 hash
  3. release gate 非零条件覆盖 SPEC 9.20
- **依赖**：T001,T102,T105,T109,T110,T113,T114
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T115.xml
  - evidence/diffs/T115.patch
  - `AGENT_LOG.md` 中的 T115 记录
- **Commit**：`未填写`

## T116 — 最终 Spec Compliance、Code Quality 与发布

- **状态**：[!] 未开始；最终门禁
- **阻塞说明**：前置任务和外部验收尚未完成
- **Worktree**：`wt-delivery`
- **覆盖需求**：`最终双阶段评审`, `系统级 DoD`
- **目标**：先做规约合规审查，再做代码质量审查；修复全部 Critical/High 后创建 Release Candidate 和最终 Tag。
- **涉及文件**：
  - `docs/FINAL_REVIEW.md`
  - `AGENT_LOG.md`
  - `REFLECTION.md`
  - `PLAN.md`
- **预期实现要点**：
  - 逐 Task 填写 commit 和证据
  - Git 状态干净，CI 全绿
  - 禁止以文档承诺替代未通过的客观验收
- **将要先写的失败测试**：
  - `test_T116_no_unfinished_p0_or_open_critical_issue_before_release` 先失败。
- **验证步骤**：
  1. 独立 reviewer 两阶段报告
  2. 干净 clone `make test`
  3. Mock demo、Windows、阿里云最终 smoke
- **依赖**：T115
- **可并行性**：否
- **预期证据**：
  - evidence/test-reports/T116.xml
  - evidence/diffs/T116.patch
  - `AGENT_LOG.md` 中的 T116 记录
- **Commit**：`未填写`

# Phase 12 — P1 延后清单

> 下列条目不是遗漏，而是依据 OQ 和 P0 范围显式延后。状态均为 `[~] P1 延后`。

|编号|条目|延后理由|
|---|---|---|
|P1-01|向量数据库/Embedding 检索|OQ-18：P0 不需要；P0 使用确定性检索|
|P1-02|完整多语言 AST 依赖图|P0 Python 符号级、TypeScript 文件级|
|P1-03|自动 Git commit/push/rebase|OQ-15：P0 不自动 commit|
|P1-04|多用户身份与多实例分布式锁|P0 本地单用户、云端基础访问、单实例|
|P1-05|审计 Hash 链/外部不可篡改存储|P0 追加写入与权限保护；若时间允许增强|
|P1-06|公共演示上传真实仓库或调用真实 LLM|OQ-09/OQ-20：P0 禁止|
|P1-07|语义进展相似度模型|OQ-13：P0 规则法|

# 最终里程碑

|里程碑|必须完成 Task|完成证据|
|---|---|---|
|M0 规约可执行|T000～T008、T114 首轮|决策冻结、追踪矩阵、共享契约、单 Head、冷启动报告|
|M1 数据与分析|T009～T043|完整数据模型、索引、知识、ImpactReport|
|M2 治理 Harness|T044～T080|ExecutionPolicy、工具二次检查、主循环、验证与 CompletionGate|
|M3 离线可证明|T081～T085|8 个 E2E、无网络、确定性时间线|
|M4 可交互|T086～T099|REST/SSE、React、浏览器 E2E、可访问性|
|M5 可交付|T100～T113|NFR、Windows、云端、CI、文档、Demo|
|M6 可发布|T114 复跑、T115～T116|ACCEPTANCE_REPORT、全部证据、双阶段评审、Release|

# 全局禁止事项

- 禁止在 T000～T008 和首次冷启动验证完成前大规模并行实现。
- 禁止把现成 Agent Runner、Coding Agent 或 Skill 当作 Harness 主循环。
- 禁止 LLM 自由文本直接调用 Shell、文件系统或改变任务状态。
- 禁止 BLOCK/DENY_HARD 被普通审批覆盖。
- 禁止写工具绕过 WRITE 锁、ExecutionPolicy、PolicyEnforcer、事务和 base revision。
- 禁止为了通过验证删除断言、批量 skip、降低检查标准或缩小必需测试。
- 禁止真实 Key 进入源码、Git、Prompt、日志、DB、子进程、分发包、镜像或验收证据。
- 禁止把聊天记录或 LLM 猜测直接标为 VERIFIED 工程知识。
- 禁止回滚后把未落地变更写成 active 架构事实。
- 禁止没有客观证据就把 Task、P0 Requirement 或 Release 标记完成。
