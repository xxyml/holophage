import argparse
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def build_parquet(src: Path, out: Path, chunksize: int) -> None:
    writer = None
    rows_written = 0

    if out.exists():
        out.unlink()

    try:
        for chunk_idx, chunk in enumerate(
            pd.read_csv(
                src,
                sep="\t",
                usecols=["protein_id", "protein_sequence"],
                chunksize=chunksize,
                low_memory=False,
            ),
            start=1,
        ):
            chunk = chunk.rename(
                columns={"protein_id": "id", "protein_sequence": "sequence"}
            )
            chunk["id"] = chunk["id"].astype(str)
            chunk["sequence"] = chunk["sequence"].astype(str)

            table = pa.Table.from_pandas(chunk, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(out, table.schema, compression="snappy")

            writer.write_table(table)
            rows_written += len(chunk)
            print(f"chunk={chunk_idx} rows_written={rows_written}")
    finally:
        if writer is not None:
            writer.close()

    if not out.exists():
        raise RuntimeError(f"failed to create parquet: {out}")

    print(f"done rows={rows_written} size={out.stat().st_size} path={out}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild embedding input parquet from the current authoritative protein table."
    )
    parser.add_argument("--src", required=True, help="Source TSV path")
    parser.add_argument("--out", required=True, help="Output parquet path")
    parser.add_argument("--chunksize", type=int, default=200000)
    args = parser.parse_args()

    build_parquet(Path(args.src), Path(args.out), args.chunksize)


if __name__ == "__main__":
    main()
