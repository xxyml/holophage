# Gate Entropy Reference Check

更新时间：2026-04-01

## 目标

- 保留一个最小 `gate_entropy` 对照证据
- 只用于后续解释性参照，不抢主链资源

## 当前真相依赖

- [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
- [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)
- [ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)
- [current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)
- [2026-03-31-multimodal-gate-collapse-analysis.md](D:/data/ai4s/holophage/tasks/2026-03-31-multimodal-gate-collapse-analysis.md)

## 运行契约

- workflow_kind: `experiment_run`
- risk_level: `low`
- candidate: `gate_entropy`
- config:
  - [train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_entropy.reference_check.yaml](D:/data/ai4s/holophage/baseline/train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_entropy.reference_check.yaml)
- run_dir:
  - [multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_entropy_reference_check](D:/data/ai4s/holophage/baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_entropy_reference_check)

## Success Criteria

- 能形成最小对照证据
- 不影响主链 higher-budget 运行窗口
- 结果能解释“为什么当前仍优先 `gate_load_balance`”
