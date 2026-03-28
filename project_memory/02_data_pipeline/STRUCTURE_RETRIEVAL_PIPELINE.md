# Structure Retrieval Pipeline

更新时间：2026-03-26

## 1. 目标

当前结构链分成两层：

1. 现成结构回收
2. 缺口结构补算

正式主键：

- `exact_sequence_rep_id`

第一轮重点目标：

- `trainable_core` 的 `173,866` 条 exact unique sequence

长期目标：

- 全量 `976,210` 条 exact unique sequence

## 2. 当前结论

- 没有查到独立公开的 “INPHARED 全量结构数据库”
- `INPHARED 1419` 只是小规模 benchmark / seed set
- 更接近全量 phage 结构库的公开资源是 `phold Search DB 1.36M`
- 当前本地已有两批 PDB 可作为 bootstrap 结构资产，但需要标准化后才能接训练

## 3. 现成结构优先级

1. 本地已有结构资产
2. `phold Search DB 1.36M`
3. `AFDB`
4. `BFVD`
5. `Viro3D`

说明：

- `AFDB > BFVD > Viro3D` 仍保留为“在线直连来源优先级”
- 但对当前项目整体覆盖率而言，`phold Search DB 1.36M` 比 `INPHARED 1419` 更关键
- `phold Search DB 1.36M` 的 Zenodo 记录为约 `42.7 GB` 单 tar 包，适合先做下载 dry-run 和本地磁盘评估
- 基于 `PHROG` 生成的 `phold_retrieval_plan.tsv` 是 “candidate for phold search”，不是“已经 exact 命中”

## 4. 本地已有结构资产

当前已确认两批本地 PDB：

- `D:\data\ai4s\dataset_empathi\HoloPhage\data\400_1500`
- `D:\data\ai4s\dataset_empathi\dataset\data\pdb_storage`

已知不一致：

- 置信度标尺不一致：一批接近 `0-100 pLDDT`，一批接近 `0-1`
- 残基编号起点不一致：`0` vs `1`
- header 记录不一致：是否有 `PARENT N/A`
- 文件名是 `protein_id`，不是 `exact_sequence_rep_id`

因此必须先做：

- `local_structure_manifest.tsv`
- `all_exact_structure_status.tsv`
- `missing_exact_all.tsv`
- `missing_exact_trainable_core.tsv`

## 5. 目录与产物

结构脚本目录：

- [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline)

结构产物目录：

- [structures](D:/data/ai4s/holophage/structures)

关键产物：

- `structures/manifests/structure_target_manifest.tsv`
- `structures/manifests/local_structure_manifest.tsv`
- `structures/manifests/all_exact_structure_status.tsv`
- `structures/manifests/missing_exact_all.tsv`
- `structures/manifests/missing_exact_trainable_core.tsv`
- `structures/manifests/phold_retrieval_plan.tsv`

## 6. 当前默认不做

- 不把 `INPHARED 1419` 误当作全量 phage 结构库
- 不把现有不同来源 PDB 直接混入训练而不做标准化
- 不逐条在线提交结构预测 API 作为主方案
