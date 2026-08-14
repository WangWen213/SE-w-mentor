# SE-Mentor Runbook

> **运行、故障定位、恢复与运维手册**  
> 对应交付任务：T112

本手册用于指导 SE-Mentor 的日常运行、故障定位和恢复。

适用范围包括：

- 源码本地运行；
- Windows EXE 本地运行；
- CLI 管理；
- 正式 Online WebUI；
- Mechanism Demo；
- Project Bootstrap；
- Proposal；
- Governance / Approval；
- Agent Execution；
- Validation；
- SSE；
- Cancel；
- Rollback；
- Crash Recovery；
- Credential；
- SQLite / Migration；
- 性能日志；
- 服务重启。

---

# 1. Runbook 原则

处理 SE-Mentor 故障时，优先保护以下内容：

```text
用户代码
    ↓
Transaction 一致性
    ↓
用户未提交修改
    ↓
Project / Task 持久化状态
    ↓
工程知识
    ↓
WebUI 当前显示状态
```

因此遇到问题时，不应首先采用：

```text
刷新页面
删除数据库
git reset --hard
删除运行目录
强制杀全部 Python 进程
```

这些操作可能让界面暂时恢复，但会掩盖真正的状态问题，甚至破坏用户代码。

推荐遵循：

```text
确认症状
    ↓
确认 Backend 是否存活
    ↓
确认真实 Backend State
    ↓
确认 Project / Task 状态
    ↓
确认 Transaction / Lock / Recovery
    ↓
确认 Frontend 是否只是展示异常
    ↓
执行最小恢复操作
```

---

# 2. 产品运行形态

SE-Mentor 当前存在以下运行方式：

| 运行方式 | 主要用途 | Harness 位置 |
|---|---|---|
| 源码本地运行 | 开发、调试 | 用户电脑 |
| CLI | 管理、凭据操作 | 用户电脑 |
| Windows EXE | 正式本地使用 | 用户电脑 |
| Online WebUI | 正式在线产品 | 服务器 |
| Mechanism Demo | 课程/机制演示 | 独立 Demo 环境 |

其中：

```text
Online WebUI
≠
Mechanism Demo
```

Online WebUI 是正式产品入口。

Mechanism Demo 是使用 Mock / Stub LLM 的独立确定性演示环境。

---

# 3. 本地源码运行

## 3.1 环境位置

开发仓库示例：

```text
C:\Users\ww\Desktop\SE-w-mentor
```

以下命令以该目录为例。

如果仓库位于其他位置，请替换为实际路径。

---

## 3.2 启动 Backend

### PowerShell

进入仓库根目录：

```powershell
cd C:\Users\ww\Desktop\SE-w-mentor
```

设置 Python 模块路径：

```powershell
$env:PYTHONPATH=(Resolve-Path backend\src).Path
```

启动 FastAPI：

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn se_mentor.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

也可以进入 Backend：

```powershell
cd C:\Users\ww\Desktop\SE-w-mentor\backend

.\.venv\Scripts\python.exe -m uvicorn se_mentor.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

---

## 3.3 CMD 启动方式

如果使用 CMD：

```cmd
cd /d C:\Users\ww\Desktop\SE-w-mentor
set PYTHONPATH=%CD%\backend\src
backend\.venv\Scripts\python.exe -m uvicorn se_mentor.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

注意：

PowerShell 使用：

```powershell
$env:PYTHONPATH=...
```

CMD 使用：

```cmd
set PYTHONPATH=...
```

不要混用。

---

## 3.4 正确的 ASGI 入口

当前 Backend 使用：

```text
se_mentor.main:create_app
```

并需要：

```text
--factory
```

不要使用：

```text
se_mentor.main:app
```

如果出现：

```text
ERROR: Error loading ASGI app.
Attribute "app" not found in module "se_mentor.main".
```

通常说明使用了错误入口。

正确命令：

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn se_mentor.main:create_app --factory --reload
```

---

# 4. 启动 Frontend

新开一个终端：

```powershell
cd C:\Users\ww\Desktop\SE-w-mentor\frontend
```

运行：

```powershell
npm run dev -- --host 127.0.0.1 --port 5173
```

浏览器访问：

```text
http://127.0.0.1:5173
```

正常情况下：

```text
Browser :5173
    ↓
Vite
    ↓
REST / SSE
    ↓
FastAPI :8000
```

---

# 5. Backend 健康检查

Backend 启动后优先检查：

```text
http://127.0.0.1:8000/health
```

PowerShell：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health
```

如果返回成功状态，则说明 FastAPI 基础服务存活。

注意：

```text
Backend 存活
```

不代表：

```text
Project READY
```

也不代表：

```text
Agent Harness 当前任务正常
```

Health Check 只用于确认服务进程本身。

---

# 6. Frontend 可用性检查

检查：

```text
http://127.0.0.1:5173
```

PowerShell：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173/
```

如果 Backend 正常、Frontend 不可访问：

优先检查：

- `npm run dev` 是否仍在运行；
- 5173 是否被占用；
- Vite 是否编译失败；
- `node_modules` 是否完整；
- `vite.config.ts` 是否配置正确。

---

# 7. 端口占用

默认开发端口：

```text
Backend   8000
Frontend  5173
```

Windows 检查：

```powershell
netstat -ano | Select-String ":8000"
```

```powershell
netstat -ano | Select-String ":5173"
```

然后根据 PID 查看进程：

```powershell
Get-Process -Id <PID>
```

不要看到端口占用就立即：

```powershell
taskkill /F
```

先确认该 PID 是否属于：

- 当前 Mentor；
- 旧 Mentor；
- 其他开发服务；
- 系统程序。

---

# 8. 旧 Backend 占用端口

如果出现：

```text
Frontend 看起来是新版本
但 API 行为仍然像旧代码
```

很可能 8000 端口仍由旧 Backend 占用。

处理顺序：

```text
1. 查询 :8000 PID
2. 确认进程路径
3. 停止确认无用的旧 Mentor Backend
4. 用当前 backend\.venv 重新启动
5. 再检查 /health
```

不要仅仅重启 Vite。

---

# 9. ModuleNotFoundError

如果 Backend 出现：

```text
ModuleNotFoundError: No module named 'se_mentor'
```

检查：

```powershell
$env:PYTHONPATH
```

重新设置：

```powershell
$env:PYTHONPATH=(Resolve-Path backend\src).Path
```

或者从 `backend` 目录按项目实际环境启动。

---

# 10. Windows EXE 运行

Windows 正式本地版本采用：

```text
PyInstaller onedir
```

典型结构：

```text
SE-Mentor/
├── sementor.exe
├── _internal/
├── web/
├── migrations/
├── schemas/
└── runtime dependencies/
```

用户应运行：

```text
sementor.exe
```

不要只复制 `sementor.exe` 到另一个目录单独运行。

`onedir` 中的其他资源属于运行时依赖。

---

# 11. EXE 正常启动流程

正常流程：

```text
sementor.exe
    ↓
检查 Runtime
    ↓
初始化本地数据目录
    ↓
运行数据库 Migration
    ↓
启动 FastAPI
    ↓
加载 React Static Assets
    ↓
监听 127.0.0.1
    ↓
打开 Browser WebUI
```

正式本地版本不应默认监听：

```text
0.0.0.0
```

推荐：

```text
127.0.0.1
```

避免无意暴露到局域网。

---

# 12. EXE 无法启动

检查以下内容：

1. 分发目录是否完整；
2. 是否只复制了 `.exe`；
3. Windows x64 环境是否兼容；
4. Runtime Data 是否有写权限；
5. 数据库 Migration 是否失败；
6. 本地端口是否被占用；
7. Windows Credential Manager 是否可访问；
8. 日志中是否有启动错误。

不要直接删除用户数据目录重新运行。

如果怀疑数据库问题，应先备份。

---

# 13. CLI

当前正式 CLI 主要用于管理和凭据生命周期。

主要能力：

```text
set
status
update
clear
```

实际命令名称以当前 `backend/src/se_mentor/cli/` 实现为准。

CLI 不应绕过 Backend Service 的安全逻辑。

尤其不应出现：

```text
CLI 直接写数据库 Secret
```

或：

```text
CLI 直接绕过 PolicyEnforcer 修改 Repository
```

---

# 14. Credential 状态

本地正式模式的凭据链路：

```text
CredentialService
    ↓
CredentialStore
    ↓
Keyring
    ↓
Windows Credential Manager
```

数据库仅保存：

- Provider profile；
- 是否配置；
- 必要非 Secret metadata。

不保存真实 Key 明文。

---

# 15. 配置 Provider Key

WebUI 中：

```text
设置
→ 模型与凭据
→ 配置
```

CLI 中使用实际实现的 `set` 命令。

输入 Secret 时必须：

- 隐藏输入；
- 不回显；
- 不打印到 stdout；
- 不写普通日志。

配置成功后 UI 只应显示：

```text
已配置
```

不能重新显示完整 Key。

---

# 16. 更新 Provider Key

正常过程：

```text
输入新 Key
    ↓
CredentialService
    ↓
Secret Store Update
    ↓
更新成功
    ↓
旧 Key 不再使用
```

不要：

```text
先删除旧 Key
↓
再尝试保存新 Key
```

否则新 Key 保存失败时会导致凭据完全丢失。

---

# 17. 清除 Provider Key

Clear 后：

```text
Credential Store
→ 删除 Secret
```

Provider 应立即变为不可用状态。

后续真实模型调用应明确提示：

```text
Credential Missing
```

而不是静默 fallback 到其他真实凭据。

---

# 18. Keyring 不可用

如果 Windows Credential Manager / Keyring 不可用：

允许降级为：

```text
Session-only Secret
```

即：

```text
当前进程内使用
```

但不能：

```text
明文写 SQLite
```

不能：

```text
写 .env 作为正式 fallback
```

也不能：

```text
写浏览器 localStorage
```

重启后 Session Secret 可以丢失。

这属于安全降级，而不是持久化失败。

---

# 19. 怀疑 API Key 泄漏

立即执行：

```text
1. 在 Provider 侧撤销 Key
2. 创建新 Key
3. 更新 Mentor 凭据
4. 检查 Git
5. 检查日志
6. 检查 Evidence
7. 检查 Build Artifact
8. 检查浏览器存储
```

不要等确认“真的被人用了”之后再撤销。

---

# 20. 打开本地项目

Local 模式下：

```text
打开本地项目
```

应显示真实 Dialog。

用户输入或选择本地 Git Repository。

例如：

```text
D:\Projects\MyApp
```

Backend 应负责：

```text
解析真实路径
    ↓
确认存在
    ↓
确认可访问
    ↓
确认 Git Repository
    ↓
检查边界
    ↓
读取 Git Revision
    ↓
注册 Project
```

Frontend 不应自行把输入路径标记为“已打开”。

---

# 21. 项目打开失败

优先检查：

### 路径不存在

```text
PROJECT_PATH_NOT_FOUND
```

### 不是 Git Repository

检查：

```powershell
git -C <project-path> rev-parse --show-toplevel
```

### 无权限

确认当前 Windows 用户是否可读。

### Symlink / Junction 越界

Mentor 可以拒绝可能逃离项目 Root 的路径。

### Backend 不可用

确认：

```text
/health
```

---

# 22. Project Bootstrap

项目注册后进入：

```text
REGISTERED
    ↓
BOOTSTRAPPING
    ↓
READY
```

失败：

```text
BOOTSTRAP_FAILED
```

Bootstrap 可能进行：

- Repository Inventory；
- Code Index；
- Symbol Extraction；
- Dependency Relations；
- Git Baseline；
- Project Understanding；
- Engineering Knowledge 初始化。

---

# 23. 为什么打开项目后仍显示“正在分析”

这是正常的异步 Bootstrap 状态。

项目打开与完整项目分析已经解耦：

```text
Register Project
    ↓
立即返回
    ↓
后台 Bootstrap
```

因此用户可能先进入工作台，再看到：

```text
正在分析项目
```

只有：

```text
READY
```

之后才能执行依赖完整项目理解的操作。

---

# 24. 刷新后短暂显示“无项目”

正确 UI 必须区分：

```text
LOADING
```

和：

```text
NO_PROJECT
```

如果刷新时 Backend 状态还没有恢复完成，不应立即显示：

```text
无项目
```

然后数秒后重新出现旧项目。

如果再次出现这种问题：

优先检查 Frontend hydration / restore 逻辑，而不是 Project 数据本身。

---

# 25. Bootstrap 长时间不结束

检查：

1. Backend 日志；
2. Git 操作；
3. Repository Inventory；
4. Code Index；
5. Symbol Relation；
6. Project Understanding；
7. SQLite 写入；
8. 是否扫描巨大目录；
9. 是否误扫 `.git` / `node_modules` / `.venv` / `dist` / `build`。

正常实现应排除不必要目录。

---

# 26. Proposal 创建失败

Proposal 创建常见错误应区分。

例如：

```text
PROJECT_NOT_READY
PROVIDER_UNAVAILABLE
PROVIDER_REQUEST_BUILD_FAILED
EMPTY
INVALID
SCHEMA_INVALID
PERSIST_FAILED
```

不要把所有错误都展示成：

```text
生成失败，请重试
```

错误应该告诉用户下一步怎么做。

---

# 27. Provider Request Build Failed

如果出现：

```text
PROVIDER_REQUEST_BUILD_FAILED
```

说明错误发生在真正请求 Provider 之前。

检查：

- Credential 对象；
- Request Schema；
- Model 配置；
- Secret retrieval；
- Provider request builder。

这类错误通常：

```text
没有真正产生外部 API 调用
```

因此不要误判为 OpenAI 网络失败。

---

# 28. Provider Auth Error

典型：

```text
401
```

检查：

- Key 是否有效；
- 是否被撤销；
- Provider profile 是否正确；
- CredentialService 是否读取到当前 Key。

不要把真实 Key 打印到日志中进行排查。

---

# 29. Provider Rate Limit

典型：

```text
429
```

处理：

- 显示明确错误；
- 允许用户稍后重试；
- 避免无限自动 retry；
- 保留当前 Task / Proposal 状态。

不要因为 Provider 429 就重新创建 Project。

---

# 30. Provider Timeout

Timeout 时：

```text
LLM Call
→ Timeout
→ 明确失败 / 可恢复状态
```

不要让 Task 永久停留：

```text
正在生成
```

Frontend 应能从 Backend 得到最终状态。

---

# 31. Proposal Context 性能

Proposal Context 当前应优先使用：

- Persisted Code Symbols；
- Project Understanding；
- Git tracked paths；
- Engineering Knowledge；
- 有界 Evidence。

而不是每次：

```text
Repository Full Walk
+
读取全部文件
```

如果 Proposal 明显变慢，优先查看：

```text
[perf] proposal-context ...
```

相关日志。

---

# 32. Proposal 确认

用户点击：

```text
确认并继续
```

正确后端流程为：

```text
Confirm Proposal
    ↓
confirm_and_analyze()
    ↓
Impact
    ↓
Governance
```

Frontend 不应：

```text
Confirm API
    ↓
再主动 POST Governance API
```

否则可能造成重复治理、重复写入和状态跳动。

---

# 33. Confirm 一直显示“确认中”

检查 Backend：

- confirm 请求是否结束；
- Impact 是否完成；
- Governance 是否完成；
- Provider 是否抛错；
- Task 是否已经进入后续状态。

如果 Backend 实际已经完成，而 Frontend 一直“确认中”：

这是 UI 状态同步问题。

如果 Backend 状态停在：

```text
GOVERNING
```

则继续检查 Governance。

---

# 34. Governance

治理输入包括：

- Proposal；
- ImpactReport；
- Evidence；
- Engineering Knowledge；
- Rules；
- Project Config；
- Approval Context。

输出：

```text
ALLOW
WARN / REQUIRE_APPROVAL
BLOCK
```

---

# 35. Governance 页面加载慢

先判断：

```text
后端查询慢
```

还是：

```text
前端重复触发治理
```

Governance 页面应该：

```text
读取已有治理记录
```

而不是每次打开页面重新运行 Governance。

历史治理应持久化。

---

# 36. Governance 页面数据结构

当前产品要求：

```text
每个 Task 的治理记录都保留
```

而不是：

```text
只保留一个全局最新 Governance
```

UI 使用：

```text
单列长条历史记录
```

避免两列卡片。

---

# 37. Governance 页面反复跳动

如果出现：

```text
正在恢复
↔
治理详情
```

或：

```text
治理页面
↔
其他页面
```

检查：

- Frontend 多个 `useEffect` 是否互相写 `activeView`；
- Recovery 状态是否被误判；
- Project restore 是否重复执行；
- SSE Event 是否重复触发 navigation。

页面导航不能作为 Backend 状态机。

---

# 38. WARN / REQUIRE_APPROVAL

WARN 正常流程：

```text
Governance
    ↓
Approval Required
    ↓
等待用户
```

此时 Agent 不应执行 Side Effect。

用户点击批准后：

```text
Approval API
    ↓
Approved
```

但仍然不能立刻假设已经获得 WRITE Lock。

---

# 39. Approval 与 Execute

当前产品要求将：

```text
批准
```

和：

```text
执行
```

明确分开。

流程：

```text
批准
    ↓
Approval persisted
    ↓
UI 显示已批准
    ↓
执行
    ↓
Backend Execute API
```

不要：

```text
点击批准
→ Frontend 自己把任务改成执行中
```

---

# 40. BLOCK

如果治理结果：

```text
BLOCK
```

则：

```text
禁止执行
```

普通用户确认不能覆盖。

尤其：

```text
DENY_HARD
```

永远不能被普通 Approval override。

---

# 41. ExecutionPolicy

执行前应存在有效 ExecutionPolicy。

检查内容可能包括：

```text
readable_paths
writable_paths
protected_paths
allowed_commands
denied_commands
network_allowed
expires_at
task_id
project_id
```

如果 Policy 已过期：

```text
禁止继续使用
```

需要重新治理或重新批准。

---

# 42. Proposal 改变后旧 Policy

如果用户扩大修改范围：

```text
旧 Proposal
→ 已治理
→ 已 Approval
→ 已生成 Policy
```

随后用户新增：

```text
再顺便修改另外一个模块
```

此时旧 Policy 必须失效。

需要：

```text
New Proposal
→ Re-impact
→ Re-governance
→ 新 Approval（如需要）
→ 新 Policy
```

不能直接把新范围附加到旧授权上。

---

# 43. WRITE Lock

Side Effect 前必须获取 Project WRITE Lock。

如果任务显示：

```text
等待执行
```

但长时间不开始，检查：

- 是否有另一个 Task 持有 WRITE；
- 是否存在 Recovery；
- 是否有未结束 Transaction；
- 当前 Task 是否真的获得 Approval；
- Policy 是否仍有效。

---

# 44. WRITE Lock 不能由 Frontend 释放

Frontend 不能因为：

```text
用户切换页面
关闭 Dialog
撤销按钮状态
```

就释放 WRITE Lock。

WRITE ownership 只能由 Backend Harness 在 Safe Point 释放。

---

# 45. Tool 执行

所有 Tool Action 应经过：

```text
AgentAction
    ↓
Dispatcher
    ↓
PolicyEnforcer
    ↓
Transaction
    ↓
Tool
```

如果 Tool 被拒绝：

检查：

- 路径是否超范围；
- command 是否 deny；
- policy 是否过期；
- network 是否禁用；
- Task / Project 是否匹配。

不要修改 PolicyEnforcer 去“临时放行”。

---

# 46. Shell 长时间不结束

外部命令必须存在 timeout。

检查：

- 子进程 PID；
- timeout；
- cancel token；
- stdout/stderr 是否阻塞；
- 命令本身是否进入交互模式。

Agent Shell 不应该等待：

```text
请输入密码：
```

这种无法自动处理的交互。

---

# 47. Execution 进度刷新后才出现

正常设计：

```text
Backend State
+
SSE Event
```

Frontend 不应该依赖刷新才能看到 Agent Progress。

如果刷新后才出现：

检查：

- EventSource 是否连接；
- Nginx/Vite proxy；
- SSE endpoint；
- Frontend event handler；
- Event 是否带正确 projectId / taskId。

---

# 48. SSE 断开

SSE 不是状态数据库。

断开后：

```text
重新建立 SSE
    +
REST 重新读取 Task 当前状态
```

不能：

```text
SSE 断开
→ 前端认为 Task 不存在
```

---

# 49. Validation

代码修改后必须进入 Validation。

可能运行：

- pytest；
- Vitest；
- Build；
- Type Check；
- Static Analysis；
- Git Diff；
- Project-specific Validator。

Validation 返回确定性结果。

---

# 50. INCONCLUSIVE

如果必要 Validator 不存在：

不能：

```text
假装通过
```

应进入：

```text
INCONCLUSIVE
```

或者对应的不可完成状态。

用户需要知道：

> 哪项验证缺失，以及为什么无法确认任务完成。

---

# 51. 自动修正

Validation 失败后：

```text
Failure
    ↓
Classification
    ↓
Feedback
    ↓
Repair
    ↓
Validation
```

自动修正不能无限循环。

---

# 52. Stagnation

出现以下情况时应判定可能停滞：

- 连续相同错误；
- 连续相同 AgentAction；
- Diff 没有变化；
- Validation 没有改善；
- 多轮修复结果完全一致。

处理：

```text
STAGNATION
    ↓
REPLAN
```

必要时：

```text
STOP
```

而不是继续消耗模型调用。

---

# 53. Task 完成条件

以下情况不能判定 Task 完成：

```text
只改了代码
但没有验证
```

```text
LLM 回复“已经完成”
```

```text
测试失败但 Agent 停止
```

```text
必要 Validator 缺失
```

```text
治理要求未满足
```

只有 CompletionGate 满足条件，Task 才能进入最终完成状态。

---

# 54. Cancel

用户请求停止时：

```text
CANCEL_REQUESTED
```

正确行为：

```text
停止新的 LLM Call
停止新的 AgentAction
停止可安全中止的 Shell
等待当前原子写入完成
到达 Safe Point
```

不要立刻删除 Transaction。

---

# 55. Cancel 后的选择

达到 Safe Point 后：

```text
CANCELLED
```

用户可以选择：

### KEEP

保留已经产生的本次修改。

### ROLLBACK

恢复本次 Task 引入的修改。

---

# 56. Rollback

Rollback 根据 Transaction Manifest 进行。

典型规则：

```text
CREATE
→ 删除本次创建文件
```

```text
MODIFY
→ 恢复任务前 Backup
```

```text
DELETE
→ 恢复原始文件
```

---

# 57. 为什么禁止直接 git reset --hard

因为用户在任务开始前可能已经有：

```text
未提交修改
```

例如：

```text
src/config.py
```

如果直接：

```bash
git reset --hard
```

会把用户自己的工作一起删除。

SE-Mentor 必须只恢复：

```text
本 Task 产生的副作用
```

---

# 58. Rollback Hash Conflict

Rollback 前检查当前文件 Hash。

如果：

```text
Task 修改文件
    ↓
用户手工再次修改
    ↓
执行 Rollback
```

当前文件已经不同于 Task 最后写入状态。

此时不得覆盖。

进入：

```text
ROLLBACK_CONFLICT
```

要求人工处理。

---

# 59. Crash Recovery

如果程序异常退出时存在：

```text
PREPARED
```

或：

```text
APPLYING
```

Transaction，则下一次启动应进入：

```text
RECOVERY_REQUIRED
```

---

# 60. Recovery 时禁止新 WRITE

Recovery 未完成前：

```text
新的 READ
```

可以根据策略允许。

但：

```text
新的 WRITE Task
```

必须阻止。

原因是当前 Workspace 状态可能处于：

```text
部分应用
```

状态。

---

# 61. Recovery 页面

Recovery 页面应以 Backend Recovery State 为准。

不要在：

```text
正在恢复
↔
任务详情
```

之间反复跳动。

Recovery 真正完成后才恢复普通 Task 页面。

---

# 62. SQLite

SE-Mentor 使用 SQLite 保存本地运行状态。

可能包括：

- Project；
- Task；
- Proposal；
- Governance；
- Approval；
- ExecutionPolicy；
- Transaction metadata；
- Validation；
- EngineeringKnowledge；
- CodeIndex；
- Audit。

真实 API Key 不应作为普通明文存储在 SQLite。

---

# 63. 数据库位置

实际数据库文件位置以当前 Runtime 配置为准。

不要在文档中假定所有模式都固定为：

```text
backend/.sementor/...
```

如果需要确认实际路径：

查看：

- Runtime Config；
- Database Config；
- Backend startup log。

---

# 64. Migration

数据库 Schema 由 Alembic 管理。

任何 Schema 修改都应：

```text
新增 Migration
```

而不是要求用户手工运行 SQL 改数据库。

Migration 必须维持单 Head。

---

# 65. Migration 失败

不要直接删除数据库。

处理：

```text
1. 备份数据库
2. 查看当前 Alembic revision
3. 查看 head
4. 检查是否存在多 head
5. 检查 Migration 文件
6. 再决定 upgrade / compatibility repair
```

---

# 66. Runtime SQLite Compatibility Repair

对于历史开发数据库，某些旧约束可能与新 Migration 不一致。

Runtime 可以进行有限兼容修复。

但：

```text
Compatibility Repair
```

不是：

```text
跳过 Migration Governance
```

新 Schema 仍应通过 Migration 正式定义。

---

# 67. 日志

日志主要用于：

- Backend error；
- Provider；
- Proposal；
- Governance；
- Tool；
- Validation；
- Recovery；
- Performance。

日志中禁止出现：

- API Key；
- Authorization Header；
- 完整 Secret；
- 不必要用户敏感内容。

---

# 68. Performance 日志

性能分析可以使用：

```text
[perf]
```

标记。

例如：

```text
[perf] proposal-context ...
[perf] proposal-pipeline ...
[perf] governance ...
```

不要假设日志文件一定在：

```text
backend\.sementor\perf-runtime.log
```

日志实际位置应由 Runtime 配置确认。

如果要收集性能记录：

先找到实际运行时日志文件，再过滤：

```powershell
Get-Content <actual-log-path> |
    Select-String "\[perf\]" |
    Set-Content perf-result.txt
```

---

# 69. Proposal 性能排查

如果：

```text
用户发送需求
→ 很久才出现 Proposal
```

优先检查：

1. Context Builder；
2. 是否发生全 Repository Walk；
3. 是否读取大量源码；
4. Provider latency；
5. Project Understanding 是否 READY；
6. Code Index 是否存在；
7. `git ls-files` 是否正常；
8. 是否误进行 UI 文本全扫描。

---

# 70. Confirm → Governance 性能

如果：

```text
确认 Proposal
→ 很久才出现 Governance
```

检查：

- ImpactReport；
- Governance Rules；
- EngineeringKnowledge retrieval；
- Provider call；
- 是否重复运行 Governance；
- 是否重复加载历史治理。

确认后应由 Backend 一次完成：

```text
confirm_and_analyze()
```

而不是 Frontend 二次触发。

---

# 71. Governance 历史越来越慢

治理页面长期使用后会积累大量记录。

UI 应：

- 按 Project 查询；
- 支持分页或有界读取；
- 不为每条历史记录重新执行 Governance；
- 不重新计算旧 Impact；
- 不把所有详情一次性展开。

历史记录是持久化结果，不是实时重新分析。

---

# 72. Frontend 假控件

正式 WebUI 中：

```text
看起来能点击
```

就应该：

```text
真正有 Backend Action
```

如果功能尚未实现：

应：

```text
disabled
```

或明确显示：

```text
暂不可用
```

不能使用：

```text
按钮点击
→ 前端本地 setState
→ 假装操作成功
```

---

# 73. Project Scope

所有以下数据必须绑定 Project：

- Task；
- Memory；
- Governance；
- Evaluation；
- Approval；
- Recovery；
- Lock；
- SSE Event。

切换 Project 时不能：

```text
把旧项目 Task 显示成新项目 Task
```

也不能：

```text
把后台旧项目执行中的 Task ownership 转移
```

---

# 74. Online WebUI

正式 Online WebUI 不是 Demo。

正常拓扑：

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
Per-user Workspace
```

正式 Online 模式最终需要支持：

- 真实用户；
- 真实 Project；
- 真实 Task；
- 真实 Governance；
- 真实 Provider；
- 真实 Validation。

---

# 75. Online WebUI 安全门

在允许真实公网用户输入 Provider Key 前，必须确认：

- Authentication；
- Session Isolation；
- Project Ownership；
- Workspace Isolation；
- Credential Isolation；
- Execution Isolation；
- Persistence Isolation。

如果这些条件尚未验收：

不要启用：

```text
Public Real-provider Mode
```

---

# 76. Online 用户不能打开本地路径

Online WebUI 运行在服务器。

因此用户不能输入：

```text
C:\Users\...
D:\Projects\...
```

然后期待服务器直接读取。

在线 Project 必须通过当前实现支持的项目导入 / Clone / Workspace 机制进入服务器工作区。

具体入口以当前 Online API 实现为准。

---

# 77. Online Session 混淆

如果用户 A 看到用户 B 的：

- Task；
- Project；
- Governance；
- Credential Status；

这是 P0 安全问题。

立即停止正式公网使用。

不要仅用 Frontend 过滤解决。

Backend Query 必须验证 Ownership。

---

# 78. Online Credential 问题

Online 环境不能使用：

```text
全服务器共享一个 Credential
```

作为正式多用户模型。

需要：

```text
Authenticated User
    ↓
Per-user Credential
```

用户 Secret 不得通过普通 API Response 返回。

---

# 79. Mechanism Demo

Mechanism Demo 独立于正式 Online WebUI。

目标：

```text
稳定复现核心 Harness 机制
```

默认：

```text
Mock / Stub LLM
```

而不是 Real Provider。

---

# 80. Demo 正常场景

至少应支持确定性复现：

```text
ALLOW
WARN / APPROVAL
BLOCK
AUTO-REPAIR
STAGNATION
ROLLBACK
KNOWLEDGE FRESHNESS
```

---

# 81. Demo 不应该依赖真实 Provider

课堂展示时：

```text
Mock Scenario
```

必须在无外部网络、无真实 API Key 情况下运行。

否则：

- Provider 网络波动；
- 模型随机性；
- 额度；
- 429；

都会影响演示稳定性。

---

# 82. Demo 不是静态 HTML

Mechanism Demo 仍然应该真正经过 Harness 的关键机制。

不能只是：

```text
Static HTML
+
setTimeout
+
固定 “ALLOW”
```

来冒充治理系统。

Mock 的是：

```text
LLM
```

不是：

```text
整个 Harness
```

---

# 83. 服务重启顺序

本地源码推荐：

```text
1. 停止 Frontend
2. 停止 Backend
3. 确认 5173 / 8000 已释放
4. 启动 Backend
5. 确认 /health
6. 启动 Frontend
7. 打开 WebUI
8. 确认 Project restore
9. 检查 Recovery
10. 再继续 Task
```

---

# 84. 不要在有 Transaction 时随意重启

如果当前有：

```text
EXECUTING
APPLYING
```

Task：

尽量先：

```text
Cancel
→ Safe Point
```

再停服务。

如果已经崩溃：

下一次启动按：

```text
Recovery
```

流程处理。

---

# 85. 浏览器刷新

浏览器刷新不应：

- 删除 Project；
- 删除 Task；
- 释放 WRITE Lock；
- 取消 Agent；
- 丢失 Approval；
- 改变 Governance；
- 清除 Transaction。

如果刷新导致上述结果，属于 Backend / Frontend 状态权威问题。

---

# 86. 清浏览器缓存不是标准恢复方式

如果 UI 出现问题：

不要把：

```text
清 localStorage
```

作为常规修复。

Frontend 不应该依赖 localStorage 保存业务权威状态。

Local storage 只能保存非关键 UI 偏好或安全允许的信息。

---

# 87. 常见症状速查

| 症状 | 优先检查 |
|---|---|
| 页面打不开 | Frontend 5173 |
| API 全失败 | Backend 8000 / health |
| `app not found` | `create_app --factory` |
| 找不到 `se_mentor` | PYTHONPATH |
| 项目短暂变无项目 | restore/loading 状态 |
| Project 一直分析 | Bootstrap |
| Proposal 很慢 | Context / Provider |
| Proposal 失败但无 API 消耗 | Request Build |
| Confirm 一直转圈 | Impact / Governance |
| Governance 重复生成 | Frontend 二次触发 |
| Governance 页面很慢 | 历史查询 / 重算 |
| 批准后不执行 | Execute / WRITE Lock |
| 执行进度刷新才出现 | SSE |
| Task 卡执行中 | Tool / Lock / Provider |
| Test 失败后无限循环 | Stagnation |
| Stop 后不能新任务 | Transaction / Safe Point |
| 重启后禁止写 | RECOVERY_REQUIRED |
| Rollback 不执行 | Hash Conflict |
| Key 重启后丢失 | Keyring fallback / Credential Store |
| Online 用户数据串了 | Ownership / Session Isolation |

---

# 88. 禁止的“快速修复”

以下操作不能作为默认故障处理方式：

```bash
git reset --hard
```

```text
删除所有 SQLite 数据
```

```text
删除 Transaction Manifest
```

```text
直接修改 Task 状态为 COMPLETED
```

```text
为了能执行而关闭 PolicyEnforcer
```

```text
为了让测试通过而删除失败测试
```

```text
把 API Key 临时写到源码
```

```text
把 Online 所有用户共用一个 Credential
```

这些操作可能让当前症状消失，但会破坏 SE-Mentor 最核心的工程安全保证。

---

# 89. 推荐故障定位顺序

任何复杂问题都建议按照以下顺序：

```text
1. 服务是否存活？
2. Backend 当前真实状态是什么？
3. Project 是什么状态？
4. Task 是什么状态？
5. 是否存在 Approval？
6. 是否存在有效 Policy？
7. 是否拥有 WRITE Lock？
8. 是否存在 Transaction？
9. 是否存在 Recovery？
10. Validation 当前状态是什么？
11. SSE 是否只是展示中断？
12. Frontend 是否显示了过期状态？
```

不要反过来从 UI 猜 Backend 状态。

---

# 90. 发布前运行检查

正式发布前至少确认：

### Backend

- 可以启动；
- `/health` 正常；
- Migration 正常；
- 无 Secret 打印。

### Frontend

- 可以加载；
- 工作台可以进入；
- REST 正常；
- SSE 正常。

### Harness

- Proposal；
- Governance；
- Policy；
- Execution；
- Validation；
- Recovery。

### Credential

- Secret 不回显；
- Clear 生效；
- 构建产物无 Key。

### Distribution

- 不包含开发数据库；
- 不包含日志；
- 不包含 Backup；
- 不包含真实凭据。

---

# 91. Windows 发布检查

Windows Package 发布前：

```powershell
.\scripts\build_windows.ps1
```

然后：

```powershell
.\scripts\smoke_windows.ps1
```

最终还应在：

```text
干净 Windows 10/11 x64 环境
```

进行目标环境验证。

代码打包成功不等于目标环境已经验收。

---

# 92. Online 发布检查

正式 Online Product 上线前：

```text
Container
✓
Health
✓
Frontend
✓
REST
✓
SSE
✓
Database
✓
Workspace Isolation
✓
Authentication
✓
Session Isolation
✓
Credential Isolation
✓
Execution Isolation
✓
HTTPS
✓
```

如果只是 Demo 部署：

不能将其宣称为：

```text
Production-safe Online Product
```

---

# 93. Mechanism Demo 发布检查

Demo 发布重点：

```text
无真实 Key
✓

Mock / Stub 可确定复现
✓

ALLOW
✓

WARN
✓

BLOCK
✓

Repair
✓

Stagnation
✓

Rollback
✓

Knowledge Freshness
✓
```

Demo 的目标是稳定证明机制，而不是模拟生产多用户系统。

---

# 94. 状态权威原则

最终必须始终记住：

```text
Frontend
不是
业务状态权威
```

真正的状态来源是：

```text
Backend Harness
+
Persistent Store
+
Transaction State
+
Git / Filesystem Evidence
```

SSE 负责通知。

REST 负责读取和命令。

WebUI 负责交互。

LLM 负责提出候选动作。

---

# 95. 恢复优先原则

发生任何异常时：

> **优先恢复系统对真实代码状态的认识，而不是优先恢复页面“看起来正常”。**

例如：

```text
页面显示错
但 Transaction 正确
```

应该修页面。

而不是修改 Transaction 去迎合页面。

这也是 SE-Mentor 与普通聊天式 Coding Agent 的重要区别。

---

# 96. 相关文档

系统架构：

```text
系统架构设计.md
```

安全边界与架构决策：

```text
docs/DECISIONS_P0.md
```

项目使用说明：

```text
README.md
```

部署：

```text
deploy/README.md
```

需求与实现追踪：

```text
docs/TRACEABILITY_MATRIX.md
```

最终验收：

```text
ACCEPTANCE_REPORT.md
```

---

# 97. Runbook 总结

SE-Mentor 出现问题时，最重要的不是“重启能不能好”，而是确认：

```text
Project
Task
Governance
Policy
Lock
Transaction
Validation
Recovery
```

这几个工程状态是否仍然一致。

正确的恢复目标不是：

> 让页面重新显示绿色。

而是：

> **确保用户代码没有被破坏、权限没有被绕过、事务状态可以解释、任务状态可以恢复，并且 WebUI 最终重新与 Backend Harness 的真实状态一致。**
