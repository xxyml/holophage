# Processing Changelog

## 2026-03-26

- added `structure_pipeline/` for exact-sequence keyed structure retrieval
- locked structure asset key to `exact_sequence_rep_id`
- added online-first screening and download flow for `AFDB > BFVD > Viro3D`
- verified BFVD single-file download via `cif.tar.index + cif.tar + HTTP Range + gzip`

更新时间：2026-03-21

本文档记录当前本地数据处理、split 和 baseline 输入口径中，影响统计解释和训练边界的关键变更。

## 2026-03-20

### 1. 对齐真实蛋白主表

- `config.yaml` 对齐到真实列名
- `contig_id <- accession`
- `sequence <- protein_sequence`

### 2. 增加 `phrog_annotation -> annot` 桥接

- 在标准化主表阶段通过 `unique_phrog_annotation.tsv` 回填 `annotation_raw`

### 3. 修复 `04_build_long_multilabel_table.py`

- 修复 `NaN -> "nan"` 被误当成有效 secondary label 的问题

### 4. 修复 `05_build_task_datasets.py`

- 修复空 `level1/level2` 被误计入 coarse 任务样本数的问题

## 2026-03-21

### 5. 使用修复源重跑 01-09

权威修复源来自：

- [1genome_protein_context_phrog.txt](D:/data/ai4s/holophage/数据集修复/数据汇总/1genome_protein_context_phrog.txt)
- [PFO_v1_0_2_remapped_729_terms.csv](D:/data/ai4s/holophage/数据集修复/分类原则/PFO_v1_0_2_remapped_729_terms.csv)

### 6. 正式 split 从 `genome_v1` 切换到 `homology_cluster_v1`

实现步骤：

- 全量 `2,543,002` 条蛋白做 exact dedup
- exact unique sequence：`976,210`
- `MMseqs2` 30%/80% homology clustering
- clusters：`222,847`
- 按 `homology_cluster_id` 划分 train/val/test
- 验证结果：`clusters_cross_split = 0`

### 7. 序列模态从实例级重复计算切换到 exact 级复用

正式变更：

- 不再对 `2,543,002` 条蛋白实例逐条重复计算 ProtT5 sequence embedding
- 正式改为只对 `976,210` 个 `exact_sequence_rep_id` 计算 sequence embedding
- 训练样本仍保留全部实例级蛋白
- 上下文和标签仍按实例组织

原因：

- 同一 exact sequence 平均复用 `2.605x`
- 最大 exact 复用组达到 `504x`
- 对 sequence 模态重复计算没有新增信息，但会显著拖慢生成与训练前预处理

### 8. baseline sequence embedding 主键正式切换为 `exact_sequence_rep_id`

- `protein_id` 继续保留给日志和结果导出
- `embedding_id` 继续保留给上下文与实例追溯
- sequence embedding 查询键统一切到 `exact_sequence_rep_id`
- baseline 的 sqlite 索引、prepacked 数据和 dataloader 也同步切换到 exact 口径

### 9. 长序列 embedding 正式从“截断”切换到“滑窗重叠聚合”

- 不再把 `>512 aa` 的蛋白默认截断后直接导出 embedding
- 正式策略改为：
  - `<=512 aa`：整条 ProtT5 编码
  - `>512 aa`：`512 aa` 窗口、`128 aa` 重叠
  - 聚合方式：coverage-weighted mean of window embeddings
- 这样既保留全长信息，又能在当前 8GB 显存硬件上稳定运行
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
