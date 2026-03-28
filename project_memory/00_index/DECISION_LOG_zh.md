# 决策日志（DECISION_LOG）

## 说明
本文件记录项目中的关键设计决策、原因、替代方案与后续影响。

## 决策 001：不直接使用 PHROG / EmPATHi 作为最终训练标签体系
### 决策内容
不直接把 PHROG term 或 EmPATHi 原分类作为最终训练任务标签。

### 原因
真实 annotation term：
- 粒度不均匀
- 有大量 broad / weak / mixed labels
- 不适合直接平铺成单层训练标签

### 结果
转向自定义 PFO 框架。

## 决策 002：采用三层结构（L1/L2/L3）
### 决策内容
PFO 采用：
- Level 1：问题域 / 模块层
- Level 2：scaffold / parent layer
- Level 3：高置信可训练叶子层

### 原因
要同时满足：
- 真实 annotation 映射
- 模型训练需求
- 后续迭代扩展需求

### 结果
形成了后续所有版本的基本结构。

## 决策 003：Level 2 默认作为 parent-only scaffold
### 决策内容
Level 2 节点默认不进入第一轮精细监督，而主要作为：
- parent-only
- coarse supervision
- scaffold / fallback mapping

### 原因
很多 L2 是宽类，适合承接 broad term，但不适合作为精细监督。

### 结果
形成了 `parent_only` 这个重要状态。

## 决策 004：Level 3 只保留高置信可训练叶子
### 决策内容
L3 只包含：
- 语义相对清楚
- family/term 稳定
- 可构造相对可靠负样本
- 不只是 broad bucket 的节点

### 结果
L3 被限制为一批稳定核心叶子。

## 决策 005：引入五种训练状态
### 决策内容
正式区分：
- `trainable_core`
- `trainable_multilabel`
- `parent_only`
- `defer`
- `open_set`

### 原因
不同标签/样本在训练中作用不同，必须显式管理。

## 决策 006：`trainable_multilabel` 是正式类别，不是临时补丁
### 决策内容
明确承认某些节点必须允许多标签，例如：
- Tail_spike
- Cell_wall_depolymerase
- Internal_virion_protein
- DNA_ejection_protein
- Anti_restriction
- Anti_CRISPR
- Superinfection_exclusion

### 原因
真实词条中存在大量：
- 结构角色 + 酶活
- delivery + internal virion
- anti-defense + context-heavy 行为

## 决策 007：Level 1 由 source term 本身直接决定
### 决策内容
Level 1 不能由 Level 2 机械反推，而要根据真实 source term 自身语义决定。

### 原因
很多 term 同时包含：
- 结构位置
- 分子功能
- 上下文角色

仅靠 Level 2 反推会导致顶层误判。

## 决策 008：不把所有未分配项都强行归类
### 决策内容
对当前不适合进入 L3 的功能，分为：
- open_set
- defer
- parent_only
- candidate_new_leaf

### 原因
许多 unknown / weak / associated-only term 不能被可靠映射到细叶子。

## 决策 009：先训练稳定版本，再反向修 ontology
### 决策内容
不等待“完美 ontology”再训练，而是：
1. 冻结一个稳定版本
2. 训练模型
3. 用模型结果反向修 ontology

### 原因
很多 ontology 问题只有模型结果出来后才能真正看清。

## 决策 010：`RNA_polymerase` 应从一般 `Transcription_factor` 中独立
### 决策内容
`RNA_polymerase` 不再归入泛化 `Transcription_factor`，而应放在更合理的转录 machinery 语义下。

## 决策 011：`Integrase / Excisionase_or_recombinase` 从纯 `DNA_recombination` 语义中独立
### 决策内容
把这些更偏生活史切换/整合控制的节点，从普通 DNA_recombination 中抽离。

## 决策 012：`Cell_wall_depolymerase` 继续保留为 practical mixed leaf
### 决策内容
不把所有 virion-associated hydrolase / tail-associated lysin / entry transglycosylase 完全拆散，而保留 `Cell_wall_depolymerase` 作为实用混合叶子。

## 决策 013：采用 PFO v1.0.2 作为当前稳定版本
### 决策内容
采用 PFO v1.0.2 作为当前推荐训练版 ontology。

### 原因
它综合了：
- alpha revised 的工程可执行性
- improved / v1.1 的顶层语义改进
- 多标签和谨慎映射逻辑

## 决策 014：模型必须采用分层、多任务、多模态架构
### 决策内容
模型不做 flat single-head classifier，而是采用：
- L1/L2/L3 多头
- multilabel 子头
- open-set / reject 机制
- 多模态输入

### 原因
标签结构本身不是单平面，也不是纯单标签。

## 决策 015：未分配功能进入后续升级队列
### 决策内容
对尚未分配到细叶子的功能，建立后续管理机制：
- frequency
- family consistency
- embedding clustering
- structure support
- genome neighborhood

### 原因
这些功能不是失败样本，而是未来新 L3 的重要来源。

## 当前最重要的执行建议
- 冻结 PFO v1.0.2，不要再大改树
- 先训练第一版模型，再基于结果修 ontology
- 优先完善映射规则、多标签策略、未分配功能管理、模型输入表和数据切分
