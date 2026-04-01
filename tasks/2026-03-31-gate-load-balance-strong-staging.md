# Gate Load Balance Strong Staging

更新时间：2026-03-31

## 目标

- 基于当前首选候选 `gate_load_balance`，跑一轮比 `staging_lite` 更强的 staging 验证
- 同时验证 V2 的 `experiment_run + experiment registry`

## 基线配置

- [train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_load_balance.strong_staging.yaml](D:/data/ai4s/holophage/baseline/train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_load_balance.strong_staging.yaml)

## Success Criteria

- `summary.json`、`metrics_val.json`、`metrics_test.json` 齐全
- `multilabel.num_samples > 0`
- `gate_health.status != collapsed`
- `mean_gates.sequence < 0.95`
- `structure + context > 0.05`
- experiment registry 成功落地

## 非目标

- 本任务不并排扩展 `gate_entropy`
- 本任务不改变正式默认配置

## Outcome

- 已完成并通过 V2 `experiment_run`
- run：
  - [summary.json](D:/data/ai4s/holophage/baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_strong_staging/summary.json)
- 核心结果：
  - `best_val_l3_macro_f1 ≈ 0.9678`
  - `best_val_multilabel_micro_f1 ≈ 0.9394`
  - `val mean_gates ≈ 0.334 / 0.269 / 0.397`
  - `gate_health = healthy`
- `experiment registry` 已成功同步：
  - [multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_strong_staging__seed42.json](D:/data/ai4s/holophage/loop_state/experiments/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_strong_staging__seed42.json)
