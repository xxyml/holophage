from __future__ import annotations

import csv
import gzip
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml


STRUCTURE_DIR = Path(__file__).resolve().parent
REPO_ROOT = STRUCTURE_DIR.parent


def resolve_path(path_str: str | Path, base_dir: Path | None = None) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    root = base_dir or REPO_ROOT
    return (root / path).resolve()


def ensure_dir(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def dump_json(data: Any, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def infer_uniprot_accession(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    patterns = (
        r"^[OPQ][0-9][A-Z0-9]{3}[0-9]$",
        r"^[A-NR-Z][0-9][A-Z0-9]{3}[0-9]$",
        r"^[A-Z0-9]{10}$",
    )
    import re

    for pattern in patterns:
        if re.match(pattern, value):
            return value
    return None


def infer_afdb_entry_id(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value.startswith("AF-") and "-F" in value:
        return value
    return None


def infer_genbank_accession(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    import re

    pattern = r"^[A-Z]{1,4}_[0-9]+(?:\.[0-9]+)?$|^[A-Z]{1,2}[0-9]{5,}\.[0-9]+$|^[A-Z]{3}[0-9]{5,}\.[0-9]+$"
    if re.match(pattern, value):
        return value
    return None


def load_optional_hints(path: Path | None) -> pd.DataFrame | None:
    if path is None or not path.exists():
        return None
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, sep="\t", low_memory=False)


def make_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    return session


def fetch_json(session: requests.Session, url: str, timeout: int = 60, params: dict[str, Any] | None = None) -> tuple[int, Any]:
    response = session.get(url, params=params, timeout=timeout)
    status_code = response.status_code
    response.raise_for_status()
    return status_code, response.json()


def fetch_text(session: requests.Session, url: str, timeout: int = 60) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def fetch_binary_range(session: requests.Session, url: str, start: int, end: int, timeout: int = 120) -> bytes:
    response = session.get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=timeout)
    response.raise_for_status()
    return response.content


def gunzip_bytes(payload: bytes) -> str:
    return gzip.decompress(payload).decode("utf-8")


def normalize_format(format_name: str | None) -> str:
    if not format_name:
        return "cif"
    name = format_name.lower()
    if name in {"mmcif", "cif"}:
        return "cif"
    if name in {"pdb"}:
        return "pdb"
    return name


def write_tsv(rows: list[dict[str, Any]], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
