# 表模板字段说明

## 1. unassigned_function_tracking.csv
用于管理当前尚未稳定进入 L3 的功能词条，包括：
- defer
- open_set
- candidate_new_leaf
- 一部分只停留在 coarse layer 的难项

### 关键字段
- `current_status`：当前状态，例如 defer / open_set / candidate_new_leaf
- `candidate_level1/2/3`：后续可能升级的目标位置
- `reason_not_assigned`：当前不进入 L3 的原因
- `review_priority`：人工审查优先级（high / medium / low）
- `needs_multimodal_evidence`：是否强依赖序列之外的证据
- `promotion_evidence`：未来升级的证据来源
- `suggested_next_action`：下一步建议动作

## 2. mapping_review_log.csv
用于记录映射修订历史，避免后续不知道为什么改过。

### 关键字段
- `old_*`：修改前标签
- `new_*`：修改后标签
- `change_type`：修改类型，例如：
  - primary_reassignment
  - secondary_added
  - downgrade_to_defer
  - parent_only_to_l3
- `reason_for_change`：为什么改
- `evidence_type`：证据类型，例如：
  - term_semantics
  - family_consistency
  - structure_support
  - neighborhood_support
  - mapping_policy_update
- `confidence`：这次改动的主观置信度
- `approved`：是否正式采纳到当前版本

## 3. 推荐使用方式
- 每次遇到“现在先不分”的 term，优先写进 `unassigned_function_tracking.csv`
- 每次对映射结果改动时，必须写进 `mapping_review_log.csv`
- 这两个表应与 ontology version / mapping version 一起维护
