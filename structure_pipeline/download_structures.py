from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from structure_pipeline.common import (
    REPO_ROOT,
    dump_json,
    ensure_dir,
    fetch_binary_range,
    gunzip_bytes,
    load_yaml,
    make_session,
    now_ts,
    resolve_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download canonical structures from AFDB/BFVD/Viro3D manifests.")
    parser.add_argument("--config", default="structure_pipeline/config.yaml")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit.")
    return parser.parse_args()


def is_valid_structure_text(text: str, preferred_format: str) -> bool:
    preferred_format = (preferred_format or "").lower()
    if preferred_format == "cif":
        return text.lstrip().startswith("data_")
    return text.lstrip().startswith("HEADER") or "\nATOM" in text or text.lstrip().startswith("MODEL")


def main() -> None:
    args = parse_args()
    cfg = load_yaml(resolve_path(args.config, REPO_ROOT))
    project_root = resolve_path(cfg["project_root"])
    manifest_path = resolve_path(cfg["paths"]["download_manifest_tsv"], project_root)
    structures_root = ensure_dir(resolve_path(cfg["paths"]["structures_dir"], project_root))
    summary_json = resolve_path(cfg["paths"]["coverage_summary_json"], project_root)
    summary_md = resolve_path(cfg["paths"]["coverage_summary_md"], project_root)
    timeout = int(cfg["screening"]["timeout_sec"])

    if not manifest_path.exists():
        raise FileNotFoundError(f"Download manifest not found: {manifest_path}")

    manifest = pd.read_csv(manifest_path, sep="\t", low_memory=False)
    if args.limit:
        manifest = manifest.head(args.limit).copy()

    session = make_session(cfg["screening"]["user_agent"])
    results: list[dict[str, object]] = []
    for row in manifest.to_dict("records"):
        relpath = row["output_relpath"]
        out_path = structures_root / relpath
        out_path.parent.mkdir(parents=True, exist_ok=True)
        status = "downloaded"
        note = ""
        try:
            if out_path.exists() and out_path.stat().st_size > 0:
                existing = out_path.read_text(encoding="utf-8")
                if is_valid_structure_text(existing, row.get("preferred_format")):
                    status = "skipped_existing"
                else:
                    out_path.unlink()

            if status == "downloaded":
                if row.get("download_mode") == "range_gzip_tar_member":
                    payload = fetch_binary_range(
                        session,
                        str(row["cif_url"]),
                        int(row["range_offset"]),
                        int(row["range_offset"]) + int(row["range_length"]) - 1,
                        timeout=timeout * 2,
                    )
                    text = gunzip_bytes(payload)
                else:
                    url = row.get("cif_url") if row.get("preferred_format") == "cif" else row.get("pdb_url")
                    if not url:
                        raise ValueError("No direct download URL available.")
                    response = session.get(str(url), timeout=timeout)
                    response.raise_for_status()
                    text = response.text

                if not is_valid_structure_text(text, row.get("preferred_format")):
                    raise ValueError("Downloaded file does not look like a valid structure text file.")
                out_path.write_text(text, encoding="utf-8")
        except requests.HTTPError as exc:
            status = "http_error"
            note = str(exc)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            note = str(exc)

        results.append(
            {
                "exact_sequence_rep_id": row["exact_sequence_rep_id"],
                "source": row["source"],
                "source_model_id": row["source_model_id"],
                "output_relpath": relpath,
                "status": status,
                "note": note,
                "checked_at": now_ts(),
            }
        )

    results_df = pd.DataFrame(results)
    results_path = manifest_path.parent / "structure_download_results.tsv"
    results_df.to_csv(results_path, sep="\t", index=False, encoding="utf-8-sig")

    status_counts = results_df["status"].value_counts().to_dict() if not results_df.empty else {}
    summary = {
        "generated_at": now_ts(),
        "manifest_path": str(manifest_path),
        "structures_root": str(structures_root),
        "rows_processed": int(len(results_df)),
        "status_counts": status_counts,
        "successful_files": int(results_df["status"].isin(["downloaded", "skipped_existing"]).sum()) if not results_df.empty else 0,
    }
    dump_json(summary, summary_json)
    summary_md.parent.mkdir(parents=True, exist_ok=True)
    summary_md.write_text(
        "\n".join(
            [
                "# Structure Coverage Summary",
                "",
                f"- generated_at: `{summary['generated_at']}`",
                f"- rows_processed: `{summary['rows_processed']}`",
                f"- successful_files: `{summary['successful_files']}`",
                f"- status_counts: `{status_counts}`",
                f"- manifest_path: `{manifest_path}`",
                f"- structures_root: `{structures_root}`",
            ]
        ),
        encoding="utf-8",
    )

    print(f"[OK] download results saved: {results_path}")
    print(summary)


if __name__ == "__main__":
    main()
