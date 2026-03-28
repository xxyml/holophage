# 文件索引（FILE_INDEX）

## 说明
本文件用于记录当前项目中的关键文件、其作用、当前状态以及推荐使用方式。

## 一、当前正式使用的核心文件

### 1. `PFO_v1_0_2_remapped_729_terms.csv`
**作用**：当前正式推荐使用的 729 个真实 annotation term 映射表。  
**状态**：当前正式版本（active）  
**用途**：后续训练数据准备、覆盖率统计、映射审阅。

### 2. `PFO_v1_0_2_remapped_729_terms_guide.md`
**作用**：对 v1.0.2 映射表的详细说明文档。  
**状态**：当前正式说明文档（active）  
**用途**：解释为什么这样映射，说明多标签与弱映射项的处理原则。

### 3. `PFO_v1_0_2_L1_L2_L3_explanation.md`
**作用**：按 L1 / L2 / L3 展开的分层解释文档。  
**状态**：当前正式结构说明文档（active）  
**用途**：快速理解 v1.0.2 的树结构。

### 4. `PFO_followup_plan.md`
**作用**：后续路线计划文档。  
**状态**：当前正式 follow-up 计划（active）  
**用途**：指导如何管理未分配功能、何时升级新类、如何在模型训练后反向修 ontology。

### 5. `PROJECT_OVERVIEW_zh.md`
**作用**：项目总览文档。  
**状态**：当前 handoff 主入口（active）  
**用途**：新窗口快速了解项目全局。

### 6. `THINKING_SUMMARY_FOR_HANDOFF_zh.md`
**作用**：思考过程与关键争议提炼稿。  
**状态**：当前 handoff 核心文档（active）  
**用途**：迁移“为什么这样做”的过程信息。

### 7. `DECISION_LOG_zh.md`
**作用**：关键决策日志。  
**状态**：当前 handoff 核心文档（active）  
**用途**：追踪关键决定及其理由。

## 二、当前本体规范与节点表文件

### 8. `PFO_improved_v1_1_framework.md`
**作用**：PFO-improved v1.1 的结构说明文档。  
**状态**：关键中间版本（reference）  
**用途**：理解 v1.0.2 的来源。

### 9. `PFO_improved_v1_1_node_table.csv`
**作用**：PFO-improved v1.1 的节点表。  
**状态**：参考版本（reference）  
**用途**：对比 v1.0.2 与 v1.1 差异。

### 10. `PFO_alpha_node_table.csv`
**作用**：alpha 框架节点表。  
**状态**：历史版本（historical reference）  
**用途**：理解项目早期的训练导向设计。

### 11. `PFO_alpha_mapping_guide.md`
**作用**：alpha 版映射规则和说明。  
**状态**：历史版本（historical reference）  
**用途**：查看项目最早期的映射思路。

## 三、历史映射表和中间版本文件

### 12. `PFO_alpha_full_mapping.csv`
**作用**：alpha 版全量映射表。  
**状态**：历史版本（historical reference）

### 13. `PFO_alpha_revised_full_mapping.csv`
**作用**：alpha revised 的重映射表。  
**状态**：关键中间版本（reference）

### 14. `PFO_improved_v1_1_remapped_729_terms.csv`
**作用**：improved v1.1 框架下重映射的 729 个 term 表。  
**状态**：关键中间版本（reference）

### 15. `PFO_improved_v1_1_remapped_729_terms_guide.md`
**作用**：v1.1 映射说明文档。  
**状态**：参考文档（reference）

### 16. `PFO_alpha_modified_mapping.xlsx`
**作用**：按特定列格式导出的修订版 xlsx。  
**状态**：操作型中间文件（reference）

### 17. `PFO_alpha_explicit_multilabel_rows.csv`
**作用**：显式多标签词条子表。  
**状态**：参考文件（reference）

## 四、比较分析与讨论材料

### 18. `PFO_redefined_framework.md`
**作用**：第三方案/重定义框架文档。  
**状态**：历史比较版本（reference）

### 19. `PFO_redefined_framework_tree.tsv`
**作用**：第三方案的树结构 TSV。  
**状态**：历史比较版本（reference）

### 20. `PFO_original_vs_third_scheme_comparison.md`
**作用**：原始方案与第三方案的对比分析。  
**状态**：历史比较文档（reference）

### 21. `PFO_improved_v1_1_improvement_notes.md`
**作用**：针对 improved v1.1 的改进建议文档。  
**状态**：参考分析文档（reference）

## 五、项目背景与原始数据文件

### 22. `phrog_annotation_protein_count.tsv`
**作用**：项目核心原始统计表之一，包含 annotation 及蛋白数。  
**状态**：原始输入数据（source data）

### 23. `phrog_annot_v4.tsv`
**作用**：PHROG / PHROGs v4 注释表。  
**状态**：原始外部参考数据（source reference）

### 24. `LITERATURE_OVERVIEW.md`
**作用**：文献综述/笔记文件。  
**状态**：背景材料（reference）

## 六、模板与交接结构文件

### 25. `pfo_handoff_templates/`
**作用**：项目 handoff 模板目录。  
**状态**：模板资源（template）

### 26. `unassigned_function_tracking_template.csv`
**作用**：未分配功能升级队列表模板。  
**状态**：模板文件（template）

## 七、当前推荐阅读顺序
1. `PROJECT_OVERVIEW_zh.md`
2. `THINKING_SUMMARY_FOR_HANDOFF_zh.md`
3. `DECISION_LOG_zh.md`
4. `PFO_v1_0_2_L1_L2_L3_explanation.md`
5. `PFO_v1_0_2_remapped_729_terms_guide.md`
6. `PFO_v1_0_2_remapped_729_terms.csv`
7. `PFO_followup_plan.md`

## 八、当前正式工作基准
当前建议作为正式工作基准的文件是：
- **框架说明基准**：`PFO_v1_0_2_L1_L2_L3_explanation.md`
- **映射表基准**：`PFO_v1_0_2_remapped_729_terms.csv`
- **映射说明基准**：`PFO_v1_0_2_remapped_729_terms_guide.md`
- **后续计划基准**：`PFO_followup_plan.md`

## 九、当前不建议再作为主版本使用的文件
以下文件仍有参考价值，但不建议作为当前正式主版本继续往下改：
- `PFO_alpha_full_mapping.csv`
- `PFO_alpha_revised_full_mapping.csv`
- `PFO_improved_v1_1_remapped_729_terms.csv`
- `PFO_redefined_framework.md`

## 十、最重要的一句话
当前项目已经从“多版本探索阶段”进入“稳定版本推进阶段”。所以后续所有工作，原则上应以 **PFO v1.0.2** 为主基准，而不是重新回到 alpha / v1.1 / third scheme 上重新争论。
