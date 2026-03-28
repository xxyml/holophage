from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from utils import dump_json, ensure_dirs, load_config, resolve_path


def iter_cluster_tsv(path: Path):
    with path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if not row:
                continue
            if len(row) < 2:
                raise ValueError(f"Malformed MMseqs cluster row in {path}: {row}")
            yield row[0], row[1]


cfg = load_config()
project_root = Path(cfg["project_root"])
proc_dir = resolve_path(project_root, cfg["paths"]["processed_dir"])
hom_cfg = cfg["split"].get("homology", {})

exact_prefix = resolve_path(project_root, hom_cfg["exact_prefix"])
homology_prefix = resolve_path(project_root, hom_cfg["homology_prefix"])
membership_path = resolve_path(project_root, hom_cfg["membership_tsv"])
cluster_stats_path = resolve_path(project_root, hom_cfg["cluster_stats_tsv"])
summary_path = resolve_path(project_root, hom_cfg["membership_summary_json"])
wide_path = proc_dir / "training_labels_wide.csv"

ensure_dirs(membership_path.parent)

exact_cluster_tsv = exact_prefix.parent / f"{exact_prefix.name}_cluster.tsv"
homology_cluster_tsv = homology_prefix.parent / f"{homology_prefix.name}_cluster.tsv"

if not exact_cluster_tsv.exists():
    raise FileNotFoundError(f"Missing exact cluster TSV: {exact_cluster_tsv}")
if not homology_cluster_tsv.exists():
    raise FileNotFoundError(f"Missing homology cluster TSV: {homology_cluster_tsv}")

exact_rep_to_homology = {}
homology_cluster_sizes = Counter()

for homology_rep, exact_rep in iter_cluster_tsv(homology_cluster_tsv):
    exact_rep_to_homology[exact_rep] = homology_rep
    homology_cluster_sizes[homology_rep] += 1

rows_written = 0
protein_counter = Counter()
cluster_total_counts = Counter()
cluster_supervised_counts = Counter()
cluster_status_counts = defaultdict(Counter)
protein_to_cluster = {}

status_lookup = {}
for chunk in pd.read_csv(
    wide_path,
    usecols=["protein_id", "status"],
    chunksize=100000,
    low_memory=False,
):
    for row in chunk.itertuples(index=False):
        status_lookup[str(row.protein_id)] = str(row.status)

with membership_path.open("w", encoding="utf-8", newline="") as fout:
    writer = csv.writer(fout, delimiter="\t")
    writer.writerow(["protein_id", "exact_sequence_rep_id", "homology_cluster_id"])
    for exact_rep, protein_id in iter_cluster_tsv(exact_cluster_tsv):
        homology_cluster_id = exact_rep_to_homology.get(exact_rep)
        if homology_cluster_id is None:
            raise KeyError(f"Exact representative {exact_rep} not found in homology clusters")
        writer.writerow([protein_id, exact_rep, homology_cluster_id])
        rows_written += 1
        protein_to_cluster[protein_id] = homology_cluster_id

        status = status_lookup.get(protein_id, "")
        cluster_total_counts[homology_cluster_id] += 1
        if status and status != "open_set":
            cluster_supervised_counts[homology_cluster_id] += 1
        if status:
            cluster_status_counts[homology_cluster_id][status] += 1
        protein_counter[protein_id] += 1

duplicate_proteins = [pid for pid, count in protein_counter.items() if count != 1]
if duplicate_proteins:
    raise ValueError(f"Found proteins with duplicate cluster assignments: {duplicate_proteins[:5]}")

stats_rows = []
for cluster_id, total_count in cluster_total_counts.items():
    row = {
        "homology_cluster_id": cluster_id,
        "cluster_total_proteins": total_count,
        "cluster_supervised_proteins": cluster_supervised_counts.get(cluster_id, 0),
    }
    for status_name, count in cluster_status_counts[cluster_id].items():
        row[f"status__{status_name}"] = count
    stats_rows.append(row)

cluster_stats_df = pd.DataFrame(stats_rows).sort_values(
    by=["cluster_total_proteins", "cluster_supervised_proteins", "homology_cluster_id"],
    ascending=[False, False, True],
)
cluster_stats_df.to_csv(cluster_stats_path, sep="\t", index=False, encoding="utf-8")

summary = {
    "membership_tsv": str(membership_path),
    "cluster_stats_tsv": str(cluster_stats_path),
    "rows_written": rows_written,
    "unique_homology_clusters": int(cluster_stats_df["homology_cluster_id"].nunique()),
    "max_cluster_size": int(cluster_stats_df["cluster_total_proteins"].max()),
    "median_cluster_size": float(cluster_stats_df["cluster_total_proteins"].median()),
}
dump_json(summary_path, summary)

print(f"[OK] saved membership: {membership_path}")
print(f"[OK] saved cluster stats: {cluster_stats_path}")
print(f"[OK] saved summary: {summary_path}")
print(summary)
