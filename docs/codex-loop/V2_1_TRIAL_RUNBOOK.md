# Holophage V2 Trial Runbook

本 runbook 用于执行 `v2.1`、`v2.2`、`v2.3`、`v2.4` 和 `v2.5` 的保守试跑。

## 目标

- 验证低风险 `skill-like workflow` 能完成一次 `run-once` 全闭环
- 验证 `implementation_task` 的 gated 行为与自动执行协议都符合 policy
- 验证 lease / heartbeat / events / reviewer 行为足够稳定
- 验证 `v2.3` 的 `stage_checkpoint.json`、阶段恢复和结构化暂停原因
- 验证 `v2.4` 的 idle / wake / session closeout / implementation transcript
- 验证 `v2.5` 的 smoke experiment 自动执行、artifact scan 和 experiment transcript

## 首轮样本

- 正例：最小 `truth_calibration`
- 负例：最小 `implementation_task` gated 样本

如果后续要补第二个正例，再考虑 `results_closeout`。

## 阶段 A：预检

先落盘 policy 默认值并执行结构化预检：

```powershell
pwsh -File scripts/codex-loop-trial-precheck.ps1 -TaskId 2026-03-31-v21-autopilot-trial-truth-calibration
```

通过标准：

- `policy_materialized_shape = true`
- `lease_ready = true`
- `target_task_ready = true`
- `next_task_matches_target = true`

## 阶段 B：正例 `run-once`

```powershell
python integrations/codex_loop/cli.py run-once
```

检查：

- `loop_state/events.jsonl`
- `loop_state/current_state.json`
- `loop_runs/<run_id>/stage_checkpoint.json`
- 最新 `loop_runs/<run_id>/round_summary.md`
- 同轮 `planner_decision.json`
- 同轮 `execution_result.json`
- 同轮 `review_verdict.json`

通过标准：

- 事件链包含 `runner_started -> task_selected -> run_started -> run_completed`
- 若本轮进入 `paused_for_human`，对应事件会带 `reason_code`、`blocked_reason_detail`、`suggested_next_actions`、`recommended_action_summary`
- `current_state.status` 回到 `context_ready`、`completed` 或清晰的 `paused_for_human`
- 没有卡在中间状态
- `stage_checkpoint.json` 能反映最新阶段

## 阶段 C：负例 gated 验证

确认 `2026-03-31-v21-autopilot-trial-implementation-gated` 处于 `ready`，且正例样本已被临时暂停后，再执行一次：

```powershell
python integrations/codex_loop/cli.py run-once
```

通过标准：

- task 被转成 `paused_for_human`
- `blocked_reason = autopilot_currently_gated`
- `blocked_reason_code = autopilot_currently_gated`
- `suggested_next_actions` 非空
- `events.jsonl` 中出现 `policy_blocked`
- 没有自动代码执行链路

## 阶段 D：V2.2 implementation trial

只有在前面阶段稳定，并且你显式打开 implementation policy 后，才允许进入这一步。

先打开：

```powershell
python integrations/codex_loop/cli.py materialize-policy
```

然后把 `loop_state/intervention_policy.json` 中的 `allow_unattended_implementation` 临时改成 `true`，并确认 trial task 满足：

- `risk_level = low`
- `allowed_write_paths` 非空
- `required_checks` 非空
- 写集只落在 `integrations/codex_loop` 下的小范围文件

建议样本：

- `2026-03-31-v22-autopilot-trial-implementation-small`

执行：

```powershell
python integrations/codex_loop/cli.py run-once
```

检查：

- 最新 `loop_runs/<run_id>/execution_result.json`
- 最新 `loop_runs/<run_id>/stage_checkpoint.json`
- `write_set` 是否是真实写集
- `checks_run` / `checks_passed` 是否完整
- `prepare-review-verdict-template` 是否在 check 不全时默认给出 `revise`

通过标准：

- 自动完成 implementation -> checks -> review -> state update
- 超范围写入会 fail-fast
- check 不全不会被误判为 `approve`
- 暂停时会写出结构化 `blocked_reason_code/detail/suggested_next_actions`

## 阶段 E：短窗口自动运行

只有前两阶段都稳定后，才允许：

```powershell
python integrations/codex_loop/cli.py run-autopilot --max-rounds 2
```

检查：

- `heartbeat_at` 持续更新
- 没有异常增长 `retry_count`
- 无任务时会写 `runner_idle`
- 被唤醒执行时会写 `runner_woke`
- 结束后 lease 已释放

如果要验证 `v2.4` session 级行为，建议使用：

```powershell
python integrations/codex_loop/cli.py run-autopilot --max-session-minutes 15 --max-session-rounds 2 --idle-sleep-seconds 5 --max-idle-sleep-seconds 15
```

并检查：

- `loop_state/runtime_session.json`
- `loop_state/runtime_session_history.jsonl`
- `session_ended` 事件中的 `session_end_reason`

## 停止信号

出现以下任一情况就停：

- `active_lease_status = active` 但 `heartbeat_at` 长时间不更新
- `events.jsonl` 连续出现 `policy_blocked`、`review_failed`、`no_progress_pause`、`run_paused`
- 同一 task 的 `retry_count` 快速增长
- 非预期 task 被转成 `autopilot_currently_gated`

## 回退顺序

1. 停止继续调用 `run-autopilot`
2. 保留现场，先看 `current_state.json`、`events.jsonl`、最新 `loop_runs/<run_id>/`
3. 如果 heartbeat 过期，执行：

```powershell
python integrations/codex_loop/cli.py resume-stale-run
```

4. 如果是单 task 问题，执行：

```powershell
python integrations/codex_loop/cli.py pause-task --task-id <task_id> --reason <reason>
```

5. 修正前置条件后，先重新跑 `run-once`，不要直接回 `run-autopilot`

## V2.3 阶段恢复检查

如果需要验证 `resume-stale-run`：

1. 保留已有 `loop_runs/<run_id>/stage_checkpoint.json`
2. 人工确认当前 run 停在：
   - `planner_decision_written`
   - 或 `execution_finished`
   - 或 `review_finished`
3. 执行：

```powershell
python integrations/codex_loop/cli.py resume-stale-run
```

通过标准：

- 返回结果包含 `recovered_stage`
- 返回结果包含 `resume_action`
- 返回结果包含 `artifacts_verified`
- `events.jsonl` 中对应 `stale_resumed` 事件也应记录 `recovered_stage / resume_action / artifacts_verified / recovery_summary`
- 恢复不需要整轮重跑

## V2.2 trial note

- 2026-03-31 的最小 `implementation_task` 试跑样本固定为 `2026-03-31-v22-autopilot-trial-implementation-small`，目标仅为向 `docs/codex-loop/V2_1_TRIAL_RUNBOOK.md` 追加一条短注记并完成 `python -m unittest integrations.codex_loop.tests.test_codex_loop`。
- 本轮应把 write set 收敛到单文件文档追加，并把 unittest 结果作为 implementation 阶段是否可收口的唯一检查信号。

## V2.4 transcript note

- implementation 自动执行后，应额外检查 `loop_runs/<run_id>/implementation_transcript.jsonl`
- 至少应能看到：`preflight`、`implementation_command`、`required_check:*`、`write_scope_validation`、`diff_budget_validation`

## V2.5 experiment trial

- 首个 trial 样本固定为 `2026-03-31-v25-autopilot-trial-experiment-smoke`
- 运行前需要显式开启 `allow_unattended_experiment = true`
- trial 目标不是产出最佳实验，而是验证：
  - `experiment_run` 自动执行
  - `summary.json` artifact 检查
  - `experiment_transcript.jsonl`
  - review / registry sync preview / closeout 状态落盘
- 建议最小检查命令：

```powershell
python integrations/codex_loop/cli.py create-task --task-file tasks/2026-03-31-v25-autopilot-trial-experiment-smoke.md --workflow-kind experiment_run --risk-level low --required-check "python -m unittest integrations.codex_loop.tests.test_codex_loop" --experiment-command "python -c \"print('experiment smoke')\"" --experiment-run-dir "baseline/runs/tmp_auto_closeout_metrics_smoke" --experiment-required-artifact summary.json
```
