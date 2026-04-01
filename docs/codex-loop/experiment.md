# Experiment Workflow

You are working on a V2 `experiment_run`.

## Purpose

- run or inspect a structured experiment
- keep the run linked to one `task_id`
- preserve closeout readiness
- provide a clean `execution_result.json`
- leave a replayable `experiment_transcript.jsonl`

## What This Workflow Tracks

- `run_dir`
- `summary.json`
- `metrics_val.json`
- `metrics_test.json`
- experiment registry draft fields

## Registry Draft

The V2 registry draft reader extracts:

- `run_name`
- `variant`
- `seed`
- `best_epoch`
- `best_val_l3_macro_f1`
- `best_val_multilabel_micro_f1`
- `mean_gates`
- closeout artifact paths

This draft is not the same as final experiment state promotion.

## Hard Rules

1. Do not auto-promote an experiment.
2. Do not switch defaults.
3. Do not treat missing closeout artifacts as success.
4. Keep the execution result structured and evidence-based.
5. For unattended `experiment_run`, keep it to short smoke experiments only.
6. Always record actual checks, actual artifacts, and transcript steps.
