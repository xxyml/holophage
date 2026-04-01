from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader, Dataset

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
from baseline.dataset_multimodal import MultimodalCoreDataset, multimodal_collate
from baseline.evaluate_multimodal import load_model_from_checkpoint, run_evaluation
from baseline.multimodal_v2.losses import HierarchicalMultimodalLoss
from baseline.multimodal_v2.model import MultimodalBaselineV2
from baseline.multimodal_v2.types import (
    CONTEXT_FEATURE_DIM,
    CONTEXT_GRAPH_NODE_FEATURE_DIM,
    DEFAULT_SEQUENCE_EMBEDDING_DIM,
    DEFAULT_STRUCTURE_EMBEDDING_DIM,
)
from baseline.samplers import build_train_batch_sampler, build_train_sampler


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


def resolve_loader_sampler(dataloader: DataLoader) -> Any:
    inner_loader = resolve_inner_loader(dataloader)
    batch_sampler = getattr(inner_loader, "batch_sampler", None)
    if batch_sampler is not None and (
        hasattr(batch_sampler, "timing_snapshot") or hasattr(batch_sampler, "trace_snapshot")
    ):
        return batch_sampler
    return getattr(inner_loader, "sampler", None)


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train multimodal baseline v2.")
    parser.add_argument("--config", default="baseline/train_config.multimodal_v2.stage1.yaml")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--num-workers", type=int, default=None)
    parser.add_argument("--limit-train", type=int, default=None)
    parser.add_argument("--limit-val", type=int, default=None)
    parser.add_argument("--smoke-steps", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def make_dataloader(
    dataset: MultimodalCoreDataset,
    batch_size: int,
    num_workers: int,
    shuffle: bool,
    pin_memory: bool = False,
    sampler=None,
    batch_sampler=None,
    include_metadata: bool = False,
    include_runtime_metadata: bool = False,
) -> DataLoader:
    use_shuffle = shuffle if sampler is None else False
    dataset.include_metadata = bool(include_metadata)
    dataset.include_runtime_metadata = bool(include_runtime_metadata)
    def _factory(active_workers: int) -> DataLoader:
        if batch_sampler is not None:
            dataloader_kwargs = {
                "dataset": dataset,
                "batch_sampler": batch_sampler,
                "num_workers": active_workers,
                "pin_memory": pin_memory,
                "collate_fn": multimodal_collate,
            }
        else:
            dataloader_kwargs = {
                "dataset": dataset,
                "batch_size": batch_size,
                "shuffle": use_shuffle,
                "sampler": sampler,
                "num_workers": active_workers,
                "pin_memory": pin_memory,
                "collate_fn": multimodal_collate,
            }
        if active_workers > 0:
            dataloader_kwargs["persistent_workers"] = True
            dataloader_kwargs["prefetch_factor"] = 4
        return DataLoader(**dataloader_kwargs)

    return DataLoaderWithFallback(_factory, num_workers=num_workers, label="multimodal-train-loader")


def build_scheduler(optimizer: AdamW, total_steps: int, warmup_ratio: float) -> LambdaLR:
    warmup_steps = max(1, int(total_steps * warmup_ratio))

    def lr_lambda(step: int) -> float:
        if step < warmup_steps:
            return float(step + 1) / float(warmup_steps)
        progress = float(step - warmup_steps) / float(max(1, total_steps - warmup_steps))
        return max(0.0, 0.5 * (1.0 + math.cos(math.pi * progress)))

    return LambdaLR(optimizer, lr_lambda)


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


def prepare_datasets(config: dict[str, Any], args: argparse.Namespace, assets: MultimodalAssets) -> tuple[Dataset, Dataset]:
    train_dataset = MultimodalCoreDataset.from_prepacked_dir(
        assets.prepacked_dir,
        split="train",
        limit=args.limit_train,
        include_runtime_metadata=False,
    )
    val_dataset = MultimodalCoreDataset.from_prepacked_dir(
        assets.prepacked_dir,
        split="val",
        limit=args.limit_val,
        include_runtime_metadata=False,
    )
    return train_dataset, val_dataset


def build_eval_dataset(assets: MultimodalAssets, split: str) -> MultimodalCoreDataset:
    return MultimodalCoreDataset.from_prepacked_dir(
        assets.prepacked_dir,
        split=split,
        include_runtime_metadata=False,
    )


def save_checkpoint(
    path: Path,
    model: MultimodalBaselineV2,
    optimizer: AdamW,
    scheduler: LambdaLR,
    epoch: int,
    best_metric: float,
    config: dict[str, Any],
) -> None:
    torch.save(
        {
            "epoch": epoch,
            "best_metric": best_metric,
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "scheduler_state": scheduler.state_dict(),
            "config": config,
        },
        path,
    )


def train_one_epoch(
    model: MultimodalBaselineV2,
    dataloader: DataLoader,
    criterion: HierarchicalMultimodalLoss,
    optimizer: AdamW,
    scheduler: LambdaLR,
    device: torch.device,
    max_grad_norm: float,
    log_every_n_steps: int,
    smoke_steps: int | None,
    pin_memory_mode: str,
) -> dict[str, Any]:
    model.train()
    reset_gpu_peak_memory(device)
    dataset = resolve_dataset_from_loader(dataloader)
    inner_loader = resolve_inner_loader(dataloader)
    sampler = resolve_loader_sampler(dataloader)
    sampler_profile = sampler.shadow_profile() if sampler is not None and hasattr(sampler, "shadow_profile") else {}
    if dataset is not None and hasattr(dataset, "reset_runtime_stats"):
        dataset.reset_runtime_stats()
    running = {
        "loss": 0.0,
        "l1": 0.0,
        "l2": 0.0,
        "l3": 0.0,
        "multilabel": 0.0,
        "hierarchy": 0.0,
        "gate_regularization": 0.0,
        "gate_load_balance": 0.0,
        "g_seq": 0.0,
        "g_struct": 0.0,
        "g_ctx": 0.0,
    }
    timing = {
        "data_wait_ms": 0.0,
        "dataloader_next_ms": 0.0,
        "batch_from_indices_ms": 0.0,
        "host_prepare_ms": 0.0,
        "h2d_submit_ms": 0.0,
        "h2d_cuda_ms": 0.0,
        "h2d_ms": 0.0,
        "forward_ms": 0.0,
        "loss_ms": 0.0,
        "backward_ms": 0.0,
        "optim_ms": 0.0,
        "step_ms": 0.0,
        "context_gnn_ms": 0.0,
    }
    step_count = 0
    sample_count = 0
    last_step_end = perf_counter()
    pin_memory_probe: dict[str, Any] | None = None
    batch_iter = iter(dataloader)
    step_idx = 0
    while True:
        next_start = perf_counter()
        try:
            batch = next(batch_iter)
        except StopIteration:
            break
        step_idx += 1
        batch_ready = perf_counter()
        timing["dataloader_next_ms"] += (batch_ready - next_start) * 1000.0
        timing["data_wait_ms"] += (batch_ready - last_step_end) * 1000.0
        step_start = batch_ready
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
        optimizer.zero_grad(set_to_none=True)
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
        target_l1 = batch["label_l1"].to(device, non_blocking=True)
        target_l2 = batch["label_l2"].to(device, non_blocking=True)
        target_l3 = batch["label_l3_core"].to(device, non_blocking=True)
        target_l3_mask = batch.get("label_l3_core_mask")
        if target_l3_mask is not None:
            target_l3_mask = target_l3_mask.to(device, non_blocking=True)
        multilabel_targets = batch.get("multilabel_targets")
        if multilabel_targets is not None:
            multilabel_targets = multilabel_targets.to(device=device, non_blocking=True)
        multilabel_target_mask = batch.get("multilabel_target_mask")
        if multilabel_target_mask is not None:
            multilabel_target_mask = multilabel_target_mask.to(device, non_blocking=True)
        if h2d_event_end is not None:
            h2d_event_end.record()
        h2d_submit_ms = (perf_counter() - h2d_start) * 1000.0
        timing["h2d_submit_ms"] += h2d_submit_ms
        timing["h2d_ms"] += h2d_submit_ms
        forward_start = perf_counter()
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
        loss_start = perf_counter()
        loss_output = criterion(
            logits_l1=outputs["logits_l1"],
            logits_l2=outputs["logits_l2"],
            logits_l3=outputs["logits_l3"],
            target_l1=target_l1,
            target_l2=target_l2,
            target_l3=target_l3,
            logits_multilabel=outputs.get("logits_multilabel"),
            multilabel_targets=multilabel_targets,
            multilabel_target_mask=multilabel_target_mask,
            target_l3_mask=target_l3_mask,
            fusion_gates=outputs.get("fusion_gates"),
            fusion_gate_mask=outputs.get("modality_mask"),
        )
        timing["loss_ms"] += (perf_counter() - loss_start) * 1000.0
        backward_start = perf_counter()
        loss_output.total.backward()
        timing["backward_ms"] += (perf_counter() - backward_start) * 1000.0
        optim_start = perf_counter()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
        optimizer.step()
        scheduler.step()
        timing["optim_ms"] += (perf_counter() - optim_start) * 1000.0

        running["loss"] += float(loss_output.total.detach().cpu())
        running["l1"] += float(loss_output.l1.detach().cpu())
        running["l2"] += float(loss_output.l2.detach().cpu())
        running["l3"] += float(loss_output.l3.detach().cpu())
        running["multilabel"] += float(loss_output.multilabel.detach().cpu())
        running["hierarchy"] += float(loss_output.hierarchy.detach().cpu())
        running["gate_regularization"] += float(loss_output.gate_regularization.detach().cpu())
        running["gate_load_balance"] += float(loss_output.gate_load_balance.detach().cpu())
        running["g_seq"] += float(outputs["fusion_gates"][:, 0].mean().detach().cpu())
        running["g_struct"] += float(outputs["fusion_gates"][:, 1].mean().detach().cpu())
        running["g_ctx"] += float(outputs["fusion_gates"][:, 2].mean().detach().cpu())
        step_count += 1
        sample_count += int(sequence_embedding.shape[0])
        step_end = perf_counter()
        timing["step_ms"] += (step_end - step_start) * 1000.0
        last_step_end = step_end

        if log_every_n_steps and step_idx % log_every_n_steps == 0:
            avg_loss = running["loss"] / step_count
            avg_timing = {key: value / step_count for key, value in timing.items()}
            print(
                f"[train-multimodal] step={step_idx} avg_loss={avg_loss:.4f} "
                f"timing_ms(data={avg_timing['data_wait_ms']:.2f},next={avg_timing['dataloader_next_ms']:.2f},"
                f"host={avg_timing['host_prepare_ms']:.2f},h2d={avg_timing['h2d_ms']:.2f},"
                f"fwd={avg_timing['forward_ms']:.2f},loss={avg_timing['loss_ms']:.2f},"
                f"bwd={avg_timing['backward_ms']:.2f},optim={avg_timing['optim_ms']:.2f},"
                f"step={avg_timing['step_ms']:.2f})"
            )

        if smoke_steps is not None and step_idx >= smoke_steps:
            break

    metrics: dict[str, Any] = {key: value / max(1, step_count) for key, value in running.items()}
    metrics["steps"] = float(step_count)
    metrics["samples_seen"] = float(sample_count)
    metrics["timing"] = {key: value / max(1, step_count) for key, value in timing.items()}
    if dataset is not None and hasattr(dataset, "runtime_stats"):
        metrics["timing"].update(dataset.runtime_stats())
    if sampler_profile:
        metrics["sampler_profile"] = sampler_profile
        sampler_epoch_total_ms = float(sampler_profile.get("sampler_total_ms", 0.0))
        sampler_per_batch_ms_est = sampler_epoch_total_ms / max(1, step_count)
        metrics["timing"]["sampler_epoch_total_ms"] = sampler_epoch_total_ms
        metrics["timing"]["sampler_per_batch_ms_est"] = sampler_per_batch_ms_est
        metrics["timing"]["loader_overhead_ms_est"] = max(
            0.0,
            float(metrics["timing"].get("dataloader_next_ms", 0.0)) - sampler_per_batch_ms_est,
        )
        metrics["timing"]["worker_time_ms_est"] = float(metrics["timing"]["loader_overhead_ms_est"])
        sampler_trace = {
            key: sampler_profile[key]
            for key in ("first_batch_digest", "first_4_batches_digest", "first_8_batches_digest")
            if key in sampler_profile
        }
        if sampler_trace:
            metrics["sampler_trace"] = sampler_trace
    else:
        metrics["timing"]["sampler_epoch_total_ms"] = 0.0
        metrics["timing"]["sampler_per_batch_ms_est"] = 0.0
        metrics["timing"]["loader_overhead_ms_est"] = float(metrics["timing"].get("dataloader_next_ms", 0.0))
        metrics["timing"]["worker_time_ms_est"] = float(metrics["timing"]["loader_overhead_ms_est"])
    if pin_memory_probe is not None:
        metrics["pin_memory_probe"] = pin_memory_probe
    metrics["pin_memory_mode"] = pin_memory_mode
    metrics.update(gpu_peak_memory_stats(device))
    return metrics


def build_model(config: dict[str, Any], train_dataset: MultimodalCoreDataset, vocab_sizes: tuple[int, int, int]) -> MultimodalBaselineV2:
    model_cfg = (config.get("multimodal", {}) or {}).get("model", {}) or {}
    modalities = (config.get("multimodal", {}) or {}).get("modalities", {}) or {}
    num_l1, num_l2, num_l3 = vocab_sizes
    use_sequence = bool(modalities.get("sequence", True))
    use_structure = bool(modalities.get("structure", False))
    use_context = bool(modalities.get("context", False))
    sequence_input_dim = int(train_dataset.sequence_embedding.shape[1] if len(train_dataset) else DEFAULT_SEQUENCE_EMBEDDING_DIM)
    structure_input_dim = int(
        train_dataset.structure_embedding.shape[1]
        if use_structure and len(train_dataset) and train_dataset.structure_embedding.shape[1] > 0
        else DEFAULT_STRUCTURE_EMBEDDING_DIM
    )
    context_input_dim = int(
        train_dataset.context_features.shape[1]
        if use_context and len(train_dataset) and train_dataset.context_features.shape[1] > 0
        else CONTEXT_FEATURE_DIM
    )
    context_graph_node_dim = int(
        train_dataset.context_node_features.shape[2]
        if use_context and len(train_dataset) and train_dataset.context_node_features.ndim == 3 and train_dataset.context_node_features.shape[2] > 0
        else CONTEXT_GRAPH_NODE_FEATURE_DIM
    )
    multilabel_cfg = (config.get("multilabel_head", {}) or {})
    num_multilabel = int(train_dataset.multilabel_output_dim if bool(multilabel_cfg.get("enabled", False)) else 0)
    return MultimodalBaselineV2(
        sequence_input_dim=sequence_input_dim,
        structure_input_dim=structure_input_dim,
        context_input_dim=context_input_dim,
        context_graph_node_dim=context_graph_node_dim,
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
        num_multilabel=num_multilabel,
        use_sequence=use_sequence,
        use_structure=use_structure,
        use_context=use_context,
    )


def export_closeout_metrics(
    config: dict[str, Any],
    output_dir: Path,
    checkpoints_dir: Path,
    assets: MultimodalAssets,
    device: torch.device,
    pin_memory: bool,
    pin_memory_mode: str,
) -> dict[str, Any]:
    checkpoint_path = checkpoints_dir / "best.pt"
    if not checkpoint_path.exists():
        return {
            "best_checkpoint": str(checkpoint_path),
            "exported": False,
            "reason": "best checkpoint missing",
            "exported_files": [],
        }

    eval_dir = ensure_dir(output_dir / "evaluation")
    export_full_artifacts = bool(config.get("evaluation", {}).get("export_full_artifacts", False))
    exported_files: list[str] = []
    dual_output_runtime = {
        "enabled": False,
        "protocol": "",
        "metrics_masked_by_target_mask": True,
    }
    for split in ("val", "test"):
        dataset = build_eval_dataset(assets, split=split)
        dataloader = make_dataloader(
            dataset=dataset,
            batch_size=int(config["training"]["eval_batch_size"]),
            num_workers=int(config["training"]["num_workers"]),
            shuffle=False,
            pin_memory=pin_memory,
            include_metadata=bool(export_full_artifacts),
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
        model = load_model_from_checkpoint(config, dataset, checkpoint_path, device)
        run_evaluation(
            model=model,
            dataloader=dataloader,
            device=device,
            export_dir=eval_dir,
            split_name=split,
            topk=int(config["evaluation"]["export_topk"]),
            export_embeddings=bool(config["evaluation"]["export_embeddings"]),
            l3_to_l2=l3_to_l2,
            l2_to_l1=l2_to_l1,
            export_mode="full_export" if export_full_artifacts else "metrics_only",
            pin_memory_mode=pin_memory_mode,
        )
        exported_files.append(str(eval_dir / f"metrics_{split}.json"))
        metrics_path = eval_dir / f"metrics_{split}.json"
        if metrics_path.exists():
            metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
            dual_output = metrics_payload.get("dual_output", {})
            if isinstance(dual_output, dict) and bool(dual_output.get("multilabel_head_present", False)):
                dual_output_runtime = {
                    "enabled": True,
                    "protocol": str(dual_output.get("protocol", "")),
                    "metrics_masked_by_target_mask": bool(dual_output.get("metrics_masked_by_target_mask", True)),
                }
    return {
        "best_checkpoint": str(checkpoint_path),
        "exported": True,
        "exported_files": exported_files,
        "dual_output_runtime": dual_output_runtime,
    }


def main() -> None:
    args = parse_args()
    config = apply_active_runtime_paths(load_yaml(resolve_path(args.config, REPO_ROOT)))
    model_cfg = (config.get("multimodal", {}) or {}).get("model", {}) or {}
    if args.seed is not None:
        config.setdefault("run", {})
        config["run"]["seed"] = int(args.seed)
    if args.output_dir:
        config.setdefault("run", {})
        config["run"]["output_dir"] = str(args.output_dir)
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

    set_seed(int(config["run"]["seed"]))
    output_dir = ensure_dir(resolve_path(config["run"]["output_dir"], REPO_ROOT))
    checkpoints_dir = ensure_dir(output_dir / "checkpoints")
    logs_dir = ensure_dir(output_dir / "logs")

    train_dataset, val_dataset = prepare_datasets(config, args, assets)
    print(f"[data] train samples: {len(train_dataset)}")
    print(f"[data] val samples: {len(val_dataset)}")

    vocab_l1 = load_vocab(resolve_path(config["data"]["vocab_l1"], REPO_ROOT))
    vocab_l2 = load_vocab(resolve_path(config["data"]["vocab_l2"], REPO_ROOT))
    vocab_l3 = load_vocab(resolve_path(config["data"]["vocab_l3_core"], REPO_ROOT))
    device = choose_device(config["training"]["device"])
    print(f"[train-multimodal] device: {device}")
    pin_memory = resolve_pin_memory(config, device)
    pin_memory_mode = resolve_pin_memory_mode(config)
    train_batch_size = int(config["training"]["batch_size"])
    train_sampler = build_train_sampler(config, train_dataset, batch_size=train_batch_size)
    train_batch_sampler = build_train_batch_sampler(config, train_sampler, batch_size=train_batch_size)
    sampler_cfg = config["training"].get("sampler", {}) or {}
    batch_level_cfg = sampler_cfg.get("batch_level", {}) or {}

    train_loader = make_dataloader(
        dataset=train_dataset,
        batch_size=train_batch_size,
        num_workers=int(config["training"]["num_workers"]),
        shuffle=False,
        pin_memory=pin_memory,
        sampler=train_sampler,
        batch_sampler=train_batch_sampler,
        include_metadata=False,
        include_runtime_metadata=False,
    )
    export_epoch_artifacts = bool(config["training"].get("export_epoch_artifacts", False))
    export_full_artifacts = bool(config.get("evaluation", {}).get("export_full_artifacts", False))
    val_loader = make_dataloader(
        dataset=val_dataset,
        batch_size=int(config["training"]["eval_batch_size"]),
        num_workers=int(config["training"]["num_workers"]),
        shuffle=False,
        pin_memory=pin_memory,
        include_metadata=bool(export_epoch_artifacts and export_full_artifacts),
        include_runtime_metadata=False,
    )

    model = build_model(config, train_dataset, (len(vocab_l1), len(vocab_l2), len(vocab_l3))).to(device)
    class_weights = {}
    if bool(config["training"]["use_class_weights"]):
        class_weights = {
            "l1": train_dataset.class_weights("label_l1", len(vocab_l1)).to(device),
            "l2": train_dataset.class_weights("label_l2", len(vocab_l2)).to(device),
            "l3": train_dataset.class_weights("label_l3_core", len(vocab_l3)).to(device),
        }
    l3_to_l2, l2_to_l1 = train_dataset.hierarchy_maps(
        num_l1=len(vocab_l1),
        num_l2=len(vocab_l2),
        num_l3=len(vocab_l3),
    )
    loss_cfg = (config.get("multimodal", {}) or {}).get("loss", {}) or {}
    multilabel_cfg = (config.get("multilabel_head", {}) or {})
    criterion = HierarchicalMultimodalLoss(
        weight_l1=float(loss_cfg.get("l1", 0.5)),
        weight_l2=float(loss_cfg.get("l2", 1.0)),
        weight_l3=float(loss_cfg.get("l3", 1.2)),
        weight_multilabel=float(multilabel_cfg.get("loss_weight", 1.0)),
        class_weights_l1=class_weights.get("l1"),
        class_weights_l2=class_weights.get("l2"),
        class_weights_l3=class_weights.get("l3"),
        hierarchy_loss_weight=float(loss_cfg.get("hierarchy", 0.08)),
        gate_entropy_loss_weight=float(loss_cfg.get("gate_entropy", 0.0)),
        gate_load_balance_loss_weight=float(loss_cfg.get("gate_load_balance", 0.0)),
        l3_to_l2=l3_to_l2.to(device),
        l2_to_l1=l2_to_l1.to(device),
    ).to(device)

    optimizer = AdamW(
        model.parameters(),
        lr=float(config["training"]["learning_rate"]),
        weight_decay=float(config["training"]["weight_decay"]),
    )
    smoke_steps = args.smoke_steps or config["training"].get("smoke_steps")
    total_steps = (int(smoke_steps) if smoke_steps is not None else len(train_loader)) * int(config["training"]["epochs"])
    scheduler = build_scheduler(optimizer, total_steps=max(1, total_steps), warmup_ratio=float(config["training"]["warmup_ratio"]))

    resolved_report = {
        "runtime_paths": {k: str(v) for k, v in runtime_paths.items()},
        "support_assets": asdict(assets),
        "modalities": (config.get("multimodal", {}) or {}).get("modalities", {}),
        "prepack": prepack_summary,
        "output_dir": str(output_dir),
        "run_name": str(config["run"]["name"]),
        "seed": int(config["run"]["seed"]),
    }
    resolved_report["support_assets"] = {k: (None if v is None else str(v)) for k, v in resolved_report["support_assets"].items()}
    dump_json(resolved_report, logs_dir / "resolved_runtime.json")
    if args.dry_run:
        print("[train-multimodal] dry-run only; runtime contract resolved.")
        return

    history: list[dict[str, Any]] = []
    best_metric = float("-inf")
    best_epoch = -1
    best_val_metrics: dict[str, Any] | None = None
    for epoch in range(1, int(config["training"]["epochs"]) + 1):
        if hasattr(train_sampler, "set_epoch"):
            train_sampler.set_epoch(epoch - 1)
        train_metrics = train_one_epoch(
            model=model,
            dataloader=train_loader,
            criterion=criterion,
            optimizer=optimizer,
            scheduler=scheduler,
            device=device,
            max_grad_norm=float(config["training"]["max_grad_norm"]),
            log_every_n_steps=int(config["training"]["log_every_n_steps"]),
            smoke_steps=None if smoke_steps is None else int(smoke_steps),
            pin_memory_mode=pin_memory_mode,
        )
        val_metrics = run_evaluation(
            model=model,
            dataloader=val_loader,
            device=device,
            export_dir=(output_dir / "evaluation") if export_epoch_artifacts else None,
            split_name=f"val_epoch_{epoch:02d}",
            topk=int(config["evaluation"]["export_topk"]),
            export_embeddings=bool(config["evaluation"]["export_embeddings"]),
            l3_to_l2=l3_to_l2,
            l2_to_l1=l2_to_l1,
            export_mode="full_export" if export_epoch_artifacts and export_full_artifacts else "metrics_only",
            pin_memory_mode=pin_memory_mode,
        )
        epoch_record = {"epoch": epoch, "train": train_metrics, "val": val_metrics}
        history.append(epoch_record)
        dump_json(history, logs_dir / "history.json")

        current_metric = float(val_metrics["l3"]["macro_f1"])
        save_checkpoint(checkpoints_dir / "latest.pt", model, optimizer, scheduler, epoch, best_metric, config)
        if current_metric > best_metric:
            best_metric = current_metric
            best_epoch = epoch
            best_val_metrics = val_metrics
            save_checkpoint(checkpoints_dir / "best.pt", model, optimizer, scheduler, epoch, best_metric, config)
        print(
            f"[epoch {epoch}] train_loss={train_metrics['loss']:.4f} "
            f"val_l3_macro_f1={val_metrics['l3']['macro_f1']:.4f}"
        )

    closeout_artifacts = export_closeout_metrics(
        config=config,
        output_dir=output_dir,
        checkpoints_dir=checkpoints_dir,
        assets=assets,
        device=device,
        pin_memory=pin_memory,
        pin_memory_mode=pin_memory_mode,
    )
    dump_json(
        {
            "variant": str((config.get("multimodal", {}) or {}).get("variant", "multimodal_v2")),
            "run_name": str(config["run"]["name"]),
            "seed": int(config["run"]["seed"]),
            "best_val_l3_macro_f1": best_metric,
            "best_epoch": int(best_epoch),
            "best_val_metrics": best_val_metrics,
            "modalities": (config.get("multimodal", {}) or {}).get("modalities", {}),
            "multilabel_head": {
                "enabled": bool(multilabel_cfg.get("enabled", False)),
                "output_dim": int(getattr(train_dataset, "multilabel_output_dim", 0)),
                "loss_weight": float(multilabel_cfg.get("loss_weight", 1.0)),
            },
            "context_mode": assets.context_mode,
            "preserve_sequence": bool(model_cfg.get("preserve_sequence", True)),
            "prepack": prepack_summary,
            "epochs": len(history),
            "train_samples": len(train_dataset),
            "val_samples": len(val_dataset),
            "sampler": {
                "enabled": bool(sampler_cfg.get("enabled", True)),
                "mode": str(sampler_cfg.get("mode", "cluster_exact_balanced")),
                "seed": int(sampler_cfg.get("seed", config["run"]["seed"])),
                "samples_per_epoch": len(train_sampler),
                "runtime_mode": str(sampler_cfg.get("runtime_mode", "baseline")),
                "profiling_enabled": bool((sampler_cfg.get("profiling", {}) or {}).get("enabled", False)),
                "implementation": "batch_sampler" if train_batch_sampler is not None else "sampler",
                "batching_strategy": "prebatched_indices" if train_batch_sampler is not None else "default_dataloader",
                "trace_batches": int(batch_level_cfg.get("trace_batches", 4)),
            },
            "dataloader": {
                "train": {
                    "requested_num_workers": getattr(train_loader, "requested_num_workers", int(config["training"]["num_workers"])),
                    "active_num_workers": getattr(train_loader, "active_num_workers", int(config["training"]["num_workers"])),
                    "pin_memory": pin_memory,
                    "pin_memory_mode": pin_memory_mode,
                    "include_metadata": False,
                    "pin_memory_probe": history[-1]["train"].get("pin_memory_probe", {}) if history else {},
                },
                "val": {
                    "requested_num_workers": getattr(val_loader, "requested_num_workers", int(config["training"]["num_workers"])),
                    "active_num_workers": getattr(val_loader, "active_num_workers", int(config["training"]["num_workers"])),
                    "pin_memory": pin_memory,
                    "pin_memory_mode": pin_memory_mode,
                    "include_metadata": bool(export_epoch_artifacts and export_full_artifacts),
                    "pin_memory_probe": history[-1]["val"].get("pin_memory_probe", {}) if history else {},
                },
            },
            "timing": {
                "last_train": history[-1]["train"].get("timing", {}) if history else {},
                "last_val": history[-1]["val"].get("timing", {}) if history else {},
            },
            "closeout_artifacts": closeout_artifacts,
            "dual_output_runtime": dict(closeout_artifacts.get("dual_output_runtime", {}))
            if isinstance(closeout_artifacts.get("dual_output_runtime"), dict)
            else {
                "enabled": False,
                "protocol": "",
                "metrics_masked_by_target_mask": True,
            },
        },
        output_dir / "summary.json",
    )


if __name__ == "__main__":
    main()
