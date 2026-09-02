# Slice 6 Ordered Implementation Tasks — Evidence-based Recommendation

> 状态：APPROVED PLANNING BASELINE / Implementation not yet authorized
>
> Slice 6 的目标、Scope、Acceptance、预算与 Task 表已经过 Human Planning Review。下表现在使用正式 Task 状态；S06 workflow policy 已预配置并随本 baseline 激活。`NOT_STARTED` 不构成 Implementation authority：开始 S06-T01 前仍须取得单独的 Slice Implementation 授权。

Slice 6 承接 Slice 5 未执行的 multi-product evidence collection、commerce refresh、HARD recheck 和 Derived Evidence。它仍使用 `max_action_rounds = 2 total`：第 1 轮包含初始候选证据读取；最多第 2 轮执行一个 allowlisted corrective action。

Provisional budget config:

| Key | Provisional hard limit | Stop reason |
|---|---:|---|
| `max_action_rounds` | `2` total | `ACTION_ROUND_LIMIT` |
| `max_tool_calls` | `2` per turn | `TOOL_CALL_LIMIT` |
| `turn_deadline_ms` | `8000` | `TURN_DEADLINE` |
| `max_retrieval_tokens` | `4000` per turn | `RETRIEVAL_TOKEN_BUDGET` |
| `max_model_tokens` | `1200` per turn | `MODEL_TOKEN_BUDGET` |

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | Candidate evidence bundle contract | DONE | Slice 5 completion + Slice 6 planning baseline |
| T02 | Per-product RAG evidence collection plan | DONE | T01 |
| T03 | Commerce refresh and HARD recheck plan | DONE | T01 |
| T04 | Derived Evidence computation | DONE | T02, T03 |
| T05 | Recommendation explanation and degradation | DONE | T04 |
| T06 | Multi-product recommendation walking skeleton | DONE | T05 |
| T07 | Slice 6 verification matrix and completion evidence | DONE | T06 |

## T01 — Candidate evidence bundle contract

- **Goal**：定义每个候选的 Catalog/Shopify/RAG/Derived Evidence bundle。
- **Why**：多商品推荐只有在每个候选的证据包隔离后，才能避免跨商品理由污染。
- **Scope**：未来 `backend/evidence/` bundle value objects；unit/contract tests；tasks execution record。
- **Contract**：`CandidateEvidenceBundle`、candidate identity、catalog evidence、commerce evidence、rag evidence、derived evidence、coverage state。
- **Acceptance**：bundle 与 candidate identity 一致；公共 schema 变化先停 Human checkpoint；不同候选 Evidence 不共享 mutable state。
- **Verification**：Contract + Unit.
- **Dependencies**：Slice 5 completion + Slice 6 planning approval.
- **Out of Scope**：真实推荐文案、RAG retrieval execution、commerce refresh execution。

### Execution Record — S06-T01

- **Status**：DONE
- **Start commit**：`ce515ca1b809449538ce209fa30d93dcc59c3b00`
- **Start workspace**：clean；无 staged 或 untracked 文件。
- **Changed paths**：`backend/evidence/recommendation_bundle.py`、`backend/evidence/__init__.py`、`tests/unit/test_s06_t01_evidence_bundle.py`、`tests/contract/test_s06_t01_evidence_bundle_contract.py`、本任务表。
- **Implementation**：新增 candidate identity、source-separated evidence lanes、coverage state、derived evidence 输入引用和 bundle identity/ID invariants；未修改公共 wire Contract。
- **Verification**：targeted unit/contract `6 passed`；changed-file Ruff lint/format 通过；`git diff --check` 通过。
- **First failure and fix**：首次 Ruff 发现 contract test 两个未使用的 datetime imports（exit `1`）；删除 imports 后重跑通过。
- **Scope/safety**：仅限 T01 allowlist；无依赖、网络、Shopify 调用或写操作。
- **Next**：进入 S06-T02。

## T02 — Per-product RAG evidence collection plan

- **Goal**：为每个 Product/Variant 分配独立 evidence objectives 与检索预算。
- **Why**：推荐最多三款 Product，必须避免单个文档丰富的商品占满证据预算。
- **Scope**：未来 `backend/agent/` evidence plan；`backend/evidence/` coverage state；integration with Slice 5 retriever。
- **Contract**：`RecommendationActionPlan` 的 candidate set、evidence objectives、per-product budgets、ActionRoundTrace。
- **Acceptance**：每个候选只接收自身 scoped Evidence；缺证有 coverage state；预算耗尽用 exact stop reason 记录。
- **Verification**：Unit + Integration with Slice 5 retriever.
- **Dependencies**：T01.
- **Out of Scope**：multi-product retrieval 算法定案、reranker 固化、开放网络。

### Execution Record — S06-T02

- **Status**：DONE
- **Start commit**：`ce515ca1b809449538ce209fa30d93dcc59c3b00`
- **Start workspace**：T01 changes present only; no staged or unrelated paths.
- **Changed paths**：`backend/agent/recommendation_evidence_plan.py`、`backend/agent/__init__.py`、`tests/unit/test_s06_t02_evidence_plan.py`、`tests/integration/test_s06_t02_retrieval_plan.py`、本任务表。
- **Implementation**：新增 candidate-set、per-product objectives/budgets、两轮上限及 typed `RetrievalRequest` builder；每个 request 保留独立 Store/Product/Variant scope，不执行 retriever。
- **Verification**：targeted unit/integration `4 passed`；changed-file Ruff lint/format 通过；`git diff --check` 通过。
- **First failure and fix**：首次 integration fixture 使用了错误的 `DocumentManifest` shape（exit `1`）；改为合法授权 `DocumentSource` 后通过。随后修正 3 个 Ruff 格式问题并重跑通过。
- **Scope/safety**：仅限 T02 allowlist；无公共 Contract、依赖、网络、Shopify 调用或写操作。
- **Next**：进入 S06-T03。

## T03 — Commerce refresh and HARD recheck plan

- **Goal**：推荐解释前刷新动态事实并复核 HARD eligibility。
- **Why**：推荐合法性依赖当前价格、库存和可售状态，不能沿用旧 commerce facts。
- **Scope**：未来 `backend/agent/` refresh plan；`backend/catalog/` HARD recheck adapter；`backend/evidence/` commerce Evidence；zero-write tests。
- **Contract**：`RecommendationActionPlan` commerce refresh needs、Shopify ToolResult、CandidateEvidenceBundle commerce evidence。
- **Acceptance**：动态事实失败、过期或 identity mismatch 时 fail closed；不使用 stale facts；Shopify write count 为 0。
- **Verification**：Integration + zero-write ledger.
- **Dependencies**：T01.
- **Out of Scope**：Shopify write、真实 credentials、retry/backoff framework、状态持久化重构。

### Execution Record — S06-T03

- **Status**：DONE
- **Start commit**：`ce515ca1b809449538ce209fa30d93dcc59c3b00`
- **Start workspace**：T01/T02 changes present; no staged or unrelated paths.
- **Changed paths**：`backend/catalog/commerce_refresh.py`、`backend/evidence/commerce.py`、相关 package exports、`tests/unit/test_s06_t03_commerce_evidence.py`、`tests/integration/test_s06_t03_commerce_refresh.py`、本任务表。
- **Implementation**：使用现有 `ShopifyReadPort.refresh_commerce_state` 获取当前 ToolResult，立即执行 Variant-level HARD recheck；仅将当前成功/部分数据转换为 candidate-scoped commerce Evidence，失败不复用旧值。
- **Verification**：targeted unit/integration `4 passed`；changed-file Ruff lint/format 通过；import probe 与 `git diff --check` 通过；fixture ledger 仅记录 refresh read，write count 为 `0`。
- **First failure and fix**：首次测试错误使用 Slice 1 Shopify fixture 的 `drone-travel`/`store-s02-alpha` identity，导致预期成功路径返回 `PRODUCT_NOT_FOUND`（exit `1`）；改为当前 `store-drone-cn / drone-mini / mini-standard` fixture identity 后通过。
- **Scope/safety**：仅限 T03 allowlist；未修改 Port surface、公共 Contract、依赖或外部服务。
- **Next**：进入 S06-T04。

## T04 — Derived Evidence computation

- **Goal**：计算预算余量、差价、重量/续航/电池差等可复算 Evidence。
- **Why**：推荐解释经常需要“更便宜多少”“轻多少”等派生事实，必须由已验证输入计算。
- **Scope**：未来 `backend/evidence/` deterministic derivation utilities；unit tests with table fixtures。
- **Contract**：`DerivedEvidence` formula/rule、input evidence IDs、computed value、unit、observed/catalog version。
- **Acceptance**：每项派生值绑定输入 Evidence、单位和公式；输入缺失则不生成；不做模型自由数学。
- **Verification**：Unit + property-like table.
- **Dependencies**：T02, T03.
- **Out of Scope**：不可解释评分、学习排序、Product RAG retrieval。

### Execution Record — S06-T04

- **Status**：DONE
- **Start commit**：`ce515ca1b809449538ce209fa30d93dcc59c3b00`
- **Start workspace**：T01–T03 changes present; no staged or unrelated paths.
- **Changed paths**：`backend/evidence/derived.py`、`backend/evidence/__init__.py`、`tests/unit/test_s06_t04_derived_evidence.py`、本任务表。
- **Implementation**：新增预算余量和同候选数值差的确定性派生函数；强制输入为 KNOWN、数值、同一 Variant，并记录公式、输入 Evidence ID、单位与时间戳。
- **Verification**：targeted unit `3 passed`；changed-file Ruff lint/format、import probe 与 `git diff --check` 通过。
- **First failure and fix**：首次 Ruff format 检查发现派生模块与测试各有一处需格式化（exit `1`）；格式化后重跑全部通过。
- **Scope/safety**：仅限 T04 allowlist；未引入学习排序、模型数学或公共 Contract 变化。
- **Next**：进入 S06-T05。

## T05 — Recommendation explanation and degradation

- **Goal**：生成理由、取舍、coverage disclosure 和 fallback/degradation。
- **Why**：证据不足不能阻塞所有价值，但正式推荐理由必须只表达被证据支持的内容。
- **Scope**：未来 `backend/agent/` explanation policy；`backend/evidence/` coverage checks；contract/integration tests。
- **Contract**：`RecommendationExplanation`、supported reasons、tradeoffs、binding map、`RecommendationFallback`。
- **Acceptance**：每条理由都有 Evidence 或被删除/降级；UNKNOWN 明确披露；关键 coverage 不足时 fallback。
- **Verification**：Contract + Integration.
- **Dependencies**：T04.
- **Out of Scope**：正式 UI、个性化学习排序、利润/库存去化排序。

### Execution Record — S06-T05

- **Status**：DONE
- **Start commit**：`ce515ca1b809449538ce209fa30d93dcc59c3b00`
- **Start workspace**：T01–T04 changes present; no staged or unrelated paths.
- **Changed paths**：`backend/agent/recommendation_explanation.py`、`backend/agent/__init__.py`、`tests/unit/test_s06_t05_explanation.py`、`tests/contract/test_s06_t05_explanation_contract.py`、`tests/integration/test_s06_t05_explanation_flow.py`、本任务表。
- **Implementation**：新增按候选 Evidence 覆盖生成理由、tradeoff 与 unknown disclosure 的内部模型；非关键缺证据降级，关键缺证据返回 fallback；禁止 foreign-candidate tradeoff。
- **Verification**：targeted unit/contract/integration `5 passed`；changed-file Ruff lint/format、import 与 `git diff --check` 通过。
- **First failure and fix**：首次 Ruff 检查发现 import 排序、3 处行长及 1 个未使用局部变量（exit `1`）；修正并格式化后重跑通过。
- **Scope/safety**：仅限 T05 allowlist；未生成公共 AnswerEnvelope、未引入学习排序或外部服务。
- **Next**：进入 S06-T06。

## T06 — Multi-product recommendation walking skeleton

- **Goal**：打通 constraints -> eligibility -> per-product evidence -> derived -> explanation -> response。
- **Why**：Slice 6 需要证明推荐输出在多候选、多证据、多降级路径下仍可回放。
- **Scope**：未来 `backend/application/` recommendation flow；`backend/agent/` plan; `backend/catalog/` eligibility; `backend/evidence/` bundle; tests。
- **Contract**：CandidateEvidenceBundle、RecommendationActionPlan、DerivedEvidence、RecommendationExplanation、existing AnswerEnvelope or versioned proposal。
- **Acceptance**：最多三款 Product；每款 Variant 明确；no-match 与 partial-evidence fallback 可靠；所有 facts 绑定对应候选。
- **Verification**：Integration + E2E.
- **Dependencies**：T05.
- **Out of Scope**：Slice 7 storefront、真实外部服务、push、完整比较引擎。

### Execution Record — S06-T06

- **Status**：DONE
- **Start commit**：`ce515ca1b809449538ce209fa30d93dcc59c3b00`
- **Start workspace**：T01–T05 changes present; no staged or unrelated paths.
- **Changed paths**：`backend/application/recommendation.py`、`backend/application/__init__.py`、`tests/integration/test_s06_t06_recommendation_flow.py`、`tests/e2e/test_s06_t06_recommendation_journey.py`、本任务表。
- **Implementation**：打通 Catalog eligibility/ranking → candidate-scoped current commerce refresh/HARD recheck → per-candidate RAG retrieval → Derived Evidence → explanation/degradation → internal typed response；最多三款 Product，所有 trace 共享 correlation ID。
- **Verification**：targeted integration `2 passed`、E2E `1 passed`；changed-file Ruff lint/format、import 与 `git diff --check` 通过；test read double write count 为 `0`。
- **First failure and fix**：首次 integration 断言过度假设具体排序结果，把 `drone-survey` 错判为失败（exit `1`）；收敛为验证最多三款、Product 去重与页面候选存在后通过。随后修正 import/format 问题并重跑通过。
- **Scope/safety**：未修改公共 `AnswerEnvelope` 或 Shopify Port；多商品 public payload 继续是后续 Contract 决策，不调用网络或写操作。
- **Next**：进入 S06-T07。

## T07 — Slice 6 verification matrix and completion evidence

- **Goal**：覆盖 S6-A01～S6-A12 和 Matrix #1～#12。
- **Why**：Slice 6 完成前需要证明推荐合法性、动态事实、派生证据、降级和零写边界都可靠。
- **Scope**：tests、eval fixtures、tasks execution evidence、Slice completion review。
- **Contract**：S6 verification matrix、ActionRoundTrace、RecommendationFallback、zero-write evidence。
- **Acceptance**：full suite、scope、evidence、dynamic fact、derived replay、zero-write gates 通过。
- **Verification**：Static + Unit + Contract + Integration + E2E + full suite.
- **Dependencies**：T06.
- **Out of Scope**：Slice 7 implementation、fine-tuning、feature delivery workflow changes。

### Execution Record — S06-T07

- **Status**：DONE
- **Start commit**：`ce515ca1b809449538ce209fa30d93dcc59c3b00`
- **Start workspace**：T01–T06 changes present; no staged or unrelated paths.
- **Changed paths**：`tests/e2e/test_s06_t07_completion_matrix.py`、本任务表。
- **Implementation**：补齐候选上限、HARD no-match/UNKNOWN、per-candidate Evidence 与 Derived Evidence identity、当前动态事实、RAG 缺失降级、确定性回放、trace correlation 与 zero-write matrix。
- **Verification**：targeted matrix `7 passed`；`uv lock --check` 通过；全仓 Ruff lint/format 通过；完整 suite `525 passed`；`git diff --check` 通过。
- **First failure and fix**：首次 Ruff 检查发现 matrix 测试 import 排序和 4 处行长问题（exit `1`）；格式化并整理 imports 后 targeted 与全量门禁通过。
- **Matrix result**：S6-A01～S6-A12 及 Matrix #1～#12 均有可回放测试证据；无 Shopify write、外部网络、秘密 trace 或跨 Store 读取。
- **Scope/safety**：仅限 T07 allowlist；未修改公共 Contract、Architecture、Workflow、依赖或 Slice 7。
- **Completion**：S06 T01–T07 全部 `DONE`；等待一次独立 Slice completion review 与 Human 集成决策。

## Human Escalation

公共 Contract、Product Behavior、Architecture、重大依赖、外部服务、open-network Evidence、Shopify write、learning ranking 固化、Evidence Gate 放宽或超过 `2` 个 total action rounds 都必须升级。
