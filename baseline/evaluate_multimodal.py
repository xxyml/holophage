from __future__ import annotations

import argparse
from dataclasses import dataclass
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
from baseline.multimodal_v2.model import MultimodalBaselineV2
from baseline.dataset_multimodal import MultimodalCoreDataset
from baseline.multimodal_v2.types import CONTEXT_FEATURE_DIM, DEFAULT_SEQUENCE_EMBEDDING_DIM, DEFAULT_STRUCTURE_EMBEDDING_DIM


@dataclass(frozen=True)
class MultimodalAssets:
    prepacked_dir: Path
    structure_embedding_dir: Path | None
    context_feature_table: Path | None


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


def build_model(config: dict[str, Any], dataset: MultimodalCoreDataset, vocab_sizes: tuple[int, int, int]) -> MultimodalBaselineV2:
    model_cfg = (config.get("multimodal", {}) or {}).get("model", {}) or {}
    modalities = (config.get("multimodal", {}) or {}).get("modalities", {}) or {}
    num_l1, num_l2, num_l3 = vocab_sizes
    return MultimodalBaselineV2(
        sequence_input_dim=int(getattr(dataset, "sequence_embedding").shape[1] if len(dataset) else DEFAULT_SEQUENCE_EMBEDDING_DIM),
        structure_input_dim=int(getattr(dataset, "structure_embedding").shape[1] if len(dataset) else DEFAULT_STRUCTURE_EMBEDDING_DIM),
        context_input_dim=int(getattr(dataset, "context_features").shape[1] if len(dataset) else CONTEXT_FEATURE_DIM),
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
) -> dict[str, Any]:
    model.eval()
    all_targets = {"l1": [], "l2": [], "l3": []}
    all_preds = {"l1": [], "l2": [], "l3": []}
    prediction_rows: list[dict[str, Any]] = []
    embedding_rows = []
    gate_rows: list[dict[str, Any]] = []
    gate_sums = torch.zeros(3, dtype=torch.float64)
    gate_batches = 0

    for batch in dataloader:
        outputs = model(
            sequence_embedding=batch["sequence_embedding"].to(device),
            structure_embedding=batch["structure_embedding"].to(device),
            context_features=batch["context_features"].to(device),
            modality_mask=batch["modality_mask"].to(device),
        )
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
        pred_map: dict[str, torch.Tensor] = {}
        for key, logits in logits_map.items():
            preds = torch.argmax(logits, dim=-1).cpu()
            pred_map[key] = preds
            all_preds[key].extend(preds.tolist())
            all_targets[key].extend(target_map[key].tolist())

        probs_l3 = torch.softmax(outputs["logits_l3"], dim=-1)
        topk_scores, topk_indices = torch.topk(probs_l3, k=min(topk, probs_l3.shape[1]), dim=-1)
        gate_sums += outputs["fusion_gates"].detach().cpu().double().mean(dim=0)
        gate_batches += 1

        batch_size = len(batch["protein_id"])
        for idx in range(batch_size):
            gate_values = outputs["fusion_gates"][idx].detach().cpu().tolist()
            prediction_rows.append(
                {
                    "protein_id": batch["protein_id"][idx],
                    "embedding_id": batch["embedding_id"][idx],
                    "exact_sequence_rep_id": batch["exact_sequence_rep_id"][idx],
                    "split": batch["split"][idx],
                    "split_strategy": batch["split_strategy"][idx],
                    "split_version": batch["split_version"][idx],
                    "homology_cluster_id": batch["homology_cluster_id"][idx],
                    "target_l1": int(batch["label_l1"][idx]),
                    "target_l2": int(batch["label_l2"][idx]),
                    "target_l3_core": int(batch["label_l3_core"][idx]),
                    "pred_l1": int(pred_map["l1"][idx]),
                    "pred_l2": int(pred_map["l2"][idx]),
                    "pred_l3_core": int(pred_map["l3"][idx]),
                    "confidence_l3_core": float(topk_scores[idx, 0].cpu()),
                    "topk_l3_indices": ",".join(str(int(x)) for x in topk_indices[idx].cpu().tolist()),
                    "topk_l3_scores": ",".join(f"{float(x):.6f}" for x in topk_scores[idx].cpu().tolist()),
                    "gate_sequence": float(gate_values[0]),
                    "gate_structure": float(gate_values[1]),
                    "gate_context": float(gate_values[2]),
                }
            )
            gate_rows.append(
                {
                    "target_l1": int(batch["label_l1"][idx]),
                    "target_l2": int(batch["label_l2"][idx]),
                    "target_l3_core": int(batch["label_l3_core"][idx]),
                    "gate_sequence": float(gate_values[0]),
                    "gate_structure": float(gate_values[1]),
                    "gate_context": float(gate_values[2]),
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
    metrics["hierarchy_violation_rate"] = float(
        hierarchy_violation_rate(all_preds["l1"], all_preds["l2"], all_preds["l3"], l3_to_l2, l2_to_l1)
    )
    if gate_batches > 0:
        mean_gates = (gate_sums / gate_batches).tolist()
        metrics["mean_gates"] = {
            "sequence": float(mean_gates[0]),
            "structure": float(mean_gates[1]),
            "context": float(mean_gates[2]),
        }

    if export_dir is not None:
        ensure_dir(export_dir)
        pd.DataFrame(prediction_rows).to_csv(export_dir / f"predictions_{split_name}.csv", index=False)
        pd.DataFrame(confusion_matrix(all_targets["l3"], all_preds["l3"])).to_csv(
            export_dir / f"confusion_l3_{split_name}.csv",
            index=False,
        )
        if gate_rows:
            gate_df = pd.DataFrame(gate_rows)
            gate_df.groupby("target_l1", as_index=False)[["gate_sequence", "gate_structure", "gate_context"]].mean().to_csv(
                export_dir / f"gates_by_l1_{split_name}.csv",
                index=False,
            )
            gate_df.groupby("target_l3_core", as_index=False)[["gate_sequence", "gate_structure", "gate_context"]].mean().to_csv(
                export_dir / f"gates_by_l3_{split_name}.csv",
                index=False,
            )
        dump_json(metrics, export_dir / f"metrics_{split_name}.json")
        if export_embeddings:
            torch.save(embedding_rows, export_dir / f"features_{split_name}.pt")
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
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


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
    assets = resolve_assets(config)
    validate_support_assets(config, assets)
    device = choose_device(config["training"]["device"])

    dataset = MultimodalCoreDataset.from_prepacked_dir(assets.prepacked_dir, split=args.split, limit=args.limit)
    vocab_l1 = load_vocab(resolve_path(config["data"]["vocab_l1"], REPO_ROOT))
    vocab_l2 = load_vocab(resolve_path(config["data"]["vocab_l2"], REPO_ROOT))
    vocab_l3 = load_vocab(resolve_path(config["data"]["vocab_l3_core"], REPO_ROOT))
    l3_to_l2, l2_to_l1 = dataset.hierarchy_maps(
        num_l1=len(vocab_l1),
        num_l2=len(vocab_l2),
        num_l3=len(vocab_l3),
    )
    dataloader = make_dataloader(
        dataset,
        batch_size=int(config["training"]["eval_batch_size"]),
        num_workers=int(config["training"]["num_workers"]),
        pin_memory=device.type == "cuda",
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
    )
    print(metrics)


if __name__ == "__main__":
    main()
