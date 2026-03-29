# 多模态 v2 阶段性实验结果（2026-03-29）

## 1. 实验范围

当前已完成的正式实验：

- `seq-only`：3 / 3 seeds
- `seq+struct`：3 / 3 seeds
- `seq+ctx`：3 / 3 seeds

当前已暂停：

- `all`：未纳入本次阶段性结论

统一口径：

- split：`homology_cluster_v1`
- status：`trainable_core`
- labels：`L1 + L2 + L3 core`
- seeds：`42 / 52 / 62`

## 2. 主结果概览

### `seq-only`

| seed | L3 macro F1 | L3 accuracy |
| --- | ---: | ---: |
| 42 | 0.9592 | 0.9656 |
| 52 | 0.9671 | 0.9736 |
| 62 | 0.9553 | 0.9605 |
| mean | **0.9606** | **0.9665** |

结论：

- 当前 `seq-only` 已经是非常强的正式 baseline
- 说明在 `trainable_core` 单标签任务上，sequence 信息本身已经足够强

### `seq+struct`

| seed | L3 macro F1 | L3 accuracy | structure gate |
| --- | ---: | ---: | ---: |
| 42 | 0.9650 | 0.9709 | 0.00065 |
| 52 | 0.9708 | 0.9765 | 0.00049 |
| 62 | 0.9643 | 0.9700 | 0.00241 |
| mean | **0.9667** | **0.9725** | **0.00118** |

相对 `seq-only`：

- 平均 `L3 macro F1` 提升约 **+0.0061**
- `3 / 3` seeds 全部为正向提升

结论：

- `seq+struct` 有**稳定小幅提升**
- 结构分支不是无效分支
- 但结构 gate 极低，说明它更像**弱增强 / 定向补益**，不是主判别来源

### `seq+ctx`

| seed | L3 macro F1 | L3 accuracy | context gate |
| --- | ---: | ---: | ---: |
| 42 | 0.9626 | 0.9678 | 0.00014 |
| 52 | 0.9644 | 0.9683 | 0.00024 |
| 62 | 0.9575 | 0.9656 | 0.00022 |
| mean | **0.9615** | **0.9672** | **0.00020** |

相对 `seq-only`：

- 平均 `L3 macro F1` 变化约 **+0.0009**
- 三个 seeds 为 `+ / - / +`

结论：

- 当前 `seq+ctx` **没有表现出明确、稳定的全局增益**
- context gate 接近 0，说明当前 `context_features_v1` 基本没有真正进入决策

## 3. 长尾类观察

当前可见证据下，`seq+struct` 对部分长尾类有正向收益，代表性类别包括：

- `Minor_capsid`
- `Ribonucleotide_reductase`
- `Replication_initiator`
- `RNA_polymerase`
- `CI_like_repressor`

结论：

- 结构分支的价值更像**对特定类的定向补益**
- 不是所有长尾类都提升，但确实存在可见正向受益类别

## 4. 泄露与评估风险排查

当前已确认：

- `exact_sequence_rep_id` 跨 split 交集 = `0`
- 原始 `sequence` 跨 split 交集 = `0`
- `homology_cluster_id` 跨 split 交集 = `0`

说明：

- 当前没有发现重复序列或同源 cluster 跨 split 泄露

仍需注意：

- 当前 split 是 `homology_cluster_v1`
- 不是 `genome-heldout`
- `genome_id` 在 split 间有大量重复

结论：

- 对 sequence-only baseline，这不构成明显硬泄露证据
- 但对 context 分支，这意味着结果可能仍带有 genome/context 简化风险

## 5. 阶段性判断

当前阶段最稳的结论是：

1. `seq-only` 是强且稳定的正式 baseline
2. `seq+struct` 有稳定小幅提升，值得保留为弱增强结构分支
3. `seq+ctx` 当前实现没有表现出明确价值
4. `all` 在当前 context 表示不强的情况下优先级下降，已暂停

## 6. 后续动作

建议的下一步：

1. 保留当前 `seq-only` 和 `seq+struct` 结果
2. 重做 context 分支表示
3. 给 context 单独补更严格的 `genome/context-aware` 辅助评估
4. context 重构后，再决定是否恢复 `all`
5. 结构分支后续升级优先候选：
   - `ProstT5 -> 3Di -> SaProt(AA+3Di)`

---
doc_status: draft
source_of_truth_level: reference
doc_scope: experiment_results
owner_path: project_memory/02_data_pipeline
last_verified: 2026-03-29
version: 1
supersedes: []
superseded_by: []
related_active_manifest:
  - project_memory/04_active_assets/ACTIVE_VERSION.yaml
  - project_memory/04_active_assets/ACTIVE_PATHS.yaml
runtime_allowed: false
archive_if_replaced: true
---
