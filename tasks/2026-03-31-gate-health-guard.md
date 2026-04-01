# Gate Health Guard

更新时间：2026-03-31

## 目标

- 在不改变当前正式主线 truth 的前提下，为 multimodal multilabel 评估与 closeout 增加机器可读的 `gate_health`
- 不再只靠人工阅读 `mean_gates` 判断 sequence-only collapse

## 范围

- 允许修改：
  - `baseline/evaluate_multimodal.py`
  - `skills/results-closeout-lite/`
  - 必要的对应测试
- 不修改模型结构
- 不修改 loss
- 不切默认配置

## Success Criteria

- `metrics_val.json` / `metrics_test.json` 中包含结构化 `gate_health`
- `results-closeout-lite` 输出中包含最小 `gate_health` 摘要
- 旧指标结构不回退
- 相关 tests 通过

## 非目标

- 本任务不做新实验
- 本任务不决定是否 promote/demote 某个候选配置

## Outcome

- 已完成
- `baseline/evaluate_multimodal.py` 现在会稳定导出结构化 `gate_health`
- `results-closeout-lite` 现在会在 JSON / markdown 输出中给出 `gate_health` 摘要
- `experiment registry` 与 `report template` 已能携带 `gate_health`
- 相关回归通过：
  - `conda run -n ai4s python -m unittest baseline.tests.test_multimodal_multilabel_head_wiring`
  - `conda run -n ai4s python -m unittest skills.tests.test_workflow_skills`
  - `conda run -n ai4s python -m unittest integrations.codex_loop.tests.test_codex_loop`
