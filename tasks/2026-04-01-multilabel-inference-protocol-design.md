# Multilabel Inference Protocol Design

更新时间：2026-04-01

## 目标

- 明确未来推理时如何处理“未知 multilabel mask”
- 只产出方案，不实现 selector 或新 head

## 当前真相依赖

- [ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)
- [ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)
- [ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)
- [2026-03-31-multilabel-head-wiring.md](D:/data/ai4s/holophage/tasks/2026-03-31-multilabel-head-wiring.md)
- [2026-03-31-multimodal-gate-collapse-analysis.md](D:/data/ai4s/holophage/tasks/2026-03-31-multimodal-gate-collapse-analysis.md)

## 必答问题

1. 推理时是“双输出并存”，还是要新增 `is_multilabel` selector
2. 如果不立刻实现 selector，现阶段对外解释口径是什么
3. 这项设计在什么阶段再转成实现任务最合理
