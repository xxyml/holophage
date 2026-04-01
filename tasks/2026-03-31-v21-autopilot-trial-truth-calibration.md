# V2.1 Autopilot Trial Truth Calibration

更新时间：2026-03-31

## 目标

- 为 `v2.1 autopilot` 首轮试跑提供一个最小、低风险、白名单内的正例任务
- 只验证 loop 行为，不改变当前正式主线 truth

## 范围

- workflow 固定为 `truth_calibration`
- 不修改 ontology
- 不修改默认配置
- 不修改训练与评估代码

## Success Criteria

- `run-once` 能完成一次完整的 planner -> execution -> reviewer -> state update 闭环
- `events.jsonl` 中出现完整事件链
- `current_state` 不停留在异常 lease / workspace 中间状态

## 非目标

- 不产出新的实验结果
- 不作为模型/数据主线任务
- 不替代手动三窗口流程

## Outcome

- 待执行
