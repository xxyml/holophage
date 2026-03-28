import argparse
import os
import time
from pathlib import Path

import requests


FILES = [
    "config.json",
    "pytorch_model.bin",
    "special_tokens_map.json",
    "spiece.model",
    "tokenizer_config.json",
    "README.md",
]


def format_gb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 ** 3):.2f} GB"


def format_mb_s(num_bytes_per_sec: float) -> str:
    return f"{num_bytes_per_sec / (1024 ** 2):.2f} MB/s"


def download_file(base_url: str, filename: str, out_dir: Path, chunk_size: int = 8 * 1024 * 1024) -> None:
    out_path = out_dir / filename
    url = f"{base_url.rstrip('/')}/{filename}"

    existing = out_path.stat().st_size if out_path.exists() else 0
    headers = {"Accept-Encoding": "identity"}
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"

    with requests.get(url, headers=headers, stream=True, allow_redirects=True, timeout=60) as resp:
        if resp.status_code not in (200, 206):
            raise RuntimeError(f"Failed to download {filename}: status={resp.status_code}")

        total = resp.headers.get("Content-Length")
        total_bytes = existing + int(total) if total is not None else None
        mode = "ab" if existing > 0 and resp.status_code == 206 else "wb"
        if mode == "wb":
            existing = 0

        print(f"[START] {filename} -> {out_path}")
        if total_bytes is not None:
            print(f"        total={format_gb(total_bytes)} existing={format_gb(existing)}")

        downloaded = existing
        last_report_time = time.time()
        last_report_bytes = downloaded

        with open(out_path, mode) as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)

                now = time.time()
                if now - last_report_time >= 10:
                    speed = (downloaded - last_report_bytes) / max(now - last_report_time, 1e-6)
                    if total_bytes is None:
                        print(f"[PROGRESS] {filename}: downloaded={format_gb(downloaded)} speed={format_mb_s(speed)}")
                    else:
                        pct = downloaded / total_bytes * 100
                        print(
                            f"[PROGRESS] {filename}: {pct:.2f}% "
                            f"downloaded={format_gb(downloaded)} speed={format_mb_s(speed)}"
                        )
                    last_report_time = now
                    last_report_bytes = downloaded

    final_size = out_path.stat().st_size
    print(f"[DONE] {filename}: size={format_gb(final_size)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Directly download ProtT5 files with resume support.")
    parser.add_argument(
        "--base-url",
        default="https://hf-mirror.com/Rostlab/prot_t5_xl_uniref50/resolve/main",
        help="Base resolve URL for the model repo.",
    )
    parser.add_argument(
        "--out-dir",
        default=r"D:\data\ai4s\holophage\models\prot_t5_xl_uniref50_http",
        help="Output directory.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": "holophage-prott5-downloader/1.0"})
    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

    # Bind session into requests.get used above.
    requests.get = session.get  # type: ignore[assignment]

    for filename in FILES:
        download_file(args.base_url, filename, out_dir)

    print(f"DOWNLOADED_TO {out_dir}")


if __name__ == "__main__":
    main()
