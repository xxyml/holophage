from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader, Dataset

from baseline.common import (
    DataLoaderWithFallback,
    REPO_ROOT,
    apply_active_runtime_paths,
    dump_json,
    ensure_dir,
    gpu_peak_memory_stats,
    load_vocab,
    load_yaml,
    print_runtime_paths,
    reset_gpu_peak_memory,
    resolve_path,
    resolve_runtime_paths,
    validate_paths_exist,
    validate_runtime_contract,
)
from baseline.multimodal_v2.model import MultimodalBaselineV2
from baseline.dataset_multimodal import MultimodalCoreDataset, multimodal_collate
from baseline.multimodal_v2.types import (
    CONTEXT_FEATURE_DIM,
    CONTEXT_GRAPH_NODE_FEATURE_DIM,
    DEFAULT_SEQUENCE_EMBEDDING_DIM,
    DEFAULT_STRUCTURE_EMBEDDING_DIM,
)


@dataclass(frozen=True)
class MultimodalAssets:
    prepacked_dir: Path
    structure_embedding_dir: Path | None
    context_feature_table: Path | None
    context_mode: str
    split_override_csv: Path | None


def load_prepack_summary(prepacked_dir: Path) -> dict[str, Any]:
    summary_path = prepacked_dir / "summary.json"
    if not summary_path.exists():
        return {
            "prepacked_dir": str(prepacked_dir),
            "summary_path": str(summary_path),
            "storage_layout": "unknown",
            "schema_version": "unknown",
        }
    summary = load_yaml(summary_path)
    return {
        "prepacked_dir": str(prepacked_dir),
        "summary_path": str(summary_path),
        "storage_layout": str(summary.get("storage_layout", "unknown")),
        "schema_version": str(summary.get("schema_version", "unknown")),
        "pack_bytes_total": int(summary.get("pack_bytes_total", 0) or 0),
    }


def print_multimodal_runtime_banner(config: dict[str, Any], assets: MultimodalAssets, prepack_summary: dict[str, Any]) -> None:
    multimodal_cfg = config.get("multimodal", {}) or {}
    print("[runtime][multimodal] resolved multimodal prepack:")
    print(f"[runtime][multimodal]   variant: {str(multimodal_cfg.get('variant', 'multimodal_v2'))}")
    print(f"[runtime][multimodal]   effective_prepacked_dir: {assets.prepacked_dir}")
    print(f"[runtime][multimodal]   storage_layout: {prepack_summary.get('storage_layout', 'unknown')}")
    print(f"[runtime][multimodal]   schema_version: {prepack_summary.get('schema_version', 'unknown')}")
    print(f"[runtime][multimodal]   summary_path: {prepack_summary.get('summary_path', 'unknown')}")
    print(f"[runtime][multimodal]   modalities: {multimodal_cfg.get('modalities', {}) or {}}")


def resolve_dataset_from_loader(dataloader: DataLoader) -> Any:
    dataset = getattr(dataloader, "dataset", None)
    if dataset is not None:
        return dataset
    inner_loader = getattr(dataloader, "_loader", None)
    if inner_loader is not None:
        return getattr(inner_loader, "dataset", None)
    return None


def resolve_inner_loader(dataloader: DataLoader) -> Any:
    return getattr(dataloader, "_loader", dataloader)


def resolve_pin_memory(config: dict[str, Any], device: torch.device) -> bool:
    training_cfg = config.get("training", {}) or {}
    override = training_cfg.get("pin_memory_override")
    if override is None:
        return bool(device.type == "cuda")
    return bool(override)


def resolve_pin_memory_mode(config: dict[str, Any]) -> str:
    training_cfg = config.get("training", {}) or {}
    override = training_cfg.get("pin_memory_override")
    if override is None:
        return "auto"
    return "true" if bool(override) else "false"


def start_cuda_timing(device: torch.device) -> tuple[torch.cuda.Event | None, torch.cuda.Event | None]:
    if device.type != "cuda":
        return None, None
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    return start, end


def finish_cuda_timing(start: torch.cuda.Event | None, end: torch.cuda.Event | None) -> float:
    if start is None or end is None:
        return 0.0
    end.synchronize()
    return float(start.elapsed_time(end))


def choose_device(device_name: str) -> torch.device:
    if device_name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(device_name)


def resolve_assets(config: dict[str, Any]) -> MultimodalAssets:
    assets = (config.get("multimodal", {}) or {}).get("assets", {}) or {}
    prepacked_dir = assets.get("prepacked_dir")
    if not prepacked_dir:
        raise ValueError("multimodal.assets.prepacked_dir must be configured.")
    structure_dir = assets.get("structure_embedding_dir")
    context_table = assets.get("context_feature_table")
    context_mode = str(assets.get("context_mode", "handcrafted"))
    split_override_csv = assets.get("split_override_csv")
    return MultimodalAssets(
        prepacked_dir=resolve_path(prepacked_dir, REPO_ROOT),
        structure_embedding_dir=None if not structure_dir else resolve_path(structure_dir, REPO_ROOT),
        context_feature_table=None if not context_table else resolve_path(context_table, REPO_ROOT),
        context_mode=context_mode,
        split_override_csv=None if not split_override_csv else resolve_path(split_override_csv, REPO_ROOT),
    )


def validate_support_assets(config: dict[str, Any], assets: MultimodalAssets) -> None:
    modalities = (config.get("multimodal", {}) or {}).get("modalities", {}) or {}
    required = {"prepacked_dir": assets.prepacked_dir}
    if bool(modalities.get("structure", False)):
        if assets.structure_embedding_dir is None:
            raise ValueError("multimodal.structure=true but structure_embedding_dir is missing.")
        required["structure_embedding_dir"] = assets.structure_embedding_dir
    if bool(modalities.get("context", False)):
        if assets.context_feature_table is None:
            raise ValueError("multimodal.context=true but context_feature_table is missing.")
        required["context_feature_table"] = assets.context_feature_table
    if assets.split_override_csv is not None:
        required["split_override_csv"] = assets.split_override_csv
    validate_paths_exist(required)


def build_model(config: dict[str, Any], dataset: MultimodalCoreDataset, vocab_sizes: tuple[int, int, int]) -> MultimodalBaselineV2:
    model_cfg = (config.get("multimodal", {}) or {}).get("model", {}) or {}
    modalities = (config.get("multimodal", {}) or {}).get("modalities", {}) or {}
    multilabel_cfg = (config.get("multilabel_head", {}) or {})
    num_l1, num_l2, num_l3 = vocab_sizes
    use_sequence = bool(modalities.get("sequence", True))
    use_structure = bool(modalities.get("structure", False))
    use_context = bool(modalities.get("context", False))
    return MultimodalBaselineV2(
        sequence_input_dim=int(getattr(dataset, "sequence_embedding").shape[1] if len(dataset) else DEFAULT_SEQUENCE_EMBEDDING_DIM),
        structure_input_dim=int(
            getattr(dataset, "structure_embedding").shape[1]
            if use_structure and len(dataset) and getattr(dataset, "structure_embedding").shape[1] > 0
            else DEFAULT_STRUCTURE_EMBEDDING_DIM
        ),
        context_input_dim=int(
            getattr(dataset, "context_features").shape[1]
            if use_context and len(dataset) and getattr(dataset, "context_features").shape[1] > 0
            else CONTEXT_FEATURE_DIM
        ),
        context_graph_node_dim=int(
            getattr(dataset, "context_node_features").shape[2]
            if use_context and len(dataset) and getattr(dataset, "context_node_features").ndim == 3 and getattr(dataset, "context_node_features").shape[2] > 0
            else CONTEXT_GRAPH_NODE_FEATURE_DIM
        ),
        fusion_dim=int(model_cfg.get("fusion_dim", 512)),
        adapter_hidden_dim=int(model_cfg.get("branch_hidden_dim", 256)),
        trunk_hidden_dim=int(model_cfg.get("trunk_hidden_dim", 512)),
        trunk_hidden_dim2=int(model_cfg.get("trunk_hidden_dim2", model_cfg.get("trunk_hidden_dim", 512))),
        dropout=float(model_cfg.get("dropout", 0.1)),
        modality_dropout=float(model_cfg.get("modality_dropout", 0.1)),
        preserve_sequence=bool(model_cfg.get("preserve_sequence", True)),
        context_mode=str((config.get("multimodal", {}) or {}).get("assets", {}).get("context_mode", "handcrafted")),
        context_gnn_hidden_dim=int(model_cfg.get("context_gnn_hidden_dim", 128)),
        context_gnn_output_dim=int(model_cfg.get("context_gnn_output_dim", 128)),
        context_center_residual=bool(model_cfg.get("context_center_residual", False)),
        num_l1=num_l1,
        num_l2=num_l2,
        num_l3=num_l3,
        num_multilabel=int(dataset.multilabel_output_dim if bool(multilabel_cfg.get("enabled", False)) else 0),
        use_sequence=use_sequence,
        use_structure=use_structure,
        use_context=use_context,
    )


def make_dataloader(
    dataset: MultimodalCoreDataset,
    batch_size: int,
    num_workers: int,
    pin_memory: bool = False,
    include_metadata: bool = False,
    include_runtime_metadata: bool = False,
) -> DataLoader:
    dataset.include_metadata = bool(include_metadata)
    dataset.include_runtime_metadata = bool(include_runtime_metadata)
    def _factory(active_workers: int) -> DataLoader:
        dataloader_kwargs = {
            "dataset": dataset,
            "batch_size": batch_size,
            "shuffle": False,
            "num_workers": active_workers,
            "pin_memory": pin_memory,
            "collate_fn": multimodal_collate,
        }
        if active_workers > 0:
            dataloader_kwargs["persistent_workers"] = True
            dataloader_kwargs["prefetch_factor"] = 4
        return DataLoader(**dataloader_kwargs)

    return DataLoaderWithFallback(_factory, num_workers=num_workers, label="multimodal-eval-loader")


def hierarchy_violation_rate(
    pred_l1: list[int],
    pred_l2: list[int],
    pred_l3: list[int],
    l3_to_l2: torch.Tensor | None,
    l2_to_l1: torch.Tensor | None,
) -> float:
    if not pred_l1 or l3_to_l2 is None or l2_to_l1 is None:
        return 0.0
    violations = 0
    checked = 0
    for a, b, c in zip(pred_l1, pred_l2, pred_l3):
        if c >= len(l3_to_l2) or b >= len(l2_to_l1):
            continue
        implied_l2 = int(l3_to_l2[c])
        implied_l1 = int(l2_to_l1[b])
        if implied_l2 < 0 or implied_l1 < 0:
            continue
        checked += 1
        if implied_l2 != b or implied_l1 != a:
            violations += 1
    return 0.0 if checked == 0 else violations / checked


def _update_confusion(confusion: torch.Tensor, targets: torch.Tensor, preds: torch.Tensor) -> None:
    num_classes = confusion.shape[0]
    flat = targets.to(torch.int64) * num_classes + preds.to(torch.int64)
    counts = torch.bincount(flat, minlength=num_classes * num_classes)
    confusion += counts.reshape(num_classes, num_classes)


def _metrics_from_confusion(confusion: torch.Tensor) -> dict[str, float]:
    matrix = confusion.to(dtype=torch.float64)
    total = float(matrix.sum().item())
    accuracy = 0.0 if total == 0.0 else float(torch.trace(matrix).item() / total)
    true_count = matrix.sum(dim=1)
    pred_count = matrix.sum(dim=0)
    denom = true_count + pred_count
    tp = torch.diag(matrix)
    f1 = torch.zeros_like(tp)
    valid = denom > 0
    f1[valid] = (2.0 * tp[valid]) / denom[valid]
    active = (true_count + pred_count) > 0
    macro_f1 = 0.0 if not bool(active.any()) else float(f1[active].mean().item())
    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
    }


def _update_gate_aggregates(
    aggregates: dict[int, dict[str, Any]],
    targets: torch.Tensor,
    gates: torch.Tensor,
) -> None:
    target_list = targets.tolist()
    gate_cpu = gates.detach().cpu().double()
    for idx, target in enumerate(target_list):
        bucket = aggregates.setdefault(int(target), {"sum": torch.zeros(3, dtype=torch.float64), "count": 0})
        bucket["sum"] += gate_cpu[idx]
        bucket["count"] += 1


def _gate_aggregate_to_frame(aggregates: dict[int, dict[str, Any]], label_name: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for target, stats in sorted(aggregates.items()):
        count = int(stats["count"])
        if count <= 0:
            continue
        mean_gate = stats["sum"] / count
        rows.append(
            {
                label_name: int(target),
                "gate_sequence": float(mean_gate[0]),
                "gate_structure": float(mean_gate[1]),
                "gate_context": float(mean_gate[2]),
            }
        )
    return pd.DataFrame(rows)


def build_gate_health_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    thresholds = {
        "collapsed_sequence_gte": 0.95,
        "collapsed_structure_lte": 0.03,
        "collapsed_context_lte": 0.03,
        "warning_sequence_gte": 0.85,
    }
    mean_gates_raw = metrics.get("mean_gates") if isinstance(metrics, dict) else {}
    mean_gates = mean_gates_raw if isinstance(mean_gates_raw, dict) else {}
    multilabel_raw = metrics.get("multilabel") if isinstance(metrics, dict) else {}
    multilabel = multilabel_raw if isinstance(multilabel_raw, dict) else {}

    sequence = float(mean_gates.get("sequence", 0.0) or 0.0)
    structure = float(mean_gates.get("structure", 0.0) or 0.0)
    context = float(mean_gates.get("context", 0.0) or 0.0)
    multilabel_num_samples = int(multilabel.get("num_samples", 0) or 0)

    status = "healthy"
    reason_codes: list[str] = []
    if multilabel_num_samples <= 0:
        status = "warning"
        reason_codes.append("multilabel_num_samples_zero")
    if (
        sequence >= thresholds["collapsed_sequence_gte"]
        and structure <= thresholds["collapsed_structure_lte"]
        and context <= thresholds["collapsed_context_lte"]
    ):
        status = "collapsed"
        reason_codes.append("sequence_only_collapse")
    elif sequence >= thresholds["warning_sequence_gte"]:
        if status != "collapsed":
            status = "warning"
        reason_codes.append("sequence_dominant")

    return {
        "status": status,
        "mean_gates": {
            "sequence": sequence,
            "structure": structure,
            "context": context,
        },
        "multilabel_num_samples": multilabel_num_samples,
        "reason_codes": reason_codes,
        "thresholds": thresholds,
    }


def _format_index_list(indices: list[int]) -> str:
    return ",".join(str(int(item)) for item in indices)


def _format_score_list(values: list[float]) -> str:
    return ",".join(f"{float(item):.6f}" for item in values)


@torch.no_grad()
def run_evaluation(
    model: MultimodalBaselineV2,
    dataloader: DataLoader,
    device: torch.device,
    export_dir: Path | None = None,
    split_name: str = "val",
    topk: int = 3,
    export_embeddings: bool = False,
    l3_to_l2: torch.Tensor | None = None,
    l2_to_l1: torch.Tensor | None = None,
    export_mode: str | None = None,
    pin_memory_mode: str = "auto",
) -> dict[str, Any]:
    model.eval()
    reset_gpu_peak_memory(device)
    dataset = resolve_dataset_from_loader(dataloader)
    inner_loader = resolve_inner_loader(dataloader)
    if dataset is not None and hasattr(dataset, "reset_runtime_stats"):
        dataset.reset_runtime_stats()
    export_mode = export_mode or ("full_export" if export_dir is not None else "metrics_only")
    if export_mode not in {"metrics_only", "full_export"}:
        raise ValueError(f"Unsupported export_mode: {export_mode}")
    export_full_artifacts = export_mode == "full_export"
    confusion: dict[str, torch.Tensor] | None = None
    embedding_rows = []
    gate_sums = torch.zeros(3, dtype=torch.float64)
    gate_batches = 0
    hierarchy_violations = 0
    hierarchy_checked = 0
    write_predictions = export_dir is not None and export_full_artifacts
    collect_artifacts = write_predictions or export_embeddings
    gate_by_l1: dict[int, dict[str, Any]] = {}
    gate_by_l3: dict[int, dict[str, Any]] = {}
    multilabel_targets_batches: list[np.ndarray] = []
    multilabel_pred_batches: list[np.ndarray] = []
    dual_output_prediction_rows = 0
    multilabel_head_present = False
    predictions_path: Path | None = None
    write_header = True
    timing = {
        "data_wait_ms": 0.0,
        "dataloader_next_ms": 0.0,
        "batch_from_indices_ms": 0.0,
        "host_prepare_ms": 0.0,
        "h2d_submit_ms": 0.0,
        "h2d_cuda_ms": 0.0,
        "h2d_ms": 0.0,
        "forward_ms": 0.0,
        "metric_agg_ms": 0.0,
        "artifact_write_ms": 0.0,
        "context_gnn_ms": 0.0,
    }
    last_batch_end = perf_counter()
    pin_memory_probe: dict[str, Any] | None = None

    if export_dir is not None:
        ensure_dir(export_dir)
        predictions_path = export_dir / f"predictions_{split_name}.csv"
        if predictions_path.exists():
            predictions_path.unlink()

    batch_iter = iter(dataloader)
    while True:
        next_start = perf_counter()
        try:
            batch = next(batch_iter)
        except StopIteration:
            break
        batch_ready = perf_counter()
        timing["dataloader_next_ms"] += (batch_ready - next_start) * 1000.0
        timing["data_wait_ms"] += (batch_ready - last_batch_end) * 1000.0
        host_prepare_start = perf_counter()
        if pin_memory_probe is None:
            pin_memory_probe = {
                "pin_memory_requested": bool(getattr(inner_loader, "pin_memory", False)),
                "pin_memory_effective": {
                    "sequence_embedding": bool(getattr(batch["sequence_embedding"], "is_pinned", lambda: False)()),
                    "context_node_features": bool(getattr(batch["context_node_features"], "is_pinned", lambda: False)()),
                    "context_adjacency": bool(getattr(batch["context_adjacency"], "is_pinned", lambda: False)()),
                    "context_node_mask": bool(getattr(batch["context_node_mask"], "is_pinned", lambda: False)()),
                },
            }
        timing["host_prepare_ms"] += (perf_counter() - host_prepare_start) * 1000.0
        forward_start = perf_counter()
        h2d_start = perf_counter()
        h2d_event_start, h2d_event_end = start_cuda_timing(device)
        sequence_embedding = batch["sequence_embedding"].to(device=device, non_blocking=True)
        structure_embedding = batch["structure_embedding"].to(device=device, non_blocking=True)
        context_features = batch.get("context_features")
        if context_features is not None:
            context_features = context_features.to(device=device, non_blocking=True)
        context_node_features = batch["context_node_features"].to(device=device, non_blocking=True)
        context_adjacency = batch["context_adjacency"].to(device=device, non_blocking=True)
        context_node_mask = batch["context_node_mask"].to(device, non_blocking=True)
        context_center_index = batch["context_center_index"].to(device, non_blocking=True)
        modality_mask = batch["modality_mask"].to(device, non_blocking=True)
        if h2d_event_end is not None:
            h2d_event_end.record()
        h2d_submit_ms = (perf_counter() - h2d_start) * 1000.0
        timing["h2d_submit_ms"] += h2d_submit_ms
        timing["h2d_ms"] += h2d_submit_ms
        sequence_embedding = sequence_embedding.float()
        structure_embedding = structure_embedding.float()
        if context_features is not None:
            context_features = context_features.float()
        context_node_features = context_node_features.float()
        outputs = model(
            sequence_embedding=sequence_embedding,
            structure_embedding=structure_embedding,
            context_features=context_features,
            context_node_features=context_node_features,
            context_adjacency=context_adjacency,
            context_node_mask=context_node_mask,
            context_center_index=context_center_index,
            modality_mask=modality_mask,
        )
        timing["forward_ms"] += (perf_counter() - forward_start) * 1000.0
        timing["h2d_cuda_ms"] += finish_cuda_timing(h2d_event_start, h2d_event_end)
        timing["context_gnn_ms"] += float((outputs.get("timing") or {}).get("context_gnn_ms", 0.0))
        metric_agg_start = perf_counter()
        logits_map = {
            "l1": outputs["logits_l1"],
            "l2": outputs["logits_l2"],
            "l3": outputs["logits_l3"],
        }
        target_l3_mask = batch.get("label_l3_core_mask")
        if target_l3_mask is None:
            target_l3_mask = torch.ones_like(batch["label_l3_core"], dtype=torch.bool)
        target_l3_mask = target_l3_mask.bool().cpu()
        target_map = {
            "l1": batch["label_l1"].cpu(),
            "l2": batch["label_l2"].cpu(),
            "l3": batch["label_l3_core"].cpu(),
        }
        pred_map = {key: torch.argmax(logits, dim=-1).cpu() for key, logits in logits_map.items()}
        if confusion is None:
            confusion = {
                key: torch.zeros((logits.shape[1], logits.shape[1]), dtype=torch.int64)
                for key, logits in logits_map.items()
            }
        for key in ("l1", "l2", "l3"):
            if key == "l3":
                active = target_l3_mask
                if bool(active.any()):
                    _update_confusion(confusion[key], target_map[key][active], pred_map[key][active])
                continue
            _update_confusion(confusion[key], target_map[key], pred_map[key])

        if outputs.get("logits_multilabel") is not None and "multilabel_targets" in batch:
            multilabel_head_present = True
            multilabel_active = batch.get("multilabel_target_mask")
            if multilabel_active is None:
                multilabel_active = torch.ones((batch["multilabel_targets"].shape[0],), dtype=torch.bool)
            multilabel_active = multilabel_active.bool().cpu()
            if bool(multilabel_active.any()):
                pred_ml = (torch.sigmoid(outputs["logits_multilabel"]).cpu() >= 0.5).to(dtype=torch.int64)
                true_ml = batch["multilabel_targets"].cpu().to(dtype=torch.int64)
                multilabel_pred_batches.append(pred_ml[multilabel_active].numpy())
                multilabel_targets_batches.append(true_ml[multilabel_active].numpy())

        gate_sums += outputs["fusion_gates"].detach().cpu().double().mean(dim=0)
        gate_batches += 1
        if write_predictions:
            _update_gate_aggregates(gate_by_l1, target_map["l1"], outputs["fusion_gates"])
            _update_gate_aggregates(gate_by_l3, target_map["l3"], outputs["fusion_gates"])

        if l3_to_l2 is not None and l2_to_l1 is not None:
            pred_l1 = pred_map["l1"]
            pred_l2 = pred_map["l2"]
            pred_l3 = pred_map["l3"]
            valid = target_l3_mask & (pred_l3 < len(l3_to_l2)) & (pred_l2 < len(l2_to_l1))
            if bool(valid.any()):
                implied_l2 = l3_to_l2[pred_l3[valid]]
                implied_l1 = l2_to_l1[pred_l2[valid]]
                valid_maps = (implied_l2 >= 0) & (implied_l1 >= 0)
                if bool(valid_maps.any()):
                    checked_l1 = pred_l1[valid][valid_maps]
                    checked_l2 = pred_l2[valid][valid_maps]
                    implied_l1 = implied_l1[valid_maps]
                    implied_l2 = implied_l2[valid_maps]
                    hierarchy_checked += int(valid_maps.sum().item())
                    hierarchy_violations += int(((checked_l2 != implied_l2) | (checked_l1 != implied_l1)).sum().item())
        timing["metric_agg_ms"] += (perf_counter() - metric_agg_start) * 1000.0

        if collect_artifacts:
            batch_size = len(batch["label_l1"])
            if write_predictions:
                artifact_write_start = perf_counter()
                probs_l3 = torch.softmax(outputs["logits_l3"], dim=-1)
                topk_scores, topk_indices = torch.topk(probs_l3, k=min(topk, probs_l3.shape[1]), dim=-1)
                multilabel_active = batch.get("multilabel_target_mask")
                if multilabel_active is None:
                    multilabel_active = torch.ones((batch_size,), dtype=torch.bool)
                multilabel_active = multilabel_active.bool().cpu()
                multilabel_probs = None
                multilabel_topk_scores = None
                multilabel_topk_indices = None
                multilabel_positive_mask = None
                if outputs.get("logits_multilabel") is not None:
                    multilabel_head_present = True
                    multilabel_probs = torch.sigmoid(outputs["logits_multilabel"]).detach().cpu()
                    positive_threshold = 0.5
                    multilabel_positive_mask = multilabel_probs >= positive_threshold
                    multilabel_k = min(topk, multilabel_probs.shape[1])
                    if multilabel_k > 0:
                        multilabel_topk_scores, multilabel_topk_indices = torch.topk(multilabel_probs, k=multilabel_k, dim=-1)
                    else:
                        multilabel_topk_scores = torch.zeros((batch_size, 0), dtype=multilabel_probs.dtype)
                        multilabel_topk_indices = torch.zeros((batch_size, 0), dtype=torch.long)
                prediction_rows: list[dict[str, Any]] = []
                for idx in range(batch_size):
                    gate_values = outputs["fusion_gates"][idx].detach().cpu().tolist()
                    positive_indices: list[int] = []
                    positive_scores: list[float] = []
                    multilabel_top_indices: list[int] = []
                    multilabel_top_scores_values: list[float] = []
                    if multilabel_probs is not None and multilabel_positive_mask is not None:
                        positive_indices = torch.nonzero(multilabel_positive_mask[idx], as_tuple=False).flatten().tolist()
                        positive_scores = [float(multilabel_probs[idx, item]) for item in positive_indices]
                        multilabel_top_indices = [int(item) for item in multilabel_topk_indices[idx].tolist()]
                        multilabel_top_scores_values = [float(item) for item in multilabel_topk_scores[idx].tolist()]
                    prediction_rows.append(
                        {
                            "protein_id": batch["protein_id"][idx],
                            "embedding_id": batch["embedding_id"][idx],
                            "exact_sequence_rep_id": batch["exact_sequence_rep_id"][idx],
                            "split": batch["split"][idx],
                            "split_strategy": batch["split_strategy"][idx],
                            "split_version": batch["split_version"][idx],
                            "homology_cluster_id": batch["homology_cluster_id"][idx],
                            "target_l1": int(target_map["l1"][idx]),
                            "target_l2": int(target_map["l2"][idx]),
                            "target_l3_core": int(target_map["l3"][idx]),
                            "pred_l1": int(pred_map["l1"][idx]),
                            "pred_l2": int(pred_map["l2"][idx]),
                            "pred_l3_core": int(pred_map["l3"][idx]),
                            "confidence_l3_core": float(topk_scores[idx, 0].cpu()),
                            "topk_l3_indices": ",".join(str(int(x)) for x in topk_indices[idx].cpu().tolist()),
                            "topk_l3_scores": ",".join(f"{float(x):.6f}" for x in topk_scores[idx].cpu().tolist()),
                            "gate_sequence": float(gate_values[0]),
                            "gate_structure": float(gate_values[1]),
                            "gate_context": float(gate_values[2]),
                            "multilabel_positive_indices": _format_index_list(positive_indices),
                            "multilabel_positive_scores": _format_score_list(positive_scores),
                            "multilabel_topk_indices": _format_index_list(multilabel_top_indices),
                            "multilabel_topk_scores": _format_score_list(multilabel_top_scores_values),
                            "multilabel_active_for_metrics": bool(multilabel_active[idx].item()),
                        }
                    )
                dual_output_prediction_rows += len(prediction_rows)
                pd.DataFrame(prediction_rows).to_csv(
                    predictions_path,
                    mode="w" if write_header else "a",
                    header=write_header,
                    index=False,
                )
                write_header = False
                timing["artifact_write_ms"] += (perf_counter() - artifact_write_start) * 1000.0
            if export_embeddings:
                artifact_write_start = perf_counter()
                for idx in range(batch_size):
                    embedding_rows.append(
                        {
                            "protein_id": batch["protein_id"][idx],
                            "embedding_id": batch["embedding_id"][idx],
                            "feature": outputs["features"][idx].detach().cpu().tolist(),
                        }
                    )
                timing["artifact_write_ms"] += (perf_counter() - artifact_write_start) * 1000.0
        last_batch_end = perf_counter()

    metric_agg_start = perf_counter()
    metrics = {key: _metrics_from_confusion(confusion[key]) for key in ("l1", "l2", "l3")} if confusion is not None else {
        "l1": {"accuracy": 0.0, "macro_f1": 0.0},
        "l2": {"accuracy": 0.0, "macro_f1": 0.0},
        "l3": {"accuracy": 0.0, "macro_f1": 0.0},
    }
    metrics["hierarchy_violation_rate"] = 0.0 if hierarchy_checked == 0 else float(hierarchy_violations / hierarchy_checked)
    if multilabel_targets_batches:
        multilabel_targets = np.concatenate(multilabel_targets_batches, axis=0)
        multilabel_preds = np.concatenate(multilabel_pred_batches, axis=0)
        metrics["multilabel"] = {
            "micro_f1": float(f1_score(multilabel_targets, multilabel_preds, average="micro", zero_division=0)),
            "macro_f1": float(f1_score(multilabel_targets, multilabel_preds, average="macro", zero_division=0)),
            "samples_f1": float(f1_score(multilabel_targets, multilabel_preds, average="samples", zero_division=0)),
            "num_samples": int(multilabel_targets.shape[0]),
        }
    else:
        metrics["multilabel"] = {
            "micro_f1": 0.0,
            "macro_f1": 0.0,
            "samples_f1": 0.0,
            "num_samples": 0,
        }
    if gate_batches > 0:
        mean_gates = (gate_sums / gate_batches).tolist()
        metrics["mean_gates"] = {
            "sequence": float(mean_gates[0]),
            "structure": float(mean_gates[1]),
            "context": float(mean_gates[2]),
        }
    metrics["dual_output"] = {
        "protocol": "dual_output_without_selector" if multilabel_head_present else "",
        "multilabel_head_present": multilabel_head_present,
        "positive_threshold": 0.5 if multilabel_head_present else None,
        "topk": int(topk),
        "exported_prediction_rows": int(dual_output_prediction_rows),
        "metrics_masked_by_target_mask": True,
    }
    metrics["gate_health"] = build_gate_health_summary(metrics)
    timing["metric_agg_ms"] += (perf_counter() - metric_agg_start) * 1000.0

    batch_count = max(1, len(dataloader))
    metrics["timing"] = {key: value / batch_count for key, value in timing.items()}
    if dataset is not None and hasattr(dataset, "runtime_stats"):
        metrics["timing"].update(dataset.runtime_stats())
    metrics["timing"]["worker_time_ms_est"] = float(metrics["timing"].get("dataloader_next_ms", 0.0))
    if pin_memory_probe is not None:
        metrics["pin_memory_probe"] = pin_memory_probe
    metrics["pin_memory_mode"] = pin_memory_mode
    metrics.update(gpu_peak_memory_stats(device))

    if export_dir is not None:
        artifact_write_start = perf_counter()
        if export_full_artifacts:
            pd.DataFrame(confusion["l3"].tolist()).to_csv(
                export_dir / f"confusion_l3_{split_name}.csv",
                index=False,
            )
            gate_by_l1_frame = _gate_aggregate_to_frame(gate_by_l1, "target_l1")
            gate_by_l3_frame = _gate_aggregate_to_frame(gate_by_l3, "target_l3_core")
            if not gate_by_l1_frame.empty:
                gate_by_l1_frame.to_csv(
                    export_dir / f"gates_by_l1_{split_name}.csv",
                    index=False,
                )
            if not gate_by_l3_frame.empty:
                gate_by_l3_frame.to_csv(
                    export_dir / f"gates_by_l3_{split_name}.csv",
                    index=False,
                )
            if export_embeddings:
                torch.save(embedding_rows, export_dir / f"features_{split_name}.pt")
            timing["artifact_write_ms"] += (perf_counter() - artifact_write_start) * 1000.0
            metrics["timing"] = {key: value / batch_count for key, value in timing.items()}
            if dataset is not None and hasattr(dataset, "runtime_stats"):
                metrics["timing"].update(dataset.runtime_stats())
            metrics["timing"]["worker_time_ms_est"] = float(metrics["timing"].get("dataloader_next_ms", 0.0))
            if pin_memory_probe is not None:
                metrics["pin_memory_probe"] = pin_memory_probe
            metrics["pin_memory_mode"] = pin_memory_mode
        dump_json(metrics, export_dir / f"metrics_{split_name}.json")
    metrics["timing"] = {key: value / batch_count for key, value in timing.items()}
    if dataset is not None and hasattr(dataset, "runtime_stats"):
        metrics["timing"].update(dataset.runtime_stats())
    metrics["timing"]["worker_time_ms_est"] = float(metrics["timing"].get("dataloader_next_ms", 0.0))
    if pin_memory_probe is not None:
        metrics["pin_memory_probe"] = pin_memory_probe
    metrics["pin_memory_mode"] = pin_memory_mode
    print(
        f"[eval-multimodal] split={split_name} timing_ms(data={metrics['timing']['data_wait_ms']:.2f},"
        f"next={metrics['timing']['dataloader_next_ms']:.2f},host={metrics['timing']['host_prepare_ms']:.2f},"
        f"h2d={metrics['timing']['h2d_ms']:.2f},fwd={metrics['timing']['forward_ms']:.2f},metric={metrics['timing']['metric_agg_ms']:.2f},"
        f"artifact={metrics['timing']['artifact_write_ms']:.2f})"
    )
    return metrics


def load_model_from_checkpoint(
    config: dict[str, Any],
    dataset: MultimodalCoreDataset,
    checkpoint_path: Path,
    device: torch.device,
) -> MultimodalBaselineV2:
    vocab_l1 = load_vocab(resolve_path(config["data"]["vocab_l1"], REPO_ROOT))
    vocab_l2 = load_vocab(resolve_path(config["data"]["vocab_l2"], REPO_ROOT))
    vocab_l3 = load_vocab(resolve_path(config["data"]["vocab_l3_core"], REPO_ROOT))
    model = build_model(config, dataset, (len(vocab_l1), len(vocab_l2), len(vocab_l3))).to(device)
    checkpoint = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(checkpoint["model_state"])
    return model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate multimodal baseline v2.")
    parser.add_argument("--config", default="baseline/train_config.multimodal_v2.stage1.yaml")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--split", default="val", choices=["train", "val", "test"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--num-workers", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--metrics-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = apply_active_runtime_paths(load_yaml(resolve_path(args.config, REPO_ROOT)))
    if args.num_workers is not None:
        config.setdefault("training", {})
        config["training"]["num_workers"] = int(args.num_workers)
    runtime_paths = resolve_runtime_paths(config)
    assets = resolve_assets(config)
    prepack_summary = load_prepack_summary(assets.prepacked_dir)
    print_runtime_paths(runtime_paths)
    print_multimodal_runtime_banner(config, assets, prepack_summary)
    validate_paths_exist(
        {
            "label_table_csv": runtime_paths["label_table_csv"],
            "join_index_csv": runtime_paths["join_index_csv"],
            "vocab_l1": runtime_paths["vocab_l1"],
            "vocab_l2": runtime_paths["vocab_l2"],
            "vocab_l3_core": runtime_paths["vocab_l3_core"],
            "embedding_dir": runtime_paths["embedding_dir"],
            "embedding_index_db": runtime_paths["embedding_index_db"],
        }
    )
    validate_runtime_contract(config, runtime_paths)
    validate_support_assets(config, assets)
    device = choose_device(config["training"]["device"])
    pin_memory = resolve_pin_memory(config, device)
    pin_memory_mode = resolve_pin_memory_mode(config)

    dataset = MultimodalCoreDataset.from_prepacked_dir(
        assets.prepacked_dir,
        split=args.split,
        limit=args.limit,
        include_runtime_metadata=False,
    )
    vocab_l1 = load_vocab(resolve_path(config["data"]["vocab_l1"], REPO_ROOT))
    vocab_l2 = load_vocab(resolve_path(config["data"]["vocab_l2"], REPO_ROOT))
    vocab_l3 = load_vocab(resolve_path(config["data"]["vocab_l3_core"], REPO_ROOT))
    l3_to_l2, l2_to_l1 = dataset.hierarchy_maps(
        num_l1=len(vocab_l1),
        num_l2=len(vocab_l2),
        num_l3=len(vocab_l3),
    )
    export_full_artifacts = bool(config.get("evaluation", {}).get("export_full_artifacts", False))
    dataloader = make_dataloader(
        dataset,
        batch_size=int(config["training"]["eval_batch_size"]),
        num_workers=int(config["training"]["num_workers"]),
        pin_memory=pin_memory,
        include_metadata=bool((not args.dry_run) and ((not args.metrics_only and export_full_artifacts) or bool(config["evaluation"]["export_embeddings"]))),
        include_runtime_metadata=False,
    )
    if args.dry_run:
        print(f"[evaluate-multimodal] dry-run only; split={args.split} rows={len(dataset)}")
        return
    model = load_model_from_checkpoint(config, dataset, resolve_path(args.checkpoint, REPO_ROOT), device)
    output_dir = resolve_path(args.output_dir or config["run"]["output_dir"], REPO_ROOT) / "evaluation"
    metrics = run_evaluation(
        model=model,
        dataloader=dataloader,
        device=device,
        export_dir=output_dir,
        split_name=args.split,
        topk=int(config["evaluation"]["export_topk"]),
        export_embeddings=bool(config["evaluation"]["export_embeddings"]),
        l3_to_l2=l3_to_l2,
        l2_to_l1=l2_to_l1,
        export_mode="full_export" if (not args.metrics_only and export_full_artifacts) else "metrics_only",
        pin_memory_mode=pin_memory_mode,
    )
    metrics["dataloader"] = {
        "requested_num_workers": getattr(dataloader, "requested_num_workers", int(config["training"]["num_workers"])),
        "active_num_workers": getattr(dataloader, "active_num_workers", int(config["training"]["num_workers"])),
        "pin_memory": pin_memory,
        "pin_memory_mode": pin_memory_mode,
        "include_metadata": bool((not args.metrics_only and export_full_artifacts) or bool(config["evaluation"]["export_embeddings"])),
    }
    metrics["prepack"] = prepack_summary
    if output_dir is not None:
        dump_json(metrics, output_dir / f"metrics_{args.split}.json")
    print(metrics)


if __name__ == "__main__":
    main()
