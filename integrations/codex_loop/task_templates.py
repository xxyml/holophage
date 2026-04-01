from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from integrations.codex_loop.constants import (
    GENERATED_TASKS_DIR,
    REPO_ROOT,
)


def _today_slug() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def _task_path(task_id: str) -> Path:
    return GENERATED_TASKS_DIR / f"{task_id}.md"


def _title_from_stage(stage_slug: str) -> str:
    words = [part.capitalize() for part in stage_slug.replace("-", " ").split()]
    return "Gate Load Balance " + " ".join(words)


def _markdown(
    *,
    title: str,
    goals: list[str],
    dependencies: list[str],
    success_criteria: list[str],
    non_goals: list[str] | None = None,
    required_questions: list[str] | None = None,
) -> str:
    lines = [f"# {title}", "", f"更新时间：{_today_slug()}", "", "## 目标", ""]
    lines.extend(f"- {item}" for item in goals)
    lines.extend(["", "## 当前真相依赖", ""])
    lines.extend(f"- {item}" for item in dependencies)
    lines.extend(["", "## Success Criteria", ""])
    lines.extend(f"- {item}" for item in success_criteria)
    if required_questions:
        lines.extend(["", "## 必答问题", ""])
        lines.extend(f"{idx}. {item}" for idx, item in enumerate(required_questions, start=1))
    if non_goals:
        lines.extend(["", "## 非目标", ""])
        lines.extend(f"- {item}" for item in non_goals)
    return "\n".join(lines) + "\n"


def build_results_closeout_task(
    *,
    task_id: str,
    title: str,
    objective: str,
    run_dir: str | list[str],
    dependencies: list[str],
    success_criteria: list[str],
    required_questions: list[str],
    priority: int,
    source_evidence_ids: list[str],
    template_name: str,
) -> dict[str, Any]:
    skill_args: dict[str, Any] = {"mode": "strict_closeout", "format": "json"}
    skill_args["run_dir"] = run_dir
    markdown = _markdown(
        title=title,
        goals=[objective],
        dependencies=dependencies,
        success_criteria=success_criteria,
        required_questions=required_questions,
        non_goals=[
            "不切 production default",
            "不改 multilabel head 或当前损失结构",
        ],
    )
    return {
        "task_id": task_id,
        "task_path": _task_path(task_id),
        "markdown": markdown,
        "create_kwargs": {
            "workflow_kind": "results_closeout",
            "objective": objective,
            "risk_level": "low",
            "skill_args": skill_args,
        },
        "record_overrides": {
            "status": "ready",
            "priority": priority,
            "autopilot_enabled": True,
            "generated_by": "queue_planner",
            "generation_reason": template_name,
            "source_evidence_ids": source_evidence_ids,
            "template_name": template_name,
        },
    }


def build_experiment_task(
    *,
    task_id: str,
    title: str,
    objective: str,
    config_path: str,
    run_dir: str,
    dependencies: list[str],
    success_criteria: list[str],
    priority: int,
    required_checks: list[str],
    experiment_required_artifacts: list[str],
    source_evidence_ids: list[str],
    template_name: str,
) -> dict[str, Any]:
    markdown = _markdown(
        title=title,
        goals=[objective],
        dependencies=dependencies,
        success_criteria=success_criteria,
        non_goals=[
            "不改结构，不改 gate 正则形式",
            "不恢复 `all`，不并行推进 `gate_entropy`",
        ],
    )
    return {
        "task_id": task_id,
        "task_path": _task_path(task_id),
        "markdown": markdown,
        "create_kwargs": {
            "workflow_kind": "experiment_run",
            "objective": objective,
            "risk_level": "low",
            "required_checks": required_checks,
            "experiment_command": f"conda run -n ai4s python -m baseline.train_multimodal --config {config_path}",
            "experiment_run_dir": run_dir,
            "experiment_required_artifacts": experiment_required_artifacts,
            "experiment_config_path": config_path,
        },
        "record_overrides": {
            "status": "ready",
            "priority": priority,
            "autopilot_enabled": True,
            "generated_by": "queue_planner",
            "generation_reason": template_name,
            "source_evidence_ids": source_evidence_ids,
            "template_name": template_name,
        },
    }


def build_skill_task(
    *,
    task_id: str,
    title: str,
    objective: str,
    workflow_kind: str,
    dependencies: list[str],
    success_criteria: list[str],
    priority: int,
    source_evidence_ids: list[str],
    template_name: str,
    skill_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    markdown = _markdown(
        title=title,
        goals=[objective],
        dependencies=dependencies,
        success_criteria=success_criteria,
        non_goals=[
            "不切 production default",
            "不引入新的开放式研究实验",
        ],
    )
    return {
        "task_id": task_id,
        "task_path": _task_path(task_id),
        "markdown": markdown,
        "create_kwargs": {
            "workflow_kind": workflow_kind,
            "objective": objective,
            "risk_level": "low",
            "skill_args": dict(skill_args or {}),
        },
        "record_overrides": {
            "status": "ready",
            "priority": priority,
            "autopilot_enabled": True,
            "generated_by": "queue_planner",
            "generation_reason": template_name,
            "source_evidence_ids": source_evidence_ids,
            "template_name": template_name,
        },
    }


def build_implementation_task(
    *,
    task_id: str,
    title: str,
    objective: str,
    dependencies: list[str],
    success_criteria: list[str],
    priority: int,
    source_evidence_ids: list[str],
    template_name: str,
    allowed_write_paths: list[str],
    required_checks: list[str],
) -> dict[str, Any]:
    markdown = _markdown(
        title=title,
        goals=[objective],
        dependencies=dependencies,
        success_criteria=success_criteria,
        non_goals=[
            "不启动新的训练实验",
            "不引入 `is_multilabel` selector",
        ],
    )
    return {
        "task_id": task_id,
        "task_path": _task_path(task_id),
        "markdown": markdown,
        "create_kwargs": {
            "workflow_kind": "implementation_task",
            "objective": objective,
            "risk_level": "low",
            "allowed_write_paths": list(allowed_write_paths),
            "required_checks": list(required_checks),
        },
        "record_overrides": {
            "status": "ready",
            "priority": priority,
            "autopilot_enabled": False,
            "generated_by": "queue_planner",
            "generation_reason": template_name,
            "source_evidence_ids": source_evidence_ids,
            "template_name": template_name,
        },
    }


def build_gate_load_balance_template(template_name: str, *, source_evidence_ids: list[str]) -> dict[str, Any]:
    date_prefix = _today_slug()
    if template_name == "promotion_readiness_review":
        task_id = f"{date_prefix}-gate-load-balance-promotion-readiness-review"
        return build_results_closeout_task(
            task_id=task_id,
            title="Gate Load Balance Promotion Readiness Review",
            objective="Aggregate real_case, higher_budget, and second_seed evidence into a promotion-readiness review.",
            run_dir=[
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_real_case_staging",
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_higher_budget_staging",
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_higher_budget_staging_seed52",
            ],
            dependencies=[
                "[ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)",
                "[ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)",
                "[ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)",
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
            ],
            success_criteria=[
                "对三轮 run 的 artifact facts 形成统一只读汇总",
                "明确回答是否进入更大规模 staging 与 promotion candidate 级别",
            ],
            required_questions=[
                "是否进入更大规模 staging",
                "是否已经达到 promotion candidate 级别",
                "是否仍需额外 seed / 额外真实案例",
                "loop 是否仍有会阻塞主线推进的 runtime 问题",
            ],
            priority=10,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    if template_name == "promotion_candidate_decision":
        task_id = f"{date_prefix}-gate-load-balance-promotion-candidate-decision"
        return build_results_closeout_task(
            task_id=task_id,
            title="Gate Load Balance Promotion Candidate Decision",
            objective="Aggregate readiness + extended real-case evidence and decide whether gate_load_balance now qualifies as a promotion candidate.",
            run_dir=[
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_real_case_staging",
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_higher_budget_staging",
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_higher_budget_staging_seed52",
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging",
            ],
            dependencies=[
                "[ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)",
                "[ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)",
                "[ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)",
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
                "[2026-04-01-gate-load-balance-promotion-readiness-review.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-promotion-readiness-review.md)",
                "[2026-04-01-gate-load-balance-extended-real-case-closeout-decision.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-extended-real-case-closeout-decision.md)",
            ],
            success_criteria=[
                "形成统一严格 closeout 结论",
                "明确回答是否进入 promotion candidate",
                "明确回答是否还需要额外 seed / 更大规模 staging",
            ],
            required_questions=[
                "gate_load_balance 是否已具备 promotion candidate 级别",
                "当前是否仍需额外 seed 或更大规模 staging",
                "loop 是否仍有会阻塞主线推进的 runtime / recovery / closeout 暗病",
            ],
            priority=40,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    if template_name == "extended_real_case_staging":
        task_id = f"{date_prefix}-gate-load-balance-extended-real-case-staging"
        return build_experiment_task(
            task_id=task_id,
            title="Gate Load Balance Extended Real Case Staging",
            objective="Run a stronger extended real-case staging experiment for gate_load_balance after readiness review approval.",
            config_path="baseline/train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_load_balance.extended_real_case_staging.yaml",
            run_dir="baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging",
            dependencies=[
                "[ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)",
                "[ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)",
                "[ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)",
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
                "[2026-04-01-gate-load-balance-promotion-readiness-review.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-promotion-readiness-review.md)",
            ],
            success_criteria=[
                "summary.json、metrics_val.json、metrics_test.json 齐全",
                "gate_health.status != collapsed",
                "mean_gates.sequence < 0.95 且 structure + context > 0.05",
            ],
            priority=20,
            required_checks=[
                "pwsh -Command Test-Path baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging/summary.json",
            ],
            experiment_required_artifacts=[
                "summary.json",
                "evaluation/metrics_val.json",
                "evaluation/metrics_test.json",
            ],
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    if template_name == "extended_real_case_closeout":
        task_id = f"{date_prefix}-gate-load-balance-extended-real-case-closeout-decision"
        return build_results_closeout_task(
            task_id=task_id,
            title="Gate Load Balance Extended Real Case Closeout Decision",
            objective="Strict-close the extended real-case gate_load_balance run and decide whether to enter promotion-candidate decision.",
            run_dir="baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging",
            dependencies=[
                "[ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)",
                "[ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)",
                "[ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)",
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
            ],
            success_criteria=[
                "strict closeout 通过",
                "明确回答是否进入 promotion_candidate_decision",
            ],
            required_questions=[
                "更强真实案例是否继续支持 gate_load_balance",
                "当前是否进入 promotion_candidate_decision",
                "是否仍存在会阻塞持续运行主线的 loop 问题",
            ],
            priority=30,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    if template_name == "inference_protocol_evidence_closeout":
        task_id = f"{date_prefix}-multilabel-inference-protocol-evidence-closeout"
        return build_results_closeout_task(
            task_id=task_id,
            title="Multilabel Inference Protocol Evidence Closeout",
            objective="Summarize the current gate_load_balance promotion evidence and isolate what is still unknown about inference-time multilabel activation.",
            run_dir=[
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_real_case_staging",
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_higher_budget_staging",
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_higher_budget_staging_seed52",
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging",
            ],
            dependencies=[
                "[ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)",
                "[ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)",
                "[ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)",
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
                "[2026-04-01-multilabel-inference-protocol-design.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-inference-protocol-design.md)",
            ],
            success_criteria=[
                "形成只读证据汇总",
                "明确当前推理协议决策仍未闭合的关键问题",
            ],
            required_questions=[
                "当前 multilabel 推理协议的关键未决问题是什么",
                "现有证据是否已经足够做出协议层决策",
            ],
            priority=50,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    if template_name == "inference_protocol_decision":
        task_id = f"{date_prefix}-multilabel-inference-protocol-decision"
        return build_skill_task(
            task_id=task_id,
            title="Multilabel Inference Protocol Decision",
            objective="Produce a bounded decision on multilabel inference protocol using the accumulated gate_load_balance evidence.",
            workflow_kind="truth_calibration",
            dependencies=[
                "[ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)",
                "[ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)",
                "[2026-04-01-multilabel-inference-protocol-design.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-inference-protocol-design.md)",
            ],
            success_criteria=[
                "输出 chosen_protocol / rejected_protocols / requires_selector_experiment / ready_for_implementation",
                "结论与当前 decision memory 一致或明确 supersede 关系",
            ],
            priority=60,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
            skill_args={"format": "json", "topic": "multilabel_inference_protocol"},
        )
    if template_name == "inference_protocol_handoff":
        task_id = f"{date_prefix}-multilabel-inference-protocol-handoff"
        return build_results_closeout_task(
            task_id=task_id,
            title="Multilabel Inference Protocol Handoff",
            objective="Close out the inference protocol decision and publish the next implementation recommendation.",
            run_dir=[
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_real_case_staging",
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging",
            ],
            dependencies=[
                "[ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)",
                "[2026-04-01-multilabel-inference-protocol-design.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-inference-protocol-design.md)",
            ],
            success_criteria=[
                "形成结构化 handoff 结论",
                "明确是否进入 implementation follow-up",
            ],
            required_questions=[
                "推理协议是否已准备好进入实现阶段",
                "是否仍需 selector feasibility experiment",
            ],
            priority=70,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    if template_name == "promotion_followup_closeout":
        task_id = f"{date_prefix}-gate-load-balance-promotion-followup-closeout"
        return build_results_closeout_task(
            task_id=task_id,
            title="Gate Load Balance Promotion Follow-up Closeout",
            objective="Close out promotion-candidate evidence and determine the minimal safe follow-up lane.",
            run_dir=[
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging",
            ],
            dependencies=[
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
                "[2026-04-01-gate-load-balance-promotion-candidate-decision.md](D:/data/ai4s/holophage/tasks/2026-04-01-gate-load-balance-promotion-candidate-decision.md)",
            ],
            success_criteria=[
                "明确下一条 follow-up lane 是推理协议决策还是进一步实现/验证",
            ],
            required_questions=[
                "promotion candidate 之后的最小 follow-up workflow 是什么",
            ],
            priority=80,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    if template_name == "promotion_followup_decision":
        task_id = f"{date_prefix}-gate-load-balance-promotion-followup-decision"
        return build_skill_task(
            task_id=task_id,
            title="Gate Load Balance Promotion Follow-up Decision",
            objective="Produce a bounded follow-up decision after promotion candidate closeout.",
            workflow_kind="truth_calibration",
            dependencies=[
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
            ],
            success_criteria=[
                "明确 next recommended workflow",
                "不发散到新的开放式实验搜索",
            ],
            priority=90,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
            skill_args={"format": "json", "topic": "promotion_candidate_followup"},
        )
    if template_name == "dual_output_plan_evidence_closeout":
        task_id = f"{date_prefix}-multilabel-dual-output-plan-evidence-closeout"
        return build_results_closeout_task(
            task_id=task_id,
            title="Multilabel Dual Output Plan Evidence Closeout",
            objective="Aggregate promotion evidence, inference protocol decisions, and current runtime scope to define the dual-output implementation boundary.",
            run_dir=[
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_real_case_staging",
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_higher_budget_staging",
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_higher_budget_staging_seed52",
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging",
            ],
            dependencies=[
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
                "[2026-04-01-multilabel-inference-protocol-design.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-inference-protocol-design.md)",
            ],
            success_criteria=[
                "汇总 dual-output 实现所需的 promotion 证据与推理协议决策",
                "明确 dual-output 实现的输入/输出边界",
            ],
            required_questions=[
                "dual-output 实现当前的输入与输出边界是什么",
                "当前 runtime scope 决策还限制了哪些实现路径",
            ],
            priority=100,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    if template_name == "dual_output_plan_decision":
        task_id = f"{date_prefix}-multilabel-dual-output-plan-decision"
        return build_skill_task(
            task_id=task_id,
            title="Multilabel Dual Output Plan Decision",
            objective="Produce a bounded, machine-readable implementation plan for dual-output multilabel inference.",
            workflow_kind="truth_calibration",
            dependencies=[
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
                "[2026-04-01-multilabel-inference-protocol-design.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-inference-protocol-design.md)",
            ],
            success_criteria=[
                "输出 chosen_protocol / implementation_scope / requires_runtime_api_change / requires_model_output_change / next_action_hint",
                "不直接改模型或推理代码",
            ],
            priority=110,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
            skill_args={"format": "json", "topic": "dual_output_implementation_plan"},
        )
    if template_name == "dual_output_plan_handoff":
        task_id = f"{date_prefix}-multilabel-dual-output-plan-handoff"
        return build_results_closeout_task(
            task_id=task_id,
            title="Multilabel Dual Output Plan Handoff",
            objective="Close out the dual-output implementation plan and hand off the minimal next implementation package.",
            run_dir=[
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging",
            ],
            dependencies=[
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
                "[2026-04-01-multilabel-dual-output-implementation-plan.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-dual-output-implementation-plan.md)",
            ],
            success_criteria=[
                "形成 dual-output 实现链的 handoff",
                "明确下一步只收敛到 patch / report closeout / hold 三选一",
            ],
            required_questions=[
                "dual-output 实现的最小下一步是什么",
                "当前是否需要 runtime API 或 model output 改动",
            ],
            priority=120,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    raise ValueError(f"Unsupported gate_load_balance template: {template_name}")


def build_multilabel_phase2_placeholder(template_name: str, *, source_evidence_ids: list[str]) -> dict[str, Any]:
    date_prefix = _today_slug()
    if template_name == "selector_feasibility_smoke":
        candidate = build_experiment_task(
            task_id=f"{date_prefix}-multilabel-selector-feasibility-smoke",
            title="Multilabel Selector Feasibility Smoke",
            objective="Run the smallest safe experiment to validate whether an is_multilabel selector is needed and learnable.",
            config_path="baseline/train_config.multimodal_v2.seq_struct_ctx_gnn_w4.multilabel_head.gate_load_balance.real_case_staging.yaml",
            run_dir="baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_selector_feasibility_smoke",
            dependencies=[
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
                "[2026-04-01-multilabel-inference-protocol-design.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-inference-protocol-design.md)",
            ],
            success_criteria=[
                "selector feasibility smoke 产物齐全",
                "不会破坏当前 `PFO v1.0.2` / `homology_cluster_v1` / `exact_sequence_rep_id` / `L1 + L2 + L3 core` / `trainable_core` 主线",
            ],
            priority=200,
            required_checks=[
                "pwsh -Command Test-Path baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_selector_feasibility_smoke/summary.json",
            ],
            experiment_required_artifacts=["summary.json"],
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    elif template_name == "dual_output_implementation_plan":
        candidate = build_skill_task(
            task_id=f"{date_prefix}-multilabel-dual-output-implementation-plan",
            title="Multilabel Dual Output Implementation Plan",
            objective="Produce the smallest safe implementation plan for dual-output multilabel inference without introducing a selector first.",
            workflow_kind="truth_calibration",
            dependencies=[
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
                "[2026-04-01-multilabel-inference-protocol-design.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-inference-protocol-design.md)",
            ],
            success_criteria=[
                "明确 dual-output implementation scope",
                "不引入新的开放式研究分支",
            ],
            priority=200,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
            skill_args={"format": "json", "topic": "dual_output_implementation_plan"},
        )
    elif template_name == "inference_hold_closeout":
        candidate = build_results_closeout_task(
            task_id=f"{date_prefix}-multilabel-inference-hold-closeout",
            title="Multilabel Inference Hold Closeout",
            objective="Close out the current inference discussion and explicitly hold further experiment/implementation until new evidence arrives.",
            run_dir=[
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging",
            ],
            dependencies=[
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
                "[2026-04-01-multilabel-inference-protocol-design.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-inference-protocol-design.md)",
            ],
            success_criteria=[
                "明确当前进入 hold，而不是继续实验或实现",
            ],
            required_questions=[
                "为什么当前要 hold",
                "下次解除 hold 需要什么新增证据",
            ],
            priority=200,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    else:
        raise ValueError(f"Unsupported multilabel placeholder template: {template_name}")

    candidate["record_overrides"].update(
        {
            "status": "proposed",
            "autopilot_enabled": False,
            "priority": 900,
        }
    )
    return candidate


def build_multilabel_phase3_placeholder(template_name: str, *, source_evidence_ids: list[str]) -> dict[str, Any]:
    date_prefix = _today_slug()
    if template_name == "dual_output_runtime_patch":
        candidate = build_implementation_task(
            task_id=f"{date_prefix}-multilabel-dual-output-runtime-patch",
            title="Multilabel Dual Output Runtime Patch",
            objective="Implement the smallest safe multimodal dual-output runtime patch so hierarchical outputs and multilabel inference outputs are exported together.",
            dependencies=[
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
                "[2026-04-01-multilabel-dual-output-implementation-plan.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-dual-output-implementation-plan.md)",
            ],
            success_criteria=[
                "为所有样本稳定导出 multilabel dual-output 推理视图",
                "保持 multilabel metrics 仍只在 multilabel_target_mask=true 的样本上计算",
                "执行完成后下一步收敛到 dual_output_report_closeout 或 dual_output_hold_closeout",
            ],
            priority=300,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
            allowed_write_paths=[
                "baseline/evaluate_multimodal.py",
                "baseline/train_multimodal.py",
                "integrations/codex_loop/artifacts.py",
                "integrations/codex_loop/program_planner.py",
            ],
            required_checks=[
                "conda run -n ai4s python -m unittest baseline.tests.test_multimodal_multilabel_head_wiring",
                "conda run -n ai4s python -m unittest integrations.codex_loop.tests.test_codex_loop",
            ],
        )
    elif template_name == "dual_output_report_closeout":
        candidate = build_results_closeout_task(
            task_id=f"{date_prefix}-multilabel-dual-output-report-closeout",
            title="Multilabel Dual Output Report Closeout",
            objective="Close out the implemented dual-output runtime patch and capture the final implementation report.",
            run_dir=[
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging",
            ],
            dependencies=[
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
                "[2026-04-01-multilabel-dual-output-implementation-plan.md](D:/data/ai4s/holophage/tasks/2026-04-01-multilabel-dual-output-implementation-plan.md)",
            ],
            success_criteria=[
                "将已落地的 dual-output runtime patch 收口成最终报告",
            ],
            required_questions=[
                "当前 dual-output runtime patch 实际落地了哪些接口变化",
            ],
            priority=300,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    elif template_name == "dual_output_hold_closeout":
        candidate = build_results_closeout_task(
            task_id=f"{date_prefix}-multilabel-dual-output-hold-closeout",
            title="Multilabel Dual Output Hold Closeout",
            objective="Explicitly hold dual-output implementation and record the gating reason.",
            run_dir=[
                "baseline/runs/multimodal_v2_seq_struct_ctx_gnn_v2a_w4_multilabel_head_gate_load_balance_extended_real_case_staging",
            ],
            dependencies=[
                "[current-sprint.md](D:/data/ai4s/holophage/docs/current-sprint.md)",
            ],
            success_criteria=[
                "明确 why hold，而不是继续实现",
            ],
            required_questions=[
                "当前为什么不能进入 dual-output 实现",
            ],
            priority=300,
            source_evidence_ids=source_evidence_ids,
            template_name=template_name,
        )
    else:
        raise ValueError(f"Unsupported multilabel phase-3 placeholder template: {template_name}")

    candidate["record_overrides"].update(
        {
            "status": "proposed",
            "autopilot_enabled": False,
            "priority": 950,
        }
    )
    return candidate


def build_experiment_closeout_template(
    *,
    source_task_id: str,
    title: str,
    objective: str,
    run_dir: str,
    priority: int,
    source_evidence_ids: list[str],
) -> dict[str, Any]:
    if source_task_id.endswith("-second-seed-higher-budget"):
        task_id = source_task_id.replace("-second-seed-higher-budget", "-second-seed-closeout-decision")
    elif source_task_id.endswith("-higher-budget-staging"):
        task_id = source_task_id.replace("-higher-budget-staging", "-higher-budget-closeout-decision")
    elif source_task_id.endswith("-extended-real-case-staging"):
        task_id = source_task_id.replace("-extended-real-case-staging", "-extended-real-case-closeout-decision")
    elif source_task_id.endswith("-staging"):
        task_id = source_task_id.replace("-staging", "-closeout-decision")
    else:
        task_id = f"{source_task_id}-closeout-decision"
    return build_results_closeout_task(
        task_id=task_id,
        title=title,
        objective=objective,
        run_dir=run_dir,
        dependencies=[
            "[ACTIVE_VERSION.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_VERSION.yaml)",
            "[ACTIVE_PATHS.yaml](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_PATHS.yaml)",
            "[ACTIVE_RUNTIME_CONTRACT.md](D:/data/ai4s/holophage/project_memory/04_active_assets/ACTIVE_RUNTIME_CONTRACT.md)",
            f"[{source_task_id}.md]({str((_task_path(source_task_id)).resolve()).replace(chr(92), '/')})",
        ],
        success_criteria=[
            "strict closeout 通过",
            "形成明确的阶段推进结论",
        ],
        required_questions=[
            "当前 run 是否继续支持 gate_load_balance 作为主候选",
            "当前是否进入下一阶段",
        ],
        priority=priority,
        source_evidence_ids=source_evidence_ids,
        template_name="results_closeout",
    )
