# SE-Mentor Deterministic Mechanism Demo

Status: IMPLEMENTED AND REPEATABILITY VERIFIED ON FINAL MAIN BASELINE

## Purpose

Mechanism Demo 是独立于 Formal Online WebUI 的离线课程演示入口。它使用
`MockLLMProvider`，但真实调用 SE-Mentor 自研 Harness 的 Context、AgentAction、Governance、
Dispatcher、Feedback 与 Engineering Knowledge 机制。Mock 的是 LLM，不是整个 Harness。

它不访问网络、不需要真实 API Key、不访问 Credential Manager、不接触用户项目，也不代表
production ONLINE_SAFE 多用户验收。

## Demo vs Formal Online Product

| 维度 | Formal Online WebUI | Mechanism Demo |
| --- | --- | --- |
| 目标 | 真实用户的软件维护产品 | 确定性课程机制展示 |
| Provider | 用户自己的 OpenAI-compatible Provider | `MockLLMProvider` |
| Project | Session 隔离的用户 ZIP workspace | 临时隔离 fixture repository |
| Credential | Session-scoped，安全请求中使用 | 不需要、不接受真实 Key |
| Determinism | 受真实项目和 Provider 影响 | 固定 scenario 和 expected evidence |
| Output | Task、变更、Evaluation、Memory、ZIP/Patch | 控制台结果与 JSON evidence |

`CLOUD_DEMO` 是该演示形态的 runtime/profile 术语，不代表整个 Online WebUI 是 Demo。

## Exact Entrypoint

Windows PowerShell：

```powershell
$env:PYTHONPATH=(Resolve-Path backend\src).Path
.\backend\.venv\Scripts\python.exe scripts\demo_harness.py --all
```

输出 JSON evidence：

```powershell
.\backend\.venv\Scripts\python.exe scripts\demo_harness.py --all --output $env:TEMP\sementor-demo-evidence
```

单场景运行：

```powershell
.\backend\.venv\Scripts\python.exe scripts\demo_harness.py --scenario governance
.\backend\.venv\Scripts\python.exe scripts\demo_harness.py --scenario feedback
.\backend\.venv\Scripts\python.exe scripts\demo_harness.py --scenario memory
```

## Supported Scenarios

### Governance Guardrail

预置危险写动作经过真实 GovernanceDecisionService，预期结果为 `BLOCK`，且 dangerous Tool
没有执行。

### Feedback-driven Self Correction

第一次 Validation 为 `FAIL`；Feedback 被送入下一次 Mock Provider context；AgentAction 改变；
第二次 Validation 为 `PASS`。

### Engineering Memory / Context

Engineering Knowledge 被写入并检索命中，随后注入 Context 并实际影响 Agent 行为。

ALLOW、Approval、Stagnation、Rollback 与 Knowledge Freshness 属于完整 Harness 产品能力，但
当前 CLI 没有把它们分别实现为独立场景，因此本说明不把它们计入 Demo scenario 数量。

## Expected Result

```text
Governance Guardrail             PASS
Feedback-driven Self Correction  PASS
Engineering Memory / Context     PASS

Scenarios passed: 3 / 3
```

测试入口：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\demo\test_harness_demo.py
```

聚焦测试验证重复运行结果、JSON evidence、无 Secret evidence 和失败退出码。

## Presentation Order

1. 先说明 Formal Online WebUI 与 Mechanism Demo 的边界。
2. 展示 `MockLLMProvider` 与临时 repository，不使用真实 Key。
3. 运行 Governance Guardrail，证明硬阻断与无副作用。
4. 运行 Feedback-driven Self Correction，证明反馈闭环。
5. 运行 Engineering Memory / Context，证明知识影响后续行为。
6. 展示 JSON evidence，并明确它不是 public real-provider E2E 证据。
