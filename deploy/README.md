# SE-Mentor Deployment Guide

Status: IMPLEMENTED DEPLOYMENT ARCHITECTURE — FINAL EXTERNAL ACCEPTANCE PARTIALLY PENDING

本文以当前 Repository、`README.md`、`RUNBOOK.md`、`系统架构设计.md`、
`docs/ONLINE_SAFE_PHASE5A_READINESS.md` 和 `docs/PRODUCTION_CD_RUNBOOK.md` 为基线。

## 1. Deployment Scope

SE-Mentor 有四种交付/运行形态：

| 形态 | 定位 | 当前实现状态 | 最终验收状态 |
| --- | --- | --- | --- |
| Local Source | 开发者本地入口 | IMPLEMENTED | 最终回归 TO BE VERIFIED |
| Windows EXE | Windows 本地正式入口，PyInstaller onedir | IMPLEMENTED | 干净 Windows 机器验收 TO BE VERIFIED |
| Formal Online WebUI | 面向真实用户、真实项目与真实 Provider 的正式浏览器产品 | IMPLEMENTED / CURRENT PRODUCT | 公网 HTTPS 与 production ONLINE_SAFE 验收 TO BE VERIFIED |
| Mechanism Demo | 独立、确定性的 Harness 机制演示环境 | IMPLEMENTED | VERIFIED — focused tests 3 PASS；CLI 3/3 PASS |

`deploy/` 主要承载服务器侧的 Formal Online WebUI 与 Mechanism Demo 部署构件。
`CLOUD_DEMO` 若仍出现在 Compose 或 runtime profile 中，只是 Mechanism Demo 的实现术语，
不能据此把整个 Online WebUI 定义为 Demo。

## 2. Formal Online Product

Formal Online WebUI 的目标拓扑为：

```text
Browser
  -> HTTPS
  -> Reverse Proxy / Nginx
  -> FastAPI
  -> SE-Mentor self-built Harness
  -> Per-user Workspace
```

它复用与本地产品相同的 Harness 主链路：Project Bootstrap、Proposal、User Confirmation、
ContextPackage、Impact Analysis、Governance、Approval、ExecutionPolicy、受控执行、Validation、
Recovery 与 Engineering Knowledge。正式在线形态面向真实用户、用户自己的项目副本、
用户级 Session 和真实 Provider path。

Online WebUI 的产品实现与“允许公网真实用户安全使用真实 Provider”是两种状态：

- Formal Online WebUI：IMPLEMENTED / CURRENT PRODUCT。
- Online workspace / user isolation architecture：IMPLEMENTED。
- Production-safe real-provider public acceptance：TO BE VERIFIED。

正式开放 real-provider public mode 前，必须对 Authentication、Session、Project Ownership、
Workspace、Credential、Execution 与 Persistence Isolation 做目标环境验收。没有这些证据时，
不得用 Mechanism Demo 或普通 health check 代替 production ONLINE_SAFE 验收。

## 3. Online Security Boundary

Formal Online WebUI 必须保持以下边界：

- User ownership：每个 Project、Task、Governance、Credential 与导出物属于明确用户/会话。
- Session isolation：会话标识不能成为跨会话读取数据的授权替代品。
- Project isolation：所有业务查询与命令验证当前主体对项目的 ownership。
- Workspace isolation：上传项目只解压到当前 Session 的服务器 Workspace，并进行路径包含检查。
- Credential isolation：真实 Provider 凭据按用户/Session 隔离，不使用全服务器共享用户 Key。
- Execution isolation：Tool 仍经过 Governance、ExecutionPolicy、PolicyEnforcer、WRITE Lock 与 Transaction。
- Persistence isolation：持久化查询与事件回放按用户、Session 与 Project 过滤。
- Path containment：拒绝绝对宿主路径、路径穿越、符号链接逃逸和跨 Workspace 访问。
- Secret redaction：API、日志、错误、证据、导出物与知识库均不得回显 Secret。

`ONLINE_SAFE` 不访问用户电脑上的本地路径。用户上传的是项目副本，修改发生在当前 Session
隔离的服务器 Workspace 中；导出 ZIP 或 Patch 后由用户自行取回。

## 4. Mechanism Demo Deployment

Mechanism Demo 是独立部署形态，不是 Formal Online WebUI 的别名。它使用：

- Mock / Stub Provider；
- 隔离的 Demo Repository；
- 确定性场景与预期结果；
- 不需要也不接受真实用户 API Key；
- 不接受任意宿主路径；
- 受限 Tool 范围；
- 真实 Harness 的治理、执行、验证、修正、回滚与知识机制。

Demo 中 Mock 的是 LLM，不是整个 Harness。当前确定性 CLI 用于稳定展示 Governance Guardrail、
Feedback-driven Self Correction 与 Engineering Memory / Context；完整产品还包含其他治理与恢复能力。

## 5. Docker

仓库当前提供 `deploy/docker-compose.yml` 与 `deploy/docker-compose.production.yml`：

- backend、frontend、gateway 位于内部 Docker network；
- backend 的 SQLite/runtime 数据位于持久 volume；
- production override 不公开 backend `8000` 和 frontend `8080`；
- production gateway 对外承载 HTTP/HTTPS；
- TLS 证书和 ACME webroot 从宿主机只读挂载，不进入镜像或 Git。

实际启动、构建和 production cutover 命令必须以当前 Repository 中最终部署文件及
`docs/PRODUCTION_CD_RUNBOOK.md` 为准。部署前必须显式确认 runtime profile，不能让正式环境
静默退回 `CLOUD_DEMO`。

## 6. Reverse Proxy / Nginx

Reverse Proxy 负责：

- `/` 转发至 frontend；
- `/api/` 转发至 FastAPI；
- `/health` 转发至 backend health endpoint；
- `GET /api/tasks/{task_id}/events` 作为 SSE 长连接；
- HTTPS 终止、可信 forwarded scheme 与安全响应头；
- 仅将应用内部端口暴露在 Docker internal network。

SSE 路由必须关闭缓存与 buffering，并配置足够的 read/send timeout：

```nginx
proxy_buffering off;
proxy_cache off;
```

生产代理必须覆盖 `X-Forwarded-Proto` 为 `$scheme`。Backend 只有在显式启用可信代理时才可
接受 forwarded scheme；客户端自带的伪造 header 不能建立安全请求。

## 7. Persistence

需要持久化的运行数据包括：

- SQLite / persistent database；
- Project、Task、Governance、Approval 与事件状态；
- Transaction manifest、backup 引用与 recovery metadata；
- Engineering Knowledge、证据引用与 freshness 状态；
- 运行日志和审计事件。

持久数据目录不得与镜像层绑定，也不得在普通容器重建时丢失。Migration 应在服务使用新模型前
完成。备份、恢复与保留策略分别遵循 `RUNBOOK.md`、`docs/MIGRATION_POLICY.md` 与
`docs/DATA_RETENTION.md`。

## 8. Secrets

三类凭据必须分离：

| 凭据 | 使用边界 |
| --- | --- |
| Local LLM credentials | 本地用户凭据存储；不进入项目、Prompt、日志或 SQLite 明文 |
| Online user credentials | 按用户/Session 隔离；不回显；不进入导出物或 Engineering Knowledge |
| Deployment credentials | 由部署平台/宿主机管理；不提供给 Harness 和用户 Workspace |

Secret 不得进入 source、Git history、container image、Dockerfile、普通日志、SQLite plaintext、
Engineering Knowledge、frontend storage、项目 ZIP/Patch、测试证据或子进程环境。TLS private key
和部署 SSH key 也必须保留在 Git 外部。

## 9. Health Check

Health check 只证明服务进程能够响应以及基础依赖可达。它适合容器编排、滚动部署与故障定位，
但不证明 Proposal、Governance、Execution、Validation、SSE、隔离、凭据或真实 Provider 全链路
已经验收。`/health = 200` 不能写成 Harness full acceptance PASS。

## 10. Rollback

必须区分两种 rollback：

- Deployment rollback：把服务重新部署到已知可用的应用版本或镜像；它是运维动作。
- Agent Transaction rollback：依据当前 Task 的 Transaction Manifest 恢复该次受控代码变更；
  它是 Harness 业务能力。

部署 rollback 不能替代 Agent Transaction rollback；Agent rollback 也不会自动回退服务器版本。
两者都不得用无差别 `git reset --hard` 或删除 persistent volume 实现。

## 11. Current Deployment Status

| 项目 | Implementation Status | Current Evidence | Final Verification |
| --- | --- | --- | --- |
| Formal Online WebUI | IMPLEMENTED / CURRENT PRODUCT | `README.md`、`RUNBOOK.md`、ONLINE_SAFE readiness 与当前 deploy 构件 | 公网真实用户全链路 TO BE VERIFIED |
| Online workspace / user isolation architecture | IMPLEMENTED | `docs/ONLINE_SAFE_PHASE5A_READINESS.md` | production ONLINE_SAFE acceptance TO BE VERIFIED |
| Mechanism Demo | IMPLEMENTED | `scripts/demo_harness.py`、focused tests、独立 Demo profile | VERIFIED — 3 tests；CLI 3/3 |
| Docker / Compose | IMPLEMENTED | 当前 Compose 构件 | 目标主机部署 smoke TO BE VERIFIED |
| Nginx / SSE gateway | IMPLEMENTED | 当前 gateway 配置与说明 | 公网 HTTPS/SSE smoke TO BE VERIFIED |
| HTTPS architecture | IMPLEMENTED | production template 与 readiness contract | 证书、443 和外部 smoke TO BE VERIFIED |
| Real-provider production safety | IMPLEMENTED AS ARCHITECTURE AND PRODUCT PATH | ONLINE_SAFE 安全门与人工 E2E 方案 | EXTERNAL ACCEPTANCE REQUIRED |

总体状态：IMPLEMENTATION SUBSTANTIALLY COMPLETE；BUGFIX / STABILIZATION IN PROGRESS；
FINAL ACCEPTANCE EVIDENCE PARTIALLY PENDING。
