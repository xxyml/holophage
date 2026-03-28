from __future__ import annotations

from pathlib import Path

import pandas as pd

from utils import dump_json, ensure_dirs, load_config, resolve_path


cfg = load_config()
project_root = Path(cfg["project_root"])
proc_dir = resolve_path(project_root, cfg["paths"]["processed_dir"])
splits_dir = resolve_path(project_root, cfg["paths"]["splits_dir"])
ensure_dirs(splits_dir)

wide_path = proc_dir / "training_labels_wide.csv"
hom_cfg = cfg["split"].get("homology", {})

fasta_path = resolve_path(project_root, hom_cfg["fasta_path"])
summary_path = resolve_path(project_root, hom_cfg["fasta_summary_json"])
ensure_dirs(fasta_path.parent)

total_rows = 0
exported_rows = 0
blank_sequence_rows = 0

with fasta_path.open("w", encoding="utf-8", newline="\n") as fout:
    for chunk in pd.read_csv(
        wide_path,
        usecols=["protein_id", "sequence"],
        chunksize=100000,
        low_memory=False,
    ):
        for row in chunk.itertuples(index=False):
            total_rows += 1
            protein_id = str(row.protein_id).strip()
            sequence = "" if pd.isna(row.sequence) else str(row.sequence).strip()
            if not sequence:
                blank_sequence_rows += 1
                continue
            fout.write(f">{protein_id}\n{sequence}\n")
            exported_rows += 1

summary = {
    "source_csv": str(wide_path),
    "fasta_path": str(fasta_path),
    "total_rows": total_rows,
    "exported_rows": exported_rows,
    "blank_sequence_rows": blank_sequence_rows,
}
dump_json(summary_path, summary)

print(f"[OK] saved FASTA: {fasta_path}")
print(f"[OK] saved summary: {summary_path}")
print(summary)
