# Structure Full Coverage Plan

更新时间：2026-03-26

## 1. 目标层级

结构全覆盖分成两个目标：

1. 训练优先目标
   - `trainable_core` exact unique sequence：`173,866`
2. 全库最终目标
   - 全量 exact unique sequence：`976,210`

## 2. 为什么不是直接重算全部

当前已经有一批现成结构资产：

- 本地两批 PDB
- `INPHARED 1419`
- `phold Search DB 1.36M`
- `AFDB / BFVD / Viro3D`

如果直接从零重算全部，会浪费已经存在的可回收结构。

## 3. 正式路线

### 阶段 A：盘点与标准化

- 扫描本地已有 PDB
- 映射 `protein_id -> exact_sequence_rep_id`
- 标准化 confidence scale
- 产出 exact 级覆盖表

### 阶段 B：现成结构回收

- 优先利用 `phold Search DB 1.36M`
- 其次补 `AFDB / BFVD / Viro3D`
- `INPHARED 1419` 仅作 seed / benchmark
- 先生成 `phold_retrieval_plan.tsv`，再决定是否下载完整 `42.7 GB` tar 包
- 注意：`phold_retrieval_plan.tsv` 代表“可优先进入 phold 搜索/回收流程的候选 exact 集”，不等于已经 exact 命中结构

### 阶段 C：缺口补算

- 对未命中的 exact sequences 建立缺口队列
- 新生成结构统一按同一管线、同一 schema 落盘
- 长期归档目标可以是 `mmCIF` 或统一的结构 manifest + feature store

## 4. 当前关键数字

- 全量 exact unique sequence：`976,210`
- `trainable_core` exact unique sequence：`173,866`
- 本地已有结构覆盖的 `trainable_core exact`：约 `31,762`
- 当前 `trainable_core exact` 结构缺口：约 `142,104`

## 5. 下一步动作

1. 运行 `build_local_structure_manifest.py`
2. 运行 `build_structure_gap_manifest.py`
3. 运行 `build_phold_retrieval_plan.py`
4. 用 `download_phold_search_db.py --dry-run` 做下载检查
5. 决定是否下载 / 接入 `phold Search DB 1.36M`
6. 在 exact 缺口清单上继续推进结构回收或预测
