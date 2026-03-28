from __future__ import annotations

import torch
from torch import nn


class SoftmaxGatedFusion(nn.Module):
    def __init__(
        self,
        input_dim: int,
        fusion_dim: int,
        num_modalities: int = 3,
        gate_hidden_dim: int | None = None,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.num_modalities = int(num_modalities)
        gate_hidden_dim = gate_hidden_dim or max(fusion_dim, input_dim)
        self.base_proj = nn.Sequential(
            nn.Linear(input_dim * self.num_modalities, fusion_dim),
            nn.LayerNorm(fusion_dim),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.gate_proj = nn.Sequential(
            nn.Linear(input_dim * self.num_modalities + self.num_modalities, gate_hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(gate_hidden_dim, self.num_modalities),
        )

    def forward(
        self,
        modalities: list[torch.Tensor],
        modality_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        if len(modalities) != self.num_modalities:
            raise ValueError(f"Expected {self.num_modalities} modalities, got {len(modalities)}")
        stacked = torch.cat(modalities, dim=-1)
        if modality_mask is None:
            modality_mask = torch.ones(stacked.shape[0], self.num_modalities, device=stacked.device, dtype=torch.bool)
        if modality_mask.ndim != 2 or modality_mask.shape[1] != self.num_modalities:
            raise ValueError("modality_mask must have shape [batch, num_modalities]")
        masked_modalities = []
        for i, modality in enumerate(modalities):
            mask = modality_mask[:, i].float().unsqueeze(-1)
            masked_modalities.append(modality * mask)
        masked_stacked = torch.cat(masked_modalities, dim=-1)
        base = self.base_proj(masked_stacked)
        gate_logits = self.gate_proj(torch.cat([masked_stacked, modality_mask.float()], dim=-1))
        gate_logits = gate_logits.masked_fill(~modality_mask.bool(), -1e4)
        gates = torch.softmax(gate_logits, dim=-1)
        fused = base
        for i, modality in enumerate(masked_modalities):
            fused = fused + gates[:, i : i + 1] * modality
        return fused, gates, base

