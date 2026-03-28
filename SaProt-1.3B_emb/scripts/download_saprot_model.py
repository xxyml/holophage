import json
import shutil
from pathlib import Path
from typing import Optional

import requests
from huggingface_hub import HfApi


DEFAULT_REPO_ID = "westlake-repl/SaProt_1.3B_AF2"
BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = BASE_DIR / "models" / "SaProt_1.3B_AF2"
DEFAULT_MANIFEST_DIR = BASE_DIR / "manifests"
REQUIRED_FILES = [
    "config.json",
    "pytorch_model.bin",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
]
OPTIONAL_FILES = ["README.md"]
CHUNK_SIZE = 8 * 1024 * 1024


def build_resolve_url(repo_id: str, filename: str, revision: Optional[str] = None) -> str:
    rev = revision or "main"
    return f"https://huggingface.co/{repo_id}/resolve/{rev}/{filename}?download=true"


def verify_model_dir(model_dir: Path) -> list[str]:
    return [name for name in REQUIRED_FILES if not (model_dir / name).exists()]


def download_file(repo_id: str, filename: str, target_path: Path, revision: Optional[str]) -> None:
    url = build_resolve_url(repo_id, filename, revision)
    part_path = target_path.with_suffix(target_path.suffix + ".part")
    existing = part_path.stat().st_size if part_path.exists() else 0

    headers = {}
    mode = "wb"
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"
        mode = "ab"

    with requests.get(url, stream=True, timeout=60, headers=headers, allow_redirects=True) as resp:
        if resp.status_code not in (200, 206):
            raise RuntimeError(f"Failed to download {filename}: status={resp.status_code}")
        if existing > 0 and resp.status_code == 200:
            existing = 0
            mode = "wb"
        total = resp.headers.get("Content-Length")
        total_bytes = int(total) + existing if total is not None else None
        print(f"Downloading {filename} -> {target_path}")
        if total_bytes is not None:
            print(f"Expected bytes: {total_bytes}")
        with part_path.open(mode) as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
    shutil.move(str(part_path), str(target_path))


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Download SaProt-1.3B model from Hugging Face.")
    ap.add_argument("--repo-id", type=str, default=DEFAULT_REPO_ID)
    ap.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    ap.add_argument("--manifests-dir", type=Path, default=DEFAULT_MANIFEST_DIR)
    ap.add_argument("--revision", type=str, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    args.model_dir.mkdir(parents=True, exist_ok=True)
    args.manifests_dir.mkdir(parents=True, exist_ok=True)

    api = HfApi()
    info = api.model_info(args.repo_id, revision=args.revision, files_metadata=True)
    file_sizes = {item.rfilename: getattr(item, "size", None) for item in info.siblings}
    total_bytes = sum(size for size in file_sizes.values() if isinstance(size, int))

    summary = {
        "repo_id": args.repo_id,
        "revision": args.revision,
        "target_dir": str(args.model_dir),
        "required_files": REQUIRED_FILES,
        "optional_files": OPTIONAL_FILES,
        "available_files": sorted(file_sizes.keys()),
        "total_remote_bytes": total_bytes,
    }
    summary_path = args.manifests_dir / "download_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Repo: {args.repo_id}")
    print(f"Target dir: {args.model_dir}")
    print(f"Remote total bytes: {total_bytes}")
    print(f"Summary: {summary_path}")

    if args.dry_run:
        print("Dry-run only, not downloading.")
        return

    for filename in REQUIRED_FILES + OPTIONAL_FILES:
        target_path = args.model_dir / filename
        if target_path.exists() and target_path.stat().st_size > 0:
            print(f"Skip existing file: {target_path}")
            continue
        download_file(args.repo_id, filename, target_path, args.revision)

    missing = verify_model_dir(args.model_dir)
    if missing:
        raise RuntimeError(f"Downloaded model is incomplete, missing: {missing}")

    completion_path = args.manifests_dir / "download_complete.json"
    completion = {
        "repo_id": args.repo_id,
        "model_dir": str(args.model_dir),
        "required_files_present": True,
        "missing_files": [],
    }
    completion_path.write_text(json.dumps(completion, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Download complete. Completion manifest: {completion_path}")


if __name__ == "__main__":
    main()
