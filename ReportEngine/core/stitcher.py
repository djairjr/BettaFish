"""Chapter binder: Responsible for merging multiple JSON chapters into the entire IR.

DocumentComposer injects missing anchors, unifies order, and completes IR-level metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Set

from ..ir import IR_VERSION


class DocumentComposer:
    """A simple binder that splices chapters into Document IR.

    Function:
        - Sort chapters by order, supplement the default chapterId;
        - Prevent anchor duplication and generate globally unique anchor points;
        - Inject IR version and generation timestamp."""

    def __init__(self):
        """Initialize the binder and record used anchor points to avoid duplication"""
        self._seen_anchors: Set[str] = set()

    def build_document(
        self,
        report_id: str,
        metadata: Dict[str, object],
        chapters: List[Dict[str, object]],
    ) -> Dict[str, object]:
        """Sort all chapters in order and inject unique anchor points to form the entire IR.

        At the same time, metadata/themeTokens/assets are merged for direct consumption by the renderer.

        Parameters:
            report_id: ID of this report.
            metadata: global meta information (title, topic, toc, etc.).
            chapters: Chapter payload list.

        Return:
            dict: Document IR that meets the needs of the renderer."""
        # Build a mapping from chapterId to toc anchor
        toc_anchor_map = self._build_toc_anchor_map(metadata)

        ordered = sorted(chapters, key=lambda c: c.get("order", 0))
        for idx, chapter in enumerate(ordered, start=1):
            chapter.setdefault("chapterId", f"S{idx}")

            # Priority: 1. The anchor configured in the directory 2. The anchor that comes with the chapter 3. The default anchor
            chapter_id = chapter.get("chapterId")
            anchor = (
                toc_anchor_map.get(chapter_id) or
                chapter.get("anchor") or
                f"section-{idx}"
            )
            chapter["anchor"] = self._ensure_unique_anchor(anchor)
            chapter.setdefault("order", idx * 10)
            if chapter.get("errorPlaceholder"):
                self._ensure_heading_block(chapter)

        document = {
            "version": IR_VERSION,
            "reportId": report_id,
            "metadata": {
                **metadata,
                "generatedAt": metadata.get("generatedAt")
                or datetime.utcnow().isoformat() + "Z",
            },
            "themeTokens": metadata.get("themeTokens", {}),
            "chapters": ordered,
            "assets": metadata.get("assets", {}),
        }
        return document

    def _ensure_unique_anchor(self, anchor: str) -> str:
        """If there are duplicate anchor points, the sequence number will be appended to ensure global uniqueness."""
        base = anchor
        counter = 2
        while anchor in self._seen_anchors:
            anchor = f"{base}-{counter}"
            counter += 1
        self._seen_anchors.add(anchor)
        return anchor

    def _build_toc_anchor_map(self, metadata: Dict[str, object]) -> Dict[str, str]:
        """Build chapterId to anchor mapping from metadata.toc.customEntries.

        Parameters:
            metadata: document meta information.

        Return:
            dict: mapping of chapterId -> anchor."""
        toc_config = metadata.get("toc") or {}
        custom_entries = toc_config.get("customEntries") or []
        anchor_map = {}

        for entry in custom_entries:
            if isinstance(entry, dict):
                chapter_id = entry.get("chapterId")
                anchor = entry.get("anchor")
                if chapter_id and anchor:
                    anchor_map[chapter_id] = anchor

        return anchor_map

    def _ensure_heading_block(self, chapter: Dict[str, object]) -> None:
        """Ensure that placeholder chapters still have heading blocks available for the table of contents."""
        blocks = chapter.get("blocks")
        if isinstance(blocks, list):
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "heading":
                    return
        heading = {
            "type": "heading",
            "level": 2,
            "text": chapter.get("title") or "Placeholder chapter",
            "anchor": chapter.get("anchor"),
        }
        if isinstance(blocks, list):
            blocks.insert(0, heading)
        else:
            chapter["blocks"] = [heading]


__all__ = ["DocumentComposer"]
