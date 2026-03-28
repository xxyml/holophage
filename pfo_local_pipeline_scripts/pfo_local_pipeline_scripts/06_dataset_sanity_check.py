from pathlib import Path
import pandas as pd
from utils import load_config, resolve_path, ensure_dirs, write_markdown

cfg = load_config()
project_root = Path(cfg["project_root"])
proc_dir = resolve_path(project_root, cfg["paths"]["processed_dir"])
out_dir = resolve_path(project_root, cfg["paths"]["outputs_dir"])
ensure_dirs(out_dir)

wide = pd.read_csv(proc_dir / "training_labels_wide.csv", low_memory=False)

report = []
report.append("# Training Data Sanity Check\n")
report.append("## 1. status counts")
report.append(wide["status"].value_counts(dropna=False).to_markdown())
report.append("\n## 2. L1 counts")
report.append(wide["level1_label"].fillna("").value_counts(dropna=False).head(50).to_markdown())
report.append("\n## 3. L2 counts")
report.append(wide["level2_label"].fillna("").value_counts(dropna=False).head(100).to_markdown())
report.append("\n## 4. L3 primary counts")
report.append(wide["node_primary"].fillna("").value_counts(dropna=False).head(100).to_markdown())
report.append("\n## 5. multilabel counts")
report.append(wide["multi_label_flag"].fillna("").value_counts(dropna=False).to_markdown())
report.append("\n## 6. missing mapping summary")
missing_primary = int((wide["node_primary"].fillna("").astype(str).str.len() == 0).sum())
report.append(f"- rows with empty `node_primary`: **{missing_primary}**")

out_path = out_dir / "training_statistics.md"
write_markdown(out_path, "\n".join(report))
print(f"[OK] saved: {out_path}")
