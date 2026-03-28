from pathlib import Path
from huggingface_hub import hf_hub_download, HfApi

MODEL_DIR = Path(r"D:\data\ai4s\holophage\embedding_pipeline\models\prot_t5_xl_uniref50_bits")
REPO_ID = "Rostlab/prot_t5_xl_uniref50"
REVISION = "refs/pr/1"
FILENAME = "model.safetensors"

def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    download_dir = MODEL_DIR / ".cache" / "huggingface" / "download"
    download_dir.mkdir(parents=True, exist_ok=True)

    lock_file = download_dir / f"{FILENAME}.lock"
    if lock_file.exists():
        print(f"[cleanup] removing lock: {lock_file}")
        lock_file.unlink()

    incomplete_files = list(download_dir.glob("*.incomplete"))
    for f in incomplete_files:
        print(f"[cleanup] removing incomplete: {f}")
        f.unlink()

    api = HfApi()
    info = api.model_info(REPO_ID, revision=REVISION, files_metadata=True)
    size_map = {s.rfilename: s.size for s in info.siblings}
    print(f"[info] remote file size: {size_map.get(FILENAME)} bytes")

    print("[download] start...")
    path = hf_hub_download(
        repo_id=REPO_ID,
        filename=FILENAME,
        revision=REVISION,
        local_dir=str(MODEL_DIR),
        local_dir_use_symlinks=False,
        resume_download=True,
    )

    p = Path(path)
    print(f"[done] saved to: {p}")
    print(f"[done] exists: {p.exists()}")
    print(f"[done] size: {p.stat().st_size if p.exists() else 'N/A'} bytes")

if __name__ == "__main__":
    main()
