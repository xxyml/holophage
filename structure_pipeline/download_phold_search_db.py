from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from structure_pipeline.common import REPO_ROOT, ensure_dir, load_yaml, now_ts, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download phold Search DB tarball with resume support.")
    parser.add_argument("--config", default="structure_pipeline/config.yaml")
    parser.add_argument("--output", default=None, help="Optional output tar path override.")
    parser.add_argument("--chunk-mb", type=int, default=16)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_yaml(resolve_path(args.config, REPO_ROOT))
    phold_cfg = cfg["sources"]["phold_search_db"]
    out_dir = ensure_dir(resolve_path(cfg["paths"]["phold_download_dir"], resolve_path(cfg["project_root"])))
    file_name = phold_cfg["zenodo_file_name"]
    out_path = Path(args.output) if args.output else out_dir / file_name
    url = phold_cfg["direct_download_url"]
    chunk_size = args.chunk_mb * 1024 * 1024

    print(f"[INFO] {now_ts()} phold source: {phold_cfg['zenodo_record_url']}")
    print(f"[INFO] download url: {url}")
    print(f"[INFO] output path: {out_path}")

    head = requests.head(url, allow_redirects=True, timeout=60)
    head.raise_for_status()
    total_size = int(head.headers.get("Content-Length", "0"))
    print(f"[INFO] remote size bytes: {total_size}")

    if args.dry_run:
        print("[OK] dry run only, no download started.")
        return

    existing_size = out_path.stat().st_size if out_path.exists() else 0
    headers = {}
    mode = "wb"
    if existing_size > 0 and existing_size < total_size:
        headers["Range"] = f"bytes={existing_size}-"
        mode = "ab"
        print(f"[INFO] resume from byte offset: {existing_size}")
    elif existing_size >= total_size > 0:
        print("[OK] file already complete, skipping download.")
        return

    with requests.get(url, headers=headers, stream=True, allow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open(mode) as handle:
            written = existing_size
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)
                if total_size:
                    pct = round(written / total_size * 100, 2)
                    print(f"[PROGRESS] {written}/{total_size} bytes ({pct}%)")
                else:
                    print(f"[PROGRESS] {written} bytes")

    print(f"[OK] download finished: {out_path}")


if __name__ == "__main__":
    main()
