# Server Asset Checklist

这份清单回答两个问题：

1. 服务器 `git clone` 代码后，还需要单独放哪些运行资产  
2. 如果只跑当前正式 baseline，和如果要跑多模态 v2，分别最少需要哪些文件

## 1. 代码仓库 clone 完之后，默认**还不够运行**

原因是当前 git 仓库**只包含代码、配置和文档**，不包含以下大资产：

- 训练主表
- split 文件
- exact embedding
- SaProt embedding
- baseline 预打包产物
- 训练/评估输出

所以服务器上推荐分成两块：

- 代码仓库：`~/holophage`
- 运行资产：例如 `/data/holophage_assets`

## 2. 只跑当前正式 sequence-only baseline 时，最少需要的资产

来自 `project_memory/04_active_assets/ACTIVE_PATHS.yaml` 的正式 runtime 输入：

- `data_processed/training_labels_wide_with_split.csv`
- `data_processed/baseline_embedding_join_index.csv`
- `outputs/label_vocab_l1.json`
- `outputs/label_vocab_l2.json`
- `outputs/label_vocab_l3_core.json`
- `splits/split_by_homology_cluster_v1.csv`
- `embedding_pipeline/outputs/embed_exact/`
- `baseline/artifacts/embedding_index_exact.sqlite`
- `baseline/artifacts/prepacked_core_exact/`

当前这几项里体积最大的通常是：

- `data_processed/training_labels_wide_with_split.csv`：约 `1021.93 MB`
- `data_processed/baseline_embedding_join_index.csv`：约 `428.68 MB`
- `embedding_pipeline/outputs/embed_exact/`：大目录
- `baseline/artifacts/prepacked_core_exact/`：大目录

## 3. 跑多模态 v2 时，在 sequence-only baseline 基础上再补这些

根据当前四个 v2 config：

- `baseline/train_config.multimodal_v2.seq_struct.yaml`
- `baseline/train_config.multimodal_v2.seq_ctx.yaml`
- `baseline/train_config.multimodal_v2.all.yaml`

额外需要：

- `data_processed/context_features_v1.parquet`
- `SaProt-1.3B_emb/outputs/embed_exact/`
- `baseline/artifacts/prepacked_multimodal_v2/`  
  这一项可以不从本地带，服务器上重新 prepack 也可以

其中：

- `data_processed/context_features_v1.parquet`：约 `75.59 MB`
- `SaProt-1.3B_emb/outputs/`：大目录

## 4. 推荐的服务器目录布局

代码仓库：

- `~/holophage`

运行资产：

- `/data/holophage_assets/data_processed`
- `/data/holophage_assets/outputs`
- `/data/holophage_assets/splits`
- `/data/holophage_assets/embed_exact`
- `/data/holophage_assets/saprot_embed_exact`
- `/data/holophage_assets/baseline_artifacts`

如果你不想改代码路径，最省事的做法是：

- 直接把这些目录按仓库相对路径放回 clone 后的项目目录里

也就是服务器最终仍然是：

- `~/holophage/data_processed/...`
- `~/holophage/outputs/...`
- `~/holophage/splits/...`
- `~/holophage/embedding_pipeline/outputs/embed_exact/...`
- `~/holophage/SaProt-1.3B_emb/outputs/embed_exact/...`
- `~/holophage/baseline/artifacts/...`

## 5. 两种迁移策略

### 方案 A：最省事

服务器上：

1. `git clone` 代码
2. 直接把本地这些运行目录整体传上去：
   - `data_processed/`
   - `outputs/`
   - `splits/`
   - `embedding_pipeline/outputs/embed_exact/`
   - `SaProt-1.3B_emb/outputs/embed_exact/`
   - `baseline/artifacts/`

优点：

- 不需要改 manifest
- 几乎零额外配置

缺点：

- 项目目录会比较大

### 方案 B：代码和资产彻底分离

服务器上：

1. `git clone` 代码到 `~/holophage`
2. 大资产放到 `/data/holophage_assets`
3. 后续再通过 manifest 或软链接把代码和资产接起来

优点：

- 更适合长期批量实验
- 代码仓和运行资产边界清楚

缺点：

- 第一次布置稍麻烦

## 6. 我对你当前阶段的推荐

如果你现在最优先是**尽快把实验转移到服务器跑起来**，推荐：

- **先用方案 A**

也就是：

1. 服务器 `git clone`
2. 直接按原相对路径把运行资产拷过去
3. 先把实验跑起来

等后面服务器工作流稳定了，再考虑把代码和资产彻底拆开。

## 7. 第一次迁移时，建议优先传的目录

优先级最高：

- `data_processed/`
- `outputs/`
- `embedding_pipeline/outputs/embed_exact/`
- `baseline/artifacts/`

如果要跑多模态 v2，再补：

- `SaProt-1.3B_emb/outputs/embed_exact/`
- `data_processed/context_features_v1.parquet`

如果只跑 sequence-only baseline，多模态这两项可以先不传。

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
  - D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml
runtime_allowed: false
archive_if_replaced: true
