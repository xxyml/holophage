---
doc_status: active
source_of_truth_level: canonical
doc_scope: active_assets
owner_path: project_memory/04_active_assets
last_verified: 2026-03-28
version: 2
supersedes: []
superseded_by: []
related_active_manifest:
  - project_memory/04_active_assets/ACTIVE_VERSION.yaml
  - project_memory/04_active_assets/ACTIVE_PATHS.yaml
runtime_allowed: false
archive_if_replaced: true
---

# Active Runtime Contract

本文档用自然语言解释当前 runtime contract，并和两份 YAML manifest 互相补充。

## 当前 active runtime

当前真正处于 active runtime contract 内的主线目录是：

- [baseline](D:/data/ai4s/holophage/baseline)
- [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)
- [data_processed](D:/data/ai4s/holophage/data_processed)
- [outputs](D:/data/ai4s/holophage/outputs)
- [splits](D:/data/ai4s/holophage/splits)
- [project_memory](D:/data/ai4s/holophage/project_memory)

其中当前 active baseline 的正式解释固定为：

- `ontology_version = PFO_v1.0.2`
- `split_strategy = homology_cluster`
- `split_version = homology_cluster_v1`
- `sequence_embedding_key = exact_sequence_rep_id`
- `baseline_scope = L1 + L2 + L3 core`
- `target_status = trainable_core`

## Manifest-first 运行规则

从 2026-03-28 开始，baseline runtime 采用如下优先级：

1. [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml) 负责“读什么”。
2. [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml) 负责“哪一版是真的”。
3. `train_config*.yaml` 只负责训练超参与实验设置，不再作为 runtime 路径的主来源。

当前已接入 manifest-first 的入口脚本：

- [train.py](D:/data/ai4s/holophage/baseline/train.py)
- [evaluate.py](D:/data/ai4s/holophage/baseline/evaluate.py)
- [build_embedding_index.py](D:/data/ai4s/holophage/baseline/build_embedding_index.py)
- [prepack_embeddings.py](D:/data/ai4s/holophage/baseline/prepack_embeddings.py)

这些脚本启动时都会：

- 打印 resolved runtime paths
- 校验关键输入是否存在
- 校验 split / vocab / embedding key / baseline 边界 contract
- 缺失时 fail-fast，而不是运行到首个 batch 再报错

## 当前不属于 active baseline runtime 的内容

下面这些目录可以存在，也可以被引用，但默认不是当前 baseline 的 runtime 入口：

- [SaProt-1.3B_emb](D:/data/ai4s/holophage/SaProt-1.3B_emb)
- [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline)
- [structures](D:/data/ai4s/holophage/structures)
- [dataset_pipeline_portable](D:/data/ai4s/holophage/dataset_pipeline_portable)
- [AI_HANDOFF_PACKAGE](D:/data/ai4s/holophage/AI_HANDOFF_PACKAGE)
- [data_intermediate](D:/data/ai4s/holophage/data_intermediate)
- [tmp](D:/data/ai4s/holophage/tmp)

这些内容应被理解为：

- support branch
- handoff mirror
- workbench / archive

而不是当前 baseline 当前主线的一部分。

## 当前最重要的硬约束

1. 不要把 `node_primary` 当成全量 L3 vocab。
2. 不要再用旧的 `genome-aware` 口径解释当前 split。
3. 当前 sequence-only core baseline 是永久对照组，不要丢。
4. 当前主线先补 runtime contract 和 supervision routing，不先扩 backbone。
