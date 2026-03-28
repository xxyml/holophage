# 训练数据结构定义（TRAINING_DATA_SCHEMA）

## 1. 文档目的
本文件定义进入模型训练阶段的最终数据表结构。  
目标是让：

- ontology
- 映射表
- 多标签扩展
- 模型输入
- 数据切分

之间保持一致。

---

## 2. 建议的数据表层次
建议维护至少 4 层表：

1. **raw annotation table**
2. **mapped ontology table**
3. **training sample table (wide)**
4. **training label table (long, multilabel-ready)**

---

## 3. raw annotation table
表示最原始统计或输入表。  
建议字段：

- `annotation_raw`
- `annotation_normalized`
- `protein_count`
- `percent`
- `source_database`
- `source_version`

用途：
- 保留原始来源
- 不直接送入模型

---

## 4. mapped ontology table
表示 annotation 映射到 PFO 的结果。  
建议字段：

- `annotation_raw`
- `annotation_normalized`
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
- `ontology_version`
- `mapping_version`

用途：
- ontology 分析
- 覆盖率统计
- 人工审阅
- 训练标签生成的上游表

---

## 5. training sample table（wide）
这是最接近模型输入的主样本表。  
一行代表一个训练样本（蛋白或 annotation 实体）。

建议字段：

### 5.1 标识信息
- `sample_id`
- `protein_id`
- `genome_id`
- `contig_id`（可选）

### 5.2 生物序列信息
- `sequence`
- `sequence_length`

### 5.3 embedding / feature 路径
- `sequence_embedding_path`
- `structure_embedding_path`
- `context_embedding_path`（可选）
- `feature_json_path`（可选）

### 5.4 标签信息
- `level1_label`
- `level2_label`
- `node_primary`
- `status`
- `multi_label_flag`
- `secondary_nodes`（列表/JSON）

### 5.5 训练辅助字段
- `is_open_set`
- `is_parent_only`
- `is_multilabel`
- `split`
- `split_version`
- `ontology_version`

### 5.6 元信息
- `annotation_raw`
- `annotation_normalized`
- `protein_count`
- `note`

---

## 6. training label table（long）
用于多标签训练和长格式分析。  
一行表示一个样本与一个标签的关系。

建议字段：

- `sample_id`
- `node_name`
- `level1_label`
- `level2_label`
- `label_role`（primary / secondary）
- `status`
- `split`
- `is_positive`（通常为 1）
- `ontology_version`

优势：
- 适合 multilabel loss
- 适合分析每个标签的样本数
- 适合之后扩到 tertiary labels

---

## 7. 各任务专用数据表
从 wide / long 表进一步派生：

### 7.1 `dataset_l1.csv`
字段建议：
- `sample_id`
- `level1_label`
- `split`
- `input_paths...`

### 7.2 `dataset_l2.csv`
字段建议：
- `sample_id`
- `level2_label`
- `split`
- `input_paths...`

### 7.3 `dataset_l3_core.csv`
只保留 `status = trainable_core`  
字段建议：
- `sample_id`
- `node_primary`
- `split`
- `input_paths...`

### 7.4 `dataset_l3_multilabel.csv`
只保留 `status = trainable_multilabel`  
字段建议：
- `sample_id`
- `primary_node`
- `secondary_nodes`
- `split`
- `input_paths...`

### 7.5 `dataset_open_set.csv`
字段建议：
- `sample_id`
- `unknown_label`
- `split`
- `input_paths...`

---

## 8. secondary_nodes 推荐编码方式
建议用 JSON list 或分号分隔字符串，例如：

- `["Tail_spike"]`
- `["Internal_virion_protein"]`
- `[]`

不要在一个字段里混入 free text。

---

## 9. context 输入建议编码
如果使用 genome context，建议保存：

- `neighbor_ids`
- `neighbor_count`
- `window_size`
- `gene_order_info`

若上下游 embedding 已预先汇总，则可只存：
- `context_embedding_path`

---

## 10. 最小可用 schema
如果想尽快开训，最少应保证 wide 表里有这些字段：

- `sample_id`
- `protein_id`
- `genome_id`
- `sequence`
- `sequence_embedding_path`
- `structure_embedding_path`
- `level1_label`
- `level2_label`
- `node_primary`
- `status`
- `multi_label_flag`
- `secondary_nodes`
- `split`

---

## 11. 版本控制建议
每次更新训练表时，建议记录：
- `ontology_version`
- `mapping_version`
- `split_version`
- `data_schema_version`

---

## 12. 最重要的一句话
训练数据结构的设计原则不是“先把所有字段都堆进去”，而是：

> **确保同一个样本在 ontology、映射、切分和模型训练之间始终能被一致追踪。**
---
doc_status: active
source_of_truth_level: canonical
doc_scope: data_pipeline
owner_path: project_memory/02_data_pipeline
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
