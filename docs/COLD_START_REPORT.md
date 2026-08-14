# Cold Start Validation Report

Status: FIRST PASS EXECUTED AND RECORDED — FINAL PRE-RELEASE RERUN NOT YET EXECUTED

Task: T114

## 1. Purpose

Cold Start 验证用于判断：一个不了解历史对话的新 Agent，是否能仅凭冻结的 SPEC、Plan 和必要
仓库文档，正确理解任务边界、识别不确定性、在需要时暂停，并产生符合规约的结果。

它验证的是规约和计划的自解释性，不能由产品代码存在与否推断通过。

## 2. Method

每轮实验应满足：

- 使用 fresh agent，不提供历史对话；
- 输入仅包含指定版本的 SPEC、Plan 与明确列出的基础文档；
- 选择一个边界清晰、可观察结果的任务；
- 记录所有不确定性、暂停点与错误假设；
- 将发现落为 SPEC / Plan / process 文档修订；
- 由第二个 fresh reader 复读修订后的基线；
- 保留开始 commit、输入文档、输出、结论与证据位置。

## 3. Required Evidence

最终 T114 证据至少包含：

| Evidence | Required content |
| --- | --- |
| Agent identity | fresh-agent 标识及其是否接触历史上下文 |
| Selected task | 执行/评审的 Task 与范围 |
| Input documents | SPEC、Plan 及允许读取的文件清单 |
| Start baseline | start commit 或等价不可变版本 |
| Decisions | agent 采取的关键决定与依据 |
| Ambiguities | 无法从输入唯一判断的内容 |
| Pause points | agent 主动停止并请求澄清的位置 |
| Incorrect assumptions | 错误推断、影响及发现方式 |
| Output | 产生的实现、审查或文档结果 |
| Spec revisions | 对 SPEC / Plan / process 的修订 diff |
| Second-read result | 第二位 fresh reader 的复读结论 |

## 4. Current Baseline And Recorded First Pass

仓库存在真实首轮记录：

- `evidence/logs/T114/cold-start-first-pass.md`；
- `evidence/reviews/T114-spec-review.md`；
- `evidence/reviews/T114-code-review.md`；
- `evidence/test-reports/T114.xml`；
- `evidence/tdd/T114.md`。

该记录日期为 2026-08-07，结论限定为 Foundation / M0 first cold-start pass。记录显示 fresh
read-only reviewer 发现的是文档漂移，并由当轮修订基础文档后完成复读结论。

因此当前准确状态不是“从未进行过任何 Cold Start”，也不是“T114 最终完成”，而是：

```text
FIRST COLD-START PASS: EXECUTED AND RECORDED
FINAL PRE-RELEASE COLD-START RERUN: NOT YET EXECUTED
```

首轮结论只覆盖其记录中的 Foundation / M0 范围，不能自动证明当前完整产品规约已通过最终冷启动。

## 5. Planned Final Execution

实现冻结后执行最终复跑：

1. 冻结 SPEC、Plan、Architecture、README、Runbook、Traceability 与部署/验收文档版本。
2. 选择没有接触项目历史对话的新 Agent。
3. 只提供冻结输入和明确 Task，不提供实现提示。
4. 记录 agent 的理解、假设、暂停点、决策、输出和耗时。
5. 对每个歧义建立文档修订，不能用口头解释代替。
6. 由第二个 fresh reader 仅凭修订后文档复读。
7. 保存 start commit、输入清单、两轮记录、diff 与最终结论。
8. 只有证据齐全且未留下阻断歧义时，才更新 T114 最终状态。

## 6. Release Impact

T114 不能仅凭当前代码或架构文档标记为最终 COMPLETE。首轮真实记录可以作为当前 evidence，
但最终 pre-release rerun 仍是 Release Gate 的客观证据项。

当前结论：

```text
T114 FIRST PASS: PASS (RECORDED EVIDENCE)
T114 FINAL RERUN: NOT YET EXECUTED
FINAL T114 ACCEPTANCE: TO BE VERIFIED
```
