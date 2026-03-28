# Baseline Input Manifest

更新时间：2026-03-27

本文件列出当前 baseline 第一轮训练应直接使用的正式输入文件，以及每个文件的用途、关键字段和当前口径。

## 1. 标签主表

### `data_processed/training_labels_wide_with_split.csv`

路径：
- [training_labels_wide_with_split.csv](D:/data/ai4s/holophage/data_processed/training_labels_wide_with_split.csv)

关键字段：
- `protein_id`
- `genome_id`
- `contig_id`
- `gene_index`
- `sequence`
- `sequence_length`
- `status`
- `level1_label`
- `level2_label`
- `node_primary`
- `split`
- `split_strategy`
- `split_version`
- `exact_sequence_rep_id`
- `homology_cluster_id`

正式口径：
- `split_strategy = homology_cluster`
- `split_version = homology_cluster_v1`

## 2. baseline join 索引

### `data_processed/baseline_embedding_join_index.csv`

路径：
- [baseline_embedding_join_index.csv](D:/data/ai4s/holophage/data_processed/baseline_embedding_join_index.csv)

关键字段：
- `protein_id`
- `embedding_id`
- `sequence_embedding_key`
- `exact_sequence_rep_id`
- `homology_cluster_id`
- `split`
- `status`
- `level1_label`
- `level2_label`
- `node_primary`

说明：
- `embedding_id` 仅保留给日志、debug、上下文回填
- `sequence_embedding_key` 当前应等于 `exact_sequence_rep_id`

## 3. 正式 split

### `splits/split_by_homology_cluster_v1.csv`

路径：
- [split_by_homology_cluster_v1.csv](D:/data/ai4s/holophage/splits/split_by_homology_cluster_v1.csv)

## 4. sequence embedding 输入与输出

### exact sequence 输入表

- [exact_sequence_embedding_input.parquet](D:/data/ai4s/holophage/embedding_pipeline/inputs/exact_sequence_embedding_input.parquet)

字段：
- `id = exact_sequence_rep_id`
- `sequence`

### exact sequence embedding 目录

- [embed_exact](D:/data/ai4s/holophage/embedding_pipeline/outputs/embed_exact)

说明：
- 当前 `shard_*.pt` 保存 `976,210` 条 exact unique sequence 的 embedding
- baseline 训练时按实例表中的 `exact_sequence_rep_id` 回填 sequence embedding
- 长序列正式策略：
  - `<=512 aa`：整条编码
  - `>512 aa`：滑窗重叠后聚合

## 5. embedding 流水线目录

- [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)

说明：
- 脚本：`scripts/`
- 输入：`inputs/`
- 模型：`models/`
- 输出：`outputs/`
- 日志：`logs/`

## 6. structure retrieval 资产

- [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline)
- [structures](D:/data/ai4s/holophage/structures)

说明：
- 当前结构链保留为可选增强资产
- 第一轮 baseline 不再依赖真实结构文件作为必选主输入

## 7. vocab

- [label_vocab_l1.json](D:/data/ai4s/holophage/outputs/label_vocab_l1.json)
- [label_vocab_l2.json](D:/data/ai4s/holophage/outputs/label_vocab_l2.json)
- [label_vocab_l3_core.json](D:/data/ai4s/holophage/outputs/label_vocab_l3_core.json)
---
doc_status: active
source_of_truth_level: canonical
doc_scope: data_pipeline
owner_path: project_memory/02_data_pipeline
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
