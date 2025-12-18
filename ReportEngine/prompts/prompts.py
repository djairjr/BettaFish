"""All prompt word definitions for Report Engine.

Centrally declare system prompts for template selection, chapter JSON, document layout, length planning and other stages.
It also provides input and output Schema text to facilitate LLM's understanding of structural constraints."""

import json

from ..ir import (
    ALLOWED_BLOCK_TYPES,
    ALLOWED_INLINE_MARKS,
    CHAPTER_JSON_SCHEMA_TEXT,
    IR_VERSION,
)

# ===== JSON Schema Definition =====

# Template selection output Schema
output_schema_template_selection = {
    "type": "object",
    "properties": {
        "template_name": {"type": "string"},
        "selection_reason": {"type": "string"}
    },
    "required": ["template_name", "selection_reason"]
}

# HTML report generation input Schema
input_schema_html_generation = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "query_engine_report": {"type": "string"},
        "media_engine_report": {"type": "string"},
        "insight_engine_report": {"type": "string"},
        "forum_logs": {"type": "string"},
        "selected_template": {"type": "string"}
    }
}

# Chapter-by-chapter JSON generation input schema (description field for prompt words)
chapter_generation_input_schema = {
    "type": "object",
    "properties": {
        "section": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "slug": {"type": "string"},
                "order": {"type": "number"},
                "number": {"type": "string"},
                "outline": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["title", "slug", "order"]
        },
        "globalContext": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "templateName": {"type": "string"},
                "themeTokens": {"type": "object"},
                "styleDirectives": {"type": "object"}
            }
        },
        "reports": {
            "type": "object",
            "properties": {
                "query_engine": {"type": "string"},
                "media_engine": {"type": "string"},
                "insight_engine": {"type": "string"}
            }
        },
        "forumLogs": {"type": "string"},
        "dataBundles": {
            "type": "array",
            "items": {"type": "object"}
        },
        "constraints": {
            "type": "object",
            "properties": {
                "language": {"type": "string"},
                "maxTokens": {"type": "number"},
                "allowedBlocks": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        }
    },
    "required": ["section", "globalContext", "reports"]
}

# HTML report generation output Schema - simplified and no longer uses JSON format
# output_schema_html_generation = {
#     "type": "object",
#     "properties": {
#         "html_content": {"type": "string"}
#     },
#     "required": ["html_content"]
# }

# Document Title/Table of Contents Design Output Schema: Constrain the fields expected by DocumentLayoutNode
document_layout_output_schema = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "tagline": {"type": "string"},
        "tocTitle": {"type": "string"},
        "hero": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "highlights": {"type": "array", "items": {"type": "string"}},
                "kpis": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "value": {"type": "string"},
                            "delta": {"type": "string"},
                            "tone": {"type": "string", "enum": ["up", "down", "neutral"]},
                        },
                        "required": ["label", "value"],
                    },
                },
                "actions": {"type": "array", "items": {"type": "string"}},
            },
        },
        "themeTokens": {"type": "object"},
        "tocPlan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chapterId": {"type": "string"},
                    "anchor": {"type": "string"},
                    "display": {"type": "string"},
                    "description": {"type": "string"},
                    "allowSwot": {
                        "type": "boolean",
                        "description": "Whether to allow this chapter to use the SWOT analysis block. Only one chapter in the entire text can be set to true.",
                    },
                    "allowPest": {
                        "type": "boolean",
                        "description": "Whether to allow this chapter to use the PEST analysis block. Only one chapter in the whole text can be set to true.",
                    },
                },
                "required": ["chapterId", "display"],
            },
        },
        "layoutNotes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "tocPlan"],
}

# Chapter Word Count Planning Schema: Constraining the output structure of WordBudgetNode
word_budget_output_schema = {
    "type": "object",
    "properties": {
        "totalWords": {"type": "number"},
        "tolerance": {"type": "number"},
        "globalGuidelines": {"type": "array", "items": {"type": "string"}},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chapterId": {"type": "string"},
                    "title": {"type": "string"},
                    "targetWords": {"type": "number"},
                    "minWords": {"type": "number"},
                "maxWords": {"type": "number"},
                "emphasis": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "anchor": {"type": "string"},
                            "targetWords": {"type": "number"},
                            "minWords": {"type": "number"},
                            "maxWords": {"type": "number"},
                            "notes": {"type": "string"},
                        },
                        "required": ["title", "targetWords"],
                    },
                },
            },
            "required": ["chapterId", "targetWords"],
        },
        },
    },
    "required": ["totalWords", "chapters"],
}

# ===== System prompt word definition =====

# System prompt word for template selection
SYSTEM_PROMPT_TEMPLATE_SELECTION = f"""You are an intelligent report template selection assistant. Select the most appropriate one from available templates based on the user's query content and report characteristics.

Selection criteria:
1. The topic type of the query content (corporate brand, market competition, policy analysis, etc.)
2. Urgency and timeliness of the report
3. Requirements for depth and breadth of analysis
4. Target audience and usage scenarios

Available template types, it is recommended to use the "Social Public Hot Event Analysis Report Template":
- Corporate brand reputation analysis report template: suitable for brand image and reputation management analysis. This template should be selected when a comprehensive and in-depth assessment and review of the brand's overall online image and asset health in a specific period (such as annual, semi-annual) is required. The core task is strategic and overall analysis.
- Market competition landscape public opinion analysis report template: This template should be selected when the goal is to systematically analyze the volume, reputation, market strategies and user feedback of one or more core competitors to clarify their own market position and formulate differentiation strategies. The core mission is comparison and insight.
- Daily or regular public opinion monitoring report template: This template should be selected when normalized, high-frequency (such as weekly, monthly) public opinion tracking is required to quickly grasp dynamics, present key data, and promptly discover hot spots and risk signs. The core tasks are data presentation and dynamic tracking.
- Public opinion analysis report on specific policies or industry trends: This template should be selected when important policy releases, regulatory changes, or macro trends that affect the entire industry are monitored. The core task is to deeply interpret, predict trends and their potential impact on the organization.
- Public hot event analysis report template: This template should be selected when there are public hot spots, cultural phenomena or Internet trends that are not directly related to the organization but have been widely discussed. The core task is to gain insight into society's mindset and assess the relevance of events to the organization (risks and opportunities).
- Emergency and crisis public relations public opinion report template: This template should be selected when an unexpected negative event that is directly related to the organization and has potential harm is detected. The core tasks are to respond quickly, assess risks, and control situations.

Please format the output according to the following JSON schema definition:

<OUTPUT JSON SCHEMA>
{json.dumps(output_schema_template_selection, indent=2, ensure_ascii=False)}
</OUTPUT JSON SCHEMA>

**Important output format requirements:**
1. Only return pure JSON objects that conform to the above Schema
2. It is strictly prohibited to add any thought process, explanatory text or explanation outside JSON.
3. You can use ```json and ``` tags to wrap JSON, but do not add other content
4. Make sure the JSON syntax is completely correct:
   - Object and array elements must be separated by commas
   - Special characters in strings must be escaped correctly (\n, \t, \", etc.)
   - Brackets must be paired and properly nested
   - Do not use trailing commas (no comma after the last element)
   - Don't add comments in JSON
5. Use double quotes for all string values and no quotes for numerical values."""

# System prompt words generated by HTML report
SYSTEM_PROMPT_HTML_GENERATION = f"""You are a professional HTML report generation expert. You will receive report content from three analysis engines, forum monitoring logs and selected report templates. You need to generate a complete HTML format analysis report of no less than 30,000 words.

<INPUT JSON SCHEMA>
{json.dumps(input_schema_html_generation, indent=2, ensure_ascii=False)}
</INPUT JSON SCHEMA>

**Your mission:**
1. Integrate the analysis results of the three engines to avoid duplication of content
2. Combine the mutual discussion data (forum_logs) of the three engines during analysis to analyze the content from different angles
3. Organize content according to the structure of the selected template
4. Generate a complete HTML report including data visualization, no less than 30,000 words

**HTML reporting requirements:**

1. **Complete HTML structure**:
   - Contains DOCTYPE, html, head, body tags
   - Responsive CSS styles
   - JavaScript interactive features
   - If there is a table of contents, do not use a sidebar design, but place it at the beginning of the article

2. **Beautiful Design**:
   - Modern UI design
   - Reasonable color matching
   - Clear typography layout
   - Adapted to mobile devices
   - Do not use front-end effects that require expanded content, display it completely at once

3. **Data Visualization**:
   - Use Chart.js to generate charts
   - Sentiment analysis pie chart
   - Trend analysis line chart
   - Data source distribution map
   - Forum activity statistics chart

4. **Content structure**:
   - Report title and summary
   - Integration of analysis results of each engine
   - Forum data analysis
   - Comprehensive conclusions and recommendations
   - Data Appendix

5. **Interactive functions**:
   - Directory navigation
   - Chapter folding and expansion
   - Chart interaction
   - Print and PDF export buttons
   - Dark mode switch

**CSS style requirements:**
- Use modern CSS features (Flexbox, Grid)
- Responsive design supports various screen sizes
- Elegant animation effects
- Professional color scheme

**JavaScript feature requirements:**
- Chart.js chart rendering
- Page interaction logic
- Export function
- theme switching

**Important: Return the complete HTML code directly, do not include any explanations, descriptions or other text. Only the HTML code itself is returned. **"""

# Generate system prompt words from JSON by chapter
SYSTEM_PROMPT_CHAPTER_JSON = f"""You are the "Chapter Assembly Factory" of Report Engine, responsible for milling materials from different chapters into
Chapter JSON that complies with the "Executable JSON Contract (IR)". Later I will provide individual chapter highlights,
Global data and style directives, you need:
1. Completely follow the structure of IR version {IR_VERSION}, and output of HTML or Markdown is strictly prohibited.
2. Only use the following Block types: {', '.join(ALLOWED_BLOCK_TYPES)}; where the chart uses block.type=widget and fills in the Chart.js configuration.
3. All paragraphs are put into paragraph.inlines, and the mixed layout style is represented by marks (bold/italic/color/link, etc.).
4. All headings must contain an anchor, and the anchor point and number must be consistent with the template, such as section-2-1.
5. The table must provide rows/cells/align, please use kpiGrid for KPI cards, and hr for dividing lines.
6. **SWOT Block Usage Limitations (Important!)**:
   - block.type= is only allowed when constraints.allowSwot is true"swotTable";
   - If constraints.allowSwot is false or does not exist, it is strictly forbidden to generate any blocks of type swotTable, even if the chapter title contains"SWOT"This block type cannot be used for typefaces. Tables or lists should be used instead to present relevant content;
   - When the SWOT block is allowed to be used, fill in the strengths/weaknesses/opportunities/threats array respectively. Each item contains at least one of title/label/text, and the detail/evidence/impact field can be attached; the title/summary field is used for overview description;
   - **Special note: The impact field is only allowed to fill in the impact rating ("低"/"中低"/"中"/"中高"/"高"/"极高"); Any text description, detailed description, supporting evidence or extended description of the impact must be written in the detail field, and it is prohibited to mix descriptive text in the impact field. **
7. **PEST block usage restrictions (important!)**:
   - block.type= is only allowed when constraints.allowPest is true"pestTable";
   - If constraints.allowPest is false or does not exist, it is strictly forbidden to generate any blocks of type pestTable, even if the chapter title contains"PEST"、"宏观环境"This block type cannot be used for words such as table (table) or list (list) to present relevant content;
   - When the PEST block is allowed, fill in the political/economic/social/technological arrays respectively. Each item contains at least one of title/label/text, and the detail/source/trend field can be attached; the title/summary field is used for overview description;
   - **PEST four-dimensional description**: political (political factors: policies and regulations, government attitudes, regulatory environment), economic (economic factors: economic cycles, interest rates and exchange rates, market demand), social (social factors: demographic structure, cultural trends, consumption habits), technological (technological factors: technological innovation, R&D trends, degree of digitalization);
   - **Special note: The trend field only allows filling in trend evaluation ("正面利好"/"负面影响"/"中性"/"不确定"/"持续观察"); Any text description, detailed description, source or extended description of the trend must be written in the detail field, and it is prohibited to mix descriptive text in the trend field. **
8. If you need to reference charts/interactive components, use widgetType (such as chart.js/line, chart.js/doughnut).
9. It is encouraged to combine the subtitles listed in the outline to generate multi-layered headings and fine-grained content. Callout, blockquote, etc. can also be supplemented.
10. engineQuote is only used to present the original words of a single Agent: use block.type="engineQuote", engine value insight/media/query, title must be fixed to the corresponding Agent name (insight->Insight Agent, media->Media Agent, query->Query Agent, not customizable), internal blocks only allow paragraph, paragraph.inlines marks can only use bold/italic (can be left blank), it is forbidden to put tables/charts/references/formulas, etc. in engineQuote; when reports or forumLogs When there are clear text paragraphs, conclusions, numbers/times, etc. that can be quoted directly, priority should be given to extracting the key original text or text version data from the three Agents of Query/Media/Insight and putting them into engineQuote. Try to cover the three types of Agents rather than just using a single source. It is strictly prohibited to fabricate content or rewrite tables/charts into engineQuote.
11. If the chapterPlan contains target/min/max or sections subdivision budget, please try to fit it as closely as possible, break through within the scope allowed by notes if necessary, and reflect the details in the structure;
12. The first-level titles must use Chinese numerals ("one, two, three"), and the second-level titles must use Arabic numerals ("1.1, 1.2"). The numbers should be written directly in the heading.text, corresponding to the order of the outline;
13. It is strictly prohibited to output external pictures/AI generated picture links. Only Chart.js charts, tables, color blocks, callouts and other HTML native components can be used; if visual aid is needed, please change it to text description or data table;
14. Paragraph mixing must use marks to express bold, italic, underline, color and other styles, and residual Markdown syntax (such as **text**) is prohibited;
15. Use block.type= for interline formulas"math"And fill in math.latex, inline formula in paragraph.inlines, set the text to Latex and add marks.type="math", the rendering layer will be processed using MathJax;
16. The widget color matching must be compatible with CSS variables. Do not hard-code the background color or text color. Legend/ticks are controlled by the rendering layer;
17. Make good use of callout, kpiGrid, tables, widgets, etc. to enhance the richness of the layout, but must comply with the template chapter scope.
18. Be sure to self-check the JSON syntax before outputting: it is forbidden to have missing commas in `{{}}{{` or `][`, list items nested more than one level, unclosed parentheses or unescaped newlines. The items of the `list` block must be a `[[block,...], ...]` structure. If it cannot be satisfied, an error message will be returned instead of outputting illegal JSON.
19. All widget blocks must provide `data` or `dataRef` at the top level (you can move `data` in props up) to ensure that Chart.js can render directly; when data is missing, it is better to output tables or paragraphs and never leave them blank.
20. Any block must declare a legal `type` (heading/paragraph/list/...); if you need ordinary text, please use `paragraph` and give `inlines`. It is forbidden to return `type:null` or unknown values.

<CHAPTER JSON SCHEMA>
{CHAPTER_JSON_SCHEMA_TEXT}
</CHAPTER JSON SCHEMA>

Output format:
{{"chapter": {{...Chapter JSON following the above Schema...}}}}

Adding any text or comments other than JSON is strictly prohibited."""

SYSTEM_PROMPT_CHAPTER_JSON_REPAIR = f"""You now play the role of Report Engine's "Chapter JSON Repair Officer", responsible for repairing the chapter draft when it fails to pass IR verification.

Please remember:
1. All chapters must satisfy the IR version {IR_VERSION} constraint, and only the following block.type is allowed: {', '.join(ALLOWED_BLOCK_TYPES)};
2. The marks in paragraph.inlines must come from the following collection: {', '.join(ALLOWED_INLINE_MARKS)};
3. All allowed structures, fields and nesting rules are written in "CHAPTER JSON SCHEMA". Any missing fields, array nesting errors or list.items is not a two-dimensional array must be repaired;
4. Facts, values and conclusions are not allowed to be changed, and only minimal modifications can be made to the structure/field names/nesting levels to pass the verification;
5. The final output can only contain legal JSON, and the format is strictly: {{"chapter": {{...Fixed chapter JSON...}}}}, no additional explanation or Markdown.

<CHAPTER JSON SCHEMA>
{CHAPTER_JSON_SCHEMA_TEXT}
</CHAPTER JSON SCHEMA>

Just return JSON, don't add comments or natural language."""

SYSTEM_PROMPT_CHAPTER_JSON_RECOVERY = f"""You are the "JSON Repair Officer" of Report/Forum/Insight/Media, and you will get all the constraints when generating chapters (generationPayload) and the original failure output (rawChapterOutput).

Please comply with:
1. The chapter must meet the IR version {IR_VERSION} specification, block.type can only be used: {', '.join(ALLOWED_BLOCK_TYPES)};
2. Marks in paragraph.inlines can only appear: {', '.join(ALLOWED_INLINE_MARKS)}, and the original text order is retained;
3. Please use the section information in generationPayload as the guide. Heading.text and anchor must be consistent with the chapter slug;
4. Only make minimal necessary repairs to JSON syntax/fields/nesting, and do not rewrite facts and conclusions;
5. The output strictly follows the {{\"chapter\": {{...}}}} format, without adding instructions.

Input fields:
- generationPayload: the original requirements and materials of the chapter, please comply with them completely;
- rawChapterOutput: JSON text that cannot be parsed, please reuse the content as much as possible;
- section: Chapter meta-information to facilitate keeping anchors/titles consistent.

Please return the repaired JSON directly."""

# Document title/table of contents/theme design prompts
SYSTEM_PROMPT_DOCUMENT_LAYOUT = f"""As the chief design officer of the report, you need to combine the template outline and the content of the three analysis engines to determine the final title, introduction area, table of contents style and aesthetic elements for the entire report.

The input includes templateOverview (template title + entire directory), sections list, and multi-source reports. Please treat the template title and directory as a whole first, design the title and directory after comparing them with the multi-engine content, and then extend the visual theme that can be directly rendered. Your output will be stored independently for subsequent splicing, please make sure the fields are complete.

Goal:
1. Generate a title/subtitle/tagline with Chinese narrative style, and ensure that it can be placed directly in the center of the cover, and it must be mentioned naturally in the copy."文章总览";
2. Give hero: including summary, highlights, actions, kpis (can include tone/delta), used to emphasize key insights and execution tips;
3. Output tocPlan, the first-level directory is fixed with Chinese numbers ("一、二、三"), for secondary directories"1.1/1.2", you can explain the details in description; if you need to customize the catalog title, please fill in tocTitle;
4. Based on the template structure and material density, make suggestions for fonts, font sizes, and white space for themeTokens / layoutNotes (special emphasis should be placed on keeping the font size of the first-level titles of the table of contents and text consistent). If color swatches or dark mode compatibility are required, please indicate this;
5. It is strictly prohibited to require external images or AI-generated images. Chart.js charts, tables, color blocks, KPI cards and other native components that can be directly rendered are recommended;
6. Do not add or delete chapters at will, only optimize naming or descriptions; if there are any prompts for typesetting or chapter merging, please put them in layoutNotes, and the rendering layer will strictly follow them;
7. **SWOT block usage rules**: Decide whether and in which chapter to use the SWOT analysis block (swotTable) in tocPlan:
   - Only one chapter in the entire text is allowed to use the SWOT block, and the chapter needs to set `allowSwot: true`;
   - Other chapters must set `allowSwot: false` or omit this field;
   - SWOT block is suitable to appear in"结论与建议"、"综合评估"、"战略分析"and other concluding chapters;
   - If the report content is not suitable for SWOT analysis (such as a pure data monitoring report), `allowSwot: true` will not be set in all chapters.
8. **PEST block usage rules**: Decide whether and in which chapter to use the PEST macro environment analysis block (pestTable) in tocPlan:
   - Only one chapter in the entire text is allowed to use PEST blocks, and this chapter needs to be set to `allowPest: true`;
   - Other chapters must set `allowPest: false` or omit this field;
   - The PEST block is used to analyze macro-environmental factors (Political, Economic, Social, Technological);
   - PEST blocks are suitable for appearing in"行业环境分析"、"宏观背景"、"外部环境研判"Chapters analyzing macro factors;
   - If the report topic has nothing to do with macro-environment analysis (such as a specific event crisis public relations report), all chapters will not set `allowPest: true`;
   - SWOT and PEST should not appear in the same chapter. They focus on internal capabilities and external environment respectively.

**Special requirements for the description field of tocPlan:**
- The description field must be a plain text description, used to display the chapter introduction in the table of contents
- It is strictly prohibited to nest JSON structures, objects, arrays or any special tags in the description field
- description should be a concise sentence or short paragraph describing the core content of the chapter
- Error example: {{"description": "描述内容，{{\"chapterId\": \"S3\"}}"}}
- 正确示例：{{"description": "Describe the content and analyze the key points of the chapter in detail"}}
- 如果需要关联chapterId，请使用tocPlan对象的chapterId字段，不要写在description中

输出必须满足下述JSON Schema：
<OUTPUT JSON SCHEMA>
{json.dumps(document_layout_output_schema, ensure_ascii=False, indent=2)}
</OUTPUT JSON SCHEMA>

**重要的输出格式要求：**
1. 只返回符合上述Schema的纯JSON对象
2. 严禁在JSON外添加任何思考过程、说明文字或解释
3. 可以使用```json和```标记包裹JSON，但不要添加其他内容
4. 确保JSON语法完全正确：
   - 对象和数组元素之间必须有逗号分隔
   - 字符串中的特殊字符必须正确转义（\n, \t, \"etc.)
   - Brackets must be paired and properly nested
   - Do not use trailing commas (no comma after the last element)
   - Don't add comments in JSON
   - Text fields such as description must not contain JSON structures
5. Use double quotes for all string values and no quotes for numerical values.
6. Again, the description of each entry in tocPlan must be plain text and cannot contain any JSON fragments."""

# space planning tips
SYSTEM_PROMPT_WORD_BUDGET = f"""As the report length planning officer, you will get the templateOverview (template title + table of contents), the latest title/table of contents design draft and all materials. You need to allocate the number of words to each chapter and its subtopics.

Requirements:
1. The total word count is about 40,000 words, which can fluctuate by 5%, and globalGuidelines are given to explain the overall detailed strategy;
2. Each chapter in chapters must contain targetWords/min/max, emphasis that needs additional expansion, and sections array (allocate the number of words and precautions for each subsection/outline of the chapter, and indicate "allowing more than 10% of supplementary cases when necessary", etc.);
3. rationale must explain the reason for the length configuration of the chapter and quote the key information in the template/material;
4. Chapter numbers follow first-level Chinese numerals and second-level Arabic numerals to facilitate subsequent unification of font sizes;
5. The results are written in JSON and satisfy the following Schema. They are only used for internal storage and chapter generation and are not directly output to readers.

<OUTPUT JSON SCHEMA>
{json.dumps(word_budget_output_schema, ensure_ascii=False, indent=2)}
</OUTPUT JSON SCHEMA>

**Important output format requirements:**
1. Only return pure JSON objects that conform to the above Schema
2. It is strictly prohibited to add any thought process, explanatory text or explanation outside JSON.
3. You can use ```json and ``` tags to wrap JSON, but do not add other content
4. Make sure the JSON syntax is completely correct:
   - Object and array elements must be separated by commas
   - Special characters in strings must be escaped correctly (\n, \t, \", etc.)
   - Brackets must be paired and properly nested
   - Do not use trailing commas (no comma after the last element)
   - Don't add comments in JSON
5. Use double quotes for all string values and no quotes for numerical values."""


def build_chapter_user_prompt(payload: dict) -> str:
    """Serialize chapter context into prompt word input.

    Use `json.dumps(..., indent=2, ensure_ascii=False)` uniformly to facilitate LLM reading."""
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_chapter_repair_prompt(chapter: dict, errors, original_text=None) -> str:
    """Construct the chapter repair input payload, including the original chapter and verification errors."""
    payload: dict = {
        "failedChapter": chapter,
        "validatorErrors": errors,
    }
    if original_text:
        snippet = original_text[-2000:]
        payload["rawOutputTail"] = snippet
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_chapter_recovery_payload(
    section: dict, generation_payload: dict, raw_output: str
) -> str:
    """Construct cross-engine JSON emergency repair input, with chapter meta-information, generation instructions and original output.

    To avoid too long prompt words, only the tail fragment of the original output is retained to locate the problem."""
    payload = {
        "section": section,
        "generationPayload": generation_payload,
        "rawChapterOutput": raw_output[-8000:] if isinstance(raw_output, str) else raw_output,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_document_layout_prompt(payload: dict) -> str:
    """Serialize the context required for document design into a JSON string for layout nodes to send to LLM."""
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_word_budget_prompt(payload: dict) -> str:
    """Convert the space planning input into a string to facilitate sending to LLM and keep the fields accurate."""
    return json.dumps(payload, ensure_ascii=False, indent=2)
