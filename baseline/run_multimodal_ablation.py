from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from baseline.common import REPO_ROOT, resolve_path


VARIANT_SPECS = {
    "seq_only": {
        "config": "baseline/train_config.multimodal_v2.stage1.yaml",
        "run_slug": "multimodal_v2_seq_only_hc",
    },
    "seq_struct": {
        "config": "baseline/train_config.multimodal_v2.seq_struct.yaml",
        "run_slug": "multimodal_v2_seq_struct_hc",
    },
    "seq_ctx": {
        "config": "baseline/train_config.multimodal_v2.seq_ctx.yaml",
        "run_slug": "multimodal_v2_seq_ctx_handcrafted_hc",
    },
    "seq_ctx_gnn_w1": {
        "config": "baseline/train_config.multimodal_v2.seq_ctx_gnn_w1.yaml",
        "run_slug": "multimodal_v2_seq_ctx_gnn_v2a_w1_hc",
    },
    "seq_ctx_gnn_w2": {
        "config": "baseline/train_config.multimodal_v2.seq_ctx_gnn_w2.yaml",
        "run_slug": "multimodal_v2_seq_ctx_gnn_v2a_w2_hc",
    },
    "seq_ctx_gnn_w4": {
        "config": "baseline/train_config.multimodal_v2.seq_ctx_gnn_w4.yaml",
        "run_slug": "multimodal_v2_seq_ctx_gnn_v2a_w4_hc",
    },
    "all": {
        "config": "baseline/train_config.multimodal_v2.all.yaml",
        "run_slug": "multimodal_v2_all_hc",
    },
}


@dataclass(frozen=True)
class RunSpec:
    variant: str
    config_path: Path
    seed: int
    output_dir: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multimodal v2 ablation matrix.")
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=list(VARIANT_SPECS.keys()),
        default=["seq_only", "seq_struct", "seq_ctx", "all"],
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 52, 62])
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--smoke-steps", type=int, default=1)
    parser.add_argument("--limit-train", type=int, default=None)
    parser.add_argument("--limit-val", type=int, default=None)
    parser.add_argument("--limit-test", type=int, default=None)
    parser.add_argument("--skip-prepack", action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--overwrite-prepack", action="store_true")
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--summary-prefix", default="baseline/runs/multimodal_v2_ablation_summary")
    return parser.parse_args()


def run_command(command: list[str]) -> None:
    print("[ablation-runner] " + " ".join(command))
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def build_run_spec(variant: str, seed: int) -> RunSpec:
    config_path = resolve_path(VARIANT_SPECS[variant]["config"], REPO_ROOT)
    run_name = f"{VARIANT_SPECS[variant]['run_slug']}_seed{seed}"
    output_dir = REPO_ROOT / "baseline" / "runs" / run_name
    return RunSpec(
        variant=variant,
        config_path=config_path,
        seed=int(seed),
        output_dir=output_dir,
    )


def prepack_command(args: argparse.Namespace, spec: RunSpec) -> list[str]:
    command = [
        args.python_exe,
        "-m",
        "baseline.prepack_multimodal",
        "--config",
        str(spec.config_path),
    ]
    if args.overwrite_prepack:
        command.append("--overwrite")
    if args.limit_train is not None:
        command += ["--limit-train", str(args.limit_train)]
    if args.limit_val is not None:
        command += ["--limit-val", str(args.limit_val)]
    if args.limit_test is not None:
        command += ["--limit-test", str(args.limit_test)]
    return command


def train_command(args: argparse.Namespace, spec: RunSpec) -> list[str]:
    command = [
        args.python_exe,
        "-m",
        "baseline.train_multimodal",
        "--config",
        str(spec.config_path),
        "--seed",
        str(spec.seed),
        "--output-dir",
        str(spec.output_dir),
    ]
    if args.limit_train is not None:
        command += ["--limit-train", str(args.limit_train)]
    if args.limit_val is not None:
        command += ["--limit-val", str(args.limit_val)]
    if args.smoke:
        command += ["--smoke-steps", str(args.smoke_steps)]
    return command


def eval_command(args: argparse.Namespace, spec: RunSpec) -> list[str]:
    checkpoint_path = spec.output_dir / "checkpoints" / "best.pt"
    command = [
        args.python_exe,
        "-m",
        "baseline.evaluate_multimodal",
        "--config",
        str(spec.config_path),
        "--checkpoint",
        str(checkpoint_path),
        "--split",
        "val",
        "--output-dir",
        str(spec.output_dir),
    ]
    if args.limit_val is not None:
        command += ["--limit", str(args.limit_val)]
    return command


def summary_command(args: argparse.Namespace) -> list[str]:
    return [
        args.python_exe,
        "-m",
        "baseline.summarize_multimodal_ablation",
        "--output-prefix",
        str(resolve_path(args.summary_prefix, REPO_ROOT)),
    ]


def main() -> None:
    args = parse_args()
    specs = [build_run_spec(variant, seed) for variant in args.variants for seed in args.seeds]

    # Prepack is variant-level, not seed-level.
    if not args.skip_prepack:
        seen_variants: set[str] = set()
        for spec in specs:
            if spec.variant in seen_variants:
                continue
            seen_variants.add(spec.variant)
            run_command(prepack_command(args, spec))

    for spec in specs:
        if not args.skip_train:
            run_command(train_command(args, spec))
        if not args.skip_eval:
            run_command(eval_command(args, spec))

    run_command(summary_command(args))


if __name__ == "__main__":
    main()
