# Context Graph v2 规范

## 1. 目的

本文档定义 `gnn_v2a` context 分支的图资产、pack 字段和模型输入约定，是：

- `tools/build_context_graph_v2.py`
- `baseline/prepack_multimodal.py`
- `baseline/dataset_multimodal.py`
- `baseline/multimodal_v2/model.py`

共享的单一真相。

## 2. 节点模板

- 节点顺序固定：`[-4,-3,-2,-1,0,+1,+2,+3,+4]`
- `max_nodes = 9`
- `center_index = 4`
- 中心节点始终对应 offset `0`

`window=1/2/4` 只改变“允许出现的邻居范围”，节点模板不变。

名义有效节点数：
- `window1 -> 3`
- `window2 -> 5`
- `window4 -> 9`

实际有效节点数允许因 contig 边界而减少，具体由 `node_mask` 表达。

## 3. 节点特征（v2a）

每个节点固定 14 维：

1. `protein_len_norm`
2. `strand_forward`
3. `strand_reverse`
4. `has_phrog`
5. `is_center`
6. `offset_-4`
7. `offset_-3`
8. `offset_-2`
9. `offset_-1`
10. `offset_0`
11. `offset_+1`
12. `offset_+2`
13. `offset_+3`
14. `offset_+4`

默认规则：
- 缺失节点全 0
- `protein_len_norm = min(length / 1000, 1.0)`
- `has_phrog` 延续 `context_features_v1` 的 `phrog_known` 逻辑

这是第一轮的 `node-only relational encoding`；不包含 edge attr，不混 sequence embedding。

## 4. adjacency 规则

图按无向处理。

固定边类型：
- `chain edges`：相邻 offset 之间连边
- `center-star edges`：中心节点与所有有效邻居连边

实现上输出致密 adjacency 矩阵：
- shape：`[9, 9]`
- dtype：`float32`
- 无效节点行列全 0

## 5. node_mask 规则

- shape：`[9]`
- dtype：`bool`
- `true` 表示该 offset 对应真实节点存在
- `false` 表示该 offset 在当前样本中缺失或超出窗口

## 6. 预处理资产字段

每条 `protein_id` 对应一行，至少包含：

- `protein_id`
- `genome_id`
- `contig_id`
- `gene_index`
- `split`
- `split_strategy`
- `split_version`
- `window_size`
- `center_index`
- `num_valid_nodes`
- `node_features_flat`
- `adjacency_flat`
- `node_mask_flat`

其中：
- `node_features_flat` 是按行展开后的 `9 * 14 = 126` 元素
- `adjacency_flat` 是按行展开后的 `9 * 9 = 81` 元素
- `node_mask_flat` 是长度 `9` 的布尔掩码

三者以 JSON 字符串形式写入 parquet，避免不同后端对 list 列的解释差异。

## 7. pack 字段

`gnn_v2a` pack 固定新增：

- `context_mode`
- `context_graph_version`
- `context_node_features`: `[N, 9, 14]`
- `context_adjacency`: `[N, 9, 9]`
- `context_node_mask`: `[N, 9]`
- `context_center_index`: `[N]`

其中：
- `context_mode = "gnn_v2a"`
- `context_graph_version = "context_graph_v2a"`

旧 handcrafted pack 继续保留：
- `context_features`: `[N, 18]`

## 8. 模型输入

`gnn_v2a` 模式下，模型读取：

- `context_node_features`
- `context_adjacency`
- `context_node_mask`
- `context_center_index`

经 2-layer GraphSAGE 编码后取中心节点 embedding，再接现有 context 分支投影。

## 9. 版本命名

第一轮图特征版本固定为：

- `context_graph_features_v2a_window1.parquet`
- `context_graph_features_v2a_window2.parquet`
- `context_graph_features_v2a_window4.parquet`

其中：
- `v2a` 表示 graph version 2 + feature set A

--- 
doc_status: draft
source_of_truth_level: reference
doc_scope: data_pipeline
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
