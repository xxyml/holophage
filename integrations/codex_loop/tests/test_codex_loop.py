from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class CodexLoopV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[3]
        self.real_current_state = self.repo_root / "loop_state" / "current_state.json"
        self.real_current_state_snapshot = self.real_current_state.read_text(encoding="utf-8") if self.real_current_state.exists() else ""
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.loop_home = Path(self.tempdir.name)
        os.environ["HOLOPHAGE_LOOP_HOME"] = str(self.loop_home)
        self.addCleanup(os.environ.pop, "HOLOPHAGE_LOOP_HOME", None)
        self.generated_tasks_dir = self.loop_home / "generated_tasks"
        os.environ["HOLOPHAGE_LOOP_TASKS_DIR"] = str(self.generated_tasks_dir)
        self.addCleanup(os.environ.pop, "HOLOPHAGE_LOOP_TASKS_DIR", None)

        import integrations.codex_loop.constants as loop_constants
        import integrations.codex_loop.schemas as loop_schemas
        import integrations.codex_loop.artifacts as loop_artifacts
        import integrations.codex_loop.context_builder as loop_context_builder
        import integrations.codex_loop.events as loop_events
        import integrations.codex_loop.experiment_runner as loop_experiment_runner
        import integrations.codex_loop.governor as loop_governor
        import integrations.codex_loop.implementation_runner as loop_implementation_runner
        import integrations.codex_loop.policy as loop_policy
        import integrations.codex_loop.program_planner as loop_program_planner
        import integrations.codex_loop.queue_planner as loop_queue_planner
        import integrations.codex_loop.regression_sentinel as loop_regression_sentinel
        import integrations.codex_loop.autopilot as loop_autopilot
        import integrations.codex_loop.task_templates as loop_task_templates
        import integrations.codex_loop.trial as loop_trial
        import integrations.codex_loop.workflow_registry as loop_workflow_registry

        self.constants = importlib.reload(loop_constants)
        self.schemas = importlib.reload(loop_schemas)
        self.artifacts = importlib.reload(loop_artifacts)
        self.context_builder = importlib.reload(loop_context_builder)
        self.events = importlib.reload(loop_events)
        self.experiment_runner = importlib.reload(loop_experiment_runner)
        self.governor = importlib.reload(loop_governor)
        self.implementation_runner = importlib.reload(loop_implementation_runner)
        self.policy = importlib.reload(loop_policy)
        self.program_planner = importlib.reload(loop_program_planner)
        self.queue_planner = importlib.reload(loop_queue_planner)
        self.regression_sentinel = importlib.reload(loop_regression_sentinel)
        self.autopilot = importlib.reload(loop_autopilot)
        self.task_templates = importlib.reload(loop_task_templates)
        self.trial = importlib.reload(loop_trial)
        self.workflow_registry = importlib.reload(loop_workflow_registry)
        self.schemas.ensure_runtime_state_files(self.constants.DEFAULT_INTERVENTION_POLICY)

    def tearDown(self) -> None:
        if self.real_current_state.exists():
            self.assertEqual(self.real_current_state.read_text(encoding="utf-8"), self.real_current_state_snapshot)

    def _write_json(self, path: Path, payload: dict) -> None:
        self.schemas.write_json(path, payload)

    def _read_events(self) -> list[dict]:
        lines = self.constants.EVENTS_PATH.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def _decision_payload(self, run_id: str, workflow_kind: str = "truth_calibration", action_kind: str = "skill", action_name: str = "active-truth-calibration") -> dict:
        return {
            "schema_version": self.constants.SCHEMA_VERSION,
            "run_id": run_id,
            "task_id": "2026-03-31-test-task",
            "phase": "multilabel_transition",
            "workflow_kind": workflow_kind,
            "task_type": workflow_kind if workflow_kind in self.constants.TASK_TYPE_TO_SKILL else "",
            "objective": "x",
            "preflight_required": True,
            "action": {"kind": action_kind, "name": action_name, "args": {"format": "json"}},
            "success_criteria": ["x"],
            "fail_fast_conditions": ["x"],
            "review_focus": ["x"],
            "risk_level": "low",
            "needs_human_before_execute": False,
            "allowed_write_paths": ["baseline/model.py"] if workflow_kind == "implementation_task" else [],
            "required_checks": ["python -m unittest x"] if workflow_kind in ("implementation_task", "experiment_run") else [],
            "linked_experiment_id": "",
            "autocontinue_eligible": workflow_kind in self.constants.AUTOCONTINUE_WORKFLOW_KINDS,
        }

    def _execution_payload(self, run_id: str, workflow_kind: str = "truth_calibration") -> dict:
        return {
            "schema_version": self.constants.SCHEMA_VERSION,
            "run_id": run_id,
            "task_id": "2026-03-31-test-task",
            "linked_experiment_id": "",
            "preflight": {
                "skill": "active-truth-calibration",
                "exit_code": 0,
                "status": "pass",
                "stdout_excerpt": "{}",
                "stderr_excerpt": "",
                "stdout_json": {"status": "ok"},
            },
            "action": {
                "kind": "implementation" if workflow_kind == "implementation_task" else "skill",
                "name": "implementation-task" if workflow_kind == "implementation_task" else "active-truth-calibration",
                "command": "pwsh ...",
                "args": {"format": "json"},
                "exit_code": 0,
                "stdout_excerpt": "{}",
                "stderr_excerpt": "",
                "stdout_json": {"status": "ok"},
            },
            "artifacts": {},
            "machine_assessment": {
                "fail_fast": False,
                "completed_execution": True,
                "detected_conditions": [],
            },
            "write_set": ["baseline/model.py"] if workflow_kind == "implementation_task" else [],
            "checks_run": ["python -m unittest x"] if workflow_kind == "implementation_task" else [],
            "checks_passed": ["python -m unittest x"] if workflow_kind == "implementation_task" else [],
            "progress_delta": {
                "summary": "done",
                "fingerprint": f"{workflow_kind}|done",
            },
        }

    def _verdict_payload(self, run_id: str, verdict: str = "approve", next_mode: str = "continue") -> dict:
        return {
            "schema_version": self.constants.SCHEMA_VERSION,
            "run_id": run_id,
            "task_id": "2026-03-31-test-task",
            "linked_experiment_id": "",
            "verdict": verdict,
            "objective_met": verdict == "approve",
            "needs_human": False,
            "drift_detected": False,
            "issues": [],
            "recommended_next_mode": next_mode,
            "next_objective": "next",
            "evidence": {
                "write_set": [],
                "checks_run": [],
                "checks_passed": [],
                "detected_conditions": [],
            },
            "decision_payload": {},
        }

    def test_current_state_uses_temp_loop_home(self) -> None:
        self.assertTrue(str(self.constants.CURRENT_STATE_PATH).startswith(str(self.loop_home)))
        self.assertTrue(self.constants.CURRENT_STATE_PATH.exists())
        self.assertNotEqual(self.constants.CURRENT_STATE_PATH.resolve(), self.real_current_state.resolve())
        self.assertTrue(self.constants.EVENTS_PATH.exists())

    def test_runtime_state_defaults_include_v21_fields(self) -> None:
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        self.assertIn("runner_id", state)
        self.assertIn("heartbeat_at", state)
        self.assertIn("blocked_reason_code", state)
        policy = self.policy.load_policy()
        self.assertIn("allowed_unattended_workflow_kinds", policy)
        self.assertEqual(policy["default_unattended_risk_level"], "low")
        self.assertIn("allow_unattended_implementation", policy)
        self.assertIn("allow_unattended_experiment", policy)
        self.assertIn("idle_sleep_seconds", policy)
        runtime_session = self.schemas.load_json(self.constants.RUNTIME_SESSION_PATH)
        self.assertIn("last_wake_reason", runtime_session)
        self.assertTrue(self.constants.RUNTIME_SESSION_HISTORY_PATH.exists())
        self.assertTrue(self.constants.QUEUE_PLANNER_STATE_PATH.exists())

    def test_materialize_policy_defaults_updates_old_shape_file(self) -> None:
        old_shape = {
            "hard_stop": ["x"],
            "soft_stop": ["y"],
        }
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, old_shape)
        path = self.trial.materialize_policy_defaults()
        payload = self.schemas.load_json(path)
        self.assertIn("allowed_unattended_workflow_kinds", payload)
        self.assertEqual(payload["default_unattended_risk_level"], "low")

    def test_create_task_then_prepare_plan_packet_promotes_status_to_ready(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multimodal-gate-collapse-analysis.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="implementation_task", allowed_write_paths=["baseline/model.py"])
        task_record = self.schemas.load_json(task_record_path)
        self.assertEqual(task_record["status"], "proposed")

        packet_path = self.governor.prepare_plan_packet(task_id=task_record["task_id"])
        self.assertTrue(packet_path.exists())
        task_record = self.schemas.load_json(task_record_path)
        self.assertEqual(task_record["status"], "ready")

    def test_prepare_planner_workspace_does_not_mutate_real_state(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multilabel-head-wiring.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="implementation_task", allowed_write_paths=["baseline/model.py"])
        task_id = self.schemas.load_json(task_record_path)["task_id"]
        packet_path = self.governor.prepare_plan_packet(run_id="unit-plan", task_id=task_id)
        workspace_path = self.governor.prepare_planner_workspace("unit-plan")
        self.assertTrue(packet_path.exists())
        self.assertTrue(workspace_path.exists())
        workspace = self.schemas.load_json(workspace_path)
        self.assertEqual(workspace["workspace_kind"], "planner")

    def test_prepare_planner_decision_template_contains_v2_fields(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multilabel-head-wiring.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="implementation_task", allowed_write_paths=["baseline/model.py"])
        task_id = self.schemas.load_json(task_record_path)["task_id"]
        self.governor.prepare_plan_packet(run_id="unit-template", task_id=task_id)
        template_path = self.governor.prepare_planner_decision_template("unit-template")
        template = self.schemas.load_json(template_path)
        self.assertEqual(template["task_id"], task_id)
        self.assertEqual(template["workflow_kind"], "implementation_task")
        self.assertIn("allowed_write_paths", template)
        self.assertIn("required_checks", template)

    def test_prepare_implementation_workspace_writes_execution_template(self) -> None:
        run_id = "unit-impl"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        decision = self._decision_payload(run_id, workflow_kind="implementation_task", action_kind="implementation", action_name="implementation-task")
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update({"status": "planner_workspace_ready", "current_run_id": run_id, "active_task_id": decision["task_id"]})
        self._write_json(self.constants.CURRENT_STATE_PATH, state)
        workspace_path = self.governor.prepare_implementation_workspace(str(run_dir / self.constants.PLANNER_DECISION_NAME))
        template_path = run_dir / self.constants.EXECUTION_RESULT_TEMPLATE_NAME
        self.assertTrue(workspace_path.exists())
        self.assertTrue(template_path.exists())
        template = self.schemas.load_json(template_path)
        self.assertEqual(template["action"]["kind"], "implementation")

    def test_prepare_experiment_workspace_writes_execution_template(self) -> None:
        run_id = "unit-exp"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        decision = self._decision_payload(run_id, workflow_kind="experiment_run", action_kind="experiment", action_name="experiment-run")
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update({"status": "planner_workspace_ready", "current_run_id": run_id, "active_task_id": decision["task_id"]})
        self._write_json(self.constants.CURRENT_STATE_PATH, state)
        workspace_path = self.governor.prepare_experiment_workspace(str(run_dir / self.constants.PLANNER_DECISION_NAME))
        self.assertTrue(workspace_path.exists())
        self.assertTrue((run_dir / self.constants.EXECUTION_RESULT_TEMPLATE_NAME).exists())

    def test_run_execution_accepts_experiment_task_and_writes_execution_result(self) -> None:
        run_id = "unit-run-experiment"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        decision = self._decision_payload(run_id, workflow_kind="experiment_run", action_kind="experiment", action_name="experiment-run")
        decision["required_checks"] = ["python -m unittest integrations.codex_loop.tests.test_codex_loop"]
        decision["action"]["args"] = {"command": "python -c \"print('ok')\"", "run_dir": "baseline/runs/tmp_auto_closeout_metrics_smoke", "config_path": ""}
        decision["experiment_required_artifacts"] = ["summary.json"]
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update({"status": "experiment_workspace_ready", "current_run_id": run_id, "active_task_id": decision["task_id"]})
        self._write_json(self.constants.CURRENT_STATE_PATH, state)

        payload = self._execution_payload(run_id)
        payload["action"]["kind"] = "experiment"
        payload["action"]["name"] = "experiment-run"
        payload["artifacts"] = {"run_dir": "baseline/runs/tmp_auto_closeout_metrics_smoke", "closeout_status": "ready"}
        payload["transcript_path"] = str(run_dir / self.constants.EXPERIMENT_TRANSCRIPT_NAME)
        payload["step_count"] = 3
        payload["failed_step"] = ""
        with mock.patch.object(self.governor, "execute_experiment", return_value=payload):
            result_path = self.governor.run_execution(str(run_dir / self.constants.PLANNER_DECISION_NAME))

        self.assertTrue(result_path.exists())
        result = self.schemas.load_json(result_path)
        self.assertEqual(result["action"]["kind"], "experiment")

    def test_experiment_runner_collects_transcript_and_artifacts(self) -> None:
        policy = self.policy.load_policy()
        policy["allow_unattended_experiment"] = True
        decision = self._decision_payload("unit-experiment-runner", workflow_kind="experiment_run", action_kind="experiment", action_name="experiment-run")
        decision["action"]["args"] = {
            "command": "python -c \"print('ok')\"",
            "run_dir": "baseline/runs/tmp_auto_closeout_metrics_smoke",
            "config_path": "",
        }
        decision["experiment_required_artifacts"] = ["summary.json"]
        decision["required_checks"] = ["python -m unittest integrations.codex_loop.tests.test_codex_loop"]
        run_dir = self.constants.LOOP_RUNS_DIR / "unit-experiment-runner"
        run_dir.mkdir(parents=True, exist_ok=True)

        fake_preflight = self.governor.CommandResult("active-truth-calibration", "pwsh ...", {"format": "json"}, 0, "{}", "")
        fake_action = self.governor.CommandResult("experiment-command", "python -c \"print('ok')\"", {}, 0, "ok", "")
        fake_check = self.governor.CommandResult("required-check", "python -m unittest integrations.codex_loop.tests.test_codex_loop", {}, 0, "", "")
        fake_registry = {
            "experiment_id": "exp-1",
            "task_id": decision["task_id"],
            "run_dir": str((self.repo_root / "baseline" / "runs" / "tmp_auto_closeout_metrics_smoke").resolve()),
            "summary_path": "summary.json",
            "config_path": "",
            "variant": "v",
            "seed": 1,
            "status": "candidate",
            "closeout_status": "ready",
            "review_verdict": "",
            "metrics_val_path": "",
            "metrics_test_path": "",
            "last_verified_at": "",
            "best_epoch": None,
            "best_val_l3_macro_f1": None,
            "best_val_multilabel_micro_f1": None,
            "mean_gates": {},
            "gate_health": {},
        }
        with mock.patch.object(self.experiment_runner, "run_skill", return_value=fake_preflight), \
            mock.patch.object(self.experiment_runner, "_run_command", return_value=fake_action), \
            mock.patch.object(self.experiment_runner, "_run_check_command", return_value=fake_check), \
            mock.patch.object(self.experiment_runner, "build_experiment_registry_draft", return_value=fake_registry):
            payload = self.experiment_runner.execute_experiment(decision, policy=policy, run_dir=run_dir)

        self.assertTrue(payload["transcript_path"])
        self.assertGreater(payload["step_count"], 0)
        self.assertEqual(payload["artifacts"]["closeout_status"], "ready")
        transcript_text = Path(payload["transcript_path"]).read_text(encoding="utf-8")
        self.assertIn("experiment_command", transcript_text)
        self.assertIn("artifact_scan", transcript_text)

    def test_experiment_runner_missing_summary_pauses_via_detected_conditions(self) -> None:
        policy = self.policy.load_policy()
        decision = self._decision_payload("unit-experiment-missing-summary", workflow_kind="experiment_run", action_kind="experiment", action_name="experiment-run")
        decision["action"]["args"] = {
            "command": "python -c \"print('ok')\"",
            "run_dir": "tmp/nonexistent-experiment",
            "config_path": "",
        }
        decision["experiment_required_artifacts"] = ["summary.json"]
        decision["required_checks"] = ["python -m unittest integrations.codex_loop.tests.test_codex_loop"]
        run_dir = self.constants.LOOP_RUNS_DIR / "unit-experiment-missing-summary"
        run_dir.mkdir(parents=True, exist_ok=True)

        fake_preflight = self.governor.CommandResult("active-truth-calibration", "pwsh ...", {"format": "json"}, 0, "{}", "")
        fake_action = self.governor.CommandResult("experiment-command", "python -c \"print('ok')\"", {}, 0, "ok", "")
        fake_check = self.governor.CommandResult("required-check", "python -m unittest integrations.codex_loop.tests.test_codex_loop", {}, 0, "", "")
        with mock.patch.object(self.experiment_runner, "run_skill", return_value=fake_preflight), \
            mock.patch.object(self.experiment_runner, "_run_command", return_value=fake_action), \
            mock.patch.object(self.experiment_runner, "_run_check_command", return_value=fake_check):
            payload = self.experiment_runner.execute_experiment(decision, policy=policy, run_dir=run_dir)

        self.assertTrue(payload["machine_assessment"]["fail_fast"])
        self.assertTrue(any(item.startswith("missing_required_artifact:summary.json") for item in payload["machine_assessment"]["detected_conditions"]))

    def test_prepare_reviewer_workspace_accepts_manual_implementation_execution(self) -> None:
        run_id = "unit-manual-impl-review"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        decision = self._decision_payload(run_id, workflow_kind="implementation_task", action_kind="implementation", action_name="implementation-task")
        execution = self._execution_payload(run_id, workflow_kind="implementation_task")
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        self._write_json(run_dir / self.constants.EXECUTION_RESULT_NAME, execution)
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update({"status": "implementation_workspace_ready", "current_run_id": run_id, "active_task_id": decision["task_id"]})
        self._write_json(self.constants.CURRENT_STATE_PATH, state)

        workspace_path = self.governor.prepare_reviewer_workspace(str(run_dir / self.constants.EXECUTION_RESULT_NAME))
        self.assertTrue(workspace_path.exists())
        updated_state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        self.assertEqual(updated_state["status"], "reviewer_workspace_ready")

    def test_gate_blocks_forbidden_write_path(self) -> None:
        decision = self._decision_payload("unit-gate", workflow_kind="implementation_task", action_kind="implementation", action_name="implementation-task")
        decision["allowed_write_paths"] = ["project_memory/04_active_assets/ACTIVE_VERSION.yaml"]
        reasons = self.governor._gate_action_assets(decision)
        self.assertTrue(any("forbidden implementation write path" in item for item in reasons))

    def test_sync_experiment_from_run_builds_registry_entry(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multimodal-gate-collapse-analysis.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="experiment_run")
        task_id = self.schemas.load_json(task_record_path)["task_id"]
        run_dir = self.repo_root / "baseline" / "runs" / "tmp_auto_closeout_metrics_smoke"
        experiment_path = self.governor.sync_experiment_from_run(task_id, str(run_dir), status="staging")
        record = self.schemas.load_json(experiment_path)
        self.assertEqual(record["task_id"], task_id)
        self.assertEqual(record["status"], "staging")
        self.assertTrue(record["summary_path"].endswith("summary.json"))
        self.assertIn("gate_health", record)
        self.assertIsInstance(record["gate_health"], dict)

    def test_run_execution_skill_flow_writes_execution_result(self) -> None:
        run_id = "unit-run-skill"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        decision = self._decision_payload(run_id, workflow_kind="truth_calibration", action_kind="skill", action_name="active-truth-calibration")
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update({"status": "executor_workspace_ready", "current_run_id": run_id, "active_task_id": decision["task_id"]})
        self._write_json(self.constants.CURRENT_STATE_PATH, state)

        fake = self.governor.CommandResult(
            skill="active-truth-calibration",
            command="pwsh ...",
            args={"format": "json"},
            exit_code=0,
            stdout='{"status":"ok","conflicts":[]}',
            stderr="",
        )
        with mock.patch.object(self.governor, "run_skill", return_value=fake):
            result_path = self.governor.run_execution(str(run_dir / self.constants.PLANNER_DECISION_NAME))

        self.assertTrue(result_path.exists())
        payload = self.schemas.load_json(result_path)
        self.assertEqual(payload["task_id"], decision["task_id"])
        self.assertEqual(payload["action"]["kind"], "skill")

    def test_autopilot_run_once_executes_low_risk_skill_task(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multimodal-gate-collapse-analysis.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="truth_calibration", risk_level="low")
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "ready"
        self.schemas.write_json(task_record_path, task_record)

        fake = self.governor.CommandResult(
            skill="active-truth-calibration",
            command="pwsh ...",
            args={"format": "json"},
            exit_code=0,
            stdout='{"status":"ok","conflicts":[]}',
            stderr="",
        )
        with mock.patch.object(self.governor, "run_skill", return_value=fake), mock.patch.object(self.autopilot, "run_skill", return_value=fake, create=True):
            result = self.autopilot.run_once("runner-unit")

        self.assertEqual(result["task_id"], task_record["task_id"])
        self.assertIn(result["status"], ("context_ready", "completed"))
        events = self.constants.EVENTS_PATH.read_text(encoding="utf-8")
        self.assertIn("run_completed", events)
        self.assertIn("planner_ms", events)

    def test_autopilot_gates_implementation_task(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multilabel-head-wiring.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="implementation_task", risk_level="low", allowed_write_paths=["baseline/model.py"])
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "ready"
        task_record["priority"] = 0
        self.schemas.write_json(task_record_path, task_record)

        result = self.autopilot.run_once("runner-gated")
        self.assertEqual(result["status"], "idle")
        updated = self.schemas.load_json(task_record_path)
        self.assertEqual(updated["status"], "paused_for_human")
        self.assertEqual(updated["blocked_reason"], "autopilot_currently_gated")

    def test_run_execution_accepts_implementation_task_and_writes_execution_result(self) -> None:
        run_id = "unit-run-implementation"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        decision = self._decision_payload(run_id, workflow_kind="implementation_task", action_kind="implementation", action_name="implementation-task")
        decision["required_checks"] = ["python -m unittest integrations.codex_loop.tests.test_codex_loop"]
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update({"status": "implementation_workspace_ready", "current_run_id": run_id, "active_task_id": decision["task_id"]})
        self._write_json(self.constants.CURRENT_STATE_PATH, state)

        payload = self._execution_payload(run_id, workflow_kind="implementation_task")
        payload["checks_run"] = list(decision["required_checks"])
        payload["checks_passed"] = list(decision["required_checks"])
        with mock.patch.object(self.governor, "execute_implementation", return_value=payload):
            result_path = self.governor.run_execution(str(run_dir / self.constants.PLANNER_DECISION_NAME))

        self.assertTrue(result_path.exists())
        result = self.schemas.load_json(result_path)
        self.assertEqual(result["action"]["kind"], "implementation")
        self.assertEqual(result["checks_run"], decision["required_checks"])

    def test_prepare_review_verdict_template_marks_failed_implementation_execution_as_revise(self) -> None:
        run_id = "unit-impl-review-template"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        decision = self._decision_payload(run_id, workflow_kind="implementation_task", action_kind="implementation", action_name="implementation-task")
        decision["required_checks"] = ["python -m unittest a", "python -m unittest b"]
        execution = self._execution_payload(run_id, workflow_kind="implementation_task")
        execution["checks_run"] = list(decision["required_checks"])
        execution["checks_passed"] = ["python -m unittest a"]
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        self._write_json(run_dir / self.constants.EXECUTION_RESULT_NAME, execution)

        template_path = self.governor.prepare_review_verdict_template(str(run_dir / self.constants.EXECUTION_RESULT_NAME))
        template = self.schemas.load_json(template_path)
        self.assertEqual(template["verdict"], "revise")
        self.assertFalse(template["objective_met"])
        self.assertTrue(any("failed_required_check:" in item for item in template["issues"]))
        self.assertIn("evidence", template)
        self.assertIn("detected_conditions", template["evidence"])

    def test_autopilot_run_once_executes_low_risk_implementation_task_when_policy_allows(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multilabel-head-wiring.md"
        task_record_path = self.governor.create_task(
            str(task_file),
            workflow_kind="implementation_task",
            risk_level="low",
            allowed_write_paths=["baseline/model.py"],
            required_checks=["python -m unittest integrations.codex_loop.tests.test_codex_loop"],
        )
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "ready"
        self.schemas.write_json(task_record_path, task_record)

        policy = self.policy.load_policy()
        policy["allow_unattended_implementation"] = True
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)

        def _fake_execute(decision: dict, *, policy: dict, run_dir: Path) -> dict:
            payload = self._execution_payload(decision["run_id"], workflow_kind="implementation_task")
            payload["task_id"] = task_record["task_id"]
            payload["checks_run"] = ["python -m unittest integrations.codex_loop.tests.test_codex_loop"]
            payload["checks_passed"] = list(payload["checks_run"])
            return payload

        with mock.patch.object(self.governor, "execute_implementation", side_effect=_fake_execute):
            result = self.autopilot.run_once("runner-impl")

        self.assertEqual(result["task_id"], task_record["task_id"])
        self.assertIn(result["status"], ("context_ready", "completed"))
        updated = self.schemas.load_json(task_record_path)
        self.assertNotEqual(updated["status"], "paused_for_human")

    def test_autopilot_gates_experiment_task_when_policy_disabled(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multimodal-gate-collapse-analysis.md"
        task_record_path = self.governor.create_task(
            str(task_file),
            workflow_kind="experiment_run",
            risk_level="low",
            required_checks=["python -m unittest integrations.codex_loop.tests.test_codex_loop"],
            experiment_command="python -c \"print('ok')\"",
            experiment_run_dir="baseline/runs/tmp_auto_closeout_metrics_smoke",
            experiment_required_artifacts=["summary.json"],
        )
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "ready"
        self.schemas.write_json(task_record_path, task_record)

        result = self.autopilot.run_once("runner-exp-gated")
        self.assertEqual(result["status"], "idle")
        updated = self.schemas.load_json(task_record_path)
        self.assertEqual(updated["status"], "paused_for_human")
        self.assertEqual(updated["blocked_reason_code"], "autopilot_currently_gated")

    def test_autopilot_run_once_executes_low_risk_experiment_task_when_policy_allows(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multimodal-gate-collapse-analysis.md"
        task_record_path = self.governor.create_task(
            str(task_file),
            workflow_kind="experiment_run",
            risk_level="low",
            required_checks=["python -m unittest integrations.codex_loop.tests.test_codex_loop"],
            experiment_command="python -c \"print('ok')\"",
            experiment_run_dir="baseline/runs/tmp_auto_closeout_metrics_smoke",
            experiment_required_artifacts=["summary.json"],
        )
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "ready"
        self.schemas.write_json(task_record_path, task_record)

        policy = self.policy.load_policy()
        policy["allow_unattended_experiment"] = True
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)

        def _fake_experiment_payload(decision: dict, *, policy: dict, run_dir: Path) -> dict:
            payload = self._execution_payload(decision["run_id"])
            payload["task_id"] = task_record["task_id"]
            payload["action"]["kind"] = "experiment"
            payload["action"]["name"] = "experiment-run"
            payload["action"]["args"] = dict(decision["action"]["args"])
            payload["linked_experiment_id"] = ""
            payload["artifacts"] = {
                "run_dir": str((self.repo_root / "baseline" / "runs" / "tmp_auto_closeout_metrics_smoke").resolve()),
                "required_artifacts": ["summary.json"],
                "existing_artifacts": ["summary.json"],
                "missing_artifacts": [],
                "check_results": [],
                "registry_preview": {},
                "closeout_status": "ready",
            }
            payload["transcript_path"] = str(run_dir / self.constants.EXPERIMENT_TRANSCRIPT_NAME)
            payload["step_count"] = 4
            payload["failed_step"] = ""
            Path(payload["transcript_path"]).write_text("{}", encoding="utf-8")
            return payload

        with mock.patch.object(self.governor, "execute_experiment", side_effect=_fake_experiment_payload), \
            mock.patch.object(self.autopilot, "sync_experiment_from_run", return_value=self.loop_home / "loop_state" / "experiments" / "exp-1.json"):
            self._write_json(
                self.loop_home / "loop_state" / "experiments" / "exp-1.json",
                {
                    "experiment_id": "exp-1",
                    "task_id": task_record["task_id"],
                    "run_dir": str((self.repo_root / "baseline" / "runs" / "tmp_auto_closeout_metrics_smoke").resolve()),
                    "summary_path": "summary.json",
                    "config_path": "",
                    "variant": "v",
                    "seed": 1,
                    "status": "candidate",
                    "closeout_status": "pending",
                    "review_verdict": "",
                    "metrics_val_path": "",
                    "metrics_test_path": "",
                    "last_verified_at": "",
                    "best_epoch": None,
                    "best_val_l3_macro_f1": None,
                    "best_val_multilabel_micro_f1": None,
                    "mean_gates": {},
                    "gate_health": {},
                },
            )
            result = self.autopilot.run_once("runner-exp")

        self.assertEqual(result["task_id"], task_record["task_id"])
        self.assertIn(result["status"], ("context_ready", "completed"))

    def test_implementation_execute_detects_out_of_scope_write(self) -> None:
        policy = self.policy.load_policy()
        policy["implementation_max_files_touched"] = 4
        policy["implementation_max_diff_lines"] = 200
        decision = self._decision_payload("unit-impl-runner", workflow_kind="implementation_task", action_kind="implementation", action_name="implementation-task")
        decision["required_checks"] = ["python -m unittest integrations.codex_loop.tests.test_codex_loop"]
        run_dir = self.constants.LOOP_RUNS_DIR / "unit-impl-runner"
        run_dir.mkdir(parents=True, exist_ok=True)

        fake_preflight = self.governor.CommandResult("active-truth-calibration", "pwsh ...", {"format": "json"}, 0, "{}", "")
        fake_action = self.governor.CommandResult("codex-implementation", "codex exec ...", {}, 0, "done", "")
        fake_check = self.governor.CommandResult("required-check", "python -m unittest integrations.codex_loop.tests.test_codex_loop", {}, 0, "", "")
        with mock.patch.object(self.implementation_runner, "run_skill", return_value=fake_preflight), \
            mock.patch.object(self.implementation_runner, "run_codex_implementation", return_value=fake_action), \
            mock.patch.object(self.implementation_runner, "snapshot_allowed_paths", side_effect=[{"baseline/model.py": "before"}, {"baseline/model.py": "after"}]), \
            mock.patch.object(self.implementation_runner, "snapshot_repo_changes", side_effect=[set(), {"project_memory/04_active_assets/ACTIVE_VERSION.yaml"}]), \
            mock.patch.object(self.implementation_runner, "run_check_command", return_value=fake_check), \
            mock.patch.object(self.implementation_runner, "diff_line_count", return_value=4):
            payload = self.implementation_runner.execute_implementation(decision, policy=policy, run_dir=run_dir)

        self.assertTrue(payload["machine_assessment"]["fail_fast"])
        self.assertIn("implementation_write_scope_violation", payload["machine_assessment"]["detected_conditions"])
        self.assertTrue(payload["transcript_path"])
        self.assertGreater(payload["step_count"], 0)
        self.assertTrue(Path(payload["transcript_path"]).exists())
        transcript_lines = Path(payload["transcript_path"]).read_text(encoding="utf-8").splitlines()
        self.assertTrue(any("write_scope_validation" in line for line in transcript_lines))

    def test_implementation_policy_gate_blocks_forbidden_check_prefix(self) -> None:
        policy = self.policy.load_policy()
        allowed, reason_code = self.implementation_runner.validate_command_against_policy("bash test.sh", policy, is_check=True)
        self.assertFalse(allowed)
        self.assertEqual(reason_code, "implementation_forbidden_check_prefix")

    def test_implementation_policy_gate_blocks_forbidden_command_substring(self) -> None:
        policy = self.policy.load_policy()
        allowed, reason_code = self.implementation_runner.validate_command_against_policy("python -c \"git reset --hard\"", policy, is_check=False)
        self.assertFalse(allowed)
        self.assertEqual(reason_code, "implementation_forbidden_command_substring")

    def test_advance_review_pauses_implementation_when_checks_not_fully_passed(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multilabel-head-wiring.md"
        task_record_path = self.governor.create_task(
            str(task_file),
            workflow_kind="implementation_task",
            allowed_write_paths=["baseline/model.py"],
            required_checks=["python -m unittest a", "python -m unittest b"],
        )
        task_id = self.schemas.load_json(task_record_path)["task_id"]
        run_id = "unit-advance-impl-revise"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        decision = self._decision_payload(run_id, workflow_kind="implementation_task", action_kind="implementation", action_name="implementation-task")
        decision["task_id"] = task_id
        decision["required_checks"] = ["python -m unittest a", "python -m unittest b"]
        execution = self._execution_payload(run_id, workflow_kind="implementation_task")
        execution["task_id"] = task_id
        execution["checks_run"] = list(decision["required_checks"])
        execution["checks_passed"] = ["python -m unittest a"]
        verdict = self._verdict_payload(run_id, verdict="approve", next_mode="continue")
        verdict["task_id"] = task_id
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        self._write_json(run_dir / self.constants.EXECUTION_RESULT_NAME, execution)
        self._write_json(run_dir / self.constants.REVIEW_VERDICT_NAME, verdict)
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update({"status": "reviewer_workspace_ready", "current_run_id": run_id, "active_task_id": task_id})
        self._write_json(self.constants.CURRENT_STATE_PATH, state)

        self.governor.advance_review(str(run_dir / self.constants.REVIEW_VERDICT_NAME))
        updated_task = self.schemas.load_json(task_record_path)
        self.assertEqual(updated_task["status"], "paused_for_human")
        self.assertEqual(updated_task["blocked_reason_code"], "implementation_required_checks_failed")
        self.assertTrue(updated_task["suggested_next_actions"])

    def test_canonical_reason_code_maps_failed_required_check_prefix(self) -> None:
        self.assertEqual(
            self.governor._canonical_reason_code("failed_required_check:python -m unittest a"),
            "implementation_required_checks_failed",
        )

    def test_pause_actions_include_failed_check_name_from_evidence(self) -> None:
        actions = self.governor._pause_actions(
            "implementation_required_checks_failed",
            evidence={
                "checks_run": ["python -m unittest a", "python -m unittest b"],
                "checks_passed": ["python -m unittest a"],
            },
        )
        self.assertIn("python -m unittest b", actions[0])

    def test_pause_actions_include_write_scope_path_from_evidence(self) -> None:
        actions = self.governor._pause_actions(
            "implementation_write_scope_violation",
            evidence={
                "write_set": ["baseline/out_of_scope.py"],
            },
        )
        self.assertIn("baseline/out_of_scope.py", actions[0])

    def test_two_rounds_no_progress_pauses_task_with_structured_actions(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multilabel-head-wiring.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="implementation_task", allowed_write_paths=["baseline/model.py"])
        task_id = self.schemas.load_json(task_record_path)["task_id"]
        run_id = "unit-two-rounds-no-progress"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        decision = self._decision_payload(run_id, workflow_kind="implementation_task", action_kind="implementation", action_name="implementation-task")
        decision["task_id"] = task_id
        execution = self._execution_payload(run_id, workflow_kind="implementation_task")
        execution["task_id"] = task_id
        execution["write_set"] = ["baseline/model.py"]
        execution["checks_run"] = ["python -m unittest a"]
        execution["checks_passed"] = ["python -m unittest a"]
        execution["progress_delta"]["fingerprint"] = "same-progress"
        verdict = self._verdict_payload(run_id, verdict="approve", next_mode="continue")
        verdict["task_id"] = task_id
        verdict["objective_met"] = False
        verdict["evidence"] = {
            "write_set": ["baseline/model.py"],
            "checks_run": ["python -m unittest a"],
            "checks_passed": ["python -m unittest a"],
            "detected_conditions": [],
        }
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        self._write_json(run_dir / self.constants.EXECUTION_RESULT_NAME, execution)
        self._write_json(run_dir / self.constants.REVIEW_VERDICT_NAME, verdict)
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update(
            {
                "status": "reviewer_workspace_ready",
                "current_run_id": run_id,
                "active_task_id": task_id,
                "last_progress_fingerprint": "same-progress",
                "consecutive_no_progress": 1,
            }
        )
        self._write_json(self.constants.CURRENT_STATE_PATH, state)

        self.governor.advance_review(str(run_dir / self.constants.REVIEW_VERDICT_NAME))
        updated_task = self.schemas.load_json(task_record_path)
        updated_state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        self.assertEqual(updated_task["status"], "paused_for_human")
        self.assertEqual(updated_task["blocked_reason_code"], "two_rounds_no_progress")
        self.assertTrue(updated_task["suggested_next_actions"])
        self.assertEqual(updated_state["status"], "paused_for_human")
        self.assertEqual(updated_state["blocked_reason_code"], "two_rounds_no_progress")

    def test_resume_stale_run_takes_over_lease(self) -> None:
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update(
            {
                "runner_id": "runner-old",
                "heartbeat_at": "2000-01-01T00:00:00+00:00",
                "lease_acquired_at": "2000-01-01T00:00:00+00:00",
                "active_lease_status": "active",
            }
        )
        self.schemas.write_json(self.constants.CURRENT_STATE_PATH, state)
        resumed = self.autopilot.resume_stale("runner-new")
        self.assertEqual(resumed["runner_id"], "runner-new")
        self.assertEqual(resumed["active_lease_status"], "resumed")

    def test_resume_stale_run_recovers_from_execution_finished_checkpoint(self) -> None:
        run_id = "unit-stale-execution-finished"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        decision = self._decision_payload(run_id, workflow_kind="truth_calibration", action_kind="skill", action_name="active-truth-calibration")
        execution = self._execution_payload(run_id)
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        self._write_json(run_dir / self.constants.EXECUTION_RESULT_NAME, execution)
        self._write_json(
            run_dir / self.constants.STAGE_CHECKPOINT_NAME,
            {
                "run_id": run_id,
                "task_id": decision["task_id"],
                "runner_id": "runner-old",
                "stage": "execution_finished",
                "state_status": "executed",
                "updated_at": "2000-01-01T00:00:00+00:00",
                "checkpoint_version": 1,
                "resume_hint": "reviewer",
                "artifacts_ready": {
                    "planner_input_packet": False,
                    "planner_decision": True,
                    "execution_result": True,
                    "review_verdict": False,
                },
            },
        )
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update(
            {
                "runner_id": "runner-old",
                "heartbeat_at": "2000-01-01T00:00:00+00:00",
                "lease_acquired_at": "2000-01-01T00:00:00+00:00",
                "active_lease_status": "active",
                "current_run_id": run_id,
                "active_task_id": decision["task_id"],
                "status": "executed",
            }
        )
        self._write_json(self.constants.CURRENT_STATE_PATH, state)

        verdict_template = run_dir / self.constants.REVIEW_VERDICT_TEMPLATE_NAME
        verdict = run_dir / self.constants.REVIEW_VERDICT_NAME
        summary = run_dir / self.constants.ROUND_SUMMARY_NAME
        verdict_template.write_text("{}", encoding="utf-8")
        verdict.write_text("{}", encoding="utf-8")
        summary.write_text("summary", encoding="utf-8")
        with mock.patch.object(self.autopilot, "prepare_reviewer_workspace", return_value=run_dir / self.constants.REVIEWER_WORKSPACE_NAME), \
            mock.patch.object(self.autopilot, "prepare_review_verdict_template", return_value=verdict_template), \
            mock.patch.object(self.autopilot, "_write_review_verdict_from_template", return_value=verdict), \
            mock.patch.object(self.autopilot, "advance_review", return_value=summary):
            resumed = self.autopilot.resume_stale("runner-new")

        self.assertEqual(resumed["resume_action"], "resume_from_reviewer_stage")
        self.assertEqual(resumed["recovered_stage"], "execution_finished")
        stale_resumed = [item for item in self._read_events() if item["event_type"] == "stale_resumed"][-1]
        self.assertEqual(stale_resumed["details"]["recovered_stage"], "execution_finished")
        self.assertEqual(stale_resumed["details"]["resume_action"], "resume_from_reviewer_stage")
        self.assertEqual(
            stale_resumed["details"]["recovery_summary"],
            "execution_finished -> resume_from_reviewer_stage",
        )

    def test_resume_stale_run_recovers_from_planner_decision_checkpoint(self) -> None:
        run_id = "unit-stale-planner"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        decision = self._decision_payload(run_id, workflow_kind="implementation_task", action_kind="implementation", action_name="implementation-task")
        decision["required_checks"] = ["python -m unittest integrations.codex_loop.tests.test_codex_loop"]
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        self._write_json(
            run_dir / self.constants.STAGE_CHECKPOINT_NAME,
            {
                "run_id": run_id,
                "task_id": decision["task_id"],
                "runner_id": "runner-old",
                "stage": "planner_decision_written",
                "state_status": "planner_workspace_ready",
                "updated_at": "2000-01-01T00:00:00+00:00",
                "checkpoint_version": 1,
                "resume_hint": "execution",
                "artifacts_ready": {
                    "planner_input_packet": False,
                    "planner_decision": True,
                    "execution_result": False,
                    "review_verdict": False,
                },
            },
        )
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update(
            {
                "runner_id": "runner-old",
                "heartbeat_at": "2000-01-01T00:00:00+00:00",
                "lease_acquired_at": "2000-01-01T00:00:00+00:00",
                "active_lease_status": "active",
                "current_run_id": run_id,
                "active_task_id": decision["task_id"],
                "status": "planner_workspace_ready",
            }
        )
        self._write_json(self.constants.CURRENT_STATE_PATH, state)

        execution = run_dir / self.constants.EXECUTION_RESULT_NAME
        verdict_template = run_dir / self.constants.REVIEW_VERDICT_TEMPLATE_NAME
        verdict = run_dir / self.constants.REVIEW_VERDICT_NAME
        summary = run_dir / self.constants.ROUND_SUMMARY_NAME
        execution.write_text("{}", encoding="utf-8")
        verdict_template.write_text("{}", encoding="utf-8")
        verdict.write_text("{}", encoding="utf-8")
        summary.write_text("summary", encoding="utf-8")
        with mock.patch.object(self.autopilot, "prepare_implementation_workspace", return_value=run_dir / self.constants.IMPLEMENTATION_WORKSPACE_NAME), \
            mock.patch.object(self.autopilot, "run_execution", return_value=execution), \
            mock.patch.object(self.autopilot, "prepare_reviewer_workspace", return_value=run_dir / self.constants.REVIEWER_WORKSPACE_NAME), \
            mock.patch.object(self.autopilot, "prepare_review_verdict_template", return_value=verdict_template), \
            mock.patch.object(self.autopilot, "_write_review_verdict_from_template", return_value=verdict), \
            mock.patch.object(self.autopilot, "advance_review", return_value=summary):
            resumed = self.autopilot.resume_stale("runner-new")

        self.assertEqual(resumed["resume_action"], "rerun_execution_from_boundary")
        self.assertEqual(resumed["recovered_stage"], "planner_decision_written")
        stale_resumed = [item for item in self._read_events() if item["event_type"] == "stale_resumed"][-1]
        self.assertEqual(stale_resumed["details"]["recovered_stage"], "planner_decision_written")
        self.assertEqual(stale_resumed["details"]["resume_action"], "rerun_execution_from_boundary")
        self.assertEqual(
            stale_resumed["details"]["recovery_summary"],
            "planner_decision_written -> rerun_execution_from_boundary",
        )

    def test_run_paused_event_includes_recommended_action_summary(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multilabel-head-wiring.md"
        task_record_path = self.governor.create_task(
            str(task_file),
            workflow_kind="truth_calibration",
            risk_level="low",
        )
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "ready"
        self.schemas.write_json(task_record_path, task_record)

        def _raise_governor_error(*args, **kwargs):
            state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
            state["status"] = "paused_for_human"
            state["blocked_reason_code"] = "planner_gate"
            state["blocked_reason_detail"] = "planner gate tripped"
            state["suggested_next_actions"] = ["先修 planner decision。", "再重新运行本轮。"]
            self.schemas.write_json(self.constants.CURRENT_STATE_PATH, state)
            raise self.governor.GovernorError("planner gate tripped")

        with mock.patch.object(self.autopilot, "prepare_planner_workspace", side_effect=_raise_governor_error):
            with self.assertRaises(self.governor.GovernorError):
                self.autopilot.run_once("runner-paused-event")

        run_paused = [item for item in self._read_events() if item["event_type"] == "run_paused"][-1]
        self.assertEqual(run_paused["reason_code"], "planner_gate")
        self.assertEqual(run_paused["details"]["recommended_action_summary"], "先修 planner decision。")
        self.assertEqual(run_paused["details"]["blocked_reason_detail"], "planner gate tripped")
        self.assertTrue(run_paused["suggested_next_actions"])

    def test_show_loop_status_exposes_runtime_session_fields(self) -> None:
        runtime_session = {
            "runner_id": "runner-status",
            "started_at": "2026-03-31T10:00:00+08:00",
            "last_heartbeat_at": "2026-03-31T10:05:00+08:00",
            "rounds_completed": 3,
            "idle_cycles": 2,
            "last_wake_reason": "eligible_task_found",
            "session_end_reason": "max_session_rounds_reached",
            "last_run_id": "run-1",
            "last_task_id": "task-1",
        }
        self.schemas.write_json(self.constants.RUNTIME_SESSION_PATH, runtime_session)
        status = self.autopilot.show_loop_status()
        self.assertEqual(status["last_wake_reason"], "eligible_task_found")
        self.assertEqual(status["session_end_reason"], "max_session_rounds_reached")
        self.assertEqual(status["idle_cycles"], 2)
        self.assertIn("queue_planner_enabled", status)
        self.assertIn("last_planner_run_at", status)
        self.assertIn("last_generated_task_ids", status)
        self.assertIn("active_workflow_id", status)
        self.assertIn("current_workflow_stage", status)
        self.assertIn("workflow_status", status)
        self.assertIn("program_goal", status)

    def test_create_workflow_instance_persists_state(self) -> None:
        workflow = self.workflow_registry.create_workflow_instance(
            "gate_load_balance_promotion",
            workflow_id="wf-main",
            lane="gate_load_balance",
        )
        self.assertEqual(workflow["workflow_id"], "wf-main")
        self.assertTrue((self.constants.WORKFLOW_STATE_DIR / "wf-main.json").exists())
        program = self.workflow_registry.load_program_state()
        self.assertEqual(program["active_workflow_id"], "wf-main")

    def test_plan_queue_noop_when_disabled(self) -> None:
        result = self.queue_planner.plan_queue()
        self.assertFalse(result["enabled"])
        self.assertEqual(result["generated_task_ids"], [])

    def test_workflow_advances_to_promotion_readiness_after_second_seed_closeout(self) -> None:
        self.workflow_registry.create_workflow_instance("gate_load_balance_promotion", workflow_id="wf-promo")
        for task_name in (
            "2026-04-01-gate-load-balance-real-case-staging.md",
            "2026-04-01-gate-load-balance-real-case-closeout-decision.md",
            "2026-04-01-gate-load-balance-higher-budget-staging.md",
            "2026-04-01-gate-load-balance-higher-budget-closeout-decision.md",
            "2026-04-01-gate-load-balance-second-seed-higher-budget.md",
            "2026-04-01-gate-load-balance-second-seed-closeout-decision.md",
        ):
            task_record_path = self.governor.create_task(
                str(self.repo_root / "tasks" / task_name),
                workflow_kind="results_closeout" if "closeout" in task_name else "experiment_run",
                objective="stage",
                risk_level="low",
            )
            task_record = self.schemas.load_json(task_record_path)
            task_record["status"] = "completed" if "closeout" in task_name else "evaluating"
            if task_name.endswith("second-seed-closeout-decision.md"):
                task_record["workflow_signal"] = {"enter_extended_staging": False, "enter_promotion_candidate": False, "runtime_blocker": False}
            self.schemas.write_json(task_record_path, task_record)
        policy = self.policy.load_policy()
        policy["enable_queue_planner"] = True
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)
        result = self.queue_planner.plan_queue()
        self.assertIn("2026-04-01-gate-load-balance-promotion-readiness-review", result["generated_task_ids"])

    def test_promotion_readiness_signal_generates_extended_real_case(self) -> None:
        workflow = self.workflow_registry.create_workflow_instance("gate_load_balance_promotion", workflow_id="wf-readiness")
        workflow["completed_stages"] = [
            "real_case_staging",
            "real_case_closeout",
            "higher_budget_staging",
            "higher_budget_closeout",
            "second_seed_higher_budget",
            "second_seed_closeout",
        ]
        workflow["current_stage"] = "promotion_readiness_review"
        self.workflow_registry.save_workflow_instance(workflow)
        task_record_path = self.governor.create_task(
            str(self.repo_root / "tasks" / "2026-04-01-gate-load-balance-promotion-readiness-review.md"),
            workflow_kind="results_closeout",
            objective="readiness",
            risk_level="low",
        )
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "completed"
        task_record["workflow_signal"] = {"enter_extended_staging": True, "runtime_blocker": False}
        self.schemas.write_json(task_record_path, task_record)
        policy = self.policy.load_policy()
        policy["enable_queue_planner"] = True
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)
        result = self.queue_planner.plan_queue()
        self.assertIn("2026-04-01-gate-load-balance-extended-real-case-staging", result["generated_task_ids"])

    def test_extended_real_case_closeout_signal_generates_promotion_candidate(self) -> None:
        workflow = self.workflow_registry.create_workflow_instance("gate_load_balance_promotion", workflow_id="wf-extended")
        workflow["completed_stages"] = [
            "real_case_staging",
            "real_case_closeout",
            "higher_budget_staging",
            "higher_budget_closeout",
            "second_seed_higher_budget",
            "second_seed_closeout",
            "promotion_readiness_review",
            "extended_real_case_staging",
        ]
        workflow["current_stage"] = "extended_real_case_closeout"
        self.workflow_registry.save_workflow_instance(workflow)
        task_record_path = self.governor.create_task(
            str(self.repo_root / "tasks" / "2026-04-01-gate-load-balance-extended-real-case-closeout-decision.md"),
            workflow_kind="results_closeout",
            objective="closeout",
            risk_level="low",
        )
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "completed"
        task_record["workflow_signal"] = {"enter_promotion_candidate": True, "runtime_blocker": False}
        self.schemas.write_json(task_record_path, task_record)
        policy = self.policy.load_policy()
        policy["enable_queue_planner"] = True
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)
        result = self.queue_planner.plan_queue()
        self.assertIn("2026-04-01-gate-load-balance-promotion-candidate-decision", result["generated_task_ids"])

    def test_workflow_blocks_without_required_signal(self) -> None:
        workflow = self.workflow_registry.create_workflow_instance("gate_load_balance_promotion", workflow_id="wf-block")
        workflow["completed_stages"] = [
            "real_case_staging",
            "real_case_closeout",
            "higher_budget_staging",
            "higher_budget_closeout",
            "second_seed_higher_budget",
            "second_seed_closeout",
        ]
        workflow["current_stage"] = "promotion_readiness_review"
        self.workflow_registry.save_workflow_instance(workflow)
        task_record_path = self.governor.create_task(
            str(self.repo_root / "tasks" / "2026-04-01-gate-load-balance-promotion-readiness-review.md"),
            workflow_kind="results_closeout",
            objective="readiness",
            risk_level="low",
        )
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "completed"
        self.schemas.write_json(task_record_path, task_record)
        policy = self.policy.load_policy()
        policy["enable_queue_planner"] = True
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)
        result = self.queue_planner.plan_queue()
        self.assertEqual(result["generated_task_ids"], [])
        updated = self.workflow_registry.load_workflow_instance("wf-block")
        self.assertEqual(updated["status"], "blocked")

    def test_plan_queue_respects_max_generated_tasks(self) -> None:
        workflow = self.workflow_registry.create_workflow_instance("gate_load_balance_promotion", workflow_id="wf-limit")
        workflow["completed_stages"] = [
            "real_case_staging",
            "real_case_closeout",
            "higher_budget_staging",
            "higher_budget_closeout",
            "second_seed_higher_budget",
            "second_seed_closeout",
        ]
        workflow["current_stage"] = "promotion_readiness_review"
        self.workflow_registry.save_workflow_instance(workflow)
        task_record_path = self.governor.create_task(
            str(self.repo_root / "tasks" / "2026-04-01-gate-load-balance-promotion-readiness-review.md"),
            workflow_kind="results_closeout",
            objective="readiness",
            risk_level="low",
        )
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "completed"
        task_record["workflow_signal"] = {"enter_extended_staging": True, "runtime_blocker": False}
        self.schemas.write_json(task_record_path, task_record)
        policy = self.policy.load_policy()
        policy["enable_queue_planner"] = True
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)
        result = self.queue_planner.plan_queue(max_generated_tasks=1)
        self.assertEqual(len(result["generated_task_ids"]), 1)

    def test_run_loop_uses_queue_planner_before_idling(self) -> None:
        fake_result = {
            "status": "completed",
            "runner_id": "runner-loop",
            "task_id": "task-loop",
            "run_id": "run-loop",
            "summary_path": "summary.md",
        }
        policy = self.policy.load_policy()
        policy["enable_queue_planner"] = True
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)
        task_ready = {"task_id": "task-loop", "workflow_kind": "truth_calibration"}
        with mock.patch.object(
            self.autopilot,
            "select_next_task",
            side_effect=[None, task_ready, None],
        ), mock.patch.object(
            self.autopilot,
            "run_once",
            return_value=fake_result,
        ), mock.patch.object(
            self.autopilot,
            "plan_queue",
            return_value={"generated_task_ids": ["task-loop"], "workflow_id": "wf-loop", "current_stage": "promotion_readiness_review"},
        ), mock.patch.object(
            self.autopilot.time,
            "sleep",
            side_effect=lambda seconds: None,
        ):
            result = self.autopilot.run_loop(
                "runner-queue-loop",
                max_rounds=1,
                max_session_minutes=1,
                idle_sleep_seconds_override=1,
                max_idle_sleep_seconds_override=2,
            )

        self.assertEqual(result["last_wake_reason"], "workflow_stage_advanced")

    def test_run_loop_idles_then_wakes_for_eligible_task(self) -> None:
        fake_result = {
            "status": "completed",
            "runner_id": "runner-loop",
            "task_id": "task-loop",
            "run_id": "run-loop",
            "summary_path": "summary.md",
        }
        idle_sleeps: list[int] = []
        task_ready = {"task_id": "task-loop", "workflow_kind": "truth_calibration"}
        with mock.patch.object(
            self.autopilot,
            "select_next_task",
            side_effect=[None, task_ready, None],
        ), mock.patch.object(
            self.autopilot,
            "run_once",
            return_value=fake_result,
        ), mock.patch.object(
            self.autopilot.time,
            "sleep",
            side_effect=lambda seconds: idle_sleeps.append(seconds),
        ):
            result = self.autopilot.run_loop(
                "runner-loop",
                max_rounds=1,
                max_session_minutes=1,
                idle_sleep_seconds_override=1,
                max_idle_sleep_seconds_override=2,
            )

        self.assertEqual(result["rounds_completed"], 1)
        self.assertEqual(result["last_wake_reason"], "eligible_task_found")
        self.assertTrue(idle_sleeps)
        events = self._read_events()
        self.assertTrue(any(item["event_type"] == "runner_idle" for item in events))
        self.assertTrue(any(item["event_type"] == "runner_woke" and item["details"].get("wake_reason") == "eligible_task_found" for item in events))
        runtime_session = self.schemas.load_json(self.constants.RUNTIME_SESSION_PATH)
        self.assertEqual(runtime_session["last_wake_reason"], "eligible_task_found")

    def test_run_loop_writes_session_end_reason_and_history(self) -> None:
        fake_result = {
            "status": "completed",
            "runner_id": "runner-session",
            "task_id": "task-session",
            "run_id": "run-session",
            "summary_path": "summary.md",
        }
        with mock.patch.object(self.autopilot, "select_next_task", return_value={"task_id": "task-session", "workflow_kind": "truth_calibration"}), \
            mock.patch.object(self.autopilot, "run_once", return_value=fake_result):
            result = self.autopilot.run_loop("runner-session", max_rounds=1, max_session_minutes=1)

        self.assertEqual(result["session_end_reason"], "max_session_rounds_reached")
        runtime_session = self.schemas.load_json(self.constants.RUNTIME_SESSION_PATH)
        self.assertEqual(runtime_session["session_end_reason"], "max_session_rounds_reached")
        history_lines = self.constants.RUNTIME_SESSION_HISTORY_PATH.read_text(encoding="utf-8").splitlines()
        self.assertTrue(history_lines)

    def test_run_once_releases_runner_id_after_success(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-v21-autopilot-trial-truth-calibration.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="truth_calibration", risk_level="low")
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "ready"
        self.schemas.write_json(task_record_path, task_record)

        fake = self.governor.CommandResult(
            skill="active-truth-calibration",
            command="pwsh ...",
            args={"format": "json"},
            exit_code=0,
            stdout='{"status":"ok","conflicts":[]}',
            stderr="",
        )
        with mock.patch.object(self.governor, "run_skill", return_value=fake), mock.patch.object(self.autopilot, "run_skill", return_value=fake, create=True):
            self.autopilot.run_once("runner-release")

        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        self.assertEqual(state["runner_id"], "")
        self.assertEqual(state["active_lease_status"], "idle")

    def test_autopilot_pauses_after_retry_limit(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multimodal-gate-collapse-analysis.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="truth_calibration", risk_level="low")
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "ready"
        task_record["retry_count"] = 2
        self.schemas.write_json(task_record_path, task_record)

        policy = self.policy.load_policy()
        policy["max_retries_per_task"] = 2
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)

        result = self.autopilot.run_once("runner-retry")
        self.assertEqual(result["status"], "paused_for_human")
        updated = self.schemas.load_json(task_record_path)
        self.assertEqual(updated["status"], "paused_for_human")
        policy_blocked = [item for item in self._read_events() if item["event_type"] == "policy_blocked"][-1]
        self.assertEqual(policy_blocked["reason_code"], "autopilot_max_retries_exceeded")
        self.assertTrue(policy_blocked["suggested_next_actions"])
        self.assertTrue(policy_blocked["details"]["recommended_action_summary"])
        self.assertIn("blocked_reason_detail", policy_blocked["details"])

    def test_select_next_task_uses_priority_and_sprint(self) -> None:
        task_a_path = self.governor.create_task(
            str(self.repo_root / "tasks" / "2026-03-31-multimodal-gate-collapse-analysis.md"),
            workflow_kind="truth_calibration",
            risk_level="low",
        )
        task_b_path = self.governor.create_task(
            str(self.repo_root / "tasks" / "2026-03-31-multilabel-head-wiring.md"),
            workflow_kind="truth_calibration",
            risk_level="low",
        )
        task_a = self.schemas.load_json(task_a_path)
        task_b = self.schemas.load_json(task_b_path)
        task_a["status"] = "ready"
        task_b["status"] = "ready"
        task_a["priority"] = 20
        task_b["priority"] = 10
        self.schemas.write_json(task_a_path, task_a)
        self.schemas.write_json(task_b_path, task_b)

        selected = self.autopilot.select_next_task()
        self.assertEqual(selected["task_id"], task_b["task_id"])

    def test_trial_precheck_reports_ready_truth_calibration_task(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-v21-autopilot-trial-truth-calibration.md"
        task_record_path = self.governor.create_task(
            str(task_file),
            workflow_kind="truth_calibration",
            objective="trial",
            risk_level="low",
        )
        task_record = self.schemas.load_json(task_record_path)
        task_record["status"] = "ready"
        self.schemas.write_json(task_record_path, task_record)
        result = self.trial.trial_precheck(task_record["task_id"])
        self.assertEqual(result["target_task"]["task_id"], task_record["task_id"])
        self.assertTrue(result["checks"]["target_task_ready"])

    def test_advance_review_updates_task_and_state(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multilabel-head-wiring.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="implementation_task", allowed_write_paths=["baseline/model.py"])
        task_id = self.schemas.load_json(task_record_path)["task_id"]
        run_id = "unit-advance"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        decision = self._decision_payload(run_id, workflow_kind="implementation_task", action_kind="implementation", action_name="implementation-task")
        decision["task_id"] = task_id
        execution = self._execution_payload(run_id, workflow_kind="implementation_task")
        execution["task_id"] = task_id
        verdict = self._verdict_payload(run_id, verdict="approve", next_mode="continue")
        verdict["task_id"] = task_id
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        self._write_json(run_dir / self.constants.EXECUTION_RESULT_NAME, execution)
        self._write_json(run_dir / self.constants.REVIEW_VERDICT_NAME, verdict)
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update({"status": "reviewer_workspace_ready", "current_run_id": run_id, "active_task_id": task_id})
        self._write_json(self.constants.CURRENT_STATE_PATH, state)

        summary_path = self.governor.advance_review(str(run_dir / self.constants.REVIEW_VERDICT_NAME))
        self.assertTrue(summary_path.exists())
        updated_task = self.schemas.load_json(task_record_path)
        self.assertEqual(updated_task["status"], "ready")
        updated_state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        self.assertEqual(updated_state["status"], "context_ready")

    def test_trial_truth_calibration_task_completes_after_approve(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-v21-autopilot-trial-truth-calibration.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="truth_calibration", risk_level="low")
        task_id = self.schemas.load_json(task_record_path)["task_id"]
        run_id = "unit-trial-complete"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        decision = self._decision_payload(run_id, workflow_kind="truth_calibration", action_kind="skill", action_name="active-truth-calibration")
        decision["task_id"] = task_id
        execution = self._execution_payload(run_id)
        execution["task_id"] = task_id
        verdict = self._verdict_payload(run_id, verdict="approve", next_mode="continue")
        verdict["task_id"] = task_id
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        self._write_json(run_dir / self.constants.EXECUTION_RESULT_NAME, execution)
        self._write_json(run_dir / self.constants.REVIEW_VERDICT_NAME, verdict)
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update({"status": "reviewer_workspace_ready", "current_run_id": run_id, "active_task_id": task_id})
        self._write_json(self.constants.CURRENT_STATE_PATH, state)

        self.governor.advance_review(str(run_dir / self.constants.REVIEW_VERDICT_NAME))
        updated_task = self.schemas.load_json(task_record_path)
        self.assertEqual(updated_task["status"], "completed")

    def test_completed_trial_task_wins_over_two_rounds_no_progress_pause(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-v21-autopilot-trial-truth-calibration.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="truth_calibration", risk_level="low")
        task_id = self.schemas.load_json(task_record_path)["task_id"]
        run_id = "unit-trial-no-progress"
        run_dir = self.constants.LOOP_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        decision = self._decision_payload(run_id, workflow_kind="truth_calibration", action_kind="skill", action_name="active-truth-calibration")
        decision["task_id"] = task_id
        execution = self._execution_payload(run_id)
        execution["task_id"] = task_id
        execution["progress_delta"]["fingerprint"] = "same-fingerprint"
        verdict = self._verdict_payload(run_id, verdict="approve", next_mode="continue")
        verdict["task_id"] = task_id
        self._write_json(run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        self._write_json(run_dir / self.constants.EXECUTION_RESULT_NAME, execution)
        self._write_json(run_dir / self.constants.REVIEW_VERDICT_NAME, verdict)
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update(
            {
                "status": "reviewer_workspace_ready",
                "current_run_id": run_id,
                "active_task_id": task_id,
                "last_progress_fingerprint": "same-fingerprint",
                "consecutive_no_progress": 1,
            }
        )
        self._write_json(self.constants.CURRENT_STATE_PATH, state)

        self.governor.advance_review(str(run_dir / self.constants.REVIEW_VERDICT_NAME))
        updated_state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        updated_task = self.schemas.load_json(task_record_path)
        self.assertEqual(updated_task["status"], "completed")
        self.assertEqual(updated_state["status"], "completed")

    def test_prepare_handoff_and_report_templates(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multimodal-gate-collapse-analysis.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="experiment_run")
        task_id = self.schemas.load_json(task_record_path)["task_id"]
        run_dir = self.repo_root / "baseline" / "runs" / "tmp_auto_closeout_metrics_smoke"
        experiment_path = self.governor.sync_experiment_from_run(task_id, str(run_dir))
        experiment_id = self.schemas.load_json(experiment_path)["experiment_id"]

        handoff_path = self.governor.prepare_handoff_template(task_id)
        report_path = self.governor.prepare_report_template(task_id, experiment_id)
        self.assertTrue(handoff_path.exists())
        self.assertTrue(report_path.exists())
        report_text = report_path.read_text(encoding="utf-8")
        self.assertIn("gate_health", report_text)

    def test_experiment_run_review_preserves_existing_registry_status(self) -> None:
        task_file = self.repo_root / "tasks" / "2026-03-31-multimodal-gate-collapse-analysis.md"
        task_record_path = self.governor.create_task(str(task_file), workflow_kind="experiment_run")
        task_id = self.schemas.load_json(task_record_path)["task_id"]
        run_dir = self.repo_root / "baseline" / "runs" / "tmp_auto_closeout_metrics_smoke"
        experiment_path = self.governor.sync_experiment_from_run(task_id, str(run_dir), status="staging")
        experiment_id = self.schemas.load_json(experiment_path)["experiment_id"]

        run_id = "unit-experiment-review"
        loop_run_dir = self.constants.LOOP_RUNS_DIR / run_id
        loop_run_dir.mkdir(parents=True, exist_ok=True)
        decision = self._decision_payload(run_id, workflow_kind="experiment_run", action_kind="experiment", action_name="experiment-run")
        decision["task_id"] = task_id
        decision["linked_experiment_id"] = experiment_id
        decision["required_checks"] = ["pwsh -Command Test-Path summary.json"]
        execution = self._execution_payload(run_id)
        execution["task_id"] = task_id
        execution["linked_experiment_id"] = experiment_id
        execution["action"]["kind"] = "experiment"
        execution["action"]["name"] = "experiment-run"
        verdict = self._verdict_payload(run_id, verdict="approve", next_mode="continue")
        verdict["task_id"] = task_id
        verdict["linked_experiment_id"] = experiment_id
        self._write_json(loop_run_dir / self.constants.PLANNER_DECISION_NAME, decision)
        self._write_json(loop_run_dir / self.constants.EXECUTION_RESULT_NAME, execution)
        self._write_json(loop_run_dir / self.constants.REVIEW_VERDICT_NAME, verdict)
        state = self.schemas.load_json(self.constants.CURRENT_STATE_PATH)
        state.update({"status": "reviewer_workspace_ready", "current_run_id": run_id, "active_task_id": task_id, "active_experiment_id": experiment_id})
        self._write_json(self.constants.CURRENT_STATE_PATH, state)

        self.governor.advance_review(str(loop_run_dir / self.constants.REVIEW_VERDICT_NAME))
        experiment_record = self.schemas.load_json(experiment_path)
        self.assertEqual(experiment_record["status"], "staging")

    def test_program_planner_marks_milestone_completed_after_workflow_completion(self) -> None:
        workflow = self.workflow_registry.create_workflow_instance(
            "gate_load_balance_promotion",
            workflow_id="wf-program-complete",
            lane="gate_load_balance",
        )
        workflow["completed_stages"] = [
            "real_case_staging",
            "real_case_closeout",
            "higher_budget_staging",
            "higher_budget_closeout",
            "second_seed_higher_budget",
            "second_seed_closeout",
            "promotion_readiness_review",
            "extended_real_case_staging",
            "extended_real_case_closeout",
            "promotion_candidate_decision",
        ]
        workflow["current_stage"] = ""
        workflow["status"] = "completed"
        self.workflow_registry.save_workflow_instance(workflow)
        program = self.workflow_registry.load_program_state()
        program["active_workflow_id"] = "wf-program-complete"
        self.workflow_registry.save_program_state(program)

        result = self.program_planner.recompute_program_state()
        completed = {item["milestone_id"] for item in result["milestones"] if item["status"] == "completed"}
        self.assertIn("gate_load_balance_validation_complete", completed)
        self.assertIn("gate_load_balance_promotion_candidate", completed)

    def test_program_planner_does_not_duplicate_completed_workflow(self) -> None:
        workflow = self.workflow_registry.create_workflow_instance(
            "gate_load_balance_promotion",
            workflow_id="wf-no-duplicate",
            lane="gate_load_balance",
        )
        workflow["completed_stages"] = [
            "real_case_staging",
            "real_case_closeout",
            "higher_budget_staging",
            "higher_budget_closeout",
            "second_seed_higher_budget",
            "second_seed_closeout",
            "promotion_readiness_review",
            "extended_real_case_staging",
            "extended_real_case_closeout",
            "promotion_candidate_decision",
        ]
        workflow["current_stage"] = ""
        workflow["status"] = "completed"
        self.workflow_registry.save_workflow_instance(workflow)
        program = self.workflow_registry.load_program_state()
        program["active_workflow_id"] = "wf-no-duplicate"
        self.workflow_registry.save_program_state(program)

        result = self.program_planner.ensure_program_progress()
        self.assertTrue(result["created_workflow"])
        created = self.workflow_registry.active_workflow_instance()
        self.assertEqual(created["template_name"], "multilabel_inference_protocol_decision")
        workflows = self.workflow_registry.list_workflow_instances()
        self.assertEqual(len([item for item in workflows if item["template_name"] == "gate_load_balance_promotion"]), 1)

    def test_decision_memory_blocks_restore_all_conflict(self) -> None:
        self.program_planner.ensure_decision_memory()
        decisions = self.program_planner.show_decisions()["decisions"]
        block_reason = self.program_planner._workflow_conflicts_with_decisions("restore_all_modalities", decisions)
        self.assertEqual(block_reason, "decision_memory_blocks_restore_all")

    def test_regression_sentinel_blocks_program_progress(self) -> None:
        task_path = self.repo_root / "tasks" / "2026-03-31-multimodal-gate-collapse-analysis.md"
        task_record_path = self.governor.create_task(str(task_path), workflow_kind="experiment_run")
        task_id = self.schemas.load_json(task_record_path)["task_id"]
        run_dir = self.repo_root / "baseline" / "runs" / "tmp_auto_closeout_metrics_smoke"
        experiment_path = self.governor.sync_experiment_from_run(task_id, str(run_dir))
        record = self.schemas.load_json(experiment_path)
        record["gate_health"] = {"status": "collapsed"}
        self.schemas.write_json(experiment_path, record)

        result = self.program_planner.recompute_program_state()
        self.assertTrue(result["regression_sentinel"]["regression_detected"])
        self.assertEqual(result["program"]["program_block_reason"], "regression_sentinel_triggered")

    def test_budget_guard_pauses_program(self) -> None:
        today = self.program_planner._now_iso()
        for idx in range(4):
            task_markdown = self.generated_tasks_dir / f"2026-04-01-budget-guard-{idx}.md"
            task_markdown.parent.mkdir(parents=True, exist_ok=True)
            task_markdown.write_text("# budget guard\n", encoding="utf-8")
            task_path = self.governor.create_task(
                str(task_markdown),
                workflow_kind="experiment_run",
            )
            task = self.schemas.load_json(task_path)
            task["status"] = "completed"
            task["updated_at"] = today
            self.schemas.write_json(task_path, task)
        policy = self.policy.load_policy()
        policy["program_max_experiments_per_day"] = 3
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)

        result = self.program_planner.recompute_program_state()
        self.assertEqual(result["program"]["program_block_reason"], "budget_guard_triggered")
        self.assertEqual(result["program"]["status"], "paused_for_human")

    def test_budget_guard_does_not_block_non_experiment_workflow(self) -> None:
        today = self.program_planner._now_iso()
        for idx in range(4):
            task_markdown = self.generated_tasks_dir / f"2026-04-01-budget-non-exp-{idx}.md"
            task_markdown.parent.mkdir(parents=True, exist_ok=True)
            task_markdown.write_text("# budget non experiment\n", encoding="utf-8")
            task_path = self.governor.create_task(str(task_markdown), workflow_kind="experiment_run")
            task = self.schemas.load_json(task_path)
            task["status"] = "completed"
            task["updated_at"] = today
            self.schemas.write_json(task_path, task)
        workflow = self.workflow_registry.create_workflow_instance(
            "gate_load_balance_promotion",
            workflow_id="wf-budget-non-exp",
            lane="gate_load_balance",
        )
        workflow["completed_stages"] = [
            "real_case_staging",
            "real_case_closeout",
            "higher_budget_staging",
            "higher_budget_closeout",
            "second_seed_higher_budget",
            "second_seed_closeout",
            "promotion_readiness_review",
            "extended_real_case_staging",
            "extended_real_case_closeout",
            "promotion_candidate_decision",
        ]
        workflow["current_stage"] = ""
        workflow["status"] = "completed"
        self.workflow_registry.save_workflow_instance(workflow)
        program = self.workflow_registry.load_program_state()
        program["active_workflow_id"] = "wf-budget-non-exp"
        self.workflow_registry.save_program_state(program)
        policy = self.policy.load_policy()
        policy["program_max_experiments_per_day"] = 3
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)

        result = self.program_planner.recompute_program_state()
        self.assertEqual(result["budget_guard"]["budget_state"]["budget_window_status"], "exhausted")
        self.assertEqual(result["program"]["status"], "active")
        self.assertEqual(result["program"]["next_workflow_template"], "multilabel_inference_protocol_decision")

    def test_run_loop_uses_program_planner_when_no_active_workflow(self) -> None:
        policy = self.policy.load_policy()
        policy["enable_queue_planner"] = True
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)

        with mock.patch.object(self.autopilot, "select_next_task", side_effect=[None, {"task_id": "task-generated", "workflow_kind": "truth_calibration"}, None]), \
            mock.patch.object(self.autopilot, "run_once", return_value={"status": "completed", "runner_id": "runner-program", "task_id": "task-generated", "run_id": "run-generated"}), \
            mock.patch.object(self.autopilot, "ensure_program_progress", return_value={"created_workflow": True, "workflow_id": "wf-created", "program_status": "active"}), \
            mock.patch.object(self.autopilot, "plan_queue", return_value={"generated_task_ids": ["task-generated"], "workflow_id": "wf-created"}):
            result = self.autopilot.run_loop(
                "runner-program",
                max_rounds=1,
                max_session_minutes=1,
                idle_sleep_seconds_override=1,
                max_idle_sleep_seconds_override=1,
            )

        self.assertEqual(result["last_wake_reason"], "workflow_stage_advanced")
        events = self._read_events()
        self.assertTrue(any(item["event_type"] == "runner_woke" and item["details"].get("wake_reason") == "workflow_stage_advanced" for item in events))

    def test_program_status_and_decision_views_expose_program_level_fields(self) -> None:
        status = self.program_planner.show_program_status()
        milestones = self.program_planner.show_milestones()
        decisions = self.program_planner.show_decisions()
        self.assertIn("active_milestone", status)
        self.assertIn("program_block_reason", status)
        self.assertIn("milestones", milestones)
        self.assertIn("decisions", decisions)

    def test_budget_window_reset_resumes_program(self) -> None:
        budget_state = {
            "date": "2026-03-31",
            "experiments_run_today": 5,
            "gpu_budget_minutes_used": 100,
            "last_reset_at": "2026-03-31T00:00:00+08:00",
            "budget_window_status": "exhausted",
        }
        self.schemas.write_json(self.constants.PROGRAM_BUDGET_STATE_PATH, budget_state)
        result = self.program_planner.reset_budget_window()
        self.assertEqual(result["budget_state"]["budget_window_status"], "open")
        self.assertEqual(result["budget_state"]["experiments_run_today"], 0)
        self.assertIn("program", result)

    def test_program_planner_creates_inference_protocol_workflow_after_promotion_completion(self) -> None:
        workflow = self.workflow_registry.create_workflow_instance(
            "gate_load_balance_promotion",
            workflow_id="wf-promo-complete",
            lane="gate_load_balance",
        )
        workflow["completed_stages"] = [
            "real_case_staging",
            "real_case_closeout",
            "higher_budget_staging",
            "higher_budget_closeout",
            "second_seed_higher_budget",
            "second_seed_closeout",
            "promotion_readiness_review",
            "extended_real_case_staging",
            "extended_real_case_closeout",
            "promotion_candidate_decision",
        ]
        workflow["current_stage"] = ""
        workflow["status"] = "completed"
        self.workflow_registry.save_workflow_instance(workflow)
        program = self.workflow_registry.load_program_state()
        program["active_workflow_id"] = "wf-promo-complete"
        self.workflow_registry.save_program_state(program)
        policy = self.policy.load_policy()
        policy["program_max_experiments_per_day"] = 999
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)

        result = self.program_planner.ensure_program_progress()
        self.assertTrue(result["created_workflow"])
        created = self.workflow_registry.active_workflow_instance()
        self.assertEqual(created["template_name"], "multilabel_inference_protocol_decision")

    def test_active_inference_decision_prevents_duplicate_inference_workflow(self) -> None:
        self.program_planner.ensure_decision_memory()
        with self.constants.DECISION_MEMORY_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "decision_id": "inference-protocol-final",
                "topic": "multilabel_inference_selector",
                "topic_kind": "inference_protocol",
                "chosen_option": "dual_output_without_selector",
                "rejected_options": ["selector_first"],
                "evidence_ids": ["e1"],
                "confidence": 0.8,
                "supersedes": [],
                "decision_status": "active",
                "next_action_hint": "none",
                "blocks_workflows": [],
                "recorded_at": self.program_planner._now_iso(),
            }, ensure_ascii=False) + "\n")
        workflow = self.workflow_registry.create_workflow_instance(
            "gate_load_balance_promotion",
            workflow_id="wf-promo-done-2",
            lane="gate_load_balance",
        )
        workflow["completed_stages"] = [
            "real_case_staging",
            "real_case_closeout",
            "higher_budget_staging",
            "higher_budget_closeout",
            "second_seed_higher_budget",
            "second_seed_closeout",
            "promotion_readiness_review",
            "extended_real_case_staging",
            "extended_real_case_closeout",
            "promotion_candidate_decision",
        ]
        workflow["current_stage"] = ""
        workflow["status"] = "completed"
        self.workflow_registry.save_workflow_instance(workflow)
        program = self.workflow_registry.load_program_state()
        program["active_workflow_id"] = "wf-promo-done-2"
        self.workflow_registry.save_program_state(program)
        policy = self.policy.load_policy()
        policy["program_max_experiments_per_day"] = 999
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)

        result = self.program_planner.ensure_program_progress()
        self.assertTrue(result["created_workflow"])
        created = self.workflow_registry.active_workflow_instance()
        self.assertEqual(created["template_name"], "promotion_candidate_followup")

    def test_inference_protocol_decision_payload_syncs_to_decision_memory(self) -> None:
        task_markdown = self.generated_tasks_dir / "2026-04-01-multilabel-inference-protocol-decision.md"
        task_markdown.parent.mkdir(parents=True, exist_ok=True)
        task_markdown.write_text("# inference decision\n", encoding="utf-8")
        task_path = self.governor.create_task(
            str(task_markdown),
            workflow_kind="truth_calibration",
            skill_args={"topic": "multilabel_inference_protocol", "format": "json"},
        )
        task = self.schemas.load_json(task_path)
        task["status"] = "completed"
        task["template_name"] = "inference_protocol_decision"
        task["decision_payload"] = {
            "topic": "multilabel_inference_selector",
            "chosen_protocol": "dual_output_without_selector",
            "rejected_protocols": ["selector_first"],
            "requires_selector_experiment": False,
            "ready_for_implementation": True,
            "next_action_hint": "promotion_candidate_followup",
        }
        self.schemas.write_json(task_path, task)

        decisions = self.program_planner.recompute_program_state()["decisions"]
        matches = [item for item in decisions if item.get("decision_id") == f"{task['task_id']}-decision"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["topic"], "multilabel_inference_selector")
        self.assertEqual(matches[0]["next_action_hint"], "promotion_candidate_followup")

    def test_followup_decision_promotes_exactly_one_placeholder_task(self) -> None:
        task_markdown = self.generated_tasks_dir / "2026-04-01-gate-load-balance-promotion-followup-decision.md"
        task_markdown.parent.mkdir(parents=True, exist_ok=True)
        task_markdown.write_text("# followup decision\n", encoding="utf-8")
        task_path = self.governor.create_task(
            str(task_markdown),
            workflow_kind="truth_calibration",
            skill_args={"topic": "promotion_candidate_followup", "format": "json"},
        )
        task = self.schemas.load_json(task_path)
        task["status"] = "completed"
        task["template_name"] = "promotion_followup_decision"
        task["decision_payload"] = {
            "topic": "promotion_candidate_followup",
            "chosen_protocol": "dual_output_without_selector",
            "rejected_protocols": ["selector_feasibility_smoke", "hold_no_experiment"],
            "requires_selector_experiment": False,
            "ready_for_implementation": True,
            "next_action_hint": "dual_output_implementation_plan",
        }
        self.schemas.write_json(task_path, task)

        self.program_planner.recompute_program_state()
        records = self.governor.list_task_records()
        placeholders = [
            item for item in records
            if str(item.get("template_name", "")) in {
                "selector_feasibility_smoke",
                "dual_output_implementation_plan",
                "inference_hold_closeout",
            }
        ]
        self.assertEqual(len(placeholders), 3)
        ready = [item for item in placeholders if str(item.get("status", "")) == "ready"]
        self.assertEqual(len(ready), 0)
        result = self.program_planner.recompute_program_state()
        self.assertEqual(result["program"]["next_workflow_template"], "dual_output_implementation_plan")
        dual_placeholder = next(item for item in placeholders if str(item.get("template_name", "")) == "dual_output_implementation_plan")
        self.assertEqual(str(dual_placeholder.get("status", "")), "proposed")
        self.assertFalse(bool(dual_placeholder.get("autopilot_enabled", True)))

    def test_program_planner_creates_dual_output_workflow_after_followup_decision(self) -> None:
        task_markdown = self.generated_tasks_dir / "2026-04-01-gate-load-balance-promotion-followup-decision.md"
        task_markdown.parent.mkdir(parents=True, exist_ok=True)
        task_markdown.write_text("# dual output next\n", encoding="utf-8")
        task_path = self.governor.create_task(
            str(task_markdown),
            workflow_kind="truth_calibration",
            skill_args={"topic": "promotion_candidate_followup", "format": "json"},
        )
        task = self.schemas.load_json(task_path)
        task["status"] = "completed"
        task["template_name"] = "promotion_followup_decision"
        task["decision_payload"] = {
            "topic": "promotion_candidate_followup",
            "chosen_protocol": "dual_output_without_selector",
            "rejected_protocols": ["selector_feasibility_smoke"],
            "requires_selector_experiment": False,
            "ready_for_implementation": True,
            "next_action_hint": "dual_output_implementation_plan",
        }
        self.schemas.write_json(task_path, task)
        policy = self.policy.load_policy()
        policy["program_max_experiments_per_day"] = 999
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)

        result = self.program_planner.ensure_program_progress()
        self.assertTrue(result["created_workflow"])
        workflow = self.workflow_registry.active_workflow_instance()
        self.assertEqual(workflow["template_name"], "dual_output_implementation_plan")

    def test_dual_output_workflow_stages_can_be_instantiated(self) -> None:
        workflow = self.workflow_registry.create_workflow_instance(
            "dual_output_implementation_plan",
            workflow_id="wf-dual-output",
            lane="gate_load_balance",
        )
        self.assertEqual(workflow["current_stage"], "dual_output_plan_evidence_closeout")
        policy = self.policy.load_policy()
        policy["enable_queue_planner"] = True
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)

        result = self.queue_planner.plan_queue(max_generated_tasks=1)
        self.assertTrue(result["generated_task_ids"])
        record = self.governor.get_task_record(result["generated_task_ids"][0])
        self.assertEqual(str(record.get("template_name", "")), "dual_output_plan_evidence_closeout")

    def test_dual_output_completed_stage_advances_to_next_stage(self) -> None:
        workflow = self.workflow_registry.create_workflow_instance(
            "dual_output_implementation_plan",
            workflow_id="wf-dual-output-advance",
            lane="gate_load_balance",
        )
        task_markdown = self.generated_tasks_dir / "2026-04-01-multilabel-dual-output-plan-evidence-closeout.md"
        task_markdown.parent.mkdir(parents=True, exist_ok=True)
        task_markdown.write_text("# dual output evidence\n", encoding="utf-8")
        task_path = self.governor.create_task(str(task_markdown), workflow_kind="results_closeout")
        task = self.schemas.load_json(task_path)
        task["task_id"] = "2026-04-01-multilabel-dual-output-plan-evidence-closeout"
        task["template_name"] = "dual_output_plan_evidence_closeout"
        task["status"] = "completed"
        self.schemas.write_json(self.constants.TASK_REGISTRY_DIR / "2026-04-01-multilabel-dual-output-plan-evidence-closeout.json", task)
        policy = self.policy.load_policy()
        policy["enable_queue_planner"] = True
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)

        result = self.queue_planner.plan_queue(max_generated_tasks=1)
        generated = result["generated_task_ids"]
        self.assertTrue(generated)
        record = self.governor.get_task_record(generated[0])
        self.assertEqual(str(record.get("template_name", "")), "dual_output_plan_decision")

    def test_dual_output_decision_payload_syncs_and_promotes_single_phase3_placeholder(self) -> None:
        task_markdown = self.generated_tasks_dir / "2026-04-01-multilabel-dual-output-plan-decision.md"
        task_markdown.parent.mkdir(parents=True, exist_ok=True)
        task_markdown.write_text("# dual output plan decision\n", encoding="utf-8")
        task_path = self.governor.create_task(
            str(task_markdown),
            workflow_kind="truth_calibration",
            skill_args={"topic": "dual_output_implementation_plan", "format": "json"},
        )
        task = self.schemas.load_json(task_path)
        task["status"] = "completed"
        task["template_name"] = "dual_output_plan_decision"
        task["decision_payload"] = {
            "topic": "dual_output_implementation_plan",
            "chosen_protocol": "dual_output_without_selector",
            "rejected_protocols": ["selector_first"],
            "implementation_scope": "dual_output_runtime_and_model_outputs",
            "requires_runtime_api_change": True,
            "requires_model_output_change": True,
            "ready_for_implementation": True,
            "next_action_hint": "dual_output_runtime_patch",
        }
        self.schemas.write_json(task_path, task)

        decisions = self.program_planner.recompute_program_state()["decisions"]
        matches = [item for item in decisions if item.get("decision_id") == f"{task['task_id']}-decision"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["topic"], "dual_output_implementation_plan")
        phase3 = [
            item for item in self.governor.list_task_records()
            if str(item.get("template_name", "")) in {
                "dual_output_runtime_patch",
                "dual_output_report_closeout",
                "dual_output_hold_closeout",
            }
        ]
        self.assertEqual(len(phase3), 3)
        ready = [item for item in phase3 if str(item.get("status", "")) == "ready"]
        self.assertEqual(len(ready), 1)
        self.assertEqual(str(ready[0].get("template_name", "")), "dual_output_runtime_patch")

    def test_run_loop_exits_gracefully_when_program_waits_for_next_phase(self) -> None:
        with mock.patch.object(self.autopilot, "select_next_task", return_value=None), \
            mock.patch.object(self.autopilot, "ensure_program_progress", return_value={"created_workflow": False, "workflow_id": "", "program_status": "paused_for_human"}), \
            mock.patch.object(self.autopilot, "plan_queue", return_value={"generated_task_ids": [], "workflow_id": ""}), \
            mock.patch.object(self.autopilot, "show_program_status", return_value={"status": "paused_for_human", "active_workflow_id": "", "next_recommended_workflow": "dual_output_runtime_patch"}), \
            mock.patch.object(self.autopilot, "show_program_handoff", return_value={"next_recommended_workflow": "dual_output_runtime_patch", "next_ready_task_id": "2026-04-01-multilabel-dual-output-runtime-patch"}):
            result = self.autopilot.run_loop(
                "runner-stop",
                max_rounds=5,
                max_session_minutes=10,
                idle_sleep_seconds_override=1,
                max_idle_sleep_seconds_override=1,
            )

        self.assertEqual(result["session_end_reason"], "program_waiting_for_next_phase")

    def test_show_loop_status_tolerates_partial_state_files(self) -> None:
        self.constants.QUEUE_PLANNER_STATE_PATH.write_text("{bad", encoding="utf-8")
        self.constants.DECISION_MEMORY_PATH.write_text("{bad\n", encoding="utf-8")
        status = self.autopilot.show_loop_status()
        self.assertIn("queue_planner_enabled", status)
        self.assertIn("program_status", status)

    def test_strict_closeout_passed_run_updates_best_known_metrics(self) -> None:
        task_path = self.repo_root / "tasks" / "2026-03-31-multimodal-gate-collapse-analysis.md"
        task_record_path = self.governor.create_task(str(task_path), workflow_kind="experiment_run")
        task_id = self.schemas.load_json(task_record_path)["task_id"]
        run_dir = self.repo_root / "baseline" / "runs" / "tmp_auto_closeout_metrics_smoke"
        experiment_path = self.governor.sync_experiment_from_run(task_id, str(run_dir))
        record = self.schemas.load_json(experiment_path)
        record["variant"] = "gate_load_balance_candidate"
        record["closeout_status"] = "passed"
        record["best_val_l3_macro_f1"] = 0.91
        record["best_val_multilabel_micro_f1"] = 0.92
        record["mean_gates"] = {"sequence": 0.4, "structure": 0.3, "context": 0.3}
        record["gate_health"] = {"status": "healthy"}
        self.schemas.write_json(experiment_path, record)

        best_known = self.program_planner.show_best_known()
        self.assertEqual(best_known["source_experiment_id"], record["experiment_id"])
        self.assertEqual(best_known["best_gate_health_status"], "healthy")

    def test_followup_milestone_can_be_instantiated_as_workflow(self) -> None:
        workflow = self.workflow_registry.create_workflow_instance(
            "multilabel_inference_protocol_decision",
            workflow_id="wf-infer-complete",
            lane="gate_load_balance",
        )
        workflow["completed_stages"] = [
            "inference_protocol_evidence_closeout",
            "inference_protocol_decision",
            "inference_protocol_handoff",
        ]
        workflow["current_stage"] = ""
        workflow["status"] = "completed"
        self.workflow_registry.save_workflow_instance(workflow)
        program = self.workflow_registry.load_program_state()
        program["active_workflow_id"] = "wf-infer-complete"
        self.workflow_registry.save_program_state(program)
        policy = self.policy.load_policy()
        policy["program_max_experiments_per_day"] = 999
        self.schemas.write_json(self.constants.INTERVENTION_POLICY_PATH, policy)

        result = self.program_planner.ensure_program_progress()
        self.assertTrue(result["created_workflow"])
        created = self.workflow_registry.active_workflow_instance()
        self.assertEqual(created["template_name"], "promotion_candidate_followup")

    def test_program_handoff_updates_on_recompute(self) -> None:
        snapshot = self.program_planner.recompute_program_state()
        handoff = self.program_planner.show_program_handoff()
        self.assertIn("active_milestone", handoff)
        self.assertIn("best_known_metrics_snapshot", handoff)
        self.assertIn("next_ready_task_id", handoff)
        self.assertIn("program_stop_reason", handoff)
        self.assertEqual(handoff["program_id"], snapshot["program"]["program_id"])
        report_path = self.constants.REPORTS_DIR / "program" / f"{self.program_planner.datetime.now().astimezone().date().isoformat()}-program-summary.md"
        self.assertTrue(report_path.exists())

    def test_dual_output_runtime_patch_template_is_real_implementation_task(self) -> None:
        candidate = self.task_templates.build_multilabel_phase3_placeholder(
            "dual_output_runtime_patch",
            source_evidence_ids=["dual_output_implementation_plan_ready"],
        )
        self.assertEqual(candidate["create_kwargs"]["workflow_kind"], "implementation_task")
        self.assertTrue(candidate["create_kwargs"]["allowed_write_paths"])
        self.assertTrue(candidate["create_kwargs"]["required_checks"])

    def test_dual_output_runtime_patch_completion_promotes_report_closeout(self) -> None:
        decision_markdown = self.generated_tasks_dir / "2026-04-01-multilabel-dual-output-plan-decision.md"
        decision_markdown.parent.mkdir(parents=True, exist_ok=True)
        decision_markdown.write_text("# dual output plan decision\n", encoding="utf-8")
        decision_path = self.governor.create_task(
            str(decision_markdown),
            workflow_kind="truth_calibration",
            skill_args={"topic": "dual_output_implementation_plan", "format": "json"},
        )
        decision_task = self.schemas.load_json(decision_path)
        decision_task["status"] = "completed"
        decision_task["template_name"] = "dual_output_plan_decision"
        decision_task["decision_payload"] = {
            "topic": "dual_output_implementation_plan",
            "chosen_protocol": "dual_output_without_selector",
            "rejected_protocols": ["selector_first"],
            "ready_for_implementation": True,
            "implementation_scope": "dual_output_runtime_and_model_outputs",
            "requires_runtime_api_change": True,
            "requires_model_output_change": True,
            "next_action_hint": "dual_output_runtime_patch",
        }
        self.schemas.write_json(decision_path, decision_task)

        runtime_markdown = self.generated_tasks_dir / "2026-04-01-multilabel-dual-output-runtime-patch.md"
        runtime_markdown.parent.mkdir(parents=True, exist_ok=True)
        runtime_markdown.write_text("# runtime patch\n", encoding="utf-8")
        runtime_path = self.governor.create_task(
            str(runtime_markdown),
            workflow_kind="implementation_task",
            objective="patch",
            allowed_write_paths=["baseline/evaluate_multimodal.py"],
            required_checks=["conda run -n ai4s python -m unittest integrations.codex_loop.tests.test_codex_loop"],
        )
        runtime_task = self.schemas.load_json(runtime_path)
        runtime_task["status"] = "completed"
        runtime_task["template_name"] = "dual_output_runtime_patch"
        runtime_task["decision_payload"] = {
            "topic": "dual_output_implementation_plan",
            "chosen_protocol": "dual_output_without_selector",
            "rejected_protocols": ["selector_first"],
            "ready_for_implementation": True,
            "implementation_scope": "dual_output_runtime_and_model_outputs",
            "requires_runtime_api_change": True,
            "requires_model_output_change": True,
            "next_action_hint": "dual_output_report_closeout",
        }
        self.schemas.write_json(runtime_path, runtime_task)

        self.program_planner.recompute_program_state()
        decisions = self.program_planner.show_decisions()["decisions"]
        active_matches = [
            item
            for item in decisions
            if item.get("topic") == "dual_output_implementation_plan"
            and item.get("decision_status") == "active"
        ]
        self.assertEqual(len(active_matches), 1)
        self.assertEqual(active_matches[0]["decision_id"], f"{runtime_task['task_id']}-decision")
        self.assertEqual(active_matches[0]["next_action_hint"], "dual_output_report_closeout")
        ready = [
            item for item in self.governor.list_task_records()
            if str(item.get("template_name", "")) in {
                "dual_output_runtime_patch",
                "dual_output_report_closeout",
                "dual_output_hold_closeout",
            }
            and str(item.get("status", "")) == "ready"
        ]
        self.assertEqual(len(ready), 1)
        self.assertEqual(str(ready[0].get("template_name", "")), "dual_output_report_closeout")
        runtime_updated = self.governor.get_task_record(runtime_task["task_id"])
        self.assertEqual(str(runtime_updated.get("status", "")), "completed")

    def test_build_experiment_registry_draft_captures_dual_output_runtime(self) -> None:
        run_dir = self.loop_home / "baseline" / "runs" / "dual-output-ready"
        evaluation_dir = run_dir / "evaluation"
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        self.schemas.write_json(
            run_dir / "summary.json",
            {
                "run_name": "dual-output-ready",
                "variant": "gate_load_balance_candidate",
                "seed": 42,
                "best_val_l3_macro_f1": 0.9,
                "best_val_metrics": {
                    "multilabel": {"micro_f1": 0.91},
                    "mean_gates": {"sequence": 0.4, "structure": 0.3, "context": 0.3},
                    "gate_health": {"status": "healthy"},
                },
                "dual_output_runtime": {
                    "enabled": True,
                    "protocol": "dual_output_without_selector",
                    "metrics_masked_by_target_mask": True,
                },
            },
        )
        self.schemas.write_json(evaluation_dir / "metrics_val.json", {"dual_output": {"protocol": "dual_output_without_selector"}})
        self.schemas.write_json(evaluation_dir / "metrics_test.json", {"dual_output": {"protocol": "dual_output_without_selector"}})

        draft = self.artifacts.build_experiment_registry_draft(run_dir, task_id="task-1")
        self.assertIn("dual_output_runtime", draft)
        self.assertEqual(draft["dual_output_runtime"]["protocol"], "dual_output_without_selector")


if __name__ == "__main__":
    unittest.main()
