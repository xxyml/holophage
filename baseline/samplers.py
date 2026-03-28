from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd
import torch
from torch.utils.data import Sampler


def _build_generator(seed: int, epoch: int) -> torch.Generator:
    generator = torch.Generator()
    generator.manual_seed(int(seed) + int(epoch))
    return generator


@dataclass
class SamplerMetadata:
    mode: str
    seed: int
    samples_per_epoch: int


class EpochAwareSampler(Sampler[int]):
    def __init__(self, seed: int, num_samples: int) -> None:
        self.seed = int(seed)
        self.num_samples = int(num_samples)
        self.epoch = 0

    def __len__(self) -> int:
        return self.num_samples

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)


class RandomFixedEpochSampler(EpochAwareSampler):
    def __init__(self, dataset_size: int, seed: int, num_samples: int) -> None:
        super().__init__(seed=seed, num_samples=num_samples)
        self.dataset_size = int(dataset_size)
        if self.dataset_size <= 0:
            raise ValueError("dataset_size must be positive for RandomFixedEpochSampler")

    def __iter__(self) -> Iterable[int]:
        generator = _build_generator(self.seed, self.epoch)
        remaining = self.num_samples
        while remaining > 0:
            perm = torch.randperm(self.dataset_size, generator=generator).tolist()
            take = min(remaining, self.dataset_size)
            for index in perm[:take]:
                yield int(index)
            remaining -= take


class ClusterExactBalancedSampler(EpochAwareSampler):
    def __init__(
        self,
        sampler_frame: pd.DataFrame,
        seed: int,
        num_samples: int,
        cluster_weight_power: float = 1.0,
        exact_weight_power: float = 1.0,
        shuffle_within_group: bool = True,
    ) -> None:
        super().__init__(seed=seed, num_samples=num_samples)
        required = {"row_index", "homology_cluster_id", "exact_sequence_rep_id"}
        missing = required - set(sampler_frame.columns)
        if missing:
            raise KeyError(f"sampler_frame missing columns: {sorted(missing)}")

        self.shuffle_within_group = bool(shuffle_within_group)
        self.cluster_entries: list[dict[str, object]] = []

        cluster_sizes = sampler_frame["homology_cluster_id"].value_counts().to_dict()
        for cluster_id, cluster_df in sampler_frame.groupby("homology_cluster_id", sort=False):
            exact_entries: list[dict[str, object]] = []
            exact_sizes = cluster_df["exact_sequence_rep_id"].value_counts().to_dict()
            for exact_id, exact_df in cluster_df.groupby("exact_sequence_rep_id", sort=False):
                row_indices = exact_df["row_index"].astype("int64").tolist()
                exact_entries.append(
                    {
                        "exact_sequence_rep_id": str(exact_id),
                        "row_indices": row_indices,
                        "weight": 1.0 / (float(exact_sizes[exact_id]) ** float(exact_weight_power)),
                    }
                )
            cluster_weight = 1.0 / (float(cluster_sizes[cluster_id]) ** float(cluster_weight_power))
            exact_weight_tensor = torch.tensor([float(entry["weight"]) for entry in exact_entries], dtype=torch.float)
            exact_weight_tensor = exact_weight_tensor / exact_weight_tensor.sum()
            self.cluster_entries.append(
                {
                    "homology_cluster_id": str(cluster_id),
                    "weight": cluster_weight,
                    "exact_entries": exact_entries,
                    "exact_weights": exact_weight_tensor,
                }
            )

        cluster_weights = torch.tensor([float(entry["weight"]) for entry in self.cluster_entries], dtype=torch.float)
        self.cluster_weights = cluster_weights / cluster_weights.sum()

    def __iter__(self) -> Iterable[int]:
        generator = _build_generator(self.seed, self.epoch)
        for _ in range(self.num_samples):
            cluster_idx = int(torch.multinomial(self.cluster_weights, 1, replacement=True, generator=generator).item())
            cluster_entry = self.cluster_entries[cluster_idx]
            exact_entries = cluster_entry["exact_entries"]  # type: ignore[assignment]
            exact_weights = cluster_entry["exact_weights"]  # type: ignore[assignment]
            exact_idx = int(torch.multinomial(exact_weights, 1, replacement=True, generator=generator).item())
            row_indices = exact_entries[exact_idx]["row_indices"]  # type: ignore[index]
            if self.shuffle_within_group:
                selected = int(torch.randint(len(row_indices), (1,), generator=generator).item())
                yield int(row_indices[selected])
            else:
                yield int(row_indices[0])


def build_train_sampler(config: dict, dataset) -> EpochAwareSampler:
    sampler_cfg = config["training"].get("sampler", {}) or {}
    seed = int(sampler_cfg.get("seed", config["run"]["seed"]))
    enabled = bool(sampler_cfg.get("enabled", True))
    mode = str(sampler_cfg.get("mode", "cluster_exact_balanced"))
    default_samples = len(dataset)
    num_samples = int(sampler_cfg.get("samples_per_epoch") or default_samples)
    if num_samples <= 0:
        raise ValueError("training.sampler.samples_per_epoch must be positive")

    if not enabled or mode == "random":
        return RandomFixedEpochSampler(dataset_size=len(dataset), seed=seed, num_samples=num_samples)
    if mode == "cluster_exact_balanced":
        frame = dataset.sampler_frame()
        return ClusterExactBalancedSampler(
            sampler_frame=frame,
            seed=seed,
            num_samples=num_samples,
            cluster_weight_power=float(sampler_cfg.get("cluster_weight_power", 1.0)),
            exact_weight_power=float(sampler_cfg.get("exact_weight_power", 1.0)),
            shuffle_within_group=bool(sampler_cfg.get("shuffle_within_group", True)),
        )
    raise ValueError(f"Unsupported training.sampler.mode: {mode}")
