# V2.5 Autopilot Trial Experiment Smoke

## Goal

验证 `experiment_run` 在 `V2.5` 中可以走通：

- autopilot plan
- smoke experiment execution
- artifact scan
- required checks
- reviewer
- registry sync preview
- closeout state update

## Contract

- workflow_kind: `experiment_run`
- risk_level: `low`
- run mode: unattended smoke only
- required artifact: `summary.json`
- required checks: at least one

## Success

- `execution_result.json` 记录真实 experiment 证据
- `experiment_transcript.jsonl` 可定位失败 step
- 缺少关键 artifact 时稳定转 `paused_for_human`
