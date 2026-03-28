# 数据处理规范（DATA_PROCESSING_SPEC）

## 1. 文档目的
本文件定义从原始 annotation 统计表到最终训练输入表的完整数据处理流程。  
目标是确保：

- 不同脚本和不同阶段对同一字段解释一致
- annotation 归一化规则稳定
- 多标签扩展规则可复现
- 训练集与统计分析使用同一套映射逻辑

---

## 2. 原始输入
当前核心原始输入包括：

- `phrog_annotation_protein_count.tsv`
- `phrog_annot_v4.tsv`
- 现有映射表（如 `PFO_v1_0_2_remapped_729_terms.csv`）

其中：
- `phrog_annotation_protein_count.tsv` 是主要统计输入
- `phrog_annot_v4.tsv` 用作术语来源与背景参考
- `PFO_v1_0_2_remapped_729_terms.csv` 是当前正式映射基准

---

## 3. 数据处理总体流程

### Step 1：读取原始 annotation 统计表
输入字段通常至少包括：
- `annotation`
- `protein_count`
- `percent`

输出：
- 原始 term 表

### Step 2：annotation 归一化
对 `annotation` 文本进行规则化处理：
- 去除首尾空格
- 统一大小写策略（建议保留原文，同时新增 normalized 版本）
- 统一连字符/斜杠/分号风格
- 规范常见变体拼写
- 处理空白 annotation 和 `<no_phrog_mapping>`

输出：
- `annotation_raw`
- `annotation_normalized`

### Step 3：映射到 PFO v1.0.2
依据当前正式映射表，将 `annotation_normalized` 映射到：
- `level1_direct`
- `level2_primary`
- `node_primary`
- `status`
- `multi_label_flag`
- `secondary_level1`
- `secondary_level2`
- `secondary_node`

输出：
- 主映射表

### Step 4：补充训练相关字段
根据节点表和训练策略补充：
- `dominant_modality`
- `parent_fit`
- `is_open_set`
- `is_parent_only`
- `is_multilabel`

输出：
- 训练准备表

### Step 5：多标签展开
对于 `multi_label_flag = yes` 且 secondary 存在的记录，生成：
- wide 版（保留 primary / secondary 字段）
- long 版（每个 label 一行）

输出：
- `training_labels_wide.csv`
- `training_labels_long.csv`

### Step 6：生成任务级数据集
分别生成：
- L1 训练表
- L2 训练表
- L3 core 训练表
- L3 multilabel 训练表
- open-set / unknown 表

输出：
- `dataset_l1.csv`
- `dataset_l2.csv`
- `dataset_l3_core.csv`
- `dataset_l3_multilabel.csv`
- `dataset_open_set.csv`

---

## 4. annotation 归一化规范

### 4.1 保留原始文本
必须保留原始 `annotation`，不得覆盖。

### 4.2 建议新增 normalized 字段
例如：
- 全部去掉额外空格
- `anti restriction` → `anti-restriction`
- `tailspike` → `tail spike`（仅在规则明确时）
- `no_phrog_mapping` 与 `<no_phrog_mapping>` 统一

### 4.3 不要过度归一化
如果归一化会引入语义风险，则应保守处理。  
例如：
- `associated`
- `putative`
- `like`
- `possible`
不能简单删除。

---

## 5. 特殊输入处理

### 5.1 空白项
- 空字符串
- `unknown function`
- `hypothetical protein`
- `unresolved_blank_annotation`

处理原则：
- 不强行映射 L3
- 优先进入 open-set / weakly-resolved

### 5.2 no mapping
如：
- `<no_phrog_mapping>`
- `no_phrog_mapping`

处理原则：
- 进入 open-set
- 保留原始记录

### 5.3 associated-only terms
如：
- `CRISPR/Cas system associated`

处理原则：
- 优先 `defer`
- 不强行映射到具体叶子

---

## 6. 多标签展开规则

### 6.1 何时展开 secondary
仅当：
- `multi_label_flag = yes`
- 且 `secondary_node` 非空

才生成 secondary label 记录。

### 6.2 long-format 推荐结构
建议最终训练前转换为 long-format：

字段示例：
- `annotation`
- `node_name`
- `label_role`（primary / secondary）
- `level1`
- `level2`
- `status`

### 6.3 不强补 secondary
如果某个节点是 multilabel 类，但当前 term 没有明确 secondary，不应自动补 secondaries。

---

## 7. 训练数据集生成规则

### 7.1 L1 数据集
包含：
- trainable_core
- trainable_multilabel
- parent_only
- 一部分 defer（如果 coarse mapping 稳定）

不包含：
- 纯 open-set（除非做 unknown coarse task）

### 7.2 L2 数据集
包含：
- trainable_core
- trainable_multilabel
- parent_only
- 一部分 defer（如果 L2 合理）

### 7.3 L3 core 数据集
只包含：
- `status = trainable_core`

### 7.4 L3 multilabel 数据集
只包含：
- `status = trainable_multilabel`

### 7.5 open-set 数据集
包含：
- `status = open_set`
- 部分高风险 defer

---

## 8. 版本与输出管理

### 8.1 每次处理都应记录版本
建议字段：
- `ontology_version`
- `mapping_version`
- `data_processing_version`

### 8.2 每次处理都应输出日志
至少记录：
- 输入文件版本
- 处理脚本版本
- 新增/修改映射条目数
- 未匹配条目数
- 多标签展开条目数

---

## 9. 推荐输出文件
建议统一生成以下文件：

- `annotations_normalized.csv`
- `mapped_terms_primary.csv`
- `mapped_terms_multilabel_long.csv`
- `dataset_l1.csv`
- `dataset_l2.csv`
- `dataset_l3_core.csv`
- `dataset_l3_multilabel.csv`
- `dataset_open_set.csv`
- `processing_summary.json`

---

## 10. 最重要的一句话
数据处理的目标不是“尽快产出一个训练表”，而是：

> **保证从原始 annotation 到训练标签的每一步都可追踪、可复现、可审查。**
