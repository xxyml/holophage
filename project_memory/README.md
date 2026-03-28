# project_memory

这个目录保存项目的正式文档、规则说明、规划记录和历史归档。

## 先读这里

如果你的目标是理解**当前 baseline runtime 主线**，不要先从旧 planning 文档开始，请先读：

1. [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
2. [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)
3. [ACTIVE_DOCS.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_DOCS.md)
4. [ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)

这四份文件定义：

- 当前哪一版是真的
- 当前 runtime 应该读哪些路径
- 哪些文档是 active runtime docs
- 哪些目录只是 support / reference / archive

## 目录说明

- [00_index](D:/data/ai4s/holophage/project_memory/00_index)
  - 项目总览、索引和交接思考
- [01_ontology_spec](D:/data/ai4s/holophage/project_memory/01_ontology_spec)
  - ontology、标签政策、设计规则
- [02_data_pipeline](D:/data/ai4s/holophage/project_memory/02_data_pipeline)
  - split、数据 schema、baseline 输入、训练边界、变更记录
- [03_tracking_tables](D:/data/ai4s/holophage/project_memory/03_tracking_tables)
  - 跟踪表和审阅过程材料
- [04_active_assets](D:/data/ai4s/holophage/project_memory/04_active_assets)
  - 当前 active manifest 和 runtime contract 的唯一入口
- [05_archive](D:/data/ai4s/holophage/project_memory/05_archive)
  - 历史材料与归档，不作为当前 runtime 真相源

## 当前阅读优先级

如果你是第一次接手项目，推荐顺序是：

1. [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
2. [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)
3. [ACTIVE_DOCS.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_DOCS.md)
4. [PROJECT_OVERVIEW_zh.md](D:/data/ai4s/holophage/project_memory/00_index/PROJECT_OVERVIEW_zh.md)
5. [BASELINE_INPUT_MANIFEST.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/BASELINE_INPUT_MANIFEST.md)
6. [TRAINING_TASK_BOUNDARY.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/TRAINING_TASK_BOUNDARY.md)

不要默认：

- 所有 planning 文档都与当前 runtime 同权
- 所有 changelog / schema / policy 文档都能单独定义当前主线
- 归档目录可以反推当前训练配置
