"""Chart API fix module.

Provides LLM API for calling 4 Engines (ReportEngine, ForumEngine, InsightEngine, MediaEngine)
to fix the functionality of chart data."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from loguru import logger

from ReportEngine.utils.config import settings


# Chart repair tips
CHART_REPAIR_SYSTEM_PROMPT = """You are a professional chart data repair assistant. Your task is to fix formatting errors in Chart.js chart data and ensure that the chart can be rendered normally.

**Chart.js standard data format:**

1. Standard charts (line, bar, pie, doughnut, radar, polarArea):
```json
{"type": "widget",
  "widgetType": "chart.js/bar",
  "widgetId": "chart-001",
  "props": {
    "type": "bar",
    "title": "图表标题",
    "options": {
      "responsive": true,
      "plugins": {
        "legend": {
          "display": true
        }
      }
    }
  },
  "data": {
    "labels": ["A", "B", "C"],
    "datasets": [
      {
        "label": "系列1",
        "data": [10, 20, 30]
      }
    ]
  }
}
```

2. Special charts (scatter, bubble):
```json
{"data": {
    "datasets": [
      {
        "label": "系列1",
        "data": [
          {"x": 10, "y": 20},
          {"x": 15, "y": 25}
        ]
      }
    ]
  }
}
```

**Repair Principles:**
1. **Rather no changes than fix errors** - If you are not sure how to fix it, keep the original data
2. **MINIMAL CHANGES** - Only fix clear bugs, don’t overdo it
3. **Maintain Data Integrity** - Don’t lose the original data
4. **Verify the repair results** - Ensure that the repair complies with the Chart.js format

**Common errors and how to fix them:**
1. Missing labels field → generate default labels based on data
2. datasets are not arrays → convert to array format
3. Data length does not match → truncate or fill in null
4. Non-numeric data → try to convert or set to null
5. Missing required fields → Add default value

Please repair the chart data according to the error information and return the repaired complete widget block (JSON format)."""


# Table repair prompts
TABLE_REPAIR_SYSTEM_PROMPT = """You are a professional table data repair assistant. Your task is to fix format errors in the IR table data and ensure that the table renders properly.

**Standard tabular data format:**

```json
{"type": "table",
  "rows": [
    {
      "cells": [
        {
          "header": true,
          "blocks": [
            {
              "type": "paragraph",
              "inlines": [{"text": "列标题", "marks": []}]
            }
          ]
        },
        {
          "header": true,
          "blocks": [
            {
              "type": "paragraph",
              "inlines": [{"text": "另一列", "marks": []}]
            }
          ]
        }
      ]
    },
    {
      "cells": [
        {
          "blocks": [
            {
              "type": "paragraph",
              "inlines": [{"text": "数据内容", "marks": []}]
            }
          ]
        },
        {
          "blocks": [
            {
              "type": "paragraph",
              "inlines": [{"text": "另一数据", "marks": []}]
            }
          ]
        }
      ]
    }
  ]
}
```

**⚠️ Common mistake: nested cells structure**

This is a very common mistake. LLM often nests cells at the same level incorrectly:

❌ **Error Example:**
```json
{"cells": [
    { "blocks": [...], "colspan": 1 },
    { "cells": [
        { "blocks": [...] },
        { "cells": [...] }
      ]
    }
  ]
}
```

✅ **Correct format:**
```json
{"cells": [
    { "blocks": [...], "colspan": 1 },
    { "blocks": [...] },
    { "blocks": [...] }
  ]
}
```

**Repair Principles:**
1. **Flat nested cells** - Flatten incorrectly nested cells to siblings
2. **Make sure each cell has blocks** - Each cell must have a blocks array
3. Use paragraph within **blocks** - text content should be placed within paragraph block
4. **Maintain Data Integrity** - Don’t lose the original content

**Fix:**
1. Nested cells structure → flatten into sibling cells array
2. Missing blocks field → add blocks containing paragraph
3. Empty cells array → add default empty cells
4. Illegal cell type → Convert to standard format

Please repair the table data according to the error message and return the repaired complete table block (JSON format)."""


# Word Cloud Repair Prompt Words
WORDCLOUD_REPAIR_SYSTEM_PROMPT = """You are a professional word cloud data repair assistant. Your task is to fix formatting errors in the word cloud widget data and ensure that the word cloud renders properly.

**Standard word cloud data format:**

```json
{"type": "widget",
  "widgetType": "wordcloud",
  "widgetId": "wordcloud-001",
  "title": "词云标题",
  "data": {
    "words": [
      {"text": "关键词1", "weight": 10},
      {"text": "关键词2", "weight": 8},
      {"text": "关键词3", "weight": 6}
    ]
  }
}
```

**⚠️ Data path description: **

Word cloud data can be located in the following paths (in order of priority):
1. `data.words` - recommended path
2. `data.items` - alternative path
3. `props.words` - alternative path
4. `props.items` - alternative path
5. `props.data` - alternative path

**Word Cloud Project Format:**

Each word cloud item should be an object containing:
- `text` or `word` or `label`: word text (required)
- `weight` or `value`: weight/frequency (required)
- `category`: category (optional)

**Repair Principles:**
1. **Normalized data path** - preferentially use `data.words`
2. **Make sure fields are required** - Each term must have text and weight
3. **Convert Compatible Formats** - Convert other formats to standard formats
4. **Maintain Data Integrity** - Don’t lose the original words

**Common errors and how to fix them:**
1. Data is in wrong path → move to `data.words`
2. Missing weight field → generate default weight based on position
3. Use word instead of text → Unify into text field
4. Array elements are strings → converted to object format

Please repair the word cloud data according to the error message and return the repaired complete widget block (JSON format)."""


def build_table_repair_prompt(
    table_block: Dict[str, Any],
    validation_errors: List[str]
) -> str:
    """Build table repair prompt words.

    Args:
        table_block: original table block
        validation_errors: validation error list

    Returns:
        str: prompt word"""
    block_json = json.dumps(table_block, ensure_ascii=False, indent=2)
    errors_text = "\n".join(f"- {error}" for error in validation_errors)

    prompt = f"""Please fix errors in the following table data:

**Raw data:**
```json
{block_json}
```

**Error detected:**
{errors_text}

**Requirements:**
1. Return the complete table block after repair (JSON format)
2. Pay special attention to flattening the nested cells structure
3. Make sure each cell has a blocks array
4. If you are not sure how to fix it, keep the original data

**Important output format requirements:**
1. Only return pure JSON objects, do not add any description text
2. Do not use ```json``` to mark packages
3. Make sure the JSON syntax is completely correct
4. Use double quotes for all strings"""
    return prompt


def build_wordcloud_repair_prompt(
    widget_block: Dict[str, Any],
    validation_errors: List[str]
) -> str:
    """Build a word cloud to repair prompt words.

    Args:
        widget_block: original wordcloud widget block
        validation_errors: validation error list

    Returns:
        str: prompt word"""
    block_json = json.dumps(widget_block, ensure_ascii=False, indent=2)
    errors_text = "\n".join(f"- {error}" for error in validation_errors)

    prompt = f"""Please fix the errors in the following word cloud data:

**Raw data:**
```json
{block_json}
```

**Error detected:**
{errors_text}

**Requirements:**
1. Return the repaired complete widget block (JSON format)
2. Make sure the word cloud data is located in the data.words path
3. Each term must have text and weight fields
4. If you are not sure how to fix it, keep the original data

**Important output format requirements:**
1. Only return pure JSON objects, do not add any description text
2. Do not use ```json``` to mark packages
3. Make sure the JSON syntax is completely correct
4. Use double quotes for all strings"""
    return prompt


def build_chart_repair_prompt(
    widget_block: Dict[str, Any],
    validation_errors: List[str]
) -> str:
    """Build diagram repair prompt words.

    Args:
        widget_block: original widget block
        validation_errors: validation error list

    Returns:
        str: prompt word"""
    block_json = json.dumps(widget_block, ensure_ascii=False, indent=2)
    errors_text = "\n".join(f"- {error}" for error in validation_errors)

    prompt = f"""Please fix errors in the following chart data:

**Raw data:**
```json
{block_json}
```

**Error detected:**
{errors_text}

**Requirements:**
1. Return the repaired complete widget block (JSON format)
2. Only fix clear errors and leave other data unchanged
3. Ensure that the repaired data meets the Chart.js format requirements
4. If you are not sure how to fix it, keep the original data

**Important output format requirements:**
1. Only return pure JSON objects, do not add any description text
2. Do not use ```json``` to mark packages
3. Make sure the JSON syntax is completely correct
4. Use double quotes for all strings"""
    return prompt


def create_llm_repair_functions() -> List:
    """Create a list of LLM repair functions.

    Returns the repair function of 4 Engines:
    1. ReportEngine
    2. ForumEngine (via ForumHost)
    3.InsightEngine
    4.MediaEngine

    Returns:
        List[Callable]: Repair function list"""
    repair_functions = []

    # 1. ReportEngine repair function
    if settings.REPORT_ENGINE_API_KEY and settings.REPORT_ENGINE_BASE_URL:
        def repair_with_report_engine(widget_block: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
            """Fix charts using ReportEngine's LLM"""
            try:
                from ReportEngine.llms import LLMClient

                client = LLMClient(
                    api_key=settings.REPORT_ENGINE_API_KEY,
                    base_url=settings.REPORT_ENGINE_BASE_URL,
                    model_name=settings.REPORT_ENGINE_MODEL_NAME or "gpt-4",
                )

                prompt = build_chart_repair_prompt(widget_block, errors)
                response = client.invoke(
                    CHART_REPAIR_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.0,
                    top_p=0.05
                )

                if not response:
                    return None

                # Parse response
                repaired = json.loads(response)
                return repaired

            except Exception as e:
                logger.exception(f"ReportEngine chart repair failed: {e}")
                return None

        repair_functions.append(repair_with_report_engine)
        logger.debug("ReportEngine chart repair function added")

    # 2. ForumEngine repair function
    if settings.FORUM_HOST_API_KEY and settings.FORUM_HOST_BASE_URL:
        def repair_with_forum_engine(widget_block: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
            """Fix charts using ForumEngine’s LLM"""
            try:
                from ReportEngine.llms import LLMClient

                client = LLMClient(
                    api_key=settings.FORUM_HOST_API_KEY,
                    base_url=settings.FORUM_HOST_BASE_URL,
                    model_name=settings.FORUM_HOST_MODEL_NAME or "gpt-4",
                )

                prompt = build_chart_repair_prompt(widget_block, errors)
                response = client.invoke(
                    CHART_REPAIR_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.0,
                    top_p=0.05
                )

                if not response:
                    return None

                repaired = json.loads(response)
                return repaired

            except Exception as e:
                logger.exception(f"ForumEngine chart repair failed: {e}")
                return None

        repair_functions.append(repair_with_forum_engine)
        logger.debug("ForumEngine chart repair function added")

    # 3. InsightEngine repair function
    if settings.INSIGHT_ENGINE_API_KEY and settings.INSIGHT_ENGINE_BASE_URL:
        def repair_with_insight_engine(widget_block: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
            """Repair charts using InsightEngine’s LLM"""
            try:
                from ReportEngine.llms import LLMClient

                client = LLMClient(
                    api_key=settings.INSIGHT_ENGINE_API_KEY,
                    base_url=settings.INSIGHT_ENGINE_BASE_URL,
                    model_name=settings.INSIGHT_ENGINE_MODEL_NAME or "gpt-4",
                )

                prompt = build_chart_repair_prompt(widget_block, errors)
                response = client.invoke(
                    CHART_REPAIR_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.0,
                    top_p=0.05
                )

                if not response:
                    return None

                repaired = json.loads(response)
                return repaired

            except Exception as e:
                logger.exception(f"InsightEngine chart repair failed: {e}")
                return None

        repair_functions.append(repair_with_insight_engine)
        logger.debug("InsightEngine chart repair function added")

    # 4. MediaEngine repair function
    if settings.MEDIA_ENGINE_API_KEY and settings.MEDIA_ENGINE_BASE_URL:
        def repair_with_media_engine(widget_block: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
            """Fix charts using MediaEngine's LLM"""
            try:
                from ReportEngine.llms import LLMClient

                client = LLMClient(
                    api_key=settings.MEDIA_ENGINE_API_KEY,
                    base_url=settings.MEDIA_ENGINE_BASE_URL,
                    model_name=settings.MEDIA_ENGINE_MODEL_NAME or "gpt-4",
                )

                prompt = build_chart_repair_prompt(widget_block, errors)
                response = client.invoke(
                    CHART_REPAIR_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.0,
                    top_p=0.05
                )

                if not response:
                    return None

                repaired = json.loads(response)
                return repaired

            except Exception as e:
                logger.exception(f"MediaEngine chart repair failed: {e}")
                return None

        repair_functions.append(repair_with_media_engine)
        logger.debug("MediaEngine chart repair function added")

    if not repair_functions:
        logger.warning("No Engine API is configured, chart API fix functionality will not be available")
    else:
        logger.info(f"The chart API repair function has been enabled, and a total of {len(repair_functions)} Engines are available.")

    return repair_functions


def create_table_repair_functions() -> List:
    """Create a tabular LLM repair function list.

    Use the same Engine configuration as the chart fix.

    Returns:
        List[Callable]: Repair function list"""
    repair_functions = []

    # Fix the table using ReportEngine
    if settings.REPORT_ENGINE_API_KEY and settings.REPORT_ENGINE_BASE_URL:
        def repair_table_with_report_engine(table_block: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
            """Repair tables using ReportEngine's LLM"""
            try:
                from ReportEngine.llms import LLMClient

                client = LLMClient(
                    api_key=settings.REPORT_ENGINE_API_KEY,
                    base_url=settings.REPORT_ENGINE_BASE_URL,
                    model_name=settings.REPORT_ENGINE_MODEL_NAME or "gpt-4",
                )

                prompt = build_table_repair_prompt(table_block, errors)
                response = client.invoke(
                    TABLE_REPAIR_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.0,
                    top_p=0.05
                )

                if not response:
                    return None

                # Parse response
                repaired = json.loads(response)
                return repaired

            except Exception as e:
                logger.exception(f"ReportEngine table repair failed: {e}")
                return None

        repair_functions.append(repair_table_with_report_engine)
        logger.debug("ReportEngine table repair function added")

    if not repair_functions:
        logger.warning("No Engine API is configured, table API fixes will not be available")
    else:
        logger.info(f"Tables API repair functions are enabled, {len(repair_functions)} Engines available")

    return repair_functions


def create_wordcloud_repair_functions() -> List:
    """Create a word cloud list of LLM repair functions.

    Use the same Engine configuration as the chart fix.

    Returns:
        List[Callable]: Repair function list"""
    repair_functions = []

    # Fix word cloud using ReportEngine
    if settings.REPORT_ENGINE_API_KEY and settings.REPORT_ENGINE_BASE_URL:
        def repair_wordcloud_with_report_engine(widget_block: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
            """Fix word cloud using ReportEngine's LLM"""
            try:
                from ReportEngine.llms import LLMClient

                client = LLMClient(
                    api_key=settings.REPORT_ENGINE_API_KEY,
                    base_url=settings.REPORT_ENGINE_BASE_URL,
                    model_name=settings.REPORT_ENGINE_MODEL_NAME or "gpt-4",
                )

                prompt = build_wordcloud_repair_prompt(widget_block, errors)
                response = client.invoke(
                    WORDCLOUD_REPAIR_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.0,
                    top_p=0.05
                )

                if not response:
                    return None

                # Parse response
                repaired = json.loads(response)
                return repaired

            except Exception as e:
                logger.exception(f"ReportEngine word cloud repair failed: {e}")
                return None

        repair_functions.append(repair_wordcloud_with_report_engine)
        logger.debug("ReportEngine word cloud repair function added")

    if not repair_functions:
        logger.warning("No Engine API is configured, word cloud API fix functionality will not be available")
    else:
        logger.info(f"Word cloud API repair function is enabled, a total of {len(repair_functions)} Engines are available")

    return repair_functions
