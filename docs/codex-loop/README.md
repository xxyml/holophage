# Holophage Codex Loop

这个目录定义 Holophage loop 的控制层协议。

核心原则保持不变：

- `Codex-first`
- `Governor` 负责状态与安全闸门
- 只把 machine truth 写入 `loop_state/` 与 `loop_runs/`
- `tasks/`、`handoff/`、`reports/` 仍是 narrative docs，不是机器真相

## V2.9 概览

`v2.9` 在 `v2.8` 的 Program Planner 之上，补齐了 program 级 continuation：

- 新增 `loop_state/program_budget_state.json`
- 新增 `loop_state/best_known_metrics.json`
- 新增 `loop_state/program_handoff.json`
- budget window reset 后，program 可以按 milestone 语义自动恢复
- `multilabel_inference_protocol_decision` 与 `promotion_candidate_followup` 已升级为正式 workflow
- `Decision Memory` 新增 `decision_status / topic_kind / next_action_hint / blocks_workflows`
- `Regression Sentinel` 现在优先对比 strict-closeout 通过后的 best-known 指标
- `show-program-plan` / `show-program-status` 会暴露 budget、best-known、handoff 摘要

## V2.9.1 概览

`v2.9.1` 在 `v2.9` 的 program continuation 之上，补了 dual-output 规划链与 runtime 收口：

- 新增 `dual_output_implementation_plan` workflow：
  - `dual_output_plan_evidence_closeout`
  - `dual_output_plan_decision`
  - `dual_output_plan_handoff`
- `promotion_candidate_followup` 选择 `dual_output_implementation_plan` 后，Program Planner 会自动激活 `dual_output_implementation_plan_ready`
- `decision_payload` 扩展为可描述 dual-output 规划：
  - `implementation_scope`
  - `requires_runtime_api_change`
  - `requires_model_output_change`
- 新增 phase-3 占位任务：
  - `dual_output_runtime_patch`
  - `dual_output_report_closeout`
  - `dual_output_hold_closeout`
- `program_handoff.json` 现在会明确：
  - `next_ready_task_id`
  - `next_ready_task_template`
  - `program_stop_reason`
- 当 program 已收敛到明确停点且没有可继续自动执行的 task 时，`run-autopilot` 会优雅结束并写：
  - `session_end_reason = program_waiting_for_next_phase`

## V2.9.2 概览

`v2.9.2` 继续把 `dual_output_runtime_patch` 落成真实 implementation/runtime patch：

- `dual_output_runtime_patch` 不再是占位 `truth_calibration`，而是受限 `implementation_task`
- `baseline/evaluate_multimodal.py` 现在会为所有样本导出 dual-output 视图：
  - `multilabel_positive_indices`
  - `multilabel_positive_scores`
  - `multilabel_topk_indices`
  - `multilabel_topk_scores`
  - `multilabel_active_for_metrics`
- `metrics_{split}.json` 新增：
  - `dual_output.protocol = dual_output_without_selector`
  - `multilabel_head_present`
  - `positive_threshold = 0.5`
  - `metrics_masked_by_target_mask = true`
- `summary.json` / experiment registry draft 现在会携带 `dual_output_runtime`
- `Program Planner` 会在 `dual_output_runtime_patch` 完成后，把 phase-3 下一步收敛到：
  - `dual_output_report_closeout`
  - 或 `dual_output_hold_closeout`

## V2.8 概览

`v2.8` 在 `v2.7` 的 workflow engine 之上，新增最小项目级控制面：

- 新增 `program_planner.py`
- 新增 `loop_state/milestones.json`
- 新增 `loop_state/decision_memory.jsonl`
- 新增 `regression_sentinel.py`
- 新增 program 级预算守门
- `run-autopilot` 在 workflow 完成后，会先由 Program Planner 判断下一 milestone，而不是直接结束
- `show-loop-status` / `show-program-status` 会暴露 `program_status`、`active_milestone`、`program_block_reason`

## V2.7 概览

`v2.7` 在 `v2.6` 之上把 Queue Planner 升级成 workflow-aware runtime：

- 自动挑选可无人值守的低风险任务
- 自动推进 `skill-like workflow`
- 在 policy 显式开启时，自动推进受限的 `implementation_task`
- 每轮写 `stage_checkpoint.json`
- `resume-stale-run` 采用阶段级恢复
- `run_loop` 具备 idle / backoff / wake 语义
- 记录 runtime session 与 session history
- implementation 自动执行会写 transcript
- experiment 自动执行会写 transcript
- policy 显式开启时，自动推进受限的 `experiment_run`
- experiment 执行后自动做 artifact scan / review / registry sync preview
- `paused_for_human` 带结构化原因和建议动作
- `events.jsonl` 关键完成事件带阶段耗时和稳定 `reason_code`
- reviewer verdict 带结构化 `evidence`
- 记录 runner lease / heartbeat / stale recovery
- 统一写入系统级事件日志 `loop_state/events.jsonl`
- 在 policy 显式开启时，自动补受限主链任务队列
- `gate_load_balance` 主线可表示为 workflow instance
- 新增最小 `program_state.json`
- 新增 `workflow_state`，支持 stage 级实例化与推进

第一版默认只自动推进下面这些 workflow：

- `truth_calibration`
- `governance_refresh`
- `results_closeout`
- `multilabel_readiness_audit`
- `artifact_repair`

`implementation_task` 的自动执行不是默认开启。只有同时满足下面条件时，`autopilot` 才会推进：

- `allow_unattended_implementation = true`
- `risk_level == low`
- `autopilot_enabled == true`
- `allowed_write_paths` 非空
- `required_checks` 非空
- `allowed_write_paths` 不命中 forbidden path

不满足这些条件时，`implementation_task` 会显式转为 `paused_for_human` 并写入 `autopilot_currently_gated`。

`experiment_run` 在 `v2.5` 中不再只保留手动/半自动流程。只有同时满足下面条件时，`autopilot` 才会推进：

- `allow_unattended_experiment = true`
- `risk_level == low`
- `autopilot_enabled == true`
- `required_checks` 非空
- `experiment_command` 非空
- `experiment_run_dir` 非空

`v2.6` 不是自由研究 agent。它仍然是一个有边界、可审计、可暂停的任务控制层。

Queue Planner 第一版只做 bounded backlog generation：

- 只在 `enable_queue_planner = true` 时启用
- 只围绕当前 `queue_planner_active_lane`
- 只补标准模板任务，不自由发明新主线
- 当前默认只服务 `gate_load_balance`

## 两种使用方式

### 1. 手动三窗口模式

适用于：

- `experiment_run`
- 需要人工判断 planner / reviewer 的轮次
- 任何不满足 `implementation_task` 自动执行条件的轮次

最小流程：

```powershell
conda activate ai4s
python integrations/codex_loop/cli.py prepare-plan-packet
python integrations/codex_loop/cli.py prepare-planner-workspace --run-id <run_id>
python integrations/codex_loop/cli.py prepare-planner-decision-template --run-id <run_id>
```

然后让 `Planner Codex` 读取：

- [planner.md](/D:/data/ai4s/holophage/docs/codex-loop/planner.md)
- [planner-window-template.md](/D:/data/ai4s/holophage/docs/codex-loop/planner-window-template.md)
- `loop_runs/<run_id>/planner_workspace.json`

生成 `planner_decision.json` 后继续：

```powershell
python integrations/codex_loop/cli.py prepare-executor-workspace --decision loop_runs/<run_id>/planner_decision.json
python integrations/codex_loop/cli.py run-execution --decision loop_runs/<run_id>/planner_decision.json
python integrations/codex_loop/cli.py prepare-reviewer-workspace --execution loop_runs/<run_id>/execution_result.json
python integrations/codex_loop/cli.py prepare-review-verdict-template --execution loop_runs/<run_id>/execution_result.json
python integrations/codex_loop/cli.py advance-review --verdict loop_runs/<run_id>/review_verdict.json
```

如果是 `implementation_task`，则把 executor 步骤替换为：

```powershell
python integrations/codex_loop/cli.py prepare-implementation-workspace --decision loop_runs/<run_id>/planner_decision.json
python integrations/codex_loop/cli.py run-implementation --decision loop_runs/<run_id>/planner_decision.json
python integrations/codex_loop/cli.py prepare-reviewer-workspace --execution loop_runs/<run_id>/execution_result.json
python integrations/codex_loop/cli.py prepare-review-verdict-template --execution loop_runs/<run_id>/execution_result.json
python integrations/codex_loop/cli.py advance-review --verdict loop_runs/<run_id>/review_verdict.json
```

### 2. V2.5 Autopilot 模式

适用于：

- 低风险、白名单内的 `skill-like workflow`
- policy 显式开启时的低风险、小写集 `implementation_task`
- policy 显式开启时的低风险 smoke `experiment_run`
- 本机长期值守
- 想让 loop 自动完成 planner -> execution -> reviewer -> state update

单轮试跑：

```powershell
python integrations/codex_loop/cli.py run-once
```

持续运行：

```powershell
python integrations/codex_loop/cli.py run-autopilot
```

也可以用 session 级覆盖参数：

```powershell
python integrations/codex_loop/cli.py run-autopilot --max-session-minutes 30 --max-session-rounds 4 --idle-sleep-seconds 5 --max-idle-sleep-seconds 30
```

或使用脚本入口：

```powershell
pwsh -File scripts/start-loop-runner.ps1
```

查看当前状态：

```powershell
python integrations/codex_loop/cli.py show-loop-status
```

手动触发一次 Queue Planner：

```powershell
python integrations/codex_loop/cli.py plan-queue
```

查看 Queue Planner 当前状态与候选：

```powershell
python integrations/codex_loop/cli.py show-queue-plan
```

查看 workflow / program 状态：

```powershell
python integrations/codex_loop/cli.py show-workflow-status
python integrations/codex_loop/cli.py show-program-status
python integrations/codex_loop/cli.py show-milestones
python integrations/codex_loop/cli.py show-decisions
python integrations/codex_loop/cli.py show-program-plan
python integrations/codex_loop/cli.py recompute-program-state
python integrations/codex_loop/cli.py show-budget-state
python integrations/codex_loop/cli.py reset-budget-window
python integrations/codex_loop/cli.py show-best-known
python integrations/codex_loop/cli.py show-program-handoff
```

恢复 stale runner：

```powershell
python integrations/codex_loop/cli.py resume-stale-run
```

## V2.5 自动驾驶默认行为

`autopilot` 默认会：

1. 读取 state / policy / task registry
2. 抢占 runner lease 并写 heartbeat
3. 只选择 `status == ready` 且 `autopilot_enabled == true` 的任务
4. 只自动运行 policy 白名单 workflow
5. 只在 policy 明确开启时自动运行受限 `implementation_task`
6. 只在 policy 明确开启时自动运行受限 `experiment_run`
7. 只自动运行默认 `risk_level == low` 的任务
8. 超过 retry/no-progress/policy 上限时转 `paused_for_human`
9. 每个关键阶段都会覆盖写入 `stage_checkpoint.json`
10. 无任务时进入 idle sleep，并按 backoff 增长等待时间
11. session 结束时写 `runtime_session.json` 与 `runtime_session_history.jsonl`

当前 state 会新增：

- `runner_id`
- `lease_acquired_at`
- `heartbeat_at`
- `stale_after_seconds`
- `active_lease_status`
- `blocked_reason_code`
- `blocked_reason_detail`
- `suggested_next_actions`

当前 task record 会新增：

- `priority`
- `retry_count`
- `last_attempt_at`
- `cooldown_until`
- `autopilot_enabled`
- `required_checks`

当前 implementation policy 会新增：

- `allow_unattended_implementation`
- `implementation_max_files_touched`
- `implementation_max_diff_lines`
- `implementation_require_all_checks_pass`
- `implementation_pause_on_partial_write`
- `implementation_allowed_command_prefixes`
- `implementation_forbidden_command_prefixes`
- `implementation_forbidden_command_substrings`
- `implementation_require_pwsh_for_checks`

当前 experiment policy 会新增：

- `allow_unattended_experiment`
- `experiment_allowed_command_prefixes`
- `experiment_forbidden_command_prefixes`
- `experiment_forbidden_command_substrings`
- `experiment_max_wall_clock_minutes`
- `experiment_require_summary_json`
- `experiment_require_metrics`
- `experiment_required_artifacts`
- `experiment_pause_on_missing_artifacts`

当前 runtime policy 会新增：

- `idle_sleep_seconds`
- `backoff_multiplier`
- `max_idle_sleep_seconds`
- `wake_on_stale_run`
- `wake_on_cooldown_expiry`
- `wake_on_task_registry_change`
- `max_runner_session_minutes`
- `max_runner_session_rounds`

当前 queue planner policy 会新增：

- `enable_queue_planner`
- `queue_planner_max_generated_tasks`
- `queue_planner_allowed_templates`
- `queue_planner_max_budget_level`
- `queue_planner_require_closeout_pass`
- `queue_planner_allow_auxiliary_tasks`
- `queue_planner_active_lane`

## 运行目录

- `loop_state/`：当前 machine state
- `loop_state/events.jsonl`：系统级长期事件日志
- `loop_state/runtime_session.json`：当前 runner session 快照
- `loop_state/runtime_session_history.jsonl`：session 历史
- `loop_state/queue_planner_state.json`：自动补队列状态与生成历史
- `loop_state/program_state.json`：最小 program 控制面
- `loop_state/program_budget_state.json`：program 预算窗口 ledger
- `loop_state/best_known_metrics.json`：strict-closeout 后的 best-known 指标基线
- `loop_state/program_handoff.json`：program 级 handoff / summary
- `loop_state/workflows/*.json`：workflow instance 状态
- `loop_runs/<run_id>/`：单轮审计记录
- `loop_runs/<run_id>/stage_checkpoint.json`：阶段级恢复点
- `loop_runs/<run_id>/implementation_transcript.jsonl`：implementation 动作 transcript
- `loop_runs/<run_id>/experiment_transcript.jsonl`：experiment 动作 transcript

## 事件与 Review

`events.jsonl` 现在会在关键事件中记录：

- `reason_code`
- `suggested_next_actions`（当事件对应 `paused_for_human` / policy gate / review failure 时）
- `recommended_action_summary`（暂停类事件的首选恢复动作摘要）
- `recovery_summary`（`stale_resumed` 事件的阶段恢复摘要）
- `wake_reason`
- `session_end_reason`
- `planner_ms`
- `execution_ms`
- `checks_ms`
- `review_ms`
- `round_ms`
- `queue_planner_generated`（通过 `task_registry_changed` 的 reason/details 暴露）

`review_verdict.json` 现在必须带 `evidence`，至少包括：

- `write_set`
- `checks_run`
- `checks_passed`
- `detected_conditions`

`execution_result.json` 在 implementation / experiment 路径还会补：

- `transcript_path`
- `step_count`
- `failed_step`

## Stale Recovery

`resume-stale-run` 不再只是“抢回 lease”，而是会读取 `stage_checkpoint.json` 并按最近安全阶段恢复：

- `planner_decision_written` / `execution_started`：回到 execution 边界重新执行
- `execution_finished`：直接从 reviewer 阶段继续
- `review_finished`：只重做 state commit

如果 checkpoint 与现场产物冲突，系统会保留现有 run 产物，不会自动覆盖它们。

## 3 窗口工作法

当使用手动模式时，角色隔离规则不变：

- 窗口 A：`Planner`
  只读 `planner_workspace.json` 指向的文件，不能读取 `execution_result.json`
- 窗口 B：`Executor`
  只读 `executor_workspace.json` 指向的文件，不能读取 `planner_input_packet.json`
- 窗口 C：`Reviewer`
  只读 `reviewer_workspace.json` 指向的文件，默认不能读取 `planner_input_packet.json` 和历史 `loop_runs`

三个窗口共享同一仓库与状态目录，但不共享任务对话上下文。

## 产物约定

- `baseline/train.py` 与 `baseline/train_multimodal.py` 训练结束后会自动为 `best.pt` 导出：
  - `evaluation/metrics_val.json`
  - `evaluation/metrics_test.json`
- 这样 `results_closeout` 的 strict 模式更容易直接通过，不需要每次手工补评估产物

## Experiment Registry Draft

实验注册草稿仍从现有 run 产物中抽取：

- `summary.json`
- `evaluation/metrics_val.json`
- `evaluation/metrics_test.json`
- `closeout_artifacts`

这个层仍是 draft / normalization layer；真正是否持久化，由 Governor 和 CLI 决定。

## V2.5 Experiment Note

- `experiment_run` 第一版只面向短时 smoke experiment，不面向正式长训练
- 默认不自动 promote experiment registry status
- 自动路径会优先检查 `summary.json`，metrics 默认仍可选

## V2.6 Queue Planner Note

- 当前 Queue Planner 只会自动补主链标准模板任务：
  - `results_closeout`
  - `experiment_run`
  - `promotion_readiness_review`
  - `promotion_candidate_decision`
- 当前不会自动补：
  - `gate_entropy` 并行主线
  - `multilabel inference protocol design`
  - `is_multilabel` selector 实现
  - 新结构 / 新损失 / 新 truth

## V2.7 Workflow Engine Note

- `queue_planner` 现在会先读取 active workflow 的当前 stage，再决定是否实例化下一个 task
- 第一版 workflow engine 只服务 `gate_load_balance` lane
- 当前主 workflow 是 `gate_load_balance_promotion`
- `results_closeout` 会补最小 `workflow_signal`
- 当前自动驱动的关键跳转只有：
  - `second_seed_closeout -> promotion_readiness_review`
  - `promotion_readiness_review -> extended_real_case_staging`
  - `extended_real_case_closeout -> promotion_candidate_decision`

## V2.9 Program Runtime Continuation Note

- budget guard 现在通过 `program_budget_state.json` 持久化，而不是只靠“今天跑了多少 task”临时推断
- budget window reset 后，如果当前 milestone 允许自动恢复，program 会恢复为可继续推进
- `multilabel_inference_protocol_decision` 已被提升为正式非实验型 workflow：
  - `inference_protocol_evidence_closeout`
  - `inference_protocol_decision`
  - `inference_protocol_handoff`
- `promotion_candidate_followup` 已作为 follow-up workflow 骨架接入
- best-known 指标只从 strict-closeout 通过的 `gate_load_balance` run 刷新
- `program_handoff.json` 会在 milestone 切换、budget pause、workflow 完成时自动更新

## V2.2 Trial Note

- 2026-03-31 的一轮受限 `implementation_task` 试跑仅追加本说明，并要求执行 `python -m unittest integrations.codex_loop.tests.test_codex_loop` 作为最小检查。
