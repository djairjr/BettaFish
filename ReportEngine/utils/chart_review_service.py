"""Chart Review Services - Unified management of chart verification and repair.

Provide a singleton service to ensure that all renderers share repair status and avoid repeated repairs.
After successful repair, it can be automatically persisted to the IR file.

Thread safety instructions:
- Validator and fixer instances are stateless and safe to share
- Each review_document call will create an independent ReviewSession
-Statistics information is returned through ReviewSession to avoid concurrency contention"""

from __future__ import annotations

import copy
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from ReportEngine.utils.chart_validator import (
    ChartValidator,
    ChartRepairer,
    ValidationResult,
    create_chart_validator,
    create_chart_repairer
)
from ReportEngine.utils.chart_repair_api import create_llm_repair_functions


@dataclass
class ReviewStats:
    """Chart Review Statistics - Independent statistics for each review session.

    By creating a separate ReviewStats instance for each review_document call,
    Avoid statistical data competition problems when multi-thread concurrency occurs."""
    total: int = 0
    valid: int = 0
    repaired_locally: int = 0
    repaired_api: int = 0
    failed: int = 0

    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary format"""
        return {
            'total': self.total,
            'valid': self.valid,
            'repaired_locally': self.repaired_locally,
            'repaired_api': self.repaired_api,
            'failed': self.failed
        }

    @property
    def repaired_total(self) -> int:
        """Total number of fixes"""
        return self.repaired_locally + self.repaired_api


class ChartReviewService:
    """Chart review service - singleton pattern.

    Responsibilities:
    1. Unified management of chart verification and repair
    2. Maintain and repair cache to avoid repeated repairs
    3. Support automatic persistence to IR file after repair
    4. Provide statistical information (returned through ReviewStats, thread-safe)

    Thread safety instructions:
    - validator and repairer are stateless and safe to share
    - Create independent ReviewStats for each review_document call
    - No longer use global _stats to avoid concurrency contention"""

    _instance: Optional["ChartReviewService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ChartReviewService":
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the service (only executed when called for the first time)"""
        if self._initialized:
            return

        self._initialized = True

        # Initialize validators and fixers (stateless, safe to share)
        self.validator = create_chart_validator()
        self.llm_repair_fns = create_llm_repair_functions()
        self.repairer = create_chart_repairer(
            validator=self.validator,
            llm_repair_fns=self.llm_repair_fns
        )

        # Print LLM repair function status
        if not self.llm_repair_fns:
            logger.warning("ChartReviewService: No LLM API is configured, chart API repair functionality is not available")
        else:
            logger.info(f"ChartReviewService: {len(self.llm_repair_fns)} LLM repair functions configured")

        # Last reviewed statistics (for backward compatibility only, not recommended for use in concurrent scenarios)
        # New code should use the ReviewStats returned by review_document
        self._last_stats: Optional[ReviewStats] = None
        self._last_stats_lock = threading.Lock()

        logger.info("ChartReviewService initialization completed")

    def reset_stats(self) -> None:
        """Reset statistics (backward compatibility, deprecated).

        NOTE: This method is for backward compatibility only. In a concurrent scenario,
        The ReviewStats object returned by review_document should be used."""
        with self._last_stats_lock:
            self._last_stats = None

    @property
    def stats(self) -> Dict[str, int]:
        """Get a copy of the statistics for the last review (backward compatibility).

        Warning: In concurrent scenarios, this property may return statistics from other threads.
        It is recommended to use the ReviewStats object returned by review_document.

        Return:
            Dict[str, int]: copy of statistics dictionary"""
        with self._last_stats_lock:
            if self._last_stats is None:
                return {
                    'total': 0,
                    'valid': 0,
                    'repaired_locally': 0,
                    'repaired_api': 0,
                    'failed': 0
                }
            return self._last_stats.to_dict()

    def review_document(
        self,
        document_ir: Dict[str, Any],
        ir_file_path: Optional[str | Path] = None,
        *,
        reset_stats: bool = True,
        save_on_repair: bool = True
    ) -> ReviewStats:
        """Review and fix all diagrams in the document.

        Traverse the blocks of all chapters and detect chart type widgets.
        Validation and repair of unreviewed charts.

        Thread safety: Create independent ReviewStats for each call to avoid concurrency competition.

        Parameters:
            document_ir: Document IR data
            ir_file_path: IR file path, if provided and repaired, will be automatically saved
            reset_stats: Parameters retained for backward compatibility, no longer have any practical effect
            save_on_repair: whether to automatically save to the file after repair

        Return:
            ReviewStats: Statistics for this review (thread-safe)"""
        # Create an independent statistical object for each call to avoid concurrency competition
        session_stats = ReviewStats()

        if not document_ir:
            logger.warning("ChartReviewService: document_ir is empty, skip review")
            # Update _last_stats to maintain backward compatibility
            with self._last_stats_lock:
                self._last_stats = session_stats
            return session_stats

        has_repairs = False

        # Go through all chapters
        for chapter in document_ir.get("chapters", []) or []:
            if not isinstance(chapter, dict):
                continue
            blocks = chapter.get("blocks", [])
            if isinstance(blocks, list):
                chapter_repairs = self._walk_and_review_blocks(blocks, chapter, session_stats)
                if chapter_repairs:
                    has_repairs = True

        # Output statistics
        self._log_stats(session_stats)

        # Update _last_stats to maintain backward compatibility
        with self._last_stats_lock:
            self._last_stats = session_stats

        # If there is a fix and a file path is provided, save to file
        if has_repairs and ir_file_path and save_on_repair:
            self._save_ir_to_file(document_ir, ir_file_path)

        return session_stats

    def _walk_and_review_blocks(
        self,
        blocks: List[Any],
        chapter_context: Dict[str, Any] | None,
        session_stats: ReviewStats
    ) -> bool:
        """Recursively traverse the blocks and review the graph.

        Parameters:
            blocks: list of blocks to traverse
            chapter_context: Chapter context
            session_stats: statistical object of this review session

        Return:
            bool: whether a repair occurred"""
        has_repairs = False

        for block in blocks or []:
            if not isinstance(block, dict):
                continue

            # Check if it is a chart widget
            if block.get("type") == "widget":
                repaired = self._review_chart_block(block, chapter_context, session_stats)
                if repaired:
                    has_repairs = True

            # Process nested blocks recursively
            nested_blocks = block.get("blocks")
            if isinstance(nested_blocks, list):
                if self._walk_and_review_blocks(nested_blocks, chapter_context, session_stats):
                    has_repairs = True

            # Handle items of type list
            if block.get("type") == "list":
                for item in block.get("items", []):
                    if isinstance(item, list):
                        if self._walk_and_review_blocks(item, chapter_context, session_stats):
                            has_repairs = True

            # Processing cells of table type
            if block.get("type") == "table":
                for row in block.get("rows", []):
                    if not isinstance(row, dict):
                        continue
                    for cell in row.get("cells", []):
                        if isinstance(cell, dict):
                            cell_blocks = cell.get("blocks", [])
                            if isinstance(cell_blocks, list):
                                if self._walk_and_review_blocks(cell_blocks, chapter_context, session_stats):
                                    has_repairs = True

        return has_repairs

    def _review_chart_block(
        self,
        block: Dict[str, Any],
        chapter_context: Dict[str, Any] | None,
        session_stats: ReviewStats
    ) -> bool:
        """Review a single chart block.

        Parameters:
            block: the block to be reviewed
            chapter_context: Chapter context
            session_stats: statistical object of this review session

        Return:
            bool: whether repairs have been made"""
        widget_type = block.get("widgetType", "")
        if not isinstance(widget_type, str):
            return False

        # Only chart.js types are processed (word clouds are processed separately and do not need to be repaired)
        is_chart = widget_type.startswith("chart.js")
        is_wordcloud = "wordcloud" in widget_type.lower()

        if not is_chart:
            return False

        widget_id = block.get("widgetId", "unknown")

        # Check if it has been reviewed
        if block.get("_chart_reviewed"):
            logger.debug(f"Chart {widget_id} reviewed, skipped")
            return False

        session_stats.total += 1

        # The word cloud is directly marked as valid
        if is_wordcloud:
            session_stats.valid += 1
            block["_chart_reviewed"] = True
            block["_chart_review_status"] = "valid"
            block["_chart_review_method"] = "none"
            return False

        # Perform data normalization first (supplement data from chapter context)
        self._normalize_chart_block(block, chapter_context)

        # Validate chart
        validation_result = self.validator.validate(block)

        if validation_result.is_valid:
            # Verification passed
            session_stats.valid += 1
            block["_chart_reviewed"] = True
            block["_chart_review_status"] = "valid"
            block["_chart_review_method"] = "none"
            if validation_result.warnings:
                logger.debug(f"Chart {widget_id} passed validation with warnings: {validation_result.warnings}")
            return False

        # Verification failed, try to repair
        logger.warning(f"Chart {widget_id} validation failed: {validation_result.errors}")

        repair_result = self.repairer.repair(block, validation_result)

        if repair_result.success and repair_result.repaired_block:
            # The repair is successful and the original block data is overwritten.
            repaired_block = repair_result.repaired_block
            # Preserve some original meta-information
            original_widget_id = block.get("widgetId")
            block.clear()
            block.update(repaired_block)
            # Make sure the widgetId is not lost
            if original_widget_id and not block.get("widgetId"):
                block["widgetId"] = original_widget_id

            method = repair_result.method or "local"
            if method == "local":
                session_stats.repaired_locally += 1
            elif method == "api":
                session_stats.repaired_api += 1

            block["_chart_reviewed"] = True
            block["_chart_review_status"] = "repaired"
            block["_chart_review_method"] = method

            logger.info(f"Chart {widget_id} repaired successfully (method: {method}): {repair_result.changes}")
            return True

        # Repair failed
        session_stats.failed += 1
        block["_chart_reviewed"] = True
        block["_chart_renderable"] = False
        block["_chart_review_status"] = "failed"
        block["_chart_review_method"] = "none"
        block["_chart_error_reason"] = self._format_error_reason(validation_result)

        logger.warning(f"Chart {widget_id} repair failed, marked as non-renderable")
        return False

    def _normalize_chart_block(
        self,
        block: Dict[str, Any],
        chapter_context: Dict[str, Any] | None = None
    ) -> None:
        """Standardize chart data, complete missing fields (such as props, scales, datasets), and improve fault tolerance.

        Consistent with HTMLRenderer._normalize_chart_block():
        - Make sure props exist
        - Merge top-level scales into props.options
        - Make sure data exists
        - Try to use chapter-level data as a fallback
        - Automatically generate labels"""
        if not isinstance(block, dict):
            return

        if block.get("type") != "widget":
            return

        widget_type = block.get("widgetType", "")
        if not (isinstance(widget_type, str) and widget_type.startswith("chart.js")):
            return

        # Make sure props exist
        props = block.get("props")
        if not isinstance(props, dict):
            block["props"] = {}
            props = block["props"]

        # Merge top-level scales into options to avoid configuration loss
        scales = block.get("scales")
        if isinstance(scales, dict):
            options = props.get("options") if isinstance(props.get("options"), dict) else {}
            props["options"] = self._merge_dicts(options, {"scales": scales})

        # Make sure data exists
        data = block.get("data")
        if not isinstance(data, dict):
            data = {}
            block["data"] = data

        # If datasets is empty, try to populate it with chapter-level data
        if chapter_context and self._is_chart_data_empty(data):
            chapter_data = chapter_context.get("data") if isinstance(chapter_context, dict) else None
            if isinstance(chapter_data, dict):
                fallback_ds = chapter_data.get("datasets")
                if isinstance(fallback_ds, list) and len(fallback_ds) > 0:
                    merged_data = copy.deepcopy(data)
                    merged_data["datasets"] = copy.deepcopy(fallback_ds)

                    if not merged_data.get("labels") and isinstance(chapter_data.get("labels"), list):
                        merged_data["labels"] = copy.deepcopy(chapter_data["labels"])

                    block["data"] = merged_data

        # If labels are still missing and the data points contain x values, automatically generate fallback and coordinate scales
        data_ref = block.get("data")
        if isinstance(data_ref, dict) and not data_ref.get("labels"):
            datasets_ref = data_ref.get("datasets")
            if isinstance(datasets_ref, list) and datasets_ref:
                first_ds = datasets_ref[0]
                ds_data = first_ds.get("data") if isinstance(first_ds, dict) else None
                if isinstance(ds_data, list):
                    labels_from_data = []
                    for idx, point in enumerate(ds_data):
                        if isinstance(point, dict):
                            label_text = point.get("x") or point.get("label") or f"Point {idx + 1}"
                        else:
                            label_text = f"Point {idx + 1}"
                        labels_from_data.append(str(label_text))

                    if labels_from_data:
                        data_ref["labels"] = labels_from_data

    @staticmethod
    def _is_chart_data_empty(data: Dict[str, Any] | None) -> bool:
        """Check if chart data is empty or missing valid datasets"""
        if not isinstance(data, dict):
            return True

        datasets = data.get("datasets")
        if not isinstance(datasets, list) or len(datasets) == 0:
            return True

        for ds in datasets:
            if not isinstance(ds, dict):
                continue
            series = ds.get("data")
            if isinstance(series, list) and len(series) > 0:
                return False

        return True

    @staticmethod
    def _merge_dicts(
        base: Dict[str, Any] | None, override: Dict[str, Any] | None
    ) -> Dict[str, Any]:
        """Recursively merge two dictionaries, override covers base, and both are new copies to avoid side effects."""
        result = copy.deepcopy(base) if isinstance(base, dict) else {}
        if not isinstance(override, dict):
            return result
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = ChartReviewService._merge_dicts(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    def _format_error_reason(self, validation_result: ValidationResult | None) -> str:
        """Reasons for formatting errors"""
        if not validation_result:
            return "unknown error"
        errors = validation_result.errors or []
        if not errors:
            return "Verification failed but no specific error message"
        return "; ".join(errors[:3])

    def _log_stats(self, stats: ReviewStats) -> None:
        """Output statistics"""
        if stats.total == 0:
            logger.debug("ChartReviewService: There are no charts to review")
            return

        logger.info(
            f"ChartReviewService Chart review completed:"
            f"Total {stats.total},"
            f"Valid {stats.valid},"
            f"Repair {stats.repaired_total} (local {stats.repaired_locally}, API {stats.repaired_api}),"
            f"failed {stats.failed}"
        )

    # Internal metadata key, should not be saved to IR file
    _INTERNAL_METADATA_KEYS = frozenset([
        "_chart_reviewed",
        "_chart_renderable",
        "_chart_review_status",
        "_chart_review_method",
        "_chart_error_reason",
    ])

    def _strip_internal_metadata(self, document_ir: Dict[str, Any]) -> Dict[str, Any]:
        """Removes all internal metadata keys from the document, returning a clean copy for persistence.

        These internal markers are only used for state tracking of the rendering process and should not be saved to the IR file.
        To avoid polluting the document structure and causing inconsistent behavior when reused."""
        cleaned = copy.deepcopy(document_ir)

        def strip_from_block(block: Dict[str, Any]) -> None:
            """Recursively remove internal metadata in blocks and their nested structures"""
            if not isinstance(block, dict):
                return

            # Removes the internal keys of the current block
            for key in self._INTERNAL_METADATA_KEYS:
                block.pop(key, None)

            # Process nested blocks recursively
            nested_blocks = block.get("blocks")
            if isinstance(nested_blocks, list):
                for nested in nested_blocks:
                    strip_from_block(nested)

            # Handle items of type list
            if block.get("type") == "list":
                for item in block.get("items", []):
                    if isinstance(item, list):
                        for sub_block in item:
                            strip_from_block(sub_block)

            # Processing cells of table type
            if block.get("type") == "table":
                for row in block.get("rows", []):
                    if not isinstance(row, dict):
                        continue
                    for cell in row.get("cells", []):
                        if isinstance(cell, dict):
                            cell_blocks = cell.get("blocks", [])
                            if isinstance(cell_blocks, list):
                                for cell_block in cell_blocks:
                                    strip_from_block(cell_block)

        # Process all chapters
        for chapter in cleaned.get("chapters", []) or []:
            if not isinstance(chapter, dict):
                continue
            blocks = chapter.get("blocks", [])
            if isinstance(blocks, list):
                for block in blocks:
                    strip_from_block(block)

        return cleaned

    def _save_ir_to_file(self, document_ir: Dict[str, Any], file_path: str | Path) -> None:
        """Save IR to file (after removing internal metadata)"""
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            # Remove internal metadata keys to keep IR files clean
            cleaned_ir = self._strip_internal_metadata(document_ir)

            path.write_text(
                json.dumps(cleaned_ir, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.info(f"ChartReviewService: Repaired IR saved to {path}")
        except Exception as e:
            logger.exception(f"ChartReviewService: Failed to save IR file: {e}")


# Global singleton instance
_chart_review_service: Optional[ChartReviewService] = None


def get_chart_review_service() -> ChartReviewService:
    """Get the ChartReviewService singleton instance"""
    global _chart_review_service
    if _chart_review_service is None:
        _chart_review_service = ChartReviewService()
    return _chart_review_service


def review_document_charts(
    document_ir: Dict[str, Any],
    ir_file_path: Optional[str | Path] = None,
    *,
    reset_stats: bool = True,
    save_on_repair: bool = True
) -> ReviewStats:
    """Convenience function: Review and fix all diagrams in the document.

    Parameters:
        document_ir: Document IR data
        ir_file_path: IR file path, if provided and repaired, will be automatically saved
        reset_stats: Parameters retained for backward compatibility, no longer have any practical effect
        save_on_repair: whether to automatically save to the file after repair

    Return:
        ReviewStats: Statistics for this review"""
    service = get_chart_review_service()
    return service.review_document(
        document_ir,
        ir_file_path,
        reset_stats=reset_stats,
        save_on_repair=save_on_repair
    )


__all__ = [
    "ChartReviewService",
    "ReviewStats",
    "get_chart_review_service",
    "review_document_charts",
]

