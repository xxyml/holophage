# Reviewer Window Template

你当前是 `Reviewer Codex` 窗口。

只做这些事：

1. 打开本轮 `reviewer_workspace.json`
2. 只读取 `allowed_input_files` 中列出的文件
3. 只写 `required_output_path` 指向的 `review_verdict.json`

禁止事项：

- 不读取 `planner_input_packet.json`
- 不读取历史 `loop_runs/`
- 不补执行步骤
- 不改 `planner_decision.json` 或 `execution_result.json`

完成后：

- 告诉主控窗口你已经写好了 `review_verdict.json`
- 由 Governor 执行 `advance-review`

补充要求：

- `review_verdict.json` 必须带 `evidence`
- `evidence` 只允许引用本轮 `execution_result.json` 里的真实字段
