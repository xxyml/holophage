# Structure Pipeline

这个目录负责两类事：

1. 现成结构命中筛查与按需下载
2. 本地已有结构资产盘点与缺口清单生成

当前正式口径：

- 目标集默认以 `exact_sequence_rep_id` 为主键
- 第一轮重点目标：`trainable_core`
- 现成结构优先级：`本地已有结构 > phold Search DB > AFDB > BFVD > Viro3D`
- 正式长期目标：覆盖 `976,210` 条 exact unique sequence

## 目录内脚本

1. `build_structure_targets.py`
2. `build_local_structure_manifest.py`
3. `build_structure_gap_manifest.py`
4. `build_phold_retrieval_plan.py`
5. `download_phold_search_db.py`
6. `extract_phold_subarchives.py`
7. `screen_structure_sources.py`
8. `select_canonical_structures.py`
9. `download_structures.py`

## 典型运行顺序

```powershell
conda run -n ai4s python D:\data\ai4s\holophage\structure_pipeline\build_structure_targets.py
conda run -n ai4s python D:\data\ai4s\holophage\structure_pipeline\build_local_structure_manifest.py
conda run -n ai4s python D:\data\ai4s\holophage\structure_pipeline\build_structure_gap_manifest.py
conda run -n ai4s python D:\data\ai4s\holophage\structure_pipeline\build_phold_retrieval_plan.py
conda run -n ai4s python D:\data\ai4s\holophage\structure_pipeline\download_phold_search_db.py --dry-run
conda run -n ai4s python D:\data\ai4s\holophage\structure_pipeline\extract_phold_subarchives.py --dry-run --limit-phrogs 100
conda run -n ai4s python D:\data\ai4s\holophage\structure_pipeline\screen_structure_sources.py --limit 1000
conda run -n ai4s python D:\data\ai4s\holophage\structure_pipeline\select_canonical_structures.py
conda run -n ai4s python D:\data\ai4s\holophage\structure_pipeline\download_structures.py --limit 100
```

## 当前现实约束

- 本地已有两批 PDB 资产来自不同生成渠道，置信度标尺不一致
- 当前主表中没有大量可直接命中的 UniProt / AFDB / BFVD protein-level identifier
- `INPHARED 1419` 只能作为小规模 benchmark/seed，不是全量 phage 结构库
- 要逼近 `976,210` 条 exact 全覆盖，必须走：
  - 现成结构回收
  - 统一 manifest
  - 剩余缺口再批量预测

## 关键产物

- `structures/manifests/structure_target_manifest.tsv`
- `structures/manifests/local_structure_manifest.tsv`
- `structures/manifests/all_exact_structure_status.tsv`
- `structures/manifests/missing_exact_all.tsv`
- `structures/manifests/missing_exact_trainable_core.tsv`
- `structures/manifests/phold_retrieval_plan.tsv`
