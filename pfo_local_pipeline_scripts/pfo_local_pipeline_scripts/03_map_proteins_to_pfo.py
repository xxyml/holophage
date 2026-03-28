from pathlib import Path
import pandas as pd
from utils import load_config, resolve_path, ensure_dirs, safe_read_table

cfg = load_config()
project_root = Path(cfg["project_root"])

inter_dir = resolve_path(project_root, cfg["paths"]["intermediate_dir"])
proc_dir = resolve_path(project_root, cfg["paths"]["processed_dir"])
ensure_dirs(proc_dir)

protein_path = inter_dir / "protein_master_standardized.csv"
mapping_path = resolve_path(project_root, cfg["paths"]["mapping_table"])

protein_df = pd.read_csv(protein_path, low_memory=False)
mapping_df = safe_read_table(mapping_path, sep=",", encoding="utf-8")

mcol = cfg["mapping_columns"]
required = [mcol["annotation"], mcol["level1_direct"], mcol["level2_primary"], mcol["node_primary"], mcol["status"]]
missing = [c for c in required if c not in mapping_df.columns]
if missing:
    raise ValueError(f"Missing required columns in mapping table: {missing}")

rename_map = {
    mcol["annotation"]: "annotation_normalized",
    mcol["level1_direct"]: "level1_label",
    mcol["level2_primary"]: "level2_label",
    mcol["node_primary"]: "node_primary",
    mcol["status"]: "status",
}

for k in ["multi_label_flag", "secondary_level1", "secondary_level2", "secondary_node"]:
    src = mcol.get(k)
    if src and src in mapping_df.columns:
        rename_map[src] = k

mapping_df = mapping_df.rename(columns=rename_map)

for k in ["multi_label_flag", "secondary_level1", "secondary_level2", "secondary_node"]:
    if k not in mapping_df.columns:
        mapping_df[k] = ""

keep_cols = [
    "annotation_normalized",
    "level1_label",
    "level2_label",
    "node_primary",
    "status",
    "multi_label_flag",
    "secondary_level1",
    "secondary_level2",
    "secondary_node",
]
mapping_df = mapping_df[keep_cols].drop_duplicates()

merged = protein_df.merge(mapping_df, on="annotation_normalized", how="left")

merged["status"] = merged["status"].fillna("open_set")
for c in ["level1_label", "level2_label", "node_primary", "secondary_level1", "secondary_level2", "secondary_node"]:
    merged[c] = merged[c].fillna("")
merged["multi_label_flag"] = merged["multi_label_flag"].fillna("no")

merged["is_open_set"] = (merged["status"] == "open_set").astype(int)
merged["is_parent_only"] = (merged["status"] == "parent_only").astype(int)
merged["is_multilabel"] = (merged["multi_label_flag"].astype(str).str.lower() == "yes").astype(int)
merged["ontology_version"] = "PFO_v1.0.2"

out_path = proc_dir / "training_labels_wide.csv"
merged.to_csv(out_path, index=False, encoding="utf-8-sig")

print(f"[OK] saved: {out_path}")
print("\n[INFO] status counts:")
print(merged["status"].value_counts(dropna=False).to_string())
