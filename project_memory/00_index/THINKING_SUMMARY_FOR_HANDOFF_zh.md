# 思考过程与交接摘要（THINKING_SUMMARY_FOR_HANDOFF）

## 1. 这份文档的作用
这份文档不是正式规范，而是对本项目思考过程的浓缩总结。目标是让新的窗口、新协作者或未来的自己，快速理解：
- 这一路是怎么想过来的
- 为什么做了现在这些选择
- 哪些地方反复争论过
- 目前哪些结论是强共识
- 哪些只是当前最优妥协

## 2. 项目最初的核心问题
项目一开始面对的是一个很现实的问题：

> 手里有 700+ 个真实噬菌体蛋白 annotation term，但这些词条的粒度、质量、机制清晰度和多标签程度都不一致。我们需要一个既适合映射、又适合训练、还可迭代的分类框架。

最开始最直观的方案是直接找一个现成分类体系，例如：
- PFO 原始版本
- PFO-2
- PFO_v3
- EmPATHi

但很快发现，没有哪一套可以直接拿来做训练任务。

## 3. 最早出现的核心冲突
最早的冲突不是“树怎么画”，而是：

### 3.1 数据世界 vs ontology 世界不一致
真实 annotation term 里有很多是：
- 宽类（例如 `tail protein`）
- 模糊类（例如 `DNA-binding protein`）
- 混合类（例如 `tail associated lysin`）
- 弱证据类（例如 `putative membrane protein`）

而理想 ontology 想要的是：
- 每个节点语义纯
- 父子关系清楚
- 每个叶子都是可训练原子功能

这两个世界本来就不一致。

### 3.2 数据库映射需求 vs 模型训练需求不一致
有些节点很适合“给数据库里东西找个架子放着”，但不适合拿来做模型监督。

这引出了一个关键理解：
> **适合数据库映射 ≠ 适合直接训练监督**

这个认识后来成为整个项目最关键的思想之一。

## 4. 为什么从“全功能树”转向“三层框架”
在反复讨论中，逐渐形成了一个共识：

### 不应该把所有功能词条都当成 Level 3 叶子
因为这样会造成：
- broad term 被硬塞成细叶子
- weak term 被过度解释
- 多标签结构被强行单标签化
- 训练噪声过大

所以逐步形成了：
- **Level 1**：问题域 / 模块层
- **Level 2**：scaffold / parent-only 层
- **Level 3**：高置信可训练叶子层

这个思路受到了 Empathi 训练逻辑的启发，但又没有简单照抄 Empathi。

## 5. 为什么后面又强调 “Level 1 由 source term 直接决定”
中间一度出现过一种习惯性做法：
- 先决定 Level 2
- 再由 Level 2 反推出 Level 1

但随着映射工作深入，发现这个做法经常出错。因为真实 annotation term 的语义往往比 Level 2 更复杂。

例如：
- `tail associated lysin`
- `internal virion protein with endolysin domain`
- `tail injection transglycosylase`

这些词条不能只靠父类 scaffold 去决定顶层问题域。于是形成了一个明确结论：

> **Level 1 必须由具体 source term 本身直接决定，而不是由 Level 2 机械反推。**

## 6. 关于多标签问题，是怎么想通的
一开始虽然知道有些类“好像可能多标签”，但映射表仍然是单标签主映射，导致一个疑问不断出现：

> 如果 `trainable_multilabel` 真有意义，为什么表里看不出双标签？

后来逐渐理清楚：

### 6.1 当前主映射表本质上是 primary mapping table
也就是说，一行 term 先给一个主标签。

### 6.2 但 ontology 层面要提前标出哪些类不能被假装成纯单标签
这就形成了 `trainable_multilabel` 的意义：
- 它不是说数据表已经展开成 multi-hot
- 而是在提醒后续训练逻辑和 secondary mapping 逻辑

### 6.3 显式双标签场景
后来进一步明确了哪些词条确实应该直接显式双标签，例如：
- `tail spike protein with colonic acid degradation activity`
- `internal virion protein with endolysin domain`
- `baseplate hub and tail lysozyme`
- `tail associated lysin`
- `tail injection transglycosylase`

这时，multilabel 不再只是一个概念，而开始进入映射表。

## 7. 为什么最终不建议“先做完美 ontology 再训练”
这是一个反复出现的问题，也是一个关键转折点。

一开始很容易有一种冲动：
> 既然 ontology 还有不完美，那是不是应该继续修到很完整，再开始训练？

但反复分析后形成了一个很明确的结论：

### 7.1 真实 annotation 世界本来就不会支持一个“完美”的第一版 ontology
因为：
- 粒度不齐
- 词义混合
- 数据库语言风格不一致
- unknown 太多

### 7.2 很多 ontology 问题只有模型跑起来后才会暴露
例如：
- 哪些类总被混淆
- 哪些 broad bucket 其实可以拆
- 哪些 defer 项形成新 cluster
- 哪些类在 embedding 空间里根本不稳

### 7.3 因此更好的路线是
- 冻结一个稳定版本
- 先训练模型
- 再反向修 ontology

最终形成的共识是：
> **不要在第一轮把分类法追求到完美；应该先基于一个稳定版本训练模型，再迭代本体。**

## 8. 为什么后来选择 v1.0.2 而不是继续在两个版本之间来回
后期的主要对比对象有两个：
- alpha revised：更工程、更直白、主标签更果断
- improved / v1.1：更谨慎、更承认多标签、更避免过度解释

最后的判断不是“谁绝对更强”，而是：
- alpha revised 更像稳定工程基线
- v1.1 更像成熟 ontology 草案

于是最终没有直接二选一，而是做了一个融合：

## PFO v1.0.2
它的设计目标是：
- 保留 v1.1 的顶层问题域
- 保留 alpha revised 在结构件上的 practical 主判定
- 对多标签和弱证据词条使用 v1.1 式谨慎逻辑
- 不为了追求树的完美，牺牲你已有 700+ 真实词条的可映射性

所以 v1.0.2 是一个“折中但可执行”的版本。

## 9. 到目前为止形成的强共识
以下结论可以视为当前强共识：
1. 项目不做 flat 729 类单标签分类
2. Level 1 / 2 / 3 三层结构是必要的
3. Level 2 默认是 parent-only
4. Level 3 只放高置信叶子
5. `Tail_spike`、`Cell_wall_depolymerase` 等必须允许多标签
6. open-set / defer 是正式组成部分
7. 训练应先于 ontology 完美化
8. 当前应先冻结 v1.0.2 作为稳定版本

## 10. 当前仍属于“最优妥协”而非终局答案的地方
这些地方目前仍然是“当前最好用”，而不是完全解决：
- `Host_defense_counterdefense` 仍偏宽
- `Transcription_factor` 内部粒度仍不均
- `Peptidoglycan_degradation` 仍是 practical mixed bucket
- `DNA_injection_internal_delivery` 仍偏 context-heavy
- `Protein_RNA_processing` 目前仍缺乏稳定 L3 支撑

这些都属于后续版本迭代的重点。

## 11. 对未来自己的提醒
如果你在未来再看这个项目，最重要的是记住：

- 不要重新回到“为了树的纯度，牺牲真实 annotation 可映射性”
- 不要重新回到“先做完美 ontology，再训练模型”
- 不要把 open-set 当成垃圾桶
- 不要忽视 `parent_only` 的训练价值
- 不要把 `trainable_multilabel` 再偷换回 flat single-label

## 12. 最终一句话
这个项目到目前为止最重要的思想，不是某个具体节点该叫什么名字，而是：

> **承认真实 annotation 的脏与混合性，用分层、分状态、多标签和 open-set 来管理复杂性，而不是用一棵看似完美的树去掩盖它。**
