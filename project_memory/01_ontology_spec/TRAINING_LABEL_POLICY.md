# 训练标签策略（TRAINING_LABEL_POLICY）

## 1. 文档目的
本文件定义 **PFO v1.0.2** 在模型训练阶段如何使用不同层级、不同状态的标签。  
它回答的不是“某个蛋白生物学上是什么”，而是：

- 这个标签在训练中怎么用
- 哪些样本进入哪一个任务头
- 哪些样本只做父类监督
- 哪些样本暂不进入主训练
- 如何处理多标签和开放集

---

## 2. 训练任务的基本分解
基于 PFO v1.0.2，训练任务不应被定义成“729 类单标签分类”，而应拆成：

1. **L1 问题域分类任务**
2. **L2 scaffold 分类任务**
3. **L3 精细功能分类任务**
4. **L3 多标签任务**
5. **open-set / unknown 识别任务**

也就是说，一个样本可能同时参与多个任务，但参与方式不同。

---

## 3. 五种训练状态定义

### 3.1 `trainable_core`
定义：
- 可直接作为 L3 主监督标签
- 通常边界较清楚
- 相对适合单主标签处理
- 可以较稳定构造正负样本

典型节点：
- Major_capsid
- Portal
- DNA_polymerase
- Integrase
- RNA_polymerase
- Endolysin
- Holin
- Spanin

训练用途：
- 进入 L3 core 主分类头
- 同时自动参与 L2 / L1 父类监督

---

### 3.2 `trainable_multilabel`
定义：
- 可进入 L3 训练
- 但不能假设与其他类互斥
- 常与结构角色、上下文角色或其他机制共存
- 应允许 multi-hot 或 primary + secondary

典型节点：
- Tail_spike
- Cell_wall_depolymerase
- Internal_virion_protein
- DNA_ejection_protein
- Anti_restriction
- Anti_CRISPR
- Superinfection_exclusion

训练用途：
- 进入 L3 multilabel 头
- 同时参与 L2 / L1 父类监督
- 不应简单作为平面 softmax 中的互斥类

---

### 3.3 `parent_only`
定义：
- 当前只适合作为 L2 / L1 scaffold 标签
- 不进入第一轮 L3 精细监督
- 往往是宽类或中层骨架类

典型节点：
- Capsid
- Tail
- DNA_replication
- DNA_recombination
- Transcription_factor
- Nucleotide_metabolism

训练用途：
- 进入 L2 任务
- 自动参与 L1 任务
- 不进入 L3 主分类头

---

### 3.4 `defer`
定义：
- 当前先延后
- 可能具有一定功能指向，但证据不足或边界不稳
- 可作为后续升级候选

典型情况：
- CRISPR/Cas system associated
- restriction enzyme I / III
- generic DNA-binding protein
- 泛化 transcriptional regulator
- 含义不清的 host takeover 小蛋白

训练用途：
- 第一轮一般不进入 L3
- 可视情况参与 L1 / L2 粗监督
- 或进入 unknown/open-set regularization

---

### 3.5 `open_set`
定义：
- 当前无法稳定映射到已知本体叶子
- 本质上属于未知、弱解析、未映射或极弱证据状态

典型情况：
- no_phrog_mapping
- unresolved_blank_annotation
- conserved_hypothetical_phage_protein
- putative_membrane_protein
- putative_virion_associated_unknown

训练用途：
- 不进入 L3 主监督
- 进入 unknown/open-set 任务
- 用于拒识 / abstain / OOD 校准

---

## 4. 各状态与各层任务的对应关系

| status | L1 | L2 | L3 core | L3 multilabel | open-set |
|---|---|---|---|---|---|
| trainable_core | 是 | 是 | 是 | 否 | 否 |
| trainable_multilabel | 是 | 是 | 否 | 是 | 否 |
| parent_only | 是 | 是 | 否 | 否 | 否 |
| defer | 可选 | 可选 | 否 | 否 | 可选 |
| open_set | 否/可选 | 否 | 否 | 否 | 是 |

### 4.1 关于 `defer`
`defer` 是否进入 L1/L2 取决于 term 是否至少有一个可信的 coarse mapping。  
如果 coarse mapping 也不可靠，则更接近 open-set。

---

## 5. L1 / L2 / L3 的监督作用

### 5.1 L1 的作用
L1 主要是：
- 问题域监督
- genome context 监督
- coarse routing
- 为 unknown/defer 提供最低限度模块信息

L1 不要求非常细，但要求问题域语义稳定。

### 5.2 L2 的作用
L2 主要是：
- ontology scaffold
- coarse supervision
- 宽类承接
- L3 的父类先验

L2 不应被强行理解为“都能拿来做精细训练的功能类”。

### 5.3 L3 的作用
L3 才是：
- 精细功能预测
- 多标签/细机制建模
- 高置信叶子学习

---

## 6. 多标签策略

## 6.1 什么情况下属于 multilabel
如果一个 term 显式同时表达：
- 结构角色 + 酶活
- delivery + internal virion
- anti-defense + context-heavy block

则应优先进入 `trainable_multilabel` 或给 secondary label。

### 典型示例
- tail associated lysin
- baseplate hub and tail lysozyme
- tail spike protein with colonic acid degradation activity
- tail injection transglycosylase
- pilot protein for DNA ejection
- internal virion protein with endolysin domain

## 6.2 当前映射表中的 multilabel 表达
当前映射表仍然首先是一个 **primary mapping table**。  
也就是说，每个 term 先有主标签。  
对于显式双重语义的 term，才额外保留 secondary fields。

## 6.3 训练实现建议
对于 `trainable_multilabel`：
- 不用单纯 softmax
- 推荐 multi-hot / sigmoid BCE / focal loss
- 不应把相邻 cross-branch class 简单当作硬负类

---

## 7. 负样本构造原则

### 7.1 `trainable_core`
可相对更直接构造负样本，但仍需避开：
- broad parent-only bucket
- unresolved 同源宽类
- source term 明显重叠的邻近类

### 7.2 `trainable_multilabel`
负样本构造必须谨慎。  
例如：
- `Tail_spike` 不应把 `Cell_wall_depolymerase` 直接当硬负
- `DNA_ejection_protein` 不应把 `Internal_virion_protein` 直接当硬负
- `Anti_CRISPR` 不应把其他 context-heavy anti-defense term 一律当硬负

### 7.3 `parent_only`
不进入 L3 负样本竞争，但能作为 L2 父类正样本。

---

## 8. 数据切分原则
训练时不得简单随机切分蛋白。  
建议至少采用以下之一：

- 按 PHROG family / cluster 切分
- 按 genome / phage genome 切分
- 最好避免同一局部 operon/context 在 train/test 同时出现

原因：
- 防止 context 泄漏
- 防止同家族近邻直接泄漏到测试集

---

## 9. 评估策略

### 9.1 L1
评估：
- macro F1
- confusion matrix

### 9.2 L2
评估：
- macro F1
- parent-only 覆盖效果
- 宽类稳定性

### 9.3 L3 core
评估：
- macro F1
- per-class precision/recall
- 长尾类别表现

### 9.4 L3 multilabel
评估：
- macro F1
- micro F1
- mAP
- exact match（可选）
- 主要看 pairwise label 共现是否合理

### 9.5 open-set
评估：
- AUROC / AUPRC
- 拒识准确率
- 已知类与 unknown 的分离效果

---

## 10. 后续升级机制

### 10.1 从 `parent_only` 升级到新 L3
某一类若满足：
- 高频
- 语义较稳定
- family consistency 较高
- embedding 可形成稳定簇
- 可写出负样本规则

则可以考虑升级为新的 L3。

### 10.2 从 `defer` 升级到新 L3
某些 defer 项在后续模型和多模态证据支持下，也可升级。

### 10.3 `open_set` 的用途
open-set 不是终点，它是：
- 新叶子候选库
- 未知功能空间
- 后续本体扩容来源

---

## 11. 当前推荐执行顺序

### 第一步
冻结 PFO v1.0.2 的当前标签版本。

### 第二步
训练第一版模型，使用：
- trainable_core
- trainable_multilabel
- parent_only
- open-set

### 第三步
基于模型结果做误差分析：
- 哪些类总混淆
- 哪些 parent-only 可升级
- 哪些 defer/open-set 形成稳定簇

### 第四步
再考虑推出 v1.0.3 或更高版本。

---

## 12. 最重要的一句话
训练标签策略的目标不是“把所有样本都塞进同一种任务里”，而是：

> **根据标签语义质量、边界清晰度和多标签属性，把样本放进最适合它的训练通道里。**
---
doc_status: active
source_of_truth_level: canonical
doc_scope: ontology
owner_path: project_memory/01_ontology_spec
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
