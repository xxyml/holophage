# AI 项目上手文档

更新时间：2026-03-28

这份文档面向第一次接触本项目的 AI 或新工程师。目标不是罗列所有文件，而是快速建立**正确的项目心智模型**，知道：

- 项目到底在做什么
- 当前哪些数据和文档是“正式版本”
- baseline 现在做到哪一步
- embedding / split / 标签的正式口径是什么
- 后续接手时最容易踩的坑是什么

---

## 1. 项目一句话概述

这个项目在做：

> **面向噬菌体蛋白功能预测的多模态训练框架**，其中 ontology 为 `PFO v1.0.2`，当前第一轮 baseline 先从 **sequence embedding** 出发，训练 `L1 + L2 + L3 core` 三头分类模型。

当前项目的设计原则不是“先把 ontology 做到完美再训练”，而是：

> **先冻结一个稳定可执行版本，跑出第一轮模型，再用模型表现反向修正 ontology 和训练设计。**

项目总入口：
- [README.md](D:/data/ai4s/holophage/README.md)

更完整的项目背景和设计思想：
- [PROJECT_OVERVIEW_zh.md](D:/data/ai4s/holophage/project_memory/00_index/PROJECT_OVERVIEW_zh.md)

---

## 2. 当前单一真相（Single Source of Truth）

当前主线已经统一到以下口径，后续所有分析、训练、评估都应以这些定义为准：

- 正式 ontology / 标签版本：`PFO v1.0.2`
- 正式 split：`homology_cluster_v1`
- 正式 sequence embedding 主键：`exact_sequence_rep_id`
- 正式 baseline 第一轮任务：`L1 + L2 + L3 core`
- 当前 sequence embedding 资产目录：
  - [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)
- 当前 baseline 训练代码目录：
  - [baseline](D:/data/ai4s/holophage/baseline)
- 当前结构侧新主线：
  - [SaProt-1.3B_emb](D:/data/ai4s/holophage/SaProt-1.3B_emb)

不要再把下面这些当作当前正式口径：

- 旧的 `genome_v1` split
- 旧的 `embedding_id = contig_id + "_" + gene_index` 作为 sequence embedding 主键
- 旧的“按 protein 实例重复计算 sequence embedding”的方案
- 依赖真实 `PDB/CIF` 才能跑通 baseline 的结构模态设计

---

### 2.1 当前最需要记住的收紧点

当前最重要的一条 single source of truth 修正是：

- **L2 正式训练 vocab = 21 类**

这个数字必须与：

- [ONTOLOGY_SPEC_PFO_v1_0_2.md](D:/data/ai4s/holophage/project_memory/01_ontology_spec/ONTOLOGY_SPEC_PFO_v1_0_2.md)
- [label_vocab_l2.json](D:/data/ai4s/holophage/outputs/label_vocab_l2.json)
- [training_statistics.md](D:/data/ai4s/holophage/project_memory/04_active_assets/model_dev_transfer_package/outputs/training_statistics.md)
- [baseline/README.md](D:/data/ai4s/holophage/baseline/README.md)

保持一致。

另外，当前评估与训练解释应统一为：

- `split_strategy = homology_cluster`
- `split_version = homology_cluster_v1`

不再沿用旧的 genome-aware / genome-heldout 口径。

当前推荐优先读取的机器可读 manifest：

- [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
- [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)

---

## 3. 当前正式数据资产

### 3.1 主训练表

正式主表：
- [training_labels_wide_with_split.csv](D:/data/ai4s/holophage/data_processed/training_labels_wide_with_split.csv)

这张表是当前训练数据的主入口，至少需要理解这些字段：

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

### 3.2 baseline join 索引

正式 join 索引：
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

注意：

- `embedding_id` 现在主要保留给日志/debug，不再是 sequence embedding 主键
- `sequence_embedding_key` 当前应等于 `exact_sequence_rep_id`

### 3.3 vocab

- [label_vocab_l1.json](D:/data/ai4s/holophage/outputs/label_vocab_l1.json)
- [label_vocab_l2.json](D:/data/ai4s/holophage/outputs/label_vocab_l2.json)
- [label_vocab_l3_core.json](D:/data/ai4s/holophage/outputs/label_vocab_l3_core.json)

### 3.4 split 文件

- [split_by_homology_cluster_v1.csv](D:/data/ai4s/holophage/splits/split_by_homology_cluster_v1.csv)
- [homology_split_summary.json](D:/data/ai4s/holophage/splits/homology_cluster_v1/homology_split_summary.json)

---

## 4. 数据规模与当前训练边界

当前项目中最重要的几个数字：

- 蛋白实例总数：`2,543,002`
- exact unique sequence：`976,210`
- homology clusters：`222,847`
- `trainable_core` 实例数：`426,351`
- `trainable_core` exact unique sequence：`173,866`

### 为什么有两个规模：97.6 万 和 17.4 万

- `976,210` 是**全库 exact unique sequence**
- `173,866` 是当前第一轮主任务 `trainable_core` 对应的 exact unique sequence

所以：

- 如果讨论 **全量 embedding 生成**，通常看 `976,210`
- 如果讨论 **第一轮 core 训练任务**，通常看 `173,866`

### 当前第一轮 baseline 明确不做的事

当前 baseline 第一轮只做：

- `L1`
- `L2`
- `L3 core`

不做：

- `trainable_multilabel`
- `open_set`
- `parent_only`
- 真实结构文件主训练
- 上下文模态主训练

边界文档：
- [TRAINING_TASK_BOUNDARY.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/TRAINING_TASK_BOUNDARY.md)

---

## 5. split 策略与泄露控制

当前正式 split 不再是 genome-aware，而是：

> `homology_cluster_v1`

含义：

- 先对全量 `2,543,002` 条蛋白做 exact dedup
- 再对 `976,210` 条 unique sequence 做同源聚类
- 再按 `homology_cluster_id` 划分 train / val / test

这样做的目的，是**避免同源泄露**。

当前需要记住的关键事实：

- `clusters_cross_split = 0`
- 也就是同一 `homology_cluster_id` 不会同时出现在多个 split

正式策略说明：
- [DATA_SPLIT_POLICY.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/DATA_SPLIT_POLICY.md)

相关 split 中间产物：

- [protein_to_homology_cluster.tsv](D:/data/ai4s/holophage/splits/homology_cluster_v1/protein_to_homology_cluster.tsv)
- [homology_cluster_stats.tsv](D:/data/ai4s/holophage/splits/homology_cluster_v1/homology_cluster_stats.tsv)
- [mmseqs_exact100_cluster.tsv](D:/data/ai4s/holophage/splits/homology_cluster_v1/mmseqs_exact100_cluster.tsv)
- [mmseqs_homology30_cluster.tsv](D:/data/ai4s/holophage/splits/homology_cluster_v1/mmseqs_homology30_cluster.tsv)

---

## 6. 标签体系应该怎么理解

项目的 ontology 基础是 `PFO v1.0.2`，但训练边界不是直接从全量 `node_primary` 平铺得到的。

最重要的理解是：

> `node_primary` 是主映射字段，不等于“可以直接作为全量 L3 分类空间的唯一来源”。

原因：

- `node_primary` 可能落到：
  - `trainable_core`
  - `trainable_multilabel`
  - `parent_only`
  - `defer`
  - `open_set`

所以第一轮 L3 主头只能从：

- `status == trainable_core`

这部分去定义。

建议必读：

- [PROJECT_OVERVIEW_zh.md](D:/data/ai4s/holophage/project_memory/00_index/PROJECT_OVERVIEW_zh.md)
- [TRAINING_TASK_BOUNDARY.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/TRAINING_TASK_BOUNDARY.md)

---

## 6.1 后续开发优先级

如果新 AI 要继续推进模型系统，默认优先级应是：

1. 先收紧 single source of truth
   - 锁死 L2 = 21 类
   - 清理旧 genome-aware 表述
2. 保留当前 sequence-only core baseline
   - 它是永久对照组
3. 先扩 coarse supervision
   - 把 `parent_only + trainable_multilabel` 正式纳入 `L1/L2`
4. 再加独立 multilabel head
   - 不把 multilabel 节点并进 core softmax
5. 最后再做 open-set 与 context branch

也就是说，下一步真正优先补的是 **status-aware supervision routing**，不是更复杂的 backbone。

---

## 7. sequence embedding 当前正式主线

sequence embedding 现在已经统一整理到：

- [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)

正式输入：
- [exact_sequence_embedding_input.parquet](D:/data/ai4s/holophage/embedding_pipeline/inputs/exact_sequence_embedding_input.parquet)

正式输出：
- [embed_exact](D:/data/ai4s/holophage/embedding_pipeline/outputs/embed_exact)

### 当前 sequence embedding 的正式口径

- 主键：`exact_sequence_rep_id`
- 不是按 protein 实例重复生成
- 长序列策略：
  - `<=512 aa`：整条编码
  - `>512 aa`：滑窗重叠后聚合

这样做的原因是：

- 完全相同的序列不需要重复算 embedding
- 训练样本仍按 protein 实例保留
- embedding 只在 exact 层复用

embedding 流水线说明：
- [embedding_pipeline/README.md](D:/data/ai4s/holophage/embedding_pipeline/README.md)

---

## 8. SaProt 结构感知 embedding 当前主线

真实结构文件链仍然保留，但当前更推荐的结构模态方向是：

> **sequence-derived structural embedding**

也就是：

- 不强依赖真实 `PDB/CIF`
- 直接从序列生成结构感知 embedding

当前新主线已经放在：
- [SaProt-1.3B_emb](D:/data/ai4s/holophage/SaProt-1.3B_emb)

当前正式设定：

- 模型：`SaProt-1.3B`
- 模式：`AA-only`
- 输出粒度：蛋白级 pooled embedding
- 默认 batch：`4`
- 长序列策略：
  - `<=1024 aa`：整条编码
  - `>1024 aa`：滑窗重叠聚合

相关文档：

- [SaProt-1.3B_emb/README.md](D:/data/ai4s/holophage/SaProt-1.3B_emb/README.md)
- [environment.md](D:/data/ai4s/holophage/SaProt-1.3B_emb/environment.md)

说明：

- 这条线是“结构感知模态”的当前推荐实现
- 它不会替代 sequence branch
- 更像是后续多模态 baseline 的第二分支

---

## 9. baseline 当前实现现状

baseline 代码在：
- [baseline](D:/data/ai4s/holophage/baseline)

核心入口：

- [train.py](D:/data/ai4s/holophage/baseline/train.py)
- [model.py](D:/data/ai4s/holophage/baseline/model.py)
- [losses.py](D:/data/ai4s/holophage/baseline/losses.py)
- [dataset.py](D:/data/ai4s/holophage/baseline/dataset.py)
- [samplers.py](D:/data/ai4s/holophage/baseline/samplers.py)

当前 baseline 的重要事实：

- 第一轮还是 sequence-only 主线
- 训练样本按实例保留
- sequence embedding 按 `exact_sequence_rep_id` 回填
- 采样默认是：
  - `cluster_exact_balanced`

当前正式训练配置：
- [train_config.full_stage2.yaml](D:/data/ai4s/holophage/baseline/train_config.full_stage2.yaml)

配置里当前最重要的口径：

- `embedding_dir = embedding_pipeline/outputs/embed_exact`
- `embedding_index_db = baseline/artifacts/embedding_index_exact.sqlite`
- `split_strategy = homology_cluster`
- sampler 已启用 `cluster_exact_balanced`

baseline README：
- [baseline/README.md](D:/data/ai4s/holophage/baseline/README.md)

---

## 10. 结构文件链当前怎么理解

真实结构链仍在仓库中保留，但它现在不再是 baseline 的主阻塞项。

结构回收与相关资产在：

- [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline)
- [structures](D:/data/ai4s/holophage/structures)

应该这样理解：

- 真实结构资产现在更像：
  - 可选增强资产
  - 验证资产
  - 后续分析资产
- 当前 baseline 主线已经不再要求：
  - “必须先有完整 PDB/CIF 才能训练”

结构链文档：

- [STRUCTURE_RETRIEVAL_PIPELINE.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/STRUCTURE_RETRIEVAL_PIPELINE.md)
- [STRUCTURE_FULL_COVERAGE_PLAN.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/STRUCTURE_FULL_COVERAGE_PLAN.md)

---

## 11. 新 AI 最容易误解的点

### 11.1 `embedding_id` 不是当前 sequence embedding 主键

现在应该用：

- `exact_sequence_rep_id`

### 11.2 `node_primary` 不是全量 L3 vocab 的直接来源

当前第一轮 L3 主头只能看：

- `status == trainable_core`

### 11.3 97.6 万和 17.4 万不是矛盾

- `976,210`：全库 exact unique sequence
- `173,866`：`trainable_core` 对应的 exact unique sequence

### 11.4 split 已经切换到 homology-cluster-heldout

不要再默认使用旧的 genome-aware 解释方式。

### 11.5 当前 baseline 不是多模态全开

现在更准确的状态是：

- ontology / 数据 / split 已经整理好
- sequence baseline 已有骨架
- structure-aware embedding（SaProt）正在独立收口
- 真正的多模态融合还没有最终定版

---

## 12. 推荐阅读顺序

### 5 分钟快速上手

1. [README.md](D:/data/ai4s/holophage/README.md)
2. [BASELINE_INPUT_MANIFEST.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/BASELINE_INPUT_MANIFEST.md)
3. [TRAINING_TASK_BOUNDARY.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/TRAINING_TASK_BOUNDARY.md)
4. [DATA_SPLIT_POLICY.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/DATA_SPLIT_POLICY.md)

### 如果你要做 baseline 训练

1. [baseline/README.md](D:/data/ai4s/holophage/baseline/README.md)
2. [train.py](D:/data/ai4s/holophage/baseline/train.py)
3. [train_config.full_stage2.yaml](D:/data/ai4s/holophage/baseline/train_config.full_stage2.yaml)
4. [BASELINE_DATALOADER_SPEC.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/BASELINE_DATALOADER_SPEC.md)

### 如果你要做 embedding / 模态

1. [embedding_pipeline/README.md](D:/data/ai4s/holophage/embedding_pipeline/README.md)
2. [SaProt-1.3B_emb/README.md](D:/data/ai4s/holophage/SaProt-1.3B_emb/README.md)
3. [BASELINE_MODALITY_ASSETS.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/BASELINE_MODALITY_ASSETS.md)

### 如果你要理解 ontology 和长期方向

1. [PROJECT_OVERVIEW_zh.md](D:/data/ai4s/holophage/project_memory/00_index/PROJECT_OVERVIEW_zh.md)
2. [PROCESSING_CHANGELOG.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/PROCESSING_CHANGELOG.md)

---

## 13. 给新 AI 的一句建议

如果你是第一次接这个项目，最安全的工作方式是：

1. 先确认当前任务是在处理：
   - ontology
   - data pipeline
   - sequence embedding
   - SaProt 结构感知 embedding
   - baseline 训练
   哪一层
2. 再确认你引用的是不是**当前正式主线文档**
3. 不要默认历史文件仍然有效
4. 所有涉及 split、标签空间、embedding 主键的问题，优先以本文和上面列出的正式文档为准

---

## 14. 相关正式文档总表

- [README.md](D:/data/ai4s/holophage/README.md)
- [PROJECT_OVERVIEW_zh.md](D:/data/ai4s/holophage/project_memory/00_index/PROJECT_OVERVIEW_zh.md)
- [BASELINE_INPUT_MANIFEST.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/BASELINE_INPUT_MANIFEST.md)
- [TRAINING_DATA_SCHEMA.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/TRAINING_DATA_SCHEMA.md)
- [TRAINING_TASK_BOUNDARY.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/TRAINING_TASK_BOUNDARY.md)
- [DATA_SPLIT_POLICY.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/DATA_SPLIT_POLICY.md)
- [BASELINE_DATALOADER_SPEC.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/BASELINE_DATALOADER_SPEC.md)
- [BASELINE_INPUT_MANIFEST.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/BASELINE_INPUT_MANIFEST.md)
- [BASELINE_MODALITY_ASSETS.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/BASELINE_MODALITY_ASSETS.md)
- [PROCESSING_CHANGELOG.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/PROCESSING_CHANGELOG.md)
- [STRUCTURE_RETRIEVAL_PIPELINE.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/STRUCTURE_RETRIEVAL_PIPELINE.md)
- [STRUCTURE_FULL_COVERAGE_PLAN.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/STRUCTURE_FULL_COVERAGE_PLAN.md)
- [baseline/README.md](D:/data/ai4s/holophage/baseline/README.md)
- [embedding_pipeline/README.md](D:/data/ai4s/holophage/embedding_pipeline/README.md)
- [SaProt-1.3B_emb/README.md](D:/data/ai4s/holophage/SaProt-1.3B_emb/README.md)
---
doc_status: active
source_of_truth_level: canonical
doc_scope: onboarding
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

## Runtime Priority Note

如果你的目标是继续当前 baseline runtime，请先把下面这组内容当成唯一高优先级入口：

- [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
- [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)
- [ACTIVE_DOCS.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_DOCS.md)
- [ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)

当前 baseline runtime 主线只包括：

- [baseline](D:/data/ai4s/holophage/baseline)
- [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)
- [data_processed](D:/data/ai4s/holophage/data_processed)
- [outputs](D:/data/ai4s/holophage/outputs)
- [splits](D:/data/ai4s/holophage/splits)
- [project_memory/04_active_assets](D:/data/ai4s/holophage/project_memory/04_active_assets)

而下面这些当前应视为 support / reference branch，不应被误读成“baseline 已经正式接入”的主线：

- [SaProt-1.3B_emb](D:/data/ai4s/holophage/SaProt-1.3B_emb)
- [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline)
- [structures](D:/data/ai4s/holophage/structures)
- 旧 planning / changelog / schema / policy 文档
