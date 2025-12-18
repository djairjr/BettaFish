#!/usr/bin/env python3
"""PDF export tool - use Python to directly generate PDF, no garbled characters

Usage:
    python ReportEngine/scripts/export_to_pdf.py <Report IR JSON file> [Output PDF path]

Example:
    python ReportEngine/scripts/export_to_pdf.py final_reports/ir/report_ir_xxx.json output.pdf
    python ReportEngine/scripts/export_to_pdf.py final_reports/ir/report_ir_xxx.json"""

import sys
import json
from pathlib import Path
from loguru import logger

from ReportEngine.renderers import PDFRenderer


def export_to_pdf(ir_json_path: str, output_pdf_path: str = None):
    """Generate PDF from IR JSON file

    Parameters:
        ir_json_path: Document IR JSON file path
        output_pdf_path: output PDF path (optional, defaults to .pdf with the same name)"""
    ir_path = Path(ir_json_path)

    if not ir_path.exists():
        logger.error(f"File does not exist: {ir_path}")
        return False

    # Read IR data
    logger.info(f"Read report: {ir_path}")
    with open(ir_path, 'r', encoding='utf-8') as f:
        document_ir = json.load(f)

    # Determine output path
    if output_pdf_path is None:
        output_pdf_path = ir_path.parent / f"{ir_path.stem}.pdf"
    else:
        output_pdf_path = Path(output_pdf_path)

    # Generate PDF
    logger.info(f"Start generating PDF...")
    renderer = PDFRenderer()

    try:
        renderer.render_to_pdf(document_ir, output_pdf_path)
        logger.success(f"✓ PDF generated: {output_pdf_path}")
        return True
    except Exception as e:
        logger.error(f"✗ PDF generation failed: {e}")
        logger.exception("Detailed error message:")
        return False


def main():
    """main function"""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    ir_json_path = sys.argv[1]
    output_pdf_path = sys.argv[2] if len(sys.argv) > 2 else None

    # Check environment variables
    import os
    if 'DYLD_LIBRARY_PATH' not in os.environ:
        logger.warning("DYLD_LIBRARY_PATH is not set, trying to set it automatically...")
        os.environ['DYLD_LIBRARY_PATH'] = '/opt/homebrew/lib'

    success = export_to_pdf(ir_json_path, output_pdf_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
