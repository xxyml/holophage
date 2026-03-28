# Baseline Execution Plan

更新时间：2026-03-20

本文件用于把当前已经跑通的数据处理链，正式衔接到第一轮 baseline 训练。

当前状态：

- 原始蛋白表已标准化
- `PFO v1.0.2` 映射已完成
- task datasets 已生成
- genome-aware split 已生成
- label vocab 已生成
- 训练边界和 split 风险已写入正式文档

因此，项目已从“数据准备阶段”进入“baseline 可执行阶段”。

## 阶段 1：Baseline 模型训练准备与验证

### 目标

- 验证 baseline pipeline 可用
- 确认 L1 / L2 / L3 core 主任务可训
- 保证训练边界和 split 正确
- 避免未解决风险破坏实验

### 任务清单

1. 准备训练输入
   - `data_processed/training_labels_wide_with_split.csv`
   - `outputs/label_vocab_l1.json`
   - `outputs/label_vocab_l2.json`
   - `outputs/label_vocab_l3_core.json`
   - `outputs/label_vocab_l3_multilabel.json`

2. 确定 backbone
   - 序列模态：ESM2 / ProtT5
   - 结构模态：AF2 / ESMFold / 现成结构 embedding
   - 融合层：gated fusion 或 cross-attention
   - 输出头：L1 / L2 / L3 core 多头

3. 训练配置
   - loss：CrossEntropy + hierarchical consistency
   - optimizer / scheduler
   - class weight 或 focal loss
   - batch size / gradient accumulation

4. Sanity check
   - 输出每个 split 样本数
   - 检查 L1 / L2 / L3 覆盖
   - 再次核对 `status` 与 head 边界

5. 第一轮 baseline
   - 只训 L1 + L2 + L3 core
   - 记录每个 head 的 loss / accuracy / F1
   - 记录 hierarchical consistency violations
   - 保留 embedding 输出供后续分析

## 阶段 2：Multilabel / open-set / context

### 目标

- 在 baseline 上扩展复杂任务
- 逐步接入 multilabel、context 和 open-set

### 任务清单

1. 加入 multilabel L3 head
   - 训练数据：`data_processed/dataset_l3_multilabel.csv`
   - loss：BCE with logits / focal BCE
   - 结合 class weight

2. 加入 context 模态
   - 基于 `genome_id + contig_id + gene_index` 动态重建局部窗口
   - 邻居 embedding 可做 attention pooling
   - context-heavy 类单独观察收益

3. 加入 open-set head
   - 训练样本：`status == open_set`
   - 可采用 BCE / energy-based / distance-based 方案
   - 目标是做 reject / abstain，而不是强行闭集化

## 阶段 3：同源风险控制与评估

### 目标

- 更严格评估模型泛化能力
- 区分 genome-aware 泛化和 homology-heldout 泛化

### 任务清单

1. 新增 homology-cluster-aware split
   - MMseqs2 / CD-HIT 聚类
   - cluster 整体分配到 train / val / test
   - 与 genome-aware 共同约束

2. baseline 对比
   - genome-aware split
   - homology-cluster-aware split

## 阶段 4：defer / open_set / 新叶子探索

### 目标

- 从未分配与弱解析样本中发现后续 ontology 升级候选

### 任务清单

1. embedding 聚类
   - 使用 baseline embedding 分析 `open_set` / `defer`

2. candidate leaf 审核
   - 结合 ontology、annotation、context 和结构信息复核

3. 增量更新
   - 更新 vocab
   - 更新 mapping
   - 进入下一轮训练

## 阶段 5：日志与监控

所有阶段都应维护：

- 处理流水线日志
- split / class coverage / sample 数
- 模型训练日志
- embedding / evaluation 日志

重要变更必须同步更新：

- `PROCESSING_CHANGELOG.md`
- `TRAINING_TASK_BOUNDARY.md`
- `DATA_SPLIT_POLICY.md`
- `MODEL_TRAINING_PLAN.md`

## 当前优先级

1. 第一轮 baseline：L1 + L2 + L3 core
2. 加入 multilabel head 和 context
3. 处理 open-set / defer / 新叶子探索
4. 加入同源聚类 split 对比评估
5. 持续维护日志与文档

## 当前一句话建议

> 现在最应该做的是先把第一轮 baseline 训起来，优先验证 L1 / L2 / L3 core 三头可收敛、split 可解释、训练边界无混淆。
