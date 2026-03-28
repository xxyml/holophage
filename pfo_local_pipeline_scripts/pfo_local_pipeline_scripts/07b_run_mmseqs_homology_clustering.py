from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from utils import ensure_dirs, load_config, resolve_path


def rel_to_workspace(path: Path, workspace_root: Path) -> str:
    rel = path.resolve().relative_to(workspace_root.resolve())
    return f"/workspace/{rel.as_posix()}"


def run_cmd(cmd: list[str]) -> None:
    printable = " ".join(shlex.quote(part) for part in cmd)
    print(f"[RUN] {printable}")
    subprocess.run(cmd, check=True)


cfg = load_config()
project_root = Path(cfg["project_root"])
hom_cfg = cfg["split"].get("homology", {})

docker_image = str(hom_cfg["docker_image"])
threads = int(hom_cfg.get("threads", 8))
exact_workflow = str(hom_cfg.get("exact_workflow", "easy-linclust"))
cluster_workflow = str(hom_cfg.get("cluster_workflow", "easy-cluster"))

fasta_path = resolve_path(project_root, hom_cfg["fasta_path"])
exact_prefix = resolve_path(project_root, hom_cfg["exact_prefix"])
exact_tmp_dir = resolve_path(project_root, hom_cfg["exact_tmp_dir"])
homology_prefix = resolve_path(project_root, hom_cfg["homology_prefix"])
homology_tmp_dir = resolve_path(project_root, hom_cfg["homology_tmp_dir"])

ensure_dirs(exact_prefix.parent, exact_tmp_dir, homology_prefix.parent, homology_tmp_dir)

workspace_mount = project_root.resolve().as_posix()

common_prefix = [
    "docker",
    "run",
    "--rm",
    "-v",
    f"{workspace_mount}:/workspace",
    "-w",
    "/workspace",
    docker_image,
]

exact_cmd = common_prefix + [
    exact_workflow,
    rel_to_workspace(fasta_path, project_root),
    rel_to_workspace(exact_prefix, project_root),
    rel_to_workspace(exact_tmp_dir, project_root),
    "--min-seq-id",
    str(hom_cfg["exact_min_seq_id"]),
    "-c",
    str(hom_cfg["exact_coverage"]),
    "--cov-mode",
    str(hom_cfg.get("exact_cov_mode", 0)),
    "--threads",
    str(threads),
]

homology_input = exact_prefix.parent / f"{exact_prefix.name}_rep_seq.fasta"
cluster_cmd = common_prefix + [
    cluster_workflow,
    rel_to_workspace(homology_input, project_root),
    rel_to_workspace(homology_prefix, project_root),
    rel_to_workspace(homology_tmp_dir, project_root),
    "--min-seq-id",
    str(hom_cfg["cluster_min_seq_id"]),
    "-c",
    str(hom_cfg["cluster_coverage"]),
    "--cov-mode",
    str(hom_cfg.get("cluster_cov_mode", 0)),
    "-e",
    str(hom_cfg["cluster_evalue"]),
    "--threads",
    str(threads),
]

if not (exact_prefix.parent / f"{exact_prefix.name}_cluster.tsv").exists():
    run_cmd(exact_cmd)
else:
    print(f"[SKIP] exact cluster already exists: {exact_prefix.parent / f'{exact_prefix.name}_cluster.tsv'}")

if not homology_input.exists():
    raise FileNotFoundError(f"Missing representative FASTA after exact clustering: {homology_input}")

if not (homology_prefix.parent / f"{homology_prefix.name}_cluster.tsv").exists():
    run_cmd(cluster_cmd)
else:
    print(
        f"[SKIP] homology cluster already exists: "
        f"{homology_prefix.parent / f'{homology_prefix.name}_cluster.tsv'}"
    )

print("[OK] MMseqs2 exact dedup + homology clustering finished.")
