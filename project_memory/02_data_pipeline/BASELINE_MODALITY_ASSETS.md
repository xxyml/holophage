# Baseline Modality Assets

更新时间：2026-03-27

## 1. 当前正式 sequence 资产

标签主表：
- [training_labels_wide_with_split.csv](D:/data/ai4s/holophage/data_processed/training_labels_wide_with_split.csv)

sequence embedding 输入：
- [exact_sequence_embedding_input.parquet](D:/data/ai4s/holophage/embedding_pipeline/inputs/exact_sequence_embedding_input.parquet)

sequence embedding 输出：
- [embed_exact](D:/data/ai4s/holophage/embedding_pipeline/outputs/embed_exact)

模型目录：
- [prot_t5_xl_uniref50_bits](D:/data/ai4s/holophage/embedding_pipeline/models/prot_t5_xl_uniref50_bits)

正式口径：
- 一条 `exact_sequence_rep_id` 只算一次 sequence embedding
- `<=512 aa`：整条编码
- `>512 aa`：滑窗重叠后聚合

## 2. 当前结构资产层

结构脚本目录：
- [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline)

结构产物目录：
- [structures](D:/data/ai4s/holophage/structures)

结构主键：
- `exact_sequence_rep_id`

当前建议：
- 第一轮 baseline 不强依赖真实 PDB
- 结构端更适合改成 “sequence-derived structural embedding”

## 3. 键对应关系

实例级保留：
- `protein_id`
- `embedding_id = contig_id + "_" + gene_index`

sequence 正式查询键：
- `exact_sequence_rep_id`

这意味着：
- sequence embedding 复用 exact 序列
- context 与标签仍按实例级保留
- 结构增强如果接入，也应最终映射到 `exact_sequence_rep_id`

## 4. embedding 统一目录

- [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)

子目录说明：
- `scripts/`
- `inputs/`
- `models/`
- `outputs/`
- `logs/`
- `manifests/`
