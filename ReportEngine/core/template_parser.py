"""Markdown template slicing tool.

LLM needs to be "called by chapter", so the Markdown template must be parsed into a structured chapter queue.
Here, through lightweight regularity and indentation heuristics, "# title" is compatible with
"- **1.0 title** / - 1.1 subtitle" and other writing methods."种写法。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

SECTION_ORDER_STEP = 10


@dataclass
class TemplateSection:
    """Template chapter entity.

    Record the title, slug, serial number, hierarchy, original title, chapter number and outline,
    It is convenient for subsequent nodes to be referenced in prompt words and to keep the anchor points consistent."""

    title: str
    slug: str
    order: int
    depth: int
    raw_title: str
    number: str = ""
    chapter_id: str = ""
    outline: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize chapter entities into a dictionary.

        This structure is widely used to prompt word context and as input to layout/word budget nodes."""
        return {
            "title": self.title,
            "slug": self.slug,
            "order": self.order,
            "depth": self.depth,
            "number": self.number,
            "chapterId": self.chapter_id,
            "outline": self.outline,
        }


# Parsing expressions deliberately avoid using `.*` to maintain the certainty of matching.
# And avoid common regular DoS risks in untrusted template text.
heading_pattern = re.compile(
    r"""(?P<marker>\#{1,6}) # Markdown title mark
    [ \t]+ # Required whitespace characters
    (?P<title>[^\r\n]+) # Title text without line breaks"      # Title text without line breaks
    """,
    re.VERBOSE,
)
bullet_pattern = re.compile(
    r"""(?P<marker>[-*+]) # list bullets
    [\t]+
    (?P<title>[^\r\n]+)"
    """,
    re.VERBOSE,
)
number_pattern = re.compile(
    r"""
    (?P<num>
        (?:0|[1-9]\d*)
        (?:\.(?:0|[1-9]\d*))*
    )
    (?:
        (?:[ \t\u00A0\u3000、:：-]+|\.(?!\d))+
        (?P<label>[^\r\n]*)
    )?
    """,
    re.VERBOSE,
)


def parse_template_sections(template_md: str) -> List[TemplateSection]:
    """Divide the Markdown template into a list of chapters (by large title).

    Each TemplateSection returned carries the slug/order/chapter number,
    This facilitates subsequent chapter calling and anchor point generation. Will be compatible at the same time when parsing
    "# title", "unsigned number", "list outline" and other different writing methods.

    Parameters:
        template_md: Full text of template Markdown.

    Return:
        list[TemplateSection]: Structured sequence of sections."
    返回:
        list[TemplateSection]: 结构化的章节序列。
    """

    sections: List[TemplateSection] = []
    current: Optional[TemplateSection] = None
    order = SECTION_ORDER_STEP
    used_slugs = set()

    for raw_line in template_md.splitlines():
        if not raw_line.strip():
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()

        meta = _classify_line(stripped, indent)
        if not meta:
            continue

        if meta["is_section"]:
            slug = _ensure_unique_slug(meta["slug"], used_slugs)
            section = TemplateSection(
                title=meta["title"],
                slug=slug,
                order=order,
                depth=meta["depth"],
                raw_title=meta["raw"],
                number=meta["number"],
            )
            sections.append(section)
            current = section
            order += SECTION_ORDER_STEP
            continue

        # outline items
        if current:
            current.outline.append(meta["title"])

    for idx, section in enumerate(sections, start=1):
        # Generate a stable chapter_id for each chapter to facilitate subsequent reference
        section.chapter_id = f"S{idx}"

    return sections


def _classify_line(stripped: str, indent: int) -> Optional[dict]:
    """Sort lines based on indentation and symbols.

    Use regular rules to determine whether the current line is a chapter title, outline, or an ordinary list item.
    And derive derived information such as depth/slug/number.

    Parameters:
        stripped: The original line after removing leading and trailing spaces.
        indent: The number of spaces at the beginning of the line, used to distinguish levels.

    Return:
        dict | None: Recognized metadata; returns None if unrecognized."""

    heading_match = heading_pattern.fullmatch(stripped)
    if heading_match:
        level = len(heading_match.group("marker"))
        payload = _strip_markup(heading_match.group("title").strip())
        title_info = _split_number(payload)
        slug = _build_slug(title_info["number"], title_info["title"])
        return {
            "is_section": level <= 2,
            "depth": level,
            "title": title_info["display"],
            "raw": payload,
            "number": title_info["number"],
            "slug": slug,
        }

    bullet_match = bullet_pattern.fullmatch(stripped)
    if bullet_match:
        payload = _strip_markup(bullet_match.group("title").strip())
        title_info = _split_number(payload)
        slug = _build_slug(title_info["number"], title_info["title"])
        is_section = indent <= 1
        depth = 1 if indent <= 1 else 2
        return {
            "is_section": is_section,
            "depth": depth,
            "title": title_info["display"],
            "raw": payload,
            "number": title_info["number"],
            "slug": slug,
        }

    # Compatible with "1.1..." lines without prefix symbols
    number_match = number_pattern.fullmatch(stripped)
    if number_match and number_match.group("label"):
        payload = stripped
        title = number_match.group("label").strip()
        number = number_match.group("num")
        slug = _build_slug(number, title)
        is_section = indent == 0 and number.count(".") <= 1
        depth = 1 if is_section else 2
        display = f"{number} {title}" if title else number
        return {
            "is_section": is_section,
            "depth": depth,
            "title": display,
            "raw": payload,
            "number": number,
            "slug": slug,
        }

    return None


def _strip_markup(text: str) -> str:
    """Remove emphasis marks such as ** and __ from the package to avoid interfering with title matching."""
    if text.startswith(("**", "__")) and text.endswith(("**", "__")) and len(text) > 4:
        return text[2:-2].strip()
    return text


def _split_number(payload: str) -> dict:
    """Split numbers and titles.

    For example, `1.2 market trend` will be split into number=1.2, label=market trend,
    And provide display for backfilling the title.

    Parameters:
        payload: Original title string.

    Return:
        dict: contains number/title/display."""
    match = number_pattern.fullmatch(payload)
    number = match.group("num") if match else ""
    label = match.group("label") if match else payload
    label = (label or "").strip()
    display = f"{number} {label}".strip() if number else label or payload
    title_core = label or payload
    return {
        "number": number,
        "title": title_core,
        "display": display,
    }


def _build_slug(number: str, title: str) -> str:
    """Generate anchor points based on the number/title, reuse the number first, and slug the title if missing.

    Parameters:
        number: Chapter number.
        title: Title text.

    Return:
        str: slug in the form of `section-1-0`."""
    if number:
        token = number.replace(".", "-")
    else:
        token = _slugify_text(title)
    token = token or "section"
    return f"section-{token}"


def _slugify_text(text: str) -> str:
    """Denoise and transcribe any text to obtain URL-friendly slug fragments.

    It will correct the case, remove special symbols and retain Chinese characters to ensure that the anchor point is readable."""
    text = unicodedata.normalize("NFKD", text)
    text = text.replace("·", "-").replace(" ", "-")
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-").lower()


def _ensure_unique_slug(slug: str, used: set) -> str:
    """If the slug is repeated, the serial number will be automatically appended until it is unique in the used collection.

    Use `-2/-3...` to ensure that the same title will not generate duplicate anchors.

    Parameters:
        slug: initial slug.
        used: The collection has been used.

    Return:
        str: slug after deduplication."""
    if slug not in used:
        used.add(slug)
        return slug
    base = slug
    idx = 2
    while slug in used:
        slug = f"{base}-{idx}"
        idx += 1
    used.add(slug)
    return slug


__all__ = ["TemplateSection", "parse_template_sections"]
