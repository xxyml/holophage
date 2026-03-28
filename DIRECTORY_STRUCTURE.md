# 目录结构说明

更新时间：2026-03-28

本文档记录 [holophage](D:/data/ai4s/holophage) 当前目录结构，并标注：

- 哪些目录是**正式主线**
- 哪些目录是**支撑资产**
- 哪些目录更偏**交接、历史、辅助或临时**

目标不是机械列出所有文件，而是让后续接手的人能快速理解：

- 该先看哪里
- 训练主线在哪里
- embedding 主线在哪里
- ontology / split / 统计文档在哪里

---

## 1. 根目录总览

```text
D:\data\ai4s\holophage
├─ README.md
├─ PROJECT_ONBOARDING_FOR_AI.md
├─ DIRECTORY_STRUCTURE.md
├─ baseline/
├─ embedding_pipeline/
├─ SaProt-1.3B_emb/
├─ data_processed/
├─ outputs/
├─ splits/
├─ project_memory/
├─ AI_HANDOFF_PACKAGE/
├─ dataset_pipeline_portable/
├─ data_intermediate/
├─ structure_pipeline/
├─ structures/
├─ gpt生成/
├─ logs/
├─ models/
├─ outputs/
├─ paper/
├─ pfo_local_pipeline_scripts/
├─ root/
├─ tmp/
└─ 数据集修复/
```

其中最重要的主线目录是：

- [baseline](D:/data/ai4s/holophage/baseline)
- [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)
- [SaProt-1.3B_emb](D:/data/ai4s/holophage/SaProt-1.3B_emb)
- [data_processed](D:/data/ai4s/holophage/data_processed)
- [outputs](D:/data/ai4s/holophage/outputs)
- [splits](D:/data/ai4s/holophage/splits)
- [project_memory](D:/data/ai4s/holophage/project_memory)

当前“机器可读的唯一真相”入口位于：

- [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
- [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)

---

## 2. 正式主线目录

### 2.1 [baseline](D:/data/ai4s/holophage/baseline)

当前 sequence-first baseline 的核心代码目录。

```text
baseline/
├─ README.md
├─ environment.md
├─ train.py
├─ evaluate.py
├─ model.py
├─ losses.py
├─ samplers.py
├─ dataset.py
├─ prepacked_dataset.py
├─ prepack_embeddings.py
├─ build_embedding_index.py
├─ embedding_store.py
├─ common.py
├─ train_config.yaml
├─ train_config.full_stage2.yaml
├─ train_config.subset_stagecheck.yaml
├─ train_config.subset_8g.yaml
├─ train_config.embed_restart.yaml
├─ run_post_train_eval.ps1
├─ artifacts/
└─ runs/
```

说明：

- [README.md](D:/data/ai4s/holophage/baseline/README.md)：当前 baseline 训练边界与正式口径
- [train.py](D:/data/ai4s/holophage/baseline/train.py)：训练入口
- [model.py](D:/data/ai4s/holophage/baseline/model.py)：当前 baseline 模型结构
- [losses.py](D:/data/ai4s/holophage/baseline/losses.py)：当前损失函数
- [samplers.py](D:/data/ai4s/holophage/baseline/samplers.py)：cluster-aware / exact-aware 采样
- `artifacts/`：索引、prepacked 等训练产物
- `runs/`：训练实验输出

当前这条线的定位是：

- sequence-only
- trainable_core-only
- 第一轮稳定对照基线

---

### 2.2 [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)

当前正式 sequence embedding 主线，核心是 exact-sequence 级 ProtT5 embedding。

```text
embedding_pipeline/
├─ README.md
├─ inputs/
│  ├─ exact_sequence_embedding_input.parquet
│  └─ 1genome_cds_embedding_input.parquet
├─ scripts/
│  ├─ extract_prott5_embeddings.py
│  ├─ rebuild_exact_sequence_embedding_input.py
│  ├─ rebuild_embedding_input_parquet.py
│  └─ download_prott5_safetensors.py
├─ models/
├─ outputs/
├─ logs/
└─ manifests/
```

说明：

- [exact_sequence_embedding_input.parquet](D:/data/ai4s/holophage/embedding_pipeline/inputs/exact_sequence_embedding_input.parquet)：当前正式输入
- [extract_prott5_embeddings.py](D:/data/ai4s/holophage/embedding_pipeline/scripts/extract_prott5_embeddings.py)：ProtT5 embedding 生成脚本
- `models/`：ProtT5 模型目录
- `outputs/`：正式 sequence embedding shard 输出
- `manifests/`：与 embedding 相关的索引或删除候选清单

注意：

- 当前正式 sequence embedding 主键是 `exact_sequence_rep_id`
- 这条线是 baseline 当前真正依赖的 embedding 主线

---

### 2.3 [SaProt-1.3B_emb](D:/data/ai4s/holophage/SaProt-1.3B_emb)

当前结构感知 embedding 新主线，使用 SaProt-1.3B AA-only 模式。

```text
SaProt-1.3B_emb/
├─ README.md
├─ environment.md
├─ inputs/
├─ scripts/
│  ├─ download_saprot_model.py
│  └─ extract_saprot_embeddings.py
├─ models/
│  └─ SaProt_1.3B_AF2/
├─ outputs/
│  └─ embed_exact/
├─ manifests/
├─ logs/
└─ ...
```

说明：

- [README.md](D:/data/ai4s/holophage/SaProt-1.3B_emb/README.md)：SaProt 结构感知 embedding 说明
- [extract_saprot_embeddings.py](D:/data/ai4s/holophage/SaProt-1.3B_emb/scripts/extract_saprot_embeddings.py)：SaProt embedding 生成脚本
- `models/SaProt_1.3B_AF2/`：本地 SaProt 模型
- `outputs/embed_exact/`：结构感知 embedding 输出
- `manifests/`：`progress.json`、`schema.json`、`summary.json`

这条线目前是：

- 不依赖真实 `PDB/CIF`
- 作为未来多模态 baseline 的 structure-like branch

---

### 2.4 [data_processed](D:/data/ai4s/holophage/data_processed)

当前正式训练表和任务级数据表所在目录。

```text
data_processed/
├─ training_labels_wide_with_split.csv
├─ training_labels_wide.csv
├─ training_labels_long.csv
├─ baseline_embedding_join_index.csv
├─ dataset_l1.csv
├─ dataset_l2.csv
├─ dataset_l3_core.csv
├─ dataset_l3_multilabel.csv
├─ dataset_parent_only.csv
├─ dataset_defer.csv
└─ dataset_open_set.csv
```

说明：

- [training_labels_wide_with_split.csv](D:/data/ai4s/holophage/data_processed/training_labels_wide_with_split.csv)：当前正式主表
- [baseline_embedding_join_index.csv](D:/data/ai4s/holophage/data_processed/baseline_embedding_join_index.csv)：baseline join 索引
- 各 `dataset_*.csv`：按训练任务拆分后的任务级表

这是你后续统计、训练、错误分析最常引用的数据目录。

---

### 2.5 [outputs](D:/data/ai4s/holophage/outputs)

当前正式 label vocab 与训练统计目录。

```text
outputs/
├─ label_vocab_l1.json
├─ label_vocab_l2.json
├─ label_vocab_l3_core.json
├─ label_vocab_l3_multilabel.json
└─ training_statistics.md
```

说明：

- [label_vocab_l2.json](D:/data/ai4s/holophage/outputs/label_vocab_l2.json)：当前正式 L2 vocab，**21 类**
- [training_statistics.md](D:/data/ai4s/holophage/outputs/training_statistics.md)：当前数据分布统计

---

### 2.6 [splits](D:/data/ai4s/holophage/splits)

当前正式 split 产物目录。

```text
splits/
├─ split_by_homology_cluster_v1.csv
└─ homology_cluster_v1/
   ├─ all_proteins.fasta
   ├─ all_proteins_summary.json
   ├─ homology_cluster_stats.tsv
   ├─ homology_membership_summary.json
   ├─ homology_split_summary.json
   ├─ protein_to_homology_cluster.tsv
   ├─ mmseqs_exact100_cluster.tsv
   ├─ mmseqs_homology30_cluster.tsv
   ├─ mmseqs_exact100_all_seqs.fasta
   ├─ mmseqs_exact100_rep_seq.fasta
   ├─ mmseqs_homology30_all_seqs.fasta
   ├─ mmseqs_homology30_rep_seq.fasta
   ├─ tmp_exact100/
   └─ tmp_homology30/
```

说明：

- [split_by_homology_cluster_v1.csv](D:/data/ai4s/holophage/splits/split_by_homology_cluster_v1.csv)：当前正式 split
- `protein_to_homology_cluster.tsv`：蛋白到 cluster 的映射
- `homology_split_summary.json`：正式 split 摘要

当前正式口径是：

- `split_strategy = homology_cluster`
- `split_version = homology_cluster_v1`

---

### 2.7 [project_memory](D:/data/ai4s/holophage/project_memory)

项目文档与决策存档目录。

```text
project_memory/
├─ README.md
├─ 00_index/
├─ 01_ontology_spec/
├─ 02_data_pipeline/
├─ 03_tracking_tables/
├─ 04_active_assets/
└─ 05_archive/
```

必要展开：

```text
project_memory/00_index/
├─ PROJECT_OVERVIEW_zh.md
├─ FILE_INDEX.md
├─ DECISION_LOG_zh.md
├─ NEXT_ACTIONS_PLAN.md
└─ THINKING_SUMMARY_FOR_HANDOFF_zh.md

project_memory/01_ontology_spec/
├─ ONTOLOGY_SPEC_PFO_v1_0_2.md
├─ TRAINING_LABEL_POLICY.md
├─ MULTILABEL_POLICY.md
├─ MAPPING_POLICY.md
├─ MODEL_DESIGN_BLUEPRINT.md
└─ OPEN_QUESTIONS_AND_RISKS.md

project_memory/02_data_pipeline/
├─ BASELINE_DATALOADER_SPEC.md
├─ BASELINE_EXECUTION_PLAN.md
├─ BASELINE_INPUT_MANIFEST.md
├─ BASELINE_MODALITY_ASSETS.md
├─ DATA_PROCESSING_SPEC.md
├─ DATA_SPLIT_POLICY.md
├─ MODEL_TRAINING_PLAN.md
├─ PROCESSING_CHANGELOG.md
├─ TRAINING_DATA_SCHEMA.md
├─ TRAINING_TASK_BOUNDARY.md
├─ STRUCTURE_RETRIEVAL_PIPELINE.md
└─ STRUCTURE_FULL_COVERAGE_PLAN.md
```

此外，当前 active runtime contract 以这两份 manifest 为准：

- [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
- [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)

说明：

- `00_index/`：项目总览与导航
- `01_ontology_spec/`：ontology、标签策略、设计规则
- `02_data_pipeline/`：训练输入、split、baseline、变更记录
- `04_active_assets/`：当前活跃交付资产
- `05_archive/`：历史归档，不建议删

如果要快速理解项目，优先看：

- [PROJECT_ONBOARDING_FOR_AI.md](D:/data/ai4s/holophage/PROJECT_ONBOARDING_FOR_AI.md)
- [PROJECT_OVERVIEW_zh.md](D:/data/ai4s/holophage/project_memory/00_index/PROJECT_OVERVIEW_zh.md)
- [BASELINE_INPUT_MANIFEST.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/BASELINE_INPUT_MANIFEST.md)
- [TRAINING_DATA_SCHEMA.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/TRAINING_DATA_SCHEMA.md)
- [TRAINING_TASK_BOUNDARY.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/TRAINING_TASK_BOUNDARY.md)
- [MODEL_TRAINING_PLAN.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/MODEL_TRAINING_PLAN.md)

---

## 3. 交接与辅助目录

### 3.1 [AI_HANDOFF_PACKAGE](D:/data/ai4s/holophage/AI_HANDOFF_PACKAGE)

给外部 AI / 外部工程师的精简交接包。

```text
AI_HANDOFF_PACKAGE/
├─ 00_START_HERE.md
├─ 01_MODEL_ONTOLOGY_DATA_BRIEF.md
├─ PROJECT_ONBOARDING_FOR_AI.md
├─ README.md
├─ baseline/
├─ docs/
├─ embedding_pipeline/
├─ SaProt-1.3B_emb/
└─ structure_pipeline/
```

说明：

- 这是**副本目录**
- 不影响本地真实运行
- 文件数经过裁剪，适合上传给不在本机的新 AI

---

### 3.2 [dataset_pipeline_portable](D:/data/ai4s/holophage/dataset_pipeline_portable)

更偏原始数据整理和可移植数据管线，不是当前 baseline 训练主入口，但仍有追溯价值。

---

### 3.3 [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline) 与 [structures](D:/data/ai4s/holophage/structures)

真实结构检索与结构资产管理尝试所用目录。

当前项目主线已转向：

- sequence embedding
- SaProt 结构感知 embedding

因此这两块目前更偏：

- 可选增强
- 历史探索
- 后续结构资产回收管线

不是当前 baseline 的硬依赖。

---

## 4. 历史、辅助或次要目录

下面这些目录目前不是训练主线核心，但保留有意义：

- [data_intermediate](D:/data/ai4s/holophage/data_intermediate)
  - 中间处理产物
- [gpt生成](D:/data/ai4s/holophage/gpt生成)
  - ontology / 表格历史生成目录
- [logs](D:/data/ai4s/holophage/logs)
  - 运行日志
- [models](D:/data/ai4s/holophage/models)
  - 根目录旧模型缓存或遗留目录
- [paper](D:/data/ai4s/holophage/paper)
  - 论文与参考材料
- [pfo_local_pipeline_scripts](D:/data/ai4s/holophage/pfo_local_pipeline_scripts)
  - 本地脚本集合
- [root](D:/data/ai4s/holophage/root)
  - 辅助目录
- [tmp](D:/data/ai4s/holophage/tmp)
  - 临时文件
- [数据集修复](D:/data/ai4s/holophage/数据集修复)
  - 数据修复历史材料

这些目录不一定要删，但也不应和正式训练主线混淆。

---

## 5. 现在最应该看的目录

如果目标是继续训练或扩展 baseline，建议优先只看这几块：

1. [baseline](D:/data/ai4s/holophage/baseline)
2. [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)
3. [SaProt-1.3B_emb](D:/data/ai4s/holophage/SaProt-1.3B_emb)
4. [data_processed](D:/data/ai4s/holophage/data_processed)
5. [outputs](D:/data/ai4s/holophage/outputs)
6. [splits](D:/data/ai4s/holophage/splits)
7. [project_memory](D:/data/ai4s/holophage/project_memory)

如果目标是给新 AI 交接，再看：

8. [AI_HANDOFF_PACKAGE](D:/data/ai4s/holophage/AI_HANDOFF_PACKAGE)

---

## 6. 一句话总结

这个仓库当前的真正主线是：

> **`data_processed + splits + outputs + embedding_pipeline + baseline + project_memory`**

而 `SaProt-1.3B_emb` 是正在建设中的结构感知 embedding 分支；  
其余目录大多是支撑、交接、历史或探索性资产。
---
doc_status: active
source_of_truth_level: canonical
doc_scope: directory_guide
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

## Runtime Layering

为避免新接手者把“能看见的目录”误当成“当前 runtime 主线”，这里补充一层正式分层：

### active runtime mainline

- [baseline](D:/data/ai4s/holophage/baseline)
- [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)
- [data_processed](D:/data/ai4s/holophage/data_processed)
- [outputs](D:/data/ai4s/holophage/outputs)
- [splits](D:/data/ai4s/holophage/splits)
- [project_memory/04_active_assets](D:/data/ai4s/holophage/project_memory/04_active_assets)

### support / reference

- [SaProt-1.3B_emb](D:/data/ai4s/holophage/SaProt-1.3B_emb)
- [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline)
- [structures](D:/data/ai4s/holophage/structures)
- [AI_HANDOFF_PACKAGE](D:/data/ai4s/holophage/AI_HANDOFF_PACKAGE)
- planning / changelog / schema / policy 文档

也就是说，当前 baseline 还不是“多模态全开”的运行状态；结构侧和 roadmap 仍然属于 support/reference 层。
