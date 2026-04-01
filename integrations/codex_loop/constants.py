from __future__ import annotations

import os
from pathlib import Path

SCHEMA_VERSION = 2
LOOP_ID = "holophage-main-loop"

REPO_ROOT = Path(__file__).resolve().parents[2]
LOOP_HOME = Path(os.environ.get("HOLOPHAGE_LOOP_HOME", str(REPO_ROOT))).resolve()
DOCS_DIR = REPO_ROOT / "docs" / "codex-loop"
LOOP_STATE_DIR = LOOP_HOME / "loop_state"
LOOP_RUNS_DIR = LOOP_HOME / "loop_runs"
TASK_REGISTRY_DIR = LOOP_STATE_DIR / "tasks"
EXPERIMENT_REGISTRY_DIR = LOOP_STATE_DIR / "experiments"
WORKFLOW_STATE_DIR = LOOP_STATE_DIR / "workflows"
EVENTS_PATH = LOOP_STATE_DIR / "events.jsonl"
RUNTIME_SESSION_PATH = LOOP_STATE_DIR / "runtime_session.json"
RUNTIME_SESSION_HISTORY_PATH = LOOP_STATE_DIR / "runtime_session_history.jsonl"
QUEUE_PLANNER_STATE_PATH = LOOP_STATE_DIR / "queue_planner_state.json"
PROGRAM_STATE_PATH = LOOP_STATE_DIR / "program_state.json"
MILESTONES_PATH = LOOP_STATE_DIR / "milestones.json"
DECISION_MEMORY_PATH = LOOP_STATE_DIR / "decision_memory.jsonl"
PROGRAM_BUDGET_STATE_PATH = LOOP_STATE_DIR / "program_budget_state.json"
BEST_KNOWN_METRICS_PATH = LOOP_STATE_DIR / "best_known_metrics.json"
PROGRAM_HANDOFF_PATH = LOOP_STATE_DIR / "program_handoff.json"
JSONSCHEMA_DIR = REPO_ROOT / "integrations" / "codex_loop" / "jsonschema"

ACTIVE_ASSETS_DIR = REPO_ROOT / "project_memory" / "04_active_assets"
ACTIVE_VERSION_PATH = ACTIVE_ASSETS_DIR / "ACTIVE_VERSION.yaml"
ACTIVE_PATHS_PATH = ACTIVE_ASSETS_DIR / "ACTIVE_PATHS.yaml"
ACTIVE_RUNTIME_CONTRACT_PATH = ACTIVE_ASSETS_DIR / "ACTIVE_RUNTIME_CONTRACT.md"
CURRENT_SPRINT_PATH = REPO_ROOT / "docs" / "current-sprint.md"
TASKS_DIR = REPO_ROOT / "tasks"
GENERATED_TASKS_DIR = Path(os.environ.get("HOLOPHAGE_LOOP_TASKS_DIR", str(TASKS_DIR))).resolve()
HANDOFF_DIR = REPO_ROOT / "handoff"
REPORTS_DIR = REPO_ROOT / "reports"
SKILLS_DIR = REPO_ROOT / "skills"
SKILL_REGISTRY_PATH = SKILLS_DIR / "registry.json"
SKILL_ROUTING_PATH = SKILLS_DIR / "ROUTING.md"
RUN_SKILL_PATH = SKILLS_DIR / "run-skill.ps1"

CURRENT_STATE_PATH = LOOP_STATE_DIR / "current_state.json"
ACTIVE_OBJECTIVE_PATH = LOOP_STATE_DIR / "active_objective.json"
INTERVENTION_POLICY_PATH = LOOP_STATE_DIR / "intervention_policy.json"
TASK_INDEX_PATH = LOOP_STATE_DIR / "task_index.json"
EXPERIMENT_INDEX_PATH = LOOP_STATE_DIR / "experiment_index.json"

PLANNER_PACKET_NAME = "planner_input_packet.json"
PLANNER_DECISION_NAME = "planner_decision.json"
EXECUTION_RESULT_NAME = "execution_result.json"
REVIEW_VERDICT_NAME = "review_verdict.json"
ROUND_SUMMARY_NAME = "round_summary.md"
STAGE_CHECKPOINT_NAME = "stage_checkpoint.json"
IMPLEMENTATION_TRANSCRIPT_NAME = "implementation_transcript.jsonl"
EXPERIMENT_TRANSCRIPT_NAME = "experiment_transcript.jsonl"
PLANNER_WORKSPACE_NAME = "planner_workspace.json"
EXECUTOR_WORKSPACE_NAME = "executor_workspace.json"
IMPLEMENTATION_WORKSPACE_NAME = "implementation_workspace.json"
EXPERIMENT_WORKSPACE_NAME = "experiment_workspace.json"
REVIEWER_WORKSPACE_NAME = "reviewer_workspace.json"
PLANNER_DECISION_TEMPLATE_NAME = "planner_decision.template.json"
EXECUTION_RESULT_TEMPLATE_NAME = "execution_result.template.json"
REVIEW_VERDICT_TEMPLATE_NAME = "review_verdict.template.json"
HANDOFF_TEMPLATE_NAME = "handoff.template.md"
REPORT_TEMPLATE_NAME = "report.template.md"

PLANNER_PROMPT_PATH = DOCS_DIR / "planner.md"
EXECUTOR_PROMPT_PATH = DOCS_DIR / "executor.md"
REVIEWER_PROMPT_PATH = DOCS_DIR / "reviewer.md"
IMPLEMENTATION_PROMPT_PATH = DOCS_DIR / "implementation.md"
EXPERIMENT_PROMPT_PATH = DOCS_DIR / "experiment.md"
PLANNER_WINDOW_TEMPLATE_PATH = DOCS_DIR / "planner-window-template.md"
EXECUTOR_WINDOW_TEMPLATE_PATH = DOCS_DIR / "executor-window-template.md"
REVIEWER_WINDOW_TEMPLATE_PATH = DOCS_DIR / "reviewer-window-template.md"
IMPLEMENTATION_WINDOW_TEMPLATE_PATH = DOCS_DIR / "implementation-window-template.md"
EXPERIMENT_WINDOW_TEMPLATE_PATH = DOCS_DIR / "experiment-window-template.md"

TASK_TYPE_TO_SKILL = {
    "truth_calibration": {
        "skill": "active-truth-calibration",
        "default_args": {"format": "json"},
    },
    "governance_refresh": {
        "skill": "governance-assets-build-validate",
        "default_args": {},
    },
    "results_closeout": {
        "skill": "results-closeout-lite",
        "default_args": {"format": "json"},
    },
    "multilabel_readiness_audit": {
        "skill": "governance-to-multilabel-audit",
        "default_args": {"format": "json"},
    },
    "artifact_repair": {
        "skill": "evaluation-artifacts-complete",
        "default_args": {"format": "json"},
    },
}

ALLOWED_TASK_TYPES = tuple(TASK_TYPE_TO_SKILL.keys())
ALLOWED_WORKFLOW_KINDS = (
    "truth_calibration",
    "governance_refresh",
    "results_closeout",
    "multilabel_readiness_audit",
    "implementation_task",
    "experiment_run",
    "artifact_repair",
)
ALLOWED_ACTION_KINDS = ("skill", "implementation", "experiment", "artifact_repair")
ALLOWED_RISK_LEVELS = ("low", "medium", "high")
ALLOWED_REVIEW_VERDICTS = ("approve", "revise", "escalate")
ALLOWED_RECOMMENDED_NEXT_MODES = ("continue", "replan", "pause_for_human", "complete")
ALLOWED_STATES = (
    "idle",
    "context_ready",
    "planner_workspace_ready",
    "planned",
    "executor_workspace_ready",
    "implementation_workspace_ready",
    "experiment_workspace_ready",
    "gated",
    "executed",
    "reviewer_workspace_ready",
    "reviewed",
    "paused_for_human",
    "completed",
)
ALLOWED_WORKSPACE_ROLES = ("planner", "executor", "reviewer")
ALLOWED_WORKSPACE_KINDS = ("planner", "executor", "implementation", "experiment", "reviewer")
ALLOWED_TASK_STATUSES = (
    "proposed",
    "ready",
    "implementing",
    "running",
    "evaluating",
    "blocked",
    "paused_for_human",
    "completed",
)
ALLOWED_CHECKPOINT_STAGES = (
    "lease_acquired",
    "task_selected",
    "plan_packet_prepared",
    "planner_decision_written",
    "execution_started",
    "execution_finished",
    "review_started",
    "review_finished",
    "state_committed",
)
ALLOWED_EXPERIMENT_STATUSES = ("candidate", "staging", "accepted", "rejected", "archived", "blocked")
ALLOWED_CLOSEOUT_STATUSES = ("pending", "ready", "passed", "failed", "repaired")
ALLOWED_WORKFLOW_TEMPLATES = (
    "gate_load_balance_validation",
    "gate_load_balance_promotion",
    "implementation_fix_then_retest",
    "multilabel_inference_protocol_decision",
    "promotion_candidate_followup",
    "dual_output_implementation_plan",
)
ALLOWED_WORKFLOW_STATUSES = ("proposed", "active", "blocked", "completed", "paused")
AUTOCONTINUE_WORKFLOW_KINDS = (
    "truth_calibration",
    "governance_refresh",
    "results_closeout",
    "multilabel_readiness_audit",
    "artifact_repair",
    "experiment_run",
)

DEFAULT_INTERVENTION_POLICY = {
    "hard_stop": [
        "active_truth_conflict",
        "governance_validation_failed",
        "results_closeout_strict_artifacts_missing",
        "audit_fail_item_detected",
        "attempt_modify_ontology",
        "attempt_switch_default_config",
        "attempt_promote_demote",
        "attempt_destructive_operation",
        "reviewer_detected_drift",
    ],
    "soft_stop": [
        "two_rounds_no_progress",
        "planner_reviewer_conflict",
        "recoverable_incomplete_artifacts",
        "cross_sprint_decision_needed",
    ],
    "max_auto_rounds_per_task": 3,
    "max_auto_rounds_total": 12,
    "max_consecutive_no_progress": 2,
    "max_run_wall_clock_minutes": 45,
    "stale_after_seconds": 1800,
    "max_retries_per_task": 2,
    "allowed_unattended_workflow_kinds": [
        "truth_calibration",
        "governance_refresh",
        "results_closeout",
        "multilabel_readiness_audit",
        "artifact_repair",
    ],
    "default_unattended_risk_level": "low",
    "pause_on_review_revise": True,
    "night_mode_low_risk_only": False,
    "allow_unattended_implementation": False,
    "implementation_max_files_touched": 4,
    "implementation_max_diff_lines": 200,
    "implementation_require_all_checks_pass": True,
    "implementation_pause_on_partial_write": True,
    "implementation_allowed_command_prefixes": ["python", "conda", "pwsh", "git"],
    "implementation_forbidden_command_prefixes": ["cmd", "powershell", "bash", "sh"],
    "implementation_forbidden_command_substrings": ["rm ", "del ", "Remove-Item", "git reset --hard", "format "],
    "implementation_require_pwsh_for_checks": True,
    "allow_unattended_experiment": False,
    "experiment_allowed_command_prefixes": ["python", "conda", "pwsh"],
    "experiment_forbidden_command_prefixes": ["cmd", "powershell", "bash", "sh"],
    "experiment_forbidden_command_substrings": ["rm ", "del ", "Remove-Item", "git reset --hard", "format "],
    "experiment_max_wall_clock_minutes": 20,
    "experiment_require_summary_json": True,
    "experiment_require_metrics": False,
    "experiment_required_artifacts": ["summary.json"],
    "experiment_pause_on_missing_artifacts": True,
    "idle_sleep_seconds": 15,
    "backoff_multiplier": 2.0,
    "max_idle_sleep_seconds": 300,
    "wake_on_stale_run": True,
    "wake_on_cooldown_expiry": True,
    "wake_on_task_registry_change": True,
    "max_runner_session_minutes": 120,
    "max_runner_session_rounds": 50,
    "enable_queue_planner": False,
    "queue_planner_max_generated_tasks": 3,
    "queue_planner_allowed_templates": [
        "results_closeout",
        "experiment_run",
        "truth_calibration",
        "promotion_readiness_review",
        "promotion_candidate_decision",
    ],
    "queue_planner_max_budget_level": "extended_real_case",
    "queue_planner_require_closeout_pass": True,
    "queue_planner_allow_auxiliary_tasks": False,
    "queue_planner_active_lane": "gate_load_balance",
    "enable_workflow_engine": True,
    "program_max_active_workflows": 1,
    "program_max_failed_workflows_per_lane": 2,
    "program_max_experiments_per_day": 3,
    "program_gpu_budget_minutes_per_day": 360,
    "program_pause_on_budget_exhausted": True,
}

FORBIDDEN_ARG_TOKENS = (
    "ontology",
    "promote",
    "demote",
    "default",
    "delete",
    "remove-item",
    "rm ",
    "del ",
    "format c:",
)

FORBIDDEN_WRITE_TOKENS = (
    "project_memory/04_active_assets",
    "outputs/label_vocab_l3_core.json",
    "outputs/label_vocab_l2.json",
    "outputs/label_vocab_l1.json",
)
