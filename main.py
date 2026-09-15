"""main.py — Single-command entry point for the Bookable Payable system.

Usage:
    python main.py --input documents/ --output output/
    python main.py process --input documents/ --output output/
    python main.py evaluate --output output/
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer(
    name="bookable-payable",
    help="Bookable Payable Reconstruction System — PDF to ERP-bookable autodraft records.",
    add_completion=False,
)


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structured logging."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


@app.command()
def process(
    input_dir: Path = typer.Option(
        Path("candidate_kit/candidate_kit/documents"),
        "--input", "-i",
        help="Directory containing PDF documents to process.",
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output", "-o",
        help="Directory to write output JSON files.",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level", "-l",
        help="Logging level (DEBUG, INFO, WARNING, ERROR).",
    ),
) -> None:
    """Process all PDFs in the input directory and produce autodraft JSON outputs."""
    setup_logging(log_level)
    logger = logging.getLogger("main")

    if not input_dir.exists():
        logger.error("Input directory does not exist: %s", input_dir)
        raise typer.Exit(code=1)

    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        logger.error("No PDF files found in %s", input_dir)
        raise typer.Exit(code=1)

    logger.info("Found %d PDF files in %s", len(pdf_files), input_dir)
    logger.info("Output directory: %s", output_dir)

    # Import pipeline here to avoid circular imports at module level
    from src.pipeline import run_pipeline

    results = run_pipeline(pdf_files, output_dir)

    # Summary
    total = len(results)
    accepted = sum(1 for r in results if r.payables)
    declined = sum(1 for r in results if not r.payables)
    logger.info(
        "Processing complete: %d files, %d with payables, %d declined/empty",
        total, accepted, declined
    )


@app.command()
def evaluate(
    output_dir: Path = typer.Option(
        Path("output"),
        "--output", "-o",
        help="Directory containing output JSON files to evaluate.",
    ),
) -> None:
    """Evaluate generated outputs against erp_book()."""
    setup_logging("INFO")

    from scripts.evaluate import evaluate_outputs, print_report
    import json

    stats = evaluate_outputs(output_dir)
    print_report(stats)

    summary_path = output_dir / "evaluation_summary.json"
    try:
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
        logging.getLogger("main").info("Saved evaluation summary to %s", summary_path)
    except Exception as e:
        logging.getLogger("main").warning("Could not write evaluation summary: %s", e)


@app.command()
def inspect(
    pdf_path: Path = typer.Argument(
        ...,
        help="Path to the PDF document to inspect.",
    ),
) -> None:
    """Inspect a single PDF document's evidence, classification, and master-data matching."""
    from scripts.inspect_doc import inspect_pdf
    inspect_pdf(pdf_path)


@app.command()
def recheck(
    pdf_path: Path = typer.Argument(
        ...,
        help="Path to the PDF document to re-extract and validate.",
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output", "-o",
        help="Directory to write output JSON.",
    ),
) -> None:
    """Run full pipeline and targeted recheck on a single PDF document."""
    setup_logging("INFO")
    logger = logging.getLogger("main")

    if not pdf_path.exists():
        logger.error("File does not exist: %s", pdf_path)
        raise typer.Exit(code=1)

    from src.pipeline import process_single_pdf
    from src.output.writer import write_output

    result = process_single_pdf(pdf_path)
    write_output(result, output_dir)
    logger.info("Recheck complete for %s: %d payables, %d declined", pdf_path.name, len(result.payables), len(result.declined))


if __name__ == "__main__":
    app()
