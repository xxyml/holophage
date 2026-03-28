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

# Active Docs White List

这份文档定义当前仓库里哪些文档属于 active 白名单，以及它们在 runtime 层和 reference 层分别扮演什么角色。

如果某份文档不在这里，默认它更可能属于：

- `reference`
- `draft`
- `handoff_copy`
- `deprecated`
- `archived`

而不是当前 runtime / 训练解释的唯一真相。

## active_runtime_docs

这些文档直接解释当前 baseline runtime contract，默认优先级最高：

- [README.md](D:/data/ai4s/holophage/README.md)
- [PROJECT_ONBOARDING_FOR_AI.md](D:/data/ai4s/holophage/PROJECT_ONBOARDING_FOR_AI.md)
- [DIRECTORY_STRUCTURE.md](D:/data/ai4s/holophage/DIRECTORY_STRUCTURE.md)
- [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
- [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)
- [ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)
- [baseline/README.md](D:/data/ai4s/holophage/baseline/README.md)
- [BASELINE_INPUT_MANIFEST.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/BASELINE_INPUT_MANIFEST.md)
- [DATA_SPLIT_POLICY.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/DATA_SPLIT_POLICY.md)
- [TRAINING_TASK_BOUNDARY.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/TRAINING_TASK_BOUNDARY.md)

## active_reference_docs

这些文档仍然有效，但它们主要提供背景、规则解释和追溯信息，不单独决定 runtime 入口：

- [ONTOLOGY_SPEC_PFO_v1_0_2.md](D:/data/ai4s/holophage/project_memory/01_ontology_spec/ONTOLOGY_SPEC_PFO_v1_0_2.md)
- [TRAINING_LABEL_POLICY.md](D:/data/ai4s/holophage/project_memory/01_ontology_spec/TRAINING_LABEL_POLICY.md)
- [TRAINING_DATA_SCHEMA.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/TRAINING_DATA_SCHEMA.md)
- [PROCESSING_CHANGELOG.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/PROCESSING_CHANGELOG.md)
- [embedding_pipeline/README.md](D:/data/ai4s/holophage/embedding_pipeline/README.md)
- [SaProt-1.3B_emb/README.md](D:/data/ai4s/holophage/SaProt-1.3B_emb/README.md)

## 使用规则

1. 先读 [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml) 和 [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)。
2. 再读 `active_runtime_docs`。
3. 只有在需要背景、扩展或追溯时，才继续读 `active_reference_docs`。
4. 不要从 handoff 副本、历史归档或 support/workbench 目录反推当前 runtime contract。

## 文档状态块规范

当前仓库采用 **tail metadata block** 作为文档状态块规范，而不是强制要求 front matter。

原因：

- 现有 active docs 大多已经使用文末 YAML 状态块；
- 立即把所有入口文档改写成 front matter 成本更高、风险也更高；
- 当前治理目标是“规则和现实一致”，不是为了形式统一而大范围重写文档。

因此，当前正式规则以 [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml) 中的 `doc_policy.status_block_style = tail_metadata_block` 为准。
