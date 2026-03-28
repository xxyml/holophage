# 多标签策略（MULTILABEL_POLICY）

## 1. 文档目的
本文件专门定义 **PFO v1.0.2** 中“多标签”相关的规则。  
它回答的问题包括：

- 什么叫多标签
- 哪些节点属于 `trainable_multilabel`
- 什么情况下应给 secondary label
- 什么情况下虽然是多标签类，但当前 term 不强补 secondary
- 后续训练中如何处理多标签
- 多标签类的负样本该如何规避

---

## 2. 为什么需要单独的多标签策略
在噬菌体蛋白中，很多功能不是“互斥单角色”的。

常见情况包括：

### 2.1 结构角色 + 酶活共存
例如：
- tail associated lysin
- baseplate hub and tail lysozyme
- tail spike protein with colonic acid degradation activity
- tail injection transglycosylase

这些词条同时表达了：
- virion 结构/位置身份
- 明确酶学功能

### 2.2 delivery / internal virion 双重身份
例如：
- pilot protein for DNA ejection
- DNA ejection protein
- internal virion protein with endolysin domain

### 2.3 context-heavy 宿主对抗行为
例如：
- superinfection exclusion
- certain anti-defense small proteins

因此，如果仍强行把所有标签做成 flat 单标签，会导致：
- 标签信息丢失
- 相近类被错误当成互斥
- 训练时产生假负样本
- 模型学到“错误边界”

---

## 3. 什么叫 `trainable_multilabel`
`trainable_multilabel` 的意思不是：

> 这个类不重要，或者暂时不用训练。

而是：

> 这个类是值得训练的，但不能假设它与其他类严格互斥。

也就是说：

- 它是正式功能类
- 它进入 L3 训练
- 但训练目标应允许 multi-hot / primary + secondary
- 相近 cross-branch 类不能直接当硬负样本

---

## 4. 当前 PFO v1.0.2 中的 multilabel 节点
当前建议明确视为 `trainable_multilabel` 的节点包括：

- Tail_spike
- Cell_wall_depolymerase
- Internal_virion_protein
- DNA_ejection_protein
- Anti_restriction
- Anti_CRISPR
- Superinfection_exclusion

### 4.1 为什么不是所有看起来“有点混”的类都进 multilabel
因为多标签不能滥用。  
必须满足至少一条：

- 词条本身显式表达两个独立轴
- 节点机制上本来就高度交叉
- 已知 source term 在 annotation 中稳定呈现双重角色

否则就会把本来可以做主标签的类弄得过于含糊。

---

## 5. primary label 和 secondary label 的定义

### 5.1 primary label
primary label 表示：

- 当前最主要的语义落点
- 也是当前主映射表中的主标签
- 在没有充足 secondary 证据时，优先保留 primary

### 5.2 secondary label
secondary label 表示：

- 该 term 还具有一个足够明确的第二功能轴或结构轴
- 应显式记录，而不应只藏在 note 里

### 5.3 一个重要原则
> **不是所有 `trainable_multilabel` 类的每个 term 都必须有 secondary label。**

也就是说：

- 一个节点可能是 multilabel 类型
- 但具体某个 term 若证据不足，仍然只给 primary

---

## 6. 应明确添加 secondary label 的情形

## 6.1 结构角色 + 明确酶活
这些最典型，应显式多标签：

### 示例
- `tail associated lysin`
- `baseplate hub and tail lysozyme`
- `baseplate hub subunit and tail lysozyme`
- `tail spike protein with colonic acid degradation activity`
- `tail injection transglycosylase`
- `minor tail protein with lysin activity`
- `tail protein with lysin activity`
- `internal virion protein with endolysin domain`

### 推荐策略
通常：
- primary label 给**更明确的分子功能**
- secondary label 保留结构或 delivery 角色

即：
- `Cell_wall_depolymerase` 常做 primary
- `Tail_spike` / `Baseplate` / `Internal_virion_protein` 常做 secondary

---

## 6.2 delivery / internal virion 双重角色
### 示例
- `pilot protein for DNA ejection`
- `DNA ejection protein`

### 推荐策略
通常：
- `DNA_ejection_protein` 为 primary
- `Internal_virion_protein` 为 secondary（如果词条足够支持）

---

## 6.3 anti-defense / entry-blocking / context-heavy 重叠
### 示例
- `Cor superinfection exclusion protein`
- `superinfection exclusion SieA-like`
- 某些 membrane-associated exclusion proteins

### 推荐策略
目前以 primary label 为主。  
只有当 source term 足够明确时，才考虑 secondary context 标签。  
这一类不宜过度补 secondaries。

---

## 7. 不应强行补 secondary 的情形

以下 term 即便属于 multilabel node 所在类，也不建议强补 secondary：

### 7.1 只有结构身份，没有明确第二机制
- `tail spike protein`
- `major spike protein`
- `internal virion protein`

### 7.2 只有酶学词，没有明确 virion 身份
- `transglycosylase`
- 某些 generic hydrolase

### 7.3 只有 broad 行为词，没有足够机制支持
- `DNA transfer protein`
- 某些 vague anti-defense terms

在这些情况下，更稳的做法是：
- 只给 primary
- 在 note 中保留可能的 secondary 倾向
- 等后续结构或上下文证据补充后再决定

---

## 8. 多标签与训练格式的关系

## 8.1 当前映射表是什么
当前映射表本质上仍然是一个：

> **主映射表（primary mapping table）**

也就是说：
- 每个 term 至少有一个 primary label
- 某些 term 额外有 secondary label
- 它还不是完全展开的 long-format multi-hot 训练表

## 8.2 训练前建议的转换
在进入模型训练前，建议把带 secondary 的记录转换成：

### 方案 A：wide 格式
- primary node
- secondary node
- multi_label_flag

### 方案 B：long 格式（更推荐）
同一个 annotation 可以拆成多行：
- annotation | node | label_role = primary
- annotation | node | label_role = secondary

这样更适合后续 multilabel loss。

---

## 9. 多标签类的负样本规则

## 9.1 基本原则
对于 `trainable_multilabel`：
> **相近 cross-branch 类不应被轻易当成硬负样本。**

## 9.2 示例
### Tail_spike
不应直接把这些当硬负：
- Cell_wall_depolymerase
- generic receptor-binding protein
- tail_fiber（若 term 模糊）

### Cell_wall_depolymerase
不应直接把这些当硬负：
- Tail_spike
- virion-associated hydrolase
- tail associated lysin-like broad terms

### DNA_ejection_protein
不应直接把这些当硬负：
- Internal_virion_protein
- pilot protein-like terms
- virion delivery broad terms

### Anti_CRISPR
不应直接把这些当硬负：
- Anti_restriction
- weak anti-defense associated proteins
- unknown small defense-related proteins

---

## 10. 多标签类的评估建议
对于 multilabel 节点，不应只看 flat accuracy。  
建议使用：

- micro F1
- macro F1
- mAP
- label co-occurrence consistency
- pairwise confusion review

尤其要关注：
- primary/secondary 是否经常被反转
- 相邻 cross-branch 类是否被误判成互斥

---

## 11. 当前实践建议
### 第一阶段
先保留：
- primary label
- 显式 secondary label（仅对证据充分的词条）

### 第二阶段
在训练时使用：
- multilabel head
- multi-hot targets

### 第三阶段
根据模型结果，再决定是否扩大 secondary label 覆盖范围。

这样可以避免一开始就把所有“可能多标签”都展开，导致人工噪声过大。

---

## 12. 最重要的一句话
多标签策略的目标不是“尽可能给更多 secondary label”，而是：

> **只在 source term 本身已经明确显示双重语义时，保留 secondary；在不确定时，宁可先只保留 primary，也不要为了完整性强行补第二标签。**
