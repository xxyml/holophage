from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from integrations.codex_loop.governor import (
    GovernorError,
    advance_review,
    create_task,
    pause_task,
    prepare_executor_workspace,
    prepare_experiment_workspace,
    prepare_handoff_template,
    prepare_plan_packet,
    prepare_planner_decision_template,
    prepare_planner_workspace,
    prepare_report_template,
    prepare_review_verdict_template,
    prepare_reviewer_workspace,
    prepare_implementation_workspace,
    resume_task,
    run_execution,
    sync_experiment_from_run,
)
from integrations.codex_loop.autopilot import run_loop, run_once, resume_stale, show_loop_status
from integrations.codex_loop.program_planner import (
    recompute_program_state,
    reset_budget_window,
    show_best_known,
    show_budget_state,
    show_decisions,
    show_milestones,
    show_program_handoff,
    show_program_plan,
    show_program_status,
)
from integrations.codex_loop.queue_planner import plan_queue, show_queue_plan
from integrations.codex_loop.trial import materialize_policy_defaults, trial_precheck
from integrations.codex_loop.workflow_registry import create_workflow_instance, show_workflow_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Holophage Codex Loop V2 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-task", help="Create a task registry entry from a task markdown file.")
    create.add_argument("--task-file", required=True, help="Path to a task markdown file.")
    create.add_argument("--workflow-kind", default="implementation_task")
    create.add_argument("--objective", default="")
    create.add_argument("--risk-level", default="medium")
    create.add_argument("--allowed-write-path", action="append", default=[])
    create.add_argument("--required-check", action="append", default=[])
    create.add_argument("--skill-arg", action="append", default=[])
    create.add_argument("--experiment-command", default="")
    create.add_argument("--experiment-run-dir", default="")
    create.add_argument("--experiment-required-artifact", action="append", default=[])
    create.add_argument("--experiment-config-path", default="")

    prepare = subparsers.add_parser("prepare-plan-packet", help="Build planner_input_packet.json for a new round.")
    prepare.add_argument("--run-id", default="", help="Optional run id. Defaults to local timestamp.")
    prepare.add_argument("--task-id", default="", help="Task registry id.")
    prepare.add_argument("--task-file", default="", help="Optional task markdown path.")
    prepare.add_argument("--handoff-file", default="", help="Optional handoff markdown path.")

    planner_ws = subparsers.add_parser("prepare-planner-workspace", help="Build planner workspace for a run.")
    planner_ws.add_argument("--run-id", required=True)

    planner_template = subparsers.add_parser("prepare-planner-decision-template", help="Build planner_decision.template.json for a run.")
    planner_template.add_argument("--run-id", required=True)

    executor_ws = subparsers.add_parser("prepare-executor-workspace", help="Build executor workspace for a skill-like decision.")
    executor_ws.add_argument("--decision", required=True)

    impl_ws = subparsers.add_parser("prepare-implementation-workspace", help="Build implementation workspace from planner_decision.json.")
    impl_ws.add_argument("--decision", required=True)

    exp_ws = subparsers.add_parser("prepare-experiment-workspace", help="Build experiment workspace from planner_decision.json.")
    exp_ws.add_argument("--decision", required=True)

    execute = subparsers.add_parser("run-execution", help="Execute a skill-like planner_decision.json.")
    execute.add_argument("--decision", required=True)

    run_impl = subparsers.add_parser("run-implementation", help="Execute an implementation planner_decision.json.")
    run_impl.add_argument("--decision", required=True)

    reviewer_ws = subparsers.add_parser("prepare-reviewer-workspace", help="Build reviewer workspace from execution_result.json.")
    reviewer_ws.add_argument("--execution", required=True)

    reviewer_template = subparsers.add_parser("prepare-review-verdict-template", help="Build review_verdict.template.json from execution_result.json.")
    reviewer_template.add_argument("--execution", required=True)

    sync_exp = subparsers.add_parser("sync-experiment-from-run", help="Create or update an experiment registry entry from a run directory.")
    sync_exp.add_argument("--task-id", required=True)
    sync_exp.add_argument("--run-dir", required=True)
    sync_exp.add_argument("--status", default="candidate")
    sync_exp.add_argument("--config-path", default="")

    pause = subparsers.add_parser("pause-task", help="Pause a task.")
    pause.add_argument("--task-id", required=True)
    pause.add_argument("--reason", default="")

    resume = subparsers.add_parser("resume-task", help="Resume a task.")
    resume.add_argument("--task-id", required=True)

    handoff = subparsers.add_parser("prepare-handoff-template", help="Build a handoff template for a task.")
    handoff.add_argument("--task-id", required=True)

    report = subparsers.add_parser("prepare-report-template", help="Build a report template for a task/experiment.")
    report.add_argument("--task-id", required=True)
    report.add_argument("--experiment-id", required=True)

    review = subparsers.add_parser("advance-review", help="Advance state with review_verdict.json.")
    review.add_argument("--verdict", required=True)

    run_auto = subparsers.add_parser("run-autopilot", help="Run the autopilot loop until a stop condition is met.")
    run_auto.add_argument("--runner-id", default="")
    run_auto.add_argument("--max-rounds", type=int, default=0)
    run_auto.add_argument("--max-session-minutes", type=int, default=0)
    run_auto.add_argument("--max-session-rounds", type=int, default=0)
    run_auto.add_argument("--idle-sleep-seconds", type=int, default=0)
    run_auto.add_argument("--max-idle-sleep-seconds", type=int, default=0)

    run_once_parser = subparsers.add_parser("run-once", help="Run a single autopilot round.")
    run_once_parser.add_argument("--runner-id", default="")

    stale = subparsers.add_parser("resume-stale-run", help="Take over a stale runner lease.")
    stale.add_argument("--runner-id", default="")

    subparsers.add_parser("show-loop-status", help="Show current state, policy, and next eligible task.")
    planner = subparsers.add_parser("plan-queue", help="Generate the next bounded queue tasks when evidence gates pass.")
    planner.add_argument("--max-generated-tasks", type=int, default=0)
    subparsers.add_parser("show-queue-plan", help="Show queue planner state and current candidate generations.")
    create_workflow = subparsers.add_parser("create-workflow-instance", help="Create a workflow instance.")
    create_workflow.add_argument("--template-name", default="gate_load_balance_promotion")
    create_workflow.add_argument("--workflow-id", default="")
    create_workflow.add_argument("--lane", default="")
    workflow_status = subparsers.add_parser("show-workflow-status", help="Show workflow status.")
    workflow_status.add_argument("--workflow-id", default="")
    advance_workflow = subparsers.add_parser("advance-workflow", help="Advance an existing workflow stage.")
    advance_workflow.add_argument("--workflow-id", required=True)
    advance_workflow.add_argument("--next-stage", default="")
    advance_workflow.add_argument("--block-reason", default="")
    subparsers.add_parser("show-program-status", help="Show minimal program state.")
    subparsers.add_parser("show-milestones", help="Show milestone registry state.")
    subparsers.add_parser("show-decisions", help="Show decision memory entries.")
    subparsers.add_parser("show-program-plan", help="Show recomputed program plan.")
    subparsers.add_parser("recompute-program-state", help="Recompute and persist program planner state.")
    subparsers.add_parser("show-budget-state", help="Show program budget ledger.")
    subparsers.add_parser("reset-budget-window", help="Reset program budget ledger.")
    subparsers.add_parser("show-best-known", help="Show best-known metrics registry.")
    subparsers.add_parser("show-program-handoff", help="Show current program handoff summary.")

    subparsers.add_parser("materialize-policy", help="Write the merged V2.1 policy defaults to loop_state/intervention_policy.json.")

    trial_pre = subparsers.add_parser("trial-precheck", help="Run the V2.1 first-trial precheck and emit structured JSON.")
    trial_pre.add_argument("--task-id", default="")

    return parser


def _emit_ok(**payload: str) -> int:
    print(json.dumps({"status": "ok", **payload}, ensure_ascii=False, indent=2))
    return 0


def _stringify_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _parse_skill_args(items: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if "=" not in text:
            raise GovernorError(f"invalid --skill-arg `{text}`; expected key=value")
        key, value = text.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "create-task":
            path = create_task(
                task_file=args.task_file,
                workflow_kind=args.workflow_kind,
                objective=args.objective,
                risk_level=args.risk_level,
                allowed_write_paths=args.allowed_write_path,
                required_checks=args.required_check,
                skill_args=_parse_skill_args(args.skill_arg),
                experiment_command=args.experiment_command,
                experiment_run_dir=args.experiment_run_dir,
                experiment_required_artifacts=args.experiment_required_artifact,
                experiment_config_path=args.experiment_config_path,
            )
            return _emit_ok(task_record=str(path))
        if args.command == "prepare-plan-packet":
            path = prepare_plan_packet(
                run_id=args.run_id or None,
                task_id=args.task_id or None,
                task_file=args.task_file or None,
                handoff_file=args.handoff_file or None,
            )
            return _emit_ok(planner_input_packet=str(path))
        if args.command == "prepare-planner-workspace":
            return _emit_ok(planner_workspace=str(prepare_planner_workspace(args.run_id)))
        if args.command == "prepare-planner-decision-template":
            return _emit_ok(planner_decision_template=str(prepare_planner_decision_template(args.run_id)))
        if args.command == "prepare-executor-workspace":
            return _emit_ok(executor_workspace=str(prepare_executor_workspace(args.decision)))
        if args.command == "prepare-implementation-workspace":
            return _emit_ok(implementation_workspace=str(prepare_implementation_workspace(args.decision)))
        if args.command == "prepare-experiment-workspace":
            return _emit_ok(experiment_workspace=str(prepare_experiment_workspace(args.decision)))
        if args.command == "run-execution":
            return _emit_ok(execution_result=str(run_execution(args.decision)))
        if args.command == "run-implementation":
            return _emit_ok(execution_result=str(run_execution(args.decision)))
        if args.command == "prepare-reviewer-workspace":
            return _emit_ok(reviewer_workspace=str(prepare_reviewer_workspace(args.execution)))
        if args.command == "prepare-review-verdict-template":
            return _emit_ok(review_verdict_template=str(prepare_review_verdict_template(args.execution)))
        if args.command == "sync-experiment-from-run":
            return _emit_ok(experiment_record=str(sync_experiment_from_run(args.task_id, args.run_dir, status=args.status, config_path=args.config_path)))
        if args.command == "pause-task":
            return _emit_ok(task_record=str(pause_task(args.task_id, args.reason)))
        if args.command == "resume-task":
            return _emit_ok(task_record=str(resume_task(args.task_id)))
        if args.command == "prepare-handoff-template":
            return _emit_ok(handoff_template=str(prepare_handoff_template(args.task_id)))
        if args.command == "prepare-report-template":
            return _emit_ok(report_template=str(prepare_report_template(args.task_id, args.experiment_id)))
        if args.command == "advance-review":
            return _emit_ok(round_summary=str(advance_review(args.verdict)))
        if args.command == "run-autopilot":
            result = run_loop(
                args.runner_id or None,
                max_rounds=args.max_rounds or args.max_session_rounds or None,
                max_session_minutes=args.max_session_minutes or None,
                idle_sleep_seconds_override=args.idle_sleep_seconds or None,
                max_idle_sleep_seconds_override=args.max_idle_sleep_seconds or None,
            )
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "run-once":
            result = run_once(args.runner_id or None)
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "resume-stale-run":
            result = resume_stale(args.runner_id or None)
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "show-loop-status":
            result = show_loop_status()
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "plan-queue":
            result = plan_queue(max_generated_tasks=args.max_generated_tasks or None)
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "show-queue-plan":
            result = show_queue_plan()
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "create-workflow-instance":
            result = create_workflow_instance(
                args.template_name,
                workflow_id=args.workflow_id or None,
                lane=args.lane or None,
            )
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "show-workflow-status":
            result = show_workflow_status(args.workflow_id or None)
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "advance-workflow":
            from integrations.codex_loop.workflow_registry import advance_workflow_stage

            result = advance_workflow_stage(
                args.workflow_id,
                next_stage=args.next_stage or None,
                block_reason=args.block_reason or "",
            )
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "show-program-status":
            result = show_program_status()
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "show-milestones":
            result = show_milestones()
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "show-decisions":
            result = show_decisions()
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "show-program-plan":
            result = show_program_plan()
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "recompute-program-state":
            result = recompute_program_state()
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "show-budget-state":
            result = show_budget_state()
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "reset-budget-window":
            result = reset_budget_window()
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "show-best-known":
            result = show_best_known()
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "show-program-handoff":
            result = show_program_handoff()
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        if args.command == "materialize-policy":
            return _emit_ok(policy_path=str(materialize_policy_defaults()))
        if args.command == "trial-precheck":
            result = trial_precheck(args.task_id or "")
            return _emit_ok(**{key: _stringify_value(value) for key, value in result.items()})
        parser.error(f"Unsupported command: {args.command}")
        return 2
    except GovernorError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
