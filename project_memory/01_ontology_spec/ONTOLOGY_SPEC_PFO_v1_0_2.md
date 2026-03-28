# PFO v1.0.2 本体规范（ONTOLOGY_SPEC_PFO_v1_0_2）

## 1. 文档目的
本文件给出当前正式推荐使用的 **PFO v1.0.2** 分类框架规范。  
它的目标不是定义一个“最终完美”的噬菌体蛋白本体，而是定义一个：

- 对真实 annotation term 友好
- 对映射规则友好
- 对模型训练友好
- 对后续迭代友好

的稳定工作版本。

## 2. 设计原则

### 2.1 三层结构
PFO v1.0.2 采用三层结构：

- **Level 1（L1）**：问题域 / 模块层
- **Level 2（L2）**：本体骨架 / 父类承接层
- **Level 3（L3）**：高置信可训练叶子层

### 2.2 L1 由 source term 直接决定
对于真实 annotation term 的映射，L1 不由 L2 自动反推，而是由 source term 本身直接决定。

### 2.3 L2 默认作为 scaffold
L2 的主要职责是：
- 承接宽类
- 做 coarse supervision
- 提供 L3 父类语义

L2 默认不与 L3 同权进入第一轮精细训练。

### 2.4 L3 只保留高置信叶子
只有那些：
- 功能边界较清楚
- family / source term 稳定
- 可相对稳定构造负样本
- 不只是 broad bucket
的节点才进入 L3。

### 2.5 正式承认多标签
对于结构角色 + 酶活、delivery + internal virion、anti-defense + context-heavy 等类，不再强制单标签。

### 2.6 open-set / defer 是正式组成部分
未进入 L3 的条目不是失败，而是本体设计的正式部分。

## 3. Level 1 定义
PFO v1.0.2 的 Level 1 共 7 类：

1. **Virion_morphogenesis**
2. **Genome_maintenance_propagation**
3. **Lifestyle_commitment_switching**
4. **Host_interface_entry**
5. **Gene_expression_reprogramming**
6. **Host_cell_exit**
7. **Auxiliary_metabolic_support**

### 3.1 Virion_morphogenesis
用于承接病毒粒子形成、结构构建和装配相关功能。

### 3.2 Genome_maintenance_propagation
用于承接复制、重组、DNA 修饰等与基因组维持和传播相关的功能。

### 3.3 Lifestyle_commitment_switching
用于承接整合、切除、溶原/裂解生活史切换等功能。

### 3.4 Host_interface_entry
用于承接宿主识别、进入、内部递送、宿主防御对抗等与感染前期界面相关的功能。

### 3.5 Gene_expression_reprogramming
用于承接转录调控、转录重编程和噬菌体自身表达机器相关功能。

### 3.6 Host_cell_exit
用于承接裂解、细胞壁降解、膜破坏等与感染后期释放相关功能。

### 3.7 Auxiliary_metabolic_support
用于承接辅助代谢、核苷酸补给和相关支持功能。

## 4. Level 2 定义
PFO v1.0.2 当前**正式训练口径**的 Level 2 共 **21 类**。  
这个数字必须与：

- `outputs/label_vocab_l2.json`
- `training_statistics.md`
- baseline 当前训练配置

保持一致，不再沿用旧的 “17 类” 表述。

### 4.1 Virion_morphogenesis
- **Capsid**
- **Tail**
- **Connector_complex**
- **Head_assembly_packaging**

### 4.2 Genome_maintenance_propagation
- **DNA_replication**
- **DNA_recombination**
- **DNA_modification**

### 4.3 Lifestyle_commitment_switching
- **Integration_excision_control**
- **Lysogeny_lytic_switch_regulation**

### 4.4 Host_interface_entry
- **Host_recognition**
- **DNA_injection_internal_delivery**
- **Host_defense_counterdefense**
- **Entry_blocking_exclusion**

### 4.5 Gene_expression_reprogramming
- **Transcription_factor**
- **Phage_transcription_machinery**
- **Protein_RNA_processing**
- **Host_takeover_interference**

### 4.6 Host_cell_exit
- **Peptidoglycan_degradation**
- **Membrane_disruption**
- **Host_cell_exit_broad**

### 4.7 Auxiliary_metabolic_support
- **Nucleotide_metabolism**

### 4.8 关于 L2 的解释
L2 不是“全都适合直接训练的功能类”，而是中层 scaffold。  
其中一部分宽类是有意保留的，因为真实 annotation 语言本来就大量停留在这个层次，例如：

- tail protein
- transcriptional regulator
- DNA binding protein
- HNH endonuclease
- exonuclease
- minor tail protein

同时，当前正式 L2 vocab 中保留了若干**训练上必要、但并不一定直接进入第一轮精细叶子训练**的 scaffold 节点，例如：

- `Entry_blocking_exclusion`
- `Host_takeover_interference`
- `Host_cell_exit_broad`

这些节点的意义主要是：

- 提供 coarse supervision
- 承接 `parent_only / defer / trainable_multilabel` 的父类监督
- 为后续 status-aware 训练扩展留接口

## 5. Level 3 定义
PFO v1.0.2 的 Level 3 采用“受限白名单”策略。  
当前建议的 L3 包括：

### 5.1 Virion_morphogenesis
- Major_capsid
- Minor_capsid
- Portal
- Head_tail_connector
- Scaffold_protein
- Head_maturation_protease
- Terminase_large
- Terminase_small
- Major_tail
- Tail_tube
- Tail_sheath
- Baseplate
- Tail_fiber
- Tail_spike

### 5.2 Genome_maintenance_propagation
- DNA_polymerase
- Helicase
- Primase
- Replication_initiator
- Annealing_protein
- DNA_methyltransferase

### 5.3 Lifestyle_commitment_switching
- Integrase
- Excisionase_or_recombinase
- CI_like_repressor
- Cro_like_regulator

### 5.4 Host_interface_entry
- Anti_restriction
- Anti_CRISPR
- Superinfection_exclusion
- Internal_virion_protein
- DNA_ejection_protein

### 5.5 Gene_expression_reprogramming
- Transcriptional_activator
- RNA_polymerase

### 5.6 Host_cell_exit
- Endolysin
- Cell_wall_depolymerase
- Holin
- Spanin

### 5.7 Auxiliary_metabolic_support
- Ribonucleotide_reductase

## 6. 节点状态（status）定义
PFO v1.0.2 的节点/样本状态包括：

- **trainable_core**：适合直接作为主监督叶子。
- **trainable_multilabel**：适合训练，但不能假设互斥单标签。
- **parent_only**：适合做 L2/L1 监督，不进入第一轮 L3 主任务。
- **defer**：当前先延后，不进入主训练。
- **open_set**：当前归为未知/弱解析/未映射层，不强行归类。

## 7. 多标签原则
以下节点默认允许多标签或 secondary mapping：

- Tail_spike
- Cell_wall_depolymerase
- Internal_virion_protein
- DNA_ejection_protein
- Anti_restriction
- Anti_CRISPR
- Superinfection_exclusion

### 7.1 典型多标签模式
#### 结构角色 + 酶活
例如：
- tail associated lysin
- tail spike protein with colonic acid degradation activity
- baseplate hub and tail lysozyme

#### internal virion / delivery 交叉
例如：
- pilot protein for DNA ejection
- internal virion protein with endolysin domain

#### anti-defense / entry blocking / context-heavy
例如：
- superinfection exclusion
- sie-like proteins
- cor-like exclusion proteins

## 8. 树外属性（推荐）
为了避免把所有复杂语义都塞进树里，建议对节点额外维护以下属性：

- `primary_axis`
- `dominant_modality`
- `secondary_modalities`
- `requires_multimodal_evidence`
- `allow_multilabel`
- `parent_fit`
- `negative_sampling_rule`

这些字段不属于树本身，但对训练和解释非常重要。

## 9. 不进入当前 L3 的典型条目
以下类型通常不建议直接进入 L3：

### 9.1 broad terms
- tail protein
- capsid protein
- DNA metabolism protein
- transcriptional regulator

### 9.2 weak / associated-only terms
- CRISPR/Cas system associated
- putative membrane protein
- DNA-binding protein
- hypothetical protein

### 9.3 currently unresolved / open-set
- no_phrog_mapping
- unresolved_blank_annotation
- conserved_hypothetical_phage_protein
- putative_virion_associated_unknown

## 10. 文本版树结构图

### L1: Virion_morphogenesis
- L2: Capsid
  - L3: Major_capsid
  - L3: Minor_capsid
- L2: Tail
  - L3: Major_tail
  - L3: Tail_tube
  - L3: Tail_sheath
  - L3: Baseplate
  - L3: Tail_fiber
  - L3: Tail_spike
- L2: Connector_complex
  - L3: Portal
  - L3: Head_tail_connector
- L2: Head_assembly_packaging
  - L3: Scaffold_protein
  - L3: Head_maturation_protease
  - L3: Terminase_large
  - L3: Terminase_small

### L1: Genome_maintenance_propagation
- L2: DNA_replication
  - L3: DNA_polymerase
  - L3: Helicase
  - L3: Primase
  - L3: Replication_initiator
- L2: DNA_recombination
  - L3: Annealing_protein
- L2: DNA_modification
  - L3: DNA_methyltransferase

### L1: Lifestyle_commitment_switching
- L2: Integration_excision_control
  - L3: Integrase
  - L3: Excisionase_or_recombinase
- L2: Lysogeny_lytic_switch_regulation
  - L3: CI_like_repressor
  - L3: Cro_like_regulator

### L1: Host_interface_entry
- L2: Host_recognition
- L2: DNA_injection_internal_delivery
  - L3: Internal_virion_protein
  - L3: DNA_ejection_protein
- L2: Host_defense_counterdefense
  - L3: Anti_restriction
  - L3: Anti_CRISPR
  - L3: Superinfection_exclusion
- L2: Entry_blocking_exclusion

### L1: Gene_expression_reprogramming
- L2: Transcription_factor
  - L3: Transcriptional_activator
- L2: Phage_transcription_machinery
  - L3: RNA_polymerase
- L2: Protein_RNA_processing
- L2: Host_takeover_interference

### L1: Host_cell_exit
- L2: Peptidoglycan_degradation
  - L3: Endolysin
  - L3: Cell_wall_depolymerase
- L2: Membrane_disruption
  - L3: Holin
  - L3: Spanin
- L2: Host_cell_exit_broad

### L1: Auxiliary_metabolic_support
- L2: Nucleotide_metabolism
  - L3: Ribonucleotide_reductase

## 11. 版本定位
PFO v1.0.2 的定位不是“终局 ontology”，而是：

- 当前最稳的 mapping 版本
- 当前最适合第一版模型训练的版本
- 后续迭代修 ontology 的基础版本

## 12. 最重要的一句话
PFO v1.0.2 的核心不是让树看起来完美，而是让它同时满足：

- 真实 annotation 可映射
- 模型训练可执行
- 多标签可表达
- unknown 可承认
- 后续版本可升级
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
