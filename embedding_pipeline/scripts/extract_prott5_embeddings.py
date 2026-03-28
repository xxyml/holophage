import argparse
import os
from pathlib import Path
from typing import Any

import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm
from transformers import T5EncoderModel, T5Tokenizer


DEFAULT_MODEL_PATH = r"D:\data\ai4s\holophage\embedding_pipeline\models\prot_t5_xl_uniref50_bits"


def normalize_protein_sequence(seq: str) -> str:
    seq = str(seq).upper().strip()
    for ch in ["U", "Z", "O", "B"]:
        seq = seq.replace(ch, "X")
    return " ".join(list(seq))


class ProtSeqDataset(Dataset):
    def __init__(
        self,
        df: pd.DataFrame,
        id_col: str = "id",
        seq_col: str = "sequence",
        seq_len_col: str = "seq_len",
    ):
        self.df = df.reset_index(drop=True)
        self.id_col = id_col
        self.seq_col = seq_col
        self.seq_len_col = seq_len_col if seq_len_col in df.columns else None

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        pid = str(self.df.loc[idx, self.id_col])
        seq = str(self.df.loc[idx, self.seq_col])
        if self.seq_len_col is not None:
            seq_len = int(self.df.loc[idx, self.seq_len_col])
        else:
            seq_len = len(seq)
        return {"protein_id": pid, "sequence": seq, "orig_seq_len": seq_len}


def collate_fn(batch: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "protein_id": [b["protein_id"] for b in batch],
        "sequence": [b["sequence"] for b in batch],
        "orig_seq_lens": torch.tensor([b["orig_seq_len"] for b in batch], dtype=torch.long),
    }


def save_shard(
    out_path: Path,
    ids: list[str],
    embeddings: torch.Tensor,
    orig_seq_lens: torch.Tensor,
    effective_seq_lens: torch.Tensor,
    truncated_flags: torch.Tensor,
) -> None:
    payload = {
        "ids": ids,
        "embeddings": embeddings,
        "orig_seq_lens": orig_seq_lens,
        "effective_seq_lens": effective_seq_lens,
        "truncated_flags": truncated_flags,
    }
    torch.save(payload, out_path)
    print(
        f"Saved {out_path} | N={len(ids)} | emb_shape={tuple(embeddings.shape)} | dtype={embeddings.dtype}"
    )


def tensor_stats(t: torch.Tensor) -> str:
    t = t.detach().float().cpu()
    return (
        f"shape={tuple(t.shape)} "
        f"mean={t.mean().item():.6f} "
        f"std={t.std().item():.6f} "
        f"absmax={t.abs().max().item():.6f}"
    )


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Precompute ProtT5 protein embeddings from parquet.")
    ap.add_argument("--data_path", type=str, required=True, help="Input parquet path")
    ap.add_argument("--out_dir", type=str, default="./embeddings/prott5_mean")
    ap.add_argument("--model_path", type=str, default=DEFAULT_MODEL_PATH)
    ap.add_argument("--max_length", type=int, default=512, help="Window length for ProtT5 inference")
    ap.add_argument("--batch_size", type=int, default=16, help="Short-sequence batch size")
    ap.add_argument("--num_workers", type=int, default=0)
    ap.add_argument("--shard_size", type=int, default=20000)
    ap.add_argument("--dtype", type=str, default="float16", choices=["float16", "float32"])
    ap.add_argument("--use_amp", action="store_true")
    ap.add_argument("--device", type=str, default="cuda")
    ap.add_argument("--start_shard", type=int, default=0, help="Resume from shard index")
    ap.add_argument("--sort_by_length", action="store_true", help="Sort by seq_len to reduce padding")
    ap.add_argument("--id_col", type=str, default="id")
    ap.add_argument("--seq_col", type=str, default="sequence")
    ap.add_argument("--seq_len_col", type=str, default="seq_len")
    ap.add_argument(
        "--long_seq_strategy",
        type=str,
        default="sliding_windows",
        choices=["truncate", "sliding_windows"],
        help="How to handle sequences longer than max_length",
    )
    ap.add_argument(
        "--window_overlap",
        type=int,
        default=128,
        help="Overlap size for long-sequence sliding windows",
    )
    ap.add_argument(
        "--long_seq_window_batch_size",
        type=int,
        default=8,
        help="Number of windows to encode together for one long sequence",
    )
    return ap.parse_args()


def build_windows(seq: str, max_length: int, overlap: int) -> list[tuple[int, int, str]]:
    if len(seq) <= max_length:
        return [(0, len(seq), seq)]
    if overlap < 0 or overlap >= max_length:
        raise ValueError("window_overlap must be in [0, max_length)")

    stride = max_length - overlap
    windows: list[tuple[int, int, str]] = []
    start = 0
    seq_len = len(seq)
    while start < seq_len:
        end = min(start + max_length, seq_len)
        if end - start < max_length and start != 0:
            start = max(0, seq_len - max_length)
            end = seq_len
        windows.append((start, end, seq[start:end]))
        if end >= seq_len:
            break
        start += stride
    return windows


def coverage_weights(windows: list[tuple[int, int, str]]) -> list[int]:
    weights: list[int] = []
    covered_until = 0
    for start, end, _ in windows:
        unique = end - max(start, covered_until)
        unique = max(1, unique)
        weights.append(unique)
        covered_until = max(covered_until, end)
    return weights


def pooled_from_model_output(hidden: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    mask = attention_mask.unsqueeze(-1).float()
    return (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-8)


def encode_sequence_batch(
    seqs: list[str],
    tokenizer: T5Tokenizer,
    model: T5EncoderModel,
    device: torch.device,
    max_length: int,
    use_amp: bool,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    seqs_for_tokenizer = [normalize_protein_sequence(s) for s in seqs]
    enc = tokenizer(
        seqs_for_tokenizer,
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    input_ids = enc["input_ids"].to(device, non_blocking=True)
    attention_mask = enc["attention_mask"].to(device, non_blocking=True)

    with torch.inference_mode():
        if use_amp and device.type == "cuda":
            with torch.cuda.amp.autocast():
                out = model(input_ids=input_ids, attention_mask=attention_mask)
        else:
            out = model(input_ids=input_ids, attention_mask=attention_mask)
        hidden = out.last_hidden_state
        pooled = pooled_from_model_output(hidden, attention_mask)
    return pooled, hidden, input_ids


def aggregate_long_sequence(
    seq: str,
    tokenizer: T5Tokenizer,
    model: T5EncoderModel,
    device: torch.device,
    max_length: int,
    overlap: int,
    window_batch_size: int,
    use_amp: bool,
) -> tuple[torch.Tensor, int]:
    windows = build_windows(seq, max_length=max_length, overlap=overlap)
    weights = coverage_weights(windows)
    pooled_parts: list[torch.Tensor] = []

    for start in range(0, len(windows), window_batch_size):
        chunk = windows[start : start + window_batch_size]
        chunk_seqs = [w[2] for w in chunk]
        pooled, _, _ = encode_sequence_batch(
            seqs=chunk_seqs,
            tokenizer=tokenizer,
            model=model,
            device=device,
            max_length=max_length,
            use_amp=use_amp,
        )
        pooled_parts.append(pooled.detach().float().cpu())

    pooled_all = torch.cat(pooled_parts, dim=0)
    weight_t = torch.tensor(weights, dtype=torch.float32).unsqueeze(-1)
    aggregated = (pooled_all * weight_t).sum(dim=0) / weight_t.sum(dim=0).clamp(min=1e-8)
    return aggregated, len(windows)


def main() -> None:
    args = parse_args()

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Using device: {device}")
    print("Loading parquet...")
    df = pd.read_parquet(args.data_path)

    for col in [args.id_col, args.seq_col]:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    df[args.id_col] = df[args.id_col].astype(str)
    if not df[args.id_col].is_unique:
        raise ValueError(f"{args.id_col} is not unique")

    if args.seq_len_col not in df.columns:
        print(f"[WARN] {args.seq_len_col} not found, computing from sequence")
        df[args.seq_len_col] = df[args.seq_col].astype(str).str.len()

    df = df[df[args.seq_col].notna()].copy()
    df[args.seq_col] = df[args.seq_col].astype(str).str.strip()
    df = df[df[args.seq_col] != ""].copy()

    if args.sort_by_length:
        df = df.sort_values(args.seq_len_col, ascending=True).reset_index(drop=True)

    num_long = int((df[args.seq_len_col] > args.max_length).sum())
    print(f"Total usable rows: {len(df)}")
    if args.long_seq_strategy == "truncate":
        print(f"Sequences longer than max_length={args.max_length}: {num_long}/{len(df)} (will truncate)")
    else:
        print(
            f"Sequences longer than max_length={args.max_length}: {num_long}/{len(df)} "
            f"(will use sliding windows, overlap={args.window_overlap})"
        )

    print("Loading tokenizer/model from local path...")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"

    model_path = args.model_path
    model_dir = Path(model_path)
    if not model_dir.exists():
        raise FileNotFoundError(f"Model path not found: {model_dir}")
    for f in ["config.json", "spiece.model", "tokenizer_config.json"]:
        if not (model_dir / f).exists():
            raise FileNotFoundError(f"Missing {f} in local model dir: {model_dir}")

    print(f"Using local model path: {model_path}")
    has_safetensors = (model_dir / "model.safetensors").exists()
    if has_safetensors:
        print("Detected model.safetensors, loading safetensors weights.")
    else:
        print("model.safetensors not found, falling back to pytorch_model.bin.")

    tokenizer = T5Tokenizer.from_pretrained(
        model_path,
        do_lower_case=False,
        local_files_only=True,
        legacy=True,
    )
    model = T5EncoderModel.from_pretrained(
        model_path,
        local_files_only=True,
        use_safetensors=has_safetensors,
    ).to(device)

    if args.dtype == "float16" and device.type == "cuda":
        model = model.half()

    model.eval()
    target_dtype = torch.float16 if args.dtype == "float16" else torch.float32

    ds = ProtSeqDataset(df=df, id_col=args.id_col, seq_col=args.seq_col, seq_len_col=args.seq_len_col)
    dl = DataLoader(
        ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
        collate_fn=collate_fn,
    )

    shard_idx = args.start_shard
    shard_path = out_dir / f"shard_{shard_idx:05d}.pt"
    to_skip = args.start_shard * args.shard_size

    ids_buf: list[str] = []
    embs_buf: list[torch.Tensor] = []
    orig_len_buf: list[torch.Tensor] = []
    eff_len_buf: list[torch.Tensor] = []
    trunc_buf: list[torch.Tensor] = []

    validated_first_batch = False
    validated_first_long = False
    print("Start embedding precompute...")
    for batch in tqdm(dl, desc="Embedding"):
        bsz = len(batch["protein_id"])

        if to_skip > 0:
            if to_skip >= bsz:
                to_skip -= bsz
                continue
            k = to_skip
            batch["protein_id"] = batch["protein_id"][k:]
            batch["sequence"] = batch["sequence"][k:]
            batch["orig_seq_lens"] = batch["orig_seq_lens"][k:]
            to_skip = 0

        seqs = batch["sequence"]
        ids = batch["protein_id"]
        orig_seq_lens = batch["orig_seq_lens"]

        short_items: list[tuple[int, str, str, int]] = []
        long_items: list[tuple[int, str, str, int]] = []
        for idx, (pid, seq, seq_len) in enumerate(zip(ids, seqs, orig_seq_lens.tolist())):
            if seq_len <= args.max_length or args.long_seq_strategy == "truncate":
                short_items.append((idx, pid, seq, seq_len))
            else:
                long_items.append((idx, pid, seq, seq_len))

        batch_embeddings: list[torch.Tensor | None] = [None] * len(ids)
        batch_effective_lens = [0] * len(ids)
        batch_truncated = [False] * len(ids)

        if short_items:
            short_seqs = [item[2] for item in short_items]
            pooled, hidden, input_ids = encode_sequence_batch(
                seqs=short_seqs,
                tokenizer=tokenizer,
                model=model,
                device=device,
                max_length=args.max_length,
                use_amp=args.use_amp,
            )
            if not validated_first_batch:
                print("[DEBUG] First batch input_ids stats:", tensor_stats(input_ids))
                print("[DEBUG] First batch hidden stats:", tensor_stats(hidden))
                print("[DEBUG] First batch pooled stats:", tensor_stats(pooled))
                if torch.all(pooled == 0):
                    raise RuntimeError("First batch pooled embeddings are all zero.")
                if not torch.isfinite(pooled).all():
                    raise RuntimeError("First batch pooled embeddings contain NaN/Inf values.")
                validated_first_batch = True

            pooled_cpu = pooled.to(dtype=target_dtype).cpu()
            for local_idx, (orig_idx, _, _, seq_len) in enumerate(short_items):
                batch_embeddings[orig_idx] = pooled_cpu[local_idx]
                batch_effective_lens[orig_idx] = min(seq_len, args.max_length)
                batch_truncated[orig_idx] = seq_len > args.max_length

        for orig_idx, _, seq, seq_len in long_items:
            aggregated, window_count = aggregate_long_sequence(
                seq=seq,
                tokenizer=tokenizer,
                model=model,
                device=device,
                max_length=args.max_length,
                overlap=args.window_overlap,
                window_batch_size=args.long_seq_window_batch_size,
                use_amp=args.use_amp,
            )
            if not validated_first_long:
                print(
                    f"[DEBUG] First long sequence aggregated from {window_count} windows | "
                    f"orig_len={seq_len} | overlap={args.window_overlap}"
                )
                print("[DEBUG] First long aggregated stats:", tensor_stats(aggregated))
                validated_first_long = True
            emb = aggregated.to(dtype=target_dtype).cpu()
            if torch.all(emb == 0):
                raise RuntimeError("Encountered an all-zero aggregated embedding for a long sequence.")
            if not torch.isfinite(emb).all():
                raise RuntimeError("Encountered NaN/Inf aggregated embedding for a long sequence.")
            batch_embeddings[orig_idx] = emb
            batch_effective_lens[orig_idx] = seq_len
            batch_truncated[orig_idx] = False

        if any(item is None for item in batch_embeddings):
            raise RuntimeError("Some embeddings were not generated for the current batch.")

        stacked = torch.stack([item for item in batch_embeddings if item is not None], dim=0)
        embs_buf.append(stacked)
        ids_buf.extend(ids)
        orig_len_buf.append(orig_seq_lens.cpu())
        eff_len_buf.append(torch.tensor(batch_effective_lens, dtype=torch.long))
        trunc_buf.append(torch.tensor(batch_truncated, dtype=torch.bool))

        while len(ids_buf) >= args.shard_size:
            embs_cat = torch.cat(embs_buf, dim=0)
            orig_len_cat = torch.cat(orig_len_buf, dim=0)
            eff_len_cat = torch.cat(eff_len_buf, dim=0)
            trunc_cat = torch.cat(trunc_buf, dim=0)

            save_shard(
                shard_path,
                ids_buf[: args.shard_size],
                embs_cat[: args.shard_size],
                orig_len_cat[: args.shard_size],
                eff_len_cat[: args.shard_size],
                trunc_cat[: args.shard_size],
            )

            embs_buf = [embs_cat[args.shard_size :]]
            orig_len_buf = [orig_len_cat[args.shard_size :]]
            eff_len_buf = [eff_len_cat[args.shard_size :]]
            trunc_buf = [trunc_cat[args.shard_size :]]
            ids_buf = ids_buf[args.shard_size :]
            shard_idx += 1
            shard_path = out_dir / f"shard_{shard_idx:05d}.pt"

    if ids_buf:
        save_shard(
            shard_path,
            ids_buf,
            torch.cat(embs_buf, dim=0),
            torch.cat(orig_len_buf, dim=0),
            torch.cat(eff_len_buf, dim=0),
            torch.cat(trunc_buf, dim=0),
        )

    print("Done.")


if __name__ == "__main__":
    main()
