from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build exact-sequence embedding input parquet from the current label table."
    )
    parser.add_argument(
        "--src",
        default=r"D:\data\ai4s\holophage\data_processed\training_labels_wide_with_split.csv",
        help="Source CSV with exact_sequence_rep_id and sequence columns.",
    )
    parser.add_argument(
        "--out",
        default=r"D:\data\ai4s\holophage\embedding_pipeline\inputs\exact_sequence_embedding_input.parquet",
        help="Output parquet path.",
    )
    parser.add_argument("--chunksize", type=int, default=200000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    src = Path(args.src)
    out = Path(args.out)
    if out.exists():
        out.unlink()

    seen: set[str] = set()
    writer: pq.ParquetWriter | None = None
    rows_written = 0
    rows_seen = 0

    try:
        for chunk_idx, chunk in enumerate(
            pd.read_csv(
                src,
                usecols=["exact_sequence_rep_id", "sequence"],
                chunksize=args.chunksize,
                low_memory=False,
            ),
            start=1,
        ):
            rows_seen += len(chunk)
            chunk = chunk.dropna(subset=["exact_sequence_rep_id", "sequence"]).copy()
            chunk["exact_sequence_rep_id"] = chunk["exact_sequence_rep_id"].astype(str)
            chunk["sequence"] = chunk["sequence"].astype(str)
            chunk = chunk.drop_duplicates(subset=["exact_sequence_rep_id"], keep="first")
            chunk = chunk[~chunk["exact_sequence_rep_id"].isin(seen)].copy()
            if chunk.empty:
                print(f"[exact-input] chunk={chunk_idx} rows_seen={rows_seen} rows_written={rows_written}")
                continue

            seen.update(chunk["exact_sequence_rep_id"].tolist())
            chunk = chunk.rename(columns={"exact_sequence_rep_id": "id"})
            table = pa.Table.from_pandas(chunk[["id", "sequence"]], preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(out, table.schema, compression="snappy")
            writer.write_table(table)
            rows_written += len(chunk)
            print(f"[exact-input] chunk={chunk_idx} rows_seen={rows_seen} rows_written={rows_written}")
    finally:
        if writer is not None:
            writer.close()

    if not out.exists():
        raise RuntimeError(f"failed to create output: {out}")

    print(f"[exact-input] done path={out}")
    print(f"[exact-input] rows={rows_written}")
    print(f"[exact-input] size={out.stat().st_size}")


if __name__ == "__main__":
    main()
