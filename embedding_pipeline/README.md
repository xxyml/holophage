# Embedding Pipeline

更新时间：2026-03-27

这个目录统一管理本项目所有 embedding 相关资产。

## 目录结构

- [scripts](D:/data/ai4s/holophage/embedding_pipeline/scripts)
- [inputs](D:/data/ai4s/holophage/embedding_pipeline/inputs)
- [models](D:/data/ai4s/holophage/embedding_pipeline/models)
- [outputs](D:/data/ai4s/holophage/embedding_pipeline/outputs)
- [logs](D:/data/ai4s/holophage/embedding_pipeline/logs)
- [manifests](D:/data/ai4s/holophage/embedding_pipeline/manifests)

## 当前正式资产

输入：
- [exact_sequence_embedding_input.parquet](D:/data/ai4s/holophage/embedding_pipeline/inputs/exact_sequence_embedding_input.parquet)
- [1genome_cds_embedding_input.parquet](D:/data/ai4s/holophage/embedding_pipeline/inputs/1genome_cds_embedding_input.parquet)

模型：
- [prot_t5_xl_uniref50_bits](D:/data/ai4s/holophage/embedding_pipeline/models/prot_t5_xl_uniref50_bits)

输出：
- [embed_exact](D:/data/ai4s/holophage/embedding_pipeline/outputs/embed_exact)

历史输出：
- [archive](D:/data/ai4s/holophage/embedding_pipeline/outputs/archive)

日志：
- [history](D:/data/ai4s/holophage/embedding_pipeline/logs/history)
- [smoke](D:/data/ai4s/holophage/embedding_pipeline/logs/smoke)

## 核心脚本

- [extract_prott5_embeddings.py](D:/data/ai4s/holophage/embedding_pipeline/scripts/extract_prott5_embeddings.py)
- [download_prott5_safetensors.py](D:/data/ai4s/holophage/embedding_pipeline/scripts/download_prott5_safetensors.py)
- [rebuild_exact_sequence_embedding_input.py](D:/data/ai4s/holophage/embedding_pipeline/scripts/rebuild_exact_sequence_embedding_input.py)
- [rebuild_embedding_input_parquet.py](D:/data/ai4s/holophage/embedding_pipeline/scripts/rebuild_embedding_input_parquet.py)

## 当前正式口径

- sequence embedding 主键：`exact_sequence_rep_id`
- 长序列策略：
  - `<=512 aa`：整条编码
  - `>512 aa`：滑窗重叠后聚合
- baseline 读取目录：
  - `embedding_pipeline/outputs/embed_exact`

## 待清理参考

- [DELETE_CANDIDATES.tsv](D:/data/ai4s/holophage/embedding_pipeline/manifests/DELETE_CANDIDATES.tsv)
---
doc_status: active
source_of_truth_level: canonical
doc_scope: embedding_pipeline
owner_path: embedding_pipeline
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
