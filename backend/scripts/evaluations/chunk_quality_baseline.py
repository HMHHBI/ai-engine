"""P3-03 Chunk Quality Baseline Measurement Harness.

Executes deterministic characterization and statistical profiling against the
current production chunking configuration (EmbeddingService.chunk_text, 500/50).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.embedding_service import EmbeddingService
from app.utils.pdf_extractor import PDFPage

DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 50
DEFAULT_FIXTURES_DIR = (BACKEND_DIR / "tests" / "fixtures" / "chunk_quality") if (BACKEND_DIR / "tests" / "fixtures" / "chunk_quality").exists() else (REPO_ROOT / "tests" / "fixtures" / "chunk_quality")
DEFAULT_OUTPUT_DIR = (REPO_ROOT / "evaluation-results") if (REPO_ROOT / "evaluation-results").parent.exists() else Path("/app/evaluation-results")


@dataclass(frozen=True)
class FixtureChunkMetrics:
    """Summary metrics for chunks produced from a single fixture."""

    fixture_name: str
    total_characters_in: int
    chunks_generated: int
    min_chars: int
    p25_chars: float
    median_chars: float
    p75_chars: float
    p95_chars: float
    max_chars: float
    chunks_under_100: int
    chunks_under_200: int
    chunks_over_500: int
    chunks_over_600: int
    chunk_index_monotonic: bool
    empty_chunks_count: int


def calculate_percentile(values: Sequence[int], percentile: float) -> float:
    """Calculate the given percentile (0.0 to 100.0) from a sequence."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return float(d0 + d1)


def parse_fixture_pages(file_path: Path) -> list[PDFPage]:
    """Parse fixture file into PDFPage objects. Supports '--- PAGE X ---' delimiter."""
    raw_text = file_path.read_text(encoding="utf-8")
    if "--- PAGE " in raw_text:
        pages: list[PDFPage] = []
        raw_pages = raw_text.split("--- PAGE ")
        for block in raw_pages:
            block = block.strip()
            if not block:
                continue
            lines = block.splitlines()
            header = lines[0].split("---")[0].strip()
            page_num = int(header) if header.isdigit() else len(pages) + 1
            body = "\n".join(lines[1:]).strip()
            pages.append(PDFPage(page_number=page_num, text=body))
        return pages

    return [PDFPage(page_number=1, text=raw_text)]


def evaluate_fixture(
    fixture_path: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> tuple[FixtureChunkMetrics, list[dict[str, Any]]]:
    """Execute chunk_text against a fixture and compute characterization metrics."""
    pages = parse_fixture_pages(fixture_path)
    total_chars_in = sum(len(p.text) for p in pages)

    chunks = EmbeddingService.chunk_text(
        pages=pages,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    chunk_lengths = [len(c.text) for c in chunks]
    chunk_indices = [c.chunk_index for c in chunks]

    is_monotonic = True
    for i, idx in enumerate(chunk_indices):
        if idx != i:
            is_monotonic = False
            break

    metrics = FixtureChunkMetrics(
        fixture_name=fixture_path.name,
        total_characters_in=total_chars_in,
        chunks_generated=len(chunks),
        min_chars=min(chunk_lengths) if chunk_lengths else 0,
        p25_chars=calculate_percentile(chunk_lengths, 25.0),
        median_chars=calculate_percentile(chunk_lengths, 50.0),
        p75_chars=calculate_percentile(chunk_lengths, 75.0),
        p95_chars=calculate_percentile(chunk_lengths, 95.0),
        max_chars=max(chunk_lengths) if chunk_lengths else 0,
        chunks_under_100=sum(1 for length in chunk_lengths if length < 100),
        chunks_under_200=sum(1 for length in chunk_lengths if length < 200),
        chunks_over_500=sum(1 for length in chunk_lengths if length > 500),
        chunks_over_600=sum(1 for length in chunk_lengths if length > 600),
        chunk_index_monotonic=is_monotonic,
        empty_chunks_count=sum(1 for length in chunk_lengths if length == 0),
    )

    chunk_dumps = [
        {
            "chunk_index": c.chunk_index,
            "page_number": c.page_number,
            "char_length": len(c.text),
            "text": c.text,
        }
        for c in chunks
    ]

    return metrics, chunk_dumps


def run_baseline_evaluation(
    fixtures_dir: Path,
    output_dir: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> dict[str, Any]:
    """Execute evaluation across all fixtures in directory and write reports."""
    fixture_files = sorted(fixtures_dir.glob("*.txt"))
    if not fixture_files:
        raise ValueError(f"No .txt fixture files found in {fixtures_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    summary_list: list[FixtureChunkMetrics] = []
    detailed_chunks: dict[str, list[dict[str, Any]]] = {}
    all_lengths: list[int] = []

    for f_path in fixture_files:
        m, dumps = evaluate_fixture(f_path, chunk_size, overlap)
        summary_list.append(m)
        detailed_chunks[f_path.name] = dumps
        all_lengths.extend(d["char_length"] for d in dumps)

    corpus_summary = {
        "configuration": {
            "chunk_size": chunk_size,
            "overlap": overlap,
        },
        "totals": {
            "fixtures_evaluated": len(fixture_files),
            "total_chunks_generated": len(all_lengths),
            "corpus_min_chars": min(all_lengths) if all_lengths else 0,
            "corpus_p25_chars": calculate_percentile(all_lengths, 25.0),
            "corpus_median_chars": calculate_percentile(all_lengths, 50.0),
            "corpus_p75_chars": calculate_percentile(all_lengths, 75.0),
            "corpus_p95_chars": calculate_percentile(all_lengths, 95.0),
            "corpus_max_chars": max(all_lengths) if all_lengths else 0,
            "total_chunks_under_100": sum(1 for length in all_lengths if length < 100),
            "total_chunks_under_200": sum(1 for length in all_lengths if length < 200),
            "total_chunks_over_500": sum(1 for length in all_lengths if length > 500),
            "total_chunks_over_600": sum(1 for length in all_lengths if length > 600),
            "total_empty_chunks": sum(1 for length in all_lengths if length == 0),
        },
        "per_fixture": [asdict(m) for m in summary_list],
    }

    json_path = output_dir / "p3_03_chunk_quality_baseline.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(corpus_summary, f, indent=2)

    md_path = output_dir / "p3_03_chunk_quality_baseline.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# P3-03 Document Chunking Baseline Report\n\n")
        f.write(f"**Configuration**: `chunk_size={chunk_size}`, `overlap={overlap}`\n\n")
        f.write("## Corpus Aggregates\n\n")
        f.write(f"- **Fixtures Evaluated**: {corpus_summary['totals']['fixtures_evaluated']}\n")
        f.write(f"- **Total Chunks**: {corpus_summary['totals']['total_chunks_generated']}\n")
        f.write(f"- **Length Min / Median / Max**: {corpus_summary['totals']['corpus_min_chars']} / {corpus_summary['totals']['corpus_median_chars']} / {corpus_summary['totals']['corpus_max_chars']} chars\n")
        f.write(f"- **Chunks < 100 Chars**: {corpus_summary['totals']['total_chunks_under_100']}\n")
        f.write(f"- **Chunks < 200 Chars**: {corpus_summary['totals']['total_chunks_under_200']}\n")
        f.write(f"- **Chunks > 500 Chars (Oversized)**: {corpus_summary['totals']['total_chunks_over_500']}\n")
        f.write(f"- **Chunks > 600 Chars**: {corpus_summary['totals']['total_chunks_over_600']}\n")
        f.write(f"- **Empty Chunks**: {corpus_summary['totals']['total_empty_chunks']}\n\n")
        f.write("## Per-Fixture Breakdown\n\n")
        f.write("| Fixture | Chars In | Chunks | Min | Median | Max | <100 | >500 | Monotonic |\n")
        f.write("|---|---|---|---|---|---|---|---|---|\n")
        for m in summary_list:
            f.write(
                f"| `{m.fixture_name}` | {m.total_characters_in} | {m.chunks_generated} | "
                f"{m.min_chars} | {m.median_chars:.1f} | {m.max_chars} | "
                f"{m.chunks_under_100} | {m.chunks_over_500} | {'Yes' if m.chunk_index_monotonic else 'No'} |\n"
            )

    print("Baseline measurement written to:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")
    return corpus_summary


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Run P3-03 chunk quality baseline.")
    parser.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    args = parser.parse_args()

    run_baseline_evaluation(
        fixtures_dir=args.fixtures_dir,
        output_dir=args.output_dir,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )


if __name__ == "__main__":
    main()
