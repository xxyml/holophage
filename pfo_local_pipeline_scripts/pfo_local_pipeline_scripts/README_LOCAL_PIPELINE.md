# 本地数据处理脚本骨架

这套脚本是给 **holophage / PFO v1.0.2** 项目准备的本地可执行骨架。

## 目录
- `config.yaml`：路径、列名和切分参数配置
- `01_inspect_columns.py`：检查大文件列名和样本格式
- `02_build_standardized_protein_table.py`：构建标准化蛋白主表
- `03_map_proteins_to_pfo.py`：把蛋白主表映射到 PFO v1.0.2
- `04_build_long_multilabel_table.py`：生成 long-format 多标签表
- `05_build_task_datasets.py`：生成 L1/L2/L3/open-set 任务表
- `06_dataset_sanity_check.py`：生成数据统计报告
- `07_build_split.py`：按 genome 切分 train/val/test
- `utils.py`：公共函数

## 使用顺序
1. 先编辑 `config.yaml`
2. 运行 `python 01_inspect_columns.py`
3. 根据输出确认列名后，再运行：
   - `python 02_build_standardized_protein_table.py`
   - `python 03_map_proteins_to_pfo.py`
   - `python 04_build_long_multilabel_table.py`
   - `python 05_build_task_datasets.py`
   - `python 06_dataset_sanity_check.py`
   - `python 07_build_split.py`

## 依赖
```bash
pip install pandas pyyaml scikit-learn tabulate
```

## 说明
- 这套脚本默认基于 **PFO v1.0.2**
- 当前脚本优先支持：
  - annotation 归一化
  - 蛋白级主表标准化
  - 映射表对接
  - multilabel 展开
  - 任务表生成
  - genome-aware split
- 如果后续你要接 sequence / structure embedding，只需要在标准化主表或训练表里增加相应列即可
