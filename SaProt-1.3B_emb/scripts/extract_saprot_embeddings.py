import argparse
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = BASE_DIR / "inputs" / "exact_sequence_embedding_input.parquet"
DEFAULT_MODEL_DIR = BASE_DIR / "models" / "SaProt_1.3B_AF2"
DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs" / "embed_exact"
DEFAULT_LOG_DIR = BASE_DIR / "logs"
DEFAULT_MANIFEST_DIR = BASE_DIR / "manifests"


def sanitize_protein_sequence(seq: str) -> str:
    seq = str(seq).upper().strip()
    for ch in ["U", "Z", "O", "B"]:
        seq = seq.replace(ch, "X")
    return seq


def normalize_protein_sequence(seq: str) -> str:
    seq = sanitize_protein_sequence(seq)
    # SaProt AA-only mode still expects structure-aware tokens.
    # We therefore map each residue to the placeholder structural token "#",
    # yielding a sequence like "A#C#D#".
    return "".join(f"{aa}#" for aa in seq)


def saprot_aa_only_tokens(seq: str) -> list[str]:
    if len(seq) % 2 != 0:
        raise ValueError(f"SaProt AA-only sequence must have even length, got {len(seq)}")
    return [seq[i : i + 2] for i in range(0, len(seq), 2)]


class ProtSeqDataset(Dataset):
    def __init__(self, df: pd.DataFrame, id_col: str = "id", seq_col: str = "sequence", seq_len_col: str = "seq_len"):
        self.df = df.reset_index(drop=True)
        self.id_col = id_col
        self.seq_col = seq_col
        self.seq_len_col = seq_len_col

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        row = self.df.iloc[idx]
        return {
            "protein_id": str(row[self.id_col]),
            "sequence": str(row[self.seq_col]),
            "orig_seq_len": int(row[self.seq_len_col]),
        }


def collate_fn(batch: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "protein_id": [b["protein_id"] for b in batch],
        "sequence": [b["sequence"] for b in batch],
        "orig_seq_lens": torch.tensor([b["orig_seq_len"] for b in batch], dtype=torch.long),
    }


def tensor_stats(t: torch.Tensor) -> str:
    t = t.detach().float().cpu()
    return (
        f"shape={tuple(t.shape)} "
        f"mean={t.mean().item():.6f} "
        f"std={t.std().item():.6f} "
        f"absmax={t.abs().max().item():.6f}"
    )


def build_windows(seq: str, max_length: int, overlap: int) -> list[tuple[int, int, str]]:
    tokens = saprot_aa_only_tokens(seq)
    token_len = len(tokens)
    if token_len <= max_length:
        return [(0, token_len, seq)]
    if overlap < 0 or overlap >= max_length:
        raise ValueError("window_overlap must be in [0, max_length)")

    stride = max_length - overlap
    windows: list[tuple[int, int, str]] = []
    start = 0
    while start < token_len:
        end = min(start + max_length, token_len)
        if end - start < max_length and start != 0:
            start = max(0, token_len - max_length)
            end = token_len
        windows.append((start, end, "".join(tokens[start:end])))
        if end >= token_len:
            break
        start += stride
    return windows


def coverage_weights(windows: list[tuple[int, int, str]]) -> list[int]:
    weights: list[int] = []
    covered_until = 0
    for start, end, _ in windows:
        unique = end - max(start, covered_until)
        weights.append(max(1, unique))
        covered_until = max(covered_until, end)
    return weights


def residue_mask_from_inputs(input_ids: torch.Tensor, attention_mask: torch.Tensor, tokenizer: Any) -> torch.Tensor:
    special_ids = torch.tensor(sorted(set(tokenizer.all_special_ids)), device=input_ids.device)
    special_mask = torch.isin(input_ids, special_ids)
    return attention_mask.bool() & (~special_mask)


def pooled_from_model_output(hidden: torch.Tensor, residue_mask: torch.Tensor) -> torch.Tensor:
    mask = residue_mask.unsqueeze(-1).float()
    return (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-8)


def encode_sequence_batch(
    seqs: list[str],
    tokenizer: Any,
    model: Any,
    device: torch.device,
    max_length: int,
    use_amp: bool,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    enc = tokenizer(
        seqs,
        padding=True,
        truncation=True,
        max_length=max_length + 2,
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
        residue_mask = residue_mask_from_inputs(input_ids, attention_mask, tokenizer)
        pooled = pooled_from_model_output(hidden, residue_mask)
    return pooled, hidden, input_ids, residue_mask


def aggregate_long_sequence(
    seq: str,
    tokenizer: Any,
    model: Any,
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
        pooled, _, _, _ = encode_sequence_batch(
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


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


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
    print(f"Saved {out_path} | N={len(ids)} | emb_shape={tuple(embeddings.shape)} | dtype={embeddings.dtype}")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Precompute SaProt-1.3B AA-only protein embeddings from parquet.")
    ap.add_argument("--data_path", type=Path, default=DEFAULT_INPUT_PATH)
    ap.add_argument("--out_dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--model_path", type=Path, default=DEFAULT_MODEL_DIR)
    ap.add_argument("--manifests_dir", type=Path, default=DEFAULT_MANIFEST_DIR)
    ap.add_argument("--logs_dir", type=Path, default=DEFAULT_LOG_DIR)
    ap.add_argument("--batch_size", type=int, default=4)
    ap.add_argument("--num_workers", type=int, default=0)
    ap.add_argument("--shard_size", type=int, default=20000)
    ap.add_argument("--dtype", type=str, default="float16", choices=["float16", "float32"])
    ap.add_argument("--use_amp", action="store_true")
    ap.add_argument("--device", type=str, default="cuda")
    ap.add_argument("--sort_by_length", action="store_true", default=True)
    ap.add_argument("--no-sort_by_length", dest="sort_by_length", action="store_false")
    ap.add_argument("--id_col", type=str, default="id")
    ap.add_argument("--seq_col", type=str, default="sequence")
    ap.add_argument("--seq_len_col", type=str, default="seq_len")
    ap.add_argument("--window_overlap", type=int, default=256)
    ap.add_argument("--long_seq_window_batch_size", type=int, default=2)
    ap.add_argument("--limit_rows", type=int, default=None)
    ap.add_argument("--preflight-only", action="store_true")
    ap.add_argument("--resume-auto", action="store_true")
    ap.add_argument("--start_shard", type=int, default=None)
    return ap.parse_args()


def detect_resume_shard(out_dir: Path, manifests_dir: Path) -> int:
    progress_path = manifests_dir / "progress.json"
    last_from_progress = -1
    if progress_path.exists():
        try:
            payload = json.loads(progress_path.read_text(encoding="utf-8"))
            last_from_progress = int(payload.get("last_completed_shard", -1))
        except Exception:
            last_from_progress = -1

    shard_files = sorted(out_dir.glob("shard_*.pt"))
    last_from_disk = -1
    if shard_files:
        last_name = shard_files[-1].stem
        last_from_disk = int(last_name.split("_")[-1])

    return max(last_from_progress, last_from_disk) + 1


def main() -> None:
    args = parse_args()

    if not args.data_path.exists():
        raise FileNotFoundError(f"Input parquet not found: {args.data_path}")
    if not args.model_path.exists():
        raise FileNotFoundError(f"Model path not found: {args.model_path}")

    for folder in [args.out_dir, args.manifests_dir, args.logs_dir]:
        folder.mkdir(parents=True, exist_ok=True)

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"

    print(f"Using device: {device}")
    print("Loading parquet...")
    df = pd.read_parquet(args.data_path)

    for col in [args.id_col, args.seq_col]:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    df[args.id_col] = df[args.id_col].astype(str)
    if not df[args.id_col].is_unique:
        raise ValueError(f"{args.id_col} is not unique")

    raw_seq = df[args.seq_col].astype(str).map(sanitize_protein_sequence)

    if args.seq_len_col not in df.columns:
        print(f"[WARN] {args.seq_len_col} not found, computing from sequence")
        df[args.seq_len_col] = raw_seq.str.len()

    df = df[df[args.seq_col].notna()].copy()
    df["__raw_seq"] = raw_seq
    df = df[df["__raw_seq"] != ""].copy()
    df[args.seq_len_col] = df["__raw_seq"].str.len()
    df[args.seq_col] = df["__raw_seq"].map(normalize_protein_sequence)
    df = df.drop(columns=["__raw_seq"])

    if args.sort_by_length:
        df = df.sort_values(args.seq_len_col, ascending=True).reset_index(drop=True)

    if args.limit_rows is not None:
        df = df.iloc[: args.limit_rows].copy().reset_index(drop=True)

    print(f"Total usable rows: {len(df)}")
    print("Loading tokenizer/model from local path...")
    print(f"Using local model path: {args.model_path}")

    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True)
    model = AutoModel.from_pretrained(args.model_path, local_files_only=True).to(device)
    if args.dtype == "float16" and device.type == "cuda":
        model = model.half()
    model.eval()

    hidden_size = int(getattr(model.config, "hidden_size"))
    max_position_embeddings = int(getattr(model.config, "max_position_embeddings", 1026))
    max_context_aa = max(1, max_position_embeddings - 2)
    num_long = int((df[args.seq_len_col] > max_context_aa).sum())
    print(
        f"Sequences longer than max_context_aa={max_context_aa}: "
        f"{num_long}/{len(df)} (will use sliding windows, overlap={args.window_overlap})"
    )

    schema = {
        "model_name": str(args.model_path),
        "input_path": str(args.data_path),
        "hidden_size": hidden_size,
        "dtype": args.dtype,
        "max_position_embeddings": max_position_embeddings,
        "max_context_aa": max_context_aa,
        "window_overlap": args.window_overlap,
        "shard_size": args.shard_size,
        "id_col": args.id_col,
        "seq_col": args.seq_col,
        "seq_len_col": args.seq_len_col,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    save_json(args.manifests_dir / "schema.json", schema)

    ds = ProtSeqDataset(df=df, id_col=args.id_col, seq_col=args.seq_col, seq_len_col=args.seq_len_col)
    dl = DataLoader(
        ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
        collate_fn=collate_fn,
    )

    if args.start_shard is not None:
        start_shard = args.start_shard
    elif args.resume_auto:
        start_shard = detect_resume_shard(args.out_dir, args.manifests_dir)
    else:
        start_shard = 0

    target_dtype = torch.float16 if args.dtype == "float16" else torch.float32
    to_skip = start_shard * args.shard_size
    shard_idx = start_shard
    shard_path = args.out_dir / f"shard_{shard_idx:05d}.pt"

    ids_buf: list[str] = []
    embs_buf: list[torch.Tensor] = []
    orig_len_buf: list[torch.Tensor] = []
    eff_len_buf: list[torch.Tensor] = []
    trunc_buf: list[torch.Tensor] = []

    validated_first_batch = False
    validated_first_long = False
    rows_done = start_shard * args.shard_size

    print("Start SaProt embedding precompute...")
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
            if seq_len <= max_context_aa:
                short_items.append((idx, pid, seq, seq_len))
            else:
                long_items.append((idx, pid, seq, seq_len))

        batch_embeddings: list[torch.Tensor | None] = [None] * len(ids)
        batch_effective_lens = [0] * len(ids)
        batch_truncated = [False] * len(ids)

        if short_items:
            short_seqs = [item[2] for item in short_items]
            pooled, hidden, input_ids, residue_mask = encode_sequence_batch(
                seqs=short_seqs,
                tokenizer=tokenizer,
                model=model,
                device=device,
                max_length=max_context_aa,
                use_amp=args.use_amp,
            )
            if not validated_first_batch:
                print("[DEBUG] First batch input_ids stats:", tensor_stats(input_ids))
                print("[DEBUG] First batch hidden stats:", tensor_stats(hidden))
                print("[DEBUG] First batch pooled stats:", tensor_stats(pooled))
                print("[DEBUG] First batch residue_mask true_count:", int(residue_mask.sum().item()))
                if torch.all(pooled == 0):
                    raise RuntimeError("First batch pooled embeddings are all zero.")
                if not torch.isfinite(pooled).all():
                    raise RuntimeError("First batch pooled embeddings contain NaN/Inf values.")
                validated_first_batch = True
                if args.preflight_only:
                    print("Preflight passed.")
                    return

            pooled_cpu = pooled.to(dtype=target_dtype).cpu()
            for local_idx, (orig_idx, _, _, seq_len) in enumerate(short_items):
                batch_embeddings[orig_idx] = pooled_cpu[local_idx]
                batch_effective_lens[orig_idx] = seq_len
                batch_truncated[orig_idx] = False

        for orig_idx, _, seq, seq_len in long_items:
            aggregated, window_count = aggregate_long_sequence(
                seq=seq,
                tokenizer=tokenizer,
                model=model,
                device=device,
                max_length=max_context_aa,
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

            rows_done += args.shard_size
            progress = {
                "last_completed_shard": shard_idx,
                "rows_done": rows_done,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "input_path": str(args.data_path),
                "model_path": str(args.model_path),
                "hidden_size": hidden_size,
                "max_context": max_context_aa,
                "resume_auto": True,
            }
            save_json(args.manifests_dir / "progress.json", progress)

            embs_buf = [embs_cat[args.shard_size :]]
            orig_len_buf = [orig_len_cat[args.shard_size :]]
            eff_len_buf = [eff_len_cat[args.shard_size :]]
            trunc_buf = [trunc_cat[args.shard_size :]]
            ids_buf = ids_buf[args.shard_size :]
            shard_idx += 1
            shard_path = args.out_dir / f"shard_{shard_idx:05d}.pt"

    if ids_buf:
        save_shard(
            shard_path,
            ids_buf,
            torch.cat(embs_buf, dim=0),
            torch.cat(orig_len_buf, dim=0),
            torch.cat(eff_len_buf, dim=0),
            torch.cat(trunc_buf, dim=0),
        )
        rows_done += len(ids_buf)
        progress = {
            "last_completed_shard": shard_idx,
            "rows_done": rows_done,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "input_path": str(args.data_path),
            "model_path": str(args.model_path),
            "hidden_size": hidden_size,
            "max_context": max_context_aa,
            "resume_auto": True,
        }
        save_json(args.manifests_dir / "progress.json", progress)

    summary = {
        "input_path": str(args.data_path),
        "model_path": str(args.model_path),
        "rows_total": len(df),
        "rows_done": rows_done,
        "hidden_size": hidden_size,
        "max_position_embeddings": max_position_embeddings,
        "max_context_aa": max_context_aa,
        "num_long_sequences": num_long,
        "num_shards_expected": math.ceil(len(df) / args.shard_size),
        "num_shards_written": len(list(args.out_dir.glob("shard_*.pt"))),
        "dtype": args.dtype,
        "batch_size": args.batch_size,
        "window_overlap": args.window_overlap,
        "long_seq_window_batch_size": args.long_seq_window_batch_size,
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "truncated_any": False,
    }
    save_json(args.manifests_dir / "summary.json", summary)
    print("Done.")


if __name__ == "__main__":
    main()
