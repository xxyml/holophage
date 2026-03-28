# Git And Server Sync Guide

这个项目最适合用“**代码走 git，数据/embedding/训练产物单独同步**”的方式维护。

## 推荐边界

适合进 git 的内容：

- `baseline/` 中的代码、配置、README
- `baseline/multimodal_v2/` 代码
- `tools/`
- `project_memory/` 中除归档和大转移包之外的文档
- `embedding_pipeline/` 和 `SaProt-1.3B_emb/` 中的脚本、README、manifests
- 根目录文档：
  - `README.md`
  - `PROJECT_ONBOARDING_FOR_AI.md`
  - `DIRECTORY_STRUCTURE.md`
  - `GIT_SERVER_SYNC_GUIDE.md`
  - `.gitignore`

不适合进 git 的内容：

- 训练产物：
  - `baseline/artifacts/`
  - `baseline/runs/`
- 大模型和 embedding 资产：
  - `embedding_pipeline/models/`
  - `embedding_pipeline/outputs/`
  - `SaProt-1.3B_emb/models/`
  - `SaProt-1.3B_emb/outputs/`
- 大数据表：
  - `data_processed/*.csv`
  - `data_processed/*.parquet`
  - `splits/**/*.csv`
- 历史/镜像/临时目录：
  - `AI_HANDOFF_PACKAGE/`
  - `dataset_pipeline_portable/`
  - `project_memory/05_archive/`
  - `project_memory/04_active_assets/model_dev_transfer_package/`
  - `data_intermediate/`
  - `gpt生成/`
  - `tmp/`
  - `数据集修复/`

## 建议的工作流

本地机器：

1. 在项目根目录初始化 git 仓库。
2. 只提交代码、配置和文档。
3. 本地做开发、调试、文档更新。
4. 提交并推送到远端仓库。

服务器：

1. `git clone` 代码仓库。
2. 单独准备 runtime 资产目录，不走 git。
3. 通过拷贝、压缩包、`scp`、`rsync` 或网盘把大资产放到服务器。
4. 在服务器上跑正式实验，训练产物只保存在服务器，不回写 git。

## 推荐的服务器布局

代码仓库：

- `~/holophage`

数据与大资产：

- `/data/holophage_assets/data_processed`
- `/data/holophage_assets/splits`
- `/data/holophage_assets/embed_exact`
- `/data/holophage_assets/saprot_embed_exact`
- `/data/holophage_assets/baseline_artifacts`

这样做的好处是：

- 本地和服务器的代码版本一致
- 训练产物不会污染 git
- 后续可以频繁本地开发、服务器批量运行

## 第一次迁移时最需要带到服务器的内容

代码和文档：

- 当前 git 仓库内容

运行所需资产：

- `data_processed/training_labels_wide_with_split.csv`
- `data_processed/baseline_embedding_join_index.csv`
- `data_processed/context_features_v1.parquet`
- `splits/split_by_homology_cluster_v1.csv`
- `outputs/label_vocab_l1.json`
- `outputs/label_vocab_l2.json`
- `outputs/label_vocab_l3_core.json`
- `embedding_pipeline/outputs/embed_exact/`
- `SaProt-1.3B_emb/outputs/`
- 如需直接复现实验，还应带：
  - `baseline/artifacts/embedding_index_exact.sqlite`
  - `baseline/artifacts/prepacked_core_exact/`

## 建议的下一步

1. 先在本地初始化 git 仓库。
2. 先提交代码、文档、配置和 `.gitignore`。
3. 再决定服务器上数据目录的固定位置。
4. 最后把大资产单独同步到服务器。

---
doc_status: active
source_of_truth_level: reference
doc_scope: repo_ops
owner_path: D:/data/ai4s/holophage
last_verified: 2026-03-28
version: 1
supersedes: []
superseded_by: []
related_active_manifest:
  - D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml
  - D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml
runtime_allowed: false
archive_if_replaced: true
