# SE-Mentor

Production CD for the current ONLINE_SAFE deployment is documented in
`docs/PRODUCTION_CD_RUNBOOK.md`. The deployment path is:

```text
main -> CI -> Production Deploy -> ECS /opt/se-mentor -> production compose
```

> **Software Change Proposal Analysis and Governance**  
> 面向真实软件项目的受治理 Coding Agent Harness。

SE-Mentor 是一个将大语言模型的软件修改能力纳入工程治理闭环的 Coding Agent。

它并不是让 LLM 在收到需求后直接修改代码，而是在模型与真实软件项目之间建立一层自研 Harness，将一次软件修改组织为完整的软件工程流程：

```text
用户需求
    ↓
项目理解
    ↓
修改方案 Proposal
    ↓
用户确认
    ↓
影响分析
    ↓
治理决策
    ↓
必要时人工授权
    ↓
ExecutionPolicy
    ↓
受控 Agent 执行
    ↓
代码修改
    ↓
Validation
    ↓
失败修正 / Replan
    ↓
CompletionGate
    ↓
工程知识更新
```

SE-Mentor 希望让 AI 参与的软件修改具备以下能力：

- **可理解**：修改前先理解项目结构、代码关系和用户需求；
- **可确认**：先生成 Proposal，再由用户确认修改范围；
- **可治理**：执行前完成影响分析和安全治理；
- **可约束**：将治理结果转化为机器可执行的 ExecutionPolicy；
- **可验证**：以真实 Build、Test 和 Validation 结果判断任务是否完成；
- **可恢复**：支持取消、回滚和崩溃恢复；
- **可追踪**：Proposal、Governance、Execution、Validation 全过程可记录；
- **可积累**：把经过证据验证的软件工程事实沉淀为长期项目知识。

---

## 1. 为什么需要 SE-Mentor

普通 Coding Agent 的典型工作方式是：

```text
用户需求
    ↓
LLM
    ↓
读取代码
    ↓
修改代码
    ↓
执行命令
```

这种方式虽然高效，但在真实软件工程场景中仍然存在很多问题：

- LLM 是否真正理解了项目？
- 为什么要修改这些文件？
- 修改是否会影响其他模块？
- 某个危险命令为什么被允许执行？
- 用户批准的到底是什么范围？
- Agent 会不会修改需求之外的文件？
- 测试失败之后是否会陷入无限修复循环？
- 任务中途取消之后如何恢复代码？
- 历史项目知识如何判断是否已经过期？
- LLM 声称“任务完成”时，修改真的通过验证了吗？

SE-Mentor 的核心思想是：

> **LLM 负责提出候选推理和动作，Harness 负责状态、治理、权限、执行、验证和恢复。**

---

## 2. 核心工作流程

SE-Mentor 的完整主链路如下：

```text
Project
    ↓
Project Bootstrap
    ↓
Task
    ↓
Proposal
    ↓
User Confirmation
    ↓
ContextPackage
    ↓
Impact Analysis
    ↓
Governance
    ↓
Approval
    ↓
ExecutionPolicy
    ↓
LLM
    ↓
AgentAction
    ↓
Dispatcher
    ↓
PolicyEnforcer
    ↓
WRITE Lock
    ↓
Transaction
    ↓
Tools
    ↓
Code Changes
    ↓
ValidationPlan
    ↓
Validation
    ↓
Failure Classification
    ↓
Feedback
    ↓
Repair / Replan
    ↓
CompletionGate
    ↓
Engineering Knowledge Update
```

异常路径包括：

```text
Execution
    ├── CANCEL → KEEP
    ├── CANCEL → ROLLBACK
    ├── CRASH → RECOVERY
    ├── STAGNATION → REPLAN
    └── BLOCK → STOP
```

---

# 3. 产品形态

SE-Mentor 现在需要明确区分两个概念：

1. **正式产品**
2. **Mechanism Demo**

二者不是同一个运行环境。

## 3.1 正式产品

正式产品目前主要提供四种使用入口：

1. 源码本地运行；
2. CLI；
3. Windows EXE；
4. Online WebUI。

整体关系如下：

```text
                    SE-Mentor
                        │
                 SE-Mentor Harness
                        │
        ┌───────────────┼────────────────┐
        │               │                │
   Source Local        CLI          Windows EXE
        │                                │
        └───────────────┬────────────────┘
                        │
                   Local Product
                        │
                        │
                 Online WebUI
                        │
                  Online Product
```

## 3.2 Mechanism Demo

Mechanism Demo 是独立的演示环境。

它主要用于：

- 课程展示；
- 验收演示；
- 安全机制演示；
- 确定性复现场景。

Demo 默认使用：

- Mock / Stub LLM；
- Demo Repository；
- 预定义场景。

Demo 不承担正式 Online 产品的职责。

---

# 4. 正式产品入口总览

| 使用入口 | 主要用户 | 运行位置 | WebUI | 真实 Provider | 真实项目 |
|---|---|---|---|---|---|
| 源码本地运行 | 开发者 | 用户电脑 | 是 | 是 | 是 |
| CLI | 开发 / 运维 | 用户电脑 | 否 | 按命令能力 | 按命令能力 |
| Windows EXE | 普通本地用户 | 用户电脑 | 是 | 是 | 是 |
| Online WebUI | 在线正式用户 | 服务器 | 是 | 目标支持真实用户 Provider | 服务端隔离工作区 |
| Mechanism Demo | 课程评审 / 展示 | 独立 Demo 环境 | 可用 | Mock / Stub | Demo Repository |

---

# 5. WebUI

SE-Mentor 的主要图形交互界面是一套基于 React + TypeScript 的工程工作台。

它不是宣传官网，也不是把所有工程指标同时堆叠在一个 Dashboard 页面中。

当前正式界面采用：

```text
左侧固定导航
+
右侧主内容区
```

左侧主要页面包括：

- 工作台；
- 任务；
- 项目记忆；
- 治理；
- 评估；
- 设置。

用户通过左侧导航切换当前页面。

关键业务状态由 Backend Harness 决定，Frontend 主要负责：

- 展示；
- 用户输入；
- 发送 Command；
- 订阅实时事件。

Frontend 不应自行伪造：

- Project READY；
- Task COMPLETED；
- Governance APPROVED；
- WRITE Lock；
- Recovery 状态；
- Validation 成功状态。

---

# 6. 工作台

工作台是 SE-Mentor 的主要交互入口。

用户可以在工作台中完成：

```text
打开项目
    ↓
输入软件修改需求
    ↓
Mentor 分析需求
    ↓
生成 Proposal
    ↓
确认 / 调整 Proposal
    ↓
影响分析
    ↓
治理
    ↓
执行
    ↓
查看验证结果
```

主要交互包括：

- 输入修改需求；
- 查看 Mentor 回复；
- 查看 Proposal；
- 调整 Proposal；
- 确认并继续；
- 回答 Mentor 的补充问题；
- 查看任务进度；
- 查看最终修改结果。

工作台输入框固定在页面底部。

Proposal 作为对话历史的一部分展示，不再额外重复渲染一份悬浮 Proposal。

---

# 7. 任务

任务页面用于查看当前项目中的历史软件修改任务。

一个 Task 可以关联：

```text
Request
Proposal
ImpactReport
GovernanceDecision
Approval
ExecutionPolicy
ExecutionTransaction
Validation
Result
Knowledge Update
```

任务状态可能包括：

- 等待补充信息；
- 等待确认；
- 等待授权；
- 等待执行；
- 执行中；
- 验证中；
- 已完成；
- 失败；
- 已取消；
- 已回滚；
- Recovery Required。

切换正在查看的任务只影响 UI。

后台正在执行的 Task 仍然属于原来的 Project，不会因为用户切换页面而改变所有权。

---

# 8. 项目记忆

SE-Mentor 的 Memory 不是普通聊天记录。

系统主要保存：

> **有证据、受版本约束、未来软件修改任务可以复用的软件工程知识。**

例如：

- 项目架构；
- 模块职责；
- API 契约；
- 重要依赖；
- 测试方式；
- 构建方式；
- 历史修改事实；
- 已验证设计决策；
- 项目安全约束。

Knowledge 具有 Freshness。

随着 Repository 演化，知识可能进入：

```text
FRESH
    ↓
DRIFTED
    ↓
STALE
```

旧的项目记忆不能无条件覆盖当前 Repository 中的真实代码事实。

---

# 9. Proposal

SE-Mentor 不会直接把用户自然语言需求立即转化为代码修改。

系统首先生成 Proposal。

例如：

```text
用户：

给用户模块增加 email 字段，并补充测试。

Mentor：

目标
- 增加用户 email 字段

计划
- 更新用户模型
- 同步接口校验
- 补充相关测试

预计范围
- 4 个文件

风险
- 无高风险操作
```

用户可以：

- 确认；
- 调整；
- 补充信息。

Proposal Confirmation 表示：

> 用户同意系统基于当前修改目标继续执行影响分析和治理。

它并不代表 Agent 已经获得无限制写权限。

---

# 10. Impact Analysis

Proposal 确认后，Mentor 根据：

- Code Index；
- Symbol Relations；
- Git；
- Engineering Knowledge；
- Repository Evidence；

生成 ImpactReport。

Impact Analysis 可以分析：

- 直接影响文件；
- 相关模块；
- 调用关系；
- 测试影响；
- 配置影响；
- 数据模型影响；
- 潜在风险传播。

ImpactReport 是 Governance 的核心输入之一。

---

# 11. Governance

Governance 需要回答的问题是：

> **这次修改是否允许执行，以及允许执行到什么范围。**

主要决策包括：

```text
ALLOW

WARN / REQUIRE_APPROVAL

BLOCK
```

规则优先级为：

```text
DENY_HARD
>
REQUIRE_APPROVAL
>
ALLOW
```

因此即使某些规则允许修改，只要命中 `DENY_HARD`：

```text
最终结果 = BLOCK
```

普通 Approval 不能覆盖 `DENY_HARD`。

---

# 12. 治理页面

治理页面用于记录项目中每一次真实治理过程。

它不是只显示当前最近一次 Governance。

每条治理记录可以展示：

- Task；
- Impact；
- Risk；
- Rule Hits；
- GovernanceDecision；
- Approval；
- ExecutionPolicy；
- 当前权限状态。

治理历史采用单列长条形式展示，便于按照任务时间顺序回顾。

---

# 13. Approval

对于：

```text
WARN
或
REQUIRE_APPROVAL
```

系统进入：

```text
Governance
    ↓
Approval Required
    ↓
用户批准
    ↓
TemporaryGrant / Approval
    ↓
ExecutionPolicy
```

Approval 和 Execute 是两个不同动作。

用户批准表示：

> 当前 Task 可以在被批准的范围内继续。

它不表示：

> Task 已经拥有 Repository WRITE ownership。

真正的写操作仍然需要获得 WRITE Lock。

---

# 14. ExecutionPolicy

Governance 输出的不只是一段自然语言安全提示。

系统会把治理结果编译为机器可以执行的 ExecutionPolicy。

典型内容包括：

```text
readable_paths
writable_paths
protected_paths
allowed_commands
denied_commands
network_allowed
expires_at
project_id
task_id
```

例如：

```text
禁止修改 .env
```

最终会成为 Tool 执行层能够真正拒绝的机器规则。

---

# 15. 双层策略强制

SE-Mentor 使用两层策略控制：

```text
GovernanceEngine
+
PolicyEnforcer
```

第一层：

```text
AgentAction
    ↓
GovernanceEngine
    ↓
ALLOW / APPROVAL / BLOCK
```

第二层：

```text
Dispatcher
    ↓
PolicyEnforcer
    ↓
检查真实 Tool 参数
    ↓
Tool
```

因此即使 Orchestrator 错误地产生了越界 Tool Action，执行层仍然可以拒绝。

---

# 16. WRITE Lock

Governance 决定：

```text
这个动作能不能写
```

WRITE Lock 决定：

```text
当前由哪个 Task 写
```

因此：

```text
Approval
≠
WRITE Lock
```

同一个 Project 不允许多个写任务无约束地同时修改同一个工作区。

---

# 17. Transaction

所有具有写副作用的操作需要进入 Transaction。

Transaction 可以记录：

- CREATE；
- MODIFY；
- DELETE；
- 修改前 Hash；
- 修改后 Hash；
- Backup；
- Base Revision。

这使 SE-Mentor 可以处理：

- Cancel；
- Rollback；
- Crash；
- 外部修改冲突。

---

# 18. Validation

代码修改成功并不代表 Task 完成。

修改后仍然需要进入 Validation。

根据项目类型，Validation 可以运行：

- pytest；
- Vitest；
- Build；
- Type Check；
- Static Analysis；
- Git Diff；
- 项目专用验证。

最终完成状态由 CompletionGate 判断。

LLM 没有权力仅凭自然语言回复：

```text
任务已完成
```

来结束 Task。

---

# 19. Feedback 与自动修正

如果 Validation 失败：

```text
Validation Failed
    ↓
Failure Classification
    ↓
Feedback
    ↓
LLM
    ↓
Repair Action
    ↓
Validation
```

失败信息会作为下一轮 Agent 行动的工程反馈。

同时系统通过 Stagnation Detection 防止：

- 重复执行相同动作；
- 重复产生相同错误；
- 无限修复循环；
- 无意义 Token 消耗。

如果无法继续取得进展，可以进入：

```text
REPLAN
```

或者：

```text
STOP
```

---

# 20. Cancel、Rollback 与 Recovery

任务取消不是简单 Kill Agent。

正常流程为：

```text
Cancel Requested
    ↓
停止新的 LLM Call
    ↓
停止新的 AgentAction
    ↓
安全终止可取消 Tool
    ↓
达到 Safe Point
    ↓
KEEP / ROLLBACK
```

## KEEP

保留当前已经安全写入的代码。

## ROLLBACK

根据 Transaction Manifest 恢复本次 Task 的修改。

系统不默认使用：

```bash
git reset --hard
```

因为这样可能覆盖用户自己尚未提交的修改。

## Crash Recovery

如果程序在写入过程中异常退出：

```text
PREPARED / APPLYING Transaction
    ↓
Restart
    ↓
RECOVERY_REQUIRED
```

Recovery 完成前不得启动新的 WRITE Task。

---

# 21. 使用方式一：源码本地运行

适合：

- 开发 SE-Mentor；
- 调试 Backend；
- 调试 React；
- 查看 API；
- 查看 SSE；
- 定位 Harness 问题。

运行结构：

```text
React / Vite :5173
        │
    REST / SSE
        │
FastAPI :8000
        │
SE-Mentor Harness
        │
Local Git Repository
```

## 21.1 启动 Backend

PowerShell：

```powershell
cd C:\Users\ww\Desktop\SE-w-mentor

$env:PYTHONPATH=(Resolve-Path backend\src).Path

.\backend\.venv\Scripts\python.exe -m uvicorn se_mentor.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

或者进入 Backend：

```powershell
cd C:\Users\ww\Desktop\SE-w-mentor\backend

.\.venv\Scripts\python.exe -m uvicorn se_mentor.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

注意：

```text
se_mentor.main:create_app
```

需要配合：

```text
--factory
```

不要使用：

```text
se_mentor.main:app
```

除非未来代码重新提供模块级 `app`。

## 21.2 启动 Frontend

新开一个 PowerShell：

```powershell
cd C:\Users\ww\Desktop\SE-w-mentor\frontend

npm run dev -- --host 127.0.0.1 --port 5173
```

打开：

```text
http://127.0.0.1:5173
```

---

# 22. 使用方式二：CLI

CLI 是 SE-Mentor 的命令行管理入口。

当前已经明确的 CLI 能力主要包括凭据生命周期管理：

```text
set
status
update
clear
```

相关实现主要位于：

```text
backend/src/se_mentor/cli/
backend/src/se_mentor/cli/credentials.py
```

CLI 和 WebUI 不应该分别实现两套业务逻辑。

它们最终应复用相同的 Backend Service。

当前 README 不将 CLI 描述为已经完全替代 WebUI 的完整 Agent 操作方式。

也就是说，如果仓库尚未真正实现完整 Task CLI，则不能声称已经支持：

```text
CLI
↓
Proposal
↓
Governance
↓
Execution
↓
Validation
```

完整链路。

---

# 23. 使用方式三：Windows EXE

Windows EXE 是普通本地用户的正式使用方式。

目标发布形式：

```text
SE-Mentor-Windows-x64.zip
```

采用：

```text
PyInstaller onedir
```

而不是：

```text
onefile
```

运行结构：

```text
Windows 用户
    ↓
sementor.exe
    ↓
Local FastAPI
    ↓
React Static Assets
    ↓
Browser WebUI
    ↓
SE-Mentor Harness
    ↓
Local Git Repository
```

EXE 并不是另一套桌面 UI。

它主要负责将以下组件统一打包：

- Python Backend；
- React 静态资源；
- Migration；
- Runtime Dependencies；
- Launcher。

普通用户不需要再手动运行：

```text
uvicorn
npm
Vite
PYTHONPATH
```

---

# 24. Windows 分发内容

典型分发结构：

```text
dist/
└── SE-Mentor/
    ├── sementor.exe
    ├── _internal/
    ├── web/
    ├── migrations/
    ├── schemas/
    └── README.txt
```

分发包不得包含：

- OpenAI API Key；
- `.env` Secret；
- 开发数据库；
- 开发日志；
- 历史 Backup；
- 用户 Repository；
- 开发者 Credential。

首次运行时再创建用户自己的 Runtime Data。

---

# 25. 使用方式四：Online WebUI

Online WebUI 是当前 SE-Mentor 的正式产品入口之一。

它不再等同于 Mechanism Demo。

用户通过浏览器访问：

```text
https://<SE-Mentor Online URL>
```

Online WebUI 仍然使用与本地版本一致的核心工作台：

- 工作台；
- 任务；
- 项目记忆；
- 治理；
- 评估；
- 设置。

正式 Online WebUI 的目标是：

> 让真实用户通过浏览器使用真实的 SE-Mentor Harness 完成真实软件工程任务。

---

# 26. Online WebUI 架构

正式 Online WebUI 的基本结构为：

```text
Browser
    ↓
HTTPS
    ↓
Reverse Proxy
    ↓
FastAPI
    ↓
SE-Mentor Harness
    ↓
Per-user Project Workspace
```

与本地版本不同，Online WebUI 的代码执行发生在服务器工作区。

因此 Online 版本不能直接访问访问者电脑中的：

```text
C:\Users\...
D:\Projects\...
```

浏览器本身没有直接访问用户本地任意 Git Repository 的能力。

在线项目需要进入服务器隔离工作区之后再由 Harness 处理。

---

# 27. Online WebUI 的真实使用目标

Online WebUI 不再设计成：

```text
固定 Demo Repository
+
Mock LLM
+
只读演示
```

正式产品目标包括：

- 真实用户；
- 真实 Session；
- 用户自己的 Project；
- 真实 Task；
- Proposal；
- Impact；
- Governance；
- Approval；
- ExecutionPolicy；
- Agent Execution；
- Validation；
- Engineering Knowledge；
- 用户自己的真实 LLM Provider。

正式 Online Provider 的目标是：

```text
User-provided OpenAI-compatible Provider
```

而不是固定 Mock Provider。

---

# 28. Online WebUI 安全边界

因为正式 Online WebUI 面向：

```text
真实用户
+
真实代码
+
真实 Provider Secret
+
真实 Agent Side Effect
```

所以不能简单把单用户 Local Harness 直接暴露到公网。

正式 Online 环境至少需要保证：

## Authentication

真实用户拥有明确身份。

## Session Isolation

用户 A 不能访问用户 B 的：

- Project；
- Task；
- Governance；
- Memory；
- Credential；
- Transaction。

## Project Isolation

每个 Project Workspace 必须绑定明确用户。

## Credential Isolation

用户 Provider Secret 必须：

- 用户级隔离；
- 不返回 Frontend；
- 不进入普通日志；
- 不进入 Engineering Knowledge；
- 不被其他用户访问；
- 不被项目子进程继承。

## Execution Isolation

用户 A 的 Agent 不得访问用户 B 的 Workspace。

## Persistence Isolation

数据库查询除了 Project ID 之外，还需要检查用户 Ownership。

---

## 运行模式（Runtime Profiles）

SE-Mentor 提供三种相互独立的运行模式：

- `LOCAL_FULL`：本地完整模式。用户通过“打开本地仓库”选择本机 Git 仓库，SE-Mentor 直接在本地项目上执行完整的软件修改流程。
- `CLOUD_DEMO`：公网演示模式。使用固定 Demo Workspace 与内置 Mock Provider，不需要也不接受真实 API Key。
- `ONLINE_SAFE`：公网真实运行模式。用户填写自己的 OpenAI-compatible 模型凭据并上传项目 ZIP；SE-Mentor 将项目安全解压到当前 Session 独立的服务器 Workspace 中，通过真实 Harness 完成 Proposal、Impact、Governance、Execution 等流程，并允许用户下载修改后的 ZIP 或 Patch。

`ONLINE_SAFE` 不直接访问用户电脑的本地文件系统，也不依赖 Local Bridge。用户上传的是项目副本，所有修改仅发生在当前 Session 隔离的服务器 Workspace 中。

HTTPS、Trusted Proxy、安全凭据以及真实 Web 全链路验收说明见 `docs/ONLINE_SAFE_PHASE5A_READINESS.md`。

---
# 29. Online Provider 上线原则

Online WebUI 的产品目标是支持真实用户自己的 Provider。

但：

> **实现了 Real Provider API，并不等于公网环境已经安全允许任何用户输入 API Key。**

只有 Authentication、Session Isolation、Workspace Isolation 和 Credential Isolation 等 ONLINE_SAFE 条件完成并验收之后，才能正式开放：

```text
Public Real-provider Mode
```

在此之前不能为了演示方便跳过多用户安全边界。

---

# 30. 凭据管理

## 30.1 本地版本

正式 Windows 本地版本使用：

```text
CredentialService
    ↓
CredentialStore Protocol
    ↓
KeyringCredentialStore
    ↓
Windows Credential Manager
```

支持：

```text
SET
STATUS
UPDATE
CLEAR
```

真实 Key 不应进入：

- Git；
- SQLite 明文；
- 普通日志；
- Prompt；
- Engineering Knowledge；
- 项目子进程；
- Windows 分发包。

`.env` 只允许用于受控开发测试。

## 30.2 Online 版本

Online 环境不能简单复用 Windows Credential Manager。

它需要独立的用户级 Secret Storage：

```text
Authenticated User
    ↓
CredentialService
    ↓
Per-user Protected Secret Store
    ↓
Provider Access
```

真实 Secret 不应保存在浏览器 localStorage 中。

---

# 31. Mechanism Demo

Mechanism Demo 从正式 Online WebUI 中独立出来。

它的目标不是提供正式生产使用，而是：

> **稳定、确定性地证明 SE-Mentor 的核心 Harness 机制。**

Demo 默认使用：

```text
MockLLMProvider
或
Stub LLM
```

并配合预置 Demo Repository。

这样可以：

- 不消耗真实 Token；
- 避免 Provider 网络波动；
- 避免模型随机性；
- 确保课堂现场演示稳定；
- 确保每次可以触发相同治理场景。

---

# 32. Mechanism Demo 场景

Demo 重点展示以下场景。

## 32.1 ALLOW

```text
普通安全修改
    ↓
Impact
    ↓
ALLOW
    ↓
Execution
```

## 32.2 WARN

```text
高风险修改
    ↓
REQUIRE_APPROVAL
    ↓
用户批准
    ↓
ExecutionPolicy
    ↓
Execution
```

## 32.3 BLOCK

```text
危险行为
    ↓
DENY_HARD
    ↓
BLOCK
```

## 32.4 自动修正

```text
Code Change
    ↓
Test Failed
    ↓
Feedback
    ↓
Repair
    ↓
Test Passed
```

## 32.5 Stagnation

```text
Repeated Failure
    ↓
Stagnation Detected
    ↓
REPLAN / STOP
```

## 32.6 Rollback

```text
Execution
    ↓
Cancel
    ↓
Rollback
    ↓
Transaction Restore
```

## 32.7 Knowledge Freshness

```text
Old Knowledge
    ↓
Repository Changed
    ↓
Freshness Check
    ↓
DRIFTED / STALE
```

---

# 33. Online WebUI 与 Mechanism Demo 的区别

| 项目 | Online WebUI | Mechanism Demo |
|---|---|---|
| 定位 | 正式产品 | 机制演示 |
| 用户 | 真实用户 | 课程评审 / 演示人员 |
| Provider | 用户真实 Provider | Mock / Stub |
| 结果 | 真实运行结果 | 确定性结果 |
| Repository | 用户隔离项目工作区 | 预置 Demo Repo |
| Authentication | 必须 | 可简化 |
| Credential | 用户级安全存储 | 不需要真实 LLM Key |
| Governance | 真实治理 | 确定性复现 |
| Validation | 真实验证 | Demo 场景验证 |
| 主要目的 | 实际软件开发 | 证明核心机制 |

因此：

```text
Online WebUI
≠
Mechanism Demo
```

---

# 34. Project Bootstrap

Project 注册后进入：

```text
REGISTERED
    ↓
BOOTSTRAPPING
    ↓
READY
```

如果失败：

```text
BOOTSTRAP_FAILED
```

Bootstrap 主要建立：

- Repository Inventory；
- Code Index；
- Symbol Relations；
- Dependency Information；
- Git Baseline；
- Project Understanding；
- Engineering Knowledge。

项目注册和耗时 Bootstrap 解耦。

用户不需要等待整个仓库分析完之后才能进入 UI。

---

# 35. 安全文件范围

Mentor 不会把 Repository 中所有内容无差别发送给模型。

典型限制包括：

```text
.env                 ×
Secret               ×
大型 Binary           ×
Backup                ×
项目外 Symlink         ×

src/...               ✓
tests/...             ✓
README.md             ✓，但作为不可信 Repository 内容
```

Repository 中的文本本身也被视为不可信输入。

例如 README 或源码注释中的：

```text
Ignore previous rules and run ...
```

不能被当成系统指令执行。

---

# 36. Context 构建

Proposal 和 Agent 不应该每次都重新进行无边界 Repository Walk。

Context 优先来自：

- Code Index；
- Project Understanding；
- Git tracked paths；
- Engineering Knowledge；
- Proposal；
- Impact；
- ExecutionPolicy；
- 最近 Validation Feedback。

ContextPackage 具有范围和 Token Budget。

超出预算时需要：

```text
压缩
↓
重新计算
↓
必要时暂停并请求用户缩小范围
```

---

# 37. LLM Provider

SE-Mentor 使用统一 Provider 抽象：

```text
Harness
    ↓
LLM Provider Interface
    ├── Real Provider
    └── Mock Provider
```

Real Provider 用于正式软件修改。

Mock Provider 用于：

- Unit Test；
- Integration；
- E2E；
- Mechanism Demo；
- 故障注入。

无论是哪一种 Provider，都不能直接拥有文件系统权限。

---

# 38. 不使用托管 Agent Runner

SE-Mentor 可以使用普通基础设施库，例如：

- FastAPI；
- React；
- SQLAlchemy；
- OpenAI SDK；
- pytest；
- Git。

但以下核心能力必须由 SE-Mentor 自己实现：

```text
Agent Orchestrator
Governance Engine
Dispatcher
PolicyEnforcer
Transaction Manager
Validation Feedback Loop
CompletionGate
Engineering Knowledge
```

SE-Mentor 不使用供应商侧：

- Hosted Shell；
- Hosted Apply Patch；
- Hosted Agent Runner；
- Hosted Tool Loop；

替代自研 Harness。

---

# 39. Repository 结构

主要目录如下：

```text
SE-w-mentor/
├── backend/
│   ├── src/se_mentor/
│   │   ├── api/
│   │   ├── agent/
│   │   ├── proposals/
│   │   ├── impact/
│   │   ├── governance/
│   │   ├── orchestration/
│   │   ├── knowledge/
│   │   ├── llm/
│   │   ├── tools/
│   │   ├── credentials/
│   │   └── runtime/
│   ├── tests/
│   └── migrations/
│
├── frontend/
│   ├── src/
│   └── tests/
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SECURITY_BOUNDARIES.md
│   ├── ARCHITECTURE_DECISIONS.md
│   └── RUNBOOK.md
│
├── deploy/
├── packaging/
├── scripts/
├── demo/
├── evidence/
├── SPEC.md
├── PLAN.md
├── TRACEABILITY_MATRIX.md
├── AGENT_LOG.md
├── REFLECTION.md
├── ACCEPTANCE_REPORT.md
└── README.md
```

最终目录以当前 Repository 实际实现为准。

---

# 40. Windows 构建

Windows 构建入口：

```powershell
.\scripts\build_windows.ps1
```

Smoke：

```powershell
.\scripts\smoke_windows.ps1
```

Windows 分发采用：

```text
PyInstaller onedir
```

而不是：

```text
onefile
```

这样可以更方便地管理：

- React 静态资源；
- Migration；
- Schema；
- Runtime Dependencies；
- 调试信息。

---

# 41. Online 部署

正式 Online WebUI 的服务端运行可以使用：

- Docker；
- Docker Compose；
- Nginx；
- FastAPI；
- React Static Assets；
- Persistent Storage。

基本结构：

```text
Internet
    ↓
HTTPS
    ↓
Nginx
    ↓
SE-Mentor Backend
    ↓
Harness
    ↓
Per-user Workspace
```

详细部署说明见：

```text
deploy/README.md
```

---

# 42. REST 与 SSE

WebUI 与 Backend 主要通过：

```text
REST
+
SSE
```

通信。

REST 主要负责：

- Project；
- Task；
- Proposal；
- Approval；
- Execute；
- Recovery；
- 状态查询。

SSE 主要负责：

- Agent Progress；
- Task Event；
- Governance；
- Tool Execution；
- Validation；
- Recovery Progress。

SSE 不是持久化状态数据库。

如果 SSE 中断，页面应：

```text
重新建立 SSE
+
通过 REST 获取当前真实状态
```

---

# 43. 重要安全不变量

无论通过 Local、EXE 还是 Online 运行，以下规则不能被破坏：

1. LLM 不直接操作文件系统；
2. LLM 不直接执行 Shell；
3. WebUI 不直接执行 Tool；
4. BLOCK / DENY_HARD 不能被普通 Approval 覆盖；
5. 写操作必须受到 ExecutionPolicy 约束；
6. Tool 必须经过 PolicyEnforcer；
7. 写操作必须获得 WRITE Lock；
8. 写操作必须进入 Transaction；
9. Side Effect 必须可审计；
10. Cancel 不能破坏事务一致性；
11. Recovery 未完成前不能继续 WRITE；
12. Knowledge 必须具有 Evidence 和 Freshness；
13. Frontend 不是业务状态权威；
14. 真实 Secret 不进入 Prompt、Knowledge、普通日志或项目子进程；
15. 多用户 Online 模式必须实现 User / Session / Workspace / Credential 隔离；
16. Mechanism Demo 不使用真实用户 Provider Key；
17. 外部 Agent Runner 不得替代自研 Harness。

---

# 44. 测试

SE-Mentor 的核心机制支持在无真实 Provider 的情况下使用 MockLLMProvider 完成测试。

主要验证层包括：

```text
Unit
Integration
Contract
E2E
Security
Migration
Frontend
Secret Scan
Packaging
Deployment
```

测试失败时不能通过：

- 删除测试；
- 跳过测试；
- 降低质量门；
- 修改断言；
- 将失败记录伪造为 PASS；

获得所谓“完成”。

---

# 45. 已知交付边界

README 必须区分两个概念：

```text
IMPLEMENTED
```

和：

```text
VERIFIED IN TARGET ENVIRONMENT
```

例如：

```text
Windows Packaging 已实现
```

不等于：

```text
已经在另一台干净 Windows 10/11 x64 机器完成最终验收
```

同理：

```text
Online WebUI 已实现
```

也不自动等于：

```text
公网真实用户 + 真实 Provider 模式已经满足 Production Safety
```

只有获得对应目标环境证据之后，才能在最终 Acceptance Report 中宣称完全验收。

---

# 46. 当前使用方式

如果你是 SE-Mentor 开发者：

```text
源码本地运行
```

如果你需要命令行管理：

```text
CLI
```

如果你希望在自己的 Windows 电脑上正式操作本地 Git 项目：

```text
Windows EXE
```

如果你希望直接通过浏览器使用正式 SE-Mentor：

```text
Online WebUI
```

如果你需要稳定展示 ALLOW / WARN / BLOCK / Repair / Rollback 等核心机制：

```text
Mechanism Demo
```

---

# 47. 相关文档

系统架构：

```text
docs/ARCHITECTURE.md
```

安全边界：

```text
docs/SECURITY_BOUNDARIES.md
```

架构决策：

```text
docs/ARCHITECTURE_DECISIONS.md
```

运行与故障恢复：

```text
docs/RUNBOOK.md
```

部署：

```text
deploy/README.md
```

需求与实现追踪：

```text
TRACEABILITY_MATRIX.md
```

任务实施记录：

```text
AGENT_LOG.md
```

项目反思：

```text
REFLECTION.md
```

最终验收：

```text
ACCEPTANCE_REPORT.md
```

---

# 48. 一句话理解 SE-Mentor

> **SE-Mentor 是一个以自研 Agent Harness 为核心，将项目理解、软件演化记忆、影响分析、安全治理、用户授权、受控代码执行、验证反馈和恢复机制组合成完整闭环的 Coding Agent。**

源码本地运行、Windows EXE 和 Online WebUI 是正式产品的不同使用入口。

Mechanism Demo 则是独立的确定性机制演示环境。

SE-Mentor 真正的核心不是让 LLM 获得更多权限，而是：

```text
Evidence
+
Knowledge
+
Governance
+
ExecutionPolicy
+
Controlled Agent
+
Transaction
+
Validation
+
Recovery
```

让 AI 修改代码这件事真正进入可治理的软件工程流程。
