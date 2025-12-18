"""Based on the template table of contents and multi-source reports, generate the title/table of contents/theme design of the entire report."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from loguru import logger

from ..core import TemplateSection
from ..prompts import (
    SYSTEM_PROMPT_DOCUMENT_LAYOUT,
    build_document_layout_prompt,
)
from ..utils.json_parser import RobustJSONParser, JSONParseError
from .base_node import BaseNode


class DocumentLayoutNode(BaseNode):
    """Responsible for generating global title, table of contents and Hero design.

    Combined with template slicing, report summaries and forum discussions, it guides the visual and structural tone of the entire book."""

    def __init__(self, llm_client):
        """Record the LLM client and set the node name for BaseNode log use"""
        super().__init__(llm_client, "DocumentLayoutNode")
        # Initialize robust JSON parser, enable all repair strategies
        self.json_parser = RobustJSONParser(
            enable_json_repair=True,
            enable_llm_repair=False,  # LLM repair can be enabled as needed
            max_repair_attempts=3,
        )

    def run(
        self,
        sections: List[TemplateSection],
        template_markdown: str,
        reports: Dict[str, str],
        forum_logs: str,
        query: str,
        template_overview: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Comprehensive template + multi-source content to generate the title, directory structure and theme color palette of the entire book.

        Parameters:
            sections: List of sections after template slicing.
            template_markdown: template original text, used for LLM to understand the context.
            reports: Content mapping of the three engines.
            forum_logs: Forum discussion summary.
            query: user query word.
            template_overview: Pre-generated template overview, which can be reused to reduce prompt word length.

        Return:
            dict: A dictionary containing design information such as title/subtitle/toc/hero/themeTokens."""
        # Feed the original template text, slice structure and multi-source reports to LLM to facilitate its understanding of levels and materials.
        payload = {
            "query": query,
            "template": {
                "raw": template_markdown,
                "sections": [section.to_dict() for section in sections],
            },
            "templateOverview": template_overview
            or {
                "title": sections[0].title if sections else "",
                "chapters": [section.to_dict() for section in sections],
            },
            "reports": reports,
            "forumLogs": forum_logs,
        }

        user_message = build_document_layout_prompt(payload)
        response = self.llm_client.stream_invoke_to_string(
            SYSTEM_PROMPT_DOCUMENT_LAYOUT,
            user_message,
            temperature=0.3,
            top_p=0.9,
        )
        design = self._parse_response(response)
        logger.info("Document title/table of contents design generated")
        return design

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """Parse the JSON text returned by LLM and throw a friendly error if it fails.

        Multiple repair attempts using a robust JSON parser:
        1. Clean up markdown tags and thinking content
        2. Local grammar fixes (bracket balancing, comma completion, control character escaping, etc.)
        3. Use json_repair library for advanced repair
        4. Optional LLM-assisted repair

        Parameters:
            raw: LLM original return string, allowing ``` packages, thinking content, etc.

        Return:
            dict: structured design draft.

        Exception:
            ValueError: Thrown when the response is empty or JSON parsing fails."""
        try:
            result = self.json_parser.parse(
                raw,
                context_name="Document design",
                # The directory field has been renamed tocPlan, and the latest Schema verification is followed here.
                expected_keys=["title", "tocPlan", "hero"],
            )
            # Validate the type of key fields
            if not isinstance(result.get("title"), str):
                logger.warning("The document design is missing the title field or has the wrong type. Use the default value.")
                result.setdefault("title", "Unnamed report")

            # Handle tocPlan field
            toc_plan = result.get("tocPlan", [])
            if not isinstance(toc_plan, list):
                logger.warning("Document design is missing tocPlan field or has wrong type, using empty list")
                result["tocPlan"] = []
            else:
                # Clean up the description field in tocPlan
                result["tocPlan"] = self._clean_toc_plan_descriptions(toc_plan)

            if not isinstance(result.get("hero"), dict):
                logger.warning("The document design is missing the hero field or has the wrong type, using an empty object")
                result.setdefault("hero", {})

            return result
        except JSONParseError as exc:
            # Convert to original exception type to maintain backward compatibility
            raise ValueError(f"Document design JSON parsing failed: {exc}") from exc

    def _clean_toc_plan_descriptions(self, toc_plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Clean the description field of each entry in tocPlan, removing possible JSON fragments.

        Parameters:
            toc_plan: original directory plan list

        Return:
            List[Dict[str, Any]]: Cleaned directory plan list"""
        import re

        def clean_text(text: Any) -> str:
            """Clean JSON fragments from text"""
            if not text or not isinstance(text, str):
                return ""

            cleaned = text

            # Remove incomplete JSON objects starting with comma+blank+{
            cleaned = re.sub(r',\s*\{[^}]*$', '', cleaned)

            # Remove incomplete JSON arrays starting with comma+blank+[
            cleaned = re.sub(r',\s*\[[^\]]*$', '', cleaned)

            # Remove orphaned { plus following if no matching }
            open_brace_pos = cleaned.rfind('{')
            if open_brace_pos != -1:
                close_brace_pos = cleaned.rfind('}')
                if close_brace_pos < open_brace_pos:
                    cleaned = cleaned[:open_brace_pos].rstrip(',，、 \t\n')

            # Remove orphaned [ followed by content if no matching ]
            open_bracket_pos = cleaned.rfind('[')
            if open_bracket_pos != -1:
                close_bracket_pos = cleaned.rfind(']')
                if close_bracket_pos < open_bracket_pos:
                    cleaned = cleaned[:open_bracket_pos].rstrip(',，、 \t\n')

            # Remove fragments that look like JSON key-value pairs
            cleaned = re.sub(r',?\s*"[^"]+"\s*:\s*"[^"]*$', '', cleaned)
            cleaned = re.sub(r',?\s*"[^"]+"\s*:\s*[^,}\]]*$', '', cleaned)

            # Clean up trailing commas and whitespace
            cleaned = cleaned.rstrip(',，、 \t\n')

            return cleaned.strip()

        cleaned_plan = []
        for entry in toc_plan:
            if not isinstance(entry, dict):
                continue

            # Clean description field
            if "description" in entry:
                original_desc = entry["description"]
                cleaned_desc = clean_text(original_desc)

                if cleaned_desc != original_desc:
                    logger.warning(
                        f"Clean the JSON fragment in the description field of directory entry '{entry.get('display', 'unknown')}':\n"
                        f"Original text: {original_desc[:100]}...\n"
                        f"After cleaning: {cleaned_desc[:100]}..."
                    )
                    entry["description"] = cleaned_desc

            cleaned_plan.append(entry)

        return cleaned_plan


__all__ = ["DocumentLayoutNode"]
