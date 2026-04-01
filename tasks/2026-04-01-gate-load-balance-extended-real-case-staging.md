# Gate Load Balance Extended Real Case Staging

更新时间：2026-04-01

## 目标

- 在 higher-budget 双 seed 成功后，继续跑一轮更强真实案例实测
- 作为 `promotion_readiness_review` 通过后的自动下一环

## 当前真相依赖

- [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
- [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)
- [ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)
- [current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)
- [2026-04-01-gate-load-balance-promotion-readiness-review.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-promotion-readiness-review.md)

## 运行契约

- workflow_kind: `experiment_run`
- risk_level: `low`
- candidate: `gate_load_balance`
- config:
  - [train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_load_balance.extended_real_case_staging.yaml](D:/data/ai4s/holophage/baseline/train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_load_balance.extended_real_case_staging.yaml)
- run_dir:
  - [multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging](D:/data/ai4s/holophage/baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging)

## Success Criteria

- `summary.json`、`evaluation/metrics_val.json`、`evaluation/metrics_test.json` 齐全
- `multilabel.num_samples > 0`
- `gate_health.status != collapsed`
- `mean_gates.sequence < 0.95`
- `structure + context > 0.05`
- strict closeout 所需 artifact 证据链齐全

## 非目标

- 不引入新正则
- 不修改 fusion 结构
- 不切 production default
