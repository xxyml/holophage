# Current Sprint

更新时间：2026-04-01

## 当前正式主线

当前 sprint 只在下面这组正式主线上推进：

- `PFO v1.0.2`
- `homology_cluster_v1`
- `exact_sequence_rep_id`
- `L1 + L2 + L3 core`
- `trainable_core`

当前事实定义仍以以下 manifest 为准：

- [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
- [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)
- [ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)

## 当前焦点

本轮只做一件事：

- 在不改变当前正式主线 truth 的前提下，完成 C 线 staging 收口，并把主线切到 multilabel head 实现与接入

当前背景结论来自：

- [MULTIMODAL_V2_INTERIM_RESULTS_2026-03-29.md](D:/data/ai4s/holophage/project_memory/02_data_pipeline/MULTIMODAL_V2_INTERIM_RESULTS_2026-03-29.md)

已经明确的当前判断：

- `seq-only` 是强且稳定的正式 baseline
- `seq+struct` 有稳定小幅提升，应保留为弱增强分支
- `seq+struct` 的 shared-bank 默认切换已完成，当前正式工程默认目录为 `baseline/artifacts/prepacked_multimodal_v2/seq_struct`
- `baseline/artifacts/prepacked_multimodal_v2/seq_struct_inline_legacy_2026-03-30` 仅保留作历史/回退参考，`tmp/*bench*`、`*smoke*`、`*shared_candidate*` 都不是默认入口
- `seq+ctx` 当前实现没有表现出明确、稳定的全局增益
- `seq+struct+context` 仍未切正式默认，但 `optimized_v3` 已通过双 seed 复核并进入“默认候选 staging”
- C 线 staging 入口配置：`baseline/train_config.multimodal_v2.seq_struct_ctx_gnn_w4.staging_optimized_v3.yaml`（`runtime_mode=optimized_v3`）；主配置 `baseline/train_config.multimodal_v2.seq_struct_ctx_gnn_w4.yaml` 保持 `runtime_mode=baseline` 作为回退入口
- C 线 staging 期持续 gate：digest 一致、无 NaN/Inf、指标不漂；并持续追踪 `data_wait_ms / dataloader_next_ms / step_ms`，若同口径连续 2 次相对 baseline 劣化（建议阈值 >1%）则降级回 baseline 候选
- C 线 S1/S2（双 seed）执行已完成，当前结论是：`optimized_v3` 继续保持 staging 候选资格；S2 在 seed52 上有轻微 `data_wait/dataloader_next` 回弹（约 `+0.63%`），未触发降级阈值
- C 线窗口执行报告：`reports/2026-03-30-c-line-staging-s1-s2-results.md`
- C 线最终候选稳定性复核（worker+pin）已完成：`reports/2026-03-30-c-line-optimized-v3-final-stability.md`
- Windows 本机 `active_num_workers=0` 为正式可接受结论，不再作为当前阻塞项
- C 线 `optimized_v3` 为 default candidate staging，not production default
- 当前工程主阻塞已不在 B/C runtime 工程层
- 下一阶段主线：multilabel head
- multimodal multilabel mini validation 已完成并 strict closeout，通过真实 multilabel 样本确认 wiring 与评估链路可用
- 当前主阻塞已从 wiring 转为 multimodal fusion/gating 的 `sequence-only collapse`
- 已完成的最小正则对照显示：
  - `gate_entropy` 和 `gate_load_balance` 都能抑制 collapse
  - 其中 `gate_load_balance` 当前是略优正式候选
- `gate_load_balance` 的更大 mini-run 已完成：
  - [summary.json](D:/data/ai4s/holophage/baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_large_mini/summary.json)
  - `l3.macro_f1 ≈ 0.8886`
  - `multilabel.micro_f1 ≈ 0.7550`
  - `mean_gates ≈ 0.411 / 0.256 / 0.333`
  - 当前可判断 sequence-only collapse 已被实质缓解
- `gate_load_balance` 的 full-prepack staging-lite 已完成并 strict closeout：
  - [summary.json](D:/data/ai4s/holophage/baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_staging_lite/summary.json)
  - `val l3.macro_f1 ≈ 0.9446`
  - `val multilabel.micro_f1 ≈ 0.8888`
  - `test multilabel.micro_f1 ≈ 0.9482`
  - `val mean_gates ≈ 0.370 / 0.274 / 0.355`
  - `test mean_gates ≈ 0.386 / 0.251 / 0.363`
  - 当前可判断 `gate_load_balance` 已成为下一轮正式 staging 对照的首选候选
- `gate_load_balance` 的 second-seed staging-lite 也已完成：
  - [summary.json](D:/data/ai4s/holophage/baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_staging_lite_seed52/summary.json)
  - `val l3.macro_f1 ≈ 0.9498`
  - `test multilabel.micro_f1 ≈ 0.9573`
  - `val/test mean_gates ≈ 0.363 / 0.200 / 0.437` 与 `0.372 / 0.210 / 0.418`
  - 当前可判断非塌缩 gate 行为已具备双 seed 支撑
- `gate_load_balance` 的 stronger staging 已完成并通过 strict closeout：
  - [summary.json](D:/data/ai4s/holophage/baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_strong_staging/summary.json)
  - `best_val_l3_macro_f1 ≈ 0.9678`
  - `best_val_multilabel.micro_f1 ≈ 0.9394`
  - `val mean_gates ≈ 0.334 / 0.269 / 0.397`
  - `test mean_gates ≈ 0.372 / 0.235 / 0.393`
  - `gate_health = healthy`
  - 当前可判断 `gate_load_balance` 已通过更强预算复核，继续保持首选 staging 候选
- 下一步优先级：
  - 以 `gate_load_balance` 作为当前首选 staging 候选继续推进
  - `gate_entropy` 只保留作次选参照
  - 当前主 blocker 从 `gate collapse` 转向下一轮更强 staging / 阶段推进设计
- `gate_load_balance real_case_staging` 已完成并通过 strict closeout：
  - [summary.json](D:/data/ai4s/holophage/baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_real_case_staging/summary.json)
  - `best_val_l3_macro_f1 ≈ 0.9640`
  - `best_val_multilabel.micro_f1 ≈ 0.8881`
  - `mean_gates ≈ 0.328 / 0.265 / 0.407`
  - `gate_health = healthy`
  - 当前可判断 `gate_load_balance` 已通过真实案例 staging 收口，足够进入更高预算实测
- 当前 multilabel 连续运行主链已切到：
  - `higher_budget_staging -> higher_budget_closeout -> second_seed_higher_budget -> second_seed_closeout`
  - 推理协议设计仅保留为占位任务，不打断主链
- `gate_load_balance higher_budget_staging + second_seed_higher_budget` 已完成并通过 strict closeout：
  - `seed42 best_val_l3_macro_f1 ≈ 0.9678`
  - `seed42 best_val_multilabel.micro_f1 ≈ 0.9394`
  - `seed52 best_val_l3_macro_f1 ≈ 0.9588`
  - `seed52 best_val_multilabel.micro_f1 ≈ 0.9604`
  - 双 seed `gate_health = healthy`
  - 当前可判断 `gate_load_balance` 已具备进入 `promotion_readiness_review` 的证据基础
- 当前下一阶段主链已切到：
  - `promotion_readiness_review -> extended_real_case_staging -> extended_real_case_closeout`
  - `multilabel inference protocol design` 继续保留为辅链占位
- `promotion_candidate_decision` 已完成：
  - Queue Planner 已自动补出 [2026-04-01-gate-load-balance-promotion-candidate-decision.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-promotion-candidate-decision.md)
  - `results_closeout` 已完成并给出 `approve`
  - 当前可判断 `gate_load_balance` 已进入 promotion-candidate 级别决策层
- `v2.6 queue planner` 已接入：
  - 当前只服务 `gate_load_balance` 主线
  - 当前只会在 evidence gate 通过时自动补主链标准模板任务
  - 当前不自动发散到 `gate_entropy`、推理协议实现或结构改造
- `v2.7 workflow engine` 已接入：
  - 当前主线已可表示为 `gate_load_balance_promotion` workflow
  - runtime 在无直接 eligible task 时，会先尝试按 workflow stage 实例化下一环
  - 当前只服务 `gate_load_balance` lane，不扩到其它 lane
- `v2.8 program planner` 已接入：
  - 当前主线已具备 `program_state + milestones + decision_memory` 三层项目级控制面
  - `run-autopilot` 在 workflow 完成后，会先按 milestone 判断是否继续、暂停或等待人工决策
  - 当前默认 decision memory 已固定：
    - `gate_load_balance` 是主线候选
    - `gate_entropy` 仅作说明性对照
    - 不恢复 `all`
    - 不提前实现 `is_multilabel` selector
- `v2.9 program runtime continuation` 已接入：
  - 当前主线已具备 `program_budget_state + best_known_metrics + program_handoff` 三层 continuation 资产
  - budget window reset 后，program 可按 milestone 自动恢复，而不是永久停在 `budget_guard_triggered`
  - `multilabel_inference_protocol_decision` 与 `promotion_candidate_followup` 已提升为正式 workflow
  - 当前 program 会用 strict-closeout 通过后的 best-known 指标作为 regression sentinel 基线
  - 当前 program handoff 已可直接解释：当前主目标、active milestone、block reason、next recommended workflow 与 top decisions
- `v2.9.1 dual-output planning chain` 已完成：
  - `dual_output_implementation_plan` 已通过非实验 workflow 自动跑完：
    - `dual_output_plan_evidence_closeout`
    - `dual_output_plan_decision`
    - `dual_output_plan_handoff`
  - 当前决策已写入 `decision_memory`：
    - `dual_output_implementation_plan = dual_output_without_selector`
  - 当前下一步已收敛为：
    - `next_ready_task = dual_output_runtime_patch`
  - 当前 `run-autopilot` 在 program 收敛且无可自动继续 task 时，会优雅结束为：
    - `session_end_reason = program_waiting_for_next_phase`
- `v2.9.2 dual-output runtime patch` 已完成：
  - `dual_output_runtime_patch` 已从占位规划任务升级成真实 `implementation_task`
  - multimodal `evaluate_multimodal` 现在会对所有样本导出 dual-output 视图：
    - `multilabel_positive_indices`
    - `multilabel_positive_scores`
    - `multilabel_topk_indices`
    - `multilabel_topk_scores`
    - `multilabel_active_for_metrics`
  - `metrics_{split}.json` / `summary.json` 已新增 `dual_output` / `dual_output_runtime` 运行时标记
  - multilabel metrics 仍只在 `multilabel_target_mask=true` 的样本上计算，不改变当前训练/评估语义
  - 当前下一步已收敛为：
    - `next_ready_task = dual_output_report_closeout`
- C 线当前 prepack 摘要 `storage_layout=unknown` 已知不阻塞 staging，但需要在每次复核报告中持续记录并跟踪
- `all` 暂不恢复，直到 context branch 先被重做并重新验证
- active baseline 的工程默认心智保持为：
  - `shared-bank prepack`
  - Windows 本地开发机 `num_workers=0`
  - baseline 评估默认优先 `metrics-only`

## 当前活跃任务

- [2026-03-29-rebuild-context-branch-v2.md](D:/data/ai4s/holophage/tasks/2026-03-29-rebuild-context-branch-v2.md)（收尾归档）
- [2026-03-31-multilabel-head-wiring.md](D:/data/ai4s/holophage/tasks/2026-03-31-multilabel-head-wiring.md)
- [2026-03-31-multimodal-multilabel-mini-validation.md](D:/data/ai4s/holophage/tasks/2026-03-31-multimodal-multilabel-mini-validation.md)
- [2026-03-31-multimodal-gate-collapse-analysis.md](D:/data/ai4s/holophage/tasks/2026-03-31-multimodal-gate-collapse-analysis.md)
- [2026-03-31-gate-health-guard.md](D:/data/ai4s/holophage/tasks/2026-03-31-gate-health-guard.md)
- [2026-03-31-gate-load-balance-strong-staging.md](D:/data/ai4s/holophage/tasks/2026-03-31-gate-load-balance-strong-staging.md)
- [2026-03-31-gate-load-balance-closeout-decision.md](D:/data/ai4s/holophage/tasks/2026-03-31-gate-load-balance-closeout-decision.md)
- [2026-04-01-gate-load-balance-real-case-staging.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-real-case-staging.md)
- [2026-04-01-gate-load-balance-real-case-closeout-decision.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-real-case-closeout-decision.md)
- [2026-04-01-gate-load-balance-higher-budget-staging.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-higher-budget-staging.md)
- [2026-04-01-gate-load-balance-higher-budget-closeout-decision.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-higher-budget-closeout-decision.md)
- [2026-04-01-gate-load-balance-second-seed-higher-budget.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-second-seed-higher-budget.md)
- [2026-04-01-gate-load-balance-second-seed-closeout-decision.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-second-seed-closeout-decision.md)
- [2026-04-01-gate-load-balance-promotion-readiness-review.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-promotion-readiness-review.md)
- [2026-04-01-gate-load-balance-extended-real-case-staging.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-extended-real-case-staging.md)
- [2026-04-01-gate-load-balance-extended-real-case-closeout-decision.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-extended-real-case-closeout-decision.md)
- [2026-04-01-gate-load-balance-promotion-candidate-decision.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-promotion-candidate-decision.md)
- [2026-04-01-multilabel-inference-protocol-design.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-inference-protocol-design.md)
- [2026-04-01-gate-entropy-reference-check.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-entropy-reference-check.md)
- [2026-03-31-v21-autopilot-trial-truth-calibration.md](D:/data/ai4s/holophage/tasks/2026-03-31-v21-autopilot-trial-truth-calibration.md)
- [2026-03-31-v22-autopilot-trial-implementation-small.md](D:/data/ai4s/holophage/tasks/2026-03-31-v22-autopilot-trial-implementation-small.md)
- [2026-03-31-v25-autopilot-trial-experiment-smoke.md](D:/data/ai4s/holophage/tasks/2026-03-31-v25-autopilot-trial-experiment-smoke.md)

## 当前不在本轮范围

下面这些不属于当前 sprint：

- ontology 大改
- split 策略升级
- open-set head 正式接入
- 把 `all` 三模态直接恢复成当前主线

## 本阶段不再优先做

- 不再继续 Windows worker benchmark
- 不再继续 C 线 sampler 微优化
- 不再继续做 pack/schema 大改
- 不直接切 C 为正式默认

## 使用规则

1. 先读本文件，再进入当前任务文件。
2. 如果 sprint 焦点变化，先更新本文件，再更新对应 `tasks/`。
3. 不要从 archive 或旧计划文档反推当前 sprint。
