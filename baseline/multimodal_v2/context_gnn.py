from __future__ import annotations

import torch
from torch import nn


def _gather_center(x: torch.Tensor, center_index: torch.Tensor) -> torch.Tensor:
    if center_index.ndim != 1:
        raise ValueError("context_center_index must have shape [batch]")
    batch_index = torch.arange(x.shape[0], device=x.device)
    return x[batch_index, center_index]


class DenseGraphSAGELayer(nn.Module):
    def __init__(self, input_dim: int, output_dim: int, dropout: float = 0.1) -> None:
        super().__init__()
        self.self_proj = nn.Linear(input_dim, output_dim)
        self.neigh_proj = nn.Linear(input_dim, output_dim)
        self.norm = nn.LayerNorm(output_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        adjacency: torch.Tensor,
        node_mask: torch.Tensor,
    ) -> torch.Tensor:
        if x.ndim != 3:
            raise ValueError("x must have shape [batch, nodes, dim]")
        if adjacency.ndim != 3:
            raise ValueError("adjacency must have shape [batch, nodes, nodes]")
        if node_mask.ndim != 2:
            raise ValueError("node_mask must have shape [batch, nodes]")

        mask = node_mask.float()
        masked_adjacency = adjacency.float() * mask.unsqueeze(1) * mask.unsqueeze(2)
        degree = masked_adjacency.sum(dim=-1, keepdim=True).clamp(min=1.0)
        neigh = torch.bmm(masked_adjacency, x) / degree
        out = self.self_proj(x) + self.neigh_proj(neigh)
        out = self.norm(out)
        out = torch.nn.functional.gelu(out)
        out = self.dropout(out)
        return out * mask.unsqueeze(-1)


class DenseGraphSAGEContextEncoder(nn.Module):
    def __init__(
        self,
        node_input_dim: int,
        hidden_dim: int = 128,
        output_dim: int = 128,
        dropout: float = 0.1,
        use_center_residual: bool = False,
    ) -> None:
        super().__init__()
        self.use_center_residual = bool(use_center_residual)
        self.layer1 = DenseGraphSAGELayer(node_input_dim, hidden_dim, dropout=dropout)
        self.layer2 = DenseGraphSAGELayer(hidden_dim, output_dim, dropout=dropout)
        readout_dim = output_dim + hidden_dim if self.use_center_residual else output_dim
        self.readout_proj = nn.Sequential(
            nn.LayerNorm(readout_dim),
            nn.Linear(readout_dim, output_dim),
            nn.GELU(),
            nn.Dropout(dropout),
        )

    def forward(
        self,
        node_features: torch.Tensor,
        adjacency: torch.Tensor,
        node_mask: torch.Tensor,
        center_index: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        hidden1 = self.layer1(node_features, adjacency, node_mask)
        hidden2 = self.layer2(hidden1, adjacency, node_mask)

        center_l1 = _gather_center(hidden1, center_index)
        center_l2 = _gather_center(hidden2, center_index)
        if self.use_center_residual:
            center = torch.cat([center_l1, center_l2], dim=-1)
        else:
            center = center_l2
        center = self.readout_proj(center)
        return {
            "center_embedding": center,
            "layer1_center": center_l1,
            "layer2_center": center_l2,
        }
