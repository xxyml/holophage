from __future__ import annotations

import argparse
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader, Dataset

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
from baseline.dataset import BaselineCoreDataset
from baseline.evaluate import run_evaluation
from baseline.losses import MultiHeadLoss
from baseline.model import BaselineMultiHeadModel
from baseline.prepacked_dataset import PrepackedCoreDataset
from baseline.samplers import build_train_sampler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train baseline L1/L2/L3-core model.")
    parser.add_argument("--config", default="baseline/train_config.full_stage2.yaml")
    parser.add_argument("--limit-train", type=int, default=None)
    parser.add_argument("--limit-val", type=int, default=None)
    parser.add_argument("--smoke-steps", type=int, default=None)
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


def _resolve_prepacked_path(config: dict[str, Any], split: str) -> Path | None:
    prepacked_dir = config["data"].get("prepacked_dir")
    if not prepacked_dir:
        return None
    pack_path = resolve_path(prepacked_dir, REPO_ROOT) / f"core_{split}.pt"
    if not pack_path.exists():
        return None
    return pack_path


def prepare_datasets(config: dict[str, Any], args: argparse.Namespace) -> tuple[Dataset, Dataset]:
    prepacked_train = _resolve_prepacked_path(config, "train")
    prepacked_val = _resolve_prepacked_path(config, "val")
    if prepacked_train is not None and prepacked_val is not None:
        print(f"[data] using prepacked datasets: {prepacked_train.parent}")
        train_dataset = PrepackedCoreDataset(prepacked_train, limit=args.limit_train)
        val_dataset = PrepackedCoreDataset(prepacked_val, limit=args.limit_val)
        return train_dataset, val_dataset

    common_kwargs = dict(
        join_index_csv=resolve_path(config["data"]["join_index_csv"], REPO_ROOT),
        embedding_db_path=resolve_path(config["data"]["embedding_index_db"], REPO_ROOT),
        embedding_dir=resolve_path(config["data"]["embedding_dir"], REPO_ROOT),
        vocab_l1_path=resolve_path(config["data"]["vocab_l1"], REPO_ROOT),
        vocab_l2_path=resolve_path(config["data"]["vocab_l2"], REPO_ROOT),
        vocab_l3_path=resolve_path(config["data"]["vocab_l3_core"], REPO_ROOT),
    )
    train_dataset = BaselineCoreDataset(split="train", limit=args.limit_train, **common_kwargs)
    val_dataset = BaselineCoreDataset(split="val", limit=args.limit_val, **common_kwargs)
    return train_dataset, val_dataset


def save_checkpoint(
    path: Path,
    model: BaselineMultiHeadModel,
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
    model: BaselineMultiHeadModel,
    dataloader: DataLoader,
    criterion: MultiHeadLoss,
    optimizer: AdamW,
    scheduler: LambdaLR,
    device: torch.device,
    max_grad_norm: float,
    log_every_n_steps: int,
    smoke_steps: int | None,
) -> dict[str, float]:
    model.train()
    running = {"loss": 0.0, "l1": 0.0, "l2": 0.0, "l3": 0.0, "hierarchy": 0.0}
    step_count = 0
    sample_count = 0

    for step_idx, batch in enumerate(dataloader, start=1):
        optimizer.zero_grad(set_to_none=True)
        embedding = batch["embedding"].to(device)
        target_l1 = batch["label_l1"].to(device)
        target_l2 = batch["label_l2"].to(device)
        target_l3 = batch["label_l3_core"].to(device)

        outputs = model(embedding)
        loss_output = criterion(
            logits_l1=outputs["logits_l1"],
            logits_l2=outputs["logits_l2"],
            logits_l3=outputs["logits_l3"],
            target_l1=target_l1,
            target_l2=target_l2,
            target_l3=target_l3,
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
        step_count += 1
        sample_count += int(embedding.shape[0])

        if log_every_n_steps and step_idx % log_every_n_steps == 0:
            avg_loss = running["loss"] / step_count
            print(f"[train] step={step_idx} avg_loss={avg_loss:.4f}")

        if smoke_steps is not None and step_idx >= smoke_steps:
            break

    metrics = {key: value / max(1, step_count) for key, value in running.items()}
    metrics["steps"] = float(step_count)
    metrics["samples_seen"] = float(sample_count)
    return metrics


def main() -> None:
    args = parse_args()
    config = apply_active_runtime_paths(load_yaml(resolve_path(args.config, REPO_ROOT)))
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
    set_seed(int(config["run"]["seed"]))

    output_dir = ensure_dir(resolve_path(config["run"]["output_dir"], REPO_ROOT))
    checkpoints_dir = ensure_dir(output_dir / "checkpoints")
    logs_dir = ensure_dir(output_dir / "logs")

    train_dataset, val_dataset = prepare_datasets(config, args)
    print(f"[data] train samples: {len(train_dataset)}")
    print(f"[data] val samples: {len(val_dataset)}")
    if args.limit_train is None and len(train_dataset) < 10000:
        print(
            "[warn] train sample count is unexpectedly small. "
            "Check whether D:\\data\\ai4s\\holophage\\embedding_pipeline\\outputs\\embed_exact "
            "contains the full exact shard set and rebuild baseline/artifacts/embedding_index_exact.sqlite."
        )

    vocab_l1 = load_vocab(resolve_path(config["data"]["vocab_l1"], REPO_ROOT))
    vocab_l2 = load_vocab(resolve_path(config["data"]["vocab_l2"], REPO_ROOT))
    vocab_l3 = load_vocab(resolve_path(config["data"]["vocab_l3_core"], REPO_ROOT))
    device = choose_device(config["training"]["device"])
    print(f"[train] device: {device}")
    pin_memory = device.type == "cuda"
    train_sampler = build_train_sampler(config, train_dataset)
    sampler_cfg = config["training"].get("sampler", {}) or {}
    print(
        f"[data] train sampler: mode={sampler_cfg.get('mode', 'cluster_exact_balanced')} "
        f"samples_per_epoch={len(train_sampler)}"
    )

    train_loader = make_dataloader(
        dataset=train_dataset,
        batch_size=int(config["training"]["batch_size"]),
        num_workers=int(config["training"]["num_workers"]),
        shuffle=False,
        pin_memory=pin_memory,
        sampler=train_sampler,
    )
    val_loader = make_dataloader(
        dataset=val_dataset,
        batch_size=int(config["training"]["eval_batch_size"]),
        num_workers=int(config["training"]["num_workers"]),
        shuffle=False,
        pin_memory=pin_memory,
    )

    model = BaselineMultiHeadModel(
        input_dim=int(config["model"]["input_dim"]),
        hidden_dim=int(config["model"]["hidden_dim"]),
        hidden_dim2=int(config["model"]["hidden_dim2"]),
        dropout=float(config["model"]["dropout"]),
        num_l1=len(vocab_l1),
        num_l2=len(vocab_l2),
        num_l3=len(vocab_l3),
    ).to(device)

    class_weights = {}
    if bool(config["training"]["use_class_weights"]):
        class_weights = {
            "l1": train_dataset.class_weights("label_l1", len(vocab_l1)).to(device),
            "l2": train_dataset.class_weights("label_l2", len(vocab_l2)).to(device),
            "l3": train_dataset.class_weights("label_l3_core", len(vocab_l3)).to(device),
        }

    l3_to_l2, l2_to_l1 = train_dataset.hierarchy_maps()
    criterion = MultiHeadLoss(
        weight_l1=float(config["training"]["loss_weights"]["l1"]),
        weight_l2=float(config["training"]["loss_weights"]["l2"]),
        weight_l3=float(config["training"]["loss_weights"]["l3"]),
        class_weights_l1=class_weights.get("l1"),
        class_weights_l2=class_weights.get("l2"),
        class_weights_l3=class_weights.get("l3"),
        use_hierarchy_loss=bool(config["training"]["use_hierarchy_loss"]),
        hierarchy_loss_weight=float(config["training"]["hierarchy_loss_weight"]),
        l3_to_l2=l3_to_l2.to(device),
        l2_to_l1=l2_to_l1.to(device),
    ).to(device)

    optimizer = AdamW(
        model.parameters(),
        lr=float(config["training"]["learning_rate"]),
        weight_decay=float(config["training"]["weight_decay"]),
    )
    smoke_steps = args.smoke_steps or config["training"].get("smoke_steps")
    if smoke_steps is not None:
        total_steps = int(smoke_steps) * int(config["training"]["epochs"])
    else:
        total_steps = len(train_loader) * int(config["training"]["epochs"])
    scheduler = build_scheduler(
        optimizer,
        total_steps=max(1, total_steps),
        warmup_ratio=float(config["training"]["warmup_ratio"]),
    )

    history: list[dict[str, Any]] = []
    best_metric = float("-inf")

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
            save_checkpoint(checkpoints_dir / "best.pt", model, optimizer, scheduler, epoch, best_metric, config)

        print(
            f"[epoch {epoch}] train_loss={train_metrics['loss']:.4f} "
            f"val_l3_macro_f1={val_metrics['l3']['macro_f1']:.4f}"
        )

    dump_json(
        {
            "best_val_l3_macro_f1": best_metric,
            "epochs": len(history),
            "train_samples": len(train_dataset),
            "val_samples": len(val_dataset),
            "sampler": {
                "enabled": bool(sampler_cfg.get("enabled", True)),
                "mode": str(sampler_cfg.get("mode", "cluster_exact_balanced")),
                "seed": int(sampler_cfg.get("seed", config["run"]["seed"])),
                "samples_per_epoch": len(train_sampler),
                "cluster_weight_power": float(sampler_cfg.get("cluster_weight_power", 1.0)),
                "exact_weight_power": float(sampler_cfg.get("exact_weight_power", 1.0)),
                "shuffle_within_group": bool(sampler_cfg.get("shuffle_within_group", True)),
            },
        },
        output_dir / "summary.json",
    )


if __name__ == "__main__":
    main()
