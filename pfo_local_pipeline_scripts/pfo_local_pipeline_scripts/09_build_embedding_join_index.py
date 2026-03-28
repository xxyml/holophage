from pathlib import Path
import pandas as pd
from utils import load_config, resolve_path, ensure_dirs


cfg = load_config()
project_root = Path(cfg["project_root"])
proc_dir = resolve_path(project_root, cfg["paths"]["processed_dir"])
ensure_dirs(proc_dir)

wide_path = proc_dir / "training_labels_wide_with_split.csv"
wide = pd.read_csv(wide_path, low_memory=False)

wide["embedding_id"] = wide["contig_id"].astype(str) + "_" + wide["gene_index"].astype(str)
wide["sequence_embedding_key"] = wide["exact_sequence_rep_id"].astype(str)

keep_cols = [
    "protein_id",
    "embedding_id",
    "sequence_embedding_key",
    "genome_id",
    "contig_id",
    "gene_index",
    "sequence_length",
    "split",
    "split_strategy",
    "split_version",
    "exact_sequence_rep_id",
    "homology_cluster_id",
    "status",
    "level1_label",
    "level2_label",
    "node_primary",
    "multi_label_flag",
]

available_cols = [c for c in keep_cols if c in wide.columns]
index_df = wide[available_cols].copy()

out_path = proc_dir / "baseline_embedding_join_index.csv"
index_df.to_csv(out_path, index=False, encoding="utf-8-sig")

print(f"[OK] saved: {out_path}")
print(index_df.head().to_string(index=False))
