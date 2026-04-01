# V2.2 Autopilot Trial: Minimal Implementation Task

## Goal

验证 `implementation_task` 在 `v2.2` 下可以走通受限自动执行协议，而不会越界写入或跳过 required checks。

## Scope

- 只允许修改 `integrations/codex_loop` 下的 1-2 个小文件
- 不允许修改 active manifest、ontology、默认 config
- 只允许一个最小 unittest 作为 required check

## Success Criteria

- `execution_result.json` 记录真实 `write_set`
- `checks_run` 与 `checks_passed` 来自真实执行
- reviewer 能基于真实执行结果给出 `approve/revise`
- 超范围写入会被 fail-fast 并转 `paused_for_human`

## Candidate Change Shape

- 小型控制层修补
- 小型测试补丁
- 小型文档同步
