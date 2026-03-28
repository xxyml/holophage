# 下一步任务计划（NEXT_ACTIONS_PLAN）

## 1. 文档目的
本文件用于明确基于当前 **PFO v1.0.2** 框架，下一阶段从数据处理到模型 baseline 训练的具体任务、顺序与负责人。  
目标是让项目从“设计阶段”顺利进入“执行阶段”，确保数据、训练和后续 ontology 修订可追踪、可复现。

---

## 2. 总体目标
- 完成训练数据落地（wide / long / L1/L2/L3 / open-set）
- 完成训练集、验证集、测试集切分（genome-aware + family-aware）
- 启动第一个可用 baseline 模型训练
- 初步统计每个任务的样本数和类别分布
- 准备 multilabel / unknown / parent-only 的后续审阅计划

---

## 3. 任务清单

### 3.1 数据处理任务
1. **生成训练输入表**  
   - 输入：`PFO_v1_0_2_remapped_729_terms.csv`、`phrog_annotation_protein_count.tsv`  
   - 输出：`training_labels_wide.csv`、`training_labels_long.csv`  
   - 处理：归一化 annotation、映射 L1/L2/L3、填充 multi_label / secondary fields

2. **生成 L1/L2/L3 / open-set 数据集**  
   - 输出：`dataset_l1.csv`、`dataset_l2.csv`、`dataset_l3_core.csv`、`dataset_l3_multilabel.csv`、`dataset_open_set.csv`  
   - 说明：确保每个样本的层级一致，parent-only 样本进入 L2/L1，defer/open-set 单独保存

3. **生成 split 文件**  
   - 按 **genome-aware + family-aware** 方式切分训练/验证/测试集  
   - 字段：`sample_id`、`split`、`split_version`  
   - 注意 multilabel 样本完整性和 context 泄漏

4. **生成训练统计报告**  
   - 输出：各 L1/L2/L3 类别的样本数、占比、长尾类别情况  
   - 用于 baseline 前的 sanity check

### 3.2 模型任务
1. **建立第一版 baseline**  
   - 模态：sequence embedding + structure embedding  
   - 输出头：L1、L2、L3 core  
   - 输入数据：wide 表  
   - 目标：确保模型能顺利收敛并输出可解释结果

2. **运行初步训练并评估**  
   - 输出：训练日志、loss 曲线、初步 confusion matrix  
   - 检查：
     - 样本是否正确映射
     - parent-only / multilabel / open-set 是否按计划进入训练

### 3.3 multilabel / open-set / parent-only 审阅任务
1. **处理 `unassigned_function_tracking_seeded_from_v1_0_2.csv`**  
   - 优先级：
     - 高频优先表 (`unassigned_tracking_highfreq_priority.csv`) 先审
     - 最可能升级新叶子表 (`unassigned_tracking_upgrade_priority.csv`) 后审
   - 记录人工复核结果到 `unassigned_function_tracking.csv`

2. **更新 `mapping_review_log.csv`**  
   - 每次修改 L1/L2/L3 mapping 时，必须写入
   - 保留理由、证据类型、置信度、批准状态、ontology 版本

### 3.4 baseline 结果分析任务
1. **统计 L1/L2/L3 样本覆盖率和 confusion matrix**  
2. **检查 multilabel / secondary label 学习情况**  
3. **分析 open-set / defer / parent-only 样本表现**  
4. **记录下一轮 ontology 升级候选条目**

---

## 4. 优先级和顺序
| 阶段 | 任务 | 输出文件 | 优先级 |
|---|---|---|---|
| 数据准备 | 生成 wide / long 表 | `training_labels_wide.csv`, `training_labels_long.csv` | 高 |
| 数据准备 | 生成 L1/L2/L3 / open-set 表 | `dataset_l1.csv`, `dataset_l2.csv`, `dataset_l3_core.csv`, `dataset_l3_multilabel.csv`, `dataset_open_set.csv` | 高 |
| 数据准备 | 切分 train/val/test | `split.csv` | 高 |
| 数据准备 | 样本统计 | `training_statistics.md` | 中 |
| 模型训练 | 建立 baseline | 训练日志、模型 checkpoint | 高 |
| 模型训练 | 初步训练 & 验证 | loss 曲线, confusion matrix | 高 |
| 审阅 | 高频优先审阅 | 更新 `unassigned_function_tracking.csv` | 高 |
| 审阅 | 升级潜力审阅 | 更新 `unassigned_function_tracking.csv` | 中 |
| 审阅 | 更新 mapping log | `mapping_review_log.csv` | 高 |
| 分析 | baseline 评估 | 统计报告 | 中 |
| 分析 | 确定升级候选 | `unassigned_function_tracking.csv` | 中 |

---

## 5. 时间节点建议
- **第1周**：完成数据落地和 split 文件生成
- **第2周**：完成训练 baseline + 初步评估
- **第3周**：完成高频优先人工审阅
- **第4周**：完成升级潜力审阅和 mapping log 更新
- **第5周**：生成第一轮 baseline 统计报告，确定新 L3 候选
- **第6周**：准备第二版训练或 ontology 升级

---

## 6. 注意事项
1. ontology 当前冻结为 **PFO v1.0.2**，第一轮训练不允许随意改树
2. multilabel / secondary label 必须严格按照映射策略
3. open-set / defer / parent-only 样本必须保留对应状态
4. 所有数据处理步骤必须记录版本、输入文件和处理脚本版本
5. 每次人工复核、映射修改都必须写入 `mapping_review_log.csv`，保持可追踪

---

## 7. 最重要的一句话
> **先把训练数据落地 + baseline 训通，再用模型结果指导 ontology 调整和新 L3 升级，而不是一开始为了完美 ontology 无限纠结。**
