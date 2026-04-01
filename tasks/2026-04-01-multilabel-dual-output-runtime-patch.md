# Multilabel Dual Output Runtime Patch

更新时间：2026-04-01

## 目标

- 实现最小安全的 multimodal dual-output runtime patch，让层级分类输出与 multilabel 推理输出可以同时被导出与消费。

## 当前真相依赖

- [current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)
- [2026-04-01-multilabel-dual-output-implementation-plan.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-dual-output-implementation-plan.md)

## Success Criteria

- 为所有样本稳定导出 multilabel dual-output 推理视图
- 保持 multilabel metrics 仍只在 `multilabel_target_mask=true` 的样本上计算
- 执行完成后下一步收敛到 `dual_output_report_closeout` 或 `dual_output_hold_closeout`

## 非目标

- 不切 production default
- 不引入 `is_multilabel` selector
