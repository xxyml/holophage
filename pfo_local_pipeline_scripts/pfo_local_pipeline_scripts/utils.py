from __future__ import annotations
from pathlib import Path
import json
import re
import pandas as pd
import yaml

def load_config(config_path: str | Path = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def resolve_path(project_root: str | Path, relative_path: str | Path) -> Path:
    return Path(project_root) / Path(relative_path)

def ensure_dirs(*dirs: Path) -> None:
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

def normalize_annotation(x, no_mapping_aliases=None, blank_aliases=None):
    no_mapping_aliases = set(no_mapping_aliases or [])
    blank_aliases = set(blank_aliases or [])
    if pd.isna(x):
        return "unresolved_blank_annotation"
    s = str(x).strip()
    s = re.sub(r"\s+", " ", s)
    if s in blank_aliases or s == "":
        return "unresolved_blank_annotation"
    if s.lower() in {str(v).lower() for v in no_mapping_aliases}:
        return "no_phrog_mapping"
    return s

def write_markdown(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")

def safe_read_table(path: Path, sep="\t", encoding="utf-8", nrows=None):
    return pd.read_csv(path, sep=sep, encoding=encoding, nrows=nrows, low_memory=False)

def dump_json(path: Path, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
