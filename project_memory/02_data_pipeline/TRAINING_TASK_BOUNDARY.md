# Training Task Boundary

更新时间：2026-03-21

本文档定义当前 `PFO v1.0.2` 数据产物中，哪些字段可以直接进入训练头，哪些字段不能误用。

## 1. 最重要的规则

`node_primary` 是主映射字段，不是“统一 L3 标签空间”。

它表示的是：

> 当前样本最主要落到哪个节点

这个节点可能是：

- `trainable_core` 叶子
- `trainable_multilabel` 叶子
- `parent_only` scaffold 节点
- `defer` 宽节点

因此：

- 不能直接从 `training_labels_wide_with_split.csv["node_primary"]` 的全量唯一值构造 L3 vocab

## 2. 各训练任务的合法来源

### L1

- 来源：`dataset_l1.csv`
- 标签字段：`level1_label`

### L2

- 来源：`dataset_l2.csv`
- 标签字段：`level2_label`

### L3 core

- 来源：`dataset_l3_core.csv`
- 筛选条件：`status == trainable_core`
- 标签字段：`node_primary`

### L3 multilabel

- 来源：`dataset_l3_multilabel.csv`
- 筛选条件：`status == trainable_multilabel`
- 标签字段：
  - primary：`node_primary`
  - secondary：`secondary_node`

### open-set / reject / abstain

- 来源：`dataset_open_set.csv`
- 筛选条件：`status == open_set`

## 3. 第一轮 baseline 的边界

第一轮只做：

- `L1`
- `L2`
- `L3 core`

第一轮不做：

- `L3 multilabel`
- `open-set`
- `context`

## 4. 当前 split 口径

当前正式 split 已切换为：

- `split_strategy = homology_cluster`
- `split_version = homology_cluster_v1`

这影响的是样本如何划分到 train/val/test，但不改变训练任务边界本身。

## 5. 当前已知提醒

- `open_set` 占比高，主要由原始 annotation 缺失驱动，不等于 mapping 崩溃
- `parent_only` 不进入 L3 主头
- `trainable_multilabel` 只在第二轮再接入
- `node_primary` 不能被误当成全量 L3 叶子标签列
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
