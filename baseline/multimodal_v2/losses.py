from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn.functional as F
from torch import nn


@dataclass
class LossOutput:
    total: torch.Tensor
    l1: torch.Tensor
    l2: torch.Tensor
    l3: torch.Tensor
    hierarchy: torch.Tensor


class HierarchicalMultimodalLoss(nn.Module):
    def __init__(
        self,
        weight_l1: float = 0.5,
        weight_l2: float = 1.0,
        weight_l3: float = 1.2,
        class_weights_l1: torch.Tensor | None = None,
        class_weights_l2: torch.Tensor | None = None,
        class_weights_l3: torch.Tensor | None = None,
        hierarchy_loss_weight: float = 0.08,
        l3_to_l2: torch.Tensor | None = None,
        l2_to_l1: torch.Tensor | None = None,
    ) -> None:
        super().__init__()
        self.weight_l1 = float(weight_l1)
        self.weight_l2 = float(weight_l2)
        self.weight_l3 = float(weight_l3)
        self.hierarchy_loss_weight = float(hierarchy_loss_weight)
        self.ce_l1 = nn.CrossEntropyLoss(weight=class_weights_l1)
        self.ce_l2 = nn.CrossEntropyLoss(weight=class_weights_l2)
        self.ce_l3 = nn.CrossEntropyLoss(weight=class_weights_l3)
        self.register_buffer("l3_to_l2", l3_to_l2 if l3_to_l2 is not None else torch.empty(0, dtype=torch.long))
        self.register_buffer("l2_to_l1", l2_to_l1 if l2_to_l1 is not None else torch.empty(0, dtype=torch.long))

    def forward(
        self,
        logits_l1: torch.Tensor,
        logits_l2: torch.Tensor,
        logits_l3: torch.Tensor,
        target_l1: torch.Tensor,
        target_l2: torch.Tensor,
        target_l3: torch.Tensor,
    ) -> LossOutput:
        loss_l1 = self.ce_l1(logits_l1, target_l1)
        loss_l2 = self.ce_l2(logits_l2, target_l2)
        loss_l3 = self.ce_l3(logits_l3, target_l3)
        hierarchy_loss = logits_l1.new_tensor(0.0)
        if self.l3_to_l2.numel() > 0 and self.l2_to_l1.numel() > 0:
            hierarchy_loss = self._hierarchy_consistency(logits_l1, logits_l2, logits_l3)
        total = (
            self.weight_l1 * loss_l1
            + self.weight_l2 * loss_l2
            + self.weight_l3 * loss_l3
            + self.hierarchy_loss_weight * hierarchy_loss
        )
        return LossOutput(total=total, l1=loss_l1, l2=loss_l2, l3=loss_l3, hierarchy=hierarchy_loss)

    def _hierarchy_consistency(
        self,
        logits_l1: torch.Tensor,
        logits_l2: torch.Tensor,
        logits_l3: torch.Tensor,
    ) -> torch.Tensor:
        probs_l1 = torch.softmax(logits_l1, dim=-1)
        probs_l2 = torch.softmax(logits_l2, dim=-1)
        probs_l3 = torch.softmax(logits_l3, dim=-1)

        valid_l3 = self.l3_to_l2 >= 0
        valid_l2 = self.l2_to_l1 >= 0
        if not torch.any(valid_l3) or not torch.any(valid_l2):
            return logits_l1.new_tensor(0.0)

        agg_l2 = logits_l2.new_zeros(probs_l3.shape[0], probs_l2.shape[1])
        agg_l2.scatter_add_(
            1,
            self.l3_to_l2[valid_l3].unsqueeze(0).expand(probs_l3.shape[0], -1),
            probs_l3[:, valid_l3],
        )
        agg_l2 = agg_l2.clamp_min(1e-8)

        agg_l1 = logits_l1.new_zeros(probs_l2.shape[0], probs_l1.shape[1])
        agg_l1.scatter_add_(
            1,
            self.l2_to_l1[valid_l2].unsqueeze(0).expand(probs_l2.shape[0], -1),
            probs_l2[:, valid_l2],
        )
        agg_l1 = agg_l1.clamp_min(1e-8)

        kl_l3_l2 = F.kl_div(torch.log(probs_l2.clamp_min(1e-8)), agg_l2, reduction="batchmean")
        kl_l2_l1 = F.kl_div(torch.log(probs_l1.clamp_min(1e-8)), agg_l1, reduction="batchmean")
        return kl_l3_l2 + kl_l2_l1

