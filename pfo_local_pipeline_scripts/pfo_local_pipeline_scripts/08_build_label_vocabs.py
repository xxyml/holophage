from pathlib import Path
import json
import pandas as pd
from utils import load_config, resolve_path, ensure_dirs


cfg = load_config()
project_root = Path(cfg["project_root"])
proc_dir = resolve_path(project_root, cfg["paths"]["processed_dir"])
out_dir = resolve_path(project_root, cfg["paths"]["outputs_dir"])
ensure_dirs(out_dir)


def sorted_unique(series):
    vals = []
    for v in series.fillna("").astype(str):
        s = v.strip()
        if s:
            vals.append(s)
    return sorted(set(vals))


wide = pd.read_csv(proc_dir / "training_labels_wide.csv", low_memory=False)
l3_core = pd.read_csv(proc_dir / "dataset_l3_core.csv", low_memory=False)
l3_multi = pd.read_csv(proc_dir / "dataset_l3_multilabel.csv", low_memory=False)

l1_vocab = sorted_unique(wide["level1_label"])
l2_vocab = sorted_unique(wide["level2_label"])
l3_core_vocab = sorted_unique(l3_core["node_primary"])

multi_nodes = []
for col in ["node_primary", "secondary_node"]:
    if col in l3_multi.columns:
        multi_nodes.extend(sorted_unique(l3_multi[col]))
l3_multi_vocab = sorted(set(multi_nodes))

outputs = {
    "label_vocab_l1.json": l1_vocab,
    "label_vocab_l2.json": l2_vocab,
    "label_vocab_l3_core.json": l3_core_vocab,
    "label_vocab_l3_multilabel.json": l3_multi_vocab,
}

for name, vocab in outputs.items():
    path = out_dir / name
    with path.open("w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, indent=2)
    print(f"[OK] saved: {path} ({len(vocab)} labels)")
