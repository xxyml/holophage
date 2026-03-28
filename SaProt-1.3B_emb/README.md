# SaProt-1.3B Embedding Pipeline

更新时间：2026-03-27

这个目录统一管理 `SaProt-1.3B` 的 AA-only 结构感知 embedding 资产。

## 目录结构

- [scripts](D:/data/ai4s/holophage/SaProt-1.3B_emb/scripts)
- [inputs](D:/data/ai4s/holophage/SaProt-1.3B_emb/inputs)
- [models](D:/data/ai4s/holophage/SaProt-1.3B_emb/models)
- [outputs](D:/data/ai4s/holophage/SaProt-1.3B_emb/outputs)
- [logs](D:/data/ai4s/holophage/SaProt-1.3B_emb/logs)
- [manifests](D:/data/ai4s/holophage/SaProt-1.3B_emb/manifests)

## 正式口径

- 输入主键：`exact_sequence_rep_id`
- 推理模式：`AA-only`
- 输出粒度：蛋白级 pooled embedding
- 默认 batch：`4`
- 长序列策略：
  - `<= 1024 aa`：整条编码
  - `> 1024 aa`：滑窗重叠聚合
- 恢复策略：只按完整 shard 恢复，不做 step 级恢复

## 正式输入

- [exact_sequence_embedding_input.parquet](D:/data/ai4s/holophage/SaProt-1.3B_emb/inputs/exact_sequence_embedding_input.parquet)

## 正式输出

- [embed_exact](D:/data/ai4s/holophage/SaProt-1.3B_emb/outputs/embed_exact)

## 核心脚本

- [download_saprot_model.py](D:/data/ai4s/holophage/SaProt-1.3B_emb/scripts/download_saprot_model.py)
- [extract_saprot_embeddings.py](D:/data/ai4s/holophage/SaProt-1.3B_emb/scripts/extract_saprot_embeddings.py)

## 常用命令

在仓库根目录 `D:\data\ai4s\holophage` 下运行：

下载模型：

```powershell
python .\SaProt-1.3B_emb\scripts\download_saprot_model.py
```

预检：

```powershell
python .\SaProt-1.3B_emb\scripts\extract_saprot_embeddings.py --preflight-only --limit-rows 64
```

全量运行：

```powershell
python .\SaProt-1.3B_emb\scripts\extract_saprot_embeddings.py
```

自动断点恢复：

```powershell
python .\SaProt-1.3B_emb\scripts\extract_saprot_embeddings.py --resume-auto
```
---
doc_status: active
source_of_truth_level: canonical
doc_scope: structure_embedding
owner_path: SaProt-1.3B_emb
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
