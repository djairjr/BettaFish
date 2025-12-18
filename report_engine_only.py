#!/usr/bin/env python
"""Report Engine command line version

This is a command-line report generation program that requires no front-end.
Main process:
1. Check PDF dependencies
2. Get the latest log and md files
3. Directly call Report Engine to generate reports (skip files and increase auditing)
4. Automatically save HTML, PDF (if dependent) and Markdown to final_reports/ (Markdown will be generated after PDF)

How to use:
    python report_engine_only.py [options]

Options:
    --query QUERY specifies the report subject (optional, extracted from file name by default)
    --skip-pdf Skip PDF generation (even if there are dependencies)
    --skip-markdown skip Markdown generation
    --verbose show detailed logs
    --help Display help information"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from loguru import logger

# Global configuration
VERBOSE = False

# Configuration log
def setup_logger(verbose: bool = False):
    """Set log configuration"""
    global VERBOSE
    VERBOSE = verbose

    logger.remove()  # Remove default processor
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="DEBUG" if verbose else "INFO"
    )


def check_dependencies() -> tuple[bool, Optional[str]]:
    """Check system dependencies required for PDF generation

    Returns:
        tuple: (is_available: bool, message: str)
            - is_available: whether the PDF function is available
            - message: dependency check result message"""
    logger.info("=" * 70)
    logger.info("Step 1/4: Check system dependencies")
    logger.info("=" * 70)

    try:
        from ReportEngine.utils.dependency_check import check_pango_available
        is_available, message = check_pango_available()

        if is_available:
            logger.success("✓ PDF dependency detection passes, and HTML and PDF files will be generated at the same time")
        else:
            logger.warning("⚠ PDF dependency is missing, only HTML files are generated")
            logger.info("\n" + message)

        return is_available, message
    except Exception as e:
        logger.error(f"Dependency check failed: {e}")
        return False, str(e)


def get_latest_engine_reports() -> Dict[str, str]:
    """Get the latest report files in the three engine directories

    Returns:
        Dict[str, str]: mapping of engine names to file paths"""
    logger.info("\n" + "=" * 70)
    logger.info("Step 2/4: Get the latest analytics engine report")
    logger.info("=" * 70)

    # Directories that define three engines
    directories = {
        'insight': 'insight_engine_streamlit_reports',
        'media': 'media_engine_streamlit_reports',
        'query': 'query_engine_streamlit_reports'
    }

    latest_files = {}

    for engine, directory in directories.items():
        if not os.path.exists(directory):
            logger.warning(f"⚠ {engine.capitalize()} Engine directory does not exist: {directory}")
            continue

        # Get all .md files
        md_files = [f for f in os.listdir(directory) if f.endswith('.md')]

        if not md_files:
            logger.warning(f"⚠ {engine.capitalize()} No .md file found in Engine directory")
            continue

        # Get the latest files
        latest_file = max(
            md_files,
            key=lambda x: os.path.getmtime(os.path.join(directory, x))
        )
        latest_path = os.path.join(directory, latest_file)
        latest_files[engine] = latest_path

        logger.info(f"✓ Find {engine.capitalize()} Engine latest report")

    if not latest_files:
        logger.error("❌ No engine report file was found, please run the analysis engine to generate a report first")
        sys.exit(1)

    logger.info(f"\nThe latest reports found for {len(latest_files)} engines")

    return latest_files


def confirm_file_selection(latest_files: Dict[str, str]) -> bool:
    """Confirm to the user whether the selected file is correct

    Args:
        latest_files: mapping of engine names to file paths

    Returns:
        bool: Returns True if the user confirms, otherwise returns False"""
    logger.info("\n" + "=" * 70)
    logger.info("Please confirm the following selected files:")
    logger.info("=" * 70)

    for engine, file_path in latest_files.items():
        filename = os.path.basename(file_path)
        # Get file modification time
        mtime = os.path.getmtime(file_path)
        mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

        logger.info(f"  {engine.capitalize()} Engine:")
        logger.info(f"File name: {filename}")
        logger.info(f"Path: {file_path}")
        logger.info(f"Modification time: {mtime_str}")
        logger.info("")

    logger.info("=" * 70)

    # Prompt user for confirmation
    try:
        response = input("Do you want to use the above file to generate a report? [Y/n]:").strip().lower()

        # The default is y, so empty input or y indicates confirmation.
        if response == '' or response == 'y' or response == 'yes':
            logger.success("✓ User confirmation to continue generating reports")
            return True
        else:
            logger.warning("✗ User cancels operation")
            return False
    except (KeyboardInterrupt, EOFError):
        logger.warning("\n✗ User cancels operation")
        return False


def load_engine_reports(latest_files: Dict[str, str]) -> list[str]:
    """Load engine report content

    Args:
        latest_files: mapping of engine names to file paths

    Returns:
        list[str]: report content list"""
    reports = []

    for engine, file_path in latest_files.items():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                reports.append(content)
                logger.debug(f"{engine} report loaded, length: {len(content)} characters")
        except Exception as e:
            logger.error(f"Failed to load {engine} report: {e}")

    return reports


def extract_query_from_reports(latest_files: Dict[str, str]) -> str:
    """Extract query subject from report file name

    Args:
        latest_files: mapping of engine names to file paths

    Returns:
        str: extracted query subject"""
    # Try to extract the theme from the filename
    for engine, file_path in latest_files.items():
        filename = os.path.basename(file_path)
        # Assume that the file name format is: report_topic_timestamp.md
        if '_' in filename:
            parts = filename.replace('.md', '').split('_')
            if len(parts) >= 2:
                # Extract the middle part as the topic
                topic = '_'.join(parts[1:-1]) if len(parts) > 2 else parts[1]
                if topic:
                    return topic

    # If it cannot be extracted, return the default value
    return "Comprehensive analysis report"


def generate_report(reports: list[str], query: str, pdf_available: bool) -> Dict[str, Any]:
    """Call Report Engine to generate reports

    Args:
        reports: list of report contents
        query: report subject
        pdf_available: Whether the PDF function is available

    Returns:
        Dict[str, Any]: Dictionary containing generated results"""
    logger.info("\n" + "=" * 70)
    logger.info("Step 3/4: Generate Comprehensive Report")
    logger.info("=" * 70)
    logger.info(f"Report subject: {query}")
    logger.info(f"Enter the number of reports: {len(reports)}")

    try:
        from ReportEngine.agent import ReportAgent

        # Initialize Report Agent
        logger.info("Initializing Report Engine...")
        agent = ReportAgent()

        # Define streaming event handler
        def stream_handler(event_type: str, payload: Dict[str, Any]):
            """Handling Report Engine streaming events"""
            if event_type == 'stage':
                stage = payload.get('stage', '')
                if stage == 'agent_start':
                    logger.info(f"Start generating reports: {payload.get('report_id', '')}")
                elif stage == 'template_selected':
                    logger.info(f"✓ Template selected: {payload.get('template', '')}")
                elif stage == 'template_sliced':
                    logger.info(f"✓ Template parsing completed, total {payload.get('section_count', 0)} chapters")
                elif stage == 'layout_designed':
                    logger.info(f"✓ Document layout design completed")
                    logger.info(f"Title: {payload.get('title', '')}")
                elif stage == 'word_plan_ready':
                    logger.info(f"✓ The length planning is completed, the target number of chapters: {payload.get('chapter_targets', 0)}")
                elif stage == 'chapters_compiled':
                    logger.info(f"✓ Chapter generation completed, a total of {payload.get('chapter_count', 0)} chapters")
                elif stage == 'html_rendered':
                    logger.info(f"✓ HTML rendering completed")
                elif stage == 'report_saved':
                    logger.info(f"✓ Report saved")
            elif event_type == 'chapter_status':
                chapter_id = payload.get('chapterId', '')
                title = payload.get('title', '')
                status = payload.get('status', '')
                if status == 'generating':
                    logger.info(f"Generating chapter: {title}")
                elif status == 'completed':
                    attempt = payload.get('attempt', 1)
                    warning = payload.get('warning', '')
                    if warning:
                        logger.warning(f"✓ Chapter completed: {title} ({attempt}th attempt, {payload.get('warningMessage', '')})")
                    else:
                        logger.success(f"✓ Chapter completed: {title}")
            elif event_type == 'error':
                logger.error(f"Error: {payload.get('message', '')}")

        # Generate report
        logger.info("Report generation begins, this may take a few minutes...")
        result = agent.generate_report(
            query=query,
            reports=reports,
            forum_logs="",  # Do not use forum logs
            custom_template="",  # Use automatic template selection
            save_report=True,  # Automatically save reports
            stream_handler=stream_handler
        )

        logger.success("✓ Report generated successfully!")
        return result

    except Exception as e:
        logger.exception(f"❌ Report generation failed: {e}")
        sys.exit(1)


def save_pdf(document_ir_path: str, query: str) -> Optional[str]:
    """Generate and save PDF from IR files

    Args:
        document_ir_path: Document IR file path
        query: report subject

    Returns:
        Optional[str]: PDF file path, returns None if failed"""
    logger.info("\nGenerating PDF file...")

    try:
        # Read IR data
        with open(document_ir_path, 'r', encoding='utf-8') as f:
            document_ir = json.load(f)

        # Create PDF renderer
        from ReportEngine.renderers import PDFRenderer
        renderer = PDFRenderer()

        # Prepare output path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_safe = "".join(
            c for c in query if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        query_safe = query_safe.replace(" ", "_")[:30] or "report"

        pdf_dir = Path("final_reports") / "pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)

        pdf_filename = f"final_report_{query_safe}_{timestamp}.pdf"
        pdf_path = pdf_dir / pdf_filename

        # Use the render_to_pdf method to directly generate PDF files, and pass in the IR file path for saving after repair.
        logger.info(f"Start rendering PDF: {pdf_path}")
        result_path = renderer.render_to_pdf(
            document_ir,
            pdf_path,
            optimize_layout=True,
            ir_file_path=document_ir_path
        )

        # Show file size
        file_size = result_path.stat().st_size
        size_mb = file_size / (1024 * 1024)
        logger.success(f"✓ PDF saved: {pdf_path}")
        logger.info(f"File size: {size_mb:.2f} MB")

        return str(result_path)

    except Exception as e:
        logger.exception(f"❌ PDF generation failed: {e}")
        return None


def save_markdown(document_ir_path: str, query: str) -> Optional[str]:
    """Generate and save Markdown from IR file

    Args:
        document_ir_path: Document IR file path
        query: report subject

    Returns:
        Optional[str]: Markdown file path, returns None if failed"""
    logger.info("\nGenerating Markdown file...")

    try:
        with open(document_ir_path, 'r', encoding='utf-8') as f:
            document_ir = json.load(f)

        from ReportEngine.renderers import MarkdownRenderer
        renderer = MarkdownRenderer()
        # Pass in the IR file path for saving after repair
        markdown_content = renderer.render(document_ir, ir_file_path=document_ir_path)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_safe = "".join(
            c for c in query if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        query_safe = query_safe.replace(" ", "_")[:30] or "report"

        md_dir = Path("final_reports") / "md"
        md_dir.mkdir(parents=True, exist_ok=True)

        md_filename = f"final_report_{query_safe}_{timestamp}.md"
        md_path = md_dir / md_filename

        md_path.write_text(markdown_content, encoding='utf-8')

        file_size_kb = md_path.stat().st_size / 1024
        logger.success(f"✓ Markdown saved: {md_path}")
        logger.info(f"File size: {file_size_kb:.1f} KB")

        return str(md_path)

    except Exception as e:
        logger.exception(f"❌ Markdown generation failed: {e}")
        return None


def parse_arguments():
    """Parse command line parameters"""
    parser = argparse.ArgumentParser(
        description="Report Engine command line version - a front-end-free report generation tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:
  python report_engine_only.py
  python report_engine_only.py --query"土木工程行业分析"python report_engine_only.py --skip-pdf --verbose

Note:
  The program will automatically obtain the latest report files in the three engine directories.
  Without adding files for review, a comprehensive report is generated directly, and Markdown is generated after the PDF by default."""
    )

    parser.add_argument(
        '--query',
        type=str,
        default=None,
        help='指定报告主题（默认从文件名自动提取）'
    )

    parser.add_argument(
        '--skip-pdf',
        action='store_true',
        help='跳过PDF生成（即使系统支持）'
    )

    parser.add_argument(
        '--skip-markdown',
        action='store_true',
        help='跳过Markdown生成'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='显示详细日志信息'
    )

    return parser.parse_args()


def main():
    """main function"""
    # Parse command line parameters
    args = parse_arguments()

    # Setup log
    setup_logger(verbose=args.verbose)

    logger.info("\n")
    logger.info("╔" + "═" * 68 + "╗")
    logger.info("║" + " " * 20 + "Report Engine command line version" + " " * 24 + "║")
    logger.info("╚" + "═" * 68 + "╝")
    logger.info("\n")

    # Step 1: Check dependencies
    pdf_available, _ = check_dependencies()
    markdown_enabled = not args.skip_markdown

    # Disable PDF generation if user specifies to skip PDF
    if args.skip_pdf:
        logger.info("If the user specifies --skip-pdf, PDF generation will be skipped")
        pdf_available = False

    if not markdown_enabled:
        logger.info("If the user specifies --skip-markdown, Markdown generation will be skipped.")

    # Step 2: Get the latest files
    latest_files = get_latest_engine_reports()

    # Confirm file selection
    if not confirm_file_selection(latest_files):
        logger.info("\nProgram has exited")
        sys.exit(0)

    # Load report content
    reports = load_engine_reports(latest_files)

    if not reports:
        logger.error("❌ Failed to load any report content")
        sys.exit(1)

    # Extract or use the specified query subject
    query = args.query if args.query else extract_query_from_reports(latest_files)
    logger.info(f"Use report subject: {query}")

    # Step 3: Generate report
    result = generate_report(reports, query, pdf_available)

    # Step 4: Save the file
    logger.info("\n" + "=" * 70)
    logger.info("Step 4/4: Save the generated file")
    logger.info("=" * 70)

    # HTML has been automatically saved in generate_report
    html_path = result.get('report_filepath', '')
    ir_path = result.get('ir_filepath', '')
    pdf_path = None
    markdown_path = None

    if html_path:
        logger.success(f"✓ HTML saved: {result.get('report_relative_path', html_path)}")

    # If there is a PDF dependency, generate and save the PDF
    if pdf_available:
        if ir_path and os.path.exists(ir_path):
            pdf_path = save_pdf(ir_path, query)
        else:
            logger.warning("⚠ IR file not found, unable to generate PDF")
    else:
        logger.info("⚠ Skip PDF generation (missing system dependency or user specified skip)")

    # Generate and save Markdown (after PDF)
    if markdown_enabled:
        if ir_path and os.path.exists(ir_path):
            markdown_path = save_markdown(ir_path, query)
        else:
            logger.warning("⚠ IR file not found, unable to generate Markdown")
    else:
        logger.info("⚠ Skip Markdown generation (user specified)")

    # Summarize
    logger.info("\n" + "=" * 70)
    logger.success("✓ Report generation completed!")
    logger.info("=" * 70)
    logger.info(f"Report ID: {result.get('report_id', 'N/A')}")
    logger.info(f"HTML file: {result.get('report_relative_path', 'N/A')}")
    if pdf_available:
        if pdf_path:
            logger.info(f"PDF file: {os.path.relpath(pdf_path, os.getcwd())}")
        else:
            logger.info("PDF file: Generation failed, please check the logs")
    else:
        logger.info("PDF file: skipped")
    if markdown_enabled:
        if markdown_path:
            logger.info(f"Markdown file: {os.path.relpath(markdown_path, os.getcwd())}")
        else:
            logger.info("Markdown file: Generation failed, please check the logs")
    else:
        logger.info("Markdown file: skipped")
    logger.info("=" * 70)
    logger.info("\nEnd of program")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n\nUser interrupt program")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"\nThe program exited abnormally: {e}")
        sys.exit(1)
