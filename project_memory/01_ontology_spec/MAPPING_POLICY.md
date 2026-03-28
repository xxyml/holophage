# 映射策略（MAPPING_POLICY）

## 1. 文档目的
本文件用于定义：

- 真实 annotation term 如何映射到 PFO v1.0.2
- 什么情况下给 primary label
- 什么情况下给 secondary label
- 什么情况下只停留在 L2 / parent-only
- 什么情况下 defer / open-set

## 2. 基本原则

### 2.1 Level 1 由 source term 直接决定
Level 1 不能由 Level 2 机械反推。  
必须根据 source term 的直接语义决定问题域。

### 2.2 Level 2 作为 scaffold
Level 2 的作用主要是承接和过渡。  
即使某个 term 没法进入 L3，也应尽量先找到合理的 L2。

### 2.3 Level 3 只给高置信 term
如果一个 source term：
- 太宽
- 太弱
- 只是 “associated”
- 或需要过度解释才能落到某个叶子

则不应强行进 L3。

### 2.4 多标签优于误判
对于显式双重语义 term，应优先考虑：
- primary label + secondary label
而不是硬塞成单标签。

### 2.5 defer / open-set 是合法结果
如果一个 term 当前证据不足，不应被“为了完整性”强行归类。

## 3. Level 1 决定规则（高层）

### 3.1 Virion_morphogenesis
当 term 明确指向：
- capsid
- portal
- neck
- connector
- head assembly
- packaging motor / terminase
- tail structural component

但不主要表达宿主进入、裂解酶活或 host defense 行为时，优先落到这里。

### 3.2 Genome_maintenance_propagation
当 term 明确指向：
- polymerase
- helicase
- primase
- replication initiation
- recombination / annealing
- DNA modification

优先落到这里。

### 3.3 Lifestyle_commitment_switching
当 term 明确指向：
- integrase
- excisionase
- recombination directionality
- CI-like repressor
- Cro-like regulator
- lysogeny/lytic switch

优先落到这里。

### 3.4 Host_interface_entry
当 term 明确指向：
- host recognition
- receptor binding
- internal virion / pilot / ejection
- anti-restriction
- anti-CRISPR
- superinfection exclusion

优先落到这里。

### 3.5 Gene_expression_reprogramming
当 term 明确指向：
- transcriptional activator / regulator
- sigma-like factor
- anti-termination
- RNA polymerase
- RNA processing / translation repressor

优先落到这里。

### 3.6 Host_cell_exit
当 term 明确指向：
- endolysin
- holin
- spanin
- lysin
- lysozyme
- transglycosylase
- depolymerase with wall degradation implication

优先落到这里。

### 3.7 Auxiliary_metabolic_support
当 term 明确指向：
- ribonucleotide reductase
- dNTP biosynthesis / salvage
- nucleotide metabolism support

优先落到这里。

## 4. primary label 规则

### 4.1 具体酶活优先于模糊结构角色
如果一个词条同时包含：
- 明确酶活（如 lysin / lysozyme / transglycosylase / endolysin）
- 与结构/位置相关的词（如 tail / baseplate / internal virion）

则 primary label 优先给：
- 具体的分子功能（通常是 Cell_wall_depolymerase）
secondary label 再保留结构/位置语义。

### 4.2 明确机制优先于 broad bucket
例如：
- `anti-restriction protein` → Anti_restriction
而不是笼统落到 Host_defense_counterdefense

### 4.3 明确 machinery 优先于一般调控
例如：
- `phage RNA polymerase` → RNA_polymerase
而不是泛化 Transcription_factor

### 4.4 明确 lifestyle switch 优先于一般 recombination
例如：
- `integrase`
- `excisionase`
应优先落到 Lifestyle_commitment_switching，而不是继续混在 DNA_recombination。

## 5. secondary label 规则

### 5.1 应给 secondary label 的情形
#### A. 结构角色 + 酶活
例如：
- tail associated lysin
- baseplate hub and tail lysozyme
- tail spike protein with colonic acid degradation activity
- tail injection transglycosylase

#### B. delivery / internal virion 双重语义
例如：
- pilot protein for DNA ejection
- internal virion protein with endolysin domain
- DNA ejection protein

#### C. practical mixed term
当词条本身已明确显示两个独立轴时，应保留 secondary。

### 5.2 不应强补 secondary 的情形
如果词条只写了：
- tail spike protein
- internal virion protein
- transglycosylase
- DNA transfer protein

但没有足够信息支持第二功能轴，则不要为了“多标签完整性”硬补 secondary。

## 6. parent-only 规则
以下类型通常只停留在 L2 或作为 parent-only：

### 6.1 宽类
- Tail
- Capsid
- DNA_recombination
- Transcription_factor
- Nucleotide_metabolism

### 6.2 真实 annotation 中高频但不够细的类
- minor tail protein
- transcriptional regulator
- DNA-binding protein
- generic nuclease
- virion structural protein

### 6.3 尚不适合稳定拆成叶子的类
- Protein_RNA_processing 相关广义项
- 某些 host takeover / host physiology modulation broad terms

## 7. defer 规则
以下情况优先 defer：

### 7.1 only-associated terms
- CRISPR/Cas system associated
- phage-associated unknown regulator

### 7.2 方向不清的弱功能项
- dGTPase inhibitor; target for F exclusion
- broad membrane-associated small protein

### 7.3 当前树中无合适 L3 的机制项
- restriction enzyme I
- restriction enzyme III

### 7.4 过度解释风险高的 broad enzyme labels
- generic endonuclease
- generic DNA-binding protein
- generic transcription regulator

## 8. open-set 规则
以下直接视为 open-set / unknown：

- no_phrog_mapping
- unresolved_blank_annotation
- conserved_hypothetical_phage_protein
- putative_membrane_protein
- putative_virion_associated_unknown

这些不能强行进入 L3。

## 9. 典型映射示例

### 9.1 `tail associated lysin`
- primary_level1 = Host_cell_exit
- primary_level2 = Peptidoglycan_degradation
- primary_level3 = Cell_wall_depolymerase
- secondary_level1 = Host_interface_entry
- secondary_level2 = Host_recognition
- secondary_level3 = Tail_spike

### 9.2 `pilot protein for DNA ejection`
- primary_level1 = Host_interface_entry
- primary_level2 = DNA_injection_internal_delivery
- primary_level3 = DNA_ejection_protein
- secondary_level1 = Host_interface_entry
- secondary_level2 = DNA_injection_internal_delivery
- secondary_level3 = Internal_virion_protein

### 9.3 `restriction enzyme I`
- primary_level1 = Genome_maintenance_propagation
- primary_level2 = DNA_recombination
- primary_level3 = 空
- status = defer

### 9.4 `tail spike protein`
- primary_level1 = Host_interface_entry
- primary_level2 = Host_recognition
- primary_level3 = Tail_spike
- secondary = 空

### 9.5 `tail spike protein with colonic acid degradation activity`
- primary_level1 = Host_cell_exit
- primary_level2 = Peptidoglycan_degradation
- primary_level3 = Cell_wall_depolymerase
- secondary_level1 = Host_interface_entry
- secondary_level2 = Host_recognition
- secondary_level3 = Tail_spike

## 10. 需要额外记录的字段
建议在映射表中保留以下字段：

- `annotation`
- `protein_count`
- `percent`
- `level1_direct`
- `level2_primary`
- `node_primary`
- `status`
- `multi_label_flag`
- `secondary_level1`
- `secondary_level2`
- `secondary_node`
- `dominant_modality`
- `note`
- `secondary_reason`

如果后续继续细化，还建议增加：
- `parent_fit`
- `negative_sampling_rule`
- `source_term_examples`
- `heterogeneity_flag`
- `training_risk`

## 11. 最重要的一句话
映射的目标不是把每个词条“塞进一棵完美树”，而是：

> **在不引入过度解释的前提下，为每个真实 annotation 找到最合理的 primary 落点，并在必要时显式保留多标签和未决状态。**
