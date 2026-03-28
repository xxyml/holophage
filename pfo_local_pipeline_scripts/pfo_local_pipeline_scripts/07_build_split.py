from pathlib import Path
import random
import pandas as pd
from utils import dump_json, load_config, resolve_path, ensure_dirs


def greedy_balanced_assignment(unit_df, train_ratio, val_ratio, test_ratio, random_state, alpha=0.5):
    split_order = ["train", "val", "test"]
    target_total = {
        "train": unit_df["total_count"].sum() * train_ratio,
        "val": unit_df["total_count"].sum() * val_ratio,
        "test": unit_df["total_count"].sum() * test_ratio,
    }
    target_supervised = {
        "train": unit_df["supervised_count"].sum() * train_ratio,
        "val": unit_df["supervised_count"].sum() * val_ratio,
        "test": unit_df["supervised_count"].sum() * test_ratio,
    }
    current_total = {k: 0 for k in split_order}
    current_supervised = {k: 0 for k in split_order}

    items = unit_df.to_dict("records")
    rng = random.Random(random_state)
    rng.shuffle(items)
    items.sort(key=lambda x: (x["total_count"], x["supervised_count"]), reverse=True)

    assignments = {}
    for item in items:
        unit_id = item["unit_id"]
        best_split = None
        best_score = None
        for split_name in split_order:
            total_deficit = (target_total[split_name] - current_total[split_name]) / max(
                target_total[split_name], 1.0
            )
            supervised_deficit = (target_supervised[split_name] - current_supervised[split_name]) / max(
                target_supervised[split_name], 1.0
            )
            score = total_deficit + alpha * supervised_deficit
            if best_score is None or score > best_score:
                best_score = score
                best_split = split_name
        assignments[unit_id] = best_split
        current_total[best_split] += item["total_count"]
        current_supervised[best_split] += item["supervised_count"]

    return assignments, current_total, current_supervised


cfg = load_config()
project_root = Path(cfg["project_root"])
proc_dir = resolve_path(project_root, cfg["paths"]["processed_dir"])
splits_dir = resolve_path(project_root, cfg["paths"]["splits_dir"])
ensure_dirs(splits_dir)

df = pd.read_csv(proc_dir / "training_labels_wide.csv", low_memory=False)

strategy = cfg["split"]["strategy"]
split_version = str(cfg["split"].get("version", f"{strategy}_v1"))
random_state = int(cfg["split"]["random_state"])
train_ratio = float(cfg["split"]["train_ratio"])
val_ratio = float(cfg["split"]["val_ratio"])
test_ratio = float(cfg["split"]["test_ratio"])

if abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-6:
    raise ValueError("train_ratio + val_ratio + test_ratio must equal 1.0")

if strategy == "genome":
    unit_col = "genome_id"
    df["unit_id"] = df[unit_col].astype(str)
    split_extra_cols = []
    split_filename = f"split_by_{split_version}.csv"
elif strategy == "homology_cluster":
    hom_cfg = cfg["split"].get("homology", {})
    membership_path = resolve_path(project_root, hom_cfg["membership_tsv"])
    if not membership_path.exists():
        raise FileNotFoundError(
            f"Missing homology membership file: {membership_path}. "
            "Run 07a/07b/07c before 07_build_split.py."
        )
    membership = pd.read_csv(membership_path, sep="\t", low_memory=False)
    required_cols = {"protein_id", "exact_sequence_rep_id", "homology_cluster_id"}
    missing_cols = required_cols - set(membership.columns)
    if missing_cols:
        raise ValueError(f"Membership TSV missing required columns: {sorted(missing_cols)}")
    df = df.merge(membership, on="protein_id", how="left")
    if df["homology_cluster_id"].isna().any():
        missing_n = int(df["homology_cluster_id"].isna().sum())
        raise ValueError(f"{missing_n} proteins are missing homology cluster assignment.")
    df["unit_id"] = df["homology_cluster_id"].astype(str)
    split_extra_cols = ["exact_sequence_rep_id", "homology_cluster_id"]
    split_filename = f"split_by_{split_version}.csv"
else:
    raise NotImplementedError(f"Unsupported split strategy: {strategy}")

unit_stats = (
    df.groupby("unit_id", dropna=False)
    .agg(
        total_count=("protein_id", "size"),
        supervised_count=("status", lambda s: int((s.fillna("") != "open_set").sum())),
    )
    .reset_index()
)

alpha = float(cfg["split"].get("homology", {}).get("balance_alpha", 0.5))
assignments, current_total, current_supervised = greedy_balanced_assignment(
    unit_stats, train_ratio, val_ratio, test_ratio, random_state, alpha=alpha
)
df["split"] = df["unit_id"].map(assignments).fillna("unassigned")
df["split_strategy"] = strategy
df["split_version"] = split_version

split_cols = ["protein_id", "genome_id", "split", "split_strategy", "split_version"] + split_extra_cols
split_out = df[split_cols].copy()
out_path = splits_dir / split_filename
split_out.to_csv(out_path, index=False, encoding="utf-8-sig")

merged_out = proc_dir / "training_labels_wide_with_split.csv"
df.drop(columns=["unit_id"]).to_csv(merged_out, index=False, encoding="utf-8-sig")

summary_path = None
if strategy == "homology_cluster":
    summary_path = resolve_path(project_root, cfg["split"]["homology"]["split_summary_json"])
    dump_json(
        summary_path,
        {
            "strategy": strategy,
            "version": split_version,
            "split_counts": {k: int(v) for k, v in df["split"].value_counts(dropna=False).to_dict().items()},
            "assigned_total_proteins": {k: int(v) for k, v in current_total.items()},
            "assigned_supervised_proteins": {k: int(v) for k, v in current_supervised.items()},
            "unit_count": int(unit_stats["unit_id"].nunique()),
        },
    )

print(f"[OK] saved: {out_path}")
print(f"[OK] saved: {merged_out}")
if summary_path is not None:
    print(f"[OK] saved: {summary_path}")
print(df["split"].value_counts(dropna=False).to_string())
print("\n[INFO] split metadata:")
print(f"strategy={strategy}, version={split_version}")
print("[INFO] assigned total proteins by split:", current_total)
print("[INFO] assigned supervised proteins by split:", current_supervised)
