from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from structure_pipeline.common import (
    REPO_ROOT,
    dump_json,
    ensure_dir,
    fetch_json,
    fetch_text,
    load_yaml,
    make_session,
    normalize_format,
    now_ts,
    resolve_path,
)


BFVD_METADATA_COLUMNS = [
    "accession",
    "model_id",
    "confidence_score",
    "ptm_score",
    "version",
    "dataset_tier",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen AFDB/BFVD/Viro3D for structure hits.")
    parser.add_argument("--config", default="structure_pipeline/config.yaml")
    parser.add_argument("--targets", default=None, help="Override target manifest path.")
    parser.add_argument("--limit", type=int, default=None, help="Optional target row limit.")
    return parser.parse_args()


def clean_value(value: Any) -> str | None:
    if value is None:
        return None
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def cache_text_file(session: requests.Session, url: str, path: Path) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    text = fetch_text(session, url)
    path.write_text(text, encoding="utf-8")
    return path


def load_bfvd_metadata(meta_path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    df = pd.read_csv(meta_path, sep="\t", header=None, names=BFVD_METADATA_COLUMNS, low_memory=False)
    by_accession: dict[str, list[dict[str, Any]]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    for row in df.to_dict("records"):
        accession = str(row["accession"])
        model_id = str(row["model_id"])
        by_accession.setdefault(accession, []).append(row)
        by_model[model_id] = row
    return by_accession, by_model


def load_bfvd_index(index_path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    with index_path.open("r", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for model_id, offset, length in reader:
            out[model_id] = {
                "model_id": model_id,
                "range_offset": int(offset),
                "range_length": int(length),
            }
    return out


def afdb_hits(session: requests.Session, api_base: str, query_id: str, timeout: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    logs: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    url = f"{api_base.rstrip('/')}/{query_id}"
    try:
        status_code, payload = fetch_json(session, url, timeout=timeout)
        logs.append(
            {
                "source": "AFDB",
                "query_id": query_id,
                "query_mode": "identifier",
                "status": "hit" if payload else "miss",
                "http_status": status_code,
                "queried_at": now_ts(),
                "note": "",
            }
        )
        for item in payload:
            hits.append(
                {
                    "exact_sequence_rep_id": None,
                    "source": "AFDB",
                    "query_id": query_id,
                    "query_qualifier": "accession_or_entry",
                    "source_model_id": item.get("entryId") or item.get("modelEntityId"),
                    "source_entry_id": item.get("entryId"),
                    "source_accession": item.get("uniprotAccession"),
                    "confidence_score": item.get("globalMetricValue"),
                    "source_version": item.get("latestVersion"),
                    "preferred_format": "cif" if item.get("cifUrl") else "pdb",
                    "cif_url": item.get("cifUrl"),
                    "pdb_url": item.get("pdbUrl"),
                    "download_mode": "direct",
                    "raw_source": json.dumps(item, ensure_ascii=False),
                }
            )
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else None
        logs.append(
            {
                "source": "AFDB",
                "query_id": query_id,
                "query_mode": "identifier",
                "status": "miss" if code == 404 else "error",
                "http_status": code,
                "queried_at": now_ts(),
                "note": str(exc),
            }
        )
    return hits, logs


def bfvd_hits(
    query_id: str,
    accession_lookup: dict[str, list[dict[str, Any]]],
    model_lookup: dict[str, dict[str, Any]],
    cif_index: dict[str, dict[str, Any]],
    cif_archive_url: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    logs: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    if query_id in model_lookup:
        matches.append(model_lookup[query_id])
    if query_id in accession_lookup:
        matches.extend(accession_lookup[query_id])

    logs.append(
        {
            "source": "BFVD",
            "query_id": query_id,
            "query_mode": "model_or_accession",
            "status": "hit" if matches else "miss",
            "http_status": 200,
            "queried_at": now_ts(),
            "note": "",
        }
    )
    for item in matches:
        model_id = item["model_id"]
        if model_id not in cif_index:
            continue
        idx = cif_index[model_id]
        hits.append(
            {
                "exact_sequence_rep_id": None,
                "source": "BFVD",
                "query_id": query_id,
                "query_qualifier": "model_or_accession",
                "source_model_id": model_id,
                "source_entry_id": model_id,
                "source_accession": item["accession"],
                "confidence_score": item.get("confidence_score"),
                "source_version": item.get("version"),
                "preferred_format": "cif",
                "cif_url": cif_archive_url,
                "pdb_url": None,
                "range_offset": idx["range_offset"],
                "range_length": idx["range_length"],
                "compression": "gzip",
                "download_mode": "range_gzip_tar_member",
                "raw_source": json.dumps(item, ensure_ascii=False),
            }
        )
    return hits, logs


def flatten_viro3d_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("protein_structures", "results", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if all(not isinstance(v, list) for v in payload.values()):
            return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def viro3d_hits(session: requests.Session, api_base: str, identifier: str, qualifier: str, timeout: int, page_size: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    logs: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    endpoint_map = {
        "genbank_id": f"{api_base.rstrip('/')}/proteins/genbank_id/",
        "protein_name": f"{api_base.rstrip('/')}/proteins/protein_name/",
        "virus_name": f"{api_base.rstrip('/')}/proteins/virus_name/",
    }
    candidates = [
        (f"{api_base.rstrip('/')}/proteins/{identifier}_exact/", {"qualifier": qualifier}),
        (f"{api_base.rstrip('/')}/proteins/{identifier}/", {"qualifier": qualifier}),
    ]
    if qualifier in endpoint_map:
        candidates.append((endpoint_map[qualifier], {"qualifier": identifier, "page_size": page_size}))

    for url, params in candidates:
        try:
            status_code, payload = fetch_json(session, url, timeout=timeout, params=params)
            records = flatten_viro3d_records(payload)
            logs.append(
                {
                    "source": "Viro3D",
                    "query_id": identifier,
                    "query_mode": qualifier,
                    "status": "hit" if records else "miss",
                    "http_status": status_code,
                    "queried_at": now_ts(),
                    "note": url,
                }
            )
            if not records:
                continue
            for record in records:
                source_model_id = (
                    record.get("record_id")
                    or record.get("uniq_id")
                    or record.get("genbank_id")
                    or record.get("protein_name")
                    or record.get("uniprot_id")
                )
                hits.append(
                    {
                        "exact_sequence_rep_id": None,
                        "source": "Viro3D",
                        "query_id": identifier,
                        "query_qualifier": qualifier,
                        "source_model_id": source_model_id,
                        "source_entry_id": source_model_id,
                        "source_accession": record.get("uniprot_id") or record.get("genbank_id"),
                        "confidence_score": record.get("esmfold_log_pLDDT") or record.get("colabfold_json_pLDDT"),
                        "source_version": None,
                        "preferred_format": "cif",
                        "cif_url": f"{api_base.rstrip('/')}/zip/{source_model_id}/{qualifier}/cif" if source_model_id else None,
                        "pdb_url": f"{api_base.rstrip('/')}/zip/{source_model_id}/{qualifier}/pdb" if source_model_id else None,
                        "download_mode": "direct",
                        "raw_source": json.dumps(record, ensure_ascii=False),
                    }
                )
            break
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else None
            logs.append(
                {
                    "source": "Viro3D",
                    "query_id": identifier,
                    "query_mode": qualifier,
                    "status": "miss" if code == 404 else "error",
                    "http_status": code,
                    "queried_at": now_ts(),
                    "note": f"{url} :: {exc}",
                }
            )
    return hits, logs


def main() -> None:
    args = parse_args()
    cfg = load_yaml(resolve_path(args.config, REPO_ROOT))
    project_root = resolve_path(cfg["project_root"])
    targets_path = resolve_path(args.targets or cfg["paths"]["target_manifest_tsv"], project_root)
    hits_path = resolve_path(cfg["paths"]["hit_candidates_tsv"], project_root)
    log_path = resolve_path(cfg["paths"]["query_log_tsv"], project_root)
    summary_path = hits_path.parent / "screen_structure_sources.summary.json"
    cache_dir = ensure_dir(resolve_path(cfg["paths"]["cache_dir"], project_root))

    session = make_session(cfg["screening"]["user_agent"])
    targets = pd.read_csv(targets_path, sep="\t", low_memory=False)
    if args.limit:
        targets = targets.head(args.limit).copy()

    bfvd_cfg = cfg["sources"]["bfvd"]
    bfvd_meta_path = cache_text_file(session, bfvd_cfg["metadata_url"], cache_dir / "bfvd_metadata.tsv")
    bfvd_cif_index_path = cache_text_file(session, bfvd_cfg["cif_index_url"], cache_dir / "bfvd_cif.tar.index")
    bfvd_accession_lookup, bfvd_model_lookup = load_bfvd_metadata(bfvd_meta_path)
    bfvd_cif_index = load_bfvd_index(bfvd_cif_index_path)

    all_hits: list[dict[str, Any]] = []
    all_logs: list[dict[str, Any]] = []
    sleep_sec = float(cfg["screening"]["sleep_sec"])
    timeout_sec = int(cfg["screening"]["timeout_sec"])
    viro3d_page_size = int(cfg["screening"]["viro3d_page_size"])

    for row in targets.to_dict("records"):
        exact_id = row["exact_sequence_rep_id"]
        row_hits: list[dict[str, Any]] = []
        row_logs: list[dict[str, Any]] = []

        af_query = clean_value(row.get("candidate_afdb_entry_id")) or clean_value(row.get("candidate_uniprot_accession"))
        if af_query:
            hits, logs = afdb_hits(session, cfg["sources"]["afdb"]["api_base"], str(af_query), timeout_sec)
            row_hits.extend(hits)
            row_logs.extend(logs)

        bfvd_query = clean_value(row.get("candidate_bfvd_model_id")) or clean_value(row.get("candidate_uniprot_accession"))
        if bfvd_query:
            hits, logs = bfvd_hits(
                str(bfvd_query),
                bfvd_accession_lookup,
                bfvd_model_lookup,
                bfvd_cif_index,
                bfvd_cfg["cif_archive_url"],
            )
            row_hits.extend(hits)
            row_logs.extend(logs)

        viro3d_identifier = clean_value(row.get("candidate_viro3d_identifier"))
        viro3d_qualifier = clean_value(row.get("candidate_viro3d_qualifier"))
        if viro3d_identifier and viro3d_qualifier:
            hits, logs = viro3d_hits(
                session,
                cfg["sources"]["viro3d"]["api_base"],
                str(viro3d_identifier),
                str(viro3d_qualifier),
                timeout_sec,
                viro3d_page_size,
            )
            row_hits.extend(hits)
            row_logs.extend(logs)

        for item in row_hits:
            item["exact_sequence_rep_id"] = exact_id
            item["preferred_format"] = normalize_format(item.get("preferred_format"))
        for log in row_logs:
            log["exact_sequence_rep_id"] = exact_id

        all_hits.extend(row_hits)
        all_logs.extend(row_logs)
        if sleep_sec:
            time.sleep(sleep_sec)

    hits_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_hits).to_csv(hits_path, sep="\t", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_logs).to_csv(log_path, sep="\t", index=False, encoding="utf-8-sig")

    hit_df = pd.DataFrame(all_hits)
    summary = {
        "screened_at": now_ts(),
        "targets_path": str(targets_path),
        "targets_screened": int(len(targets)),
        "hit_rows": int(len(hit_df)),
        "hit_exact_ids": int(hit_df["exact_sequence_rep_id"].nunique()) if not hit_df.empty else 0,
        "query_rows": int(len(all_logs)),
        "sources_with_hits": sorted(set(hit_df["source"])) if not hit_df.empty else [],
        "cache_dir": str(cache_dir),
    }
    dump_json(summary, summary_path)

    print(f"[OK] hit candidates saved: {hits_path}")
    print(f"[OK] query log saved: {log_path}")
    print(summary)


if __name__ == "__main__":
    main()
