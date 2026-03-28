# 未解决问题与风险（OPEN_QUESTIONS_AND_RISKS）

## 1. 文档目的
本文件用于记录当前项目中仍未完全解决的问题、潜在风险以及后续需要重点观察的方向。  
它的作用不是制造不确定性，而是明确：

- 哪些地方已经形成强共识
- 哪些地方还只是当前最优妥协
- 哪些地方最可能在下一版 ontology 中发生变化
- 哪些问题会直接影响模型训练和结果解释

---

## 2. 当前已经较稳定的部分
以下内容目前相对稳定，短期内不建议再大改：

- PFO v1.0.2 作为当前工作版本
- 三层结构（L1 / L2 / L3）
- Level 1 由 source term 直接决定
- Level 2 默认作为 parent-only scaffold
- Level 3 受限白名单策略
- 多标签节点必须正式承认
- open-set / defer 正式存在
- 先训练稳定版本，再反向修 ontology

这些不属于当前主要风险区。

---

## 3. 当前仍未完全解决的核心问题

## 3.1 `Host_defense_counterdefense` 仍然偏宽
### 问题
该 L2 目前同时承接：
- Anti_restriction
- Anti_CRISPR
- Superinfection_exclusion
- 某些更泛的 host takeover / interference 候选项

这些类并不处于同一语义平面上。

### 风险
- mapping 时容易“方便地全丢进去”
- 训练时类边界会被稀释
- 解释时容易把 entry blocking 与 anti-defense 混为一谈

### 当前建议
短期内不一定马上拆树，但建议在 mapping / training 层增加：
- `defense_type`
- `training_risk`
- `context_heavy_flag`

### 未来可能升级方向
- 拆出 `Host_takeover_interference`
- 或把 `Superinfection_exclusion` 进一步 context 化

---

## 3.2 `Transcription_factor` 内部粒度不均
### 问题
该类目前混有：
- transcriptional activator
- DNA-binding protein
- transcriptional regulator
- anti-termination-like terms
- sigma-like reprogramming terms

### 风险
- source term 过宽
- 训练纯度下降
- 可能掩盖一些值得拆出来的新叶子

### 当前建议
先保留树不动，但建议后续在 mapping layer 增加：
- `subtype_hint`
- `heterogeneity_flag`

### 未来可能升级方向
- Generic_transcription_factor
- Antitermination_regulation
- Sigma_reprogramming

---

## 3.3 `Peptidoglycan_degradation` 是一个 practical mixed bucket
### 问题
当前它同时承接：
- Endolysin（偏 late exit）
- Cell_wall_depolymerase（常偏 entry-associated / virion-associated）

### 风险
- 机制解释混合
- entry-associated hydrolase 与 classic lysis enzyme 被揉在一起
- 某些词条 primary / secondary 决策不稳定

### 当前建议
短期内保留这两个 practical leaf，不建议为了机制纯度拆树。  
但建议增加树外字段：
- `lysis_timing`
- `entry_associated_flag`

### 未来可能升级方向
- 在树外稳定后，再考虑进一步拆节点

---

## 3.4 `DNA_injection_internal_delivery` 仍然偏 context-heavy
### 问题
它当前承接：
- Internal_virion_protein
- DNA_ejection_protein
- pilot protein-like terms

这些类在很多情况下依赖 context、邻近基因和 virion role，而不是单纯序列/结构。

### 风险
- 只靠单蛋白训练容易边界漂移
- mapping 里也容易因 wording 不同而摇摆

### 当前建议
不要急于改树，先增加：
- `delivery_role_type`
- `requires_multimodal_evidence`
- `training_risk = context_heavy`

### 未来可能升级方向
- 根据模型和邻域信息再决定是否细拆

---

## 3.5 `Protein_RNA_processing` 目前还比较弱
### 问题
这个类当前更多是 scaffold / 观察类，而不是成熟的训练模块。

### 风险
- 如果过早往这里塞 L3，容易引入很多 weak labels
- 可能把 translation repressor、RNA ligase、RNA-binding 等机制混成一团

### 当前建议
目前主要作为：
- parent-only
- observation bucket
- future candidate reservoir

### 未来可能升级方向
- 只有在有足够稳定 term 和 family 支持时才升级

---

## 4. 数据与映射层面的风险

## 4.1 source term 粒度不齐
### 问题
真实 annotation term 的粒度跨度非常大：
- 非常具体（e.g. terminase large subunit）
- 相当宽泛（e.g. tail protein）
- 含糊不清（e.g. associated, putative, hypothetical）

### 风险
- ontology 再好，也无法消除原始语义噪声
- 容易让人误以为“树不够好”，实际上是 source term 本身不支持

### 应对
- 保留 broad classes
- 使用 defer/open-set
- 通过 mapping policy 控制过度解释

---

## 4.2 多标签信息仍然不完整
### 问题
当前虽然已经引入 primary / secondary labels，但仍然不是所有可能多标签的 term 都被显式展开。

### 风险
- 某些 multilabel class 看起来像 single-label
- 训练时仍可能丢信息
- secondary label coverage 不均

### 应对
- 保持保守策略
- 先只记录显式双重语义 term
- 后续结合模型结果再扩 secondary coverage

---

## 4.3 `parent_only` 容易被低估
### 问题
`parent_only` 很容易被误认为“没用的中间层”。

### 风险
- 后续有人可能试图删掉或跳过 L2
- 导致宽类样本无法利用
- 层级监督和 coarse routing 丢失

### 应对
- 明确说明 parent-only 是训练和 ontology 之间的桥梁
- 在模型中保留 L2 头

---

## 5. 训练与模型层面的风险

## 5.1 如果用 flat classifier，会直接破坏当前本体设计
### 风险
- multilabel 被强行互斥
- parent-only 无法利用
- open-set 被迫闭集化
- L1/L2/L3 关系丢失

### 应对
必须坚持：
- 分层
- 多头
- multilabel 子头
- open-set 分支

---

## 5.2 genome context 泄漏风险很高
### 问题
如果按蛋白随机切分训练/测试，context 信息极易泄漏。

### 风险
- 评估虚高
- 模型看似很强，实际只是记住 operon/module

### 应对
- 按 family / cluster 切分
- 按 genome 切分
- 避免相邻基因同时落入 train/test

---

## 5.3 长尾和小样本问题仍然严重
### 问题
某些类样本很少，例如：
- Anti_CRISPR
- 某些调控类
- 某些 multilabel mixed leaf

### 风险
- 模型容易被头部类主导
- 小样本类不稳定
- multilabel 类被压制

### 应对
- class weighting
- focal loss
- prototype / metric learning
- 分阶段训练

---

## 5.4 open-set 任务如果不做，会污染所有已知类
### 风险
- unknown 被强行塞进已知类
- 混淆矩阵变脏
- ontology 错误被误判成模型错误

### 应对
- 显式 unknown head
- abstain / reject
- prototype distance / energy score

---

## 6. 后续最可能发生变化的地方
最可能在 v1.0.3 或后续版本发生变化的部分包括：

1. `Host_defense_counterdefense` 的内部组织
2. `Transcription_factor` 的 subtype 化
3. `Peptidoglycan_degradation` 的树外 timing/role 标注
4. `DNA_injection_internal_delivery` 的 role-type 标注
5. 从 `parent_only` 中升级出新的 L3
6. 从 `defer/open_set` 中识别出新的 candidate_new_leaf

---

## 7. 当前不建议轻易动的地方
以下部分当前不建议继续频繁大改：

- L1 顶层问题域
- L2 全部 parent-only 的原则
- 当前 L3 白名单整体框架
- 多标签节点的正式地位
- “先训练再反向修 ontology”的路线

这些是当前稳定骨架。

---

## 8. 监控指标建议
后续训练和 ontology 迭代时，建议重点监控：

- 哪些 L3 类总混淆
- 哪些 parent-only 类内部 embedding 明显分簇
- 哪些 defer/open_set term 高频且稳定聚类
- 哪些 multilabel 类 secondary coverage 不足
- 哪些类只依赖 context，而缺乏单蛋白可学性

---

## 9. 当前最关键的风险管理原则
### 原则 1
不要为了 ontology 的纯度，牺牲真实 annotation 可映射性。

### 原则 2
不要把 open-set 视为失败样本。

### 原则 3
不要把 current practical mixed leaf 过早拆掉。

### 原则 4
不要在第一版模型之前无休止改树。

### 原则 5
把真正的高风险问题记录在 rule layer 和 training layer，而不是全塞回树里。

---

## 10. 最重要的一句话
当前项目最大的风险，不是“树不够漂亮”，而是：

> **在真实 annotation 证据不足的情况下，过早把复杂语义硬编码进树，导致映射噪声、训练噪声和解释噪声同时放大。**
