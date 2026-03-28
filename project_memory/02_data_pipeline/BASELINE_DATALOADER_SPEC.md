# Baseline Dataloader Spec

更新时间：2026-03-21

本文档定义第一轮 baseline 训练时，dataloader 如何组织实例级输入、如何对齐 exact sequence embedding，以及如何构造标签。

## 1. 当前 baseline 范围

第一轮只覆盖：

- `L1 head`
- `L2 head`
- `L3 core head`

暂不纳入：

- multilabel head
- open-set head
- context 主训练
- structure 主训练

## 2. 输入文件

标签主表：

- [training_labels_wide_with_split.csv](D:/data/ai4s/holophage/data_processed/training_labels_wide_with_split.csv)

join 索引：

- [baseline_embedding_join_index.csv](D:/data/ai4s/holophage/data_processed/baseline_embedding_join_index.csv)

sequence embedding：

- [embed_exact](D:/data/ai4s/holophage/embed_exact)

## 3. Join 规则

实例级保留：

- `protein_id`
- `embedding_id = contig_id + "_" + gene_index`

sequence embedding 正式查询键：

- `exact_sequence_rep_id`

禁止再把 `embedding_id` 当成 sequence embedding 主键。

原因：

- 同一 exact sequence 平均对应 `2.605` 个蛋白实例
- 最大 exact 复用组大小为 `504`
- sequence 模态应复用，context 和标签仍按实例保留
- 对于 `>512 aa` 的长序列，sequence embedding 由滑窗重叠聚合得到，而不是简单截断

## 4. 样本筛选规则

第一轮主训练只保留：

- `status == trainable_core`
- `split in {train, val, test}`
- `node_primary` 非空

当前 split 口径：

- `split_strategy = homology_cluster`
- `split_version = homology_cluster_v1`

## 5. Dataset 输出字段

每个实例样本至少输出：

- `protein_id`
- `embedding_id`
- `exact_sequence_rep_id`
- `split`
- `embedding`
- `sequence_length`
- `label_l1`
- `label_l2`
- `label_l3_core`

建议附带：

- `homology_cluster_id`
- `contig_id`
- `gene_index`

## 6. sampler-ready 元数据

online dataset 和 prepacked dataset 都必须携带：

- `homology_cluster_id`
- `exact_sequence_rep_id`

用途：

- `homology_cluster_id` 用于 cluster-aware 采样
- `exact_sequence_rep_id` 用于 exact duplicate 去冗余控权

## 7. 训练与评估

训练集：

- 保留全部实例级 `trainable_core`
- 默认使用 `cluster_exact_balanced`

验证集 / 测试集：

- 不启用 sampler
- 保持全量顺序评估

## 8. 标签来源

- `label_l1 <- level1_label`
- `label_l2 <- level2_label`
- `label_l3_core <- node_primary`

L3 core vocab 只能来自：

- [label_vocab_l3_core.json](D:/data/ai4s/holophage/outputs/label_vocab_l3_core.json)
