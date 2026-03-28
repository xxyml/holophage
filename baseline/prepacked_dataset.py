from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
from torch.utils.data import Dataset


class PrepackedCoreDataset(Dataset):
    REQUIRED_KEYS = {
        "embedding",
        "label_l1",
        "label_l2",
        "label_l3_core",
        "sequence_length",
        "protein_id",
        "embedding_id",
        "split",
        "split_strategy",
        "split_version",
        "homology_cluster_id",
        "exact_sequence_rep_id",
    }

    def __init__(self, pack_path: str | Path, limit: int | None = None) -> None:
        self.pack_path = Path(pack_path)
        if not self.pack_path.exists():
            raise FileNotFoundError(f"Prepacked dataset not found: {self.pack_path}")

        payload = torch.load(self.pack_path, map_location="cpu")
        missing = self.REQUIRED_KEYS - set(payload.keys())
        if missing:
            raise KeyError(
                f"Missing keys in prepacked dataset: {sorted(missing)}. "
                "This prepacked file is from an older schema; rebuild it with "
                "`python -m baseline.prepack_embeddings --overwrite` before enabling the sampler."
            )

        self.embedding: torch.Tensor = payload["embedding"].float().contiguous()
        self.label_l1: torch.Tensor = payload["label_l1"].long().contiguous()
        self.label_l2: torch.Tensor = payload["label_l2"].long().contiguous()
        self.label_l3_core: torch.Tensor = payload["label_l3_core"].long().contiguous()
        self.sequence_length: torch.Tensor = payload["sequence_length"].long().contiguous()
        self.protein_id: list[str] = [str(x) for x in payload["protein_id"]]
        self.embedding_id: list[str] = [str(x) for x in payload["embedding_id"]]
        self.split: str = str(payload["split"])
        self.split_strategy: list[str] = [str(x) for x in payload["split_strategy"]]
        self.split_version: list[str] = [str(x) for x in payload["split_version"]]
        self.homology_cluster_id: list[str] = [str(x) for x in payload["homology_cluster_id"]]
        self.exact_sequence_rep_id: list[str] = [str(x) for x in payload["exact_sequence_rep_id"]]

        expected = self.embedding.shape[0]
        if not (
            len(self.label_l1)
            == len(self.label_l2)
            == len(self.label_l3_core)
            == len(self.sequence_length)
            == len(self.protein_id)
            == len(self.embedding_id)
            == len(self.split_strategy)
            == len(self.split_version)
            == len(self.homology_cluster_id)
            == len(self.exact_sequence_rep_id)
            == expected
        ):
            raise ValueError(f"Prepacked dataset length mismatch in {self.pack_path}")

        if limit is not None:
            n = int(limit)
            self.embedding = self.embedding[:n]
            self.label_l1 = self.label_l1[:n]
            self.label_l2 = self.label_l2[:n]
            self.label_l3_core = self.label_l3_core[:n]
            self.sequence_length = self.sequence_length[:n]
            self.protein_id = self.protein_id[:n]
            self.embedding_id = self.embedding_id[:n]
            self.split_strategy = self.split_strategy[:n]
            self.split_version = self.split_version[:n]
            self.homology_cluster_id = self.homology_cluster_id[:n]
            self.exact_sequence_rep_id = self.exact_sequence_rep_id[:n]

    def __len__(self) -> int:
        return int(self.embedding.shape[0])

    def __getitem__(self, index: int) -> dict[str, Any]:
        return {
            "protein_id": self.protein_id[index],
            "embedding_id": self.embedding_id[index],
            "embedding": self.embedding[index],
            "label_l1": self.label_l1[index],
            "label_l2": self.label_l2[index],
            "label_l3_core": self.label_l3_core[index],
            "sequence_length": self.sequence_length[index],
            "split": self.split,
            "split_strategy": self.split_strategy[index],
            "split_version": self.split_version[index],
            "homology_cluster_id": self.homology_cluster_id[index],
            "exact_sequence_rep_id": self.exact_sequence_rep_id[index],
        }

    def class_weights(self, field: str, num_classes: int) -> torch.Tensor:
        if field not in {"label_l1", "label_l2", "label_l3_core"}:
            raise KeyError(f"Unsupported label field for class weights: {field}")
        labels = getattr(self, field)
        counts = torch.bincount(labels, minlength=num_classes).float()
        total = counts.sum().item()
        weights = torch.zeros(num_classes, dtype=torch.float32)
        nonzero = counts > 0
        weights[nonzero] = total / (float(num_classes) * counts[nonzero])
        return weights

    def hierarchy_maps(self) -> tuple[torch.Tensor, torch.Tensor]:
        num_l3 = int(torch.max(self.label_l3_core).item()) + 1
        num_l2 = int(torch.max(self.label_l2).item()) + 1
        l3_to_l2 = torch.full((num_l3,), -1, dtype=torch.long)
        l2_to_l1 = torch.full((num_l2,), -1, dtype=torch.long)

        for i in range(len(self)):
            l3 = int(self.label_l3_core[i].item())
            l2 = int(self.label_l2[i].item())
            l1 = int(self.label_l1[i].item())

            if l3_to_l2[l3] not in (-1, l2):
                raise ValueError(f"Conflicting L3->L2 mapping for class {l3}")
            l3_to_l2[l3] = l2

            if l2_to_l1[l2] not in (-1, l1):
                raise ValueError(f"Conflicting L2->L1 mapping for class {l2}")
            l2_to_l1[l2] = l1

        return l3_to_l2, l2_to_l1

    def sampler_frame(self):
        import pandas as pd

        return pd.DataFrame(
            {
                "row_index": range(len(self)),
                "homology_cluster_id": self.homology_cluster_id,
                "exact_sequence_rep_id": self.exact_sequence_rep_id,
                "label_l3_core": self.label_l3_core.tolist(),
            }
        )
