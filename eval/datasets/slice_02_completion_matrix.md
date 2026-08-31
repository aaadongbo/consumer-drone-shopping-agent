# Slice 2 Completion Matrix Dataset

This is a tiny deterministic replay manifest for S02-T07. It is not training data
and does not contain real customer, Shopify, or product data.

| Acceptance | Replay focus | Test coverage |
|---|---|---|
| S2-A01 | Deterministic constraints and unsupported fallback | `test_s2_a01_constraint_parse_and_unsupported_degrade_are_replayable` |
| S2-A02 | Variant-level HARD eligibility | `test_s2_a02_a03_a10_hard_eligibility_is_variant_current_and_fail_closed` |
| S2-A03 | UNKNOWN/missing HARD fields fail closed | `test_s2_a02_a03_a10_hard_eligibility_is_variant_current_and_fail_closed` |
| S2-A04 | Response identity alignment | `test_s2_a04_a05_a09_a12_response_identity_and_evidence_contract` |
| S2-A05 | No cross-Variant fact mixing | `test_s2_a04_a05_a09_a12_response_identity_and_evidence_contract` |
| S2-A06 | Max three distinct Products | `test_s2_a06_a07_a13_candidate_cap_order_and_replay_are_stable` |
| S2-A07 | Transparent deterministic SOFT ranking | `test_s2_a06_a07_a13_candidate_cap_order_and_replay_are_stable` |
| S2-A08 | No-match fallback without recommendation claims | `test_s2_a08_no_match_fallback_has_no_recommendation_claims` |
| S2-A09 | Evidence and claim binding | `test_s2_a04_a05_a09_a12_response_identity_and_evidence_contract` |
| S2-A10 | Current dynamic facts and `observed_at` | `test_s2_a02_a03_a10_hard_eligibility_is_variant_current_and_fail_closed` |
| S2-A11 | Store isolation | `test_s2_a11_store_isolation_and_mismatched_store_fail_closed` |
| S2-A12 | Public contract and trace correlation | `test_s2_a04_a05_a09_a12_response_identity_and_evidence_contract` |
| S2-A13 | Deterministic reproducibility | `test_s2_a06_a07_a13_candidate_cap_order_and_replay_are_stable` |

Representative replay prompts:

- `请推荐一款适合旅行的无人机，预算 3000 元，重量 250g 以内，至少1块电池`
- `预算 1000 元以内，至少3块电池，适合旅行`
- `适合旅行，4K，要避障`
- `你喜欢什么颜色？`

Completion caveat: real Shopify/model smoke remains outside this Slice completion
gate unless separately authorized.
