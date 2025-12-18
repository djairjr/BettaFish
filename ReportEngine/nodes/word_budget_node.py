"""Chapter length planning nodes."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from loguru import logger

from ..core import TemplateSection
from ..prompts import (
    SYSTEM_PROMPT_WORD_BUDGET,
    build_word_budget_prompt,
)
from ..utils.json_parser import RobustJSONParser, JSONParseError
from .base_node import BaseNode


class WordBudgetNode(BaseNode):
    """Plan the word count and focus of each chapter.

    Outputs total word count, global writing guidelines, and target/min/max word count constraints for each chapter/section."""

    def __init__(self, llm_client):
        """Only LLM client references are recorded to facilitate requests initiated during the run phase."""
        super().__init__(llm_client, "WordBudgetNode")
        # Initialize robust JSON parser, enable all repair strategies
        self.json_parser = RobustJSONParser(
            enable_json_repair=True,
            enable_llm_repair=False,  # LLM repair can be enabled as needed
            max_repair_attempts=3,
        )

    def run(
        self,
        sections: List[TemplateSection],
        design: Dict[str, Any],
        reports: Dict[str, str],
        forum_logs: str,
        query: str,
        template_overview: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Plan the word count of chapters based on the design draft and all materials, so that LLM has clear length goals when writing.

        Parameters:
            sections: list of template sections.
            design: The design draft returned by the layout node (title/toc/hero, etc.).
            reports: Three-engine report mapping.
            forum_logs: Forum log original text.
            query: user query word.
            template_overview: Optional template overview, including chapter meta-information.

        Return:
            dict: Chapter length planning results, including `totalWords`, `globalGuidelines` and chapter-by-chapters`."""
        # In addition to the chapter skeleton, the input also contains layout node output, which facilitates reference of visual priority when constraining the length.
        payload = {
            "query": query,
            "design": design,
            "sections": [section.to_dict() for section in sections],
            "templateOverview": template_overview
            or {
                "title": sections[0].title if sections else "",
                "chapters": [section.to_dict() for section in sections],
            },
            "reports": reports,
            "forumLogs": forum_logs,
        }
        user = build_word_budget_prompt(payload)
        response = self.llm_client.stream_invoke_to_string(
            SYSTEM_PROMPT_WORD_BUDGET,
            user,
            temperature=0.25,
            top_p=0.85,
        )
        plan = self._parse_response(response)
        logger.info("Chapter word count plan has been generated")
        return plan

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """Convert the JSON text output by LLM into a dictionary, and prompt a planning exception when it fails.

        Multiple repair attempts using a robust JSON parser:
        1. Clean up markdown tags and thinking content
        2. Local grammar fixes (bracket balancing, comma completion, control character escaping, etc.)
        3. Use json_repair library for advanced repair
        4. Optional LLM-assisted repair

        Parameters:
            raw: LLM return value, which may include ``` packages, thinking content, etc.

        Return:
            dict: legal length planning JSON.

        Exception:
            ValueError: Thrown when the response is empty or JSON parsing fails."""
        try:
            result = self.json_parser.parse(
                raw,
                context_name="Space planning",
                expected_keys=["totalWords", "globalGuidelines", "chapters"],
            )
            # Validate the type of key fields
            if not isinstance(result.get("totalWords"), (int, float)):
                logger.warning("The totalWords field in the space plan is missing or the type is wrong. Use the default value.")
                result.setdefault("totalWords", 10000)
            if not isinstance(result.get("globalGuidelines"), list):
                logger.warning("The globalGuidelines field is missing or the type is wrong in the space plan, and an empty list is used.")
                result.setdefault("globalGuidelines", [])
            if not isinstance(result.get("chapters"), (list, dict)):
                logger.warning("The chapters field is missing or the type is wrong in the space plan, and an empty list is used.")
                result.setdefault("chapters", [])
            return result
        except JSONParseError as exc:
            # Convert to original exception type to maintain backward compatibility
            raise ValueError(f"Space planning JSON parsing failed: {exc}") from exc


__all__ = ["WordBudgetNode"]
