from __future__ import annotations

import torch
from torch import nn


class BaselineMultiHeadModel(nn.Module):
    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        hidden_dim2: int,
        dropout: float,
        num_l1: int,
        num_l2: int,
        num_l3: int,
    ) -> None:
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim2),
            nn.LayerNorm(hidden_dim2),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.head_l1 = nn.Linear(hidden_dim2, num_l1)
        self.head_l2 = nn.Linear(hidden_dim2, num_l2)
        self.head_l3 = nn.Linear(hidden_dim2, num_l3)

    def forward(self, embedding: torch.Tensor) -> dict[str, torch.Tensor]:
        features = self.backbone(embedding)
        return {
            "features": features,
            "logits_l1": self.head_l1(features),
            "logits_l2": self.head_l2(features),
            "logits_l3": self.head_l3(features),
        }
