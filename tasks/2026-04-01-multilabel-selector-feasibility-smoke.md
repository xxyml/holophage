# Multilabel Selector Feasibility Smoke

更新时间：2026-04-01

## 目标

- Run the smallest safe experiment to validate whether an is_multilabel selector is needed and learnable.

## 当前真相依赖

- [current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)
- [2026-04-01-multilabel-inference-protocol-design.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-inference-protocol-design.md)

## Success Criteria

- selector feasibility smoke 产物齐全
- 不会破坏当前 `PFO v1.0.2` / `homology_cluster_v1` / `exact_sequence_rep_id` / `L1 + L2 + L3 core` / `trainable_core` 主线

## 非目标

- 不改结构，不改 gate 正则形式
- 不恢复 `all`，不并行推进 `gate_entropy`
