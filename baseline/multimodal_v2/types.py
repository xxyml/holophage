from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import torch


MULTIMODAL_PACK_SCHEMA_VERSION = "multimodal_core_v1"
MODALITY_NAMES = ("sequence", "structure", "context")
MODALITY_INDEX = {name: idx for idx, name in enumerate(MODALITY_NAMES)}

DEFAULT_SEQUENCE_EMBEDDING_DIM = 1024
DEFAULT_STRUCTURE_EMBEDDING_DIM = 1280
CONTEXT_FEATURE_DIM = 18

CONTEXT_FEATURE_NAMES = (
    "center_len_norm",
    "neighbor_count_norm",
    "has_left_1",
    "has_right_1",
    "has_left_2",
    "has_right_2",
    "left_1_len_norm",
    "right_1_len_norm",
    "left_2_len_norm",
    "right_2_len_norm",
    "left_1_same_strand",
    "right_1_same_strand",
    "left_2_same_strand",
    "right_2_same_strand",
    "left_1_has_phrog",
    "right_1_has_phrog",
    "left_2_has_phrog",
    "right_2_has_phrog",
)


class MultimodalIds(TypedDict):
    protein_id: str
    embedding_id: str
    exact_sequence_rep_id: str
    context_key: str


class MultimodalLabels(TypedDict):
    l1: int
    l2: int
    l3_core: int


class MultimodalBatch(TypedDict, total=False):
    ids: MultimodalIds
    labels: MultimodalLabels
    protein_id: str
    embedding_id: str
    exact_sequence_rep_id: str
    context_key: str
    label_l1: torch.Tensor
    label_l2: torch.Tensor
    label_l3_core: torch.Tensor
    sequence_embedding: torch.Tensor
    structure_embedding: torch.Tensor
    context_features: torch.Tensor
    modality_mask: torch.Tensor
    split: str
    split_strategy: str
    split_version: str
    homology_cluster_id: str
    status: str
    sequence_length: torch.Tensor


@dataclass(frozen=True)
class MultimodalPaths:
    label_table_csv: Path
    join_index_csv: Path
    sequence_embedding_db: Path
    sequence_embedding_dir: Path
    structure_embedding_dir: Path
    context_source_path: Path
    prepacked_dir: Path


@dataclass(frozen=True)
class MultimodalPackConfig:
    split: str
    schema_version: str = MULTIMODAL_PACK_SCHEMA_VERSION
    sequence_dim: int = DEFAULT_SEQUENCE_EMBEDDING_DIM
    structure_dim: int = DEFAULT_STRUCTURE_EMBEDDING_DIM
    context_dim: int = CONTEXT_FEATURE_DIM
    dtype: str = "float32"
    target_status: str = "trainable_core"
    sequence_key: str = "exact_sequence_rep_id"
    structure_key: str = "exact_sequence_rep_id"
    context_key: str = "protein_id"


def build_modality_mask(
    sequence_present: bool = True,
    structure_present: bool = False,
    context_present: bool = False,
) -> torch.Tensor:
    return torch.tensor([sequence_present, structure_present, context_present], dtype=torch.bool)


def build_ids(
    protein_id: str,
    embedding_id: str,
    exact_sequence_rep_id: str,
    context_key: str | None = None,
) -> MultimodalIds:
    return {
        "protein_id": str(protein_id),
        "embedding_id": str(embedding_id),
        "exact_sequence_rep_id": str(exact_sequence_rep_id),
        "context_key": str(context_key if context_key is not None else protein_id),
    }


def build_labels(label_l1: int, label_l2: int, label_l3_core: int) -> MultimodalLabels:
    return {
        "l1": int(label_l1),
        "l2": int(label_l2),
        "l3_core": int(label_l3_core),
    }
