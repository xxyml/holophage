from __future__ import annotations

import torch
from torch import nn


class _HeadBlock(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int, dropout: float) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.LayerNorm(input_dim),
            nn.Linear(input_dim, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class ConditionalHierarchicalHeads(nn.Module):
    def __init__(
        self,
        hidden_dim: int,
        hidden_dim2: int,
        num_l1: int,
        num_l2: int,
        num_l3: int,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.l1_backbone = _HeadBlock(hidden_dim, hidden_dim2, hidden_dim, dropout)
        self.head_l1 = nn.Linear(hidden_dim, num_l1)
        self.l2_backbone = _HeadBlock(hidden_dim + num_l1, hidden_dim2, hidden_dim, dropout)
        self.head_l2 = nn.Linear(hidden_dim, num_l2)
        self.l3_backbone = _HeadBlock(hidden_dim + num_l2, hidden_dim2, hidden_dim, dropout)
        self.head_l3 = nn.Linear(hidden_dim, num_l3)

    def forward(self, features: torch.Tensor) -> dict[str, torch.Tensor]:
        l1_hidden = self.l1_backbone(features)
        logits_l1 = self.head_l1(l1_hidden)
        probs_l1 = torch.softmax(logits_l1, dim=-1)

        l2_input = torch.cat([features, probs_l1], dim=-1)
        l2_hidden = self.l2_backbone(l2_input)
        logits_l2 = self.head_l2(l2_hidden)
        probs_l2 = torch.softmax(logits_l2, dim=-1)

        l3_input = torch.cat([features, probs_l2], dim=-1)
        l3_hidden = self.l3_backbone(l3_input)
        logits_l3 = self.head_l3(l3_hidden)
        probs_l3 = torch.softmax(logits_l3, dim=-1)

        return {
            "logits_l1": logits_l1,
            "logits_l2": logits_l2,
            "logits_l3": logits_l3,
            "probs_l1": probs_l1,
            "probs_l2": probs_l2,
            "probs_l3": probs_l3,
        }

