# SE-Mentor Spec Process

本文件记录项目实际使用的需求到交付过程，不把历史补写得比真实过程更整齐。

## Authoritative sources

- `SPEC.md`：需求、最终 Runtime Profile 与安全语义。
- `PLAN.md`：Task/依赖的历史计划，以及顶部 Final Closeout Status。
- `docs/TRACEABILITY_MATRIX.md`：requirement → task → component → evidence。
- `AGENT_LOG.md`：实际执行、人工介入、验证和集成记录。
- `docs/FINAL_STATUS.md`：最终提交状态与已知限制。

## Actual delivery flow

```text
requirements
-> Task in PLAN
-> branch / worktree ownership
-> implementation with targeted tests
-> focused review and evidence
-> main integration
-> GitHub CI
-> Release Gate
-> Production Deploy triggered by workflow_run
-> ECS Docker Compose
-> production health/runtime smoke
-> final tag and clean source package
```

项目早期按严格 Task DoD 记录 red/green、Spec Review、Code Review、evidence 和 commit；部分任务
由独立 worktree/branch 完成，部分批次在 main 集成。不是每个历史分支都建立 PR，也没有在收口时
伪造 PR 或补写无法确认的 commit hash。保留的分支/worktree 是过程证据，不表示它们都应再次合并。

## Validation and release distinction

- Targeted validation 证明当前改动及生产关键路径。
- `.github/workflows/ci.yml` 是 Release CI，包含 production-critical quality/tests/security 和
  Release Gate。
- `.github/workflows/repository-health.yml` 独立跟踪 full-tree mypy 与历史 full backend suite debt；
  它不被伪装为全绿，也不与 Release Gate 合并。
- `.gitlab-ci.yml` 保留课程要求的真实 `unit-test` job 和其他 CI jobs。
- Production Deploy 必须由成功的 CI `workflow_run` 自动触发；最终证据不使用手工 SSH 或
  `workflow_dispatch` 替代。

## Final closeout rule

最终收口不扩展功能、不重构架构、不清理历史健康债务。仅集成已经验证的必需 artifact、更新
最终事实、执行 bounded Secret/targeted checks、推送 main、等待自动 CI/CD、创建不可移动的提交
Tag，并从远程 fresh clone 生成保留 `.git` history 的源码包。
