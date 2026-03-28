# holophage

更新时间：2026-03-27

当前项目已经完成：

- `PFO v1.0.2` 标签预处理主链
- `homology_cluster_v1` 无同源穿透 split
- `exact_sequence_rep_id` 级 sequence embedding 主键切换
- 长序列 `>512 aa` 的滑窗重叠聚合策略
- 结构检索链与结构缺口清单骨架

## 当前单一真相

- 正式 ontology / 标签版本：`PFO v1.0.2`
- 正式 split：`homology_cluster_v1`
- 正式 sequence embedding 主键：`exact_sequence_rep_id`
- embedding 相关代码、输入、模型、输出、日志统一收口到：
  - [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)
- baseline 训练代码在：
  - [baseline](D:/data/ai4s/holophage/baseline)
- 结构链在：
  - [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline)

## 5 分钟快速上手

1. [项目总览](D:/data/ai4s/holophage/project_memory/00_index/PROJECT_OVERVIEW_zh.md)
2. [训练输入清单](D:/data/ai4s/holophage/project_memory/02_data_pipeline/BASELINE_INPUT_MANIFEST.md)
3. [训练边界](D:/data/ai4s/holophage/project_memory/02_data_pipeline/TRAINING_TASK_BOUNDARY.md)
4. [数据切分策略](D:/data/ai4s/holophage/project_memory/02_data_pipeline/DATA_SPLIT_POLICY.md)
5. [embedding 流水线说明](D:/data/ai4s/holophage/embedding_pipeline/README.md)
6. [结构回收链说明](D:/data/ai4s/holophage/project_memory/02_data_pipeline/STRUCTURE_RETRIEVAL_PIPELINE.md)

## 当前正式产物

- [training_labels_wide_with_split.csv](D:/data/ai4s/holophage/data_processed/training_labels_wide_with_split.csv)
- [baseline_embedding_join_index.csv](D:/data/ai4s/holophage/data_processed/baseline_embedding_join_index.csv)
- [split_by_homology_cluster_v1.csv](D:/data/ai4s/holophage/splits/split_by_homology_cluster_v1.csv)
- [exact_sequence_embedding_input.parquet](D:/data/ai4s/holophage/embedding_pipeline/inputs/exact_sequence_embedding_input.parquet)
- [embed_exact](D:/data/ai4s/holophage/embedding_pipeline/outputs/embed_exact)

## 当前规模摘要

- 实例级蛋白总数：`2,543,002`
- exact unique sequence：`976,210`
- homology clusters：`222,847`
- `trainable_core` 实例数：`426,351`
- `trainable_core` exact unique sequence：`173,866`

## 当前 embedding / 结构口径

- 第一轮 baseline 先做 `L1 + L2 + L3 core`
- sequence 模态按 `exact_sequence_rep_id` 对齐
- 结构模态当前更推荐走“sequence-derived structural embedding”，而不是强依赖真实 PDB
- 现有真实结构资产仍保留在结构链里作为可选增强资产，不再阻塞 baseline

## 目录说明

- `embedding_pipeline/`：embedding 相关脚本、输入、模型、输出、日志、清单
- `baseline/`：baseline 训练代码
- `structure_pipeline/`：结构盘点、命中筛查、下载脚本
- `structures/`：结构 manifest、缓存与下载结果
- `project_memory/`：项目记忆、规范与交接文档
- `data_processed/`：当前正式训练输入
- `outputs/`：统计报告和 vocab
- `splits/`：正式 split 与同源聚类产物
- `project_memory/05_archive/`：历史归档，不作为当前正式输入
---
doc_status: active
source_of_truth_level: canonical
doc_scope: repo_root
owner_path: .
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

## Current Baseline Runtime Mainline

当前 baseline runtime 主线只包括：

- [baseline](D:/data/ai4s/holophage/baseline)
- [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)
- [data_processed](D:/data/ai4s/holophage/data_processed)
- [outputs](D:/data/ai4s/holophage/outputs)
- [splits](D:/data/ai4s/holophage/splits)
- [project_memory/04_active_assets](D:/data/ai4s/holophage/project_memory/04_active_assets)

当前 baseline 仍然是：

- sequence-first
- `L1 + L2 + L3 core`
- `target_status = trainable_core`

## Support / Reference Branches

下面这些内容当前不是 baseline runtime 主线，应按 support / reference 理解：

- [SaProt-1.3B_emb](D:/data/ai4s/holophage/SaProt-1.3B_emb)
- [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline)
- [structures](D:/data/ai4s/holophage/structures)
- planning / changelog / schema / policy 类文档

读取顺序上，先看 active manifest，再看参考文档，不要反过来。
