# Gate Load Balance Real Case Staging

更新时间：2026-04-01

## 目标

- 用 `V2.5 experiment_run` 推进一个新的 `gate_load_balance` 真实案例 staging case
- 同时把这轮运行作为 `codex_loop V2.5` 的真实主线压测

## 当前真相依赖

- [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
- [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)
- [ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)
- [current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)
- [2026-03-31-gate-load-balance-closeout-decision.md](D:/data/ai4s/holophage/tasks/2026-03-31-gate-load-balance-closeout-decision.md)
- [2026-03-31-gate-load-balance-strong-staging.md](D:/data/ai4s/holophage/tasks/2026-03-31-gate-load-balance-strong-staging.md)

## 运行契约

- workflow_kind: `experiment_run`
- risk_level: `low`
- candidate: `gate_load_balance`
- config:
  - [train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_load_balance.real_case_staging.yaml](D:/data/ai4s/holophage/baseline/train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_load_balance.real_case_staging.yaml)
- run_dir:
  - [multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_real_case_staging](D:/data/ai4s/holophage/baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_real_case_staging)

## Success Criteria

- `summary.json`、`evaluation/metrics_val.json`、`evaluation/metrics_test.json` 齐全
- `multilabel.num_samples > 0`
- `gate_health.status != collapsed`
- `mean_gates.sequence < 0.95`
- `structure + context > 0.05`
- `results_closeout` 风格的 strict artifact 证据链齐全
- `V2.5` 的 `run-once` 与短时 `run-autopilot` 都能自然完成或自然暂停

## 非目标

- 不切 production default
- 不恢复 `all`
- 不并行推进 `gate_entropy`
- 不在本轮扩大配置搜索空间

## 本轮判断问题

1. `gate_load_balance` 是否继续保持首选 staging 候选
2. 当前是否已经足够进入更高预算实测
3. `V2.5` 在真实 experiment task 上是否暴露 runtime / recovery / closeout 暗病
