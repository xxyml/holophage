# Gate Load Balance Higher Budget Staging

更新时间：2026-04-01

## 目标

- 在 `real_case_staging` 成功基础上提高预算，继续验证 `gate_load_balance` 的稳定性
- 让 `V2.5 experiment_run` 开始承接持续运行的主链第一环

## 当前真相依赖

- [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
- [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)
- [ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)
- [current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)
- [2026-04-01-gate-load-balance-real-case-closeout-decision.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-real-case-closeout-decision.md)

## 运行契约

- workflow_kind: `experiment_run`
- risk_level: `low`
- candidate: `gate_load_balance`
- config:
  - [train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_load_balance.higher_budget_staging.yaml](D:/data/ai4s/holophage/baseline/train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_load_balance.higher_budget_staging.yaml)
- run_dir:
  - [multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_higher_budget_staging](D:/data/ai4s/holophage/baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_higher_budget_staging)

## Success Criteria

- `summary.json`、`evaluation/metrics_val.json`、`evaluation/metrics_test.json` 齐全
- `multilabel.num_samples > 0`
- `gate_health.status != collapsed`
- `mean_gates.sequence < 0.95`
- `structure + context > 0.05`
- strict closeout 所需 artifact 证据链齐全

## 非目标

- 不切 production default
- 不恢复 `all`
- 不引入新正则
- 不改 fusion 结构

## 本轮判断问题

1. `gate_load_balance` 是否在更高预算下继续保持健康
2. 当前是否足够进入 second-seed 同预算复核
3. `V2.5` 在更长 experiment_run 上是否出现新的 runtime 暗病
