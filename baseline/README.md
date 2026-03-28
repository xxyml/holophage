# Baseline Skeleton (L1 + L2 + L3 Core)

当前 baseline 只覆盖：

- `L1 (7)`
- `L2 (21)`
- `L3 core (29)`

当前这条线应被视为：

- **sequence-only**
- **trainable_core-only**
- **第一轮稳定对照基线**

后续即使加入 multilabel / open-set / context / structure-like 分支，也不应删除这条 baseline；它应长期保留作为对照组。

暂不纳入：

- `parent_only`
- `trainable_multilabel`
- `defer`
- `open_set`
- 真实结构文件主训练
- 上下文模态主训练

## 当前训练边界

- 只使用 `status == trainable_core`
- `split_strategy = homology_cluster`
- `split_version = homology_cluster_v1`
- `node_primary` 不是全量 L3 vocab 来源
- L3 vocab 固定来自 `outputs/label_vocab_l3_core.json`

## 当前 sequence embedding 口径

- sequence embedding 主键：`exact_sequence_rep_id`
- 训练样本仍是实例级蛋白
- `protein_id` / `embedding_id` 继续保留，但不再作为 sequence embedding 查询键
- 当前正式 embedding 根目录：
  - [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)
- 当前正式 embedding 输出目录：
  - [embed_exact](D:/data/ai4s/holophage/embedding_pipeline/outputs/embed_exact)
- 当前正式模型目录：
  - [prot_t5_xl_uniref50_bits](D:/data/ai4s/holophage/embedding_pipeline/models/prot_t5_xl_uniref50_bits)

## 采样策略

当前训练默认使用：
- `cluster_exact_balanced`

逻辑：
1. 先按 `homology_cluster_id` 控权
2. 再按 `exact_sequence_rep_id` 去冗余控权
3. 标签长尾继续主要用 `class weight` 处理

这不是删数据，而是：
- 保留 train split 内全部蛋白实例
- 只在 batch 构造阶段降低大 cluster 和 exact duplicate 的主导效应

## 当前设计的定位

当前模型与损失设计的定位是：

- 用最小可解释结构验证 split、label、embedding 管线是否健康
- 先把 `L1 + L2 + L3 core` 跑稳
- 暂不试图一次吃下 `parent_only / trainable_multilabel / defer / open_set`

因此：

- 当前实现是合理的第一轮 baseline
- 当前实现不是最终版本
- 下一步优先补的是 **supervision routing**，不是更复杂的 backbone

## 后续优先级

后续按以下顺序推进：

1. 收紧 single source of truth
   - L2 正式固定为 `21 类`
   - 清理旧的 genome-aware 口径
2. 保留当前 sequence-only core baseline 作为永久对照组
3. 先扩 coarse supervision
   - 把 `parent_only + trainable_multilabel` 纳入 `L1/L2`
4. 再加独立 multilabel head
5. 最后再做 open-set 与 context branch

## 输入文件

- 标签主表：`data_processed/training_labels_wide_with_split.csv`
- join 索引：`data_processed/baseline_embedding_join_index.csv`
- vocab：
  - `outputs/label_vocab_l1.json`
  - `outputs/label_vocab_l2.json`
  - `outputs/label_vocab_l3_core.json`
- exact sequence embedding：
  - `D:\data\ai4s\holophage\embedding_pipeline\outputs\embed_exact\shard_*.pt`

## sampler-ready schema

online dataset 和 prepacked dataset 都必须携带：

- `protein_id`
- `embedding_id`
- `split`
- `label_l1`
- `label_l2`
- `label_l3_core`
- `homology_cluster_id`
- `exact_sequence_rep_id`

## 离线预处理

1. 构建 exact embedding sqlite 索引：

```powershell
conda run -n ai4s python -m baseline.build_embedding_index --config baseline/train_config.full_stage2.yaml --overwrite
```

2. 重建 exact prepacked 包：

```powershell
conda run -n ai4s python -m baseline.prepack_embeddings --config baseline/train_config.full_stage2.yaml --output-dir baseline/artifacts/prepacked_core_exact --overwrite --dtype float32
```

## 训练

```powershell
conda run -n ai4s python -u -m baseline.train --config baseline/train_config.full_stage2.yaml
```
---
doc_status: active
source_of_truth_level: canonical
doc_scope: baseline
owner_path: baseline
last_verified: 2026-03-28
version: 1
supersedes: []
superseded_by: []
related_active_manifest:
  - project_memory/04_active_assets/ACTIVE_VERSION.yaml
  - project_memory/04_active_assets/ACTIVE_PATHS.yaml
runtime_allowed: false
archive_if_replaced: true
---
