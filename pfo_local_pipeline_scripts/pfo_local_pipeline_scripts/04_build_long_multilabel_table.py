from pathlib import Path
import pandas as pd
from utils import load_config, resolve_path, ensure_dirs

cfg = load_config()
project_root = Path(cfg["project_root"])
proc_dir = resolve_path(project_root, cfg["paths"]["processed_dir"])
ensure_dirs(proc_dir)

wide_path = proc_dir / "training_labels_wide.csv"
df = pd.read_csv(wide_path, low_memory=False)

rows = []
for _, r in df.iterrows():
    primary_raw = r.get("node_primary", "")
    primary = "" if pd.isna(primary_raw) else str(primary_raw).strip()
    if primary:
        rows.append({
            "protein_id": r["protein_id"],
            "genome_id": r["genome_id"],
            "annotation_normalized": r["annotation_normalized"],
            "level1_label": r["level1_label"],
            "level2_label": r["level2_label"],
            "node_name": primary,
            "label_role": "primary",
            "status": r["status"],
        })

    secondary_raw = r.get("secondary_node", "")
    secondary = "" if pd.isna(secondary_raw) else str(secondary_raw).strip()
    if secondary:
        rows.append({
            "protein_id": r["protein_id"],
            "genome_id": r["genome_id"],
            "annotation_normalized": r["annotation_normalized"],
            "level1_label": r.get("secondary_level1", ""),
            "level2_label": r.get("secondary_level2", ""),
            "node_name": secondary,
            "label_role": "secondary",
            "status": r["status"],
        })

long_df = pd.DataFrame(rows)
out_path = proc_dir / "training_labels_long.csv"
long_df.to_csv(out_path, index=False, encoding="utf-8-sig")
print(f"[OK] saved: {out_path}")
print(long_df.head().to_string(index=False))
