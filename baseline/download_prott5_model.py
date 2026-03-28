import argparse
import os
from pathlib import Path

from huggingface_hub import snapshot_download


def main() -> None:
    parser = argparse.ArgumentParser(description="Download ProtT5 model files for local embedding extraction.")
    parser.add_argument(
        "--repo-id",
        default="Rostlab/prot_t5_xl_uniref50",
        help="Hugging Face model repo id.",
    )
    parser.add_argument(
        "--local-dir",
        default=r"D:\data\ai4s\holophage\models\prot_t5_xl_uniref50",
        help="Target local directory.",
    )
    parser.add_argument(
        "--endpoint",
        default="https://hf-mirror.com",
        help="HF endpoint or mirror.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Parallel download workers.",
    )
    parser.add_argument(
        "--include-readme",
        action="store_true",
        help="Also download README.md.",
    )
    args = parser.parse_args()

    os.environ["HF_ENDPOINT"] = args.endpoint
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    local_dir = Path(args.local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    allow_patterns = [
        "config.json",
        "pytorch_model.bin",
        "special_tokens_map.json",
        "spiece.model",
        "tokenizer_config.json",
    ]
    if args.include_readme:
        allow_patterns.append("README.md")

    print(f"Downloading {args.repo_id} -> {local_dir}")
    print(f"Endpoint: {args.endpoint}")
    print(f"Files: {allow_patterns}")

    path = snapshot_download(
        repo_id=args.repo_id,
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
        allow_patterns=allow_patterns,
        max_workers=args.max_workers,
        resume_download=True,
    )
    print(f"DOWNLOADED_TO {path}")


if __name__ == "__main__":
    main()
