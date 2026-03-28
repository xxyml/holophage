from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DOCS_PATH = REPO_ROOT / "project_memory" / "04_active_assets" / "ACTIVE_DOCS.md"
SECTION_RE = re.compile(r"^##\s+(active_runtime_docs|active_reference_docs)\s*$")
LINK_RE = re.compile(r"^- \[[^\]]+\]\(([^)]+)\)\s*$")
FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
REQUIRED_FIELDS = ("doc_status", "last_verified")


@dataclass
class CheckResult:
    path: Path
    status: str
    issues: list[str] = field(default_factory=list)


def load_active_doc_targets(path: Path) -> dict[str, list[Path]]:
    text = path.read_text(encoding="utf-8")
    targets: dict[str, list[Path]] = {
        "active_runtime_docs": [],
        "active_reference_docs": [],
    }
    current_section: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        section_match = SECTION_RE.match(line)
        if section_match:
            current_section = section_match.group(1)
            continue
        if line.startswith("## "):
            current_section = None
            continue
        if current_section is None:
            continue
        link_match = LINK_RE.match(line)
        if not link_match:
            continue
        target = link_match.group(1).strip()
        targets[current_section].append(normalize_doc_path(target))

    return targets


def normalize_doc_path(target: str) -> Path:
    candidate = Path(target)
    if candidate.is_absolute():
        return candidate
    return (REPO_ROOT / candidate).resolve()


def parse_top_level_fields(block_lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in block_lines:
        if not line.strip():
            continue
        if line != line.lstrip():
            continue
        match = FIELD_RE.match(line)
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return fields


def find_metadata_blocks(lines: list[str]) -> list[tuple[int, int, dict[str, str]]]:
    delimiter_indexes = [idx for idx, line in enumerate(lines) if line.strip() == "---"]
    blocks: list[tuple[int, int, dict[str, str]]] = []
    for start, end in zip(delimiter_indexes, delimiter_indexes[1:]):
        if end <= start + 1:
            continue
        fields = parse_top_level_fields(lines[start + 1 : end])
        if fields:
            blocks.append((start, end, fields))
    return blocks


def check_markdown_metadata(path: Path) -> CheckResult:
    if not path.exists():
        return CheckResult(path=path, status="FAIL", issues=["file does not exist"])
    if path.suffix.lower() != ".md":
        return CheckResult(
            path=path,
            status="WARN",
            issues=["non-Markdown asset skipped; checker only validates tail metadata blocks in Markdown docs"],
        )

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    metadata_blocks = find_metadata_blocks(lines)
    if not metadata_blocks:
        return CheckResult(path=path, status="FAIL", issues=["missing metadata block"])

    last_non_empty = len(lines) - 1
    while last_non_empty >= 0 and not lines[last_non_empty].strip():
        last_non_empty -= 1

    tail_block: tuple[int, int, dict[str, str]] | None = None
    if last_non_empty >= 0 and lines[last_non_empty].strip() == "---":
        for block in metadata_blocks:
            if block[1] == last_non_empty:
                tail_block = block
                break

    if tail_block is None:
        return CheckResult(path=path, status="FAIL", issues=["metadata block exists but is not at document tail"])

    _, _, fields = tail_block
    missing_fields = [field for field in REQUIRED_FIELDS if field not in fields]
    if missing_fields:
        return CheckResult(
            path=path,
            status="FAIL",
            issues=[f"tail metadata block missing required fields: {', '.join(missing_fields)}"],
        )

    return CheckResult(path=path, status="PASS")


def print_summary(results: list[CheckResult]) -> None:
    pass_count = sum(result.status == "PASS" for result in results)
    warn_count = sum(result.status == "WARN" for result in results)
    fail_count = sum(result.status == "FAIL" for result in results)

    print(f"[summary] PASS={pass_count} WARN={warn_count} FAIL={fail_count}")
    for result in results:
        if result.status == "PASS":
            continue
        print(f"[{result.status}] {result.path}")
        for issue in result.issues:
            print(f"  - {issue}")


def main() -> int:
    if not ACTIVE_DOCS_PATH.exists():
        print(f"[FAIL] ACTIVE_DOCS.md not found: {ACTIVE_DOCS_PATH}")
        return 1

    targets_by_section = load_active_doc_targets(ACTIVE_DOCS_PATH)
    results: list[CheckResult] = []
    for section_name in ("active_runtime_docs", "active_reference_docs"):
        section_targets = targets_by_section.get(section_name, [])
        print(f"[scan] {section_name}: {len(section_targets)} entries")
        for target in section_targets:
            result = check_markdown_metadata(target)
            results.append(result)
            detail = f" ({'; '.join(result.issues)})" if result.issues else ""
            print(f"[{result.status}] {target}{detail}")

    print_summary(results)
    if any(result.status == "FAIL" for result in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
