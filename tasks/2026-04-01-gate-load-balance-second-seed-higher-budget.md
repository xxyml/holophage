# Gate Load Balance Second Seed Higher Budget

更新时间：2026-04-01

## 目标

- 在与 higher-budget staging 相同配置下做第二 seed 复核，优先 `seed52`
- 把“当前单 seed 可用”升级成“更高预算下双 seed 可复核”

## 当前真相依赖

- [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
- [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)
- [ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)
- [current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)
- [2026-04-01-gate-load-balance-higher-budget-closeout-decision.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-higher-budget-closeout-decision.md)

## 运行契约

- workflow_kind: `experiment_run`
- risk_level: `low`
- candidate: `gate_load_balance`
- seed: `52`
- config:
  - [train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_load_balance.higher_budget_staging_seed52.yaml](D:/data/ai4s/holophage/baseline/train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_load_balance.higher_budget_staging_seed52.yaml)
- run_dir:
  - [multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_higher_budget_staging_seed52](D:/data/ai4s/holophage/baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_higher_budget_staging_seed52)

## Success Criteria

- `summary.json`、`evaluation/metrics_val.json`、`evaluation/metrics_test.json` 齐全
- `multilabel.num_samples > 0`
- `gate_health.status != collapsed`
- `mean_gates.sequence < 0.95`
- `structure + context > 0.05`
- 与单 seed higher-budget 同口径对比可解释

## 非目标

- 不新增结构超参搜索
- 不更改正则形式
- 不修改 mainline truth

## 本轮判断问题

1. `gate_load_balance` 的 higher-budget 结论是否具备双 seed 支撑
2. 当前是否足够进入更大规模 staging / promotion-readiness review
