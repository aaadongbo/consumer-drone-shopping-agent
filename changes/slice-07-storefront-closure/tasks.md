# Slice 7 Ordered Tasks — Fallback, Trace and Storefront Closure

> 状态：APPROVED IMPLEMENTATION BASELINE / NOT_STARTED
>
> Human 已接受本 Task 表，S07 Workflow Policy 已集成。下表使用正式 Task 状态；`NOT_STARTED` 仍不构成 Implementation、snapshot、commit、push 或外部服务授权。开始 S07-T01 前仍须取得单独的 Slice Implementation authorization。

## 1. Status and order

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | Storefront view-model and fallback adapter | DONE | Slice 6 completion + Slice 7 planning approval |
| T02 | Trace aggregation and redaction | DONE | T01 |
| T03 | Minimal storefront shell | DONE | T01 |
| T04 | API/storefront integration harness | DONE | T02, T03 |
| T05 | Journey and quality baseline | DONE | T04 |
| T06 | Slice completion evidence | NOT_STARTED | T05 |

Only the first dependency-ready row may be selected. These rows remain non-executable until a Slice Implementation authorization is supplied.

## 2. Provisional budget

| Key | Provisional hard limit | Stop reason |
|---|---:|---|
| `max_action_rounds` | `2` total | `ACTION_ROUND_LIMIT` |
| `max_tool_calls` | `2` per turn | `TOOL_CALL_LIMIT` |
| `turn_deadline_ms` | `8000` | `TURN_DEADLINE` |
| `max_retrieval_tokens` | `4000` per turn | `RETRIEVAL_TOKEN_BUDGET` |
| `max_model_tokens` | `1200` per turn | `MODEL_TOKEN_BUDGET` |

## 3. Task details

### S07-T01 — Storefront view-model and fallback adapter

- **Goal**：将现有 Answer/Fallback 转成客户端安全的内部 view-model。
- **Why**：客户端需要统一渲染答案、当前对象和可行动 fallback，不能自行解释领域 payload。
- **Scope**：客户端本地 view-model adapter 与必要的 `backend/api/` 映射检查；unit/contract tests；本任务表。
- **Contract**：`StorefrontTurnView` 只能由既有 response 与本地 UI 状态派生，不是 API DTO；`ConstraintPresentationState` 只展示服务端确认的有效约束/pending clarification；无法复用现有 schema 时停 Human。
- **Acceptance**：Answer/Fallback 一一映射；target scope、当前有效约束和澄清状态保持一致；内部诊断不外泄；transport rejection 不变成业务 fallback；跨 API 传输任何新增 view/state 字段先走版本化 Contract checkpoint。
- **Verification**：Unit + Contract + changed-file lint。
- **Dependencies**：Slice 6 completion + planning approval。
- **Out of Scope**：正式 UI、公共 Contract、状态持久化、真实服务。

### S07-T02 — Trace aggregation and redaction

- **Goal**：按 Turn 汇总已有 trace 并执行最小脱敏。
- **Why**：正式店面和质量回放需要可关联证据，但不能泄漏请求敏感数据。
- **Scope**：`backend/evaluation/` 或现有 trace 边界；unit/integration tests；本任务表。
- **Contract**：`TraceTurnRecord`、redaction result；不建立状态平台。
- **Acceptance**：correlation 完整；token/header/credential/payload/stack 不出现；redaction 失败 fail closed。
- **Verification**：Unit + Integration + security assertions。
- **Dependencies**：S07-T01。
- **Out of Scope**：托管 observability、长期存储、跨租户 tracing。

### S07-T03 — Minimal storefront shell

- **Goal**：提供最小发送、loading、Answer/Fallback、target display、约束 chips、澄清状态和用户动作界面。
- **Why**：需要验证正式组件中的核心成功与失败体验。
- **Scope**：`storefront/`、必要的本地静态资源和 component tests；本任务表。
- **Contract**：消费 S07-T01 内部 view-model；约束编辑/撤回/跳过必须走既有服务端路径；不新增 public wire 字段。
- **Acceptance**：显示当前对象、已确认约束及 pending clarification；不显示旧结果为当前事实；retry/clarify/switch/constraint action 仅由用户触发并以服务端确认结果更新；无自动循环；若现有 API 无法承载则停 Contract checkpoint。
- **Verification**：Static + component/unit；主要前端依赖需先升级 Human。
- **Dependencies**：S07-T01。
- **Out of Scope**：完整设计系统、登录、购物车、订单、客服外部跳转。

### S07-T04 — API/storefront integration harness

- **Goal**：将最小 storefront 与现有 Conversation API 连接并可回放。
- **Why**：证明 transport、业务 fallback 和渲染边界在真实请求链路中没有混淆。
- **Scope**：`backend/api/`、`backend/common/contracts.py`、`storefront/`、contract/integration/e2e tests；本任务表。
- **Contract**：复用既有 `TurnRequest`、`AnswerEnvelope`、`Fallback`；本 Task 已获 Human 批准，在 `AnswerEnvelope` 中新增可选、版本化的服务端权威 `conversation_state`。该字段仅包含 `active_constraints`、`pending_clarification`、`pending_switch` 与 `revision`，以支持客户端回放；禁止新增 endpoint、旁路 DTO、持久化或外部状态服务。
- **Acceptance**：合法请求形成完整链路；invalid input 下游零调用；Answer/Fallback/target/服务端确认的 conversation state/correlation 一致；新增字段向后兼容且不得让客户端成为状态权威；多轮新增、修改、撤回、跳过和最多两轮澄清可回放。
- **Verification**：Integration + E2E + zero-write。
- **Dependencies**：S07-T02、S07-T03。
- **Out of Scope**：真实 Shopify/模型、外部客服、浏览器云 CI、新 endpoint、状态持久化和外部状态服务。

#### Approved Contract record

- **Decision**：Human approved the minimal versioned `AnswerEnvelope.conversation_state` extension for S07-T04.
- **Boundary**：optional and server-authoritative only; fields are limited to `active_constraints`, `pending_clarification`, `pending_switch`, and `revision`.
- **Not approved**：new endpoint, new dependency, persistence, external service, Shopify write, or any other public Contract expansion.

### S07-T05 — Journey and quality baseline

- **Goal**：运行核心 Journey、失败矩阵和发布前质量检查，记录可复现 baseline。
- **Why**：正式店面闭环必须有证据说明成功、降级、安全和性能限制。
- **Scope**：`tests/e2e/`、`eval/`、必要的 `scripts/`；本任务表。
- **Contract**：`QualityRunRecord`、既有 trace/evaluation outputs。
- **Acceptance**：矩阵覆盖成功、fallback、transport、约束更新/撤回/跳过、最多两轮澄清、敏感信息和 zero-write；每条命令记录真实 exit code；性能指标只测量与记录，不自行调整 Spec 的 provisional gates 或 Acceptance。
- **Verification**：Full suite + E2E + static/security/dependency checks。
- **Dependencies**：S07-T04。
- **Out of Scope**：训练、fine-tuning、长期指标平台、自动发布、擅自修改 Spec 质量门槛或 Acceptance。

### S07-T06 — Slice completion evidence

- **Goal**：收敛 S7 Acceptance、Matrix、trace、安全和质量 baseline 的最终证据。
- **Why**：这是正式店面闭环的最后可审计边界。
- **Scope**：`tests/`、`eval/`、本任务表及允许的 completion evidence；不得修改核心 docs。
- **Contract**：S7 matrix、`QualityRunRecord`、zero-write evidence、completion summary。
- **Acceptance**：所有 S7 条件可回放；full suite/E2E/静态检查通过；无未批准依赖、外部服务或 Contract 变化。
- **Verification**：Full suite + E2E + scope/security + independent Slice review。
- **Dependencies**：S07-T05。
- **Out of Scope**：Slice 8+、发布到生产、push/merge policy 改造。

## 4. Workflow and escalation

- S07 Workflow Policy 已激活；不得在缺少 Slice Implementation authorization 时执行任何 S07 Task。
- Task 风险至少在 Contract、trace、安全和外部依赖处升级。
- 任何公共 Contract、主要依赖、真实外部服务、Shopify write、Product Behavior 或安全门禁变化都必须停止请求 Human。
- Full suite 只在 S07-T05/T06 运行；普通 Task 使用 targeted verification。

## 5. Completion checklist

- [x] S07 planning review 通过并建立 baseline。
- [x] S07 Workflow Policy 单独审查并激活。
- [ ] S07-T01～T06 按表顺序完成。
- [ ] 每个 Task 有真实 targeted verification 和 Execution Record。
- [ ] S7 Matrix、full suite、E2E、trace redaction、zero-write evidence 全部可回放。
- [ ] 最终独立 Slice Review 通过。
- [ ] Human 决定是否进入 feature branch delivery；当前规划不授权 push/merge。

## 6. Recommended next step

S07 planning baseline 和 Workflow Policy 已集成。下一步需要单独的 Slice Implementation authorization；在此之前不得执行 S07-T01。

## 7. Planning approval record

- **Decision**：Human accepted Slice 7 Goal、Scope、Acceptance、provisional budget 和 S07-T01～T06 task table.
- **Scope**：仅批准现有 `plan.md` 与 `tasks.md` 定义的正式店面闭环；不批准 public Contract、主要依赖、外部服务、Shopify write、Workflow Policy 或 Implementation。
- **Next authority boundary**：Human 需单独批准 planning baseline commit；随后才可单独配置 S07 Workflow Policy。

## 8. Task execution records

### S07-T01 — Storefront view-model and fallback adapter

- **Status**：DONE
- **Implementation base**：`c9eb842ddf442f9c4e48928dbe271e49f7bcc8bb`
- **Pre-existing diff**：clean worktree at start.
- **Started**：2026-09-03
- **Changed paths**：`storefront/__init__.py`, `storefront/view_model.py`, `tests/unit/test_s07_t01_storefront_view_model.py`, `tests/contract/test_s07_t01_storefront_adapter_contract.py`, `changes/slice-07-storefront-closure/tasks.md`
- **Verification**：
  - `python .agents/skills/drone-slice-workflow/scripts/check_scope.py S07-T01` → exit 0.
  - `uv run ruff check storefront tests/unit/test_s07_t01_storefront_view_model.py tests/contract/test_s07_t01_storefront_adapter_contract.py` → exit 0.
  - `uv run ruff format --check storefront tests/unit/test_s07_t01_storefront_view_model.py tests/contract/test_s07_t01_storefront_adapter_contract.py` → exit 0.
  - `uv run pytest tests/unit/test_s07_t01_storefront_view_model.py tests/contract/test_s07_t01_storefront_adapter_contract.py -q` → exit 0, `9 passed`.
  - `python .agents/skills/drone-slice-workflow/scripts/verify_task.py S07-T01` → exit 0, targeted profile passed.
- **Acceptance result**：PASS — internal StorefrontTurnView/ConstraintPresentationState are derived from existing public envelopes and local UI state only; Answer/Fallback map one-to-one; target, fallback scope, constraints, pending clarification and pending switch are preserved; internal diagnostic values fail closed before rendering; 422 transport rejection is represented as `TRANSPORT_REJECTION`, not a business fallback.
- **Out-of-scope check**：No public Contract, Architecture, core docs, dependency, formal UI shell, trace aggregation, E2E harness, external service, Shopify write, push, or integration change.

### S07-T02 — Trace aggregation and redaction

- **Status**：DONE
- **Implementation base**：`b3a4ae73f2e0a8a2b143bc01b1c2f432466bfb85`
- **Pre-existing diff**：clean worktree at start.
- **Started/completed**：2026-09-03
- **Changed paths**：`backend/evaluation/__init__.py`, `backend/evaluation/trace_turn.py`, `tests/unit/test_s07_t02_trace_turn.py`, `changes/slice-07-storefront-closure/tasks.md`
- **Verification**：
  - `python .agents/skills/drone-slice-workflow/scripts/check_scope.py S07-T02` → exit 0.
  - `uv run ruff check backend/evaluation tests/unit/test_s07_t02_trace_turn.py` → exit 0.
  - `uv run ruff format --check backend/evaluation tests/unit/test_s07_t02_trace_turn.py` → exit 0.
  - `uv run pytest -m 'unit or integration' tests/unit/test_s07_t02_trace_turn.py -q` → exit 0, `5 passed`.
  - `python .agents/skills/drone-slice-workflow/scripts/verify_task.py S07-T02` → exit 0, targeted profile passed.
- **Acceptance result**：PASS — existing summary-only `TraceEvent` values aggregate only when they share one correlation; trace projections contain no request payload, header, credential, token, or stack input. Sensitive correlation or scope attempts, mixed correlations and empty input fail closed before a record is emitted. The boundary is in-memory only and adds no observability service or persistence.
- **Out-of-scope check**：No public Contract, Architecture, dependency, external service, persistent sink, Shopify write, push, or integration change.

### S07-T03 — Minimal storefront shell

- **Status**：DONE
- **Implementation base**：`f5fcb9afe138b9bab64eaaa070515879b7f91d77`
- **Pre-existing diff**：clean worktree at start.
- **Started/completed**：2026-09-03
- **Changed paths**：`storefront/__init__.py`, `storefront/shell.py`, `tests/unit/test_s07_t03_storefront_shell.py`, `changes/slice-07-storefront-closure/tasks.md`
- **Verification**：
  - `python .agents/skills/drone-slice-workflow/scripts/check_scope.py S07-T03` → exit 0.
  - `uv run ruff check storefront tests/unit/test_s07_t03_storefront_shell.py` → exit 0.
  - `uv run ruff format --check storefront tests/unit/test_s07_t03_storefront_shell.py` → exit 0.
  - `uv run pytest -m unit tests/unit/test_s07_t03_storefront_shell.py -q` → exit 0, `3 passed`.
  - `python .agents/skills/drone-slice-workflow/scripts/verify_task.py S07-T03` → exit 0, targeted profile passed.
- **Acceptance result**：PASS — the local shell clears a previous result while loading, renders only the T01 server-confirmed view-model, preserves target/constraints/pending clarification for display, and queues only explicit user actions. Retry requires a server-marked retryable fallback; no client state or fact mutation occurs.
- **Out-of-scope check**：No public wire fields, frontend dependency, persistence, API integration, external service, Shopify write, push, or integration change.

### S07-T04 — API/storefront integration harness

- **Status**：DONE
- **Implementation base**：`81cf0b2e1f496e16f51454af1a636ac45a62ecea`
- **Pre-existing diff**：clean detached worktree at start.
- **Started/completed**：2026-09-03
- **Changed paths**：`backend/common/contracts.py`, `storefront/view_model.py`, `tests/contract/test_s07_t04_conversation_state_contract.py`, `tests/integration/test_s07_t04_storefront_api_harness.py`, `changes/slice-07-storefront-closure/tasks.md`
- **Verification**：
  - `uv run ruff check backend/common/contracts.py storefront/view_model.py tests/contract/test_s07_t04_conversation_state_contract.py tests/integration/test_s07_t04_storefront_api_harness.py` → exit 0.
  - `uv run ruff format --check backend/common/contracts.py storefront/view_model.py tests/contract/test_s07_t04_conversation_state_contract.py tests/integration/test_s07_t04_storefront_api_harness.py` → exit 0.
  - `uv run pytest -m 'integration or e2e' tests/contract/test_s07_t04_conversation_state_contract.py tests/integration/test_s07_t04_storefront_api_harness.py -q` → exit 0, `3 passed`.
  - `python .agents/skills/drone-slice-workflow/scripts/check_scope.py S07-T04` → exit 0.
  - `python .agents/skills/drone-slice-workflow/scripts/verify_task.py S07-T04` → exit 0, targeted profile passed.
- **Acceptance result**：PASS — the existing Conversation API/client and T01/T03 presentation flow replay only the optional server-authoritative `conversation_state` projection. Its fields are limited to `active_constraints`, `pending_clarification`, `pending_switch`, and `revision`; absence remains wire-compatible. The deterministic harness proves add, modify, withdraw, skip, pending switch, up to two clarifications, Answer/Fallback, target, correlation, and revision remain consistent; invalid wire input remains rejected before downstream calls by the existing transport gate.
- **Out-of-scope check**：No endpoint, bypass DTO, dependency, persistence, external service, Shopify write, architecture/core-doc, push, or integration change.

### S07-T05 — Journey and quality baseline

- **Status**：DONE
- **Implementation base**：`7b3db3a75e0d9d2c33fe6b6c82f70781e665b1b8`
- **Pre-existing diff**：clean detached snapshot at start.
- **Started/completed**：2026-09-03
- **Changed paths**：`changes/slice-07-storefront-closure/tasks.md`
- **Verification**：
  - `uv run ruff check .` → exit 0.
  - `uv run ruff format --check .` → exit 0, `138 files already formatted`.
  - `uv run pytest -q --durations=10` → exit 0, `551 passed in 0.74s`; slowest reported test call `0.01s`.
  - `uv run pytest -m e2e -q --durations=10` → exit 0, `65 passed, 486 deselected in 0.31s`; slowest reported test call `0.01s`.
  - `git diff --check` → exit 0; dependency lock/config and core-doc boundary checks → exit 0.
- **Acceptance result**：PASS — the full Journey and E2E baseline covers success/fallback/transport paths, constraint update/withdraw/skip and the T04 replay route. Existing E2E assertions verify zero Shopify writes and sensitive source metadata does not enter output or trace. Measurements are recorded only; no provisional Spec gates or Acceptance were adjusted.
- **Out-of-scope check**：No training, fine-tuning, long-lived metric platform, release automation, dependency/config, core-doc, external service, Shopify write, push, or integration change.
