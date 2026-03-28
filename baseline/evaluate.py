from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import torch
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
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
from baseline.model import BaselineMultiHeadModel
from baseline.prepacked_dataset import PrepackedCoreDataset


def make_dataloader(dataset: Dataset, batch_size: int, num_workers: int, pin_memory: bool = False) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )


def hierarchy_violation_rate(
    pred_l1: list[int],
    pred_l2: list[int],
    pred_l3: list[int],
    l3_to_l2: torch.Tensor | None,
    l2_to_l1: torch.Tensor | None,
) -> float:
    if not pred_l1:
        return 0.0
    if l3_to_l2 is None or l2_to_l1 is None or l3_to_l2.numel() == 0 or l2_to_l1.numel() == 0:
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
    if checked == 0:
        return 0.0
    return violations / checked


@torch.no_grad()
def run_evaluation(
    model: BaselineMultiHeadModel,
    dataloader: DataLoader,
    device: torch.device,
    export_dir: Path | None = None,
    split_name: str = "val",
    topk: int = 3,
    export_embeddings: bool = False,
    l3_to_l2: torch.Tensor | None = None,
    l2_to_l1: torch.Tensor | None = None,
) -> dict[str, Any]:
    model.eval()
    all_targets = {"l1": [], "l2": [], "l3": []}
    all_preds = {"l1": [], "l2": [], "l3": []}
    prediction_rows: list[dict[str, Any]] = []
    embedding_rows = []

    for batch in dataloader:
        embedding = batch["embedding"].to(device)
        outputs = model(embedding)

        logits_map = {
            "l1": outputs["logits_l1"],
            "l2": outputs["logits_l2"],
            "l3": outputs["logits_l3"],
        }
        target_map = {
            "l1": batch["label_l1"],
            "l2": batch["label_l2"],
            "l3": batch["label_l3_core"],
        }

        pred_map = {}
        for key, logits in logits_map.items():
            preds = torch.argmax(logits, dim=-1).cpu()
            pred_map[key] = preds
            all_preds[key].extend(preds.tolist())
            all_targets[key].extend(target_map[key].tolist())

        probs_l3 = torch.softmax(outputs["logits_l3"], dim=-1)
        topk_scores, topk_indices = torch.topk(probs_l3, k=min(topk, probs_l3.shape[1]), dim=-1)

        batch_size = len(batch["protein_id"])
        for idx in range(batch_size):
            prediction_rows.append(
                {
                    "protein_id": batch["protein_id"][idx],
                    "embedding_id": batch["embedding_id"][idx],
                    "split": batch["split"][idx],
                    "split_strategy": batch.get("split_strategy", [""] * batch_size)[idx],
                    "split_version": batch.get("split_version", [""] * batch_size)[idx],
                    "homology_cluster_id": batch.get("homology_cluster_id", [""] * batch_size)[idx],
                    "exact_sequence_rep_id": batch.get("exact_sequence_rep_id", [""] * batch_size)[idx],
                    "target_l1": int(batch["label_l1"][idx]),
                    "target_l2": int(batch["label_l2"][idx]),
                    "target_l3_core": int(batch["label_l3_core"][idx]),
                    "pred_l1": int(pred_map["l1"][idx]),
                    "pred_l2": int(pred_map["l2"][idx]),
                    "pred_l3_core": int(pred_map["l3"][idx]),
                    "confidence_l3_core": float(topk_scores[idx, 0].cpu()),
                    "topk_l3_indices": ",".join(str(int(x)) for x in topk_indices[idx].cpu().tolist()),
                    "topk_l3_scores": ",".join(f"{float(x):.6f}" for x in topk_scores[idx].cpu().tolist()),
                }
            )
            if export_embeddings:
                embedding_rows.append(
                    {
                        "protein_id": batch["protein_id"][idx],
                        "embedding_id": batch["embedding_id"][idx],
                        "feature": outputs["features"][idx].detach().cpu().tolist(),
                    }
                )

    metrics = {}
    for key in ("l1", "l2", "l3"):
        metrics[key] = {
            "accuracy": float(accuracy_score(all_targets[key], all_preds[key])),
            "macro_f1": float(f1_score(all_targets[key], all_preds[key], average="macro")),
        }

    l3_confusion = confusion_matrix(all_targets["l3"], all_preds["l3"])
    metrics["hierarchy_violation_rate"] = float(
        hierarchy_violation_rate(
            pred_l1=all_preds["l1"],
            pred_l2=all_preds["l2"],
            pred_l3=all_preds["l3"],
            l3_to_l2=l3_to_l2,
            l2_to_l1=l2_to_l1,
        )
    )

    if export_dir is not None:
        ensure_dir(export_dir)
        pd.DataFrame(prediction_rows).to_csv(export_dir / f"predictions_{split_name}.csv", index=False)
        pd.DataFrame(l3_confusion).to_csv(export_dir / f"confusion_l3_{split_name}.csv", index=False)
        dump_json(metrics, export_dir / f"metrics_{split_name}.json")
        if export_embeddings:
            torch.save(embedding_rows, export_dir / f"features_{split_name}.pt")

    return metrics


def load_model_from_checkpoint(config: dict[str, Any], checkpoint_path: Path, device: torch.device) -> BaselineMultiHeadModel:
    vocab_l1 = load_vocab(resolve_path(config["data"]["vocab_l1"], REPO_ROOT))
    vocab_l2 = load_vocab(resolve_path(config["data"]["vocab_l2"], REPO_ROOT))
    vocab_l3 = load_vocab(resolve_path(config["data"]["vocab_l3_core"], REPO_ROOT))

    model = BaselineMultiHeadModel(
        input_dim=config["model"]["input_dim"],
        hidden_dim=config["model"]["hidden_dim"],
        hidden_dim2=config["model"]["hidden_dim2"],
        dropout=config["model"]["dropout"],
        num_l1=len(vocab_l1),
        num_l2=len(vocab_l2),
        num_l3=len(vocab_l3),
    ).to(device)
    checkpoint = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(checkpoint["model_state"])
    return model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate baseline model.")
    parser.add_argument("--config", default="baseline/train_config.full_stage2.yaml")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--split", default="val", choices=["train", "val", "test"])
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def choose_device(device_name: str) -> torch.device:
    if device_name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(device_name)


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
    device = choose_device(config["training"]["device"])

    prepacked_dir = config["data"].get("prepacked_dir")
    prepacked_pack = None
    if prepacked_dir:
        candidate = resolve_path(prepacked_dir, REPO_ROOT) / f"core_{args.split}.pt"
        if candidate.exists():
            prepacked_pack = candidate

    if prepacked_pack is not None:
        print(f"[eval] using prepacked split pack: {prepacked_pack}")
        dataset = PrepackedCoreDataset(prepacked_pack, limit=args.limit)
    else:
        dataset = BaselineCoreDataset(
            join_index_csv=resolve_path(config["data"]["join_index_csv"], REPO_ROOT),
            embedding_db_path=resolve_path(config["data"]["embedding_index_db"], REPO_ROOT),
            embedding_dir=resolve_path(config["data"]["embedding_dir"], REPO_ROOT),
            vocab_l1_path=resolve_path(config["data"]["vocab_l1"], REPO_ROOT),
            vocab_l2_path=resolve_path(config["data"]["vocab_l2"], REPO_ROOT),
            vocab_l3_path=resolve_path(config["data"]["vocab_l3_core"], REPO_ROOT),
            split=args.split,
            limit=args.limit,
        )
    if args.limit is None and len(dataset) < 1000:
        print(
            "[warn] evaluation dataset is unexpectedly small. "
            "Check exact embedding shards and rebuild baseline/artifacts/embedding_index_exact.sqlite."
        )
    l3_to_l2, l2_to_l1 = dataset.hierarchy_maps()
    dataloader = make_dataloader(
        dataset,
        batch_size=int(config["training"]["eval_batch_size"]),
        num_workers=int(config["training"]["num_workers"]),
        pin_memory=device.type == "cuda",
    )
    model = load_model_from_checkpoint(config, resolve_path(args.checkpoint, REPO_ROOT), device)
    output_dir = resolve_path(config["run"]["output_dir"], REPO_ROOT) / "evaluation"
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
    )
    print(metrics)


if __name__ == "__main__":
    main()
