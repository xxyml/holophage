from __future__ import annotations

import torch
from torch import nn

from .adapters import ModalityAdapter, ModalityDropout, ResidualMLP
from .fusion import SoftmaxGatedFusion
from .heads import ConditionalHierarchicalHeads


class MultimodalBaselineV2(nn.Module):
    def __init__(
        self,
        sequence_input_dim: int,
        structure_input_dim: int,
        context_input_dim: int,
        fusion_dim: int,
        adapter_hidden_dim: int,
        trunk_hidden_dim: int,
        trunk_hidden_dim2: int,
        dropout: float,
        modality_dropout: float,
        num_l1: int,
        num_l2: int,
        num_l3: int,
        use_sequence: bool = True,
        use_structure: bool = True,
        use_context: bool = True,
    ) -> None:
        super().__init__()
        self.sequence_input_dim = int(sequence_input_dim)
        self.structure_input_dim = int(structure_input_dim)
        self.context_input_dim = int(context_input_dim)
        self.fusion_dim = int(fusion_dim)
        self.use_sequence = bool(use_sequence)
        self.use_structure = bool(use_structure)
        self.use_context = bool(use_context)
        self.modality_dropout = ModalityDropout(modality_dropout, preserve_sequence=True)

        self.sequence_adapter = ModalityAdapter(sequence_input_dim, fusion_dim, hidden_dim=adapter_hidden_dim, dropout=dropout)
        self.structure_adapter = ModalityAdapter(structure_input_dim, fusion_dim, hidden_dim=adapter_hidden_dim, dropout=dropout)
        self.context_adapter = ModalityAdapter(context_input_dim, fusion_dim, hidden_dim=adapter_hidden_dim, dropout=dropout)
        self.fusion = SoftmaxGatedFusion(fusion_dim, fusion_dim, num_modalities=3, gate_hidden_dim=adapter_hidden_dim, dropout=dropout)
        self.trunk = ResidualMLP(fusion_dim, trunk_hidden_dim, trunk_hidden_dim2, dropout=dropout)
        self.heads = ConditionalHierarchicalHeads(trunk_hidden_dim2, trunk_hidden_dim, num_l1, num_l2, num_l3, dropout=dropout)

    def _default_modality_mask(self, sequence_embedding: torch.Tensor) -> torch.Tensor:
        batch = sequence_embedding.shape[0]
        device = sequence_embedding.device
        mask = torch.ones((batch, 3), dtype=torch.bool, device=device)
        if not self.use_sequence:
            mask[:, 0] = False
        if not self.use_structure:
            mask[:, 1] = False
        if not self.use_context:
            mask[:, 2] = False
        return mask

    def _zero_latent(self, batch: int, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
        return torch.zeros((batch, self.fusion_dim), device=device, dtype=dtype)

    def _encode_or_zero(
        self,
        enabled: bool,
        adapter: ModalityAdapter,
        x: torch.Tensor,
        batch: int,
        device: torch.device,
        dtype: torch.dtype,
    ) -> torch.Tensor:
        if not enabled:
            return self._zero_latent(batch, device, dtype)
        return adapter(x)

    def forward(
        self,
        sequence_embedding: torch.Tensor,
        structure_embedding: torch.Tensor | None = None,
        context_features: torch.Tensor | None = None,
        modality_mask: torch.Tensor | None = None,
        missing_modality_mask: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        if sequence_embedding.ndim != 2:
            raise ValueError("sequence_embedding must be 2D [batch, dim]")
        batch = sequence_embedding.shape[0]
        device = sequence_embedding.device
        dtype = sequence_embedding.dtype

        if structure_embedding is None:
            structure_embedding = torch.zeros((batch, self.structure_input_dim), device=device, dtype=dtype)
        if context_features is None:
            context_features = torch.zeros((batch, self.context_input_dim), device=device, dtype=dtype)
        if modality_mask is None:
            modality_mask = self._default_modality_mask(sequence_embedding)

        if modality_mask.ndim != 2 or modality_mask.shape[1] != 3:
            raise ValueError("modality_mask must have shape [batch, 3]")
        modality_mask = modality_mask.bool()
        if missing_modality_mask is not None:
            if missing_modality_mask.ndim != 2 or missing_modality_mask.shape[1] != 3:
                raise ValueError("missing_modality_mask must have shape [batch, 3]")
            modality_mask = modality_mask & ~missing_modality_mask.bool()
        modality_mask = self.modality_dropout(modality_mask)

        seq = self._encode_or_zero(self.use_sequence, self.sequence_adapter, sequence_embedding, batch, device, dtype)
        struct = self._encode_or_zero(self.use_structure, self.structure_adapter, structure_embedding, batch, device, dtype)
        ctx = self._encode_or_zero(self.use_context, self.context_adapter, context_features, batch, device, dtype)

        masks = modality_mask.float().unsqueeze(-1)
        seq = seq * masks[:, 0]
        struct = struct * masks[:, 1]
        ctx = ctx * masks[:, 2]

        fused, gates, base = self.fusion([seq, struct, ctx], modality_mask=modality_mask)
        features = self.trunk(fused)
        outputs = self.heads(features)
        return {
            "features": features,
            "fusion_base": base,
            "fusion_gates": gates,
            "modality_mask": modality_mask,
            "sequence_latent": seq,
            "structure_latent": struct,
            "context_latent": ctx,
            **outputs,
        }
