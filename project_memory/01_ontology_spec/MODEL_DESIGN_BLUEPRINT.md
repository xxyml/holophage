# 模型设计蓝图（MODEL_DESIGN_BLUEPRINT）

## 1. 文档目的
本文件给出一个**适配 PFO v1.0.2 框架**的模型设计蓝图。  
目标不是直接给出最终代码实现，而是明确：

- 输入应包含哪些模态
- 模型整体结构如何搭建
- 输出头如何对应 L1 / L2 / L3
- 如何处理 `trainable_multilabel`
- 如何处理 `parent_only`
- 如何处理 `open_set`
- 训练分阶段怎么推进

---

## 2. 设计目标
模型不是一个普通的 flat classifier，而应满足：

1. **支持多层标签**
2. **支持多标签类**
3. **支持 open-set / abstain**
4. **支持 genome context**
5. **支持结构角色与机制功能混合**
6. **支持后续 ontology 迭代**

---

## 3. 推荐总体架构
建议模型采用：

## **共享多模态 backbone + 分层多任务输出头 + open-set 分支**

可记为：

### **PFO-HMNet**
Hierarchical Multimodal Network for Phage Function Ontology

其结构包括 5 个部分：

1. 输入编码层
2. 共享融合主干
3. 分层输出头
4. open-set / unknown 分支
5. prototype / retrieval 辅助模块（可选）

---

## 4. 输入模态设计

## 4.1 序列模态（必须有）
输入：
- 蛋白氨基酸序列

建议：
- 使用预训练 protein language model 提供 embedding
- 第一版优先使用固定 embedding，而不是从头训练大模型

可用来源：
- ESM2
- ProtT5
- 其他 protein foundation model embedding

作用：
- 对 replication / recombination / enzyme / regulator 类特别重要
- 例如：
  - DNA_polymerase
  - Helicase
  - Primase
  - Integrase
  - Holin
  - Endolysin
  - RNA_polymerase

---

## 4.2 结构模态（强烈建议有）
输入：
- 预测结构 embedding
- 或结构图特征 / residue contact graph

第一版建议：
- 用固定结构 embedding 或简化 GNN 特征
- 不必一开始就上完整原子图端到端模型

作用：
- 对结构角色类特别重要
- 例如：
  - Major_capsid
  - Portal
  - Head_tail_connector
  - Tail_tube
  - Tail_sheath
  - Baseplate
  - Tail_fiber
  - Tail_spike

---

## 4.3 genome context 模态（非常关键）
输入：
- 上下游 ORF 窗口
- 邻近蛋白 embedding 聚合
- 基因方向 / operon 结构
- 基因在 genome 上的位置
- 邻居的 coarse functional prior（可选）

第一版建议：
- 采用局部窗口 context encoder
- 不要求一开始就上完整 genome transformer

作用：
- 对以下类尤为重要：
  - L1 问题域判定
  - Superinfection_exclusion
  - DNA_ejection_protein
  - Internal_virion_protein
  - CI_like_repressor / Cro_like_regulator
  - 某些 host takeover / defense 类

---

## 4.4 可选辅助模态
可加但不是第一优先级：
- HMM/domain hits
- TM/signal peptide
- 蛋白长度
- coiled-coil
- motif features

可作为 metadata features 接到分类头前。

---

## 5. 共享主干设计

## 5.1 三路编码
模型内部先分别得到：
- `z_seq`
- `z_struct`
- `z_ctx`

## 5.2 融合方式
建议使用：

### **gated fusion**
而不是简单直接拼接。

原因：
- 不同类依赖不同模态
- 需要动态决定当前样本更信哪种模态
- 便于解释模型行为

示例：
- `Integrase` 更依赖序列
- `Portal` 更依赖结构
- `Superinfection_exclusion` 更依赖 context

---

## 6. 输出头设计

## 6.1 L1 头
任务：
- 预测 7 个 Level 1 问题域

输出：
- softmax over L1

用途：
- coarse routing
- genome context 模块监督
- 给 defer/open-set 提供最低粒度问题域信息

---

## 6.2 L2 头
任务：
- 预测 Level 2 scaffold 类

输出：
- softmax over L2

用途：
- 使用 parent-only 样本
- 让模型学会中层骨架
- 给 L3 提供父类先验

---

## 6.3 L3 头
L3 不建议只做一个头，而应拆成两个：

### 6.3.1 L3 core 头
对应 `trainable_core`

输出：
- softmax 或受约束的分类头

适用类：
- Major_capsid
- Portal
- DNA_polymerase
- Integrase
- RNA_polymerase
- Endolysin
- Holin
- Spanin
等

### 6.3.2 L3 multilabel 头
对应 `trainable_multilabel`

输出：
- sigmoid 多标签头

适用类：
- Tail_spike
- Cell_wall_depolymerase
- Internal_virion_protein
- DNA_ejection_protein
- Anti_restriction
- Anti_CRISPR
- Superinfection_exclusion

---

## 6.4 open-set / unknown 头
额外增加一个分支，用于判断：
- 已知可分配类
- unknown / open-set / weakly-resolved

输出：
- sigmoid / energy-based score / distance-based unknown score

用途：
- 避免把 unknown 强行塞入已知类
- 为后续新类别发现提供缓冲层

---

## 7. 层级一致性设计

## 7.1 为什么需要层级一致性
如果模型预测：
- L3 = `DNA_polymerase`

那么：
- L2 应偏向 `DNA_replication`
- L1 应偏向 `Genome_maintenance_propagation`

如果层级之间严重冲突，说明模型不稳定。

## 7.2 建议做法
加入 **hierarchical consistency loss**，约束：
- L3 与 L2 一致
- L2 与 L1 一致

作用：
- 提高小样本类稳定性
- 利用 parent-only 的信息
- 降低奇怪预测

---

## 8. 多标签处理设计

## 8.1 为什么必须单独处理
PFO 里有一批类天然不是互斥的。  
如果用单 softmax 强行做单标签，会带来系统性错误。

## 8.2 建议做法
- 保留 primary label
- 对显式 secondary label 用 multi-hot 目标
- 对 multilabel 头使用 BCE / focal BCE
- 不把相近类直接作为硬负类

---

## 9. open-set 设计

## 9.1 为什么必须有
噬菌体蛋白里：
- no mapping
- hypothetical
- weakly-resolved
- context-heavy small proteins
大量存在。

闭集 softmax 会过度自信。

## 9.2 推荐策略
### A. unknown head
增加一个显式 unknown 头

### B. prototype / distance
维护已知类原型，判断样本与类原型距离

### C. abstain 阈值
当：
- 所有类置信度都低
- 或 prototype 距离都大
时，允许拒识

---

## 10. 训练阶段建议

## 10.1 阶段一：backbone 预热
输入：
- 序列
- 结构

任务：
- L1
- L3 core

目标：
- 让 backbone 先学会明显的细功能边界

---

## 10.2 阶段二：加入 context
输入：
- 序列
- 结构
- genome context

任务：
- L1
- L2
- L3 core
- L3 multilabel

目标：
- 学 context-heavy 类
- 利用 parent-only

---

## 10.3 阶段三：加入 open-set
加入：
- unknown 头
- abstain / reject 机制
- prototype 或 energy loss

目标：
- 不要把 unknown 强行归类

---

## 10.4 阶段四：半监督 / 新类发现
利用：
- defer
- parent_only
- open_set
做：
- pseudo-label
- clustering
- candidate new leaf mining

目标：
- 为 ontology 升级准备证据

---

## 11. 损失函数建议
总损失可写成：

\[
L = \lambda_1 L_{L1} + \lambda_2 L_{L2} + \lambda_3 L_{core} + \lambda_4 L_{multi} + \lambda_5 L_{hier} + \lambda_6 L_{open} + \lambda_7 L_{proto}
\]

其中：

- `L_L1`：L1 分类损失
- `L_L2`：L2 分类损失
- `L_core`：L3 core 分类损失
- `L_multi`：L3 multilabel 损失
- `L_hier`：层级一致性损失
- `L_open`：open-set 损失
- `L_proto`：prototype / metric loss

### 第一版简化建议
可先只用：
- `L_L1`
- `L_L2`
- `L_core`
- `L_multi`
- `L_hier`

等模型跑稳后再加：
- `L_open`
- `L_proto`

---

## 12. 数据切分建议
不要随机切分蛋白。  
建议至少使用：

- family / cluster-aware split
- genome-aware split

原因：
- 避免同一近邻蛋白泄漏
- 避免 genome context 泄漏
- 更真实评估泛化能力

---

## 13. 样本使用策略

### 13.1 trainable_core
进入：
- L3 core
- L2
- L1

### 13.2 trainable_multilabel
进入：
- L3 multilabel
- L2
- L1

### 13.3 parent_only
进入：
- L2
- L1

### 13.4 defer
进入：
- 可选 L1 / L2
- 或 unknown regularization

### 13.5 open_set
进入：
- unknown / open-set 任务

---

## 14. 评估建议

### 14.1 L1
- macro F1
- confusion matrix

### 14.2 L2
- macro F1
- 宽类稳定性

### 14.3 L3 core
- macro F1
- per-class PR/F1
- 长尾类别分析

### 14.4 L3 multilabel
- micro/macro F1
- mAP
- label co-occurrence 合理性

### 14.5 open-set
- AUROC / AUPRC
- reject accuracy
- 已知/未知分离度

---

## 15. 当前最推荐的第一版实现
### 模型名称（建议）
**PFO-Net v0**

### 输入
- sequence embedding
- structure embedding
- local genome context embedding

### 主干
- 三路 encoder
- gated fusion

### 输出
- L1 softmax
- L2 softmax
- L3 core softmax
- L3 multilabel sigmoid
- unknown head

### 训练
- 分阶段
- 类别不平衡加权
- 层级一致性约束

---

## 16. 最重要的一句话
最适配 PFO 框架的模型，不是一个更大的单分类器，而是：

> **一个共享多模态 backbone + L1/L2/L3 分层头 + multilabel 子头 + open-set 分支的层级多任务模型。**
