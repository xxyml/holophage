from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
PWSH = shutil.which("pwsh")


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


active_truth_module = load_module(
    "active_truth_calibration",
    "skills/active-truth-calibration/scripts/active_truth_calibration.py",
)
governance_build_module = load_module(
    "build_training_governance_assets",
    "tools/build_training_governance_assets.py",
)
governance_runner_module = load_module(
    "run_governance_build_validate",
    "skills/governance-assets-build-validate/scripts/run_governance_build_validate.py",
)
governance_audit_module = load_module(
    "governance_to_multilabel_audit",
    "skills/governance-to-multilabel-audit/scripts/governance_to_multilabel_audit.py",
)
results_closeout_module = load_module(
    "results_closeout_lite",
    "skills/results-closeout-lite/scripts/results_closeout_lite.py",
)


class ActiveTruthCalibrationTests(unittest.TestCase):
    def test_truth_brief_uses_runtime_active_and_support_sections(self) -> None:
        active_version = {
            "active_truth": {
                "ontology_version": "PFO_v1.0.2",
                "split_strategy": "homology_cluster",
                "split_version": "homology_cluster_v1",
                "sequence_embedding_key": "exact_sequence_rep_id",
                "baseline_scope": "L1_L2_L3_core",
                "target_status_primary": "trainable_core",
            }
        }
        active_paths = {
            "paths": {
                "active_roots": {
                    "baseline": "baseline",
                    "embedding_pipeline": "embedding_pipeline",
                    "saprot_embedding": "SaProt-1.3B_emb",
                    "data_processed": "data_processed",
                    "outputs": "outputs",
                    "splits": "splits",
                    "project_memory": "project_memory",
                },
                "support_roots": {
                    "structure_pipeline": "structure_pipeline",
                    "structures": "structures",
                    "portable_pipeline": "dataset_pipeline_portable",
                },
            }
        }
        runtime_text = textwrap.dedent(
            """
            ## 当前 active runtime

            - [baseline](D:/data/ai4s/holophage/baseline)
            - [embedding_pipeline](D:/data/ai4s/holophage/embedding_pipeline)
            - [data_processed](D:/data/ai4s/holophage/data_processed)
            - [outputs](D:/data/ai4s/holophage/outputs)
            - [splits](D:/data/ai4s/holophage/splits)
            - [project_memory](D:/data/ai4s/holophage/project_memory)

            其中当前 active baseline 的正式解释固定为：

            - `ontology_version = PFO_v1.0.2`
            - `split_strategy = homology_cluster`
            - `split_version = homology_cluster_v1`
            - `sequence_embedding_key = exact_sequence_rep_id`
            - `baseline_scope = L1 + L2 + L3 core`
            - `target_status = trainable_core`

            ## 当前不属于 active baseline runtime 的内容

            - [SaProt-1.3B_emb](D:/data/ai4s/holophage/SaProt-1.3B_emb)
            - [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline)
            - [structures](D:/data/ai4s/holophage/structures)
            - [dataset_pipeline_portable](D:/data/ai4s/holophage/dataset_pipeline_portable)
            """
        ).strip()
        sprint_text = textwrap.dedent(
            """
            - `PFO v1.0.2`
            - `homology_cluster_v1`
            - `exact_sequence_rep_id`
            - `L1 + L2 + L3 core`
            - `trainable_core`

            本轮只做一件事
            - 在不改变当前正式主线 truth 的前提下，完成 C 线 staging 收口，并把主线切到 multilabel head 实现与接入
            """
        ).strip()

        conflicts, truth_brief = active_truth_module.check_conflicts(
            active_version=active_version,
            active_paths=active_paths,
            runtime_text=runtime_text,
            sprint_text=sprint_text,
        )

        self.assertEqual(conflicts, [])
        self.assertEqual(
            truth_brief["active_runtime_roots"],
            {
                "baseline": "baseline",
                "embedding_pipeline": "embedding_pipeline",
                "data_processed": "data_processed",
                "outputs": "outputs",
                "splits": "splits",
                "project_memory": "project_memory",
            },
        )
        self.assertEqual(truth_brief["active_roots"], truth_brief["active_runtime_roots"])
        self.assertEqual(
            truth_brief["support_roots"],
            {
                "saprot_embedding": "SaProt-1.3B_emb",
                "structure_pipeline": "structure_pipeline",
                "structures": "structures",
                "portable_pipeline": "dataset_pipeline_portable",
            },
        )

    def test_support_root_leakage_fails_fast(self) -> None:
        active_version = {
            "active_truth": {
                "ontology_version": "PFO_v1.0.2",
                "split_strategy": "homology_cluster",
                "split_version": "homology_cluster_v1",
                "sequence_embedding_key": "exact_sequence_rep_id",
                "baseline_scope": "L1_L2_L3_core",
                "target_status_primary": "trainable_core",
            }
        }
        active_paths = {
            "paths": {
                "active_roots": {"baseline": "baseline"},
                "support_roots": {"structure_pipeline": "structure_pipeline"},
            }
        }
        runtime_text = textwrap.dedent(
            """
            ## 当前 active runtime

            - [baseline](D:/data/ai4s/holophage/baseline)
            - [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline)

            - `ontology_version = PFO_v1.0.2`
            - `split_strategy = homology_cluster`
            - `split_version = homology_cluster_v1`
            - `sequence_embedding_key = exact_sequence_rep_id`
            - `baseline_scope = L1 + L2 + L3 core`
            - `target_status = trainable_core`

            ## 当前不属于 active baseline runtime 的内容

            - [structure_pipeline](D:/data/ai4s/holophage/structure_pipeline)
            """
        ).strip()
        sprint_text = textwrap.dedent(
            """
            - `PFO v1.0.2`
            - `homology_cluster_v1`
            - `exact_sequence_rep_id`
            - `L1 + L2 + L3 core`
            - `trainable_core`
            """
        ).strip()

        conflicts, _ = active_truth_module.check_conflicts(
            active_version=active_version,
            active_paths=active_paths,
            runtime_text=runtime_text,
            sprint_text=sprint_text,
        )

        self.assertTrue(any("Support-only roots leaked" in item for item in conflicts))


class GovernanceSummaryTests(unittest.TestCase):
    def test_write_summary_separates_canonical_and_materialized_output(self) -> None:
        master = pd.DataFrame(
            [
                {
                    "status": "trainable_core",
                    "defer_coarse_policy": "not_applicable",
                    "participates_l1": True,
                    "participates_l2": True,
                    "participates_l3_core": True,
                    "participates_l3_multilabel": False,
                    "participates_open_set": False,
                },
                {
                    "status": "trainable_multilabel",
                    "defer_coarse_policy": "not_applicable",
                    "participates_l1": True,
                    "participates_l2": True,
                    "participates_l3_core": False,
                    "participates_l3_multilabel": True,
                    "participates_open_set": False,
                },
            ]
        )
        long_df = pd.DataFrame([{"supervision_channel": "L3_multilabel"}])
        task_tables = {
            "core_task_table": master.iloc[[0]].copy(),
            "multilabel_task_table": master.iloc[[1]].copy(),
            "parent_only_coarse_table": master.iloc[0:0].copy(),
            "open_set_table": master.iloc[0:0].copy(),
            "defer_review_table": master.iloc[0:0].copy(),
        }
        multilabel_vocab = {"Tail_spike": 0, "Anti_restriction": 1}

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            governance_build_module.write_summary(
                output_dir=output_dir,
                master=master,
                long_df=long_df,
                task_tables=task_tables,
                multilabel_vocab=multilabel_vocab,
            )
            summary = json.loads((output_dir / "pfo_v1_0_2_governance_summary.json").read_text(encoding="utf-8"))

        self.assertIn("canonical_sources", summary)
        self.assertIn("materialized_output", summary)
        self.assertEqual(summary["materialized_output"]["output_dir"], str(output_dir.resolve()))
        self.assertEqual(
            summary["materialized_output"]["master_wide_routing_table"],
            str((output_dir / "pfo_v1_0_2_master_routing_table.parquet").resolve()),
        )
        self.assertEqual(
            summary["canonical_sources"]["mapped_ontology_governance_table"],
            "data_processed/training_labels_wide_with_split.csv",
        )


class GovernanceRunnerTests(unittest.TestCase):
    def test_summarize_failure_output_strips_traceback(self) -> None:
        output = textwrap.dedent(
            """
            Traceback (most recent call last):
              File "build.py", line 1, in <module>
                raise FileNotFoundError("missing file")
            FileNotFoundError: [Errno 2] No such file or directory: 'missing.csv'
            """
        ).strip()

        summary = governance_runner_module.summarize_failure_output(output)

        self.assertEqual(summary, "FileNotFoundError: [Errno 2] No such file or directory: 'missing.csv'")


class GovernanceAuditTests(unittest.TestCase):
    def _build_audit_repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        tmp_dir = tempfile.TemporaryDirectory()
        repo_root = Path(tmp_dir.name)

        (repo_root / "project_memory" / "04_active_assets").mkdir(parents=True)
        (repo_root / "data_processed" / "governance").mkdir(parents=True)
        (repo_root / "outputs").mkdir(parents=True)
        (repo_root / "baseline").mkdir(parents=True)

        (repo_root / "project_memory" / "04_active_assets" / "ACTIVE_VERSION.yaml").write_text(
            textwrap.dedent(
                """
                training_contract:
                  label_boundary:
                    trainable_multilabel_in_round1: false
                  statuses_defined:
                    - trainable_core
                    - trainable_multilabel
                """
            ).strip(),
            encoding="utf-8",
        )
        (repo_root / "data_processed" / "governance" / "pfo_v1_0_2_governance_summary.json").write_text(
            json.dumps(
                {
                    "runtime_invariants": {
                        "ontology_version": "PFO_v1.0.2",
                        "split_version": "homology_cluster_v1",
                        "sequence_embedding_key": "exact_sequence_rep_id",
                        "l2_vocab_size": 21,
                    },
                    "multilabel_vocab_name": "label_vocab_l3_multilabel",
                    "multilabel_vocab_version": "PFO_v1.0.2_multilabel",
                    "multilabel_vocab_path": "outputs/label_vocab_l3_multilabel.json",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        pd.DataFrame(
            [
                {
                    "supervision_channel": "L3_multilabel",
                    "label_name": "Tail_spike",
                    "label_vocab_name": "label_vocab_l3_multilabel",
                    "label_vocab_version": "PFO_v1.0.2_multilabel",
                    "label_vocab_path": "outputs/label_vocab_l3_multilabel.json",
                    "split_version": "homology_cluster_v1",
                    "status": "trainable_multilabel",
                }
            ]
        ).to_parquet(
            repo_root / "data_processed" / "governance" / "pfo_v1_0_2_long_multilabel_ready.parquet",
            index=False,
        )
        pd.DataFrame([{"status": "trainable_multilabel"}]).to_csv(
            repo_root / "data_processed" / "governance" / "multilabel_task_table.csv",
            index=False,
        )
        (repo_root / "outputs" / "label_vocab_l3_multilabel.json").write_text(
            json.dumps({"Tail_spike": 0}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (repo_root / "baseline" / "governance_reader.py").write_text(
            textwrap.dedent(
                """
                def load_multilabel_rows():
                    return []

                def build_multilabel_targets():
                    return []

                def load_multilabel_vocab_contract():
                    return {}
                """
            ).strip(),
            encoding="utf-8",
        )
        (repo_root / "baseline" / "dataset.py").write_text(
            "from baseline.governance_reader import GovernanceReader\n",
            encoding="utf-8",
        )
        (repo_root / "baseline" / "train_config.full_stage2.yaml").write_text(
            "data:\n  target_status: trainable_core\n",
            encoding="utf-8",
        )
        (repo_root / "baseline" / "train.py").write_text("print('train entry')\n", encoding="utf-8")
        (repo_root / "baseline" / "train_multimodal.py").write_text(
            "print('multimodal entry')\n",
            encoding="utf-8",
        )

        return tmp_dir, repo_root

    def test_build_payload_includes_requested_context(self) -> None:
        tmp_dir, repo_root = self._build_audit_repo()
        self.addCleanup(tmp_dir.cleanup)

        args = governance_audit_module.parse_args.__globals__["argparse"].Namespace(
            repo_root=str(repo_root),
            format="json",
            config="baseline/train_config.full_stage2.yaml",
            split="homology_cluster_v1",
            governance_dir="data_processed/governance",
            vocab_path="outputs/label_vocab_l3_multilabel.json",
        )
        context = governance_audit_module.build_context(args)
        checks = governance_audit_module.audit(context)
        payload = governance_audit_module.build_payload(context, checks)

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["tool_name"], "governance-to-multilabel-audit")
        self.assertIn("check_groups", payload)
        self.assertEqual(payload["requested_context"]["split"], "homology_cluster_v1")
        self.assertEqual(payload["requested_context"]["config"], str((repo_root / "baseline" / "train_config.full_stage2.yaml").resolve()))
        self.assertTrue(any(item["name"] == "requested_split_exists" and item["status"] == "PASS" for item in payload["checks"]))

    def test_requested_split_absence_fails_fast_contract(self) -> None:
        tmp_dir, repo_root = self._build_audit_repo()
        self.addCleanup(tmp_dir.cleanup)

        args = governance_audit_module.parse_args.__globals__["argparse"].Namespace(
            repo_root=str(repo_root),
            format="json",
            config="baseline/train_config.full_stage2.yaml",
            split="unknown_split_v0",
            governance_dir="data_processed/governance",
            vocab_path="outputs/label_vocab_l3_multilabel.json",
        )
        context = governance_audit_module.build_context(args)
        checks = governance_audit_module.audit(context)
        by_name = {item.name: item for item in checks}

        self.assertEqual(by_name["governance_runtime_invariants"].status, "PASS")
        self.assertEqual(by_name["requested_split_exists"].status, "FAIL")
        self.assertEqual(by_name["requested_split_multilabel_coverage"].status, "FAIL")


class ResultsCloseoutTests(unittest.TestCase):
    def test_parse_args_accepts_json_format(self) -> None:
        with mock.patch.object(
            sys,
            "argv",
            [
                "results_closeout_lite.py",
                "--run-dir",
                "baseline/runs/example",
                "--format",
                "json",
                "--strict-required-artifacts",
            ],
        ):
            args = results_closeout_module.parse_args()

        self.assertEqual(args.format, "json")
        self.assertTrue(args.strict_required_artifacts)

    def test_closeout_brief_keeps_manual_decision_boundary(self) -> None:
        report = results_closeout_module.build_markdown(
            [
                {
                    "run_dir": "D:/runs/example",
                    "run_name": "example_run",
                    "variant": "seq_only",
                    "seed": 42,
                    "best_val_l3_macro_f1": 0.95,
                    "summary_timing_last_train": {"data_wait_ms": 12.0, "step_ms": 30.0},
                    "summary_timing_last_val": {"data_wait_ms": 3.0, "step_ms": None},
                    "train_last": {},
                    "val_last": {},
                    "metrics_val": {
                        "l1": {"macro_f1": 0.9},
                        "l2": {"macro_f1": 0.8},
                        "l3": {"macro_f1": 0.7},
                        "multilabel": {"num_samples": 512},
                        "mean_gates": {"sequence": 0.99, "structure": 0.005, "context": 0.005},
                    },
                    "metrics_test": {
                        "l1": {"macro_f1": 0.91},
                        "l2": {"macro_f1": 0.81},
                        "l3": {"macro_f1": 0.71},
                        "multilabel": {"num_samples": 512},
                        "mean_gates": {"sequence": 0.91, "structure": 0.05, "context": 0.04},
                    },
                    "missing_artifacts": ["evaluation/metrics_val.json"],
                    "gate_health": {
                        "status": "collapsed",
                        "val": {"status": "collapsed", "multilabel_num_samples": 512, "mean_gates": {"sequence": 0.99, "structure": 0.005, "context": 0.005}},
                        "test": {"status": "warning", "multilabel_num_samples": 512, "mean_gates": {"sequence": 0.91, "structure": 0.05, "context": 0.04}},
                    },
                }
            ]
        )

        self.assertIn("## 需人工判定", report)
        self.assertIn("missing_artifacts", report)
        self.assertIn("gate_health", report)
        self.assertIn("collapsed", report)
        self.assertIn("是否切默认、是否窗口升级、是否 promote/demote 需人工判定。", report)
        self.assertNotIn("promote this run", report)
        self.assertNotIn("default switch recommendation", report)

    def test_closeout_json_payload_keeps_manual_decision_boundary(self) -> None:
        payload = results_closeout_module.build_payload(
            [
                {
                    "run_dir": "D:/runs/example",
                    "run_name": "example_run",
                    "variant": "seq_only",
                    "seed": 42,
                    "best_val_l3_macro_f1": 0.95,
                    "summary_timing_last_train": {"data_wait_ms": 12.0, "step_ms": 30.0},
                    "summary_timing_last_val": {"data_wait_ms": 3.0, "step_ms": None},
                    "train_last": {},
                    "val_last": {},
                    "metrics_val": {
                        "multilabel": {"num_samples": 512},
                        "mean_gates": {"sequence": 0.9, "structure": 0.05, "context": 0.05},
                    },
                    "metrics_test": {
                        "multilabel": {"num_samples": 512},
                        "mean_gates": {"sequence": 0.91, "structure": 0.04, "context": 0.05},
                    },
                    "missing_artifacts": ["evaluation/metrics_val.json"],
                }
            ],
            strict_mode=False,
        )

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["tool_name"], "results-closeout-lite")
        self.assertEqual(payload["status"], "soft_missing")
        self.assertFalse(payload["strict_mode"])
        self.assertIn("scope", payload)
        self.assertIn("runs", payload)
        self.assertIn("manual_decision_required", payload)
        self.assertEqual(payload["runs"][0]["missing_artifacts"], ["evaluation/metrics_val.json"])
        self.assertEqual(payload["runs"][0]["gate_health"]["status"], "warning")
        self.assertTrue(payload["scope"]["read_only_artifact_extraction"])

    def test_closeout_json_payload_strict_mode_marks_failure(self) -> None:
        payload = results_closeout_module.build_payload(
            [
                {
                    "run_dir": "D:/runs/example",
                    "run_name": "example_run",
                    "variant": "seq_only",
                    "seed": 42,
                    "best_val_l3_macro_f1": 0.95,
                    "summary_timing_last_train": {},
                    "summary_timing_last_val": {},
                    "train_last": {},
                    "val_last": {},
                    "metrics_val": {},
                    "metrics_test": {},
                    "missing_artifacts": ["evaluation/metrics_val.json"],
                }
            ],
            strict_mode=True,
        )

        self.assertEqual(payload["status"], "strict_fail")
        self.assertTrue(payload["strict_mode"])


@unittest.skipUnless(PWSH, "pwsh is required for CLI smoke tests")
class WorkflowSkillCLISmokeTests(unittest.TestCase):
    def run_skill(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PWSH, "-File", str(REPO_ROOT / "skills" / "run-skill.ps1"), *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def extract_json_payload(self, stdout: str) -> dict[str, Any]:
        start = stdout.find("{")
        if start == -1:
            self.fail(f"Expected JSON payload in stdout, got: {stdout}")
        return json.loads(stdout[start:])

    def test_active_truth_help_smoke(self) -> None:
        proc = self.run_skill("active-truth-calibration", "--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--format {markdown,json}", proc.stdout)

    def test_results_closeout_help_smoke(self) -> None:
        proc = self.run_skill("results-closeout-lite", "--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--strict-required-artifacts", proc.stdout)

    def test_results_closeout_json_smoke(self) -> None:
        proc = self.run_skill(
            "results-closeout-lite",
            "--run-dir",
            "baseline/runs/baseline_l1_l2_l3core_engineering_final",
            "--format",
            "json",
        )
        self.assertEqual(proc.returncode, 0)
        payload = self.extract_json_payload(proc.stdout)
        self.assertEqual(payload["tool_name"], "results-closeout-lite")
        self.assertEqual(payload["status"], "soft_missing")

    def test_results_closeout_json_strict_smoke(self) -> None:
        proc = self.run_skill(
            "results-closeout-lite",
            "--run-dir",
            "baseline/runs/baseline_l1_l2_l3core_engineering_final",
            "--format",
            "json",
            "--strict-required-artifacts",
        )
        self.assertEqual(proc.returncode, 1)
        payload = self.extract_json_payload(proc.stdout)
        self.assertEqual(payload["status"], "strict_fail")
        self.assertTrue(payload["strict_mode"])

    def test_governance_audit_help_smoke(self) -> None:
        proc = self.run_skill("governance-to-multilabel-audit", "--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--governance-dir GOVERNANCE_DIR", proc.stdout)

    def test_governance_audit_default_split_smoke(self) -> None:
        proc = self.run_skill(
            "governance-to-multilabel-audit",
            "--format",
            "json",
            "--split",
            "homology_cluster_v1",
        )
        self.assertEqual(proc.returncode, 0)
        payload = self.extract_json_payload(proc.stdout)
        self.assertEqual(payload["tool_name"], "governance-to-multilabel-audit")
        self.assertEqual(payload["requested_context"]["split"], "homology_cluster_v1")

    def test_governance_audit_unknown_split_smoke(self) -> None:
        proc = self.run_skill(
            "governance-to-multilabel-audit",
            "--format",
            "json",
            "--split",
            "unknown_split_v0",
        )
        self.assertEqual(proc.returncode, 1)
        payload = self.extract_json_payload(proc.stdout)
        checks = {item["name"]: item for item in payload["checks"]}
        self.assertEqual(checks["governance_runtime_invariants"]["status"], "PASS")
        self.assertEqual(checks["requested_split_exists"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
