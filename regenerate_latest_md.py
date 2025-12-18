"""Rebind and render the Markdown report using the latest chapter JSON."""

import json
import sys
from datetime import datetime
from pathlib import Path
from loguru import logger

# Make sure the module within the project can be found
sys.path.insert(0, str(Path(__file__).parent))

from ReportEngine.core import ChapterStorage, DocumentComposer
from ReportEngine.ir import IRValidator
from ReportEngine.renderers import MarkdownRenderer
from ReportEngine.utils.config import settings


def find_latest_run_dir(chapter_root: Path):
    """Locate the output directory of the latest run in the chapter root directory.

    Scan all subdirectories under `chapter_root` and filter out files containing `manifest.json`
    Candidates, select the latest one in reverse order of modification time. If the directory does not exist or is not valid
    manifest, will log errors and return None.

    Parameters:
        chapter_root: root directory of chapter output (usually settings.CHAPTER_OUTPUT_DIR)

    Return:
        Path | None: The latest run directory path; None if not found."""
    if not chapter_root.exists():
        logger.error(f"Chapter directory does not exist: {chapter_root}")
        return None

    run_dirs = []
    for candidate in chapter_root.iterdir():
        if not candidate.is_dir():
            continue
        manifest_path = candidate / "manifest.json"
        if manifest_path.exists():
            run_dirs.append((candidate, manifest_path.stat().st_mtime))

    if not run_dirs:
        logger.error("Chapter directory with manifest.json not found")
        return None

    latest_dir = sorted(run_dirs, key=lambda item: item[1], reverse=True)[0][0]
    logger.info(f"Find the latest run directory: {latest_dir.name}")
    return latest_dir


def load_manifest(run_dir: Path):
    """Read manifest.json in the directory of a single run.

    Returns reportId and metadata dictionary on success; failure to read or parse will log an error
    And return (None, None) so that the upper layer can terminate the process early.

    Parameters:
        run_dir: Chapter output directory containing manifest.json

    Return:
        tuple[str | None, dict | None]: (report_id, metadata)"""
    manifest_path = run_dir / "manifest.json"
    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)
        report_id = manifest.get("reportId") or run_dir.name
        metadata = manifest.get("metadata") or {}
        logger.info(f"Report ID: {report_id}")
        if manifest.get("createdAt"):
            logger.info(f"Creation time: {manifest['createdAt']}")
        return report_id, metadata
    except Exception as exc:
        logger.error(f"Failed to read manifest: {exc}")
        return None, None


def load_chapters(run_dir: Path):
    """Read all chapter JSON in the specified run directory.

    The load_chapters capability of ChapterStorage will be reused and sorted by order automatically.
    Print the number of chapters after reading to facilitate confirmation of completeness.

    Parameters:
        run_dir: Chapter directory of a single report

    Return:
        list[dict]: JSON list of chapters (empty list if the directory is empty)"""
    storage = ChapterStorage(settings.CHAPTER_OUTPUT_DIR)
    chapters = storage.load_chapters(run_dir)
    logger.info(f"Number of chapters loaded: {len(chapters)}")
    return chapters


def validate_chapters(chapters):
    """Use IRValidator to quickly verify the chapter structure.

    Only the failed chapters and the first three errors are recorded without interrupting the process; the purpose is to
    Identify potential structural problems before rebinding.

    Parameters:
        chapters: JSON list of chapters"""
    validator = IRValidator()
    invalid = []
    for chapter in chapters:
        ok, errors = validator.validate_chapter(chapter)
        if not ok:
            invalid.append((chapter.get("chapterId") or "unknown", errors))

    if invalid:
        logger.warning(f"There are {len(invalid)} chapters that have failed the structure check and will continue to be bound:")
        for chapter_id, errors in invalid:
            preview = "; ".join(errors[:3])
            logger.warning(f"  - {chapter_id}: {preview}")
    else:
        logger.info("Chapter structure verification passed")


def stitch_document(report_id, metadata, chapters):
    """Bind the chapters and metadata into a complete Document IR.

    Use DocumentComposer to uniformly process chapter order, global metadata, etc., and print
    The number of chapters and figures that have been bound.

    Parameters:
        report_id: report ID (from manifest or directory name)
        metadata: global metadata in manifest
        chapters: List of loaded chapters

    Return:
        dict: complete Document IR object"""
    composer = DocumentComposer()
    document_ir = composer.build_document(report_id, metadata, chapters)
    logger.info(
        f"Binding completed: {len(document_ir.get('chapters', []))} chapters,"
        f"{count_charts(document_ir)} charts"
    )
    return document_ir


def count_charts(document_ir):
    """Count the number of Chart.js charts in the entire Document IR.

    It will traverse the blocks of each chapter and recursively search for widget types starting with `chart.js`
    The components at the beginning make it easy to quickly perceive the scale of the chart.

    Parameters:
        document_ir: complete Document IR

    Return:
        int: total number of charts"""
    chart_count = 0
    for chapter in document_ir.get("chapters", []):
        blocks = chapter.get("blocks", [])
        chart_count += _count_chart_blocks(blocks)
    return chart_count


def _count_chart_blocks(blocks):
    """Recursively count the number of Chart.js components in the block list.

    Compatible with nested blocks/list/table structures, ensuring all levels of charts are accounted for.

    Parameters:
        blocks: block list at any level

    Return:
        int: number of chart.js charts counted"""
    count = 0
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "widget" and str(block.get("widgetType", "")).startswith("chart.js"):
            count += 1
        nested = block.get("blocks")
        if isinstance(nested, list):
            count += _count_chart_blocks(nested)
        if block.get("type") == "list":
            for item in block.get("items", []):
                if isinstance(item, list):
                    count += _count_chart_blocks(item)
        if block.get("type") == "table":
            for row in block.get("rows", []):
                for cell in row.get("cells", []):
                    if isinstance(cell, dict):
                        cell_blocks = cell.get("blocks", [])
                        if isinstance(cell_blocks, list):
                            count += _count_chart_blocks(cell_blocks)
    return count


def save_document_ir(document_ir, base_name, timestamp):
    """Place the entire rebound Document IR on disk.

    Name and write as `report_ir_{slug}_{timestamp}_regen.json`
    `settings.DOCUMENT_IR_OUTPUT_DIR`, ensures the directory exists and returns the save path.

    Parameters:
        document_ir: The entire bound IR
        base_name: safe filename fragment generated from theme/title
        timestamp: timestamp string, used to distinguish multiple regenerations

    Return:
        Path: Saved IR file path"""
    output_dir = Path(settings.DOCUMENT_IR_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    ir_filename = f"report_ir_{base_name}_{timestamp}_regen.json"
    ir_path = output_dir / ir_filename
    ir_path.write_text(json.dumps(document_ir, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"IR saved: {ir_path}")
    return ir_path


def render_markdown(document_ir, base_name, timestamp, ir_path=None):
    """Use MarkdownRenderer to render the Document IR to Markdown and save it.

    After rendering, drop it to `final_reports/md` and print the generated file size for easy confirmation.
    Output content.

    Parameters:
        document_ir: The entire bound IR
        base_name: filename fragment (derived from report subject/title)
        timestamp: timestamp string
        ir_path: optional, IR file path, it will be automatically saved after repair when provided.

    Return:
        Path: generated Markdown file path"""
    renderer = MarkdownRenderer()
    # Pass in ir_file_path and save automatically after repair
    markdown_content = renderer.render(document_ir, ir_file_path=str(ir_path) if ir_path else None)

    output_dir = Path(settings.OUTPUT_DIR) / "md"
    output_dir.mkdir(parents=True, exist_ok=True)
    md_filename = f"report_md_{base_name}_{timestamp}.md"
    md_path = output_dir / md_filename
    md_path.write_text(markdown_content, encoding="utf-8")

    file_size_kb = md_path.stat().st_size / 1024
    logger.info(f"Markdown generated successfully: {md_path} ({file_size_kb:.1f} KB)")
    return md_path


def build_slug(text):
    """Convert the subject/title into a file system safe snippet.

    Only letters/numbers/spaces/underscores/hyphens are retained. Spaces are unified into underscores and restricted
    Maximum 60 characters to avoid overly long filenames.

    Parameters:
        text: original topic or title

    Return:
        str: Cleaned safe string"""
    text = str(text or "report")
    sanitized = "".join(c for c in text if c.isalnum() or c in (" ", "-", "_")).strip()
    sanitized = sanitized.replace(" ", "_")
    return sanitized[:60] or "report"


def main():
    """Main entry: reads the latest chapter, binds IR and renders Markdown.

    Process:
        1) Find the latest chapter run directory and read the manifest;
        2) Load the chapter and perform structure verification (warning only);
        3) Bind the entire IR and save a copy of the IR;
        4) Render Markdown and output the path.

    Return:
        int: 0 indicates success, the rest indicates failure."""
    logger.info("🚀 Rebind and render Markdown using the latest LLM chapters")

    chapter_root = Path(settings.CHAPTER_OUTPUT_DIR)
    latest_run = find_latest_run_dir(chapter_root)
    if not latest_run:
        return 1

    report_id, metadata = load_manifest(latest_run)
    if not report_id or metadata is None:
        return 1

    chapters = load_chapters(latest_run)
    if not chapters:
        logger.error("Chapter JSON not found, cannot be bound")
        return 1

    validate_chapters(chapters)

    document_ir = stitch_document(report_id, metadata, chapters)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = build_slug(
        metadata.get("query") or metadata.get("title") or metadata.get("reportId") or report_id
    )

    ir_path = save_document_ir(document_ir, base_name, timestamp)
    # Pass in ir_path and the repaired chart will be automatically saved to the IR file
    md_path = render_markdown(document_ir, base_name, timestamp, ir_path=ir_path)

    logger.info("")
    logger.info("🎉 Markdown binding and rendering completed")
    logger.info(f"IR file: {ir_path.resolve()}")
    logger.info(f"Markdown file: {md_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
