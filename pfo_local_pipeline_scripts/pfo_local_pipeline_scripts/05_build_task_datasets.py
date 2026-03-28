from pathlib import Path
import pandas as pd
from utils import load_config, resolve_path, ensure_dirs

cfg = load_config()
project_root = Path(cfg["project_root"])
proc_dir = resolve_path(project_root, cfg["paths"]["processed_dir"])
ensure_dirs(proc_dir)

df = pd.read_csv(proc_dir / "training_labels_wide.csv", low_memory=False)

l1 = df[df["level1_label"].fillna("").astype(str).str.len() > 0].copy()
l1.to_csv(proc_dir / "dataset_l1.csv", index=False, encoding="utf-8-sig")

l2 = df[df["level2_label"].fillna("").astype(str).str.len() > 0].copy()
l2.to_csv(proc_dir / "dataset_l2.csv", index=False, encoding="utf-8-sig")

l3_core = df[df["status"] == "trainable_core"].copy()
l3_core = l3_core[l3_core["node_primary"].fillna("").astype(str).str.len() > 0]
l3_core.to_csv(proc_dir / "dataset_l3_core.csv", index=False, encoding="utf-8-sig")

l3_multi = df[df["status"] == "trainable_multilabel"].copy()
l3_multi.to_csv(proc_dir / "dataset_l3_multilabel.csv", index=False, encoding="utf-8-sig")

open_set = df[df["status"] == "open_set"].copy()
open_set.to_csv(proc_dir / "dataset_open_set.csv", index=False, encoding="utf-8-sig")

parent_only = df[df["status"] == "parent_only"].copy()
parent_only.to_csv(proc_dir / "dataset_parent_only.csv", index=False, encoding="utf-8-sig")

defer = df[df["status"] == "defer"].copy()
defer.to_csv(proc_dir / "dataset_defer.csv", index=False, encoding="utf-8-sig")

print("[OK] saved task datasets to", proc_dir)
for name, sub in [
    ("l1", l1), ("l2", l2), ("l3_core", l3_core), ("l3_multilabel", l3_multi),
    ("open_set", open_set), ("parent_only", parent_only), ("defer", defer)
]:
    print(f"{name}: {len(sub)}")
