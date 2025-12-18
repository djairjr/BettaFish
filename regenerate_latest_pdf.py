"""Regenerate PDF of latest reports using new SVG vector charting feature"""

import json
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger

# Add project path
sys.path.insert(0, str(Path(__file__).parent))

from ReportEngine.renderers import PDFRenderer

def find_latest_report():
    """Find the latest report IR JSON in `final_reports/ir`.

    Select the first item in reverse order of modification time. If the directory or file is missing, an error will be recorded and None will be returned.

    Return:
        Path | None: Path to the latest IR file; None if not found."""
    ir_dir = Path("final_reports/ir")

    if not ir_dir.exists():
        logger.error(f"Report directory does not exist: {ir_dir}")
        return None

    # Get all JSON files and sort by modification time
    json_files = sorted(ir_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not json_files:
        logger.error("Report file not found")
        return None

    latest_file = json_files[0]
    logger.info(f"Find the latest report: {latest_file.name}")

    return latest_file

def load_document_ir(file_path):
    """Read the Document IR JSON of the specified path and count the number of chapters/charts.

    Returns None when parsing fails; when successful, the number of chapters and figures will be printed for easy confirmation.
    Enter the size of the report.

    Parameters:
        file_path: IR file path

    Return:
        dict | None: Parsed Document IR; returns None on failure."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            document_ir = json.load(f)

        logger.info(f"Successfully loaded report: {file_path.name}")

        # Number of statistical charts
        chart_count = 0
        chapters = document_ir.get('chapters', [])

        def count_charts(blocks):
            """Recursively count the number of Chart.js charts in the block list"""
            count = 0
            for block in blocks:
                if isinstance(block, dict):
                    if block.get('type') == 'widget' and block.get('widgetType', '').startswith('chart.js'):
                        count += 1
                    # Processing nested blocks recursively
                    nested = block.get('blocks')
                    if isinstance(nested, list):
                        count += count_charts(nested)
            return count

        for chapter in chapters:
            blocks = chapter.get('blocks', [])
            chart_count += count_charts(blocks)

        logger.info(f"The report contains {len(chapters)} chapters and {chart_count} charts")

        return document_ir

    except Exception as e:
        logger.error(f"Failed to load report: {e}")
        return None

def generate_pdf_with_vector_charts(document_ir, output_path, ir_file_path=None):
    """Use PDFRenderer to render Document IR to PDF containing SVG vector graphics.

    Enable layout optimization, output file size and success prompt after generation; return None in case of exception.

    Parameters:
        document_ir: complete Document IR
        output_path: target PDF path
        ir_file_path: optional, IR file path, it will be automatically saved after repair when provided.

    Return:
        Path | None: Returns the generated PDF path on success, None on failure."""
    try:
        logger.info("=" * 60)
        logger.info("Start generating PDF (with vector graphics)")
        logger.info("=" * 60)

        # Create PDF renderer
        renderer = PDFRenderer()

        # Render PDF, passing in ir_file_path for saving after repair
        result_path = renderer.render_to_pdf(
            document_ir,
            output_path,
            optimize_layout=True,
            ir_file_path=str(ir_file_path) if ir_file_path else None
        )

        logger.info("=" * 60)
        logger.info(f"✓ PDF generated successfully: {result_path}")
        logger.info("=" * 60)

        # Show file size
        file_size = result_path.stat().st_size
        size_mb = file_size / (1024 * 1024)
        logger.info(f"File size: {size_mb:.2f} MB")

        return result_path

    except Exception as e:
        logger.error(f"Failed to generate PDF: {e}", exc_info=True)
        return None

def main():
    """Main portal: Regenerate vector PDFs of latest reports.

    Steps:
        1) Find the latest IR file;
        2) Read and count the report structure;
        3) Construct the output file name and ensure that the directory exists;
        4) Call the rendering function to generate PDF, output path and feature description.

    Return:
        int: 0 indicates success, non-0 indicates failure."""
    logger.info("🚀 Regenerate PDF of latest reports using SVG vector charts")
    logger.info("")

    # 1. Find the latest reports
    latest_report = find_latest_report()
    if not latest_report:
        logger.error("Report file not found")
        return 1

    # 2. Load report data
    document_ir = load_document_ir(latest_report)
    if not document_ir:
        logger.error("Failed to load report")
        return 1

    # 3. Generate output file name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = latest_report.stem.replace("report_ir_", "")
    output_filename = f"report_vector_{report_name}_{timestamp}.pdf"
    output_path = Path("final_reports/pdf") / output_filename

    # Make sure the output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Output path: {output_path}")
    logger.info("")

    # 4. Generate PDF and pass in the IR file path for saving after repair.
    result = generate_pdf_with_vector_charts(document_ir, output_path, ir_file_path=latest_report)

    if result:
        logger.info("")
        logger.info("🎉 PDF generation completed!")
        logger.info("")
        logger.info("Feature description:")
        logger.info("✓ Charts are rendered in SVG vector format")
        logger.info("✓ Supports unlimited scaling without distortion")
        logger.info("✓ Preserve the complete visual effect of the chart")
        logger.info("✓ Line charts, bar charts, pie charts, etc. are all vector curves")
        logger.info("")
        logger.info(f"PDF file location: {result.absolute()}")
        return 0
    else:
        logger.error("❌ PDF generation failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
