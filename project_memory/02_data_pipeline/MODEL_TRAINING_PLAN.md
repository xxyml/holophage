# 模型训练计划（MODEL_TRAINING_PLAN）

## 1. 文档目的
本文件定义第一版模型训练的实施计划。  
与 `MODEL_DESIGN_BLUEPRINT.md` 不同，这份文档更强调：

- 先训什么
- 后训什么
- 哪些先不做
- baseline 怎么设
- 每一阶段的目标是什么

---

## 2. 训练目标
第一版模型的目标不是“一步到位覆盖所有功能”，而是：

1. 在稳定版本 ontology 上建立可工作的训练基线
2. 先把 L1/L2/L3 主任务跑通
3. 让 multilabel 类能被正式纳入训练
4. 让 unknown/open-set 有初步能力
5. 为下一轮 ontology 升级提供误差分析依据

---

## 3. 当前推荐 ontology 版本
训练基于：
- **PFO v1.0.2**

训练数据基于：
- `PFO_v1_0_2_remapped_729_terms.csv`

---

## 4. 第一版模型的范围控制

## 4.1 第一版必须做
- L1 问题域分类
- L2 scaffold 分类
- L3 core 分类
- `homology_cluster_v1` 数据切分

## 4.2 第一版建议做
- 序列 + 结构双模态
- 简化版 context encoder
- hierarchical consistency loss
- 类别不平衡加权
- L3 multilabel 任务（至少支持当前显式多标签类）

## 4.3 第一版可以暂缓
- 复杂 prototype retrieval 模块
- 全功能 open-set 校准
- 大规模 pseudo-labeling
- 自动新类发现

---

## 5. 训练阶段设计

## 阶段 0：数据准备
目标：
- 固定训练输入 schema
- 生成 split-aware 数据集
- 统计每个 L1/L2/L3 类别样本数
- 审查多标签样本
- 记录 `homology_cluster_v1` 的训练边界与剩余风险

产出：
- dataset_l1
- dataset_l2
- dataset_l3_core
- dataset_l3_multilabel
- dataset_open_set（可先预留）

---

## 阶段 1：单蛋白 backbone 预热
输入：
- sequence embedding
- structure embedding

任务：
- L1
- L3 core

目标：
- 先让模型学会最稳定的细功能边界
- 避免 context 模态过早主导

建议：
- 先不加入 unknown 头
- 先不加入复杂 multilabel 逻辑（可先只保留显式多标签样本）
- 评估口径应明确为 `homology_cluster_v1` baseline，不再沿用旧的 genome-aware 解释

---

## 阶段 2：加入 L2 和 multilabel
输入：
- sequence embedding
- structure embedding
- （可选）简化 context embedding

任务：
- L1
- L2
- L3 core
- L3 multilabel

目标：
- 把 parent-only 样本利用起来
- 让 multilabel 节点正式进入训练
- 提升层级一致性
- 观察长尾 multilabel 类是否需要 class weight / focal loss / oversampling

---

## 阶段 3：加入 genome context
输入：
- sequence embedding
- structure embedding
- local genome context embedding

任务：
- L1
- L2
- L3 core
- L3 multilabel

重点类：
- Superinfection_exclusion
- DNA_ejection_protein
- Internal_virion_protein
- CI_like_repressor / Cro_like_regulator
- 部分 host-interface / regulation 类

目标：
- 学 context-heavy 标签
- 检查是否存在 context 泄漏
- 评估 context 是否真的带来提升

### 结构分支升级备选
如果后续确认当前 `SaProt AA-only` 结构分支增益有限，但仍希望增强结构信息，同时控制推理成本，则优先考虑：

- `ProstT5 -> 3Di -> SaProt(AA+3Di)`

使用意图：

- `ProstT5` 负责快速产生 3Di 表征
- `SaProt` 负责消费 `AA+3Di` 得到更强的 structure-aware embedding
- 避免把完整三维结构预测作为线上前置条件

这条路线属于后续优化候选，不属于当前第一轮正式 baseline 的既定组成部分。

---

## 阶段 4：加入 open-set / unknown
输入不变，但新增：
- unknown/open-set head

训练样本：
- open_set
- 一部分 defer
- 一部分已知类负样本

目标：
- 不把 unknown 强行塞进已知类
- 为后续 ontology 扩容打基础

---

## 6. baseline 设计建议

## 6.1 Baseline A：序列单模态
输入：
- sequence embedding

任务：
- L1
- L3 core

作用：
- 建立最低基线

## 6.2 Baseline B：序列 + 结构
输入：
- sequence embedding
- structure embedding

任务：
- L1
- L3 core
- L3 multilabel

作用：
- 看结构模态是否带来明显提升

## 6.3 Baseline C：序列 + 结构 + context
输入：
- 三模态

任务：
- 全部主任务

作用：
- 检查 context 对 context-heavy 节点的实际贡献

---

## 7. 类别不平衡处理
由于长尾明显，建议至少采用以下一种或多种：

- class weight
- focal loss
- balanced sampling
- per-class threshold tuning

尤其要关注：
- Anti_CRISPR
- 部分调控类
- multilabel mixed leaf

### 7.1 当前已知不平衡来源
当前数据处理中已知存在以下现象：

- `open_set` 占比很高，主要来自原始 annotation 缺失
- `trainable_multilabel` 总样本量明显低于 `trainable_core`
- L3 core / multilabel 内部呈长尾分布

因此训练时应明确：

- 第一轮主训练可优先聚焦 `trainable_core`
- `open_set` 不必在第一轮硬性纳入主任务头
- multilabel 训练需结合不平衡处理策略

---

## 8. 损失函数配置建议

### 第一版简化配置
总损失可先设为：

- `L_L1`
- `L_L2`
- `L_core`
- `L_multi`
- `L_hier`

即：
- L1 分类损失
- L2 分类损失
- L3 core 分类损失
- multilabel BCE 损失
- hierarchical consistency loss

### open-set 相关
在阶段 4 再加入：
- `L_open`

---

## 9. 评估计划

### 9.1 每阶段都要评估
- L1 macro F1
- L2 macro F1
- L3 core macro F1
- L3 multilabel micro/macro F1
- confusion matrix

### 9.2 阶段 3 起重点关注
- context-heavy 类提升是否真实
- 是否存在 context 泄漏迹象
- multilabel 是否被正确利用

### 9.2.1 当前 split 解释边界
当前正式实现采用的是 `homology_cluster_v1`，因此评估时必须额外注明：

- 已按 `homology_cluster_id` 做 train / val / test 隔离
- `clusters_cross_split = 0`
- 当前结果应解释为 `homology-heldout baseline`
- 不再沿用旧的 genome-heldout / genome-aware 口径

### 9.3 阶段 4 起增加
- unknown AUROC / AUPRC
- reject accuracy
- 已知 / 未知分离效果

---

## 10. 第一版训练的停止条件
满足以下条件时，可认为第一版训练阶段完成：

1. L1/L2/L3 主头均可稳定收敛
2. multilabel 头可正常输出合理 secondary pattern
3. confusion matrix 能显示出明显 ontology 问题区域
4. open-set 初版可区分部分 unknown
5. 已经能支持下一轮错误分析和 ontology 反向修正

---

## 11. 当前不建议做的事情
第一版不建议：

- 一开始就加入过多 experimental loss
- 一开始就把 open-set 做得过重
- 为了追求更高分数去用随机 protein split
- 在 ontology 还没固定前频繁换树
- 在没有误差分析前就新增很多 L3 节点

---

## 12. 第一版训练完成后的下一步
训练结束后，优先做：

1. confusion pair analysis
2. multilabel coverage review
3. parent-only cluster review
4. defer/open-set candidate mining
5. ontology 修订建议整理

---

## 13. 最重要的一句话
第一版训练计划的目标不是“做出最终模型”，而是：

> **在稳定版本 ontology 上建立一个可解释、可分析、可迭代的训练基线。**

---

## 14. 2026-03-28 之后的固定优先级
从当前 baseline、ontology 与文档状态出发，后续优先级固定为：

1. **先把 single source of truth 收紧**
   - 把 L2 正式固定为 `21 类`
   - 清除旧的 genome-aware 表述
   - 让 ontology / vocab / statistics / baseline README 完全一致
2. **保留当前 sequence-only core baseline**
   - 它是永久对照组，不应被后续实验覆盖
3. **下一步先扩 coarse supervision**
   - 把 `parent_only + trainable_multilabel` 正式纳入 `L1/L2`
   - 先补 supervision routing，不先加复杂 backbone
4. **再加独立 multilabel head**
   - 不把 multilabel 节点并进当前 core softmax
5. **最后再做 open-set 与 context branch**
   - 两者应建立在 status-aware 任务分解已经成形之后

## 15. GNN Context v2

当前 handcrafted context 在 `trainable_core + L1/L2/L3 core` 第一轮正式评估中未表现出明确增益，因此 context 路径的下一步不是恢复 `all`，而是先单独升级 context branch：

- `GNN context v2a`

固定边界：

- 只替换 context branch
- 主评估继续使用 `homology_cluster_v1`
- 同时补 `genome_context_v1` 作为更严格的 context/generalization 辅助评估
- 不在这一轮引入 multilabel / open-set / graph transformer

详细实现规范见：

- `project_memory/02_data_pipeline/CONTEXT_GRAPH_V2_SPEC.md`
