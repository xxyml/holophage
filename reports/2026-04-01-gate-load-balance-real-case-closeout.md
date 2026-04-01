# Gate Load Balance Real Case Closeout

更新时间：2026-04-01

## Summary

- `gate_load_balance real_case_staging` 已完成真实案例实测，并通过 strict closeout
- 当前结论继续支持 `gate_load_balance` 作为首选 staging 候选
- 当前已足够进入下一轮更高预算实测
- `V2.5` 在真实主线任务上没有暴露新的内核级阻塞，但暴露了两个已修复的任务契约坑与一个流程体验缺口

## Run

- run:
  - [summary.json](D:/data/ai4s/holophage/baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_real_case_staging/summary.json)
- experiment registry:
  - [multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_real_case_staging__seed42.json](D:/data/ai4s/holophage/loop_state/experiments/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_real_case_staging__seed42.json)
- closeout round:
  - [round_summary.md](D:/data/ai4s/holophage/loop_runs/2026-04-01T00-54-06/round_summary.md)

## Key Results

- `best_val_l3_macro_f1 ≈ 0.9640`
- `best_val_multilabel_micro_f1 ≈ 0.8881`
- `val mean_gates ≈ 0.328 / 0.265 / 0.407`
- `gate_health = healthy`
- `closeout_status = ready`
- required closeout artifacts 全部存在

## Decision

- `gate_load_balance` 继续作为当前首选 staging 候选
- 当前可以进入更高预算实测
- 当前不建议切 production default
- `gate_entropy` 继续仅保留为解释性对照

## V2.5 Validation Notes

- `experiment_run` 已在真实主线任务上跑通完整闭环
- `results_closeout` 已在真实主线 run 上跑通完整闭环
- 本轮真实运行暴露并已修复两个任务契约问题：
  - `experiment_command` 不能用 `python baseline/train.py`，应改为模块方式
  - 多模态配置必须走 `baseline.train_multimodal`
- 本轮还暴露一个流程体验缺口：
  - `resume-task` / 失败重试后的 state reset 语义仍不够顺滑，现场清理还偏手工
