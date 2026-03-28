# 多模态 Baseline v2 计划与实现说明

## 目标

多模态 v2 不替换当前 sequence-only baseline，也不进入当前 active runtime 主线。  
它的定位是：

- 在 [baseline](D:/data/ai4s/holophage/baseline) 内平行扩展
- 保留 v1 作为永久对照组
- 先只做 `trainable_core`
- 先只做 `L1 + L2 + L3 core`
- 先回答“sequence / structure / context 是否互补”

当前不纳入：

- `trainable_multilabel`
- `parent_only` 进入 `L3`
- `open_set`
- `defer`
- 真实结构文件主训练

## 目录规划

### 文档

- 本文档：
  - `project_memory/02_data_pipeline/MULTIMODAL_BASELINE_V2_PLAN.md`
- 状态：
  - `doc_status: draft`
  - `source_of_truth_level: reference`
  - 使用仓库当前认可的 **tail metadata block**

### 代码

多模态 v2 模块放在：

- `baseline/multimodal_v2/__init__.py`
- `baseline/multimodal_v2/types.py`
- `baseline/multimodal_v2/assets.py`
- `baseline/multimodal_v2/adapters.py`
- `baseline/multimodal_v2/fusion.py`
- `baseline/multimodal_v2/heads.py`
- `baseline/multimodal_v2/model.py`
- `baseline/multimodal_v2/losses.py`

入口脚本放在：

- `baseline/prepack_multimodal.py`
- `baseline/dataset_multimodal.py`
- `baseline/train_multimodal.py`
- `baseline/evaluate_multimodal.py`

### 配置

- `baseline/train_config.multimodal_v2.stage1.yaml`
- `baseline/train_config.multimodal_v2.seq_struct.yaml`
- `baseline/train_config.multimodal_v2.seq_ctx.yaml`
- `baseline/train_config.multimodal_v2.all.yaml`

### 产物

- 多模态 prepack：
  - `baseline/artifacts/prepacked_multimodal_v2/`
- 训练输出：
  - `baseline/runs/multimodal_v2_*`

当前已验证存在：

- `baseline/artifacts/prepacked_multimodal_v2/stage1_seq_only/`
- `baseline/artifacts/prepacked_multimodal_v2/all/`

## 数据 contract

### 三路输入

1. Sequence
- 键：`exact_sequence_rep_id`
- 来源：`embedding_pipeline/outputs/embed_exact`
- 当前 active runtime 主序列表征

2. Structure-like
- 键：`exact_sequence_rep_id`
- 来源：`SaProt-1.3B_emb/outputs/embed_exact`
- support branch，不提升为当前 active runtime mainline

3. Context
- 键：`protein_id`
- 来源：`data_processed/context_features_v1.parquet`
- 实例级特征，不做 exact 复用

### 当前固定口径

- `ontology_version = PFO_v1.0.2`
- `split_strategy = homology_cluster`
- `split_version = homology_cluster_v1`
- `sequence_embedding_key = exact_sequence_rep_id`
- `target_status = trainable_core`

### 多模态 pack 输出字段

- `protein_id`
- `embedding_id`
- `exact_sequence_rep_id`
- `homology_cluster_id`
- `split`
- `split_strategy`
- `split_version`
- `status`
- `label_l1`
- `label_l2`
- `label_l3_core`
- `sequence_embedding`
- `structure_embedding`
- `context_features`
- `modality_mask`
- `sequence_length`

## 模型结构

### 总体结构

- 三路 adapter：
  - `sequence`
  - `structure`
  - `context`
- `softmax gated fusion + residual base`
- `2-layer residual trunk`
- 条件化 `L1 / L2 / L3 core` 三头

### 具体约定

#### Adapter

每路固定：

- `LayerNorm -> Linear -> GELU -> Dropout`

统一投影维度：

- `fusion_dim = 512`

#### Fusion

- 输入：`[z_seq; z_struct; z_ctx; modality_mask]`
- gate：
  - `g = softmax(W[...])`
- residual base：
  - `z_base = proj([z_seq; z_struct; z_ctx])`
- 输出：
  - `z_fused = z_base + g_seq*z_seq + g_struct*z_struct + g_ctx*z_ctx`

必须包含：

- `missing_modality_mask`
- `modality_dropout`

#### Heads

- `p1 = HeadL1(h)`
- `p2 = HeadL2([h; p1_prob])`
- `p3 = HeadL3([h; p2_prob])`

注意：

- 条件化输入使用 `softmax probs`
- 不直接拼 raw logits

## 损失函数

第一轮固定为：

```text
L = 0.5 * CE_L1 + 1.0 * CE_L2 + 1.2 * CE_L3 + 0.08 * L_hier
```

其中：

- `CE_L1 / CE_L2 / CE_L3`：softmax cross-entropy
- `L_hier`：
  - `KL(agg(L3)->L2 , p(L2))`
  - `KL(agg(L2)->L1 , p(L1))`

当前不做：

- multilabel loss
- open-set loss
- context-specific auxiliary loss
- metric learning
- focal family 大改

## 消融顺序

固定顺序，不跳步：

1. `seq-only`
2. `seq + struct`
3. `seq + ctx`
4. `seq + struct + ctx`

每一步都必须保持：

- 同一 split
- 同一 `trainable_core` 边界
- 同一评估口径

## 已落地实现

### 已完成

- v2 目录和模块边界已固定
- `context_features_v1.parquet` 已 materialize
- `prepack_multimodal.py` 已支持：
  - `seq-only`
  - `seq+struct`
  - `seq+ctx`
  - `all`
- `train_multimodal.py` 已具备最小可训练闭环
- `evaluate_multimodal.py` 已具备最小评估闭环
- `fusion_gates` 诊断已导出到评估指标

### 已通过烟测

1. `stage1_seq_only`
- prepack 成功
- dry-run 成功
- 真实 smoke train 成功
- 真实 smoke eval 成功

2. `all`
- prepack 成功
- dry-run 成功
- 真实 smoke train 成功
- 真实 smoke eval 成功

## 下一步

最自然的后续动作是：

1. 补 `seq_struct / seq_ctx` 两条线的正式 prepack 和 smoke
2. 在 v2 训练日志中补：
   - per-branch ablation logging
   - 分类别 gate 统计
3. 再决定是否把 v2 从 `draft/reference` 提升为更正式的 support baseline

---
doc_status: draft
source_of_truth_level: reference
doc_scope: data_pipeline
owner_path: project_memory/02_data_pipeline
last_verified: 2026-03-28
version: 2
supersedes: []
superseded_by: []
related_active_manifest:
  - project_memory/04_active_assets/ACTIVE_VERSION.yaml
  - project_memory/04_active_assets/ACTIVE_PATHS.yaml
runtime_allowed: false
archive_if_replaced: true
