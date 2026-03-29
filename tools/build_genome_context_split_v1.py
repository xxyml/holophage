from __future__ import annotations

import json
import random
from pathlib import Path
import sys

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_TABLE = REPO_ROOT / "data_processed" / "training_labels_wide_with_split.csv"
OUTPUT_CSV = REPO_ROOT / "splits" / "split_by_genome_context_v1.csv"
OUTPUT_SUMMARY = REPO_ROOT / "splits" / "split_by_genome_context_v1.summary.json"
RNG_SEED = 20260329
TRAIN_RATIO = 0.70
VAL_RATIO = 0.15


def main() -> None:
    df = pd.read_csv(
        MAIN_TABLE,
        usecols=["protein_id", "genome_id", "contig_id"],
        low_memory=False,
    )
    df["protein_id"] = df["protein_id"].astype(str)
    df["genome_id"] = df["genome_id"].astype(str)
    df["contig_id"] = df["contig_id"].astype(str)

    genome_ids = sorted(df["genome_id"].dropna().astype(str).unique().tolist())
    rng = random.Random(RNG_SEED)
    rng.shuffle(genome_ids)

    total = len(genome_ids)
    train_cut = int(total * TRAIN_RATIO)
    val_cut = int(total * (TRAIN_RATIO + VAL_RATIO))

    train_genomes = set(genome_ids[:train_cut])
    val_genomes = set(genome_ids[train_cut:val_cut])
    test_genomes = set(genome_ids[val_cut:])

    def assign_split(genome_id: str) -> str:
        if genome_id in train_genomes:
            return "train"
        if genome_id in val_genomes:
            return "val"
        return "test"

    out = df[["protein_id", "genome_id", "contig_id"]].copy()
    out["split"] = out["genome_id"].map(assign_split)
    out["split_strategy"] = "genome_context"
    out["split_version"] = "genome_context_v1"

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT_CSV, index=False)

    summary = {
        "seed": RNG_SEED,
        "split_strategy": "genome_context",
        "split_version": "genome_context_v1",
        "split_unit": "genome_id",
        "allow_homology_cluster_cross_split": True,
        "genomes": {
            "train": len(train_genomes),
            "val": len(val_genomes),
            "test": len(test_genomes),
        },
        "proteins": out["split"].value_counts().sort_index().to_dict(),
        "output_csv": str(OUTPUT_CSV),
    }
    OUTPUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
