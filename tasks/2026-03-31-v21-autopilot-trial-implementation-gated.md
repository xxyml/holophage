# V2.1 Autopilot Trial Implementation Gated

更新时间：2026-03-31

## 目标

- 为 `v2.1 autopilot` 首轮试跑提供一个最小负例样本
- 验证 `implementation_task` 不会被误自动执行，而是会进入 `autopilot_currently_gated`

## 范围

- workflow 固定为 `implementation_task`
- 不执行实际代码修改
- 只验证 task selection 与 policy gate 行为

## Success Criteria

- `run-once` 不会自动执行 implementation 流程
- task 会被转成 `paused_for_human`
- `blocked_reason = autopilot_currently_gated`
- `events.jsonl` 中出现 `policy_blocked`

## 非目标

- 不验证实现逻辑本身
- 不替代真实 implementation 手动流程

## Outcome

- 待执行
