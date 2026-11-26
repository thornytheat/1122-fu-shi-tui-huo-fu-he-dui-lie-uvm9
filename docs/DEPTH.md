# 可复核的模型和处置边界

分类 AI/ML / 传统ML。

## 功能模块

| 模块 | 业务步骤 | 输出 | 核心实现 | 独立契约与边界测试 |
|---|---|---|---|---|
| M1 | 验包流水 | ParcelScan处理证据 | `src/returnscope/parcel_scan/contracts.py` `src/returnscope/parcel_scan/algorithm.py` `src/returnscope/parcel_scan/service.py` `src/returnscope/parcel_scan/counter_health.py` | `tests/test_parcel_scan.py` `tests/test_counter_health.py` |
| M2 | 换店去重 | ReturnIdentity处理证据 | `src/returnscope/shop_identity/contracts.py` `src/returnscope/shop_identity/algorithm.py` `src/returnscope/shop_identity/service.py` `src/returnscope/shop_identity/refund_register.py` | `tests/test_shop_identity.py` `tests/test_refund_register.py` |
| M3 | 退货特征 | ExpectedPackage处理证据 | `src/returnscope/return_signals/contracts.py` `src/returnscope/return_signals/algorithm.py` `src/returnscope/return_signals/service.py` | `tests/test_return_signals.py` |
| M4 | 验包评分 | RiskVector处理证据 | `src/returnscope/inspection_score/contracts.py` `src/returnscope/inspection_score/algorithm.py` `src/returnscope/inspection_score/service.py` `src/returnscope/inspection_score/rolling_validation.py` | `tests/test_inspection_score.py` `tests/test_rolling_validation.py` |
| M5 | 复核配额 | ReviewCandidate处理证据 | `src/returnscope/desk_quota/contracts.py` `src/returnscope/desk_quota/algorithm.py` `src/returnscope/desk_quota/service.py` `src/returnscope/desk_quota/staffing_frontier.py` | `tests/test_desk_quota.py` `tests/test_staffing_frontier.py` |
| M6 | 退货复盘 | RefundEvidence处理证据 | `src/returnscope/return_replay/contracts.py` `src/returnscope/return_replay/algorithm.py` `src/returnscope/return_replay/service.py` `src/returnscope/return_replay/store_risk_ledger.py` | `tests/test_return_replay.py` `tests/test_store_risk_ledger.py` |

## 边界登记

| 陷阱 | 业务输入 | 处理位置 | 验证锚点 |
|---|---|---|---|
| TRAP-19 | 资料无法自动评分时优先人工核验，容量用尽仍可追溯 | `src/returnscope/desk_quota/algorithm.py` | `tests/test_desk_quota.py::test_manual_mandate_precedes_high_scoring_known_item` |
| TRAP-22 | 相同授权的异店退款单用等价关系归并 | `src/returnscope/shop_identity/algorithm.py` | `tests/test_shop_identity.py::test_store_aliases_do_not_change_primary_authorization_when_permuted` |
| TRAP-23 | 精确落在结单时刻的扫描归下一个结算批次 | `src/returnscope/parcel_scan/algorithm.py` | `tests/test_parcel_scan.py::test_exact_close_is_next_statement` |
| TRAP-26 | 旧扫描修订不覆盖新版本称重 | `src/returnscope/parcel_scan/algorithm.py` | `tests/test_parcel_scan.py::test_old_revision_is_inert_after_new_scan` |
| TRAP-31 | 大幅正负对数概率不会指数溢出 | `src/returnscope/inspection_score/algorithm.py` | `tests/test_inspection_score.py::test_extreme_logistic_remains_finite` |
| TRAP-32 | 无称重偏差历史时使用设备偏差下限 | `src/returnscope/return_signals/algorithm.py` | `tests/test_return_signals.py::test_exact_weight_variance_uses_instrument_floor` |
| TRAP-42 | 结算截止后的样本不改变训练特征 | `src/returnscope/return_signals/algorithm.py` | `tests/test_return_signals.py::test_future_weight_does_not_enter_category_statistics` |
| TRAP-43 | 无错件历史时平均精确率留空并标记 | `src/returnscope/return_replay/algorithm.py` | `tests/test_return_replay.py::test_no_observed_mismatch_returns_explicit_unavailable_average_precision` |
| TRAP-44 | 异常包裹超出历史特征轮廓时转验包 | `src/returnscope/inspection_score/algorithm.py` | `tests/test_inspection_score.py::test_unfamiliar_weight_profile_does_not_auto_release` |
| TRAP-53 | 异常包裹与正常包裹拼批不影响正常样本概率 | `src/returnscope/inspection_score/algorithm.py` | `tests/test_inspection_score.py::test_batch_composition_cannot_change_score` |
| TRAP-54 | 变更训练轮次使拟合指纹失效 | `src/returnscope/inspection_score/algorithm.py` | `tests/test_inspection_score.py::test_history_and_hyperparameters_change_version` |
