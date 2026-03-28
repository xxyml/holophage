from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml


BASELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASELINE_DIR.parent
ACTIVE_ASSETS_DIR = REPO_ROOT / "project_memory" / "04_active_assets"
ACTIVE_VERSION_PATH = ACTIVE_ASSETS_DIR / "ACTIVE_VERSION.yaml"
ACTIVE_PATHS_PATH = ACTIVE_ASSETS_DIR / "ACTIVE_PATHS.yaml"
DEPRECATED_CONFIG_PATH_KEYS = (
    "label_table_csv",
    "join_index_csv",
    "prepacked_dir",
    "vocab_l1",
    "vocab_l2",
    "vocab_l3_core",
    "embedding_dir",
    "embedding_index_db",
)


def resolve_path(path_str: str | Path, base_dir: Path | None = None) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    root = base_dir or REPO_ROOT
    return (root / path).resolve()


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_active_paths() -> dict[str, Any]:
    return load_yaml(ACTIVE_PATHS_PATH)


def load_active_version() -> dict[str, Any]:
    return load_yaml(ACTIVE_VERSION_PATH)


def apply_active_runtime_paths(config: dict[str, Any]) -> dict[str, Any]:
    active_paths = load_active_paths()
    runtime_inputs = active_paths.get("paths", {}).get("runtime_inputs", {})
    cfg = copy.deepcopy(config)
    cfg.setdefault("data", {})
    deprecated_mirrors = [key for key in DEPRECATED_CONFIG_PATH_KEYS if key in cfg["data"]]
    if deprecated_mirrors:
        print(
            "[runtime] deprecated config path mirrors detected and overridden by ACTIVE_PATHS.yaml: "
            + ", ".join(sorted(deprecated_mirrors))
        )
    mapping = {
        "label_table_csv": "label_table_csv",
        "join_index_csv": "join_index_csv",
        "vocab_l1": "vocab_l1",
        "vocab_l2": "vocab_l2",
        "vocab_l3_core": "vocab_l3_core",
        "embedding_dir_exact": "embedding_dir",
        "embedding_index_db": "embedding_index_db",
        "prepacked_dir": "prepacked_dir",
    }
    for runtime_key, config_key in mapping.items():
        value = runtime_inputs.get(runtime_key)
        if value:
            cfg["data"][config_key] = value
    return cfg


def resolve_runtime_paths(config: dict[str, Any]) -> dict[str, Path]:
    data = config.get("data", {})
    resolved: dict[str, Path] = {}
    for key in (
        "label_table_csv",
        "join_index_csv",
        "vocab_l1",
        "vocab_l2",
        "vocab_l3_core",
        "embedding_dir",
        "embedding_index_db",
        "prepacked_dir",
    ):
        value = data.get(key)
        if value:
            resolved[key] = resolve_path(value, REPO_ROOT)
    return resolved


def print_runtime_paths(runtime_paths: dict[str, Path]) -> None:
    print("[runtime] resolved active paths:")
    for key in sorted(runtime_paths):
        print(f"[runtime]   {key}: {runtime_paths[key]}")


def validate_paths_exist(required: dict[str, Path]) -> None:
    missing: list[str] = []
    for key, path in required.items():
        if not path.exists():
            missing.append(f"{key}: {path}")
    if missing:
        bullet_block = "\n".join(f"- {item}" for item in missing)
        raise FileNotFoundError(f"Missing required runtime inputs:\n{bullet_block}")


def _nested_get(payload: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    cur: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def validate_runtime_contract(config: dict[str, Any], runtime_paths: dict[str, Path]) -> None:
    active_version = load_active_version()
    active_truth = active_version.get("active_truth", {})
    label_boundary = _nested_get(active_version, "training_contract.label_boundary", {}) or {}

    target_status = str(config.get("data", {}).get("target_status", ""))
    expected_status = str(active_truth.get("target_status_primary", ""))
    if expected_status and target_status != expected_status:
        raise ValueError(
            f"Config target_status={target_status!r} does not match ACTIVE_VERSION target_status_primary={expected_status!r}"
        )
    allowed_splits = sorted(str(x) for x in (config.get("data", {}).get("allowed_splits", []) or []))
    if allowed_splits and allowed_splits != ["test", "train", "val"]:
        raise ValueError(f"Config allowed_splits={allowed_splits!r} does not match current baseline contract ['train', 'val', 'test'].")

    expected_l1 = _nested_get(active_version, "training_contract.label_space.l1_classes")
    expected_l2 = _nested_get(active_version, "training_contract.label_space.l2_classes")
    expected_l3 = _nested_get(active_version, "training_contract.label_space.l3_core_classes")
    if "vocab_l1" in runtime_paths and expected_l1 is not None and len(load_vocab(runtime_paths["vocab_l1"])) != int(expected_l1):
        raise ValueError("L1 vocab size does not match ACTIVE_VERSION manifest.")
    if "vocab_l2" in runtime_paths and expected_l2 is not None and len(load_vocab(runtime_paths["vocab_l2"])) != int(expected_l2):
        raise ValueError("L2 vocab size does not match ACTIVE_VERSION manifest.")
    if "vocab_l3_core" in runtime_paths and expected_l3 is not None and len(load_vocab(runtime_paths["vocab_l3_core"])) != int(expected_l3):
        raise ValueError("L3 core vocab size does not match ACTIVE_VERSION manifest.")

    import pandas as pd

    expected_split_strategy = str(active_truth.get("split_strategy", ""))
    expected_split_version = str(active_truth.get("split_version", ""))
    expected_embedding_key = str(active_truth.get("sequence_embedding_key", ""))

    label_table = runtime_paths.get("label_table_csv")
    if label_table is not None and label_table.exists():
        sample = pd.read_csv(
            label_table,
            usecols=["split_strategy", "split_version", "status"],
            nrows=5000,
            low_memory=False,
        )
        if expected_split_strategy and not sample["split_strategy"].fillna("").astype(str).eq(expected_split_strategy).all():
            raise ValueError("Label table split_strategy does not match ACTIVE_VERSION manifest.")
        if expected_split_version and not sample["split_version"].fillna("").astype(str).eq(expected_split_version).all():
            raise ValueError("Label table split_version does not match ACTIVE_VERSION manifest.")

    join_index = runtime_paths.get("join_index_csv")
    if join_index is not None and join_index.exists():
        sample = pd.read_csv(
            join_index,
            usecols=["sequence_embedding_key", "exact_sequence_rep_id", "split_strategy", "split_version", "status"],
            nrows=5000,
            low_memory=False,
        )
        if expected_embedding_key == "exact_sequence_rep_id":
            matches = sample["sequence_embedding_key"].fillna("").astype(str).eq(
                sample["exact_sequence_rep_id"].fillna("").astype(str)
            )
            if not matches.all():
                raise ValueError("Join index sequence_embedding_key is not aligned to exact_sequence_rep_id.")
        if expected_split_strategy and not sample["split_strategy"].fillna("").astype(str).eq(expected_split_strategy).all():
            raise ValueError("Join index split_strategy does not match ACTIVE_VERSION manifest.")
        if expected_split_version and not sample["split_version"].fillna("").astype(str).eq(expected_split_version).all():
            raise ValueError("Join index split_version does not match ACTIVE_VERSION manifest.")

    if bool(label_boundary.get("node_primary_is_full_l3_vocab", True)):
        raise ValueError("ACTIVE_VERSION manifest violates current contract: node_primary_is_full_l3_vocab must be false.")


def load_vocab(path: str | Path) -> dict[str, int]:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if isinstance(raw, list):
        return {label: idx for idx, label in enumerate(raw)}
    if isinstance(raw, dict):
        return {str(label): int(idx) for label, idx in raw.items()}
    raise TypeError(f"Unsupported vocab format: {type(raw)!r}")


def dump_json(data: Any, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def ensure_dir(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory
