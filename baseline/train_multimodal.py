from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader, Dataset

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baseline.common import (
    REPO_ROOT,
    apply_active_runtime_paths,
    dump_json,
    ensure_dir,
    load_vocab,
    load_yaml,
    print_runtime_paths,
    resolve_path,
    resolve_runtime_paths,
    validate_paths_exist,
    validate_runtime_contract,
)
from baseline.dataset_multimodal import MultimodalCoreDataset
from baseline.evaluate_multimodal import run_evaluation
from baseline.multimodal_v2.losses import HierarchicalMultimodalLoss
from baseline.multimodal_v2.model import MultimodalBaselineV2
from baseline.samplers import build_train_sampler


@dataclass(frozen=True)
class MultimodalAssets:
    prepacked_dir: Path
    structure_embedding_dir: Path | None
    context_feature_table: Path | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train multimodal baseline v2.")
    parser.add_argument("--config", default="baseline/train_config.multimodal_v2.stage1.yaml")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output-dir", default=None)
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
    dataset: Dataset,
    batch_size: int,
    num_workers: int,
    shuffle: bool,
    pin_memory: bool = False,
    sampler=None,
) -> DataLoader:
    use_shuffle = shuffle if sampler is None else False
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=use_shuffle,
        sampler=sampler,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )


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
    return MultimodalAssets(
        prepacked_dir=resolve_path(prepacked_dir, REPO_ROOT),
        structure_embedding_dir=None if not structure_dir else resolve_path(structure_dir, REPO_ROOT),
        context_feature_table=None if not context_table else resolve_path(context_table, REPO_ROOT),
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
    validate_paths_exist(required)


def prepare_datasets(config: dict[str, Any], args: argparse.Namespace, assets: MultimodalAssets) -> tuple[Dataset, Dataset]:
    train_dataset = MultimodalCoreDataset.from_prepacked_dir(assets.prepacked_dir, split="train", limit=args.limit_train)
    val_dataset = MultimodalCoreDataset.from_prepacked_dir(assets.prepacked_dir, split="val", limit=args.limit_val)
    return train_dataset, val_dataset


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
) -> dict[str, float]:
    model.train()
    running = {
        "loss": 0.0,
        "l1": 0.0,
        "l2": 0.0,
        "l3": 0.0,
        "hierarchy": 0.0,
        "g_seq": 0.0,
        "g_struct": 0.0,
        "g_ctx": 0.0,
    }
    step_count = 0
    sample_count = 0

    for step_idx, batch in enumerate(dataloader, start=1):
        optimizer.zero_grad(set_to_none=True)
        outputs = model(
            sequence_embedding=batch["sequence_embedding"].to(device),
            structure_embedding=batch["structure_embedding"].to(device),
            context_features=batch["context_features"].to(device),
            modality_mask=batch["modality_mask"].to(device),
        )
        loss_output = criterion(
            logits_l1=outputs["logits_l1"],
            logits_l2=outputs["logits_l2"],
            logits_l3=outputs["logits_l3"],
            target_l1=batch["label_l1"].to(device),
            target_l2=batch["label_l2"].to(device),
            target_l3=batch["label_l3_core"].to(device),
        )
        loss_output.total.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
        optimizer.step()
        scheduler.step()

        running["loss"] += float(loss_output.total.detach().cpu())
        running["l1"] += float(loss_output.l1.detach().cpu())
        running["l2"] += float(loss_output.l2.detach().cpu())
        running["l3"] += float(loss_output.l3.detach().cpu())
        running["hierarchy"] += float(loss_output.hierarchy.detach().cpu())
        running["g_seq"] += float(outputs["fusion_gates"][:, 0].mean().detach().cpu())
        running["g_struct"] += float(outputs["fusion_gates"][:, 1].mean().detach().cpu())
        running["g_ctx"] += float(outputs["fusion_gates"][:, 2].mean().detach().cpu())
        step_count += 1
        sample_count += int(batch["sequence_embedding"].shape[0])

        if log_every_n_steps and step_idx % log_every_n_steps == 0:
            avg_loss = running["loss"] / step_count
            print(f"[train-multimodal] step={step_idx} avg_loss={avg_loss:.4f}")

        if smoke_steps is not None and step_idx >= smoke_steps:
            break

    metrics = {key: value / max(1, step_count) for key, value in running.items()}
    metrics["steps"] = float(step_count)
    metrics["samples_seen"] = float(sample_count)
    return metrics


def build_model(config: dict[str, Any], train_dataset: MultimodalCoreDataset, vocab_sizes: tuple[int, int, int]) -> MultimodalBaselineV2:
    model_cfg = (config.get("multimodal", {}) or {}).get("model", {}) or {}
    modalities = (config.get("multimodal", {}) or {}).get("modalities", {}) or {}
    num_l1, num_l2, num_l3 = vocab_sizes
    return MultimodalBaselineV2(
        sequence_input_dim=int(train_dataset.sequence_embedding.shape[1]),
        structure_input_dim=int(train_dataset.structure_embedding.shape[1]),
        context_input_dim=int(train_dataset.context_features.shape[1]),
        fusion_dim=int(model_cfg.get("fusion_dim", 512)),
        adapter_hidden_dim=int(model_cfg.get("branch_hidden_dim", 256)),
        trunk_hidden_dim=int(model_cfg.get("trunk_hidden_dim", 512)),
        trunk_hidden_dim2=int(model_cfg.get("trunk_hidden_dim2", model_cfg.get("trunk_hidden_dim", 512))),
        dropout=float(model_cfg.get("dropout", 0.1)),
        modality_dropout=float(model_cfg.get("modality_dropout", 0.1)),
        num_l1=num_l1,
        num_l2=num_l2,
        num_l3=num_l3,
        use_sequence=bool(modalities.get("sequence", True)),
        use_structure=bool(modalities.get("structure", False)),
        use_context=bool(modalities.get("context", False)),
    )


def main() -> None:
    args = parse_args()
    config = apply_active_runtime_paths(load_yaml(resolve_path(args.config, REPO_ROOT)))
    if args.seed is not None:
        config.setdefault("run", {})
        config["run"]["seed"] = int(args.seed)
    if args.output_dir:
        config.setdefault("run", {})
        config["run"]["output_dir"] = str(args.output_dir)
    runtime_paths = resolve_runtime_paths(config)
    print_runtime_paths(runtime_paths)
    validate_paths_exist(
        {
            "label_table_csv": runtime_paths["label_table_csv"],
            "join_index_csv": runtime_paths["join_index_csv"],
            "vocab_l1": runtime_paths["vocab_l1"],
            "vocab_l2": runtime_paths["vocab_l2"],
            "vocab_l3_core": runtime_paths["vocab_l3_core"],
            "embedding_dir": runtime_paths["embedding_dir"],
            "embedding_index_db": runtime_paths["embedding_index_db"],
            "prepacked_dir": runtime_paths["prepacked_dir"],
        }
    )
    validate_runtime_contract(config, runtime_paths)
    assets = resolve_assets(config)
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
    train_sampler = build_train_sampler(config, train_dataset)
    sampler_cfg = config["training"].get("sampler", {}) or {}

    train_loader = make_dataloader(
        dataset=train_dataset,
        batch_size=int(config["training"]["batch_size"]),
        num_workers=int(config["training"]["num_workers"]),
        shuffle=False,
        pin_memory=device.type == "cuda",
        sampler=train_sampler,
    )
    val_loader = make_dataloader(
        dataset=val_dataset,
        batch_size=int(config["training"]["eval_batch_size"]),
        num_workers=int(config["training"]["num_workers"]),
        shuffle=False,
        pin_memory=device.type == "cuda",
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
    criterion = HierarchicalMultimodalLoss(
        weight_l1=float(loss_cfg.get("l1", 0.5)),
        weight_l2=float(loss_cfg.get("l2", 1.0)),
        weight_l3=float(loss_cfg.get("l3", 1.2)),
        class_weights_l1=class_weights.get("l1"),
        class_weights_l2=class_weights.get("l2"),
        class_weights_l3=class_weights.get("l3"),
        hierarchy_loss_weight=float(loss_cfg.get("hierarchy", 0.08)),
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
        )
        val_metrics = run_evaluation(
            model=model,
            dataloader=val_loader,
            device=device,
            export_dir=output_dir / "evaluation",
            split_name=f"val_epoch_{epoch:02d}",
            topk=int(config["evaluation"]["export_topk"]),
            export_embeddings=bool(config["evaluation"]["export_embeddings"]),
            l3_to_l2=l3_to_l2,
            l2_to_l1=l2_to_l1,
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

    dump_json(
        {
            "variant": str((config.get("multimodal", {}) or {}).get("variant", "multimodal_v2")),
            "run_name": str(config["run"]["name"]),
            "seed": int(config["run"]["seed"]),
            "best_val_l3_macro_f1": best_metric,
            "best_epoch": int(best_epoch),
            "best_val_metrics": best_val_metrics,
            "modalities": (config.get("multimodal", {}) or {}).get("modalities", {}),
            "epochs": len(history),
            "train_samples": len(train_dataset),
            "val_samples": len(val_dataset),
            "sampler": {
                "enabled": bool(sampler_cfg.get("enabled", True)),
                "mode": str(sampler_cfg.get("mode", "cluster_exact_balanced")),
                "seed": int(sampler_cfg.get("seed", config["run"]["seed"])),
                "samples_per_epoch": len(train_sampler),
            },
        },
        output_dir / "summary.json",
    )


if __name__ == "__main__":
    main()
