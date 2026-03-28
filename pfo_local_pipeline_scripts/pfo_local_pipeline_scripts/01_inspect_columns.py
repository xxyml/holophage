from pathlib import Path
from utils import load_config, resolve_path, safe_read_table

cfg = load_config()
project_root = Path(cfg["project_root"])
raw_path = resolve_path(project_root, cfg["paths"]["raw_protein_table"])

print(f"[INFO] Inspecting: {raw_path}")
df = safe_read_table(
    raw_path,
    sep=cfg["input"]["sep"],
    encoding=cfg["input"]["encoding"],
    nrows=cfg["input"]["preview_nrows"],
)

print("\n[INFO] Columns:")
for c in df.columns.tolist():
    print("-", c)

print("\n[INFO] Preview:")
print(df.head(cfg["input"]["preview_nrows"]).to_string(index=False))

print("\n[INFO] 如果列名与 config.yaml 不一致，请先修改 config.yaml 再继续。")
