from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn


class ModalityAdapter(nn.Module):
    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        hidden_dim: int | None = None,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        hidden_dim = hidden_dim or max(input_dim, output_dim)
        self.net = nn.Sequential(
            nn.LayerNorm(input_dim),
            nn.Linear(input_dim, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, output_dim),
            nn.LayerNorm(output_dim),
            nn.GELU(),
            nn.Dropout(dropout),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class ResidualMLP(nn.Module):
    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        hidden_dim2: int,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.norm1 = nn.LayerNorm(hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim2)
        self.norm2 = nn.LayerNorm(hidden_dim2)
        self.proj = nn.Linear(input_dim, hidden_dim2) if input_dim != hidden_dim2 else nn.Identity()
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = self.proj(x)
        x = self.fc1(x)
        x = self.norm1(x)
        x = torch.nn.functional.gelu(x)
        x = self.dropout(x)
        x = self.fc2(x)
        x = self.norm2(x)
        x = torch.nn.functional.gelu(x)
        x = self.dropout(x)
        return x + residual


class ModalityDropout(nn.Module):
    def __init__(self, drop_prob: float = 0.0, preserve_sequence: bool = True) -> None:
        super().__init__()
        self.drop_prob = float(drop_prob)
        self.preserve_sequence = bool(preserve_sequence)

    def forward(self, modality_mask: torch.Tensor) -> torch.Tensor:
        if not self.training or self.drop_prob <= 0.0:
            return modality_mask
        if modality_mask.ndim != 2:
            raise ValueError("modality_mask must be 2D [batch, modalities]")
        keep = torch.rand_like(modality_mask.float()) > self.drop_prob
        if self.preserve_sequence and keep.shape[1] > 0:
            keep[:, 0] = True
        return modality_mask.bool() & keep.bool()

