# Data Split Policy

更新时间：2026-03-21

本文档定义当前项目的正式数据划分策略，以及如何解释由此得到的训练/验证/测试结果。

## 1. 当前正式策略

当前正式策略不再是 `genome-aware split`，而是：

> `homology-cluster-heldout split (homology_cluster_v1)`

实现步骤：

1. 对全量 `2,543,002` 条蛋白导出 FASTA
2. 使用 `MMseqs2` 做 `100% identity` exact dedup
3. exact dedup 后得到 `976,210` 条唯一序列
4. 对唯一序列使用 `MMseqs2` 做同源聚类：
   - `min_seq_id = 0.3`
   - `coverage = 0.8`
   - `cov_mode = 0`
   - `e-value = 1e-3`
5. 得到 `222,847` 个 homology clusters
6. 以 `homology_cluster_id` 为最小切分单元做 train/val/test 划分

## 2. 当前正式文件

- [split_by_homology_cluster_v1.csv](D:/data/ai4s/holophage/splits/split_by_homology_cluster_v1.csv)
- [training_labels_wide_with_split.csv](D:/data/ai4s/holophage/data_processed/training_labels_wide_with_split.csv)
- [baseline_embedding_join_index.csv](D:/data/ai4s/holophage/data_processed/baseline_embedding_join_index.csv)
- [homology_split_summary.json](D:/data/ai4s/holophage/splits/homology_cluster_v1/homology_split_summary.json)

同源聚类中间与结果资产：

- [protein_to_homology_cluster.tsv](D:/data/ai4s/holophage/splits/homology_cluster_v1/protein_to_homology_cluster.tsv)
- [homology_cluster_stats.tsv](D:/data/ai4s/holophage/splits/homology_cluster_v1/homology_cluster_stats.tsv)
- [mmseqs_exact100_cluster.tsv](D:/data/ai4s/holophage/splits/homology_cluster_v1/mmseqs_exact100_cluster.tsv)
- [mmseqs_homology30_cluster.tsv](D:/data/ai4s/holophage/splits/homology_cluster_v1/mmseqs_homology30_cluster.tsv)

## 3. 当前 split 统计

全量蛋白：

- train: `1,793,622`
- val: `371,592`
- test: `377,788`

监督蛋白总数（非 `open_set`）：

- train: `617,596`
- val: `141,330`
- test: `136,964`

严格泄露检查：

- `clusters_cross_split = 0`

这意味着：

- 同一个 `homology_cluster_id` 不会同时出现在多个 split
- 当前评估已经避免了跨 split 的同源 cluster 泄露

## 4. 与旧策略的区别

旧策略 `genome_v1` 的优点是避免 genome 内邻域泄露，但仍允许：

- 不同 genome 之间的高同源蛋白落入不同 split
- 测试集出现训练集的近同源蛋白
- 指标对真实泛化能力偏乐观

当前 `homology_cluster_v1` 的改进点是：

- 以同源 cluster 为最小切分单元
- 直接堵住同源 cluster 跨 split 的泄露路径

## 5. 当前策略的解释边界

当前结果可以解释为：

> 对 `homology-cluster-heldout` 场景的泛化评估

但仍需注意：

- 这不是按 genome 分层的 context 评估
- 如果未来引入显式邻域/context 模态，还需要额外检查 cluster split 下的 context 缓存构造是否 split-aware

## 6. 为什么这次要全量 254 万蛋白一起聚类

本次不是只聚类监督子集，而是把全量蛋白都纳入聚类空间。原因是：

- 如果只聚类监督子集，未标注蛋白可能充当“桥接序列”，导致真实同源关系被截断
- 全量聚类能更完整地反映全局序列空间
- 这样再把监督样本投影回 cluster，泄露控制更严格

## 7. 训练时如何使用

当前 baseline 仍按既定边界训练：

- `L1 + L2 + L3 core`
- 首轮主头只使用 `status == trainable_core`

但 split 一律以新字段为准：

- `split`
- `split_strategy = homology_cluster`
- `split_version = homology_cluster_v1`

## 8. 历史文件处理

`split_by_genome_v1.csv` 不再是当前正式 split，只能视作历史版本。

如果仍需保留，必须放入归档语境中解释，不能再作为当前训练输入默认引用。
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
