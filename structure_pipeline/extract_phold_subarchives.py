from __future__ import annotations

import argparse
import sys
import tarfile
from pathlib import Path

import pandas as pd

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from structure_pipeline.common import REPO_ROOT, dump_json, ensure_dir, load_yaml, now_ts, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract only selected PHROG subarchives from the phold top-level tar.")
    parser.add_argument("--config", default="structure_pipeline/config.yaml")
    parser.add_argument("--limit-phrogs", type=int, default=None, help="Optional top-N PHROGs by demand to extract.")
    parser.add_argument("--target-status", choices=["all", "trainable_core"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_yaml(resolve_path(args.config, REPO_ROOT))
    project_root = resolve_path(cfg["project_root"])
    phold_cfg = cfg["sources"]["phold_search_db"]
    tar_path = resolve_path(cfg["paths"]["phold_download_dir"], project_root) / phold_cfg["zenodo_file_name"]
    plan_path = resolve_path(cfg["paths"]["phold_plan_tsv"], project_root)
    out_dir = ensure_dir(resolve_path(cfg["paths"]["phold_selected_subarchives_dir"], project_root))
    summary_path = out_dir / f"extract_summary_{args.target_status}.json"

    if not tar_path.exists():
        raise FileNotFoundError(f"phold tarball not found: {tar_path}")
    if not plan_path.exists():
        raise FileNotFoundError(f"phold retrieval plan not found: {plan_path}")

    plan_df = pd.read_csv(plan_path, sep="\t", low_memory=False)
    if args.target_status == "trainable_core":
        plan_df = plan_df[plan_df["any_trainable_core"] == True].copy()

    subarchive_counts = (
        plan_df.groupby("phold_subarchive_name", as_index=False)
        .agg(exact_sequence_count=("exact_sequence_rep_id", "count"))
        .sort_values("exact_sequence_count", ascending=False)
    )
    if args.limit_phrogs is not None:
        subarchive_counts = subarchive_counts.head(args.limit_phrogs).copy()
    targets = set(subarchive_counts["phold_subarchive_name"].dropna().astype(str))

    extracted: list[dict[str, object]] = []
    missing: list[str] = []

    with tarfile.open(tar_path, "r") as tf:
        member_map = {Path(member.name).name: member for member in tf.getmembers() if member.isfile()}
        for subarchive_name in targets:
            member = member_map.get(subarchive_name)
            if member is None:
                missing.append(subarchive_name)
                continue
            dest_path = out_dir / subarchive_name
            row = subarchive_counts[subarchive_counts["phold_subarchive_name"] == subarchive_name].iloc[0]
            extracted.append(
                {
                    "subarchive_name": subarchive_name,
                    "member_name": member.name,
                    "size_bytes": member.size,
                    "exact_sequence_count": int(row["exact_sequence_count"]),
                    "dest_path": str(dest_path),
                }
            )
            if not args.dry_run and not dest_path.exists():
                extracted_handle = tf.extractfile(member)
                if extracted_handle is None:
                    missing.append(subarchive_name)
                    continue
                with dest_path.open("wb") as out_handle:
                    out_handle.write(extracted_handle.read())

    summary = {
        "built_at": now_ts(),
        "tar_path": str(tar_path),
        "plan_path": str(plan_path),
        "target_status": args.target_status,
        "limit_phrogs": args.limit_phrogs,
        "requested_subarchives": len(targets),
        "extracted_or_planned_subarchives": len(extracted),
        "missing_subarchives": len(missing),
        "dry_run": args.dry_run,
        "top_extracts": extracted[:20],
        "missing_examples": missing[:20],
    }
    dump_json(summary, summary_path)

    print(f"[OK] phold selective extraction summary saved: {summary_path}")
    print(summary)


if __name__ == "__main__":
    main()
