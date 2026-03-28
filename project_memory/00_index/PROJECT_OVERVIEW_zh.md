# 项目总览（PROJECT_OVERVIEW）

## 1. 项目名称
PFO（Phage Function Ontology）构建与多模态噬菌体蛋白功能预测项目

## 2. 项目目标
本项目的核心目标是围绕真实噬菌体蛋白注释数据，建立一套**适合映射、适合训练、可逐步迭代**的功能分类框架（PFO），并基于该框架训练一个多模态模型，用于噬菌体蛋白功能预测。

本项目不是单纯做一个“好看的 ontology”，而是要同时满足三个条件：

1. **对真实 annotation term 友好**  
   能够承接来自 PHROG / PHROGs / PHROG-like term、人工整理 term、数据库输出 term 的真实注释语言。

2. **对模型训练友好**  
   能够区分哪些标签适合直接做主监督，哪些只能做父类监督，哪些应 defer/open-set。

3. **对后续迭代友好**  
   第一版不追求完美；后续可以通过模型结果、embedding 聚类、结构信息和基因组上下文，反向修正 ontology。

## 3. 项目背景与问题来源
真实噬菌体蛋白功能注释具有以下特点：

- 注释粒度不均匀：有的非常具体（如 `terminase large subunit`），有的非常宽泛（如 `tail protein`）
- 结构角色与分子功能常常交叉：如 tail spike 既是结构角色又可能有 depolymerase 活性
- 大量 unknown / no mapping / weakly-resolved 项存在
- 部分蛋白功能高度依赖 genome context，无法只靠序列词条判断
- 很多标签天然不是互斥，而是多标签共存

因此，不能直接把 700+ 真实功能词条平铺成一个“729 类单标签分类任务”。

## 4. 当前项目已经形成的核心共识
### 4.1 不追求一开始就做“完美 ontology”
更合理的路线是：
- 先冻结一个**稳定可执行版本**
- 基于这个版本训练第一版模型
- 再根据模型表现和错误分析去修 ontology

### 4.2 分类框架采用三层设计
- **Level 1**：问题域 / 模块层
- **Level 2**：ontology scaffold / 父类骨架层
- **Level 3**：高置信可训练叶子层

### 4.3 Level 1 不是由 Level 2 反推
对于真实 annotation term 的映射，**Level 1 应由 source term 本身直接决定**，而不是简单由 Level 2 倒推。

### 4.4 Level 2 默认作为 parent-only scaffold
Level 2 的主要作用是：
- 承接宽类
- 做 coarse supervision
- 作为 Level 3 的父类骨架

而不是和所有 Level 3 一样进入主监督。

### 4.5 Level 3 只保留高置信、可训练叶子
只有那些：
- 边界相对清楚
- family/term 稳定
- 负样本相对可定义
- 不只是 broad bucket
的节点才进入 Level 3 主监督。

### 4.6 必须正式引入多标签逻辑
对于以下类，不能继续假装是纯单标签：
- Tail_spike
- Cell_wall_depolymerase
- Internal_virion_protein
- DNA_ejection_protein
- Anti_restriction
- Anti_CRISPR
- Superinfection_exclusion

### 4.7 open-set / defer / weakly-resolved 不是失败，而是正式组成部分
未能进入 L3 的词条不应被强行归类，而应纳入：
- `parent_only`
- `defer`
- `open_set`
- `candidate_new_leaf`

## 5. 当前定版状态
当前推荐使用的版本是：

## **PFO v1.0.2**
这是一个融合版框架，综合了：
- alpha revised 版本的工程可执行性
- improved / v1.0.1 版本在顶层语义上的改进
- 对多标签、宽类、context-heavy 节点的修正

### 5.1 这一版的定位
PFO v1.0.2 不是终局本体，而是：
- 当前最稳定的 mapping 版本
- 当前最适合第一版训练的 ontology 版本
- 后续版本演化的基础

## 6. 当前已完成的工作
### 6.1 ontology 设计与比较
已经比较过多套方案：
- PFO 原始版本
- PFO-2
- PFO_v3
- EmPATHi
- PFO-alpha
- PFO-improved v1.1
- PFO v1.0.2（融合版）

### 6.2 700+ annotation term 的映射工作
已经完成对 729 个真实 annotation term 的多轮重映射，包括：
- alpha revised 版本映射
- improved v1.1 映射
- v1.0.2 融合映射

### 6.3 多标签词条的显式校正
尤其对以下类型做了重点修正：
- 结构角色 + 酶活
- entry / injection + wall degradation
- anti-defense / entry blocking
- internal virion + endolysin domain

### 6.4 训练策略已经形成初步方案
已经明确：
- trainable_core
- trainable_multilabel
- parent_only
- defer
- open_set

五种训练状态

### 6.5 已经形成后续路线
项目已经形成一个清晰路线：
1. 冻结稳定版本
2. 先训练第一版模型
3. 用模型结果反过来修 ontology
4. 再升级新类

## 7. 当前最重要的文件
建议优先阅读以下文件：
1. `PROJECT_OVERVIEW_zh.md`
2. `THINKING_SUMMARY_FOR_HANDOFF_zh.md`
3. `DECISION_LOG_zh.md`
4. `PFO_v1_0_2_remapped_729_terms_guide.md`
5. `PFO_v1_0_2_remapped_729_terms.csv`
6. `PFO_v1_0_2_L1_L2_L3_explanation.md`
7. `PFO_followup_plan.md`

## 8. 当前最重要的未解决问题
当前尚未完全解决的问题包括：
- `Host_defense_counterdefense` 是否还需要进一步拆分
- `Transcription_factor` 是否应再拆 subtype
- `Peptidoglycan_degradation` 内部是否应显式区分 entry-associated vs exit-associated
- `DNA_injection_internal_delivery` 是否需要进一步 role-type 细分
- 哪些 `defer/open_set` 项可以在下一轮升级为新 Level 3

## 9. 当前推荐路线
### 9.1 先冻结 PFO v1.0.2 作为训练版 ontology
不要继续反复改树。

### 9.2 基于 v1.0.2 先训第一版模型
模型建议采用：
- 多模态 backbone
- L1/L2/L3 多头
- multilabel 子头
- open-set / abstain 机制

### 9.3 训练后再做 ontology 反向修正
根据：
- confusion matrix
- embedding clustering
- structure/domain consistency
- genome neighborhood

去决定下一版本体如何升级。

## 10. 最重要的一句话
当前项目的核心理念不是：
> 先把 ontology 做到完美，再开始训练

而是：
> 先冻结一个稳定可执行版本，训练模型，再让模型帮助我们发现 ontology 的不足并逐步修正。
