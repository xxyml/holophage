from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
import torch

from baseline.evaluate_multimodal import build_gate_health_summary, run_evaluation
from baseline.dataset_multimodal import MultimodalCoreDataset, multimodal_collate
from baseline.multimodal_v2.losses import HierarchicalMultimodalLoss
from baseline.multimodal_v2.model import MultimodalBaselineV2
from baseline.prepack_multimodal import limit_split_frame


class MultimodalMultilabelHeadWiringTests(unittest.TestCase):
    def _prediction_batch(self) -> dict[str, torch.Tensor | list[str]]:
        batch = [
            {
                "protein_id": "p1",
                "embedding_id": "e1",
                "exact_sequence_rep_id": "s1",
                "split": "val",
                "split_strategy": "exact_sequence_rep_id",
                "split_version": "test",
                "homology_cluster_id": "h1",
                "label_l1": torch.tensor(0),
                "label_l2": torch.tensor(1),
                "label_l3_core": torch.tensor(2),
                "has_l3_core": torch.tensor(True),
                "label_l3_core_mask": torch.tensor(True),
                "multilabel_target_mask": torch.tensor(False),
                "multilabel_label_ids": tuple(),
                "multilabel_label_count": torch.tensor(0),
                "multilabel_output_dim": 3,
                "multilabel_targets": torch.tensor([0.0, 0.0, 0.0]),
                "sequence_embedding": torch.randn(8),
                "structure_embedding": torch.zeros(4),
                "context_node_features": torch.zeros(1, 2),
                "context_adjacency": torch.eye(1, dtype=torch.bool),
                "context_node_mask": torch.tensor([True], dtype=torch.bool),
                "context_center_index": torch.tensor(0),
                "modality_mask": torch.tensor([True, False, False]),
                "sequence_length": torch.tensor(10),
            },
            {
                "protein_id": "p2",
                "embedding_id": "e2",
                "exact_sequence_rep_id": "s2",
                "split": "val",
                "split_strategy": "exact_sequence_rep_id",
                "split_version": "test",
                "homology_cluster_id": "h2",
                "label_l1": torch.tensor(0),
                "label_l2": torch.tensor(1),
                "label_l3_core": torch.tensor(2),
                "has_l3_core": torch.tensor(True),
                "label_l3_core_mask": torch.tensor(True),
                "multilabel_target_mask": torch.tensor(True),
                "multilabel_label_ids": (1,),
                "multilabel_label_count": torch.tensor(1),
                "multilabel_output_dim": 3,
                "multilabel_targets": torch.tensor([0.0, 1.0, 0.0]),
                "sequence_embedding": torch.randn(8),
                "structure_embedding": torch.zeros(4),
                "context_node_features": torch.zeros(1, 2),
                "context_adjacency": torch.eye(1, dtype=torch.bool),
                "context_node_mask": torch.tensor([True], dtype=torch.bool),
                "context_center_index": torch.tensor(0),
                "modality_mask": torch.tensor([True, False, False]),
                "sequence_length": torch.tensor(12),
            },
        ]
        return multimodal_collate(batch)

    def test_model_emits_multilabel_logits_when_enabled(self) -> None:
        model = MultimodalBaselineV2(
            sequence_input_dim=8,
            structure_input_dim=4,
            context_input_dim=3,
            context_graph_node_dim=2,
            fusion_dim=6,
            adapter_hidden_dim=5,
            trunk_hidden_dim=6,
            trunk_hidden_dim2=4,
            dropout=0.0,
            modality_dropout=0.0,
            preserve_sequence=True,
            context_mode="handcrafted",
            context_gnn_hidden_dim=4,
            context_gnn_output_dim=4,
            context_center_residual=False,
            num_l1=3,
            num_l2=4,
            num_l3=5,
            num_multilabel=7,
            use_sequence=True,
            use_structure=False,
            use_context=False,
        )
        outputs = model(
            sequence_embedding=torch.randn(2, 8),
            structure_embedding=torch.zeros(2, 4),
            context_features=torch.zeros(2, 3),
            modality_mask=torch.tensor([[True, False, False], [True, False, False]]),
        )
        self.assertIn("logits_multilabel", outputs)
        self.assertEqual(tuple(outputs["logits_multilabel"].shape), (2, 7))

    def test_loss_masks_l3_and_multilabel_rows(self) -> None:
        criterion = HierarchicalMultimodalLoss(weight_multilabel=1.0)
        loss = criterion(
            logits_l1=torch.randn(2, 3),
            logits_l2=torch.randn(2, 4),
            logits_l3=torch.randn(2, 5),
            target_l1=torch.tensor([0, 1]),
            target_l2=torch.tensor([1, 2]),
            target_l3=torch.tensor([2, -100]),
            target_l3_mask=torch.tensor([True, False]),
            logits_multilabel=torch.tensor([[2.0, -2.0], [0.0, 0.0]]),
            multilabel_targets=torch.tensor([[1.0, 0.0], [0.0, 1.0]]),
            multilabel_target_mask=torch.tensor([False, True]),
        )
        self.assertGreater(float(loss.multilabel), 0.0)

    def test_gate_entropy_penalty_is_positive_for_collapsed_gates(self) -> None:
        criterion = HierarchicalMultimodalLoss(gate_entropy_loss_weight=1.0)
        loss = criterion(
            logits_l1=torch.randn(2, 3),
            logits_l2=torch.randn(2, 4),
            logits_l3=torch.randn(2, 5),
            target_l1=torch.tensor([0, 1]),
            target_l2=torch.tensor([1, 2]),
            target_l3=torch.tensor([2, 3]),
            fusion_gates=torch.tensor([[0.999, 0.001, 0.0], [0.998, 0.002, 0.0]], dtype=torch.float32),
            fusion_gate_mask=torch.tensor([[True, True, False], [True, True, False]]),
        )
        self.assertGreater(float(loss.gate_regularization), 0.5)

    def test_gate_load_balance_penalty_is_positive_for_skewed_batch_mean(self) -> None:
        criterion = HierarchicalMultimodalLoss(gate_load_balance_loss_weight=1.0)
        loss = criterion(
            logits_l1=torch.randn(2, 3),
            logits_l2=torch.randn(2, 4),
            logits_l3=torch.randn(2, 5),
            target_l1=torch.tensor([0, 1]),
            target_l2=torch.tensor([1, 2]),
            target_l3=torch.tensor([2, 3]),
            fusion_gates=torch.tensor([[0.95, 0.04, 0.01], [0.97, 0.02, 0.01]], dtype=torch.float32),
            fusion_gate_mask=torch.tensor([[True, True, True], [True, True, True]]),
        )
        self.assertGreater(float(loss.gate_load_balance), 0.1)

    def test_collate_builds_dense_multilabel_targets(self) -> None:
        batch = [
            {
                "label_l1": torch.tensor(0),
                "label_l2": torch.tensor(1),
                "label_l3_core": torch.tensor(2),
                "has_l3_core": torch.tensor(True),
                "label_l3_core_mask": torch.tensor(True),
                "multilabel_target_mask": torch.tensor(False),
                "multilabel_label_ids": tuple(),
                "multilabel_label_count": torch.tensor(0),
                "multilabel_output_dim": 4,
                "sequence_embedding": torch.randn(8),
                "structure_embedding": torch.zeros(4),
                "context_node_features": torch.zeros(0, 0),
                "context_adjacency": torch.zeros(0, 0, dtype=torch.bool),
                "context_node_mask": torch.zeros(0, dtype=torch.bool),
                "context_center_index": torch.tensor(0),
                "modality_mask": torch.tensor([True, False, False]),
                "sequence_length": torch.tensor(10),
            },
            {
                "label_l1": torch.tensor(0),
                "label_l2": torch.tensor(1),
                "label_l3_core": torch.tensor(-100),
                "has_l3_core": torch.tensor(False),
                "label_l3_core_mask": torch.tensor(False),
                "multilabel_target_mask": torch.tensor(True),
                "multilabel_label_ids": (1, 3),
                "multilabel_label_count": torch.tensor(2),
                "multilabel_output_dim": 4,
                "sequence_embedding": torch.randn(8),
                "structure_embedding": torch.zeros(4),
                "context_node_features": torch.zeros(0, 0),
                "context_adjacency": torch.zeros(0, 0, dtype=torch.bool),
                "context_node_mask": torch.zeros(0, dtype=torch.bool),
                "context_center_index": torch.tensor(0),
                "modality_mask": torch.tensor([True, False, False]),
                "sequence_length": torch.tensor(12),
            },
        ]
        collated = multimodal_collate(batch)
        self.assertIn("multilabel_targets", collated)
        self.assertEqual(tuple(collated["multilabel_targets"].shape), (2, 4))
        self.assertEqual(collated["multilabel_targets"][1].tolist(), [0.0, 1.0, 0.0, 1.0])

    def test_hierarchy_maps_skip_non_core_rows(self) -> None:
        dataset = MultimodalCoreDataset.__new__(MultimodalCoreDataset)
        dataset.sequence_row_idx = torch.arange(2, dtype=torch.long)
        dataset.label_l1 = torch.tensor([0, 0], dtype=torch.long)
        dataset.label_l2 = torch.tensor([1, 1], dtype=torch.long)
        dataset.label_l3_core = torch.tensor([2, -100], dtype=torch.long)
        dataset.label_l3_core_mask = torch.tensor([True, False], dtype=torch.bool)
        l3_to_l2, l2_to_l1 = dataset.hierarchy_maps(num_l1=2, num_l2=3, num_l3=4)
        self.assertEqual(int(l3_to_l2[2].item()), 1)
        self.assertEqual(int(l2_to_l1[1].item()), 0)

    def test_limit_split_frame_preserves_multilabel_coverage(self) -> None:
        frame = pd.DataFrame(
            {
                "protein_id": [f"p{i}" for i in range(8)],
                "status": [
                    "trainable_core",
                    "trainable_core",
                    "trainable_core",
                    "trainable_core",
                    "trainable_core",
                    "trainable_multilabel",
                    "trainable_multilabel",
                    "trainable_multilabel",
                ],
            }
        )
        limited = limit_split_frame(frame, limit=4, supervision_mode="core_plus_multilabel")
        counts = limited["status"].value_counts().to_dict()
        self.assertEqual(len(limited), 4)
        self.assertIn("trainable_multilabel", counts)
        self.assertIn("trainable_core", counts)

    def test_model_allows_sequence_dropout_when_preserve_sequence_disabled(self) -> None:
        model = MultimodalBaselineV2(
            sequence_input_dim=8,
            structure_input_dim=4,
            context_input_dim=3,
            context_graph_node_dim=2,
            fusion_dim=6,
            adapter_hidden_dim=5,
            trunk_hidden_dim=6,
            trunk_hidden_dim2=4,
            dropout=0.0,
            modality_dropout=1.0,
            preserve_sequence=False,
            context_mode="handcrafted",
            context_gnn_hidden_dim=4,
            context_gnn_output_dim=4,
            context_center_residual=False,
            num_l1=3,
            num_l2=4,
            num_l3=5,
            num_multilabel=0,
            use_sequence=True,
            use_structure=True,
            use_context=False,
        )
        model.train()
        dropped = model.modality_dropout(torch.tensor([[True, True, False], [True, True, False]]))
        self.assertFalse(bool(dropped[:, 0].any().item()))

    def test_gate_health_summary_marks_sequence_only_collapse(self) -> None:
        summary = build_gate_health_summary(
            {
                "mean_gates": {
                    "sequence": 0.99,
                    "structure": 0.005,
                    "context": 0.005,
                },
                "multilabel": {
                    "num_samples": 512,
                },
            }
        )
        self.assertEqual(summary["status"], "collapsed")
        self.assertIn("sequence_only_collapse", summary["reason_codes"])

    def test_gate_health_summary_warns_when_multilabel_samples_missing(self) -> None:
        summary = build_gate_health_summary(
            {
                "mean_gates": {
                    "sequence": 0.62,
                    "structure": 0.2,
                    "context": 0.18,
                },
                "multilabel": {
                    "num_samples": 0,
                },
            }
        )
        self.assertEqual(summary["status"], "warning")
        self.assertIn("multilabel_num_samples_zero", summary["reason_codes"])

    def test_run_evaluation_exports_dual_output_for_all_rows_but_keeps_masked_metrics(self) -> None:
        batch = self._prediction_batch()

        class _Loader:
            def __init__(self, single_batch: dict[str, torch.Tensor | list[str]]) -> None:
                self.dataset = object()
                self._batch = single_batch

            def __iter__(self):
                yield self._batch

            def __len__(self) -> int:
                return 1

        class _FakeModel(torch.nn.Module):
            def forward(self, **kwargs):
                return {
                    "logits_l1": torch.tensor([[4.0, 0.0], [4.0, 0.0]], dtype=torch.float32),
                    "logits_l2": torch.tensor([[0.0, 4.0], [0.0, 4.0]], dtype=torch.float32),
                    "logits_l3": torch.tensor([[0.0, 0.0, 4.0], [0.0, 0.0, 4.0]], dtype=torch.float32),
                    "logits_multilabel": torch.tensor([[2.0, -0.2, -1.0], [-2.0, 2.0, 0.8]], dtype=torch.float32),
                    "fusion_gates": torch.tensor([[0.6, 0.2, 0.2], [0.5, 0.25, 0.25]], dtype=torch.float32),
                    "features": torch.zeros((2, 4), dtype=torch.float32),
                    "timing": {"context_gnn_ms": 0.0},
                }

        with tempfile.TemporaryDirectory() as tmp_dir:
            metrics = run_evaluation(
                model=_FakeModel(),
                dataloader=_Loader(batch),
                device=torch.device("cpu"),
                export_dir=Path(tmp_dir),
                split_name="val",
                topk=2,
                export_embeddings=False,
                export_mode="full_export",
                pin_memory_mode="false",
            )
            predictions = pd.read_csv(Path(tmp_dir) / "predictions_val.csv")

        self.assertEqual(metrics["multilabel"]["num_samples"], 1)
        self.assertEqual(metrics["dual_output"]["protocol"], "dual_output_without_selector")
        self.assertTrue(bool(metrics["dual_output"]["multilabel_head_present"]))
        self.assertEqual(int(metrics["dual_output"]["exported_prediction_rows"]), 2)
        self.assertIn("multilabel_positive_indices", predictions.columns)
        self.assertIn("multilabel_topk_scores", predictions.columns)
        self.assertIn("multilabel_active_for_metrics", predictions.columns)
        self.assertEqual(str(predictions.loc[0, "multilabel_positive_indices"]), "0")
        self.assertEqual(str(predictions.loc[1, "multilabel_positive_indices"]), "1,2")
        self.assertEqual(bool(predictions.loc[0, "multilabel_active_for_metrics"]), False)
        self.assertEqual(bool(predictions.loc[1, "multilabel_active_for_metrics"]), True)


if __name__ == "__main__":
    unittest.main()
