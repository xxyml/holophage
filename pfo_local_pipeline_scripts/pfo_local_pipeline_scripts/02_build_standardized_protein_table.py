from pathlib import Path
from utils import load_config, resolve_path, safe_read_table, ensure_dirs, normalize_annotation

cfg = load_config()
project_root = Path(cfg["project_root"])

raw_path = resolve_path(project_root, cfg["paths"]["raw_protein_table"])
lookup_path = resolve_path(project_root, cfg["paths"]["phrog_annotation_lookup"])
inter_dir = resolve_path(project_root, cfg["paths"]["intermediate_dir"])
ensure_dirs(inter_dir)

col = cfg["columns"]
df = safe_read_table(
    raw_path,
    sep=cfg["input"]["sep"],
    encoding=cfg["input"]["encoding"],
    nrows=None,
)

required = [col["protein_id"], col["genome_id"], col["sequence"]]
missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"Missing required columns in raw table: {missing}")

annotation_raw_col = col.get("annotation_raw", "")
phrog_annotation_col = col.get("phrog_annotation", "")

if annotation_raw_col not in df.columns:
    if not phrog_annotation_col or phrog_annotation_col not in df.columns:
        raise ValueError(
            "Raw table does not contain annotation_raw, and phrog_annotation is unavailable for lookup."
        )

    lookup_df = safe_read_table(
        lookup_path,
        sep="\t",
        encoding=cfg["input"]["encoding"],
        nrows=None,
    )
    lcol = cfg["lookup_columns"]
    lookup_required = [lcol["phrog_annotation"], lcol["annotation_raw"]]
    missing_lookup = [c for c in lookup_required if c not in lookup_df.columns]
    if missing_lookup:
        raise ValueError(f"Missing required columns in PHROG lookup table: {missing_lookup}")

    lookup_df = lookup_df[[lcol["phrog_annotation"], lcol["annotation_raw"]]].drop_duplicates()
    df = df.merge(
        lookup_df,
        left_on=phrog_annotation_col,
        right_on=lcol["phrog_annotation"],
        how="left",
    )
    annotation_raw_col = lcol["annotation_raw"]

rename_map = {
    col["protein_id"]: "protein_id",
    col["genome_id"]: "genome_id",
    col["sequence"]: "sequence",
    annotation_raw_col: "annotation_raw",
}
for k in ["contig_id", "gene_index"]:
    if col.get(k) and col[k] in df.columns:
        rename_map[col[k]] = k
if phrog_annotation_col and phrog_annotation_col in df.columns:
    rename_map[phrog_annotation_col] = "phrog_annotation"

df = df.rename(columns=rename_map)

for k in ["contig_id", "gene_index"]:
    if k not in df.columns:
        df[k] = ""
if "phrog_annotation" not in df.columns:
    df["phrog_annotation"] = ""

df["sequence"] = df["sequence"].astype(str)
df["sequence_length"] = df["sequence"].str.len()

norm_cfg = cfg.get("normalize", {})
df["annotation_normalized"] = df["annotation_raw"].apply(
    lambda x: normalize_annotation(
        x,
        no_mapping_aliases=norm_cfg.get("no_mapping_aliases", []),
        blank_aliases=norm_cfg.get("blank_aliases", []),
    )
)

keep_cols = [
    "protein_id", "genome_id", "contig_id", "gene_index",
    "sequence", "sequence_length", "phrog_annotation", "annotation_raw", "annotation_normalized"
]
df = df[keep_cols]

out_path = inter_dir / "protein_master_standardized.csv"
df.to_csv(out_path, index=False, encoding="utf-8-sig")
print(f"[OK] saved: {out_path}")
print(df.head().to_string(index=False))
