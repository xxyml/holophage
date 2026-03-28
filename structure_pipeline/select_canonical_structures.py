from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from structure_pipeline.common import REPO_ROOT, dump_json, load_yaml, now_ts, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select canonical structure hit per exact sequence.")
    parser.add_argument("--config", default="structure_pipeline/config.yaml")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_yaml(resolve_path(args.config, REPO_ROOT))
    project_root = resolve_path(cfg["project_root"])
    hits_path = resolve_path(cfg["paths"]["hit_candidates_tsv"], project_root)
    canonical_path = resolve_path(cfg["paths"]["canonical_hits_tsv"], project_root)
    download_manifest_path = resolve_path(cfg["paths"]["download_manifest_tsv"], project_root)
    summary_path = canonical_path.parent / "select_canonical_structures.summary.json"

    if not hits_path.exists():
        raise FileNotFoundError(f"Hit candidates not found: {hits_path}")

    hits = pd.read_csv(hits_path, sep="\t", low_memory=False)
    if hits.empty:
        hits.to_csv(canonical_path, sep="\t", index=False, encoding="utf-8-sig")
        hits.to_csv(download_manifest_path, sep="\t", index=False, encoding="utf-8-sig")
        dump_json({"selected_at": now_ts(), "canonical_rows": 0, "download_rows": 0}, summary_path)
        print("[OK] no hits found; canonical/download manifests are empty.")
        return

    priority = cfg["selection"]["source_priority"]
    hits["source_priority"] = hits["source"].map(priority).fillna(999).astype(int)
    hits["confidence_score_num"] = pd.to_numeric(hits["confidence_score"], errors="coerce").fillna(-1.0)
    hits["source_version_num"] = pd.to_numeric(hits["source_version"], errors="coerce").fillna(-1.0)
    hits = hits.sort_values(
        by=["exact_sequence_rep_id", "source_priority", "source_version_num", "confidence_score_num"],
        ascending=[True, True, False, False],
    ).reset_index(drop=True)

    canonical = hits.drop_duplicates("exact_sequence_rep_id", keep="first").copy()
    canonical["output_subdir"] = canonical["source"].str.lower()
    canonical["output_ext"] = canonical["preferred_format"].map(lambda x: "cif" if x == "cif" else "pdb")
    canonical["output_filename"] = canonical.apply(
        lambda row: f"{row['exact_sequence_rep_id']}__{row['source'].lower()}__{row['source_model_id']}.{row['output_ext']}",
        axis=1,
    )
    canonical["output_relpath"] = canonical["output_subdir"] + "/" + canonical["output_filename"]
    canonical["expected_id"] = canonical["source_model_id"]

    download_cols = [
        "exact_sequence_rep_id",
        "source",
        "source_model_id",
        "expected_id",
        "preferred_format",
        "output_relpath",
        "download_mode",
        "cif_url",
        "pdb_url",
        "range_offset",
        "range_length",
        "compression",
        "confidence_score",
        "source_version",
    ]
    for col in download_cols:
        if col not in canonical.columns:
            canonical[col] = None

    canonical.to_csv(canonical_path, sep="\t", index=False, encoding="utf-8-sig")
    canonical[download_cols].to_csv(download_manifest_path, sep="\t", index=False, encoding="utf-8-sig")

    summary = {
        "selected_at": now_ts(),
        "hit_rows": int(len(hits)),
        "canonical_rows": int(len(canonical)),
        "download_rows": int(len(canonical)),
        "source_counts": canonical["source"].value_counts().to_dict(),
    }
    dump_json(summary, summary_path)

    print(f"[OK] canonical hits saved: {canonical_path}")
    print(f"[OK] download manifest saved: {download_manifest_path}")
    print(summary)


if __name__ == "__main__":
    main()
