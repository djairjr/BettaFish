"""Report Engine core tool collection.

This package encapsulates the three basic capabilities of template slicing, chapter storage and chapter binding.
All upper-level nodes will reuse these tools to ensure a consistent structure."""

from .template_parser import TemplateSection, parse_template_sections
from .chapter_storage import ChapterStorage
from .stitcher import DocumentComposer

__all__ = [
    "TemplateSection",
    "parse_template_sections",
    "ChapterStorage",
    "DocumentComposer",
]
