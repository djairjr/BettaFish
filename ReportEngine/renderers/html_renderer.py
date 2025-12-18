"""HTML/PDF renderer based on chapter IR, achieving consistent interaction and visual appearance with the sample report.

New points:
1. Built-in Chart.js data verification/repair (ChartValidator+LLM) to prevent injection or crash caused by illegal configuration;
2. Inline MathJax/Chart.js/html2canvas/jspdf and other dependencies with CDN fallback to adapt to offline or blocked environments;
3. Preset Base64 fonts of Siyuan Songti subset for PDF/HTML integrated export to avoid missing characters or additional system dependencies."""

from __future__ import annotations

import ast
import copy
import html
import json
import os
import re
import base64
from pathlib import Path
from typing import Any, Dict, List
from loguru import logger

from ReportEngine.ir.schema import ENGINE_AGENT_TITLES
from ReportEngine.utils.chart_validator import (
    ChartValidator,
    ChartRepairer,
    ValidationResult,
    create_chart_validator,
    create_chart_repairer
)
from ReportEngine.utils.chart_repair_api import create_llm_repair_functions
from ReportEngine.utils.chart_review_service import get_chart_review_service


class HTMLRenderer:
    """Document IR → HTML renderer.

    - Read IR metadata/chapters and map the structure to responsive HTML;
    - Dynamically construct directories, anchors, Chart.js scripts and interactive logic;
    - Provides auxiliary functions such as theme variables and number mapping."""

    # ===== Quick tour of the rendering process (easy to locate comments) =====
    # render(document_ir): Single public entry, responsible for resetting state and concatenating _render_head / _render_body.
    # _render_head: Construct <head> based on themeTokens, inject CSS variables, inline libraries and CDN fallback.
    # _render_body: Assemble the page skeleton (header/header, table of contents/toc, chapters/blocks, script injection).
    # _render_header: Generate the top button area, and the button ID and event are bound in _hydration_script.
    # _render_widget: Process the Chart.js/word cloud component, first verify and repair the data, and then write the <script type="application/json"> configuration.
    # _hydration_script: JS at the end of the output, responsible for button interaction (theme switching/printing/exporting) and chart instantiation.

    CALLOUT_ALLOWED_TYPES = {
        "paragraph",
        "list",
        "table",
        "blockquote",
        "code",
        "math",
        "figure",
        "kpiGrid",
        "swotTable",
        "pestTable",
        "engineQuote",
    }
    INLINE_ARTIFACT_KEYS = {
        "props",
        "widgetId",
        "widgetType",
        "data",
        "dataRef",
        "datasets",
        "labels",
        "config",
        "options",
    }
    TABLE_COMPLEX_CHARS = set(
        "@％%（）()，,。；;：:、？?！!·…-—_+<>[]{}|\\/\"'`~$^&*#"
    )

    def __init__(self, config: Dict[str, Any] | None = None):
        """Initializes the renderer cache and allows additional configuration to be injected.

        Parameter level description:
        - config: dict | None, for the caller to temporarily override theme/debugging switches, etc., with the highest priority;
          Typical key values:
            - themeOverride: override themeTokens in metadata;
            - enableDebug: bool, whether to output additional logs.
        Internal status:
        - self.document/metadata/chapters: Save the IR of a rendering cycle;
        - self.widget_scripts: Collect chart configuration JSON, and then inject water at the end of _render_body;
        - self._lib_cache/_pdf_font_base64: cache local libraries and fonts to avoid repeated IO;
        - self.chart_validator/chart_repairer: local and LLM repairer configured by Chart.js;
        - self.chart_validation_stats: Record the total amount/repair source/number of failures to facilitate log auditing."""
        self.config = config or {}
        self.document: Dict[str, Any] = {}
        self.widget_scripts: List[str] = []
        self.chart_counter = 0
        self.toc_entries: List[Dict[str, Any]] = []
        self.heading_counter = 0
        self.metadata: Dict[str, Any] = {}
        self.chapters: List[Dict[str, Any]] = []
        self.chapter_anchor_map: Dict[str, str] = {}
        self.heading_label_map: Dict[str, Dict[str, Any]] = {}
        self.primary_heading_index = 0
        self.secondary_heading_index = 0
        self.toc_rendered = False
        self.hero_kpi_signature: tuple | None = None
        self._current_chapter: Dict[str, Any] | None = None
        self._lib_cache: Dict[str, str] = {}
        self._pdf_font_base64: str | None = None

        # Initialize chart validator and fixer
        self.chart_validator = create_chart_validator()
        llm_repair_fns = create_llm_repair_functions()
        self.chart_repairer = create_chart_repairer(
            validator=self.chart_validator,
            llm_repair_fns=llm_repair_fns
        )
        # Print LLM repair function status
        self._llm_repair_count = len(llm_repair_fns)
        if not llm_repair_fns:
            logger.warning("HTMLRenderer: No LLM API is configured, chart API fix function is not available")
        else:
            logger.info(f"HTMLRenderer: {len(llm_repair_fns)} LLM repair functions configured")
        # Record repair failed charts to avoid triggering LLM cycle repair multiple times
        self._chart_failure_notes: Dict[str, str] = {}
        self._chart_failure_recorded: set[str] = set()

        # Statistics
        self.chart_validation_stats = {
            'total': 0,
            'valid': 0,
            'repaired_locally': 0,
            'repaired_api': 0,
            'failed': 0
        }

    @staticmethod
    def _get_lib_path() -> Path:
        """Get the directory path of the third-party library file"""
        return Path(__file__).parent / "libs"

    @staticmethod
    def _get_font_path() -> Path:
        """Returns the path to the font required for PDF export (using optimized subset fonts)"""
        return Path(__file__).parent / "assets" / "fonts" / "SourceHanSerifSC-Medium-Subset.ttf"

    def _load_lib(self, filename: str) -> str:
        """Load the contents of the specified third-party library file

        Parameters:
            filename: library file name

        Return:
            str: JavaScript code content of the library file"""
        if filename in self._lib_cache:
            return self._lib_cache[filename]

        lib_path = self._get_lib_path() / filename
        try:
            with open(lib_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self._lib_cache[filename] = content
                return content
        except FileNotFoundError:
            print(f"Warning: Library file {filename} not found, CDN alternative link will be used")
            return ""
        except Exception as e:
            print(f"Warning: Error reading library file {filename}: {e}")
            return ""

    def _load_pdf_font_data(self) -> str:
        """Load Base64 data of PDF fonts to avoid repeated reading of large files"""
        if self._pdf_font_base64 is not None:
            return self._pdf_font_base64
        font_path = self._get_font_path()
        try:
            data = font_path.read_bytes()
            self._pdf_font_base64 = base64.b64encode(data).decode("ascii")
            return self._pdf_font_base64
        except FileNotFoundError:
            logger.warning("PDF font file missing: %s", font_path)
        except Exception as exc:
            logger.warning("Failed to read PDF font file: %s (%s)", font_path, exc)
        self._pdf_font_base64 = ""
        return self._pdf_font_base64

    def _reset_chart_validation_stats(self) -> None:
        """Reset chart validation statistics and clear failure count flags"""
        self.chart_validation_stats = {
            'total': 0,
            'valid': 0,
            'repaired_locally': 0,
            'repaired_api': 0,
            'failed': 0
        }
        # Keep the failure reason cache, but reset the count for this rendering
        self._chart_failure_recorded = set()

    def _build_script_with_fallback(
        self,
        inline_code: str,
        cdn_url: str,
        check_expression: str,
        lib_name: str,
        is_defer: bool = False
    ) -> str:
        """Build script tags with CDN fallback mechanism

        Strategy:
        1. Prioritize embedding local library code
        2. Add a detection script to verify whether the library is loaded successfully
        3. If the detection fails, dynamically load the CDN version as a backup

        Parameters:
            inline_code: JavaScript code content of the native library
            cdn_url: CDN alternative link
            check_expression: JavaScript expression, used to detect whether the library is loaded successfully
            lib_name: library name (for log output)
            is_defer: whether to use the defer attribute

        Return:
            str: complete script tag HTML"""
        defer_attr = ' defer' if is_defer else ''

        if inline_code:
            # Embed native library code and add fallback detection
            return f"""<script{defer_attr}>
    // {lib_name} - embedded version
    try {{
      {inline_code}
    }} catch (e) {{
      console.error('{lib_name}embedded loading failed:', e);
    }}
  </script>
  <script{defer_attr}>
    // {lib_name} - CDN Fallback detection
    (function() {{
      var checkLib = function() {{
        if (!({check_expression})) {{
          console.warn('{lib_name} local version failed to load, loading alternate version from CDN...');
          var script = document.createElement('script');
          script.src = '{cdn_url}';
          script.onerror = function() {{
            console.error('{lib_name} CDN alternative loading also failed');
          }};
          script.onload = function() {{
            console.log('{lib_name} CDN alternative version loaded successfully');
          }};
          document.head.appendChild(script);
        }}
      }};

      // Delay detection to ensure that the embedded code has time to execute
      if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', function() {{
          setTimeout(checkLib, 100);
        }});
      }} else {{
        setTimeout(checkLib, 100);
      }}
    }})();
  </script>""".strip()
        else:
            # Failed to read local files, use CDN directly
            logger.warning(f"The {lib_name} local file was not found or failed to be read. CDN will be used directly.")
            return f'  <script{defer_attr} src="{cdn_url}"></script>'

    # ====== Public entrance ======

    def render(
        self,
        document_ir: Dict[str, Any],
        ir_file_path: str | None = None
    ) -> str:
        """Receive Document IR, reset internal state and output full HTML.

        Parameters:
            document_ir: The entire report data generated by DocumentComposer.
            ir_file_path: Optional, IR file path, it will be automatically saved after repair when provided.

        Return:
            str: A complete HTML document that can be written directly to disk."""
        self.document = document_ir or {}

        # Chart review and repair using unified ChartReviewService
        # The repair results will be written directly back to document_ir to avoid repeated repairs after multiple renderings.
        # review_document returns the statistics of this session (thread-safe)
        chart_service = get_chart_review_service()
        review_stats = chart_service.review_document(
            self.document,
            ir_file_path=ir_file_path,
            reset_stats=True,
            save_on_repair=bool(ir_file_path)
        )
        # Synchronize statistics to local (for compatibility with old _log_chart_validation_stats)
        # Use the returned ReviewStats object instead of the shared chart_service.stats
        self.chart_validation_stats.update(review_stats.to_dict())

        self.widget_scripts = []
        self.chart_counter = 0
        self.heading_counter = 0
        self.metadata = self.document.get("metadata", {}) or {}
        raw_chapters = self.document.get("chapters", []) or []
        self.toc_rendered = False
        self.chapters = self._prepare_chapters(raw_chapters)
        self.chapter_anchor_map = {
            chapter.get("chapterId"): chapter.get("anchor")
            for chapter in self.chapters
            if chapter.get("chapterId") and chapter.get("anchor")
        }
        self.heading_label_map = self._compute_heading_labels(self.chapters)
        self.toc_entries = self._collect_toc_entries(self.chapters)

        metadata = self.metadata
        theme_tokens = metadata.get("themeTokens") or self.document.get("themeTokens", {})
        title = metadata.get("title") or metadata.get("query") or "Intelligent public opinion report"
        hero_kpis = (metadata.get("hero") or {}).get("kpis")
        self.hero_kpi_signature = self._kpi_signature_from_items(hero_kpis)

        head = self._render_head(title, theme_tokens)
        body = self._render_body()

        # Output chart validation statistics
        self._log_chart_validation_stats()

        return f"<!DOCTYPE html>\n<html lang=\"zh-CN\" class=\"no-js\">\n{head}\n{body}\n</html>"

    # ====== Header/Text ======

    def _resolve_color_value(self, value: Any, fallback: str) -> str:
        """Extract string value from color token"""
        if isinstance(value, str):
            value = value.strip()
            return value or fallback
        if isinstance(value, dict):
            for key in ("main", "value", "color", "base", "default"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            for candidate in value.values():
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        return fallback

    def _resolve_color_family(self, value: Any, fallback: Dict[str, str]) -> Dict[str, str]:
        """Parse the main/light/dark colors, and fall back to the default value if missing"""
        result = {
            "main": fallback.get("main", "#007bff"),
            "light": fallback.get("light", fallback.get("main", "#007bff")),
            "dark": fallback.get("dark", fallback.get("main", "#007bff")),
        }
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                result["main"] = stripped
            return result
        if isinstance(value, dict):
            result["main"] = self._resolve_color_value(value.get("main") or value, result["main"])
            result["light"] = self._resolve_color_value(value.get("light") or value.get("lighter"), result["light"])
            result["dark"] = self._resolve_color_value(value.get("dark") or value.get("darker"), result["dark"])
        return result

    def _render_head(self, title: str, theme_tokens: Dict[str, Any]) -> str:
        """Render the <head> section, loading the theme CSS and necessary script dependencies.

        Parameters:
            title: The content of the page title tag.
            theme_tokens: theme variables, used to inject CSS. Support levels:
              - colors: {primary/secondary/bg/text/card/border/...}
              - typography: {fontFamily, fonts:{body,heading}}, fall back to system font when body/heading is empty
              - spacing: {container,gutter/pagePadding}

        Return:
            str: head fragment HTML."""
        css = self._build_css(theme_tokens)

        # Load third-party libraries
        chartjs = self._load_lib("chart.js")
        chartjs_sankey = self._load_lib("chartjs-chart-sankey.js")
        html2canvas = self._load_lib("html2canvas.min.js")
        jspdf = self._load_lib("jspdf.umd.min.js")
        mathjax = self._load_lib("mathjax.js")
        wordcloud2 = self._load_lib("wordcloud2.min.js")

        # Generate embedded script tags and add CDN fallback mechanism for each library
        # Chart.js - The main charting library
        chartjs_tag = self._build_script_with_fallback(
            inline_code=chartjs,
            cdn_url="https://cdn.jsdelivr.net/npm/chart.js",
            check_expression="typeof Chart !== 'undefined'",
            lib_name="Chart.js"
        )

        # Chart.js Sankey plugin
        sankey_tag = self._build_script_with_fallback(
            inline_code=chartjs_sankey,
            cdn_url="https://cdn.jsdelivr.net/npm/chartjs-chart-sankey@4",
            check_expression="typeof Chart !== 'undefined' && Chart.controllers && Chart.controllers.sankey",
            lib_name="chartjs-chart-sankey"
        )

        # wordcloud2 – word cloud rendering
        wordcloud_tag = self._build_script_with_fallback(
            inline_code=wordcloud2,
            cdn_url="https://cdnjs.cloudflare.com/ajax/libs/wordcloud2.js/1.2.2/wordcloud2.min.js",
            check_expression="typeof WordCloud !== 'undefined'",
            lib_name="wordcloud2"
        )

        # html2canvas - for screenshots
        html2canvas_tag = self._build_script_with_fallback(
            inline_code=html2canvas,
            cdn_url="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js",
            check_expression="typeof html2canvas !== 'undefined'",
            lib_name="html2canvas"
        )

        # jsPDF - for PDF export
        jspdf_tag = self._build_script_with_fallback(
            inline_code=jspdf,
            cdn_url="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js",
            check_expression="typeof jspdf !== 'undefined'",
            lib_name="jsPDF"
        )

        # MathJax - Mathematical formula rendering
        mathjax_tag = self._build_script_with_fallback(
            inline_code=mathjax,
            cdn_url="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js",
            check_expression="typeof MathJax !== 'undefined'",
            lib_name="MathJax",
            is_defer=True
        )

        # PDF font data is no longer embedded in HTML, reducing file size
        pdf_font_script = ""

        return f"""
<head>
  <meta charset="utf-8" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{self._escape_html(title)}</title>
  {chartjs_tag}
  {sankey_tag}
  {wordcloud_tag}
  {html2canvas_tag}
  {jspdf_tag}
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$','$$'], ['\\\\[','\\\\]']]
      }},
      options: {{
        skipHtmlTags: ['script','noscript','style','textarea','pre','code'],
        processEscapes: true
      }}
    }};
  </script>
  {mathjax_tag}
  {pdf_font_script}
  <style>
{css}
  </style>
  <script>
    document.documentElement.classList.remove('no-js');
    document.documentElement.classList.add('js-ready');
  </script>
</head>""".strip()

    def _render_body(self) -> str:
        """Assemble the <body> structure, including header, navigation, chapters and scripts.
        New version: Remove the independent cover section and merge the titles into the hero section.

        Return:
            str: body fragment HTML."""
        header = self._render_header()
        # cover = self._render_cover() # No longer render cover separately
        hero = self._render_hero()
        toc_section = self._render_toc_section()
        chapters = "".join(self._render_chapter(chapter) for chapter in self.chapters)
        widget_scripts = "\n".join(self.widget_scripts)
        hydration = self._hydration_script()
        overlay = """
<div id="export-overlay" class="export-overlay no-print" aria-hidden="true">
  <div class="export-dialog" role="status" aria-live="assertive">
    <div class="export-spinner" aria-hidden="true"></div>
    <p class="export-status">Exporting PDF, please wait...</p>
    <div class="export-progress" role="progressbar" aria-valuetext="正在导出">
      <div class="export-progress-bar"></div>
    </div>
  </div>
</div>
""".strip()

        return f"""
<body>
{header}
{overlay}
<main>
{hero}
{toc_section}
{chapters}
</main>
{widget_scripts}
{hydration}
</body>""".strip()

    # ====== Header / Meta Information / Table of Contents ======

    def _render_header(self) -> str:
        """Render the ceiling header, including title, subtitle and function buttons.

        Button/control description (ID is used to bind events in _hydration_script):
        - <theme-button id="theme-toggle" value="light" size="1.5">: Custom Web Component,
          `value` initial theme (light/dark), `size` controls the overall zoom; pass detail: 'light'/'dark' when triggering the `change` event.
        - <button id="print-btn">: After clicking window.print(), used for export/printing.
        - <button id="export-btn">: Hidden PDF export button, bound to exportPdf() when displayed.
          Displayed only when the dependency is ready or the business layer is open for export.

        Return:
            str: header HTML."""
        metadata = self.metadata
        title = metadata.get("title") or "Intelligent public opinion analysis report"
        subtitle = metadata.get("subtitle") or metadata.get("templateName") or "Automatically generated"
        return f"""
<header class="report-header no-print">
  <div>
    <h1>{self._escape_html(title)}</h1>
    <p class="subtitle">{self._escape_html(subtitle)}</p>
    {self._render_tagline()}
  </div>
  <div class="header-actions">
    <!-- Old version of day and night mode switch button (Web Component style):
    <theme-button value="light" id="theme-toggle" size="1.5"></theme-button>
    -->
    <button id="theme-toggle-btn" class="action-btn theme-toggle-btn" type="button">
      <svg class="btn-icon sun-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="5"></circle>
        <line x1="12" y1="1" x2="12" y2="3"></line>
        <line x1="12" y1="21" x2="12" y2="23"></line>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
        <line x1="1" y1="12" x2="3" y2="12"></line>
        <line x1="21" y1="12" x2="23" y2="12"></line>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
      </svg>
      <svg class="btn-icon moon-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: none;">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
      </svg>
      <span class="theme-label">Switch mode</span>
    </button>
    <button id="print-btn" class="action-btn print-btn" type="button">
      <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6 9 6 2 18 2 18 9"></polyline>
        <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
        <rect x="6" y="14" width="12" height="8"></rect>
      </svg>
      <span>Print page</span>
    </button>
    <button id="export-btn" class="action-btn" type="button" style="display: none;">⬇️ Export PDF</button>
  </div>
</header>""".strip()

    def _render_tagline(self) -> str:
        """Render the slogan below the title, or return an empty string if there is no slogan.

        Return:
            str: tagline HTML or empty string."""
        tagline = self.metadata.get("tagline")
        if not tagline:
            return ""
        return f'<p class="tagline">{self._escape_html(tagline)}</p>'

    def _render_cover(self) -> str:
        """In the cover area at the beginning of the article, the title and "Article Overview" prompt are displayed in the center.

        Return:
            str: cover section HTML."""
        title = self.metadata.get("title") or "Intelligent public opinion report"
        subtitle = self.metadata.get("subtitle") or self.metadata.get("templateName") or ""
        overview_hint = "Article overview"
        return f"""
<section class="cover">
  <p class="cover-hint">{overview_hint}</p>
  <h1>{self._escape_html(title)}</h1>
  <p class="cover-subtitle">{self._escape_html(subtitle)}</p>
</section>
""".strip()

    def _render_hero(self) -> str:
        """Output the summary/KPI/highlight area based on the hero field in the layout.
        New version: Merge title and overview together, remove elliptical background.

        Return:
            str: hero area HTML, if there is no data, it is an empty string."""
        hero = self.metadata.get("hero") or {}
        if not hero:
            return ""

        # Get title and subtitle
        title = self.metadata.get("title") or "Intelligent public opinion report"
        subtitle = self.metadata.get("subtitle") or self.metadata.get("templateName") or ""

        summary = hero.get("summary")
        summary_html = f'<p class="hero-summary">{self._escape_html(summary)}</p>' if summary else ""
        highlights = hero.get("highlights") or []
        highlight_html = "".join(
            f'<li><span class="badge">{self._escape_html(text)}</span></li>'
            for text in highlights
        )
        actions = hero.get("actions") or []
        actions_html = "".join(
            f'<button class="ghost-btn" type="button">{self._escape_html(text)}</button>'
            for text in actions
        )
        kpi_cards = ""
        for item in hero.get("kpis", []):
            delta = item.get("delta")
            tone = item.get("tone") or "neutral"
            delta_html = f'<span class="delta {tone}">{self._escape_html(delta)}</span>' if delta else ""
            kpi_cards += f"""
            <div class="hero-kpi">
                <div class="label">{self._escape_html(item.get("label"))}</div>
                <div class="value">{self._escape_html(item.get("value"))}</div>
                {delta_html}
            </div>
            """

        return f"""
<section class="hero-section-combined">
  <div class="hero-header">
    <p class="hero-hint">Article overview</p>
    <h1 class="hero-title">{self._escape_html(title)}</h1>
    <p class="hero-subtitle">{self._escape_html(subtitle)}</p>
  </div>
  <div class="hero-body">
    <div class="hero-content">
      {summary_html}
      <ul class="hero-highlights">{highlight_html}</ul>
      <div class="hero-actions">{actions_html}</div>
    </div>
    <div class="hero-side">
      {kpi_cards}
    </div>
  </div>
</section>
""".strip()

    def _render_meta_panel(self) -> str:
        """The current requirement does not display meta-information, and the method is retained for subsequent expansion."""
        return ""

    def _render_toc_section(self) -> str:
        """Generate a directory module, and return an empty string if there is no directory data.

        Return:
            str: toc HTML structure."""
        if not self.toc_entries:
            return ""
        if self.toc_rendered:
            return ""
        toc_config = self.metadata.get("toc") or {}
        toc_title = toc_config.get("title") or "📚 Table of Contents"
        toc_items = "".join(
            self._format_toc_entry(entry)
            for entry in self.toc_entries
        )
        self.toc_rendered = True
        return f"""
<nav class="toc">
  <div class="toc-title">{self._escape_html(toc_title)}</div>
  <ul>
    {toc_items}
  </ul>
</nav>
""".strip()

    def _collect_toc_entries(self, chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collect table of contents items based on tocPlan or chapter heading in metadata.

        Parameters:
            chapters: Array of chapters in Document IR.

        Return:
            list[dict]: Normalized directory entry, including level/text/anchor/description."""
        metadata = self.metadata
        toc_config = metadata.get("toc") or {}
        custom_entries = toc_config.get("customEntries")
        entries: List[Dict[str, Any]] = []

        if custom_entries:
            for entry in custom_entries:
                anchor = entry.get("anchor") or self.chapter_anchor_map.get(entry.get("chapterId"))

                # Verify whether anchor is valid
                if not anchor:
                    logger.warning(
                        f"Directory entry '{entry.get('display') or entry.get('title')}'"
                        f"Missing valid anchor, skipped"
                    )
                    continue

                # Verify whether the anchor is in chapter_anchor_map or in the blocks of chapters
                anchor_valid = self._validate_toc_anchor(anchor, chapters)
                if not anchor_valid:
                    logger.warning(
                        f"Directory entry '{entry.get('display') or entry.get('title')}'"
                        f"The corresponding chapter of anchor '{anchor}' was not found in the document."
                    )

                # Clean up description text
                description = entry.get("description")
                if description:
                    description = self._clean_text_from_json_artifacts(description)

                entries.append(
                    {
                        "level": entry.get("level", 2),
                        "text": entry.get("display") or entry.get("title") or "",
                        "anchor": anchor,
                        "description": description,
                    }
                )
            return entries

        for chapter in chapters or []:
            for block in chapter.get("blocks", []):
                if block.get("type") == "heading":
                    anchor = block.get("anchor") or chapter.get("anchor") or ""
                    if not anchor:
                        continue
                    mapped = self.heading_label_map.get(anchor, {})
                    # Clean up description text
                    description = mapped.get("description")
                    if description:
                        description = self._clean_text_from_json_artifacts(description)
                    entries.append(
                        {
                            "level": block.get("level", 2),
                            "text": mapped.get("display") or block.get("text", ""),
                            "anchor": anchor,
                            "description": description,
                        }
                    )
        return entries

    def _validate_toc_anchor(self, anchor: str, chapters: List[Dict[str, Any]]) -> bool:
        """Verify whether the table of contents anchor has a corresponding chapter or heading in the document.

        Parameters:
            anchor: anchor that needs to be verified
            chapters: array of chapters in Document IR

        Return:
            bool: whether anchor is valid"""
        # Check if it is a chapter anchor
        if anchor in self.chapter_anchor_map.values():
            return True

        # Check if it is in heading_label_map
        if anchor in self.heading_label_map:
            return True

        # Check whether there is this anchor in the blocks of the chapter
        for chapter in chapters or []:
            chapter_anchor = chapter.get("anchor")
            if chapter_anchor == anchor:
                return True

            for block in chapter.get("blocks", []):
                block_anchor = block.get("anchor")
                if block_anchor == anchor:
                    return True

        return False

    def _prepare_chapters(self, chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Copy the chapter and expand the serialized blocks in it to avoid missing rendering"""
        prepared: List[Dict[str, Any]] = []
        for chapter in chapters or []:
            chapter_copy = copy.deepcopy(chapter)
            chapter_copy["blocks"] = self._expand_blocks_in_place(chapter_copy.get("blocks", []))
            prepared.append(chapter_copy)
        return prepared

    def _expand_blocks_in_place(self, blocks: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
        """Traverse the block list and disassemble the embedded JSON string into independent blocks"""
        expanded: List[Dict[str, Any]] = []
        for block in blocks or []:
            extras = self._extract_embedded_blocks(block)
            expanded.append(block)
            if extras:
                expanded.extend(self._expand_blocks_in_place(extras))
        return expanded

    def _extract_embedded_blocks(self, block: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find the block list that is mistakenly written as a string inside the block and return the supplementary block"""
        extracted: List[Dict[str, Any]] = []

        def traverse(node: Any) -> None:
            """Recursively traverse the block tree to identify potential nested block JSON within the text field"""
            if isinstance(node, dict):
                for key, value in list(node.items()):
                    if key == "text" and isinstance(value, str):
                        decoded = self._decode_embedded_block_payload(value)
                        if decoded:
                            node[key] = ""
                            extracted.extend(decoded)
                        continue
                    traverse(value)
            elif isinstance(node, list):
                for item in node:
                    traverse(item)

        traverse(block)
        return extracted

    def _decode_embedded_block_payload(self, raw: str) -> List[Dict[str, Any]] | None:
        """Restore the block description in string form to a structured list."""
        if not isinstance(raw, str):
            return None
        stripped = raw.strip()
        if not stripped or stripped[0] not in "{[":
            return None
        payload: Any | None = None
        decode_targets = [stripped]
        if stripped and stripped[0] != "[":
            decode_targets.append(f"[{stripped}]")
        for candidate in decode_targets:
            try:
                payload = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
        if payload is None:
            for candidate in decode_targets:
                try:
                    payload = ast.literal_eval(candidate)
                    break
                except (ValueError, SyntaxError):
                    continue
        if payload is None:
            return None

        blocks = self._collect_blocks_from_payload(payload)
        return blocks or None

    @staticmethod
    def _looks_like_block(payload: Dict[str, Any]) -> bool:
        """Roughly determine whether the dict conforms to the block structure"""
        if not isinstance(payload, dict):
            return False
        block_type = payload.get("type")
        if block_type and isinstance(block_type, str):
            # Exclude inline types (inlineRun, etc.), which are not block-level elements
            inline_types = {"inlineRun", "inline", "text"}
            if block_type in inline_types:
                return False
            return True
        structural_keys = {"blocks", "rows", "items", "widgetId", "widgetType", "data"}
        return any(key in payload for key in structural_keys)

    def _collect_blocks_from_payload(self, payload: Any) -> List[Dict[str, Any]]:
        """Recursively collect block nodes in the payload"""
        collected: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            block_list = payload.get("blocks")
            block_type = payload.get("type")
            
            # Exclude inline types, which are not block-level elements
            inline_types = {"inlineRun", "inline", "text"}
            if block_type in inline_types:
                return collected
            
            if isinstance(block_list, list) and not block_type:
                for candidate in block_list:
                    collected.extend(self._collect_blocks_from_payload(candidate))
                return collected
            if payload.get("cells") and not block_type:
                for cell in payload["cells"]:
                    if isinstance(cell, dict):
                        collected.extend(self._collect_blocks_from_payload(cell.get("blocks")))
                return collected
            if payload.get("items") and not block_type:
                for item in payload["items"]:
                    collected.extend(self._collect_blocks_from_payload(item))
                return collected
            appended = False
            if block_type or payload.get("widgetId") or payload.get("rows"):
                coerced = self._coerce_block_dict(payload)
                if coerced:
                    collected.append(coerced)
                    appended = True
            items = payload.get("items")
            if isinstance(items, list) and not block_type:
                for item in items:
                    collected.extend(self._collect_blocks_from_payload(item))
                return collected
            if appended:
                return collected
        elif isinstance(payload, list):
            for item in payload:
                collected.extend(self._collect_blocks_from_payload(item))
        elif payload is None:
            return collected
        return collected

    def _coerce_block_dict(self, payload: Any) -> Dict[str, Any] | None:
        """Try to supplement the dict into a legal block structure"""
        if not isinstance(payload, dict):
            return None
        block = copy.deepcopy(payload)
        block_type = block.get("type")
        if not block_type:
            if "widgetId" in block:
                block_type = block["type"] = "widget"
            elif "rows" in block or "cells" in block:
                block_type = block["type"] = "table"
                if "rows" not in block and isinstance(block.get("cells"), list):
                    block["rows"] = [{"cells": block.pop("cells")}]
            elif "items" in block:
                block_type = block["type"] = "list"
        return block if block.get("type") else None

    def _format_toc_entry(self, entry: Dict[str, Any]) -> str:
        """Convert a single directory entry into an HTML line with description.

        Parameters:
            entry: Directory entry, must contain `text` and `anchor`.

        Return:
            str: HTML in the form of `<li>`."""
        desc = entry.get("description")
        # Clean JSON fragments in description text
        if desc:
            desc = self._clean_text_from_json_artifacts(desc)
        desc_html = f'<p class="toc-desc">{self._escape_html(desc)}</p>' if desc else ""
        level = entry.get("level", 2)
        css_level = 1 if level <= 2 else min(level, 4)
        return f'<li class="level-{css_level}"><a href="#{self._escape_attr(entry["anchor"])}">{self._escape_html(entry["text"])}</a>{desc_html}</li>'

    def _compute_heading_labels(self, chapters: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Precalculate the numbers of headings at each level (Chapter: 1, 2; Section: 1.1; Subsection: 1.1.1).

        Parameters:
            chapters: Array of chapters in Document IR.

        Return:
            dict: Mapping of anchor points to numbers/descriptions to facilitate TOC and text references."""
        label_map: Dict[str, Dict[str, Any]] = {}

        for chap_idx, chapter in enumerate(chapters or [], start=1):
            chapter_heading_seen = False
            section_idx = 0
            subsection_idx = 0
            deep_counters: Dict[int, int] = {}

            for block in chapter.get("blocks", []):
                if block.get("type") != "heading":
                    continue
                level = block.get("level", 2)
                anchor = block.get("anchor") or chapter.get("anchor")
                if not anchor:
                    continue

                raw_text = block.get("text", "")
                clean_title = self._strip_order_prefix(raw_text)
                label = None
                display_text = raw_text

                if not chapter_heading_seen:
                    label = f"{self._to_chinese_numeral(chap_idx)}、"
                    display_text = f"{label} {clean_title}".strip()
                    chapter_heading_seen = True
                    section_idx = 0
                    subsection_idx = 0
                    deep_counters.clear()
                elif level <= 2:
                    section_idx += 1
                    subsection_idx = 0
                    deep_counters.clear()
                    label = f"{chap_idx}.{section_idx}"
                    display_text = f"{label} {clean_title}".strip()
                else:
                    if section_idx == 0:
                        section_idx = 1
                    if level == 3:
                        subsection_idx += 1
                        deep_counters.clear()
                        label = f"{chap_idx}.{section_idx}.{subsection_idx}"
                    else:
                        deep_counters[level] = deep_counters.get(level, 0) + 1
                        parts = [str(chap_idx), str(section_idx or 1), str(subsection_idx or 1)]
                        for lvl in sorted(deep_counters.keys()):
                            parts.append(str(deep_counters[lvl]))
                        label = ".".join(parts)
                    display_text = f"{label} {clean_title}".strip()

                label_map[anchor] = {
                    "level": level,
                    "display": display_text,
                    "label": label,
                    "title": clean_title,
                }
        return label_map

    @staticmethod
    def _strip_order_prefix(text: str) -> str:
        """Remove prefixes like "1.0" or "一," to get the pure title"""
        if not text:
            return ""
        separators = [" ", "、", ".", "．"]
        stripped = text.lstrip()
        for sep in separators:
            parts = stripped.split(sep, 1)
            if len(parts) == 2 and parts[0]:
                return parts[1].strip()
        return stripped.strip()

    @staticmethod
    def _to_chinese_numeral(number: int) -> str:
        """Map 1/2/3 to Chinese serial numbers (within ten)"""
        numerals = ["zero", "one", "two", "three", "Four", "five", "six", "seven", "eight", "Nine", "ten"]
        if number <= 10:
            return numerals[number]
        tens, ones = divmod(number, 10)
        if number < 20:
            return "ten" + (numerals[ones] if ones else "")
        words = ""
        if tens > 0:
            words += numerals[tens] + "ten"
        if ones:
            words += numerals[ones]
        return words

    # ====== Chapter and block-level rendering ======

    def _render_chapter(self, chapter: Dict[str, Any]) -> str:
        """Wrap section blocks into <section> for easy CSS control.

        Parameters:
            chapter: single chapter JSON.

        Return:
            str: HTML wrapped by section."""
        section_id = self._escape_attr(chapter.get("anchor") or f"chapter-{chapter.get('chapterId', 'x')}")
        prev_chapter = self._current_chapter
        self._current_chapter = chapter
        try:
            blocks_html = self._render_blocks(chapter.get("blocks", []))
        finally:
            self._current_chapter = prev_chapter
        return f'<section id="{section_id}" class="chapter">\n{blocks_html}\n</section>'

    def _render_blocks(self, blocks: List[Dict[str, Any]]) -> str:
        """Render all blocks in the chapter sequentially.

        Parameters:
            blocks: block array inside the chapter.

        Return:
            str: concatenated HTML."""
        return "".join(self._render_block(block) for block in blocks or [])

    def _render_block(self, block: Dict[str, Any]) -> str:
        """Dispatched to different rendering functions based on block.type.

        Parameters:
            block: a single block object.

        Return:
            str: Rendered HTML, unknown types will output JSON debugging information."""
        block_type = block.get("type")
        handlers = {
            "heading": self._render_heading,
            "paragraph": self._render_paragraph,
            "list": self._render_list,
            "table": self._render_table,
            "swotTable": self._render_swot_table,
            "pestTable": self._render_pest_table,
            "blockquote": self._render_blockquote,
            "engineQuote": self._render_engine_quote,
            "hr": lambda b: "<hr />",
            "code": self._render_code,
            "math": self._render_math,
            "figure": self._render_figure,
            "callout": self._render_callout,
            "kpiGrid": self._render_kpi_grid,
            "widget": self._render_widget,
            "toc": lambda b: self._render_toc_section(),
        }
        handler = handlers.get(block_type)
        if handler:
            html_fragment = handler(block)
            return self._wrap_error_block(html_fragment, block)
        # Compatible with old formats: when type is missing but contains inlines, it is processed as paragraph
        if isinstance(block, dict) and block.get("inlines"):
            html_fragment = self._render_paragraph({"inlines": block.get("inlines")})
            return self._wrap_error_block(html_fragment, block)
        # Compatible with scenarios where strings are directly passed in
        if isinstance(block, str):
            html_fragment = self._render_paragraph({"inlines": [{"text": block}]})
            return self._wrap_error_block(html_fragment, {"meta": {}, "type": "paragraph"})
        if isinstance(block.get("blocks"), list):
            html_fragment = self._render_blocks(block["blocks"])
            return self._wrap_error_block(html_fragment, block)
        fallback = f'<pre class="unknown-block">{self._escape_html(json.dumps(block, ensure_ascii=False, indent=2))}</pre>'
        return self._wrap_error_block(fallback, block)

    def _wrap_error_block(self, html_fragment: str, block: Dict[str, Any]) -> str:
        """If the block is marked with error metadata, the prompt container is wrapped and the tooltip is injected."""
        if not html_fragment:
            return html_fragment
        meta = block.get("meta") or {}
        log_ref = meta.get("errorLogRef")
        if not isinstance(log_ref, dict):
            return html_fragment
        raw_preview = (meta.get("rawJsonPreview") or "")[:1200]
        error_message = meta.get("errorMessage") or "LLM returns block parsing error"
        importance = meta.get("importance") or "standard"
        ref_label = ""
        if log_ref.get("relativeFile") and log_ref.get("entryId"):
            ref_label = f"{log_ref['relativeFile']}#{log_ref['entryId']}"
        tooltip = f"{error_message} | {ref_label}".strip()
        attr_raw = self._escape_attr(raw_preview or tooltip)
        attr_title = self._escape_attr(tooltip)
        class_suffix = self._escape_attr(importance)
        return (
            f'<div class="llm-error-block importance-{class_suffix}" '
            f'data-raw="{attr_raw}" title="{attr_title}">{html_fragment}</div>'
        )

    def _render_heading(self, block: Dict[str, Any]) -> str:
        """Render the heading block, ensuring the anchor point exists"""
        original_level = max(1, min(6, block.get("level", 2)))
        if original_level <= 2:
            level = 2
        elif original_level == 3:
            level = 3
        else:
            level = min(original_level, 6)
        anchor = block.get("anchor")
        if anchor:
            anchor_attr = self._escape_attr(anchor)
        else:
            self.heading_counter += 1
            anchor = f"heading-{self.heading_counter}"
            anchor_attr = self._escape_attr(anchor)
        mapping = self.heading_label_map.get(anchor, {})
        display_text = mapping.get("display") or block.get("text", "")
        subtitle = block.get("subtitle")
        subtitle_html = f'<small>{self._escape_html(subtitle)}</small>' if subtitle else ""
        return f'<h{level} id="{anchor_attr}">{self._escape_html(display_text)}{subtitle_html}</h{level}>'

    def _render_paragraph(self, block: Dict[str, Any]) -> str:
        """Render paragraphs and maintain the shuffled style internally through inline run"""
        inlines_data = block.get("inlines", [])
        
        # Detect and skip paragraphs containing document metadata JSON
        if self._is_metadata_paragraph(inlines_data):
            return ""
        
        # When only containing a single display formula, render it directly as a block to avoid <p> inline <div>
        if len(inlines_data) == 1:
            standalone = self._render_standalone_math_inline(inlines_data[0])
            if standalone:
                return standalone

        inlines = "".join(self._render_inline(run) for run in inlines_data)
        return f"<p>{inlines}</p>"

    def _is_metadata_paragraph(self, inlines: List[Any]) -> bool:
        """Detects whether a paragraph contains only document metadata JSON.
        
        Some LLM-generated content will contain metadata (such as xrefs, widgets, footnotes, metadata)
        Incorrectly output as paragraph content, this method identifies and flags this case so that rendering can be skipped."""
        if not inlines or len(inlines) != 1:
            return False
        first = inlines[0]
        if not isinstance(first, dict):
            return False
        text = first.get("text", "")
        if not isinstance(text, str):
            return False
        text = text.strip()
        if not text.startswith("{") or not text.endswith("}"):
            return False
        # Detect typical metadata keys
        metadata_indicators = ['"xrefs"', '"widgets"', '"footnotes"', '"metadata"', '"sectionBudgets"']
        return any(indicator in text for indicator in metadata_indicators)

    def _render_standalone_math_inline(self, run: Dict[str, Any] | str) -> str | None:
        """When a paragraph only contains a single display formula, convert it to math-block to avoid destroying the inline layout."""
        if isinstance(run, dict):
            text_value, marks = self._normalize_inline_payload(run)
            if marks:
                return None
            math_id_hint = run.get("mathIds") or run.get("mathId")
        else:
            text_value = "" if run is None else str(run)
            math_id_hint = None
            marks = []

        rendered = self._render_text_with_inline_math(
            text_value,
            math_id_hint,
            allow_display_block=True
        )
        if rendered and rendered.strip().startswith('<div class="math-block"'):
            return rendered
        return None

    def _render_list(self, block: Dict[str, Any]) -> str:
        """Rendering ordered/unordered/task lists"""
        list_type = block.get("listType", "bullet")
        tag = "ol" if list_type == "ordered" else "ul"
        extra_class = "task-list" if list_type == "task" else ""
        items_html = ""
        for item in block.get("items", []):
            content = self._render_blocks(item)
            if not content.strip():
                continue
            items_html += f"<li>{content}</li>"
        class_attr = f' class="{extra_class}"' if extra_class else ""
        return f'<{tag}{class_attr}>{items_html}</{tag}>'

    def _flatten_nested_cells(self, cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flatten incorrectly nested cell structures.

        In some LLM-generated tabular data, cells were incorrectly nested recursively:
        cells[0] is normal, cells[1].cells[0] is normal, cells[1].cells[1].cells[0] is normal...
        This method flattens this nested structure into a standard parallel cell array.

        Parameters:
            cells: A cell array that may contain nested structures.

        Return:
            List[Dict]: Flattened cell array."""
        if not cells:
            return []

        flattened: List[Dict[str, Any]] = []

        def _extract_cells(cell_or_list: Any) -> None:
            """Extract all cells recursively"""
            if not isinstance(cell_or_list, dict):
                return

            # If the current object has blocks, it means it is a valid cell
            if "blocks" in cell_or_list:
                # Create a copy of a cell, removing nested cells
                clean_cell = {
                    k: v for k, v in cell_or_list.items()
                    if k != "cells"
                }
                flattened.append(clean_cell)

            # If the current object has nested cells, process it recursively
            nested_cells = cell_or_list.get("cells")
            if isinstance(nested_cells, list):
                for nested_cell in nested_cells:
                    _extract_cells(nested_cell)

        for cell in cells:
            _extract_cells(cell)

        return flattened

    def _fix_nested_table_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fix incorrectly nested table row structure.

        In some tabular data generated by LLM, the cells of all rows are nested in the first row.
        Resulting in a table with only 1 row but containing all data. This method detects and fixes this situation.

        Parameters:
            rows: original table row array.

        Return:
            List[Dict]: Repaired table row array."""
        if not rows or len(rows) != 1:
            # Only handle exceptions with only 1 row
            return rows

        first_row = rows[0]
        original_cells = first_row.get("cells", [])

        # Check if nested structure exists
        has_nested = any(
            isinstance(cell.get("cells"), list)
            for cell in original_cells
            if isinstance(cell, dict)
        )

        if not has_nested:
            return rows

        # Flatten all cells
        all_cells = self._flatten_nested_cells(original_cells)

        if len(all_cells) <= 2:
            # Too few cells, no need to reorganize
            return rows

        # Helper function: get cell text
        def _get_cell_text(cell: Dict[str, Any]) -> str:
            """Get the text content of a cell"""
            blocks = cell.get("blocks", [])
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "paragraph":
                    inlines = block.get("inlines", [])
                    for inline in inlines:
                        if isinstance(inline, dict):
                            text = inline.get("text", "")
                            if text:
                                return str(text).strip()
            return ""

        def _is_placeholder_cell(cell: Dict[str, Any]) -> bool:
            """Determine whether the cell is a placeholder (such as '--', '-', '—', etc.)"""
            text = _get_cell_text(cell)
            return text in ("--", "-", "—", "——", "", "N/A", "n/a")

        # Filter out the placeholder cells first
        all_cells = [c for c in all_cells if not _is_placeholder_cell(c)]

        if len(all_cells) <= 2:
            return rows

        # Detect header column numbers: Find cells with bold markers or typical header words
        def _is_header_cell(cell: Dict[str, Any]) -> bool:
            """Determine whether the cell looks like a header (has a bold mark or a typical header word)"""
            blocks = cell.get("blocks", [])
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "paragraph":
                    inlines = block.get("inlines", [])
                    for inline in inlines:
                        if isinstance(inline, dict):
                            marks = inline.get("marks", [])
                            if any(isinstance(m, dict) and m.get("type") == "bold" for m in marks):
                                return True
            # Also check for typical header words
            text = _get_cell_text(cell)
            header_keywords = {
                "time", "date", "name", "type", "state", "quantity", "Amount", "Proportion", "index",
                "platform", "channel", "source", "describe", "illustrate", "Remark", "serial number", "serial number",
                "event", "key", "data", "support", "reaction", "market", "emotion", "node",
                "Dimensions", "Main points", "Details", "Label", "Influence", "trend", "weight", "category",
                "information", "content", "style", "Preference", "main", "user", "core", "feature",
                "Classification", "scope", "object", "project", "stage", "cycle", "frequency", "grade",
            }
            return any(kw in text for kw in header_keywords) and len(text) <= 20

        # Calculate the number of header columns: count the number of consecutive header cells
        header_count = 0
        for cell in all_cells:
            if _is_header_cell(cell):
                header_count += 1
            else:
                # Encountering the first non-header cell indicates the beginning of the data area
                break

        # If no header is detected, try using heuristics
        if header_count == 0:
            # Assume the number of columns is 4 or 5 (common table column numbers)
            total = len(all_cells)
            for possible_cols in [4, 5, 3, 6, 2]:
                if total % possible_cols == 0:
                    header_count = possible_cols
                    break
            else:
                # Try to find the closest number of columns that is divisible
                for possible_cols in [4, 5, 3, 6, 2]:
                    remainder = total % possible_cols
                    # Allow up to 3 extra cells (possibly summary or comments at the end)
                    if remainder <= 3:
                        header_count = possible_cols
                        break
                else:
                    # Unable to determine number of columns, return original data
                    return rows

        # Calculate the number of valid cells (you may need to truncate excess cells at the end)
        total = len(all_cells)
        remainder = total % header_count
        if remainder > 0 and remainder <= 3:
            # Truncate excess cells at the end (maybe summary or comments)
            all_cells = all_cells[:total - remainder]
        elif remainder > 3:
            # The remainder is too large, the number of columns may be detected incorrectly, and the original data is returned.
            return rows

        # Reorganize into multiple lines
        fixed_rows: List[Dict[str, Any]] = []
        for i in range(0, len(all_cells), header_count):
            row_cells = all_cells[i:i + header_count]
            # Mark the first row as header
            if i == 0:
                for cell in row_cells:
                    cell["header"] = True
            fixed_rows.append({"cells": row_cells})

        return fixed_rows

    def _render_table(self, block: Dict[str, Any]) -> str:
        """Render the table while retaining the caption and cell attributes.

        Parameters:
            block: block of table type.

        Return:
            str: HTML containing <table> structure."""
        # First fix possible nested row structure issues
        raw_rows = block.get("rows") or []
        fixed_rows = self._fix_nested_table_rows(raw_rows)
        rows = self._normalize_table_rows(fixed_rows)
        rows_html = ""
        for row in rows:
            row_cells = ""
            # Flatten possible nested cell structures (as extra protection)
            cells = self._flatten_nested_cells(row.get("cells", []))
            for cell in cells:
                cell_tag = "th" if cell.get("header") or cell.get("isHeader") else "td"
                attr = []
                if cell.get("rowspan"):
                    attr.append(f'rowspan="{int(cell["rowspan"])}"')
                if cell.get("colspan"):
                    attr.append(f'colspan="{int(cell["colspan"])}"')
                if cell.get("align"):
                    attr.append(f'class="align-{cell["align"]}"')
                attr_str = (" " + " ".join(attr)) if attr else ""
                content = self._render_blocks(cell.get("blocks", []))
                row_cells += f"<{cell_tag}{attr_str}>{content}</{cell_tag}>"
            rows_html += f"<tr>{row_cells}</tr>"
        caption = block.get("caption")
        caption_html = f"<caption>{self._escape_html(caption)}</caption>" if caption else ""
        return f'<div class="table-wrap"><table>{caption_html}<tbody>{rows_html}</tbody></table></div>'

    def _render_swot_table(self, block: Dict[str, Any]) -> str:
        """Render a four-quadrant SWOT analysis and generate two layouts at the same time:
        1. Card layout (for HTML web page display) - four quadrants of rounded rectangle
        2. Table layout (for PDF export) - structured table, supports paging
        
        PDF paging strategy:
        - Use table format, each S/W/O/T quadrant is an independent table block
        - Allow paging between different quadrants
        - Keep items in each quadrant together as much as possible"""
        title = block.get("title") or "SWOT analysis"
        summary = block.get("summary")
        
        # ========== Card layout (for HTML) ==========
        card_html = self._render_swot_card_layout(block, title, summary)
        
        # ========== Table layout (for PDF) ==========
        table_html = self._render_swot_pdf_table_layout(block, title, summary)
        
        # Returns a container containing two layouts
        return f"""
        <div class="swot-container">
          {card_html}
          {table_html}
        </div>
        """
    
    def _render_swot_card_layout(self, block: Dict[str, Any], title: str, summary: str | None) -> str:
        """Render SWOT card layout (for HTML web page display)"""
        quadrants = [
            ("strengths", "Strengths", "S", "strength"),
            ("weaknesses", "Weaknesses", "W", "weakness"),
            ("opportunities", "Opportunities", "O", "opportunity"),
            ("threats", "ThreatsThreats", "T", "threat"),
        ]
        cells_html = ""
        for idx, (key, label, code, css) in enumerate(quadrants):
            items = self._normalize_swot_items(block.get(key))
            caption_text = f"{len(items)} points" if items else "To be added"
            list_html = "".join(self._render_swot_item(item) for item in items) if items else '<li class="swot-empty">尚未填入要点</li>'
            first_cell_class = " swot-cell--first" if idx == 0 else ""
            cells_html += f"""
        <div class="swot-cell swot-cell--pageable {css}{first_cell_class}" data-swot-key="{key}">
          <div class="swot-cell__meta">
            <span class="swot-pill {css}">{self._escape_html(code)}</span>
            <div>
              <div class="swot-cell__title">{self._escape_html(label)}</div>
              <div class="swot-cell__caption">{self._escape_html(caption_text)}</div>
            </div>
          </div>
          <ul class="swot-list">{list_html}</ul>
        </div>"""
        summary_html = f'<p class="swot-card__summary">{self._escape_html(summary)}</p>' if summary else ""
        title_html = f'<div class="swot-card__title">{self._escape_html(title)}</div>' if title else ""
        legend = """
            <div class="swot-legend">
              <span class="swot-legend__item strength">S Advantages</span>
              <span class="swot-legend__item weakness">W Disadvantages</span>
              <span class="swot-legend__item opportunity">O opportunities</span>
              <span class="swot-legend__item threat">T threats</span>
            </div>"""
        return f"""
        <div class="swot-card swot-card--html">
          <div class="swot-card__head">
            <div>{title_html}{summary_html}</div>
            {legend}
          </div>
          <div class="swot-grid">{cells_html}</div>
        </div>
        """
    
    def _render_swot_pdf_table_layout(self, block: Dict[str, Any], title: str, summary: str | None) -> str:
        """Render SWOT table layout (for PDF export)
        
        Design description:
        - The whole is a large table, including the title row and 4 quadrant areas
        - Each quadrant area has its own subtitle row and content row
        - Use merged cells to display quadrant titles
        - Control paging behavior through CSS"""
        quadrants = [
            ("strengths", "S", "Strengths", "swot-pdf-strength", "#1c7f6e"),
            ("weaknesses", "W", "Weaknesses", "swot-pdf-weakness", "#c0392b"),
            ("opportunities", "O", "Opportunities", "swot-pdf-opportunity", "#1f5ab3"),
            ("threats", "T", "ThreatsThreats", "swot-pdf-threat", "#b36b16"),
        ]
        
        # Title and abstract
        summary_row = ""
        if summary:
            summary_row = f"""
            <tr class="swot-pdf-summary-row">
              <td colspan="4" class="swot-pdf-summary">{self._escape_html(summary)}</td>
            </tr>"""
        
        # Generate table content for four quadrants
        quadrant_tables = ""
        for idx, (key, code, label, css_class, color) in enumerate(quadrants):
            items = self._normalize_swot_items(block.get(key))
            
            # Generate content rows for each quadrant
            items_rows = ""
            if items:
                for item_idx, item in enumerate(items):
                    item_title = item.get("title") or item.get("label") or item.get("text") or "unnamed points"
                    item_detail = item.get("detail") or item.get("description") or ""
                    item_evidence = item.get("evidence") or item.get("source") or ""
                    item_impact = item.get("impact") or item.get("priority") or ""
                    # item_score = item.get("score") # The scoring function is disabled
                    
                    # Build details
                    detail_parts = []
                    if item_detail:
                        detail_parts.append(item_detail)
                    if item_evidence:
                        detail_parts.append(f"Evidence: {item_evidence}")
                    detail_text = "<br/>".join(detail_parts) if detail_parts else "-"
                    
                    # Build tags
                    tags = []
                    if item_impact:
                        tags.append(f'<span class="swot-pdf-tag">{self._escape_html(item_impact)}</span>')
                    # if item_score not in (None, ""): # The scoring function is disabled
                    # tags.append(f'<span class="swot-pdf-tag swot-pdf-tag--score">score {self._escape_html(item_score)}</span>')
                    tags_html = " ".join(tags)
                    
                    # The first row needs to merge the quadrant header cells
                    if item_idx == 0:
                        rowspan = len(items)
                        items_rows += f"""
            <tr class="swot-pdf-item-row {css_class}">
              <td rowspan="{rowspan}" class="swot-pdf-quadrant-label {css_class}">
                <span class="swot-pdf-code">{code}</span>
                <span class="swot-pdf-label-text">{self._escape_html(label.split()[0])}</span>
              </td>
              <td class="swot-pdf-item-num">{item_idx + 1}</td>
              <td class="swot-pdf-item-title">{self._escape_html(item_title)}</td>
              <td class="swot-pdf-item-detail">{detail_text}</td>
              <td class="swot-pdf-item-tags">{tags_html}</td>
            </tr>"""
                    else:
                        items_rows += f"""
            <tr class="swot-pdf-item-row {css_class}">
              <td class="swot-pdf-item-num">{item_idx + 1}</td>
              <td class="swot-pdf-item-title">{self._escape_html(item_title)}</td>
              <td class="swot-pdf-item-detail">{detail_text}</td>
              <td class="swot-pdf-item-tags">{tags_html}</td>
            </tr>"""
            else:
                # Show placeholder when there is no content
                items_rows = f"""
            <tr class="swot-pdf-item-row {css_class}">
              <td class="swot-pdf-quadrant-label {css_class}">
                <span class="swot-pdf-code">{code}</span>
                <span class="swot-pdf-label-text">{self._escape_html(label.split()[0])}</span>
              </td>
              <td class="swot-pdf-item-num">-</td>
              <td colspan="3" class="swot-pdf-empty">No points yet</td>
            </tr>"""
            
            # Each quadrant acts as an independent tbody for easy paging control.
            quadrant_tables += f"""
          <tbody class="swot-pdf-quadrant {css_class}">
            {items_rows}
          </tbody>"""
        
        return f"""
        <div class="swot-pdf-wrapper">
          <table class="swot-pdf-table">
            <caption class="swot-pdf-caption">{self._escape_html(title)}</caption>
            <thead class="swot-pdf-thead">
              <tr>
                <th class="swot-pdf-th-quadrant">Quadrant</th>
                <th class="swot-pdf-th-num">Serial number</th>
                <th class="swot-pdf-th-title">Points</th>
                <th class="swot-pdf-th-detail">Detailed description</th>
                <th class="swot-pdf-th-tags">Impact</th>
              </tr>
              {summary_row}
            </thead>
            {quadrant_tables}
          </table>
        </div>"""

    def _normalize_swot_items(self, raw: Any) -> List[Dict[str, Any]]:
        """Organize SWOT entries into a unified structure, compatible with both string/object writing methods"""
        normalized: List[Dict[str, Any]] = []
        if raw is None:
            return normalized
        if isinstance(raw, (str, int, float)):
            text = self._safe_text(raw).strip()
            if text:
                normalized.append({"title": text})
            return normalized
        if not isinstance(raw, list):
            return normalized
        for entry in raw:
            if isinstance(entry, (str, int, float)):
                text = self._safe_text(entry).strip()
                if text:
                    normalized.append({"title": text})
                continue
            if not isinstance(entry, dict):
                continue
            title = entry.get("title") or entry.get("label") or entry.get("text")
            detail = entry.get("detail") or entry.get("description")
            evidence = entry.get("evidence") or entry.get("source")
            impact = entry.get("impact") or entry.get("priority")
            # score = entry.get("score") # The scoring function is disabled
            if not title and isinstance(detail, str):
                title = detail
                detail = None
            if not (title or detail or evidence):
                continue
            normalized.append(
                {
                    "title": title,
                    "detail": detail,
                    "evidence": evidence,
                    "impact": impact,
                    # "score": score, # The scoring function is disabled
                }
            )
        return normalized

    def _render_swot_item(self, item: Dict[str, Any]) -> str:
        """Output HTML snippet of a single SWOT entry"""
        title = item.get("title") or item.get("label") or item.get("text") or "unnamed points"
        detail = item.get("detail") or item.get("description")
        evidence = item.get("evidence") or item.get("source")
        impact = item.get("impact") or item.get("priority")
        # score = item.get("score") # The scoring function is disabled
        tags: List[str] = []
        if impact:
            tags.append(f'<span class="swot-tag">{self._escape_html(impact)}</span>')
        # if score not in (None, ""): # The scoring function is disabled
        # tags.append(f'<span class="swot-tag neutral">score {self._escape_html(score)}</span>')
        tags_html = f'<span class="swot-item-tags">{"".join(tags)}</span>' if tags else ""
        detail_html = f'<div class="swot-item-desc">{self._escape_html(detail)}</div>' if detail else ""
        evidence_html = f'<div class="swot-item-evidence">佐证：{self._escape_html(evidence)}</div>' if evidence else ""
        return f"""
            <li class="swot-item">
              <div class="swot-item-title">{self._escape_html(title)}{tags_html}</div>
              {detail_html}{evidence_html}
            </li>
        """

    # ==================== PEST Analysis Block ====================
    
    def _render_pest_table(self, block: Dict[str, Any]) -> str:
        """Render a four-dimensional PEST analysis and generate two layouts at the same time:
        1. Card layout (for HTML web page display) - horizontal strip stacking
        2. Table layout (for PDF export) - structured table, supports paging
        
        PEST analysis dimensions:
        - P: Political (political factors)
        - E: Economic (economic factors)
        - S: Social (social factors)
        - T: Technological (technical factors)"""
        title = block.get("title") or "PEST analysis"
        summary = block.get("summary")
        
        # ========== Card layout (for HTML) ==========
        card_html = self._render_pest_card_layout(block, title, summary)
        
        # ========== Table layout (for PDF) ==========
        table_html = self._render_pest_pdf_table_layout(block, title, summary)
        
        # Returns a container containing two layouts
        return f"""
        <div class="pest-container">
          {card_html}
          {table_html}
        </div>
        """
    
    def _render_pest_card_layout(self, block: Dict[str, Any], title: str, summary: str | None) -> str:
        """Rendering PEST card layout (for HTML web page display) - horizontal strip stack design"""
        dimensions = [
            ("political", "political factors political", "P", "political"),
            ("economic", "Economic factors Economic", "E", "economic"),
            ("social", "Social factors Social", "S", "social"),
            ("technological", "Technical factors Technological", "T", "technological"),
        ]
        strips_html = ""
        for idx, (key, label, code, css) in enumerate(dimensions):
            items = self._normalize_pest_items(block.get(key))
            caption_text = f"{len(items)} points" if items else "To be added"
            list_html = "".join(self._render_pest_item(item) for item in items) if items else '<li class="pest-empty">尚未填入要点</li>'
            first_strip_class = " pest-strip--first" if idx == 0 else ""
            strips_html += f"""
        <div class="pest-strip pest-strip--pageable {css}{first_strip_class}" data-pest-key="{key}">
          <div class="pest-strip__indicator {css}">
            <span class="pest-code">{self._escape_html(code)}</span>
          </div>
          <div class="pest-strip__content">
            <div class="pest-strip__header">
              <div class="pest-strip__title">{self._escape_html(label)}</div>
              <div class="pest-strip__caption">{self._escape_html(caption_text)}</div>
            </div>
            <ul class="pest-list">{list_html}</ul>
          </div>
        </div>"""
        summary_html = f'<p class="pest-card__summary">{self._escape_html(summary)}</p>' if summary else ""
        title_html = f'<div class="pest-card__title">{self._escape_html(title)}</div>' if title else ""
        legend = """
            <div class="pest-legend">
              <span class="pest-legend__item political">P Politics</span>
              <span class="pest-legend__item economic">E Economy</span>
              <span class="pest-legend__item social">S Society</span>
              <span class="pest-legend__item technological">T Technology</span>
            </div>"""
        return f"""
        <div class="pest-card pest-card--html">
          <div class="pest-card__head">
            <div>{title_html}{summary_html}</div>
            {legend}
          </div>
          <div class="pest-strips">{strips_html}</div>
        </div>
        """
    
    def _render_pest_pdf_table_layout(self, block: Dict[str, Any], title: str, summary: str | None) -> str:
        """Render PEST table layout (for PDF export)
        
        Design description:
        - The whole is a large table, including the title row and 4 dimension areas
        - Each dimension has its own subtitle row and content row
        - Use merged cells to display dimension titles
        - Control paging behavior through CSS"""
        dimensions = [
            ("political", "P", "political factors political", "pest-pdf-political", "#8e44ad"),
            ("economic", "E", "Economic factors Economic", "pest-pdf-economic", "#16a085"),
            ("social", "S", "Social factors Social", "pest-pdf-social", "#e84393"),
            ("technological", "T", "Technical factors Technological", "pest-pdf-technological", "#2980b9"),
        ]
        
        # Title and abstract
        summary_row = ""
        if summary:
            summary_row = f"""
            <tr class="pest-pdf-summary-row">
              <td colspan="4" class="pest-pdf-summary">{self._escape_html(summary)}</td>
            </tr>"""
        
        # Generate table content in four dimensions
        dimension_tables = ""
        for idx, (key, code, label, css_class, color) in enumerate(dimensions):
            items = self._normalize_pest_items(block.get(key))
            
            # Generate content rows for each dimension
            items_rows = ""
            if items:
                for item_idx, item in enumerate(items):
                    item_title = item.get("title") or item.get("label") or item.get("text") or "unnamed points"
                    item_detail = item.get("detail") or item.get("description") or ""
                    item_source = item.get("source") or item.get("evidence") or ""
                    item_trend = item.get("trend") or item.get("impact") or ""
                    
                    # Build details
                    detail_parts = []
                    if item_detail:
                        detail_parts.append(item_detail)
                    if item_source:
                        detail_parts.append(f"Source: {item_source}")
                    detail_text = "<br/>".join(detail_parts) if detail_parts else "-"
                    
                    # Build tags
                    tags = []
                    if item_trend:
                        tags.append(f'<span class="pest-pdf-tag">{self._escape_html(item_trend)}</span>')
                    tags_html = " ".join(tags)
                    
                    # The first row needs to merge the dimension header cells
                    if item_idx == 0:
                        rowspan = len(items)
                        items_rows += f"""
            <tr class="pest-pdf-item-row {css_class}">
              <td rowspan="{rowspan}" class="pest-pdf-dimension-label {css_class}">
                <span class="pest-pdf-code">{code}</span>
                <span class="pest-pdf-label-text">{self._escape_html(label.split()[0])}</span>
              </td>
              <td class="pest-pdf-item-num">{item_idx + 1}</td>
              <td class="pest-pdf-item-title">{self._escape_html(item_title)}</td>
              <td class="pest-pdf-item-detail">{detail_text}</td>
              <td class="pest-pdf-item-tags">{tags_html}</td>
            </tr>"""
                    else:
                        items_rows += f"""
            <tr class="pest-pdf-item-row {css_class}">
              <td class="pest-pdf-item-num">{item_idx + 1}</td>
              <td class="pest-pdf-item-title">{self._escape_html(item_title)}</td>
              <td class="pest-pdf-item-detail">{detail_text}</td>
              <td class="pest-pdf-item-tags">{tags_html}</td>
            </tr>"""
            else:
                # Show placeholder when there is no content
                items_rows = f"""
            <tr class="pest-pdf-item-row {css_class}">
              <td class="pest-pdf-dimension-label {css_class}">
                <span class="pest-pdf-code">{code}</span>
                <span class="pest-pdf-label-text">{self._escape_html(label.split()[0])}</span>
              </td>
              <td class="pest-pdf-item-num">-</td>
              <td colspan="3" class="pest-pdf-empty">No points yet</td>
            </tr>"""
            
            # Each dimension serves as an independent tbody for easy paging control.
            dimension_tables += f"""
          <tbody class="pest-pdf-dimension {css_class}">
            {items_rows}
          </tbody>"""
        
        return f"""
        <div class="pest-pdf-wrapper">
          <table class="pest-pdf-table">
            <caption class="pest-pdf-caption">{self._escape_html(title)}</caption>
            <thead class="pest-pdf-thead">
              <tr>
                <th class="pest-pdf-th-dimension">Dimensions</th>
                <th class="pest-pdf-th-num">Serial number</th>
                <th class="pest-pdf-th-title">Points</th>
                <th class="pest-pdf-th-detail">Detailed description</th>
                <th class="pest-pdf-th-tags">Trend/Impact</th>
              </tr>
              {summary_row}
            </thead>
            {dimension_tables}
          </table>
        </div>"""

    def _normalize_pest_items(self, raw: Any) -> List[Dict[str, Any]]:
        """Organize PEST entries into a unified structure, compatible with both string/object writing methods"""
        normalized: List[Dict[str, Any]] = []
        if raw is None:
            return normalized
        if isinstance(raw, (str, int, float)):
            text = self._safe_text(raw).strip()
            if text:
                normalized.append({"title": text})
            return normalized
        if not isinstance(raw, list):
            return normalized
        for entry in raw:
            if isinstance(entry, (str, int, float)):
                text = self._safe_text(entry).strip()
                if text:
                    normalized.append({"title": text})
                continue
            if not isinstance(entry, dict):
                continue
            title = entry.get("title") or entry.get("label") or entry.get("text")
            detail = entry.get("detail") or entry.get("description")
            source = entry.get("source") or entry.get("evidence")
            trend = entry.get("trend") or entry.get("impact")
            if not title and isinstance(detail, str):
                title = detail
                detail = None
            if not (title or detail or source):
                continue
            normalized.append(
                {
                    "title": title,
                    "detail": detail,
                    "source": source,
                    "trend": trend,
                }
            )
        return normalized

    def _render_pest_item(self, item: Dict[str, Any]) -> str:
        """Output HTML snippet of a single PEST entry"""
        title = item.get("title") or item.get("label") or item.get("text") or "unnamed points"
        detail = item.get("detail") or item.get("description")
        source = item.get("source") or item.get("evidence")
        trend = item.get("trend") or item.get("impact")
        tags: List[str] = []
        if trend:
            tags.append(f'<span class="pest-tag">{self._escape_html(trend)}</span>')
        tags_html = f'<span class="pest-item-tags">{"".join(tags)}</span>' if tags else ""
        detail_html = f'<div class="pest-item-desc">{self._escape_html(detail)}</div>' if detail else ""
        source_html = f'<div class="pest-item-source">来源：{self._escape_html(source)}</div>' if source else ""
        return f"""
            <li class="pest-item">
              <div class="pest-item-title">{self._escape_html(title)}{tags_html}</div>
              {detail_html}{source_html}
            </li>
        """

    def _normalize_table_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect and correct vertical tables with only one column, converting them to standard grids.

        Parameters:
            rows: original table rows.

        Return:
            list[dict]: If a vertical table is detected, the transposed row is returned, otherwise it is returned unchanged."""
        if not rows:
            return []
        if not all(len((row.get("cells") or [])) == 1 for row in rows):
            return rows
        texts = [self._extract_row_text(row) for row in rows]
        header_span = self._detect_transposed_header_span(rows, texts)
        if not header_span:
            return rows
        normalized = self._transpose_single_cell_table(rows, header_span)
        return normalized or rows

    def _detect_transposed_header_span(self, rows: List[Dict[str, Any]], texts: List[str]) -> int:
        """Infer the number of rows in the vertical table header for subsequent transposition"""
        max_fields = min(8, len(rows) // 2)
        header_span = 0
        for idx, text in enumerate(texts):
            if idx >= max_fields:
                break
            if self._is_potential_table_header(text):
                header_span += 1
            else:
                break
        if header_span < 2:
            return 0
        remainder = texts[header_span:]
        if not remainder or (len(rows) - header_span) % header_span != 0:
            return 0
        if not any(self._looks_like_table_value(txt) for txt in remainder):
            return 0
        return header_span

    def _is_potential_table_header(self, text: str) -> bool:
        """Determine whether it looks like a header field based on length and character characteristics"""
        if not text:
            return False
        stripped = text.strip()
        if not stripped or len(stripped) > 12:
            return False
        return not any(ch.isdigit() or ch in self.TABLE_COMPLEX_CHARS for ch in stripped)

    def _looks_like_table_value(self, text: str) -> bool:
        """Determine whether the text is more like a data value, used to assist in determining transposition"""
        if not text:
            return False
        stripped = text.strip()
        if len(stripped) >= 12:
            return True
        return any(ch.isdigit() or ch in self.TABLE_COMPLEX_CHARS for ch in stripped)

    def _transpose_single_cell_table(self, rows: List[Dict[str, Any]], span: int) -> List[Dict[str, Any]]:
        """Convert a table with a single column and multiple rows into a standard header + several data rows"""
        total = len(rows)
        if total <= span or (total - span) % span != 0:
            return []
        header_rows = rows[:span]
        data_rows = rows[span:]
        normalized: List[Dict[str, Any]] = []
        header_cells = []
        for row in header_rows:
            cell = copy.deepcopy((row.get("cells") or [{}])[0])
            cell["header"] = True
            header_cells.append(cell)
        normalized.append({"cells": header_cells})
        for start in range(0, len(data_rows), span):
            group = data_rows[start : start + span]
            if len(group) < span:
                break
            normalized.append(
                {
                    "cells": [
                        copy.deepcopy((item.get("cells") or [{}])[0])
                        for item in group
                    ]
                }
            )
        return normalized

    def _extract_row_text(self, row: Dict[str, Any]) -> str:
        """Extract plain text from table rows to facilitate heuristic analysis"""
        cells = row.get("cells") or []
        if not cells:
            return ""
        cell = cells[0]
        texts: List[str] = []
        for block in cell.get("blocks", []):
            if isinstance(block, dict):
                if block.get("type") == "paragraph":
                    for inline in block.get("inlines") or []:
                        if isinstance(inline, dict):
                            value = inline.get("text")
                        else:
                            value = inline
                        if value is None:
                            continue
                        texts.append(str(value))
        return "".join(texts)

    def _render_blockquote(self, block: Dict[str, Any]) -> str:
        """Render reference blocks, which can nest other blocks"""
        inner = self._render_blocks(block.get("blocks", []))
        return f"<blockquote>{inner}</blockquote>"

    def _render_engine_quote(self, block: Dict[str, Any]) -> str:
        """Render a single Engine speech block with independent color matching and title"""
        engine_raw = (block.get("engine") or "").lower()
        engine = engine_raw if engine_raw in ENGINE_AGENT_TITLES else "insight"
        expected_title = ENGINE_AGENT_TITLES.get(engine, ENGINE_AGENT_TITLES["insight"])
        title_raw = block.get("title") if isinstance(block.get("title"), str) else ""
        title = title_raw if title_raw == expected_title else expected_title
        inner = self._render_blocks(block.get("blocks", []))
        return (
            f'<div class="engine-quote engine-{self._escape_attr(engine)}">'
            f'  <div class="engine-quote__header">'
            f'    <span class="engine-quote__dot"></span>'
            f'    <span class="engine-quote__title">{self._escape_html(title)}</span>'
            f'  </div>'
            f'  <div class="engine-quote__body">{inner}</div>'
            f'</div>'
        )

    def _render_code(self, block: Dict[str, Any]) -> str:
        """Render code blocks with language information"""
        lang = block.get("lang") or ""
        content = self._escape_html(block.get("content", ""))
        return f'<pre class="code-block" data-lang="{self._escape_attr(lang)}"><code>{content}</code></pre>'

    def _render_math(self, block: Dict[str, Any]) -> str:
        """Render mathematical formulas, and pass placeholders to external MathJax or post-processing"""
        latex_raw = block.get("latex", "")
        latex = self._escape_html(self._normalize_latex_string(latex_raw))
        math_id = self._escape_attr(block.get("mathId", "")) if block.get("mathId") else ""
        id_attr = f' data-math-id="{math_id}"' if math_id else ""
        return f'<div class="math-block"{id_attr}>$$ {latex} $$</div>'

    def _render_figure(self, block: Dict[str, Any]) -> str:
        """According to the new specification, external images are not rendered by default and are changed to friendly prompts."""
        caption = block.get("caption") or "Image content omitted (only HTML native charts and tables allowed)"
        return f'<div class="figure-placeholder">{self._escape_html(caption)}</div>'

    def _render_callout(self, block: Dict[str, Any]) -> str:
        """Render a highlight prompt box, and tone determines the color.

        Parameters:
            block: block of callout type.

        Return:
            str: callout HTML, if it contains disallowed blocks, it will be split."""
        tone = block.get("tone", "info")
        title = block.get("title")
        safe_blocks, trailing_blocks = self._split_callout_content(block.get("blocks"))
        inner = self._render_blocks(safe_blocks)
        title_html = f"<strong>{self._escape_html(title)}</strong>" if title else ""
        callout_html = f'<div class="callout tone-{tone}">{title_html}{inner}</div>'
        trailing_html = self._render_blocks(trailing_blocks) if trailing_blocks else ""
        return callout_html + trailing_html

    def _split_callout_content(
        self, blocks: List[Dict[str, Any]] | None
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Limit the callout to contain only lightweight content, and strip the remaining blocks to the outer layer"""
        if not blocks:
            return [], []
        safe: List[Dict[str, Any]] = []
        trailing: List[Dict[str, Any]] = []
        for idx, child in enumerate(blocks):
            child_type = child.get("type")
            if child_type == "list":
                sanitized, overflow = self._sanitize_callout_list(child)
                if sanitized:
                    safe.append(sanitized)
                if overflow:
                    trailing.extend(overflow)
                    trailing.extend(copy.deepcopy(blocks[idx + 1 :]))
                    break
            elif child_type in self.CALLOUT_ALLOWED_TYPES:
                safe.append(child)
            else:
                trailing.extend(copy.deepcopy(blocks[idx:]))
                break
        else:
            return safe, []
        return safe, trailing

    def _sanitize_callout_list(
        self, block: Dict[str, Any]
    ) -> tuple[Dict[str, Any] | None, List[Dict[str, Any]]]:
        """When the list item contains a structural block, truncate it and move it out of the callout"""
        items = block.get("items") or []
        if not items:
            return block, []
        sanitized_items: List[List[Dict[str, Any]]] = []
        trailing: List[Dict[str, Any]] = []
        for idx, item in enumerate(items):
            safe, overflow = self._split_callout_content(item)
            if safe:
                sanitized_items.append(safe)
            if overflow:
                trailing.extend(overflow)
                for rest in items[idx + 1 :]:
                    trailing.extend(copy.deepcopy(rest))
                break
        if not sanitized_items:
            return None, trailing
        new_block = copy.deepcopy(block)
        new_block["items"] = sanitized_items
        return new_block, trailing

    def _render_kpi_grid(self, block: Dict[str, Any]) -> str:
        """Render KPI card raster, including indicator values ​​and increases and decreases"""
        if self._should_skip_overview_kpi(block):
            return ""
        cards = ""
        items = block.get("items", [])
        for item in items:
            delta = item.get("delta")
            delta_tone = item.get("deltaTone") or "neutral"
            delta_html = f'<span class="delta {delta_tone}">{self._escape_html(delta)}</span>' if delta else ""
            cards += f"""
            <div class="kpi-card">
              <div class="kpi-value">{self._escape_html(item.get("value", ""))}<small>{self._escape_html(item.get("unit", ""))}</small></div>
              <div class="kpi-label">{self._escape_html(item.get("label", ""))}</div>
              {delta_html}
            </div>
            """
        count_attr = f' data-kpi-count="{len(items)}"' if items else ""
        return f'<div class="kpi-grid"{count_attr}>{cards}</div>'

    def _merge_dicts(
        self, base: Dict[str, Any] | None, override: Dict[str, Any] | None
    ) -> Dict[str, Any]:
        """Recursively merge two dictionaries, override covers base, and both are new copies to avoid side effects."""
        result = copy.deepcopy(base) if isinstance(base, dict) else {}
        if not isinstance(override, dict):
            return result
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._merge_dicts(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    def _looks_like_chart_dataset(self, candidate: Any) -> bool:
        """Heuristically determines whether the object contains the common labels/datasets structure of Chart.js"""
        if not isinstance(candidate, dict):
            return False
        labels = candidate.get("labels")
        datasets = candidate.get("datasets")
        return isinstance(labels, list) or isinstance(datasets, list)

    def _coerce_chart_data_structure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Compatible with the complete configuration of Chart.js output by LLM (including type/data/options).
        If there is a real labels/datasets structure nested in data, extract and return the structure."""
        if not isinstance(data, dict):
            return {}
        if self._looks_like_chart_dataset(data):
            return data
        for key in ("data", "chartData", "payload"):
            nested = data.get(key)
            if self._looks_like_chart_dataset(nested):
                return copy.deepcopy(nested)
        return data

    def _prepare_widget_payload(
        self, block: Dict[str, Any]
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Preprocessing widget data is compatible with some blocks writing Chart.js configuration into the data field.

        Return:
            tuple(props, data): normalized props and chart data"""
        props = copy.deepcopy(block.get("props") or {})
        raw_data = block.get("data")
        data_copy = copy.deepcopy(raw_data) if isinstance(raw_data, dict) else raw_data
        widget_type = block.get("widgetType") or ""
        chart_like = isinstance(widget_type, str) and widget_type.startswith("chart.js")

        if chart_like and isinstance(data_copy, dict):
            inline_options = data_copy.pop("options", None)
            inline_type = data_copy.pop("type", None)
            normalized_data = self._coerce_chart_data_structure(data_copy)
            if isinstance(inline_options, dict):
                props["options"] = self._merge_dicts(props.get("options"), inline_options)
            if isinstance(inline_type, str) and inline_type and not props.get("type"):
                props["type"] = inline_type
        elif isinstance(data_copy, dict):
            normalized_data = data_copy
        else:
            normalized_data = {}

        return props, normalized_data

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

    def _chart_cache_key(self, block: Dict[str, Any]) -> str:
        """Use the repairer's caching algorithm to generate stable keys to facilitate sharing results across stages"""
        if hasattr(self, "chart_repairer") and block:
            try:
                return self.chart_repairer.build_cache_key(block)
            except Exception:
                pass
        return str(id(block))

    def _note_chart_failure(self, cache_key: str, reason: str) -> None:
        """Record the reason for repair failure, and use placeholder prompts directly for subsequent renderings."""
        if not cache_key:
            return
        if not reason:
            reason = "The format of the chart information returned by LLM is incorrect and cannot be displayed normally."
        self._chart_failure_notes[cache_key] = reason

    def _record_chart_failure_stat(self, cache_key: str | None = None) -> None:
        """Make sure the failure count is only counted once"""
        if cache_key and cache_key in self._chart_failure_recorded:
            return
        self.chart_validation_stats['failed'] += 1
        if cache_key:
            self._chart_failure_recorded.add(cache_key)

    def _apply_cached_review_stats(self, block: Dict[str, Any]) -> None:
        """Re-accumulate statistics on reviewed charts to avoid repeated fixes.

        When the rendering process resets statistics but the chart has already been reviewed (_chart_reviewed=True),
        Accumulate various counts directly based on the recorded status to prevent ChartRepairer from being triggered again."""
        if not isinstance(block, dict):
            return

        status = block.get("_chart_review_status") or "valid"
        method = (block.get("_chart_review_method") or "none").lower()
        cache_key = self._chart_cache_key(block)

        self.chart_validation_stats['total'] += 1
        if status == "failed":
            self._record_chart_failure_stat(cache_key)
        elif status == "repaired":
            if method == "api":
                self.chart_validation_stats['repaired_api'] += 1
            else:
                self.chart_validation_stats['repaired_locally'] += 1
        else:
            self.chart_validation_stats['valid'] += 1

    def _format_chart_error_reason(
        self,
        validation_result: ValidationResult | None = None,
        fallback_reason: str | None = None
    ) -> str:
        """Splice-friendly failure prompts"""
        base = "The format of the chart information returned by LLM is incorrect. We have tried local and multi-model repairs but still cannot display it properly."
        detail = None
        if validation_result:
            if validation_result.errors:
                detail = validation_result.errors[0]
            elif validation_result.warnings:
                detail = validation_result.warnings[0]
        if not detail and fallback_reason:
            detail = fallback_reason
        if detail:
            text = f"{base} Tip: {detail}"
            return text[:180] + ("..." if len(text) > 180 else "")
        return base

    def _render_chart_error_placeholder(
        self,
        title: str | None,
        reason: str,
        widget_id: str | None = None
    ) -> str:
        """A concise placeholder prompt when outputting a chart fails to avoid damaging the HTML/PDF layout"""
        safe_title = self._escape_html(title or "Chart failed to display")
        safe_reason = self._escape_html(reason)
        widget_attr = f' data-widget-id="{self._escape_attr(widget_id)}"' if widget_id else ""
        return f"""
        <div class="chart-card chart-card--error"{widget_attr}>
          <div class="chart-error">
            <div class="chart-error__icon">!</div>
            <div class="chart-error__body">
              <div class="chart-error__title">{safe_title}</div>
              <p class="chart-error__desc">{safe_reason}</p>
            </div>
          </div>
        </div>
        """

    def _has_chart_failure(self, block: Dict[str, Any]) -> tuple[bool, str | None]:
        """Check whether there is a repair failure record"""
        cache_key = self._chart_cache_key(block)
        if block.get("_chart_renderable") is False:
            return True, block.get("_chart_error_reason")
        if cache_key in self._chart_failure_notes:
            return True, self._chart_failure_notes.get(cache_key)
        return False, None

    def _normalize_chart_block(
        self,
        block: Dict[str, Any],
        chapter_context: Dict[str, Any] | None = None,
    ) -> None:
        """Complete missing fields (such as scales and datasets) in chart blocks to improve fault tolerance.

        - Merge scales with errors at the top level of the block into props.options.
        - When data is missing or datasets are empty, try to use chapter-level data as a fallback."""

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

        # If datasets are empty, try to fill them with chapter-level data
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

        # If labels are still missing and the data points contain x values, they are automatically generated for fallback and coordinate scales.
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

    def _ensure_chart_reviewed(
        self,
        block: Dict[str, Any],
        chapter_context: Dict[str, Any] | None = None,
        *,
        increment_stats: bool = True
    ) -> tuple[bool, str | None]:
        """Make sure the graph is reviewed/fixed and the results are written back to the original block.

        Return:
            (renderable, fail_reason)"""
        if not isinstance(block, dict):
            return True, None

        widget_type = block.get('widgetType', '')
        is_chart = isinstance(widget_type, str) and widget_type.startswith('chart.js')
        if not is_chart:
            return True, None

        is_wordcloud = 'wordcloud' in widget_type.lower() if isinstance(widget_type, str) else False
        cache_key = self._chart_cache_key(block)

        # If there is already a failure record or it is explicitly marked as non-renderable, the result can be reused directly.
        if block.get("_chart_renderable") is False:
            if increment_stats:
                self.chart_validation_stats['total'] += 1
                self._record_chart_failure_stat(cache_key)
            reason = block.get("_chart_error_reason")
            block["_chart_reviewed"] = True
            block["_chart_review_status"] = block.get("_chart_review_status") or "failed"
            block["_chart_review_method"] = block.get("_chart_review_method") or "none"
            if reason:
                self._note_chart_failure(cache_key, reason)
            return False, reason

        if block.get("_chart_reviewed"):
            if increment_stats:
                self._apply_cached_review_stats(block)
            failed, cached_reason = self._has_chart_failure(block)
            renderable = not failed and block.get("_chart_renderable", True) is not False
            return renderable, block.get("_chart_error_reason") or cached_reason

        # First review: Complete the structure first, then verify/fix it
        self._normalize_chart_block(block, chapter_context)

        if increment_stats:
            self.chart_validation_stats['total'] += 1

        if is_wordcloud:
            if increment_stats:
                self.chart_validation_stats['valid'] += 1
            block["_chart_reviewed"] = True
            block["_chart_review_status"] = "valid"
            block["_chart_review_method"] = "none"
            return True, None

        validation_result = self.chart_validator.validate(block)

        if not validation_result.is_valid:
            logger.warning(
                f"Chart {block.get('widgetId', 'unknown')} Validation failed: {validation_result.errors}"
            )

            repair_result = self.chart_repairer.repair(block, validation_result)

            if repair_result.success and repair_result.repaired_block:
                # Repair successful, write back the repaired data
                repaired_block = repair_result.repaired_block
                block.clear()
                block.update(repaired_block)
                method = repair_result.method or "local"
                logger.info(
                    f"Chart {block.get('widgetId', 'unknown')} repaired successfully"
                    f"(Method: {method}): {repair_result.changes}"
                )

                if increment_stats:
                    if method == 'local':
                        self.chart_validation_stats['repaired_locally'] += 1
                    elif method == 'api':
                        self.chart_validation_stats['repaired_api'] += 1
                block["_chart_review_status"] = "repaired"
                block["_chart_review_method"] = method
                block["_chart_reviewed"] = True
                return True, None

            # If the repair fails, the failure will be recorded and a placeholder prompt will be output.
            fail_reason = self._format_chart_error_reason(validation_result)
            block["_chart_renderable"] = False
            block["_chart_error_reason"] = fail_reason
            block["_chart_review_status"] = "failed"
            block["_chart_review_method"] = "none"
            block["_chart_reviewed"] = True
            self._note_chart_failure(cache_key, fail_reason)
            if increment_stats:
                self._record_chart_failure_stat(cache_key)
            logger.warning(
                f"Chart {block.get('widgetId', 'unknown')} repair failed, rendering skipped: {fail_reason}"
            )
            return False, fail_reason

        # Verification passed
        if increment_stats:
            self.chart_validation_stats['valid'] += 1
            if validation_result.warnings:
                logger.info(
                    f"Chart {block.get('widgetId', 'unknown')} passed the verification,"
                    f"But there are warnings: {validation_result.warnings}"
                )
        block["_chart_review_status"] = "valid"
        block["_chart_review_method"] = "none"
        block["_chart_reviewed"] = True
        return True, None

    def review_and_patch_document(
        self,
        document_ir: Dict[str, Any],
        *,
        reset_stats: bool = True,
        clone: bool = False
    ) -> Dict[str, Any]:
        """Review and repair graphs globally, writing repair results back to the original IR to avoid repeating repairs on multiple renders.

        Parameters:
            document_ir: original Document IR
            reset_stats: whether to reset statistics
            clone: whether to return a deep copy after repair (the original IR will still be written back with the repair result)

        Return:
            Repaired IR (may be the original object or its deep copy)"""
        if reset_stats:
            self._reset_chart_validation_stats()

        target_ir = document_ir or {}

        def _walk_blocks(blocks: list, chapter_ctx: Dict[str, Any] | None = None) -> None:
            for blk in blocks or []:
                if not isinstance(blk, dict):
                    continue
                if blk.get("type") == "widget":
                    self._ensure_chart_reviewed(blk, chapter_ctx, increment_stats=True)

                nested_blocks = blk.get("blocks")
                if isinstance(nested_blocks, list):
                    _walk_blocks(nested_blocks, chapter_ctx)

                if blk.get("type") == "list":
                    for item in blk.get("items", []):
                        if isinstance(item, list):
                            _walk_blocks(item, chapter_ctx)

                if blk.get("type") == "table":
                    for row in blk.get("rows", []):
                        cells = row.get("cells", [])
                        for cell in cells:
                            if isinstance(cell, dict):
                                cell_blocks = cell.get("blocks", [])
                                if isinstance(cell_blocks, list):
                                    _walk_blocks(cell_blocks, chapter_ctx)

        for chapter in target_ir.get("chapters", []) or []:
            if not isinstance(chapter, dict):
                continue
            _walk_blocks(chapter.get("blocks", []), chapter)

        return copy.deepcopy(target_ir) if clone else target_ir

    def _render_widget(self, block: Dict[str, Any]) -> str:
        """Render placeholder containers for interactive components such as Chart.js and record configuration JSON.

        Chart validation and repair before rendering:
        1. validate: ChartValidator checks the data/props/options structure of the block;
        2. repair: If it fails, repair it locally first (reply if labels/datasets/scale is missing), and then call the LLM API;
        3. Failure recovery: write _chart_renderable=False and _chart_error_reason to output an error occupancy instead of throwing an exception.

        Parameters (corresponding to IR level):
        - block.widgetType:"chart.js/bar"/"chart.js/line"/"wordcloud"etc., decide the renderer and verification strategy;
        - block.widgetId: unique ID of the component, used for canvas/data script binding;
        - block.props: transparently transmitted to the front-end Chart.js options, such as props.title / props.options.legend;
        - block.data: {labels, datasets} and other data; if missing, try to fill it in from chapter-level chapter.data;
        - block.dataRef: external data reference, temporarily used as a transparent transmission record.

        Return:
            str: HTML containing canvas and configuration script."""
        # Unified review/repair entrance to avoid subsequent repeated repairs
        widget_type = block.get('widgetType', '')
        is_chart = isinstance(widget_type, str) and widget_type.startswith('chart.js')
        is_wordcloud = isinstance(widget_type, str) and 'wordcloud' in widget_type.lower()
        reviewed = bool(block.get("_chart_reviewed"))
        renderable = True
        fail_reason = None

        if is_chart:
            renderable, fail_reason = self._ensure_chart_reviewed(
                block,
                getattr(self, "_current_chapter", None),
                increment_stats=not reviewed
            )

        widget_id = block.get('widgetId')
        props_snapshot = block.get("props") if isinstance(block.get("props"), dict) else {}
        display_title = props_snapshot.get("title") or block.get("title") or widget_id or "chart"

        if is_chart and not renderable:
            reason = fail_reason or "The format of the chart information returned by LLM is incorrect and cannot be displayed normally."
            return self._render_chart_error_placeholder(display_title, reason, widget_id)

        # Render chart HTML
        self.chart_counter += 1
        canvas_id = f"chart-{self.chart_counter}"
        config_id = f"chart-config-{self.chart_counter}"

        props, normalized_data = self._prepare_widget_payload(block)
        payload = {
            "widgetId": block.get("widgetId"),
            "widgetType": block.get("widgetType"),
            "props": props,
            "data": normalized_data,
            "dataRef": block.get("dataRef"),
        }
        config_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
        self.widget_scripts.append(
            f'<script type="application/json" id="{config_id}">{config_json}</script>'
        )

        title = props.get("title")
        title_html = f'<div class="chart-title">{self._escape_html(title)}</div>' if title else ""
        fallback_html = (
            self._render_wordcloud_fallback(props, block.get("widgetId"), block.get("data"))
            if is_wordcloud
            else self._render_widget_fallback(normalized_data, block.get("widgetId"))
        )
        return f"""
        <div class="chart-card{' wordcloud-card' if is_wordcloud else ''}">
          {title_html}
          <div class="chart-container">
            <canvas id="{canvas_id}" data-config-id="{config_id}"></canvas>
          </div>
          {fallback_html}
        </div>
        """

    def _render_widget_fallback(self, data: Dict[str, Any], widget_id: str | None = None) -> str:
        """Render a text bottom view of chart data to avoid blanks when Chart.js fails to load."""
        if not isinstance(data, dict):
            return ""
        labels = data.get("labels") or []
        datasets = data.get("datasets") or []
        if not labels or not datasets:
            return ""

        widget_attr = f' data-widget-id="{self._escape_attr(widget_id)}"' if widget_id else ""
        header_cells = "".join(
            f"<th>{self._escape_html(ds.get('label') or f'series{idx + 1}')}</th>"
            for idx, ds in enumerate(datasets)
        )
        body_rows = ""
        for idx, label in enumerate(labels):
            row_cells = [f"<td>{self._escape_html(label)}</td>"]
            for ds in datasets:
                series = ds.get("data") or []
                value = series[idx] if idx < len(series) else ""
                row_cells.append(f"<td>{self._escape_html(value)}</td>")
            body_rows += f"<tr>{''.join(row_cells)}</tr>"
        table_html = f"""
        <div class="chart-fallback" data-prebuilt="true"{widget_attr}>
          <table>
            <thead>
              <tr><th>Category</th>{header_cells}</tr>
            </thead>
            <tbody>
              {body_rows}
            </tbody>
          </table>
        </div>"""
        return table_html

    def _render_wordcloud_fallback(
        self,
        props: Dict[str, Any] | None,
        widget_id: str | None = None,
        block_data: Any | None = None,
    ) -> str:
        """Provide table backends for word clouds to avoid blank pages after WordCloud rendering fails"""
        def _collect_items(raw: Any) -> list[dict]:
            """Organize multiple word cloud input formats (array/object/tuple/plain text) into a unified list of terms"""
            collected: list[dict] = []
            skip_keys = {"items", "data", "words", "labels", "datasets", "sourceData"}
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        text = item.get("word") or item.get("text") or item.get("label")
                        weight = item.get("weight")
                        category = item.get("category") or ""
                        if text:
                            collected.append({"word": str(text), "weight": weight, "category": str(category)})
                        # If the items/words/data list is nested, recursively extract
                        for nested_key in ("items", "words", "data"):
                            nested = item.get(nested_key)
                            if isinstance(nested, list):
                                collected.extend(_collect_items(nested))
                    elif isinstance(item, (list, tuple)) and item:
                        text = item[0]
                        weight = item[1] if len(item) > 1 else None
                        category = item[2] if len(item) > 2 else ""
                        if text:
                            collected.append({"word": str(text), "weight": weight, "category": str(category)})
                    elif isinstance(item, str):
                        collected.append({"word": item, "weight": 1.0, "category": ""})
            elif isinstance(raw, dict):
                # If the items/words/data list is included, recursive extraction is preferred and the key names are not treated as words.
                handled = False
                for nested_key in ("items", "words", "data"):
                    nested = raw.get(nested_key)
                    if isinstance(nested, list):
                        collected.extend(_collect_items(nested))
                        handled = True
                if handled:
                    return collected

                # When it is not a Chart structure and does not contain skip_keys, the key/value is treated as a word cloud entry.
                if not {"labels", "datasets"}.intersection(raw.keys()):
                    for text, weight in raw.items():
                        if text in skip_keys:
                            continue
                        collected.append({"word": str(text), "weight": weight, "category": ""})
            return collected

        words: list[dict] = []
        seen: set[str] = set()
        candidates = []
        if isinstance(props, dict):
            # Only accept explicit entry array fields to avoid mistaking nested items for entries
            if "data" in props and isinstance(props.get("data"), list):
                candidates.append(props["data"])
            if "words" in props and isinstance(props.get("words"), list):
                candidates.append(props["words"])
            if "items" in props and isinstance(props.get("items"), list):
                candidates.append(props["items"])
        candidates.append((props or {}).get("sourceData"))

        # Allows the use of block.data to avoid gaps when props are missing.
        if block_data is not None:
            if isinstance(block_data, dict) and "items" in block_data and isinstance(block_data.get("items"), list):
                candidates.append(block_data["items"])
            else:
                candidates.append(block_data)

        for raw in candidates:
            for item in _collect_items(raw):
                key = f"{item['word']}::{item.get('category','')}"
                if key in seen:
                    continue
                seen.add(key)
                words.append(item)

        if not words:
            return ""

        def _format_weight(value: Any) -> str:
            """Unified formatting of weights, supporting percentage/numeric and string fallback"""
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if 0 <= value <= 1.5:
                    return f"{value * 100:.1f}%"
                return f"{value:.2f}".rstrip("0").rstrip(".")
            return str(value)

        widget_attr = f' data-widget-id="{self._escape_attr(widget_id)}"' if widget_id else ""
        rows = "".join(
            f"<tr><td>{self._escape_html(item['word'])}</td>"
            f"<td>{self._escape_html(_format_weight(item['weight']))}</td>"
            f"<td>{self._escape_html(item['category'] or '-')}</td></tr>"
            for item in words
        )
        return f"""
        <div class="chart-fallback" data-prebuilt="true"{widget_attr}>
          <table>
            <thead>
              <tr><th>Keywords</th><th>Weight</th><th>Category</th></tr>
            </thead>
            <tbody>
              {rows}
            </tbody>
          </table>
        </div>"""

    def _log_chart_validation_stats(self):
        """Output chart validation statistics"""
        stats = self.chart_validation_stats
        if stats['total'] == 0:
            return

        logger.info("=" * 60)
        logger.info("Chart validation statistics")
        logger.info("=" * 60)
        logger.info(f"Total number of charts: {stats['total']}")
        logger.info(f"✓ Verification passed: {stats['valid']} ({stats['valid']/stats['total']*100:.1f}%)")

        if stats['repaired_locally'] > 0:
            logger.info(
                f"⚠ Local repair: {stats['repaired_locally']}"
                f"({stats['repaired_locally']/stats['total']*100:.1f}%)"
            )

        if stats['repaired_api'] > 0:
            logger.info(
                f"⚠ API fix: {stats['repaired_api']}"
                f"({stats['repaired_api']/stats['total']*100:.1f}%)"
            )

        if stats['failed'] > 0:
            logger.warning(
                f"✗ Repair failed: {stats['failed']}"
                f"({stats['failed']/stats['total']*100:.1f}%) - "
                f"These charts will show concise placeholder tips"
            )

        logger.info("=" * 60)

    # ====== Pre-information protection ======

    def _kpi_signature_from_items(self, items: Any) -> tuple | None:
        """Convert array of KPIs into comparable signatures"""
        if not isinstance(items, list):
            return None
        normalized = []
        for raw in items:
            normalized_item = self._normalize_kpi_item(raw)
            if normalized_item:
                normalized.append(normalized_item)
        return tuple(normalized) if normalized else None

    def _normalize_kpi_item(self, item: Any) -> tuple[str, str, str, str, str] | None:
        """Organize individual KPI records into comparable signatures.

        Parameters:
            item: The original dictionary in the KPI array, which may have missing fields or mixed types.

        Return:
            tuple | None: a five-tuple of (label, value, unit, delta, tone); if the input is invalid, it is None."""
        if not isinstance(item, dict):
            return None

        def normalize(value: Any) -> str:
            """Unify the representation of various values ​​to facilitate the generation of stable signatures"""
            if value is None:
                return ""
            if isinstance(value, (int, float)):
                return str(value)
            return str(value).strip()

        label = normalize(item.get("label"))
        value = normalize(item.get("value"))
        unit = normalize(item.get("unit"))
        delta = normalize(item.get("delta"))
        tone = normalize(item.get("deltaTone") or item.get("tone"))
        return label, value, unit, delta, tone

    def _should_skip_overview_kpi(self, block: Dict[str, Any]) -> bool:
        """If the KPI content is consistent with the cover, it will be determined as a duplicate overview."""
        if not self.hero_kpi_signature:
            return False
        block_signature = self._kpi_signature_from_items(block.get("items"))
        if not block_signature:
            return False
        return block_signature == self.hero_kpi_signature

    # ====== Inline rendering ======

    def _normalize_inline_payload(self, run: Dict[str, Any]) -> tuple[str, List[Dict[str, Any]]]:
        """Flatten nested inline nodes into basic text and marks"""
        if not isinstance(run, dict):
            return ("" if run is None else str(run)), []

        # Handle inlineRun types: recursively expand their inlines array
        if run.get("type") == "inlineRun":
            inner_inlines = run.get("inlines") or []
            outer_marks = run.get("marks") or []
            # Recursively merge text within all inlines
            texts = []
            all_marks = list(outer_marks)
            for inline in inner_inlines:
                inner_text, inner_marks = self._normalize_inline_payload(inline)
                texts.append(inner_text)
                all_marks.extend(inner_marks)
            return "".join(texts), all_marks

        marks = list(run.get("marks") or [])
        text_value: Any = run.get("text", "")
        seen: set[int] = set()

        while isinstance(text_value, dict):
            obj_id = id(text_value)
            if obj_id in seen:
                text_value = ""
                break
            seen.add(obj_id)
            nested_marks = text_value.get("marks")
            if nested_marks:
                marks.extend(nested_marks)
            if "text" in text_value:
                text_value = text_value.get("text")
            else:
                text_value = json.dumps(text_value, ensure_ascii=False)
                break

        if text_value is None:
            text_value = ""
        elif isinstance(text_value, (int, float)):
            text_value = str(text_value)
        elif not isinstance(text_value, str):
            try:
                text_value = json.dumps(text_value, ensure_ascii=False)
            except TypeError:
                text_value = str(text_value)

        if isinstance(text_value, str):
            stripped = text_value.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                payload = None
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    try:
                        payload = ast.literal_eval(stripped)
                    except (ValueError, SyntaxError):
                        payload = None
                if isinstance(payload, dict):
                    sentinel_keys = {"xrefs", "widgets", "footnotes", "errors", "metadata"}
                    if set(payload.keys()).issubset(sentinel_keys):
                        text_value = ""
                    else:
                        inline_payload = self._coerce_inline_payload(payload)
                        if inline_payload:
                            # Handling inlineRun types
                            if inline_payload.get("type") == "inlineRun":
                                return self._normalize_inline_payload(inline_payload)
                            nested_text = inline_payload.get("text")
                            if nested_text is not None:
                                text_value = nested_text
                            nested_marks = inline_payload.get("marks")
                            if isinstance(nested_marks, list):
                                marks.extend(nested_marks)
                        elif any(key in payload for key in self.INLINE_ARTIFACT_KEYS):
                            text_value = ""

        return text_value, marks

    @staticmethod
    def _normalize_latex_string(raw: Any) -> str:
        """Removes outer mathematical delimiters and is compatible with $...$, $$...$$, \\(\\), \\[\\] and other formats"""
        if not isinstance(raw, str):
            return ""
        latex = raw.strip()
        patterns = [
            r'^\$\$(.*)\$\$$',
            r'^\$(.*)\$$',
            r'^\\\[(.*)\\\]$',
            r'^\\\((.*)\\\)$',
        ]
        for pat in patterns:
            m = re.match(pat, latex, re.DOTALL)
            if m:
                latex = m.group(1).strip()
                break
        return latex

    def _render_text_with_inline_math(
        self,
        text: Any,
        math_id: str | list | None = None,
        allow_display_block: bool = False
    ) -> str | None:
        """Recognize math delimiters in plain text and render them as math-inline/math-block to improve compatibility.

        - Supports $...$, $$...$$, \\(\\), \\[\\].
        - If no formula is detected, None is returned."""
        if not isinstance(text, str) or not text:
            return None

        pattern = re.compile(r'(\$\$(.+?)\$\$|\$(.+?)\$|\\\((.+?)\\\)|\\\[(.+?)\\\])', re.S)
        matches = list(pattern.finditer(text))
        if not matches:
            return None

        cursor = 0
        parts: List[str] = []
        id_iter = iter(math_id) if isinstance(math_id, list) else None

        for idx, m in enumerate(matches, start=1):
            start, end = m.span()
            prefix = text[cursor:start]
            raw = next(g for g in m.groups()[1:] if g is not None)
            latex = self._normalize_latex_string(raw)
            # If math_id already exists, use it directly to avoid inconsistency with the SVG injection ID; otherwise, generate it according to the local serial number
            if id_iter:
                mid = next(id_iter, f"auto-math-{idx}")
            else:
                mid = math_id or f"auto-math-{idx}"
            id_attr = f' data-math-id="{self._escape_attr(mid)}"'
            is_display = m.group(1).startswith('$$') or m.group(1).startswith('\\[')
            is_standalone = (
                len(matches) == 1 and
                not text[:start].strip() and
                not text[end:].strip()
            )
            use_block = allow_display_block and is_display and is_standalone
            if use_block:
                # Independent display formula, skip the blanks on both sides, and directly render the block level
                parts.append(f'<div class="math-block"{id_attr}>$$ {self._escape_html(latex)} $$</div>')
                cursor = len(text)
                break
            else:
                if prefix:
                    parts.append(self._escape_html(prefix))
                parts.append(f'<span class="math-inline"{id_attr}>\\( {self._escape_html(latex)} \\)</span>')
            cursor = end

        if cursor < len(text):
            parts.append(self._escape_html(text[cursor:]))
        return "".join(parts)

    @staticmethod
    def _coerce_inline_payload(payload: Dict[str, Any]) -> Dict[str, Any] | None:
        """Try our best to restore inline nodes in strings to dict and fix rendering omissions"""
        if not isinstance(payload, dict):
            return None
        inline_type = payload.get("type")
        # Support for inlineRun type: contains nested inlines arrays
        if inline_type == "inlineRun":
            return payload
        if inline_type and inline_type not in {"inline", "text"}:
            return None
        if "text" not in payload and "marks" not in payload and "inlines" not in payload:
            return None
        return payload

    def _render_inline(self, run: Dict[str, Any]) -> str:
        """Render a single inline run and support the overlay of multiple marks.

        Parameters:
            run: Inline node containing text and marks.

        Return:
            str: HTML fragment wrapped with tags/styles."""
        text_value, marks = self._normalize_inline_payload(run)
        math_mark = next((mark for mark in marks if mark.get("type") == "math"), None)
        if math_mark:
            latex = self._normalize_latex_string(math_mark.get("value"))
            if not isinstance(latex, str) or not latex.strip():
                latex = self._normalize_latex_string(text_value)
            math_id = self._escape_attr(run.get("mathId", "")) if run.get("mathId") else ""
            id_attr = f' data-math-id="{math_id}"' if math_id else ""
            return f'<span class="math-inline"{id_attr}>\\( {self._escape_html(latex)} \\)</span>'

        # Try to extract mathematical formulas from plain text (even without math mark)
        math_id_hint = run.get("mathIds") or run.get("mathId")
        mathified = self._render_text_with_inline_math(text_value, math_id_hint)
        if mathified is not None:
            return mathified

        text = self._escape_html(text_value)
        styles: List[str] = []
        prefix: List[str] = []
        suffix: List[str] = []
        for mark in marks:
            mark_type = mark.get("type")
            if mark_type == "bold":
                prefix.append("<strong>")
                suffix.insert(0, "</strong>")
            elif mark_type == "italic":
                prefix.append("<em>")
                suffix.insert(0, "</em>")
            elif mark_type == "code":
                prefix.append("<code>")
                suffix.insert(0, "</code>")
            elif mark_type == "highlight":
                prefix.append("<mark>")
                suffix.insert(0, "</mark>")
            elif mark_type == "link":
                href_raw = mark.get("href")
                if href_raw and href_raw != "#":
                    href = self._escape_attr(href_raw)
                    title = self._escape_attr(mark.get("title") or "")
                    prefix.append(f'<a href="{href}" title="{title}" target="_blank" rel="noopener">')
                    suffix.insert(0, "</a>")
                else:
                    prefix.append('<span class="broken-link">')
                    suffix.insert(0, "</span>")
            elif mark_type == "color":
                value = mark.get("value")
                if value:
                    styles.append(f"color: {value}")
            elif mark_type == "font":
                family = mark.get("family")
                size = mark.get("size")
                weight = mark.get("weight")
                if family:
                    styles.append(f"font-family: {family}")
                if size:
                    styles.append(f"font-size: {size}")
                if weight:
                    styles.append(f"font-weight: {weight}")
            elif mark_type == "underline":
                styles.append("text-decoration: underline")
            elif mark_type == "strike":
                styles.append("text-decoration: line-through")
            elif mark_type == "subscript":
                prefix.append("<sub>")
                suffix.insert(0, "</sub>")
            elif mark_type == "superscript":
                prefix.append("<sup>")
                suffix.insert(0, "</sup>")

        if styles:
            style_attr = "; ".join(styles)
            prefix.insert(0, f'<span style="{style_attr}">')
            suffix.append("</span>")

        if not marks and "**" in (run.get("text") or ""):
            return self._render_markdown_bold_fallback(run.get("text", ""))

        return "".join(prefix) + text + "".join(suffix)

    def _render_markdown_bold_fallback(self, text: str) -> str:
        """Convert **Bold** when LLM is not using marks"""
        if not text:
            return ""
        result: List[str] = []
        cursor = 0
        while True:
            start = text.find("**", cursor)
            if start == -1:
                result.append(html.escape(text[cursor:]))
                break
            end = text.find("**", start + 2)
            if end == -1:
                result.append(html.escape(text[cursor:]))
                break
            result.append(html.escape(text[cursor:start]))
            bold_content = html.escape(text[start + 2:end])
            result.append(f"<strong>{bold_content}</strong>")
            cursor = end + 2
        return "".join(result)

    # ====== Text / Security Tools ======

    def _clean_text_from_json_artifacts(self, text: Any) -> str:
        """Clean JSON fragments and fake structure markup in text.

        LLM sometimes mixes in unfinished JSON fragments in text fields, like:"描述文本，{ \"chapterId\": \"S3" 或 "Description text, { \"level\": 2"

        此方法会：
        1. 移除不完整的JSON对象（以 { 开头但未正确闭合的）
        2. 移除不完整的JSON数组（以 [ 开头但未正确闭合的）
        3. 移除孤立的JSON键值对片段

        参数:
            text: 可能包含JSON片段的文本

        返回:
            str: 清理后的纯文本
        """
        if not text:
            return ""text_str = self._safe_text(text)

        # Mode 1: Remove incomplete JSON objects starting with comma+blank+{
        # For example:"ting with comma+blank+{
        # For example: "text,{ \"key\": \"value\"" or "text,{\\n \"key\""""
        text_str = re.sub(r',\s*\{[^}]*$', '', text_str)

        # Mode 2: Remove incomplete JSON arrays starting with comma+blank+[
        text_str = re.sub(r',\s*\[[^\]]*$', '', text_str)

        # Pattern 3: Remove orphaned { followed by content (if no matching })
        # Check if there is an unclosed {
        open_brace_pos = text_str.rfind('{')
        if open_brace_pos != -1:
            close_brace_pos = text_str.rfind('}')
            if close_brace_pos < open_brace_pos:
                # {After } or without }, it means it is unclosed
                # truncate before {
                text_str = text_str[:open_brace_pos].rstrip(',，、 \t\n')

        # Mode 4: Similar processing [
        open_bracket_pos = text_str.rfind('[')
        if open_bracket_pos != -1:
            close_bracket_pos = text_str.rfind(']')
            if close_bracket_pos < open_bracket_pos:
                # [After ] or without ], it means it is unclosed
                text_str = text_str[:open_bracket_pos].rstrip(',，、 \t\n')

        # Pattern 5: Remove fragments that look like JSON key-value pairs, such as "chapterId": "S3
        # This situation usually occurs after the above pattern
        text_str = re.sub(r',?\s*"rn
        text_str = re.sub(r',?\s*"[^"]+"\s*:\s*"[^"]*$', '', text_str)
        text_str = re.sub(r',?\s*"[^"]+"\s*:\s*[^,}\]]*$', '', text_str)

        # Clean up trailing commas and whitespace
        text_str = text_str.rstrip(',,, \t\n')

        return text_str.strip()

    def _safe_text(self, value: Any) -> str:"value: Any) -> str:
        """将任意值安全转换为字符串，None与复杂对象容错"""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)

    def _escape_html(self, value: Any) -> str:
        """HTML文本上下文的转义"""
        return html.escape(self._safe_text(value), quote=False)

    def _escape_attr(self, value: Any) -> str:
        """HTML属性上下文转义并去掉危险换行"""
        escaped = html.escape(self._safe_text(value), quote=True)
        return escaped.replace("\n", " ").replace("\r", " ")

    # ====== CSS/JS (Styles & Scripts) ======

    def _build_css(self, tokens: Dict[str, Any]) -> str:"
        """根据主题token拼接整页CSS，包括响应式与打印样式"""# Safely obtain each configuration item, ensuring that they are all dictionary types
        colors_raw = tokens.get(" they are all dictionary types
        colors_raw = tokens.get("colors")
        colors = colors_raw if isinstance(colors_raw, dict) else {}

        typography_raw = tokens.get("typography")
        typography = typography_raw if isinstance(typography_raw, dict) else {}

        # Get fonts safely, make sure it is a dictionary type
        fonts_raw = tokens.get("e
        fonts_raw = tokens.get("fonts") or typography.get("fonts")
        if isinstance(fonts_raw, dict):
            fonts = fonts_raw
        else:
            # If fonts is a string or None, construct a dictionary
            font_family = typography.get("font_family = typography.get("fontFamily")
            if isinstance(font_family, str):
                fonts = {"body": font_family, "heading": font_family}
            else:
                fonts = {}

        spacing_raw = tokens.get("spacing")
        spacing = spacing_raw if isinstance(spacing_raw, dict) else {}

        primary_palette = self._resolve_color_family(
            colors.get("primary"),
            {"main": "#1a365d", "light": "#2d3748", "dark": "#0f1a2d"},
        )
        secondary_palette = self._resolve_color_family(
            colors.get("secondary"),
            {"main": "#e53e3e", "light": "#fc8181", "dark": "#c53030"},
        )
        bg = self._resolve_color_value(
            colors.get("bg") or colors.get("background") or colors.get("surface"),
            "#f8f9fa",
        )
        text_color = self._resolve_color_value(
            colors.get("text") or colors.get("onBackground"),
            "#212529",
        )
        card = self._resolve_color_value(
            colors.get("card") or colors.get("surfaceCard"),
            "#ffffff",
        )
        border = self._resolve_color_value(
            colors.get("border") or colors.get("divider"),
            "#dee2e6",
        )
        shadow = "rgba(0,0,0,0.08)"
        container_width = spacing.get("container") or spacing.get("containerWidth") or "1200px"
        gutter = spacing.get("gutter") or spacing.get("pagePadding") or "24px"
        body_font = fonts.get("body") or fonts.get("primary") or "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
        heading_font = fonts.get("heading") or fonts.get("primary") or fonts.get("secondary") or body_font

        return f"""
:root {{ /* 含义：亮色主题变量区域；设置：在本块内调整相关属性 */
  --bg-color: {bg}; /* 含义：页面背景色主色调；设置：在 themeTokens 中覆盖或改此默认值 */
  --text-color: {text_color}; /* 含义：正文文本基础颜色；设置：在 themeTokens 中覆盖或改此默认值 */
  --primary-color: {primary_palette["main"]}; /* 含义：主色调（按钮/高亮）；设置：在 themeTokens 中覆盖或改此默认值 */
  --primary-color-light: {primary_palette["light"]}; /* 含义：主色调浅色，用于悬浮/渐变；设置：在 themeTokens 中覆盖或改此默认值 */
  --primary-color-dark: {primary_palette["dark"]}; /* 含义：主色调深色，用于强调；设置：在 themeTokens 中覆盖或改此默认值 */
  --secondary-color: {secondary_palette["main"]}; /* 含义：次级色（提示/标签）；设置：在 themeTokens 中覆盖或改此默认值 */
  --secondary-color-light: {secondary_palette["light"]}; /* 含义：次级色浅色；设置：在 themeTokens 中覆盖或改此默认值 */
  --secondary-color-dark: {secondary_palette["dark"]}; /* 含义：次级色深色；设置：在 themeTokens 中覆盖或改此默认值 */
  --card-bg: {card}; /* 含义：卡片/容器背景色；设置：在 themeTokens 中覆盖或改此默认值 */
  --border-color: {border}; /* 含义：常规边框色；设置：在 themeTokens 中覆盖或改此默认值 */
  --shadow-color: {shadow}; /* 含义：阴影基色；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-insight-bg: # f4f7ff; /* Meaning: Insight engine card background; setting: override or change this default value in themeTokens */
  --engine-insight-border: # dce7ff; /* Meaning: Insight engine border; setting: override or change this default value in themeTokens */
  --engine-insight-text: # 1f4b99; /* Meaning: Insight engine text color; setting: override or change this default value in themeTokens */
  --engine-media-bg: # fff6ec; /* Meaning: Media engine card background; setting: override or change this default value in themeTokens */
  --engine-media-border: # ffd9b3; /* Meaning: Media engine border; setting: override or change this default value in themeTokens */
  --engine-media-text: # b65a1a; /* Meaning: Media engine text color; setting: override or change this default value in themeTokens */
  --engine-query-bg: # f1fbf5; /* Meaning: Query engine card background; setting: override or change this default value in themeTokens */
  --engine-query-border: # c7ebd6; /* Meaning: Query engine border; setting: override or change this default value in themeTokens */
  --engine-query-text: # 1d6b3f; /* Meaning: Query engine text color; setting: override or change this default value in themeTokens */
  --engine-quote-shadow: 0 12px 30px rgba(0,0,0,0.04); /* 含义：Engine 引用阴影；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-strength: # 1c7f6e; /* Meaning: SWOT dominant main color; setting: override or change this default value in themeTokens */
  --swot-weakness: # c0392b; /* Meaning: SWOT disadvantage main color; setting: override or change this default value in themeTokens */
  --swot-opportunity: # 1f5ab3; /* Meaning: SWOT opportunity main color; setting: override or change this default value in themeTokens */
  --swot-threat: # b36b16; /* Meaning: SWOT threat main color; setting: override or change this default value in themeTokens */
  --swot-on-light: # 0f1b2b; /* Meaning: SWOT bright text color; setting: override or change this default value in themeTokens */
  --swot-on-dark: # f7fbff; /* Meaning: SWOT dark text color; setting: override or change this default value in themeTokens */
  --swot-text: var(--text-color); /* 含义：SWOT 文本主色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-muted: rgba(0,0,0,0.58); /* 含义：SWOT 次文本色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-surface: rgba(255,255,255,0.92); /* 含义：SWOT 卡片表面色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-chip-bg: rgba(0,0,0,0.04); /* 含义：SWOT 标签底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-tag-border: var(--border-color); /* 含义：SWOT 标签边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-card-bg: linear-gradient(135deg, rgba(76,132,255,0.04), rgba(28,127,110,0.06)), var(--card-bg); /* 含义：SWOT 卡片背景渐变；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-card-border: var(--border-color); /* 含义：SWOT 卡片边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-card-shadow: 0 14px 28px var(--shadow-color); /* 含义：SWOT 卡片阴影；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-card-blur: none; /* 含义：SWOT 卡片模糊；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-base: linear-gradient(135deg, rgba(255,255,255,0.9), rgba(255,255,255,0.5)); /* 含义：SWOT 象限基础底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-border: rgba(0,0,0,0.04); /* 含义：SWOT 象限边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-strength-bg: linear-gradient(135deg, rgba(28,127,110,0.07), rgba(255,255,255,0.78)), var(--card-bg); /* 含义：SWOT 优势象限底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-weakness-bg: linear-gradient(135deg, rgba(192,57,43,0.07), rgba(255,255,255,0.78)), var(--card-bg); /* 含义：SWOT 劣势象限底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-opportunity-bg: linear-gradient(135deg, rgba(31,90,179,0.07), rgba(255,255,255,0.78)), var(--card-bg); /* 含义：SWOT 机会象限底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-threat-bg: linear-gradient(135deg, rgba(179,107,22,0.07), rgba(255,255,255,0.78)), var(--card-bg); /* 含义：SWOT 威胁象限底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-strength-border: rgba(28,127,110,0.35); /* 含义：SWOT 优势边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-weakness-border: rgba(192,57,43,0.35); /* 含义：SWOT 劣势边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-opportunity-border: rgba(31,90,179,0.35); /* 含义：SWOT 机会边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-threat-border: rgba(179,107,22,0.35); /* 含义：SWOT 威胁边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-item-border: rgba(0,0,0,0.05); /* 含义：SWOT 条目边框；设置：在 themeTokens 中覆盖或改此默认值 */
  /* PEST 分析变量 - 紫青色系 */
  --pest-political: # 8e44ad; /* Meaning: PEST political dimension main color; setting: override or change this default value in themeTokens */
  --pest-economic: # 16a085; /* Meaning: PEST economic dimension main color; setting: override or change this default value in themeTokens */
  --pest-social: # e84393; /* Meaning: PEST social dimension main color; setting: override or change this default value in themeTokens */
  --pest-technological: # 2980b9; /* Meaning: Main color of PEST technical dimension; Setting: Override or change this default value in themeTokens */
  --pest-on-light: # 1a1a2e; /* Meaning: PEST bright text color; setting: override or change this default value in themeTokens */
  --pest-on-dark: # f8f9ff; /* Meaning: PEST dark text color; setting: override or change this default value in themeTokens */
  --pest-text: var(--text-color); /* 含义：PEST 文本主色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-muted: rgba(0,0,0,0.55); /* 含义：PEST 次文本色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-surface: rgba(255,255,255,0.88); /* 含义：PEST 卡片表面色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-chip-bg: rgba(0,0,0,0.05); /* 含义：PEST 标签底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-tag-border: var(--border-color); /* 含义：PEST 标签边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-card-bg: linear-gradient(145deg, rgba(142,68,173,0.03), rgba(22,160,133,0.04)), var(--card-bg); /* 含义：PEST 卡片背景渐变；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-card-border: var(--border-color); /* 含义：PEST 卡片边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-card-shadow: 0 16px 32px var(--shadow-color); /* 含义：PEST 卡片阴影；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-card-blur: none; /* 含义：PEST 卡片模糊；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-base: linear-gradient(90deg, rgba(255,255,255,0.95), rgba(255,255,255,0.7)); /* 含义：PEST 条带基础底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-border: rgba(0,0,0,0.06); /* 含义：PEST 条带边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-political-bg: linear-gradient(90deg, rgba(142,68,173,0.08), rgba(255,255,255,0.85)), var(--card-bg); /* 含义：PEST 政治条带底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-economic-bg: linear-gradient(90deg, rgba(22,160,133,0.08), rgba(255,255,255,0.85)), var(--card-bg); /* 含义：PEST 经济条带底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-social-bg: linear-gradient(90deg, rgba(232,67,147,0.08), rgba(255,255,255,0.85)), var(--card-bg); /* 含义：PEST 社会条带底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-technological-bg: linear-gradient(90deg, rgba(41,128,185,0.08), rgba(255,255,255,0.85)), var(--card-bg); /* 含义：PEST 技术条带底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-political-border: rgba(142,68,173,0.4); /* 含义：PEST 政治条带边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-economic-border: rgba(22,160,133,0.4); /* 含义：PEST 经济条带边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-social-border: rgba(232,67,147,0.4); /* 含义：PEST 社会条带边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-technological-border: rgba(41,128,185,0.4); /* 含义：PEST 技术条带边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-item-border: rgba(0,0,0,0.06); /* 含义：PEST 条目边框；设置：在 themeTokens 中覆盖或改此默认值 */
}} /* 结束 :root */
.dark-mode {{ /* 含义：暗色主题变量区域；设置：在本块内调整相关属性 */
  --bg-color: # 121212; /* Meaning: Main color of page background color; Setting: Override or change this default value in themeTokens */
  --text-color: # e0e0e0; /* Meaning: basic text color; setting: override or change this default value in themeTokens */
  --primary-color: # 6ea8fe; /* Meaning: main color (button/highlight); setting: override or change this default value in themeTokens */
  --primary-color-light: # 91caff; /* Meaning: light main color, used for suspension/gradient; setting: override or change this default value in themeTokens */
  --primary-color-dark: # 1f6feb; /* Meaning: Main color is dark, used for emphasis; Setting: Override or change this default value in themeTokens */
  --secondary-color: # f28b82; /* Meaning: secondary color (prompt/label); setting: override or change this default value in themeTokens */
  --secondary-color-light: # f9b4ae; /* Meaning: light secondary color; setting: override or change this default value in themeTokens */
  --secondary-color-dark: # d9655c; /* Meaning: secondary color is dark; setting: override or change this default value in themeTokens */
  --card-bg: # 1f1f1f; /* Meaning: card/container background color; setting: override or change this default value in themeTokens */
  --border-color: # 2c2c2c; /* Meaning: regular border color; setting: override or change this default value in themeTokens */
  --shadow-color: rgba(0, 0, 0, 0.4); /* 含义：阴影基色；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-insight-bg: rgba(145, 202, 255, 0.08); /* 含义：Insight 引擎卡片背景；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-insight-border: rgba(145, 202, 255, 0.45); /* 含义：Insight 引擎边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-insight-text: # 9dc2ff; /* Meaning: Insight engine text color; setting: override or change this default value in themeTokens */
  --engine-media-bg: rgba(255, 196, 138, 0.08); /* 含义：Media 引擎卡片背景；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-media-border: rgba(255, 196, 138, 0.45); /* 含义：Media 引擎边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-media-text: # ffcb9b; /* Meaning: Media engine text color; setting: override or change this default value in themeTokens */
  --engine-query-bg: rgba(141, 215, 165, 0.08); /* 含义：Query 引擎卡片背景；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-query-border: rgba(141, 215, 165, 0.45); /* 含义：Query 引擎边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-query-text: # a7e2ba; /* Meaning: Query engine text color; setting: override or change this default value in themeTokens */
  --engine-quote-shadow: 0 12px 28px rgba(0, 0, 0, 0.35); /* 含义：Engine 引用阴影；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-strength: # 1c7f6e; /* Meaning: SWOT dominant main color; setting: override or change this default value in themeTokens */
  --swot-weakness: # e06754; /* Meaning: SWOT disadvantage main color; setting: override or change this default value in themeTokens */
  --swot-opportunity: # 5a8cff; /* Meaning: SWOT opportunity main color; setting: override or change this default value in themeTokens */
  --swot-threat: # d48a2c; /* Meaning: SWOT threat main color; setting: override or change this default value in themeTokens */
  --swot-on-light: # 0f1b2b; /* Meaning: SWOT bright text color; setting: override or change this default value in themeTokens */
  --swot-on-dark: # e6f0ff; /* Meaning: SWOT dark text color; setting: override or change this default value in themeTokens */
  --swot-text: # e6f0ff; /* Meaning: SWOT text main color; setting: override or change this default value in themeTokens */
  --swot-muted: rgba(230,240,255,0.75); /* 含义：SWOT 次文本色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-surface: rgba(255,255,255,0.08); /* 含义：SWOT 卡片表面色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-chip-bg: rgba(255,255,255,0.14); /* 含义：SWOT 标签底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-tag-border: rgba(255,255,255,0.24); /* 含义：SWOT 标签边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-card-bg: radial-gradient(140% 140% at 18% 18%, rgba(110,168,254,0.18), transparent 55%), radial-gradient(120% 140% at 82% 0%, rgba(28,127,110,0.16), transparent 52%), linear-gradient(160deg, # 0b1424 0%, #0b1f31 52%, #0a1626 100%); /* Meaning: SWOT card background gradient; setting: override or change this default value in themeTokens */
  --swot-card-border: rgba(255,255,255,0.14); /* 含义：SWOT 卡片边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-card-shadow: 0 24px 60px rgba(0, 0, 0, 0.58); /* 含义：SWOT 卡片阴影；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-card-blur: blur(12px); /* 含义：SWOT 卡片模糊；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-base: linear-gradient(135deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02)); /* 含义：SWOT 象限基础底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-border: rgba(255,255,255,0.2); /* 含义：SWOT 象限边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-strength-bg: linear-gradient(150deg, rgba(28,127,110,0.28), rgba(28,127,110,0.12)), var(--swot-cell-base); /* 含义：SWOT 优势象限底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-weakness-bg: linear-gradient(150deg, rgba(192,57,43,0.32), rgba(192,57,43,0.14)), var(--swot-cell-base); /* 含义：SWOT 劣势象限底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-opportunity-bg: linear-gradient(150deg, rgba(31,90,179,0.28), rgba(31,90,179,0.12)), var(--swot-cell-base); /* 含义：SWOT 机会象限底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-threat-bg: linear-gradient(150deg, rgba(179,107,22,0.32), rgba(179,107,22,0.14)), var(--swot-cell-base); /* 含义：SWOT 威胁象限底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-strength-border: rgba(28,127,110,0.65); /* 含义：SWOT 优势边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-weakness-border: rgba(192,57,43,0.68); /* 含义：SWOT 劣势边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-opportunity-border: rgba(31,90,179,0.68); /* 含义：SWOT 机会边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-cell-threat-border: rgba(179,107,22,0.68); /* 含义：SWOT 威胁边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --swot-item-border: rgba(255,255,255,0.14); /* 含义：SWOT 条目边框；设置：在 themeTokens 中覆盖或改此默认值 */
  /* PEST 分析变量 - 暗色模式 */
  --pest-political: # a569bd; /* Meaning: PEST political dimension main color; setting: override or change this default value in themeTokens */
  --pest-economic: # 48c9b0; /* Meaning: PEST economic dimension main color; setting: override or change this default value in themeTokens */
  --pest-social: # f06292; /* Meaning: PEST social dimension main color; setting: override or change this default value in themeTokens */
  --pest-technological: # 5dade2; /* Meaning: Main color of PEST technical dimension; Setting: Override or change this default value in themeTokens */
  --pest-on-light: # 1a1a2e; /* Meaning: PEST bright text color; setting: override or change this default value in themeTokens */
  --pest-on-dark: # f0f4ff; /* Meaning: PEST dark text color; setting: override or change this default value in themeTokens */
  --pest-text: # f0f4ff; /* Meaning: PEST text main color; setting: override or change this default value in themeTokens */
  --pest-muted: rgba(240,244,255,0.7); /* 含义：PEST 次文本色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-surface: rgba(255,255,255,0.06); /* 含义：PEST 卡片表面色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-chip-bg: rgba(255,255,255,0.12); /* 含义：PEST 标签底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-tag-border: rgba(255,255,255,0.22); /* 含义：PEST 标签边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-card-bg: radial-gradient(130% 130% at 15% 15%, rgba(165,105,189,0.16), transparent 50%), radial-gradient(110% 130% at 85% 5%, rgba(72,201,176,0.14), transparent 48%), linear-gradient(155deg, # 12162a 0%, #161b30 50%, #0f1425 100%); /* Meaning: PEST card background gradient; setting: override or change this default value in themeTokens */
  --pest-card-border: rgba(255,255,255,0.12); /* 含义：PEST 卡片边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-card-shadow: 0 28px 65px rgba(0, 0, 0, 0.55); /* 含义：PEST 卡片阴影；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-card-blur: blur(10px); /* 含义：PEST 卡片模糊；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-base: linear-gradient(90deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02)); /* 含义：PEST 条带基础底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-border: rgba(255,255,255,0.18); /* 含义：PEST 条带边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-political-bg: linear-gradient(90deg, rgba(142,68,173,0.25), rgba(142,68,173,0.1)), var(--pest-strip-base); /* 含义：PEST 政治条带底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-economic-bg: linear-gradient(90deg, rgba(22,160,133,0.25), rgba(22,160,133,0.1)), var(--pest-strip-base); /* 含义：PEST 经济条带底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-social-bg: linear-gradient(90deg, rgba(232,67,147,0.25), rgba(232,67,147,0.1)), var(--pest-strip-base); /* 含义：PEST 社会条带底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-technological-bg: linear-gradient(90deg, rgba(41,128,185,0.25), rgba(41,128,185,0.1)), var(--pest-strip-base); /* 含义：PEST 技术条带底色；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-political-border: rgba(165,105,189,0.6); /* 含义：PEST 政治条带边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-economic-border: rgba(72,201,176,0.6); /* 含义：PEST 经济条带边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-social-border: rgba(240,98,146,0.6); /* 含义：PEST 社会条带边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-strip-technological-border: rgba(93,173,226,0.6); /* 含义：PEST 技术条带边框；设置：在 themeTokens 中覆盖或改此默认值 */
  --pest-item-border: rgba(255,255,255,0.12); /* 含义：PEST 条目边框；设置：在 themeTokens 中覆盖或改此默认值 */
}} /* 结束 .dark-mode */
* {{ box-sizing: border-box; }} /* 含义：全局统一盒模型，避免内外边距计算误差；设置：通常保持 border-box，如需原生行为可改为 content-box */
body {{ /* 含义：全局排版与背景设置；设置：在本块内调整相关属性 */
  margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  font-family: {body_font}; /* 含义：字体族；设置：按需调整数值/颜色/变量 */
  background: linear-gradient(180deg, rgba(0,0,0,0.04), rgba(0,0,0,0)) fixed, var(--bg-color); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  color: var(--text-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  line-height: 1.7; /* 含义：行高，提升可读性；设置：按需调整数值/颜色/变量 */
  min-height: 100vh; /* 含义：最小高度，防止塌陷；设置：按需调整数值/颜色/变量 */
  transition: background-color 0.45s ease, color 0.45s ease; /* 含义：过渡动画时长/属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 body */
.report-header, main, .hero-section, .chapter, .chart-card, .callout, .engine-quote, .kpi-card, .toc, .table-wrap {{ /* 含义：常用容器的统一过渡动画；设置：在本块内调整相关属性 */
  transition: background-color 0.45s ease, color 0.45s ease, border-color 0.45s ease, box-shadow 0.45s ease; /* 含义：过渡动画时长/属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .report-header, main, .hero-section, .chapter, .chart-card, .callout, .engine-quote, .kpi-card, .toc, .table-wrap */
.report-header {{ /* 含义：页眉吸顶区域；设置：在本块内调整相关属性 */
  position: sticky; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
  top: 0; /* 含义：顶部偏移量；设置：按需调整数值/颜色/变量 */
  z-index: 10; /* 含义：层叠顺序；设置：按需调整数值/颜色/变量 */
  background: var(--card-bg); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  padding: 20px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-bottom: 1px solid var(--border-color); /* 含义：底部边框；设置：按需调整数值/颜色/变量 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  align-items: center; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  justify-content: space-between; /* 含义：flex 主轴对齐；设置：按需调整数值/颜色/变量 */
  gap: 16px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 2px 6px var(--shadow-color); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .report-header */
.tagline {{ /* 含义：标题标语行；设置：在本块内调整相关属性 */
  margin: 4px 0 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  font-size: 0.95rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .tagline */
.hero-section {{ /* 含义：封面摘要主容器；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
  gap: 24px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  padding: 24px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 20px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  background: linear-gradient(135deg, rgba(0,123,255,0.1), rgba(23,162,184,0.1)); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  border: 1px solid rgba(0,0,0,0.08); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  margin-bottom: 32px; /* 含义：margin-bottom 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .hero-section */
.hero-content {{ /* 含义：封面左侧文字区；设置：在本块内调整相关属性 */
  flex: 2; /* 含义：flex 占位比例；设置：按需调整数值/颜色/变量 */
  min-width: 260px; /* 含义：最小宽度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .hero-content */
.hero-side {{ /* 含义：封面右侧 KPI 栏；设置：在本块内调整相关属性 */
  flex: 1; /* 含义：flex 占位比例；设置：按需调整数值/颜色/变量 */
  min-width: 220px; /* 含义：最小宽度；设置：按需调整数值/颜色/变量 */
  display: grid; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); /* 含义：网格列模板；设置：按需调整数值/颜色/变量 */
  gap: 12px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
}} /* 结束 .hero-side */
@media screen {{
  .hero-side {{
    margin-top: 28px; /* 含义：仅在屏幕显示时下移，避免遮挡；设置：按需调整数值 */
  }}
}}
.hero-kpi {{ /* 含义：封面 KPI 卡片；设置：在本块内调整相关属性 */
  background: var(--card-bg); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  border-radius: 14px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  padding: 16px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 6px 16px var(--shadow-color); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .hero-kpi */
.hero-kpi .label {{ /* 含义：.hero-kpi .label 样式区域；设置：在本块内调整相关属性 */
  font-size: 0.9rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .hero-kpi .label */
.hero-kpi .value {{ /* 含义：.hero-kpi .value 样式区域；设置：在本块内调整相关属性 */
  font-size: 1.8rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 700; /* 含义：字重；设置：按需调整数值/颜色/变量 */
}} /* 结束 .hero-kpi .value */
.hero-highlights {{ /* 含义：封面亮点列表；设置：在本块内调整相关属性 */
  list-style: none; /* 含义：列表样式；设置：按需调整数值/颜色/变量 */
  padding: 0; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  margin: 16px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
  gap: 10px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
}} /* 结束 .hero-highlights */
.hero-highlights li {{ /* 含义：.hero-highlights li 样式区域；设置：在本块内调整相关属性 */
  margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .hero-highlights li */
.badge {{ /* 含义：徽章标签；设置：在本块内调整相关属性 */
  display: inline-flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  align-items: center; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  padding: 6px 12px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 999px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  background: rgba(0,0,0,0.05); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  font-size: 0.9rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .badge */
.broken-link {{ /* 含义：无效链接提示样式；设置：在本块内调整相关属性 */
  text-decoration: underline dotted; /* 含义：文本装饰；设置：按需调整数值/颜色/变量 */
  color: var(--primary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .broken-link */
.hero-actions {{ /* 含义：封面操作按钮容器；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
  gap: 12px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
}} /* 结束 .hero-actions */
.ghost-btn {{ /* 含义：次级按钮样式；设置：在本块内调整相关属性 */
  border: 1px solid var(--primary-color); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  background: transparent; /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  color: var(--primary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  border-radius: 999px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  padding: 8px 16px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  cursor: pointer; /* 含义：鼠标指针样式；设置：按需调整数值/颜色/变量 */
}} /* 结束 .ghost-btn */
.hero-summary {{ /* 含义：封面摘要文字；设置：在本块内调整相关属性 */
  font-size: 1.05rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 500; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  margin-top: 0; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .hero-summary */
.llm-error-block {{ /* 含义：LLM 错误提示容器；设置：在本块内调整相关属性 */
  border: 1px dashed var(--secondary-color); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  border-radius: 12px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  padding: 12px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  margin: 12px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  background: rgba(229,62,62,0.06); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  position: relative; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
}} /* 结束 .llm-error-block */
.llm-error-block.importance-critical {{ /* 含义：.llm-error-block.importance-critical 样式区域；设置：在本块内调整相关属性 */
  border-color: var(--secondary-color-dark); /* 含义：border-color 样式属性；设置：按需调整数值/颜色/变量 */
  background: rgba(229,62,62,0.12); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .llm-error-block.importance-critical */
.llm-error-block::after {{ /* 含义：.llm-error-block::after 样式区域；设置：在本块内调整相关属性 */
  content: attr(data-raw); /* 含义：content 样式属性；设置：按需调整数值/颜色/变量 */
  white-space: pre-wrap; /* 含义：空白与换行策略；设置：按需调整数值/颜色/变量 */
  position: absolute; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
  left: 0; /* 含义：left 样式属性；设置：按需调整数值/颜色/变量 */
  right: 0; /* 含义：right 样式属性；设置：按需调整数值/颜色/变量 */
  bottom: 100%; /* 含义：bottom 样式属性；设置：按需调整数值/颜色/变量 */
  max-height: 240px; /* 含义：max-height 样式属性；设置：按需调整数值/颜色/变量 */
  overflow: auto; /* 含义：溢出处理；设置：按需调整数值/颜色/变量 */
  background: rgba(0,0,0,0.85); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  color: # fff; /* Meaning: text color; setting: adjust value/color/variable as needed */
  font-size: 0.85rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  padding: 12px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 10px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  margin-bottom: 8px; /* 含义：margin-bottom 样式属性；设置：按需调整数值/颜色/变量 */
  opacity: 0; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
  pointer-events: none; /* 含义：pointer-events 样式属性；设置：按需调整数值/颜色/变量 */
  transition: opacity 0.2s ease; /* 含义：过渡动画时长/属性；设置：按需调整数值/颜色/变量 */
  z-index: 20; /* 含义：层叠顺序；设置：按需调整数值/颜色/变量 */
}} /* 结束 .llm-error-block::after */
.llm-error-block:hover::after {{ /* 含义：.llm-error-block:hover::after 样式区域；设置：在本块内调整相关属性 */
  opacity: 1; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .llm-error-block:hover::after */
.report-header h1 {{ /* 含义：页眉主标题；设置：在本块内调整相关属性 */
  margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  font-size: 1.6rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  color: var(--primary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .report-header h1 */
.report-header .subtitle {{ /* 含义：页眉副标题；设置：在本块内调整相关属性 */
  margin: 4px 0 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .report-header .subtitle */
.header-actions {{ /* 含义：页眉按钮组；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  gap: 12px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
  align-items: center; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
}} /* 结束 .header-actions */
theme-button {{ /* 含义：主题切换组件；设置：在本块内调整相关属性 */
  display: inline-block; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  vertical-align: middle; /* 含义：vertical-align 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 theme-button */
.cover {{ /* 含义：封面区域；设置：在本块内调整相关属性 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  margin: 20px 0 40px; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .cover */
.cover h1 {{ /* 含义：.cover h1 样式区域；设置：在本块内调整相关属性 */
  font-size: 2.4rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  margin: 0.4em 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .cover h1 */
.cover-hint {{ /* 含义：.cover-hint 样式区域；设置：在本块内调整相关属性 */
  letter-spacing: 0.4em; /* 含义：字间距；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  font-size: 0.95rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .cover-hint */
.cover-subtitle {{ /* 含义：.cover-subtitle 样式区域；设置：在本块内调整相关属性 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .cover-subtitle */
.action-btn {{ /* 含义：主按钮基础样式；设置：在本块内调整相关属性 */
  --mouse-x: 50%; /* 含义：主题变量 mouse-x；设置：在 themeTokens 中覆盖或改此默认值 */
  --mouse-y: 50%; /* 含义：主题变量 mouse-y；设置：在 themeTokens 中覆盖或改此默认值 */
  border: none; /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  border-radius: 10px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  color: # fff; /* Meaning: text color; setting: adjust value/color/variable as needed */
  padding: 11px 22px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  cursor: pointer; /* 含义：鼠标指针样式；设置：按需调整数值/颜色/变量 */
  font-size: 0.92rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  letter-spacing: 0.025em; /* 含义：字间距；设置：按需调整数值/颜色/变量 */
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1); /* 含义：过渡动画时长/属性；设置：按需调整数值/颜色/变量 */
  min-width: 140px; /* 含义：最小宽度；设置：按需调整数值/颜色/变量 */
  white-space: nowrap; /* 含义：空白与换行策略；设置：按需调整数值/颜色/变量 */
  display: inline-flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  align-items: center; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  justify-content: center; /* 含义：flex 主轴对齐；设置：按需调整数值/颜色/变量 */
  gap: 10px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.12), 0 2px 6px rgba(0, 0, 0, 0.08); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
  position: relative; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
  overflow: hidden; /* 含义：溢出处理；设置：按需调整数值/颜色/变量 */
}} /* 结束 .action-btn */
.action-btn::before {{ /* 含义：.action-btn::before 样式区域；设置：在本块内调整相关属性 */
  content: ''; /* 含义：content 样式属性；设置：按需调整数值/颜色/变量 */
  position: absolute; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
  top: 0; /* 含义：顶部偏移量；设置：按需调整数值/颜色/变量 */
  left: 0; /* 含义：left 样式属性；设置：按需调整数值/颜色/变量 */
  width: 100%; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  height: 100%; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
  background: linear-gradient(to bottom, rgba(255,255,255,0.12), transparent); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  opacity: 0; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
  transition: opacity 0.35s ease; /* 含义：过渡动画时长/属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .action-btn::before */
.action-btn::after {{ /* 含义：.action-btn::after 样式区域；设置：在本块内调整相关属性 */
  content: ''; /* 含义：content 样式属性；设置：按需调整数值/颜色/变量 */
  position: absolute; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
  top: var(--mouse-y); /* 含义：顶部偏移量；设置：按需调整数值/颜色/变量 */
  left: var(--mouse-x); /* 含义：left 样式属性；设置：按需调整数值/颜色/变量 */
  width: 0; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  height: 0; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
  background: radial-gradient(circle, rgba(255,255,255,0.18) 0%, transparent 70%); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  border-radius: 50%; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  transform: translate(-50%, -50%); /* 含义：transform 样式属性；设置：按需调整数值/颜色/变量 */
  transition: width 0.45s ease-out, height 0.45s ease-out; /* 含义：过渡动画时长/属性；设置：按需调整数值/颜色/变量 */
  pointer-events: none; /* 含义：pointer-events 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .action-btn::after */
.action-btn:hover {{ /* 含义：.action-btn:hover 样式区域；设置：在本块内调整相关属性 */
  transform: translateY(-2px); /* 含义：transform 样式属性；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.18), 0 4px 10px rgba(0, 0, 0, 0.1); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .action-btn:hover */
.action-btn:hover::before {{ /* 含义：.action-btn:hover::before 样式区域；设置：在本块内调整相关属性 */
  opacity: 1; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .action-btn:hover::before */
.action-btn:hover::after {{ /* 含义：.action-btn:hover::after 样式区域；设置：在本块内调整相关属性 */
  width: 280%; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  height: 280%; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
}} /* 结束 .action-btn:hover::after */
.action-btn:active {{ /* 含义：.action-btn:active 样式区域；设置：在本块内调整相关属性 */
  transform: translateY(0) scale(0.98); /* 含义：transform 样式属性；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .action-btn:active */
.action-btn .btn-icon {{ /* 含义：.action-btn .btn-icon 样式区域；设置：在本块内调整相关属性 */
  width: 18px; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  height: 18px; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
  flex-shrink: 0; /* 含义：flex-shrink 样式属性；设置：按需调整数值/颜色/变量 */
  filter: drop-shadow(0 1px 1px rgba(0,0,0,0.15)); /* 含义：滤镜效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .action-btn .btn-icon */
.theme-toggle-btn .sun-icon,
.theme-toggle-btn .moon-icon {{ /* 含义：主题切换按钮图标样式；设置：在本块内调整相关属性 */
  transition: transform 0.3s ease, opacity 0.3s ease; /* 含义：过渡动画时长/属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .theme-toggle-btn 图标 */
.theme-toggle-btn .sun-icon {{ /* 含义：太阳图标样式；设置：在本块内调整相关属性 */
  color: # F59E0B; /* Meaning: sun icon color; settings: adjust value/color/variable as needed */
  stroke: # F59E0B; /* Meaning: Sun icon stroke color; Settings: Adjust value/color/variable as needed */
}} /* 结束 .theme-toggle-btn .sun-icon */
.theme-toggle-btn .moon-icon {{ /* 含义：月亮图标样式；设置：在本块内调整相关属性 */
  color: # 6366F1; /* Meaning: Moon icon color; Settings: Adjust value/color/variable as needed */
  stroke: # 6366F1; /* Meaning: moon icon stroke color; settings: adjust value/color/variable as needed */
}} /* 结束 .theme-toggle-btn .moon-icon */
.theme-toggle-btn:hover .sun-icon {{ /* 含义：悬停时太阳图标效果；设置：在本块内调整相关属性 */
  transform: rotate(15deg); /* 含义：旋转变换；设置：按需调整数值/颜色/变量 */
}} /* 结束 .theme-toggle-btn:hover .sun-icon */
.theme-toggle-btn:hover .moon-icon {{ /* 含义：悬停时月亮图标效果；设置：在本块内调整相关属性 */
  transform: rotate(-15deg) scale(1.1); /* 含义：旋转和缩放变换；设置：按需调整数值/颜色/变量 */
}} /* 结束 .theme-toggle-btn:hover .moon-icon */
body.exporting {{ /* 含义：body.exporting 样式区域；设置：在本块内调整相关属性 */
  cursor: progress; /* 含义：鼠标指针样式；设置：按需调整数值/颜色/变量 */
}} /* 结束 body.exporting */
.export-overlay {{ /* 含义：导出遮罩层；设置：在本块内调整相关属性 */
  position: fixed; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
  inset: 0; /* 含义：inset 样式属性；设置：按需调整数值/颜色/变量 */
  background: rgba(3, 9, 26, 0.55); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  backdrop-filter: blur(2px); /* 含义：背景模糊；设置：按需调整数值/颜色/变量 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  align-items: center; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  justify-content: center; /* 含义：flex 主轴对齐；设置：按需调整数值/颜色/变量 */
  opacity: 0; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
  pointer-events: none; /* 含义：pointer-events 样式属性；设置：按需调整数值/颜色/变量 */
  transition: opacity 0.3s ease; /* 含义：过渡动画时长/属性；设置：按需调整数值/颜色/变量 */
  z-index: 999; /* 含义：层叠顺序；设置：按需调整数值/颜色/变量 */
}} /* 结束 .export-overlay */
.export-overlay.active {{ /* 含义：.export-overlay.active 样式区域；设置：在本块内调整相关属性 */
  opacity: 1; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
  pointer-events: all; /* 含义：pointer-events 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .export-overlay.active */
.export-dialog {{ /* 含义：.export-dialog 样式区域；设置：在本块内调整相关属性 */
  background: rgba(12, 19, 38, 0.92); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  padding: 24px 32px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 18px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  color: # fff; /* Meaning: text color; setting: adjust value/color/variable as needed */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  min-width: 280px; /* 含义：最小宽度；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 16px 40px rgba(0,0,0,0.45); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .export-dialog */
.export-spinner {{ /* 含义：.export-spinner 样式区域；设置：在本块内调整相关属性 */
  width: 48px; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  height: 48px; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
  border-radius: 50%; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  border: 3px solid rgba(255,255,255,0.2); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  border-top-color: var(--secondary-color); /* 含义：border-top-color 样式属性；设置：按需调整数值/颜色/变量 */
  margin: 0 auto 16px; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  animation: export-spin 1s linear infinite; /* 含义：animation 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .export-spinner */
.export-status {{ /* 含义：.export-status 样式区域；设置：在本块内调整相关属性 */
  margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  font-size: 1rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .export-status */
.exporting *,
.exporting *::before, /* 含义：.exporting * 样式属性；设置：按需调整数值/颜色/变量 */
.exporting *::after {{ /* 含义：.exporting *::after 样式区域；设置：在本块内调整相关属性 */
  animation: none !important; /* 含义：animation 样式属性；设置：按需调整数值/颜色/变量 */
  transition: none !important; /* 含义：过渡动画时长/属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .exporting *::after */
.export-progress {{ /* 含义：.export-progress 样式区域；设置：在本块内调整相关属性 */
  width: 220px; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  height: 6px; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
  background: rgba(255,255,255,0.25); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  border-radius: 999px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  overflow: hidden; /* 含义：溢出处理；设置：按需调整数值/颜色/变量 */
  margin: 20px auto 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  position: relative; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
}} /* 结束 .export-progress */
.export-progress-bar {{ /* 含义：.export-progress-bar 样式区域；设置：在本块内调整相关属性 */
  position: absolute; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
  top: 0; /* 含义：顶部偏移量；设置：按需调整数值/颜色/变量 */
  bottom: 0; /* 含义：bottom 样式属性；设置：按需调整数值/颜色/变量 */
  width: 45%; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  border-radius: inherit; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  background: linear-gradient(90deg, var(--primary-color), var(--secondary-color)); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  animation: export-progress 1.4s ease-in-out infinite; /* 含义：animation 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .export-progress-bar */
@keyframes export-spin {{ /* 含义：@keyframes export-spin 样式区域；设置：在本块内调整相关属性 */
  from {{ transform: rotate(0deg); }} /* 含义：关键帧起点，保持 0° 角度；设置：可改为其他起始旋转或缩放状态 */
  to {{ transform: rotate(360deg); }} /* 含义：关键帧终点，旋转一圈；设置：可改为自定义终态角度/效果 */
}} /* 结束 @keyframes export-spin */
@keyframes export-progress {{ /* 含义：@keyframes export-progress 样式区域；设置：在本块内调整相关属性 */
  0% {{ left: -45%; }} /* 含义：进度动画起点，条形从左侧之外进入；设置：调整起始 left 百分比 */
  50% {{ left: 20%; }} /* 含义：进度动画中点，条形位于容器中段；设置：按需调整偏移比例 */
  100% {{ left: 110%; }} /* 含义：进度动画终点，条形滑出右侧；设置：调整收尾 left 百分比 */
}} /* 结束 @keyframes export-progress */
main {{ /* 含义：主体内容容器；设置：在本块内调整相关属性 */
  max-width: {container_width}; /* 含义：最大宽度；设置：按需调整数值/颜色/变量 */
  margin: 40px auto; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  padding: {gutter}; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  background: var(--card-bg); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  border-radius: 16px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 10px 30px var(--shadow-color); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 main */
h1, h2, h3, h4, h5, h6 {{ /* 含义：标题通用样式；设置：在本块内调整相关属性 */
  font-family: {heading_font}; /* 含义：字体族；设置：按需调整数值/颜色/变量 */
  color: var(--text-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  margin-top: 2em; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
  margin-bottom: 0.6em; /* 含义：margin-bottom 样式属性；设置：按需调整数值/颜色/变量 */
  line-height: 1.35; /* 含义：行高，提升可读性；设置：按需调整数值/颜色/变量 */
}} /* 结束 h1, h2, h3, h4, h5, h6 */
h2 {{ /* 含义：h2 样式区域；设置：在本块内调整相关属性 */
  font-size: 1.9rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 h2 */
h3 {{ /* 含义：h3 样式区域；设置：在本块内调整相关属性 */
  font-size: 1.4rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 h3 */
h4 {{ /* 含义：h4 样式区域；设置：在本块内调整相关属性 */
  font-size: 1.2rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 h4 */
p {{ /* 含义：段落样式；设置：在本块内调整相关属性 */
  margin: 1em 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  text-align: justify; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
}} /* 结束 p */
ul, ol {{ /* 含义：列表样式；设置：在本块内调整相关属性 */
  margin-left: 1.5em; /* 含义：margin-left 样式属性；设置：按需调整数值/颜色/变量 */
  padding-left: 0; /* 含义：左侧内边距/缩进；设置：按需调整数值/颜色/变量 */
}} /* 结束 ul, ol */
img, canvas, svg {{ /* 含义：媒体元素尺寸限制；设置：在本块内调整相关属性 */
  max-width: 100%; /* 含义：最大宽度；设置：按需调整数值/颜色/变量 */
  height: auto; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
}} /* 结束 img, canvas, svg */
.meta-card {{ /* 含义：元信息卡片；设置：在本块内调整相关属性 */
  background: rgba(0,0,0,0.02); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  border-radius: 12px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  padding: 20px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--border-color); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
}} /* 结束 .meta-card */
.meta-card ul {{ /* 含义：.meta-card ul 样式区域；设置：在本块内调整相关属性 */
  list-style: none; /* 含义：列表样式；设置：按需调整数值/颜色/变量 */
  padding: 0; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .meta-card ul */
.meta-card li {{ /* 含义：.meta-card li 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  justify-content: space-between; /* 含义：flex 主轴对齐；设置：按需调整数值/颜色/变量 */
  border-bottom: 1px dashed var(--border-color); /* 含义：底部边框；设置：按需调整数值/颜色/变量 */
  padding: 8px 0; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .meta-card li */
.toc {{ /* 含义：目录容器；设置：在本块内调整相关属性 */
  margin-top: 30px; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--border-color); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  border-radius: 12px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  padding: 20px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  background: rgba(0,0,0,0.01); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .toc */
.toc-title {{ /* 含义：.toc-title 样式区域；设置：在本块内调整相关属性 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  margin-bottom: 10px; /* 含义：margin-bottom 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .toc-title */
.toc ul {{ /* 含义：.toc ul 样式区域；设置：在本块内调整相关属性 */
  list-style: none; /* 含义：列表样式；设置：按需调整数值/颜色/变量 */
  margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  padding: 0; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .toc ul */
.toc li {{ /* 含义：.toc li 样式区域；设置：在本块内调整相关属性 */
  margin: 4px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .toc li */
.toc li.level-1 {{ /* 含义：.toc li.level-1 样式区域；设置：在本块内调整相关属性 */
  font-size: 1.05rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  margin-top: 12px; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .toc li.level-1 */
.toc li.level-2 {{ /* 含义：.toc li.level-2 样式区域；设置：在本块内调整相关属性 */
  margin-left: 12px; /* 含义：margin-left 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .toc li.level-2 */
.toc li a {{ /* 含义：.toc li a 样式区域；设置：在本块内调整相关属性 */
  color: var(--primary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  text-decoration: none; /* 含义：文本装饰；设置：按需调整数值/颜色/变量 */
}} /* 结束 .toc li a */
.toc li.level-3 {{ /* 含义：.toc li.level-3 样式区域；设置：在本块内调整相关属性 */
  margin-left: 16px; /* 含义：margin-left 样式属性；设置：按需调整数值/颜色/变量 */
  font-size: 0.95em; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .toc li.level-3 */
.toc-desc {{ /* 含义：.toc-desc 样式区域；设置：在本块内调整相关属性 */
  margin: 2px 0 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  font-size: 0.9rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .toc-desc */
.toc-desc {{ /* 含义：.toc-desc 样式区域；设置：在本块内调整相关属性 */
  margin: 2px 0 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  font-size: 0.9rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .toc-desc */
.chapter {{ /* 含义：章节容器；设置：在本块内调整相关属性 */
  margin-top: 40px; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
  padding-top: 32px; /* 含义：padding-top 样式属性；设置：按需调整数值/颜色/变量 */
  border-top: 1px solid rgba(0,0,0,0.05); /* 含义：border-top 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chapter */
.chapter:first-of-type {{ /* 含义：.chapter:first-of-type 样式区域；设置：在本块内调整相关属性 */
  border-top: none; /* 含义：border-top 样式属性；设置：按需调整数值/颜色/变量 */
  padding-top: 0; /* 含义：padding-top 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chapter:first-of-type */
blockquote {{ /* 含义：引用块 - PDF基础样式；设置：在本块内调整相关属性 */
  padding: 12px 16px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  background: rgba(0,0,0,0.04); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  border-radius: 8px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  border-left: none; /* 含义：移除左侧色条；设置：按需调整数值/颜色/变量 */
}} /* 结束 blockquote */
/* ==================== Blockquote 液态玻璃效果 - 仅屏幕显示 ==================== */
@media screen {{
  blockquote {{ /* 含义：引用块液态玻璃 - 透明悬浮设计；设置：在本块内调整相关属性 */
    position: relative; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
    margin: 20px 0; /* 含义：外边距增加悬浮空间；设置：按需调整数值/颜色/变量 */
    padding: 18px 22px; /* 含义：内边距；设置：按需调整数值/颜色/变量 */
    border: none; /* 含义：移除默认边框；设置：按需调整数值/颜色/变量 */
    border-radius: 20px; /* 含义：大圆角增强液态感；设置：按需调整数值/颜色/变量 */
    background: linear-gradient(135deg, rgba(255,255,255,0.15) 0%, rgba(255,255,255,0.05) 100%); /* 含义：极淡透明渐变；设置：按需调整数值/颜色/变量 */
    backdrop-filter: blur(24px) saturate(180%); /* 含义：强背景模糊实现玻璃透视；设置：按需调整数值/颜色/变量 */
    -webkit-backdrop-filter: blur(24px) saturate(180%); /* 含义：Safari 背景模糊；设置：按需调整数值/颜色/变量 */
    box-shadow: 
      0 8px 32px rgba(0, 0, 0, 0.12),
      0 2px 8px rgba(0, 0, 0, 0.06),
      inset 0 0 0 1px rgba(255, 255, 255, 0.2),
      inset 0 2px 4px rgba(255, 255, 255, 0.15); /* 含义：多层阴影营造悬浮感；设置：按需调整数值/颜色/变量 */
    transform: translateY(0); /* 含义：初始位置；设置：按需调整数值/颜色/变量 */
    transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.4s ease; /* 含义：弹性过渡动画；设置：按需调整数值/颜色/变量 */
    overflow: visible; /* 含义：允许光效溢出；设置：按需调整数值/颜色/变量 */
    isolation: isolate; /* 含义：创建层叠上下文；设置：按需调整数值/颜色/变量 */
  }} /* 结束 blockquote 液态玻璃基础 */
  blockquote:hover {{ /* 含义：悬停时增强悬浮效果；设置：在本块内调整相关属性 */
    transform: translateY(-3px); /* 含义：上浮效果；设置：按需调整数值/颜色/变量 */
    box-shadow: 
      0 16px 48px rgba(0, 0, 0, 0.15),
      0 4px 16px rgba(0, 0, 0, 0.08),
      inset 0 0 0 1px rgba(255, 255, 255, 0.25),
      inset 0 2px 6px rgba(255, 255, 255, 0.2); /* 含义：增强阴影；设置：按需调整数值/颜色/变量 */
  }} /* 结束 blockquote:hover */
  blockquote::after {{ /* 含义：顶部高光反射；设置：在本块内调整相关属性 */
    content: ''; /* 含义：伪元素内容；设置：按需调整数值/颜色/变量 */
    position: absolute; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
    top: 0; /* 含义：顶部位置；设置：按需调整数值/颜色/变量 */
    left: 0; /* 含义：左边位置；设置：按需调整数值/颜色/变量 */
    right: 0; /* 含义：右边位置；设置：按需调整数值/颜色/变量 */
    height: 50%; /* 含义：覆盖上半部分；设置：按需调整数值/颜色/变量 */
    background: linear-gradient(180deg, rgba(255,255,255,0.15) 0%, transparent 100%); /* 含义：顶部高光渐变；设置：按需调整数值/颜色/变量 */
    border-radius: 20px 20px 0 0; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
    pointer-events: none; /* 含义：不响应鼠标；设置：按需调整数值/颜色/变量 */
    z-index: -1; /* 含义：置于内容下方；设置：按需调整数值/颜色/变量 */
  }} /* 结束 blockquote::after */
  /* 暗色模式 blockquote 液态玻璃 */
  .dark-mode blockquote {{ /* 含义：暗色模式引用块液态玻璃；设置：在本块内调整相关属性 */
    background: linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.02) 100%); /* 含义：暗色透明渐变；设置：按需调整数值/颜色/变量 */
    box-shadow: 
      0 8px 32px rgba(0, 0, 0, 0.4),
      0 2px 8px rgba(0, 0, 0, 0.2),
      inset 0 0 0 1px rgba(255, 255, 255, 0.1),
      inset 0 2px 4px rgba(255, 255, 255, 0.05); /* 含义：暗色阴影；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .dark-mode blockquote */
  .dark-mode blockquote:hover {{ /* 含义：暗色悬停效果；设置：在本块内调整相关属性 */
    box-shadow: 
      0 20px 56px rgba(0, 0, 0, 0.5),
      0 6px 20px rgba(0, 0, 0, 0.25),
      inset 0 0 0 1px rgba(255, 255, 255, 0.15),
      inset 0 2px 6px rgba(255, 255, 255, 0.08); /* 含义：暗色增强阴影；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .dark-mode blockquote:hover */
  .dark-mode blockquote::after {{ /* 含义：暗色顶部高光；设置：在本块内调整相关属性 */
    background: linear-gradient(180deg, rgba(255,255,255,0.06) 0%, transparent 100%); /* 含义：暗色高光；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .dark-mode blockquote::after */
}} /* 结束 @media screen blockquote 液态玻璃 */
.engine-quote {{ /* 含义：引擎发言块；设置：在本块内调整相关属性 */
  --engine-quote-bg: var(--engine-insight-bg); /* 含义：主题变量 engine-quote-bg；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-quote-border: var(--engine-insight-border); /* 含义：主题变量 engine-quote-border；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-quote-text: var(--engine-insight-text); /* 含义：主题变量 engine-quote-text；设置：在 themeTokens 中覆盖或改此默认值 */
  margin: 22px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  padding: 16px 18px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 14px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--engine-quote-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  background: var(--engine-quote-bg); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  box-shadow: var(--engine-quote-shadow); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
  line-height: 1.65; /* 含义：行高，提升可读性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .engine-quote */
.engine-quote__header {{ /* 含义：.engine-quote__header 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  align-items: center; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  gap: 10px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  font-weight: 650; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  color: var(--engine-quote-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  margin-bottom: 8px; /* 含义：margin-bottom 样式属性；设置：按需调整数值/颜色/变量 */
  letter-spacing: 0.02em; /* 含义：字间距；设置：按需调整数值/颜色/变量 */
}} /* 结束 .engine-quote__header */
.engine-quote__dot {{ /* 含义：.engine-quote__dot 样式区域；设置：在本块内调整相关属性 */
  width: 10px; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  height: 10px; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
  border-radius: 50%; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  background: var(--engine-quote-text); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 0 0 8px rgba(0,0,0,0.02); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .engine-quote__dot */
.engine-quote__title {{ /* 含义：.engine-quote__title 样式区域；设置：在本块内调整相关属性 */
  font-size: 0.98rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .engine-quote__title */
.engine-quote__body > *:first-child {{ margin-top: 0; }} /* 含义：.engine-quote__body > * 样式属性；设置：按需调整数值/颜色/变量 */
.engine-quote__body > *:last-child {{ margin-bottom: 0; }} /* 含义：.engine-quote__body > * 样式属性；设置：按需调整数值/颜色/变量 */
.engine-quote.engine-media {{ /* 含义：.engine-quote.engine-media 样式区域；设置：在本块内调整相关属性 */
  --engine-quote-bg: var(--engine-media-bg); /* 含义：主题变量 engine-quote-bg；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-quote-border: var(--engine-media-border); /* 含义：主题变量 engine-quote-border；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-quote-text: var(--engine-media-text); /* 含义：主题变量 engine-quote-text；设置：在 themeTokens 中覆盖或改此默认值 */
}} /* 结束 .engine-quote.engine-media */
.engine-quote.engine-query {{ /* 含义：.engine-quote.engine-query 样式区域；设置：在本块内调整相关属性 */
  --engine-quote-bg: var(--engine-query-bg); /* 含义：主题变量 engine-quote-bg；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-quote-border: var(--engine-query-border); /* 含义：主题变量 engine-quote-border；设置：在 themeTokens 中覆盖或改此默认值 */
  --engine-quote-text: var(--engine-query-text); /* 含义：主题变量 engine-quote-text；设置：在 themeTokens 中覆盖或改此默认值 */
}} /* 结束 .engine-quote.engine-query */
.table-wrap {{ /* 含义：表格滚动容器；设置：在本块内调整相关属性 */
  overflow-x: auto; /* 含义：横向溢出处理；设置：按需调整数值/颜色/变量 */
  margin: 20px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .table-wrap */
table {{ /* 含义：表格基础样式；设置：在本块内调整相关属性 */
  width: 100%; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  border-collapse: collapse; /* 含义：border-collapse 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 table */
table th, table td {{ /* 含义：表格单元格；设置：在本块内调整相关属性 */
  padding: 12px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--border-color); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
}} /* 结束 table th, table td */
table th {{ /* 含义：table th 样式区域；设置：在本块内调整相关属性 */
  background: rgba(0,0,0,0.03); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 table th */
.align-center {{ text-align: center; }} /* 含义：.align-center  text-align 样式属性；设置：按需调整数值/颜色/变量 */
.align-right {{ text-align: right; }} /* 含义：.align-right  text-align 样式属性；设置：按需调整数值/颜色/变量 */
.swot-card {{ /* 含义：SWOT 卡片容器；设置：在本块内调整相关属性 */
  margin: 26px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  padding: 18px 18px 14px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 16px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--swot-card-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  background: var(--swot-card-bg); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  box-shadow: var(--swot-card-shadow); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
  color: var(--swot-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  backdrop-filter: var(--swot-card-blur); /* 含义：背景模糊；设置：按需调整数值/颜色/变量 */
  position: relative; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
  overflow: hidden; /* 含义：溢出处理；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-card */
.swot-card__head {{ /* 含义：.swot-card__head 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  justify-content: space-between; /* 含义：flex 主轴对齐；设置：按需调整数值/颜色/变量 */
  gap: 16px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  align-items: flex-start; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-card__head */
.swot-card__title {{ /* 含义：.swot-card__title 样式区域；设置：在本块内调整相关属性 */
  font-size: 1.15rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 750; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  margin-bottom: 4px; /* 含义：margin-bottom 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-card__title */
.swot-card__summary {{ /* 含义：.swot-card__summary 样式区域；设置：在本块内调整相关属性 */
  margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  color: var(--swot-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  opacity: 0.82; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-card__summary */
.swot-legend {{ /* 含义：.swot-legend 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  gap: 8px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
  align-items: center; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-legend */
.swot-legend__item {{ /* 含义：.swot-legend__item 样式区域；设置：在本块内调整相关属性 */
  padding: 6px 12px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 999px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  font-weight: 700; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  color: var(--swot-on-dark); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--swot-tag-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 4px 12px rgba(0,0,0,0.16); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
  text-shadow: 0 1px 2px rgba(0,0,0,0.35); /* 含义：文字阴影；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-legend__item */
.swot-legend__item.strength {{ background: var(--swot-strength); }} /* 含义：.swot-legend__item.strength  background 样式属性；设置：按需调整数值/颜色/变量 */
.swot-legend__item.weakness {{ background: var(--swot-weakness); }} /* 含义：.swot-legend__item.weakness  background 样式属性；设置：按需调整数值/颜色/变量 */
.swot-legend__item.opportunity {{ background: var(--swot-opportunity); }} /* 含义：.swot-legend__item.opportunity  background 样式属性；设置：按需调整数值/颜色/变量 */
.swot-legend__item.threat {{ background: var(--swot-threat); }} /* 含义：.swot-legend__item.threat  background 样式属性；设置：按需调整数值/颜色/变量 */
.swot-grid {{ /* 含义：SWOT 象限网格；设置：在本块内调整相关属性 */
  display: grid; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); /* 含义：网格列模板；设置：按需调整数值/颜色/变量 */
  gap: 12px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  margin-top: 14px; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-grid */
.swot-cell {{ /* 含义：SWOT 象限单元格；设置：在本块内调整相关属性 */
  border-radius: 14px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--swot-cell-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  padding: 12px 12px 10px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  background: var(--swot-cell-base); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.4); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-cell */
.swot-cell.strength {{ border-color: var(--swot-cell-strength-border); background: var(--swot-cell-strength-bg); }} /* 含义：.swot-cell.strength  border-color 样式属性；设置：按需调整数值/颜色/变量 */
.swot-cell.weakness {{ border-color: var(--swot-cell-weakness-border); background: var(--swot-cell-weakness-bg); }} /* 含义：.swot-cell.weakness  border-color 样式属性；设置：按需调整数值/颜色/变量 */
.swot-cell.opportunity {{ border-color: var(--swot-cell-opportunity-border); background: var(--swot-cell-opportunity-bg); }} /* 含义：.swot-cell.opportunity  border-color 样式属性；设置：按需调整数值/颜色/变量 */
.swot-cell.threat {{ border-color: var(--swot-cell-threat-border); background: var(--swot-cell-threat-bg); }} /* 含义：.swot-cell.threat  border-color 样式属性；设置：按需调整数值/颜色/变量 */
.swot-cell__meta {{ /* 含义：.swot-cell__meta 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  gap: 10px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  align-items: flex-start; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  margin-bottom: 8px; /* 含义：margin-bottom 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-cell__meta */
.swot-pill {{ /* 含义：.swot-pill 样式区域；设置：在本块内调整相关属性 */
  display: inline-flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  align-items: center; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  justify-content: center; /* 含义：flex 主轴对齐；设置：按需调整数值/颜色/变量 */
  width: 36px; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  height: 36px; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
  border-radius: 12px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  font-weight: 800; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  color: var(--swot-on-dark); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--swot-tag-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 8px 20px rgba(0,0,0,0.18); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pill */
.swot-pill.strength {{ background: var(--swot-strength); }} /* 含义：.swot-pill.strength  background 样式属性；设置：按需调整数值/颜色/变量 */
.swot-pill.weakness {{ background: var(--swot-weakness); }} /* 含义：.swot-pill.weakness  background 样式属性；设置：按需调整数值/颜色/变量 */
.swot-pill.opportunity {{ background: var(--swot-opportunity); }} /* 含义：.swot-pill.opportunity  background 样式属性；设置：按需调整数值/颜色/变量 */
.swot-pill.threat {{ background: var(--swot-threat); }} /* 含义：.swot-pill.threat  background 样式属性；设置：按需调整数值/颜色/变量 */
.swot-cell__title {{ /* 含义：.swot-cell__title 样式区域；设置：在本块内调整相关属性 */
  font-weight: 750; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  letter-spacing: 0.01em; /* 含义：字间距；设置：按需调整数值/颜色/变量 */
  color: var(--swot-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-cell__title */
.swot-cell__caption {{ /* 含义：.swot-cell__caption 样式区域；设置：在本块内调整相关属性 */
  font-size: 0.9rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  color: var(--swot-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  opacity: 0.7; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-cell__caption */
.swot-list {{ /* 含义：SWOT 条目列表；设置：在本块内调整相关属性 */
  list-style: none; /* 含义：列表样式；设置：按需调整数值/颜色/变量 */
  padding: 0; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  flex-direction: column; /* 含义：flex 主轴方向；设置：按需调整数值/颜色/变量 */
  gap: 8px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-list */
.swot-item {{ /* 含义：SWOT 条目；设置：在本块内调整相关属性 */
  padding: 10px 12px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 12px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  background: var(--swot-surface); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--swot-item-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 12px 22px rgba(0,0,0,0.08); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-item */
.swot-item-title {{ /* 含义：.swot-item-title 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  justify-content: space-between; /* 含义：flex 主轴对齐；设置：按需调整数值/颜色/变量 */
  gap: 8px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  font-weight: 650; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  color: var(--swot-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-item-title */
.swot-item-tags {{ /* 含义：.swot-item-tags 样式区域；设置：在本块内调整相关属性 */
  display: inline-flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  gap: 6px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
  font-size: 0.85rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-item-tags */
.swot-tag {{ /* 含义：.swot-tag 样式区域；设置：在本块内调整相关属性 */
  display: inline-block; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  padding: 4px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 10px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  background: var(--swot-chip-bg); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  color: var(--swot-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--swot-tag-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 6px 14px rgba(0,0,0,0.12); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
  line-height: 1.2; /* 含义：行高，提升可读性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-tag */
.swot-tag.neutral {{ /* 含义：.swot-tag.neutral 样式区域；设置：在本块内调整相关属性 */
  opacity: 0.9; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-tag.neutral */
.swot-item-desc {{ /* 含义：.swot-item-desc 样式区域；设置：在本块内调整相关属性 */
  margin-top: 4px; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
  color: var(--swot-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  opacity: 0.92; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-item-desc */
.swot-item-evidence {{ /* 含义：.swot-item-evidence 样式区域；设置：在本块内调整相关属性 */
  margin-top: 4px; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
  font-size: 0.9rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  opacity: 0.94; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-item-evidence */
.swot-empty {{ /* 含义：.swot-empty 样式区域；设置：在本块内调整相关属性 */
  padding: 12px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 12px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  border: 1px dashed var(--swot-card-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  color: var(--swot-muted); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  opacity: 0.7; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-empty */

/* ========== SWOT PDF表格布局样式（默认隐藏）========== */
.swot-pdf-wrapper {{ /* 含义：SWOT PDF 表格容器；设置：在本块内调整相关属性 */
  display: none; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pdf-wrapper */

/* SWOT PDF表格样式定义（用于PDF渲染时显示） */
.swot-pdf-table {{ /* 含义：.swot-pdf-table 样式区域；设置：在本块内调整相关属性 */
  width: 100%; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  border-collapse: collapse; /* 含义：border-collapse 样式属性；设置：按需调整数值/颜色/变量 */
  margin: 20px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  font-size: 13px; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  table-layout: fixed; /* 含义：表格布局算法；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pdf-table */
.swot-pdf-caption {{ /* 含义：.swot-pdf-caption 样式区域；设置：在本块内调整相关属性 */
  caption-side: top; /* 含义：caption-side 样式属性；设置：按需调整数值/颜色/变量 */
  text-align: left; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  font-size: 1.15rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 700; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  padding: 12px 0; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  color: var(--text-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pdf-caption */
.swot-pdf-thead th {{ /* 含义：.swot-pdf-thead th 样式区域；设置：在本块内调整相关属性 */
  background: # f8f9fa; /* Meaning: background color or gradient effect; settings: adjust values/colors/variables as needed */
  padding: 10px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  text-align: left; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  border: 1px solid # dee2e6; /* Meaning: border style; settings: adjust values/colors/variables as needed */
  color: # 495057; /* Meaning: text color; settings: adjust value/color/variable as needed */
}} /* 结束 .swot-pdf-thead th */
.swot-pdf-th-quadrant {{ width: 80px; }} /* 含义：.swot-pdf-th-quadrant  width 样式属性；设置：按需调整数值/颜色/变量 */
.swot-pdf-th-num {{ width: 50px; text-align: center; }} /* 含义：.swot-pdf-th-num  width 样式属性；设置：按需调整数值/颜色/变量 */
.swot-pdf-th-title {{ width: 22%; }} /* 含义：.swot-pdf-th-title  width 样式属性；设置：按需调整数值/颜色/变量 */
.swot-pdf-th-detail {{ width: auto; }} /* 含义：.swot-pdf-th-detail  width 样式属性；设置：按需调整数值/颜色/变量 */
.swot-pdf-th-tags {{ width: 100px; text-align: center; }} /* 含义：.swot-pdf-th-tags  width 样式属性；设置：按需调整数值/颜色/变量 */
.swot-pdf-summary {{ /* 含义：.swot-pdf-summary 样式区域；设置：在本块内调整相关属性 */
  padding: 12px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  background: # f8f9fa; /* Meaning: background color or gradient effect; settings: adjust values/colors/variables as needed */
  color: # 666; /* Meaning: text color; setting: adjust value/color/variable as needed */
  font-style: italic; /* 含义：font-style 样式属性；设置：按需调整数值/颜色/变量 */
  border: 1px solid # dee2e6; /* Meaning: border style; settings: adjust values/colors/variables as needed */
}} /* 结束 .swot-pdf-summary */
.swot-pdf-quadrant {{ /* 含义：.swot-pdf-quadrant 样式区域；设置：在本块内调整相关属性 */
  break-inside: avoid; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  page-break-inside: avoid; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pdf-quadrant */
.swot-pdf-quadrant-label {{ /* 含义：.swot-pdf-quadrant-label 样式区域；设置：在本块内调整相关属性 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  vertical-align: middle; /* 含义：vertical-align 样式属性；设置：按需调整数值/颜色/变量 */
  padding: 12px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  font-weight: 700; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  border: 1px solid # dee2e6; /* Meaning: border style; settings: adjust values/colors/variables as needed */
  writing-mode: horizontal-tb; /* 含义：writing-mode 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pdf-quadrant-label */
.swot-pdf-quadrant-label.swot-pdf-strength {{ background: rgba(28,127,110,0.15); color: # 1c7f6e; border-left: 4px solid #1c7f6e; }} /* Meaning: .swot-pdf-quadrant-label.swot-pdf-strength background style attribute; setting: adjust value/color/variable as needed */
.swot-pdf-quadrant-label.swot-pdf-weakness {{ background: rgba(192,57,43,0.12); color: # c0392b; border-left: 4px solid #c0392b; }} /* Meaning: .swot-pdf-quadrant-label.swot-pdf-weakness background style attribute; setting: adjust value/color/variable as needed */
.swot-pdf-quadrant-label.swot-pdf-opportunity {{ background: rgba(31,90,179,0.12); color: # 1f5ab3; border-left: 4px solid #1f5ab3; }} /* Meaning: .swot-pdf-quadrant-label.swot-pdf-opportunity background style attribute; setting: adjust value/color/variable as needed */
.swot-pdf-quadrant-label.swot-pdf-threat {{ background: rgba(179,107,22,0.12); color: # b36b16; border-left: 4px solid #b36b16; }} /* Meaning: .swot-pdf-quadrant-label.swot-pdf-threat background style attribute; setting: adjust value/color/variable as needed */
.swot-pdf-code {{ /* 含义：.swot-pdf-code 样式区域；设置：在本块内调整相关属性 */
  display: block; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  font-size: 1.5rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 800; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  margin-bottom: 4px; /* 含义：margin-bottom 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pdf-code */
.swot-pdf-label-text {{ /* 含义：.swot-pdf-label-text 样式区域；设置：在本块内调整相关属性 */
  display: block; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  font-size: 0.75rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  letter-spacing: 0.02em; /* 含义：字间距；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pdf-label-text */
.swot-pdf-item-row td {{ /* 含义：.swot-pdf-item-row td 样式区域；设置：在本块内调整相关属性 */
  padding: 10px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border: 1px solid # dee2e6; /* Meaning: border style; settings: adjust values/colors/variables as needed */
  vertical-align: top; /* 含义：vertical-align 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pdf-item-row td */
.swot-pdf-item-row.swot-pdf-strength td {{ background: rgba(28,127,110,0.03); }} /* 含义：.swot-pdf-item-row.swot-pdf-strength td  background 样式属性；设置：按需调整数值/颜色/变量 */
.swot-pdf-item-row.swot-pdf-weakness td {{ background: rgba(192,57,43,0.03); }} /* 含义：.swot-pdf-item-row.swot-pdf-weakness td  background 样式属性；设置：按需调整数值/颜色/变量 */
.swot-pdf-item-row.swot-pdf-opportunity td {{ background: rgba(31,90,179,0.03); }} /* 含义：.swot-pdf-item-row.swot-pdf-opportunity td  background 样式属性；设置：按需调整数值/颜色/变量 */
.swot-pdf-item-row.swot-pdf-threat td {{ background: rgba(179,107,22,0.03); }} /* 含义：.swot-pdf-item-row.swot-pdf-threat td  background 样式属性；设置：按需调整数值/颜色/变量 */
.swot-pdf-item-num {{ /* 含义：.swot-pdf-item-num 样式区域；设置：在本块内调整相关属性 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  color: # 6c757d; /* Meaning: text color; settings: adjust values/colors/variables as needed */
}} /* 结束 .swot-pdf-item-num */
.swot-pdf-item-title {{ /* 含义：.swot-pdf-item-title 样式区域；设置：在本块内调整相关属性 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  color: # 212529; /* Meaning: text color; settings: adjust values/colors/variables as needed */
}} /* 结束 .swot-pdf-item-title */
.swot-pdf-item-detail {{ /* 含义：.swot-pdf-item-detail 样式区域；设置：在本块内调整相关属性 */
  color: # 495057; /* Meaning: text color; settings: adjust value/color/variable as needed */
  line-height: 1.5; /* 含义：行高，提升可读性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pdf-item-detail */
.swot-pdf-item-tags {{ /* 含义：.swot-pdf-item-tags 样式区域；设置：在本块内调整相关属性 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pdf-item-tags */
.swot-pdf-tag {{ /* 含义：.swot-pdf-tag 样式区域；设置：在本块内调整相关属性 */
  display: inline-block; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  padding: 3px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 4px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  font-size: 0.75rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  background: # e9ecef; /* Meaning: background color or gradient effect; settings: adjust values/colors/variables as needed */
  color: # 495057; /* Meaning: text color; settings: adjust value/color/variable as needed */
  margin: 2px; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pdf-tag */
.swot-pdf-tag--score {{ /* 含义：.swot-pdf-tag--score 样式区域；设置：在本块内调整相关属性 */
  background: # fff3cd; /* Meaning: background color or gradient effect; settings: adjust values/colors/variables as needed */
  color: # 856404; /* Meaning: text color; settings: adjust value/color/variable as needed */
}} /* 结束 .swot-pdf-tag--score */
.swot-pdf-empty {{ /* 含义：.swot-pdf-empty 样式区域；设置：在本块内调整相关属性 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  color: # adb5bd; /* Meaning: text color; settings: adjust values/colors/variables as needed */
  font-style: italic; /* 含义：font-style 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .swot-pdf-empty */

/* 打印模式下的SWOT分页控制（保留卡片布局的打印支持） */
@media print {{ /* 含义：打印模式样式；设置：在本块内调整相关属性 */
  .swot-card {{ /* 含义：SWOT 卡片容器；设置：在本块内调整相关属性 */
    break-inside: auto; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: auto; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .swot-card */
  .swot-card__head {{ /* 含义：.swot-card__head 样式区域；设置：在本块内调整相关属性 */
    break-after: avoid; /* 含义：break-after 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-after: avoid; /* 含义：page-break-after 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .swot-card__head */
  .swot-pdf-quadrant {{ /* 含义：.swot-pdf-quadrant 样式区域；设置：在本块内调整相关属性 */
    break-inside: avoid; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: avoid; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .swot-pdf-quadrant */
}} /* 结束 @media print */

/* ==================== PEST 分析样式 ==================== */
.pest-card {{ /* 含义：PEST 卡片容器；设置：在本块内调整相关属性 */
  margin: 28px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  padding: 20px 20px 16px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 18px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--pest-card-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  background: var(--pest-card-bg); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  box-shadow: var(--pest-card-shadow); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
  color: var(--pest-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  backdrop-filter: var(--pest-card-blur); /* 含义：背景模糊；设置：按需调整数值/颜色/变量 */
  position: relative; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
  overflow: hidden; /* 含义：溢出处理；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-card */
.pest-card__head {{ /* 含义：.pest-card__head 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  justify-content: space-between; /* 含义：flex 主轴对齐；设置：按需调整数值/颜色/变量 */
  gap: 16px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  align-items: flex-start; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
  margin-bottom: 16px; /* 含义：margin-bottom 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-card__head */
.pest-card__title {{ /* 含义：.pest-card__title 样式区域；设置：在本块内调整相关属性 */
  font-size: 1.18rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 750; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  margin-bottom: 4px; /* 含义：margin-bottom 样式属性；设置：按需调整数值/颜色/变量 */
  background: linear-gradient(135deg, var(--pest-political), var(--pest-technological)); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  -webkit-background-clip: text; /* 含义：-webkit-background-clip 样式属性；设置：按需调整数值/颜色/变量 */
  -webkit-text-fill-color: transparent; /* 含义：-webkit-text-fill-color 样式属性；设置：按需调整数值/颜色/变量 */
  background-clip: text; /* 含义：background-clip 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-card__title */
.pest-card__summary {{ /* 含义：.pest-card__summary 样式区域；设置：在本块内调整相关属性 */
  margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  color: var(--pest-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  opacity: 0.8; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-card__summary */
.pest-legend {{ /* 含义：.pest-legend 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  gap: 8px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
  align-items: center; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-legend */
.pest-legend__item {{ /* 含义：.pest-legend__item 样式区域；设置：在本块内调整相关属性 */
  padding: 6px 14px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 8px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  font-weight: 700; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  font-size: 0.85rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  color: var(--pest-on-dark); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--pest-tag-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 4px 14px rgba(0,0,0,0.18); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
  text-shadow: 0 1px 2px rgba(0,0,0,0.3); /* 含义：文字阴影；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-legend__item */
.pest-legend__item.political {{ background: var(--pest-political); }} /* 含义：.pest-legend__item.political  background 样式属性；设置：按需调整数值/颜色/变量 */
.pest-legend__item.economic {{ background: var(--pest-economic); }} /* 含义：.pest-legend__item.economic  background 样式属性；设置：按需调整数值/颜色/变量 */
.pest-legend__item.social {{ background: var(--pest-social); }} /* 含义：.pest-legend__item.social  background 样式属性；设置：按需调整数值/颜色/变量 */
.pest-legend__item.technological {{ background: var(--pest-technological); }} /* 含义：.pest-legend__item.technological  background 样式属性；设置：按需调整数值/颜色/变量 */
.pest-strips {{ /* 含义：PEST 条带容器；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  flex-direction: column; /* 含义：flex 主轴方向；设置：按需调整数值/颜色/变量 */
  gap: 14px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-strips */
.pest-strip {{ /* 含义：PEST 条带；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  border-radius: 14px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--pest-strip-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  background: var(--pest-strip-base); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  overflow: hidden; /* 含义：溢出处理；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 6px 16px rgba(0,0,0,0.06); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
  transition: transform 0.2s ease, box-shadow 0.2s ease; /* 含义：过渡动画时长/属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-strip */
.pest-strip:hover {{ /* 含义：.pest-strip:hover 样式区域；设置：在本块内调整相关属性 */
  transform: translateY(-2px); /* 含义：transform 样式属性；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 10px 24px rgba(0,0,0,0.1); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-strip:hover */
.pest-strip.political {{ border-color: var(--pest-strip-political-border); background: var(--pest-strip-political-bg); }} /* 含义：.pest-strip.political  border-color 样式属性；设置：按需调整数值/颜色/变量 */
.pest-strip.economic {{ border-color: var(--pest-strip-economic-border); background: var(--pest-strip-economic-bg); }} /* 含义：.pest-strip.economic  border-color 样式属性；设置：按需调整数值/颜色/变量 */
.pest-strip.social {{ border-color: var(--pest-strip-social-border); background: var(--pest-strip-social-bg); }} /* 含义：.pest-strip.social  border-color 样式属性；设置：按需调整数值/颜色/变量 */
.pest-strip.technological {{ border-color: var(--pest-strip-technological-border); background: var(--pest-strip-technological-bg); }} /* 含义：.pest-strip.technological  border-color 样式属性；设置：按需调整数值/颜色/变量 */
.pest-strip__indicator {{ /* 含义：.pest-strip__indicator 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  align-items: center; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  justify-content: center; /* 含义：flex 主轴对齐；设置：按需调整数值/颜色/变量 */
  width: 56px; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  min-width: 56px; /* 含义：最小宽度；设置：按需调整数值/颜色/变量 */
  padding: 16px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  color: var(--pest-on-dark); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  text-shadow: 0 2px 4px rgba(0,0,0,0.25); /* 含义：文字阴影；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-strip__indicator */
.pest-strip__indicator.political {{ background: linear-gradient(180deg, var(--pest-political), rgba(142,68,173,0.8)); }} /* 含义：.pest-strip__indicator.political  background 样式属性；设置：按需调整数值/颜色/变量 */
.pest-strip__indicator.economic {{ background: linear-gradient(180deg, var(--pest-economic), rgba(22,160,133,0.8)); }} /* 含义：.pest-strip__indicator.economic  background 样式属性；设置：按需调整数值/颜色/变量 */
.pest-strip__indicator.social {{ background: linear-gradient(180deg, var(--pest-social), rgba(232,67,147,0.8)); }} /* 含义：.pest-strip__indicator.social  background 样式属性；设置：按需调整数值/颜色/变量 */
.pest-strip__indicator.technological {{ background: linear-gradient(180deg, var(--pest-technological), rgba(41,128,185,0.8)); }} /* 含义：.pest-strip__indicator.technological  background 样式属性；设置：按需调整数值/颜色/变量 */
.pest-code {{ /* 含义：.pest-code 样式区域；设置：在本块内调整相关属性 */
  font-size: 1.6rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 900; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  letter-spacing: 0.02em; /* 含义：字间距；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-code */
.pest-strip__content {{ /* 含义：.pest-strip__content 样式区域；设置：在本块内调整相关属性 */
  flex: 1; /* 含义：flex 占位比例；设置：按需调整数值/颜色/变量 */
  padding: 14px 16px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  min-width: 0; /* 含义：最小宽度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-strip__content */
.pest-strip__header {{ /* 含义：.pest-strip__header 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  justify-content: space-between; /* 含义：flex 主轴对齐；设置：按需调整数值/颜色/变量 */
  align-items: baseline; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  gap: 12px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  margin-bottom: 10px; /* 含义：margin-bottom 样式属性；设置：按需调整数值/颜色/变量 */
  flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-strip__header */
.pest-strip__title {{ /* 含义：.pest-strip__title 样式区域；设置：在本块内调整相关属性 */
  font-weight: 700; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  font-size: 1rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  color: var(--pest-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-strip__title */
.pest-strip__caption {{ /* 含义：.pest-strip__caption 样式区域；设置：在本块内调整相关属性 */
  font-size: 0.85rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  color: var(--pest-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  opacity: 0.65; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-strip__caption */
.pest-list {{ /* 含义：PEST 条目列表；设置：在本块内调整相关属性 */
  list-style: none; /* 含义：列表样式；设置：按需调整数值/颜色/变量 */
  padding: 0; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  flex-direction: column; /* 含义：flex 主轴方向；设置：按需调整数值/颜色/变量 */
  gap: 8px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-list */
.pest-item {{ /* 含义：PEST 条目；设置：在本块内调整相关属性 */
  padding: 10px 14px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 10px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  background: var(--pest-surface); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--pest-item-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 8px 18px rgba(0,0,0,0.06); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-item */
.pest-item-title {{ /* 含义：.pest-item-title 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  justify-content: space-between; /* 含义：flex 主轴对齐；设置：按需调整数值/颜色/变量 */
  gap: 8px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  font-weight: 650; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  color: var(--pest-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-item-title */
.pest-item-tags {{ /* 含义：.pest-item-tags 样式区域；设置：在本块内调整相关属性 */
  display: inline-flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  gap: 6px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
  font-size: 0.82rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-item-tags */
.pest-tag {{ /* 含义：.pest-tag 样式区域；设置：在本块内调整相关属性 */
  display: inline-block; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  padding: 3px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 6px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  background: var(--pest-chip-bg); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  color: var(--pest-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--pest-tag-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 4px 10px rgba(0,0,0,0.08); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
  line-height: 1.2; /* 含义：行高，提升可读性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-tag */
.pest-item-desc {{ /* 含义：.pest-item-desc 样式区域；设置：在本块内调整相关属性 */
  margin-top: 5px; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
  color: var(--pest-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  opacity: 0.88; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
  font-size: 0.95rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-item-desc */
.pest-item-source {{ /* 含义：.pest-item-source 样式区域；设置：在本块内调整相关属性 */
  margin-top: 4px; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
  font-size: 0.88rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  opacity: 0.9; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-item-source */
.pest-empty {{ /* 含义：.pest-empty 样式区域；设置：在本块内调整相关属性 */
  padding: 14px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 10px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  border: 1px dashed var(--pest-card-border); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  color: var(--pest-muted); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  opacity: 0.65; /* 含义：透明度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-empty */

/* ========== PEST PDF表格布局样式（默认隐藏）========== */
.pest-pdf-wrapper {{ /* 含义：PEST PDF 容器；设置：在本块内调整相关属性 */
  display: none; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-pdf-wrapper */

/* PEST PDF表格样式定义（用于PDF渲染时显示） */
.pest-pdf-table {{ /* 含义：.pest-pdf-table 样式区域；设置：在本块内调整相关属性 */
  width: 100%; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  border-collapse: collapse; /* 含义：border-collapse 样式属性；设置：按需调整数值/颜色/变量 */
  margin: 20px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  font-size: 13px; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  table-layout: fixed; /* 含义：表格布局算法；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-pdf-table */
.pest-pdf-caption {{ /* 含义：.pest-pdf-caption 样式区域；设置：在本块内调整相关属性 */
  caption-side: top; /* 含义：caption-side 样式属性；设置：按需调整数值/颜色/变量 */
  text-align: left; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  font-size: 1.15rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 700; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  padding: 12px 0; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  color: var(--text-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-pdf-caption */
.pest-pdf-thead th {{ /* 含义：.pest-pdf-thead th 样式区域；设置：在本块内调整相关属性 */
  background: # f5f3f7; /* Meaning: background color or gradient effect; settings: adjust values/colors/variables as needed */
  padding: 10px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  text-align: left; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  border: 1px solid # e0dce3; /* Meaning: border style; settings: adjust values/colors/variables as needed */
  color: # 4a4458; /* Meaning: text color; settings: adjust values/colors/variables as needed */
}} /* 结束 .pest-pdf-thead th */
.pest-pdf-th-dimension {{ width: 85px; }} /* 含义：.pest-pdf-th-dimension  width 样式属性；设置：按需调整数值/颜色/变量 */
.pest-pdf-th-num {{ width: 50px; text-align: center; }} /* 含义：.pest-pdf-th-num  width 样式属性；设置：按需调整数值/颜色/变量 */
.pest-pdf-th-title {{ width: 22%; }} /* 含义：.pest-pdf-th-title  width 样式属性；设置：按需调整数值/颜色/变量 */
.pest-pdf-th-detail {{ width: auto; }} /* 含义：.pest-pdf-th-detail  width 样式属性；设置：按需调整数值/颜色/变量 */
.pest-pdf-th-tags {{ width: 100px; text-align: center; }} /* 含义：.pest-pdf-th-tags  width 样式属性；设置：按需调整数值/颜色/变量 */
.pest-pdf-summary {{ /* 含义：.pest-pdf-summary 样式区域；设置：在本块内调整相关属性 */
  padding: 12px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  background: # f8f6fa; /* Meaning: background color or gradient effect; settings: adjust values/colors/variables as needed */
  color: # 666; /* Meaning: text color; setting: adjust value/color/variable as needed */
  font-style: italic; /* 含义：font-style 样式属性；设置：按需调整数值/颜色/变量 */
  border: 1px solid # e0dce3; /* Meaning: border style; settings: adjust values/colors/variables as needed */
}} /* 结束 .pest-pdf-summary */
.pest-pdf-dimension {{ /* 含义：.pest-pdf-dimension 样式区域；设置：在本块内调整相关属性 */
  break-inside: avoid; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  page-break-inside: avoid; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-pdf-dimension */
.pest-pdf-dimension-label {{ /* 含义：.pest-pdf-dimension-label 样式区域；设置：在本块内调整相关属性 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  vertical-align: middle; /* 含义：vertical-align 样式属性；设置：按需调整数值/颜色/变量 */
  padding: 12px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  font-weight: 700; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  border: 1px solid # e0dce3; /* Meaning: border style; settings: adjust values/colors/variables as needed */
  writing-mode: horizontal-tb; /* 含义：writing-mode 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-pdf-dimension-label */
.pest-pdf-dimension-label.pest-pdf-political {{ background: rgba(142,68,173,0.12); color: # 8e44ad; border-left: 4px solid #8e44ad; }} /* Meaning: .pest-pdf-dimension-label.pest-pdf-political background style attribute; setting: adjust value/color/variable as needed */
.pest-pdf-dimension-label.pest-pdf-economic {{ background: rgba(22,160,133,0.12); color: # 16a085; border-left: 4px solid #16a085; }} /* Meaning: .pest-pdf-dimension-label.pest-pdf-economic background style attribute; setting: adjust value/color/variable as needed */
.pest-pdf-dimension-label.pest-pdf-social {{ background: rgba(232,67,147,0.12); color: # e84393; border-left: 4px solid #e84393; }} /* Meaning: .pest-pdf-dimension-label.pest-pdf-social background style attribute; setting: adjust value/color/variable as needed */
.pest-pdf-dimension-label.pest-pdf-technological {{ background: rgba(41,128,185,0.12); color: # 2980b9; border-left: 4px solid #2980b9; }} /* Meaning: .pest-pdf-dimension-label.pest-pdf-technological background style attribute; setting: adjust value/color/variable as needed */
.pest-pdf-code {{ /* 含义：.pest-pdf-code 样式区域；设置：在本块内调整相关属性 */
  display: block; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  font-size: 1.5rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 800; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  margin-bottom: 4px; /* 含义：margin-bottom 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-pdf-code */
.pest-pdf-label-text {{ /* 含义：.pest-pdf-label-text 样式区域；设置：在本块内调整相关属性 */
  display: block; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  font-size: 0.75rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  letter-spacing: 0.02em; /* 含义：字间距；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-pdf-label-text */
.pest-pdf-item-row td {{ /* 含义：.pest-pdf-item-row td 样式区域；设置：在本块内调整相关属性 */
  padding: 10px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border: 1px solid # e0dce3; /* Meaning: border style; settings: adjust values/colors/variables as needed */
  vertical-align: top; /* 含义：vertical-align 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-pdf-item-row td */
.pest-pdf-item-row.pest-pdf-political td {{ background: rgba(142,68,173,0.03); }} /* 含义：.pest-pdf-item-row.pest-pdf-political td  background 样式属性；设置：按需调整数值/颜色/变量 */
.pest-pdf-item-row.pest-pdf-economic td {{ background: rgba(22,160,133,0.03); }} /* 含义：.pest-pdf-item-row.pest-pdf-economic td  background 样式属性；设置：按需调整数值/颜色/变量 */
.pest-pdf-item-row.pest-pdf-social td {{ background: rgba(232,67,147,0.03); }} /* 含义：.pest-pdf-item-row.pest-pdf-social td  background 样式属性；设置：按需调整数值/颜色/变量 */
.pest-pdf-item-row.pest-pdf-technological td {{ background: rgba(41,128,185,0.03); }} /* 含义：.pest-pdf-item-row.pest-pdf-technological td  background 样式属性；设置：按需调整数值/颜色/变量 */
.pest-pdf-item-num {{ /* 含义：.pest-pdf-item-num 样式区域；设置：在本块内调整相关属性 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  color: # 6c757d; /* Meaning: text color; settings: adjust values/colors/variables as needed */
}} /* 结束 .pest-pdf-item-num */
.pest-pdf-item-title {{ /* 含义：.pest-pdf-item-title 样式区域；设置：在本块内调整相关属性 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  color: # 212529; /* Meaning: text color; settings: adjust values/colors/variables as needed */
}} /* 结束 .pest-pdf-item-title */
.pest-pdf-item-detail {{ /* 含义：.pest-pdf-item-detail 样式区域；设置：在本块内调整相关属性 */
  color: # 495057; /* Meaning: text color; settings: adjust value/color/variable as needed */
  line-height: 1.5; /* 含义：行高，提升可读性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-pdf-item-detail */
.pest-pdf-item-tags {{ /* 含义：.pest-pdf-item-tags 样式区域；设置：在本块内调整相关属性 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-pdf-item-tags */
.pest-pdf-tag {{ /* 含义：.pest-pdf-tag 样式区域；设置：在本块内调整相关属性 */
  display: inline-block; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  padding: 3px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 4px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  font-size: 0.75rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  background: # ece9f1; /* Meaning: background color or gradient effect; settings: adjust values/colors/variables as needed */
  color: # 5a4f6a; /* Meaning: text color; settings: adjust value/color/variable as needed */
  margin: 2px; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-pdf-tag */
.pest-pdf-empty {{ /* 含义：.pest-pdf-empty 样式区域；设置：在本块内调整相关属性 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  color: # adb5bd; /* Meaning: text color; settings: adjust values/colors/variables as needed */
  font-style: italic; /* 含义：font-style 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .pest-pdf-empty */

/* 打印模式下的PEST分页控制 */
@media print {{ /* 含义：打印模式样式；设置：在本块内调整相关属性 */
  .pest-card {{ /* 含义：PEST 卡片容器；设置：在本块内调整相关属性 */
    break-inside: auto; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: auto; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .pest-card */
  .pest-card__head {{ /* 含义：.pest-card__head 样式区域；设置：在本块内调整相关属性 */
    break-after: avoid; /* 含义：break-after 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-after: avoid; /* 含义：page-break-after 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .pest-card__head */
  .pest-pdf-dimension {{ /* 含义：.pest-pdf-dimension 样式区域；设置：在本块内调整相关属性 */
    break-inside: avoid; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: avoid; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .pest-pdf-dimension */
  .pest-strip {{ /* 含义：PEST 条带；设置：在本块内调整相关属性 */
    break-inside: avoid; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: avoid; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .pest-strip */
}} /* 结束 @media print */
.callout {{ /* 含义：高亮提示框 - PDF基础样式；设置：在本块内调整相关属性 */
  padding: 16px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 8px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  margin: 20px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  background: rgba(0,0,0,0.02); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  border-left: none; /* 含义：移除左侧色条；设置：按需调整数值/颜色/变量 */
}} /* 结束 .callout */
.callout.tone-warning {{ border-color: # ff9800; }} /* Meaning: .callout.tone-warning border-color style attribute; setting: adjust value/color/variable as needed */
.callout.tone-success {{ border-color: # 2ecc71; }} /* Meaning: .callout.tone-success border-color style attribute; setting: adjust value/color/variable as needed */
.callout.tone-danger {{ border-color: # e74c3c; }} /* Meaning: .callout.tone-danger border-color style attribute; setting: adjust value/color/variable as needed */
/* ==================== Callout 液态玻璃效果 - 仅屏幕显示 ==================== */
@media screen {{
  .callout {{ /* 含义：高亮提示框液态玻璃 - 透明悬浮设计；设置：在本块内调整相关属性 */
    --callout-accent: var(--primary-color); /* 含义：callout 主色调；设置：按需调整数值/颜色/变量 */
    --callout-glow-color: rgba(0, 123, 255, 0.35); /* 含义：callout 发光色；设置：按需调整数值/颜色/变量 */
    position: relative; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
    margin: 24px 0; /* 含义：增加外边距强化悬浮感；设置：按需调整数值/颜色/变量 */
    padding: 20px 24px; /* 含义：内边距；设置：按需调整数值/颜色/变量 */
    border: none; /* 含义：移除默认边框；设置：按需调整数值/颜色/变量 */
    border-radius: 24px; /* 含义：大圆角增强液态感；设置：按需调整数值/颜色/变量 */
    background: linear-gradient(135deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.04) 100%); /* 含义：极淡透明渐变；设置：按需调整数值/颜色/变量 */
    backdrop-filter: blur(28px) saturate(200%); /* 含义：强背景模糊实现玻璃透视；设置：按需调整数值/颜色/变量 */
    -webkit-backdrop-filter: blur(28px) saturate(200%); /* 含义：Safari 背景模糊；设置：按需调整数值/颜色/变量 */
    box-shadow: 
      0 12px 40px rgba(0, 0, 0, 0.1),
      0 4px 12px rgba(0, 0, 0, 0.05),
      inset 0 0 0 1.5px rgba(255, 255, 255, 0.18),
      inset 0 2px 6px rgba(255, 255, 255, 0.12); /* 含义：多层阴影营造悬浮感；设置：按需调整数值/颜色/变量 */
    transform: translateY(0); /* 含义：初始位置；设置：按需调整数值/颜色/变量 */
    transition: transform 0.45s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.45s ease; /* 含义：弹性过渡动画；设置：按需调整数值/颜色/变量 */
    overflow: hidden; /* 含义：隐藏溢出内容；设置：按需调整数值/颜色/变量 */
    isolation: isolate; /* 含义：创建层叠上下文；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .callout 液态玻璃基础 */
  .callout:hover {{ /* 含义：悬停时增强悬浮效果；设置：在本块内调整相关属性 */
    transform: translateY(-4px); /* 含义：上浮效果；设置：按需调整数值/颜色/变量 */
    box-shadow: 
      0 20px 56px rgba(0, 0, 0, 0.12),
      0 8px 20px rgba(0, 0, 0, 0.06),
      inset 0 0 0 1.5px rgba(255, 255, 255, 0.22),
      inset 0 3px 8px rgba(255, 255, 255, 0.15); /* 含义：增强阴影；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .callout:hover */
  .callout::after {{ /* 含义：顶部弧形高光反射；设置：在本块内调整相关属性 */
    content: ''; /* 含义：伪元素内容；设置：按需调整数值/颜色/变量 */
    position: absolute; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
    top: 0; /* 含义：顶部位置；设置：按需调整数值/颜色/变量 */
    left: 0; /* 含义：左边位置；设置：按需调整数值/颜色/变量 */
    right: 0; /* 含义：右边位置；设置：按需调整数值/颜色/变量 */
    height: 55%; /* 含义：覆盖上半部分；设置：按需调整数值/颜色/变量 */
    background: linear-gradient(180deg, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0.03) 60%, transparent 100%); /* 含义：顶部高光渐变；设置：按需调整数值/颜色/变量 */
    border-radius: 24px 24px 0 0; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
    pointer-events: none; /* 含义：不响应鼠标；设置：按需调整数值/颜色/变量 */
    z-index: -1; /* 含义：置于内容下方；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .callout::after */
  /* Callout tone 变体 - 不同颜色发光 */
  .callout.tone-info {{ /* 含义：信息类型 callout；设置：在本块内调整相关属性 */
    --callout-accent: # 3b82f6; /* Meaning: Information blue tone; Settings: Adjust values/colors/variables as needed */
    --callout-glow-color: rgba(59, 130, 246, 0.4); /* 含义：信息蓝发光；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .callout.tone-info */
  .callout.tone-warning {{ /* 含义：警告类型 callout；设置：在本块内调整相关属性 */
    --callout-accent: # f59e0b; /* Meaning: Warning orange tone; Settings: Adjust values/colors/variables as needed */
    --callout-glow-color: rgba(245, 158, 11, 0.4); /* 含义：警告橙发光；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .callout.tone-warning */
  .callout.tone-success {{ /* 含义：成功类型 callout；设置：在本块内调整相关属性 */
    --callout-accent: # 10b981; /* Meaning: Successful green tone; Settings: Adjust values/colors/variables as needed */
    --callout-glow-color: rgba(16, 185, 129, 0.4); /* 含义：成功绿发光；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .callout.tone-success */
  .callout.tone-danger {{ /* 含义：危险类型 callout；设置：在本块内调整相关属性 */
    --callout-accent: # ef4444; /* Meaning: Dangerous red tone; Settings: Adjust values/colors/variables as needed */
    --callout-glow-color: rgba(239, 68, 68, 0.4); /* 含义：危险红发光；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .callout.tone-danger */
  /* 暗色模式 callout 液态玻璃 */
  .dark-mode .callout {{ /* 含义：暗色模式 callout 液态玻璃；设置：在本块内调整相关属性 */
    background: linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.01) 100%); /* 含义：暗色透明渐变；设置：按需调整数值/颜色/变量 */
    box-shadow: 
      0 12px 40px rgba(0, 0, 0, 0.35),
      0 4px 12px rgba(0, 0, 0, 0.18),
      inset 0 0 0 1.5px rgba(255, 255, 255, 0.08),
      inset 0 2px 6px rgba(255, 255, 255, 0.04); /* 含义：暗色阴影；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .dark-mode .callout */
  .dark-mode .callout:hover {{ /* 含义：暗色悬停效果；设置：在本块内调整相关属性 */
    box-shadow: 
      0 24px 64px rgba(0, 0, 0, 0.45),
      0 10px 28px rgba(0, 0, 0, 0.22),
      inset 0 0 0 1.5px rgba(255, 255, 255, 0.12),
      inset 0 3px 8px rgba(255, 255, 255, 0.06); /* 含义：暗色增强阴影；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .dark-mode .callout:hover */
  .dark-mode .callout::after {{ /* 含义：暗色顶部高光；设置：在本块内调整相关属性 */
    background: linear-gradient(180deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.01) 50%, transparent 100%); /* 含义：暗色高光；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .dark-mode .callout::after */
  /* 暗色模式发光颜色增强 */
  .dark-mode .callout.tone-info {{ /* 含义：暗色信息类型；设置：在本块内调整相关属性 */
    --callout-glow-color: rgba(96, 165, 250, 0.5); /* 含义：暗色信息发光；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .dark-mode .callout.tone-info */
  .dark-mode .callout.tone-warning {{ /* 含义：暗色警告类型；设置：在本块内调整相关属性 */
    --callout-glow-color: rgba(251, 191, 36, 0.5); /* 含义：暗色警告发光；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .dark-mode .callout.tone-warning */
  .dark-mode .callout.tone-success {{ /* 含义：暗色成功类型；设置：在本块内调整相关属性 */
    --callout-glow-color: rgba(52, 211, 153, 0.5); /* 含义：暗色成功发光；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .dark-mode .callout.tone-success */
  .dark-mode .callout.tone-danger {{ /* 含义：暗色危险类型；设置：在本块内调整相关属性 */
    --callout-glow-color: rgba(248, 113, 113, 0.5); /* 含义：暗色危险发光；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .dark-mode .callout.tone-danger */
}} /* 结束 @media screen callout 液态玻璃 */
.kpi-grid {{ /* 含义：KPI 栅格容器；设置：在本块内调整相关属性 */
  display: grid; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); /* 含义：网格列模板；设置：按需调整数值/颜色/变量 */
  gap: 16px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  margin: 20px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .kpi-grid */
.kpi-card {{ /* 含义：KPI 卡片；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  flex-direction: column; /* 含义：flex 主轴方向；设置：按需调整数值/颜色/变量 */
  gap: 8px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  padding: 16px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 12px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  background: rgba(0,0,0,0.02); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--border-color); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  align-items: flex-start; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
}} /* 结束 .kpi-card */
.kpi-value {{ /* 含义：.kpi-value 样式区域；设置：在本块内调整相关属性 */
  font-size: 2rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  font-weight: 700; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  flex-wrap: nowrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
  gap: 4px 6px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  line-height: 1.25; /* 含义：行高，提升可读性；设置：按需调整数值/颜色/变量 */
  word-break: break-word; /* 含义：单词断行规则；设置：按需调整数值/颜色/变量 */
  overflow-wrap: break-word; /* 含义：长单词换行；设置：按需调整数值/颜色/变量 */
}} /* 结束 .kpi-value */
.kpi-value small {{ /* 含义：.kpi-value small 样式区域；设置：在本块内调整相关属性 */
  font-size: 0.65em; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  align-self: baseline; /* 含义：align-self 样式属性；设置：按需调整数值/颜色/变量 */
  white-space: nowrap; /* 含义：空白与换行策略；设置：按需调整数值/颜色/变量 */
}} /* 结束 .kpi-value small */
.kpi-label {{ /* 含义：.kpi-label 样式区域；设置：在本块内调整相关属性 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  line-height: 1.35; /* 含义：行高，提升可读性；设置：按需调整数值/颜色/变量 */
  word-break: break-word; /* 含义：单词断行规则；设置：按需调整数值/颜色/变量 */
  overflow-wrap: break-word; /* 含义：长单词换行；设置：按需调整数值/颜色/变量 */
  max-width: 100%; /* 含义：最大宽度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .kpi-label */
.delta.up {{ color: # 27ae60; }} /* Meaning: .delta.up color style attribute; setting: adjust value/color/variable as needed */
.delta.down {{ color: # e74c3c; }} /* Meaning: .delta.down color style attribute; setting: adjust value/color/variable as needed */
.delta.neutral {{ color: var(--secondary-color); }} /* 含义：.delta.neutral  color 样式属性；设置：按需调整数值/颜色/变量 */
.delta {{ /* 含义：.delta 样式区域；设置：在本块内调整相关属性 */
  display: block; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  line-height: 1.3; /* 含义：行高，提升可读性；设置：按需调整数值/颜色/变量 */
  word-break: break-word; /* 含义：单词断行规则；设置：按需调整数值/颜色/变量 */
  overflow-wrap: break-word; /* 含义：长单词换行；设置：按需调整数值/颜色/变量 */
}} /* 结束 .delta */
.chart-card {{ /* 含义：图表卡片容器；设置：在本块内调整相关属性 */
  margin: 30px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  padding: 20px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border: 1px solid var(--border-color); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  border-radius: 12px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  background: rgba(0,0,0,0.01); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-card */
.chart-card.chart-card--error {{ /* 含义：.chart-card.chart-card--error 样式区域；设置：在本块内调整相关属性 */
  border-style: dashed; /* 含义：border-style 样式属性；设置：按需调整数值/颜色/变量 */
  background: linear-gradient(135deg, rgba(0,0,0,0.015), rgba(0,0,0,0.04)); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-card.chart-card--error */
.chart-error {{ /* 含义：.chart-error 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  gap: 12px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  padding: 14px 12px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 10px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  align-items: flex-start; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  background: rgba(0,0,0,0.03); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-error */
.chart-error__icon {{ /* 含义：.chart-error__icon 样式区域；设置：在本块内调整相关属性 */
  width: 28px; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  height: 28px; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
  flex-shrink: 0; /* 含义：flex-shrink 样式属性；设置：按需调整数值/颜色/变量 */
  border-radius: 50%; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  display: inline-flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  align-items: center; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  justify-content: center; /* 含义：flex 主轴对齐；设置：按需调整数值/颜色/变量 */
  font-weight: 700; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color-dark); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  background: rgba(0,0,0,0.06); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  font-size: 0.9rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-error__icon */
.chart-error__title {{ /* 含义：.chart-error__title 样式区域；设置：在本块内调整相关属性 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  color: var(--text-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-error__title */
.chart-error__desc {{ /* 含义：.chart-error__desc 样式区域；设置：在本块内调整相关属性 */
  margin: 4px 0 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  line-height: 1.6; /* 含义：行高，提升可读性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-error__desc */
.chart-card.wordcloud-card .chart-container {{ /* 含义：.chart-card.wordcloud-card .chart-container 样式区域；设置：在本块内调整相关属性 */
  min-height: 180px; /* 含义：最小高度，防止塌陷；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-card.wordcloud-card .chart-container */
.chart-container {{ /* 含义：图表 canvas 容器；设置：在本块内调整相关属性 */
  position: relative; /* 含义：定位方式；设置：按需调整数值/颜色/变量 */
  min-height: 220px; /* 含义：最小高度，防止塌陷；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-container */
.chart-fallback {{ /* 含义：图表兜底表格；设置：在本块内调整相关属性 */
  display: none; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  margin-top: 12px; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
  font-size: 0.85rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  overflow-x: auto; /* 含义：横向溢出处理；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-fallback */
.no-js .chart-fallback {{ /* 含义：.no-js .chart-fallback 样式区域；设置：在本块内调整相关属性 */
  display: block; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
}} /* 结束 .no-js .chart-fallback */
.no-js .chart-container {{ /* 含义：.no-js .chart-container 样式区域；设置：在本块内调整相关属性 */
  display: none; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
}} /* 结束 .no-js .chart-container */
.chart-fallback table {{ /* 含义：.chart-fallback table 样式区域；设置：在本块内调整相关属性 */
  width: 100%; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  border-collapse: collapse; /* 含义：border-collapse 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-fallback table */
.chart-fallback th,
.chart-fallback td {{ /* 含义：.chart-fallback td 样式区域；设置：在本块内调整相关属性 */
  border: 1px solid var(--border-color); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  padding: 6px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  text-align: left; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-fallback td */
.chart-fallback th {{ /* 含义：.chart-fallback th 样式区域；设置：在本块内调整相关属性 */
  background: rgba(0,0,0,0.04); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-fallback th */
.wordcloud-fallback .wordcloud-badges {{ /* 含义：.wordcloud-fallback .wordcloud-badges 样式区域；设置：在本块内调整相关属性 */
  display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
  gap: 6px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  margin-top: 6px; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
}} /* 结束 .wordcloud-fallback .wordcloud-badges */
.wordcloud-badge {{ /* 含义：词云徽章；设置：在本块内调整相关属性 */
  display: inline-flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  align-items: center; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  gap: 4px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
  padding: 4px 8px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 999px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  border: 1px solid rgba(74, 144, 226, 0.35); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  color: var(--text-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  background: linear-gradient(135deg, rgba(74, 144, 226, 0.14) 0%, rgba(74, 144, 226, 0.24) 100%); /* 含义：背景色或渐变效果；设置：按需调整数值/颜色/变量 */
  box-shadow: 0 4px 10px rgba(15, 23, 42, 0.06); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .wordcloud-badge */
.dark-mode .wordcloud-badge {{ /* 含义：.dark-mode .wordcloud-badge 样式区域；设置：在本块内调整相关属性 */
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35); /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
}} /* 结束 .dark-mode .wordcloud-badge */
.wordcloud-badge small {{ /* 含义：.wordcloud-badge small 样式区域；设置：在本块内调整相关属性 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  font-weight: 600; /* 含义：字重；设置：按需调整数值/颜色/变量 */
  font-size: 0.75rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
}} /* 结束 .wordcloud-badge small */
.chart-note {{ /* 含义：图表降级提示；设置：在本块内调整相关属性 */
  margin-top: 8px; /* 含义：margin-top 样式属性；设置：按需调整数值/颜色/变量 */
  font-size: 0.85rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
}} /* 结束 .chart-note */
figure {{ /* 含义：figure 样式区域；设置：在本块内调整相关属性 */
  margin: 20px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
}} /* 结束 figure */
figure img {{ /* 含义：figure img 样式区域；设置：在本块内调整相关属性 */
  max-width: 100%; /* 含义：最大宽度；设置：按需调整数值/颜色/变量 */
  border-radius: 12px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
}} /* 结束 figure img */
.figure-placeholder {{ /* 含义：.figure-placeholder 样式区域；设置：在本块内调整相关属性 */
  padding: 16px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border: 1px dashed var(--border-color); /* 含义：边框样式；设置：按需调整数值/颜色/变量 */
  border-radius: 12px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  color: var(--secondary-color); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  font-size: 0.95rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  margin: 20px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .figure-placeholder */
.math-block {{ /* 含义：块级公式；设置：在本块内调整相关属性 */
  text-align: center; /* 含义：文本对齐；设置：按需调整数值/颜色/变量 */
  font-size: 1.1rem; /* 含义：字号；设置：按需调整数值/颜色/变量 */
  margin: 24px 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .math-block */
.math-inline {{ /* 含义：行内公式；设置：在本块内调整相关属性 */
  font-family: {fonts.get("heading", fonts.get("body", "sans-serif"))}; /* 含义：字体族；设置：按需调整数值/颜色/变量 */
  font-style: italic; /* 含义：font-style 样式属性；设置：按需调整数值/颜色/变量 */
  white-space: nowrap; /* 含义：空白与换行策略；设置：按需调整数值/颜色/变量 */
  padding: 0 0.15em; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
}} /* 结束 .math-inline */
pre.code-block {{ /* 含义：代码块；设置：在本块内调整相关属性 */
  background: # 1e1e1e; /* Meaning: background color or gradient effect; settings: adjust value/color/variable as needed */
  color: # fff; /* Meaning: text color; setting: adjust value/color/variable as needed */
  padding: 16px; /* 含义：内边距，控制内容与容器边缘的距离；设置：按需调整数值/颜色/变量 */
  border-radius: 12px; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  overflow-x: auto; /* 含义：横向溢出处理；设置：按需调整数值/颜色/变量 */
}} /* 结束 pre.code-block */
@media (max-width: 768px) {{ /* 含义：移动端断点样式；设置：在本块内调整相关属性 */
  .report-header {{ /* 含义：页眉吸顶区域；设置：在本块内调整相关属性 */
    flex-direction: column; /* 含义：flex 主轴方向；设置：按需调整数值/颜色/变量 */
    align-items: flex-start; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .report-header */
  main {{ /* 含义：主体内容容器；设置：在本块内调整相关属性 */
    margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
    border-radius: 0; /* 含义：圆角；设置：按需调整数值/颜色/变量 */
  }} /* 结束 main */
}} /* 结束 @media (max-width: 768px) */
@media print {{ /* 含义：打印模式样式；设置：在本块内调整相关属性 */
  .no-print {{ display: none !important; }} /* 含义：.no-print  display 样式属性；设置：按需调整数值/颜色/变量 */
  body {{ /* 含义：全局排版与背景设置；设置：在本块内调整相关属性 */
    background: # fff; /* Meaning: background color or gradient effect; setting: adjust value/color/variable as needed */
  }} /* 结束 body */
  main {{ /* 含义：主体内容容器；设置：在本块内调整相关属性 */
    box-shadow: none; /* 含义：阴影效果；设置：按需调整数值/颜色/变量 */
    margin: 0; /* 含义：外边距，控制与周围元素的距离；设置：按需调整数值/颜色/变量 */
    max-width: 100%; /* 含义：最大宽度；设置：按需调整数值/颜色/变量 */
  }} /* 结束 main */
  .chapter > *,
  .hero-section,
  .callout,
  .engine-quote,
  .chart-card,
  .kpi-grid,
.swot-card,
.pest-card,
.table-wrap,
figure,
blockquote {{ /* 含义：引用块；设置：在本块内调整相关属性 */
  break-inside: avoid; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: avoid; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    max-width: 100%; /* 含义：最大宽度；设置：按需调整数值/颜色/变量 */
  }} /* 结束 blockquote */
  .chapter h2,
  .chapter h3,
  .chapter h4 {{ /* 含义：.chapter h4 样式区域；设置：在本块内调整相关属性 */
    break-after: avoid; /* 含义：break-after 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-after: avoid; /* 含义：page-break-after 样式属性；设置：按需调整数值/颜色/变量 */
    break-inside: avoid; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .chapter h4 */
  .chart-card,
  .table-wrap {{ /* 含义：表格滚动容器；设置：在本块内调整相关属性 */
    overflow: visible !important; /* 含义：溢出处理；设置：按需调整数值/颜色/变量 */
    max-width: 100% !important; /* 含义：最大宽度；设置：按需调整数值/颜色/变量 */
    box-sizing: border-box; /* 含义：尺寸计算方式；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .table-wrap */
  .chart-card canvas {{ /* 含义：.chart-card canvas 样式区域；设置：在本块内调整相关属性 */
    width: 100% !important; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
    height: auto !important; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
    max-width: 100% !important; /* 含义：最大宽度；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .chart-card canvas */
  .swot-card,
  .swot-cell {{ /* 含义：SWOT 象限单元格；设置：在本块内调整相关属性 */
    break-inside: avoid; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: avoid; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .swot-cell */
  .swot-card {{ /* 含义：SWOT 卡片容器；设置：在本块内调整相关属性 */
    color: var(--swot-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
    /* 允许卡片内部分页，避免整体被抬到下一页 */
    break-inside: auto !important; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: auto !important; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .swot-card */
  .swot-card__head {{ /* 含义：.swot-card__head 样式区域；设置：在本块内调整相关属性 */
    break-after: avoid; /* 含义：break-after 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-after: avoid; /* 含义：page-break-after 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .swot-card__head */
  .swot-grid {{ /* 含义：SWOT 象限网格；设置：在本块内调整相关属性 */
    break-before: avoid; /* 含义：break-before 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-before: avoid; /* 含义：page-break-before 样式属性；设置：按需调整数值/颜色/变量 */
    break-inside: auto; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: auto; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    display: flex; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
    flex-wrap: wrap; /* 含义：换行策略；设置：按需调整数值/颜色/变量 */
    gap: 10px; /* 含义：子元素间距；设置：按需调整数值/颜色/变量 */
    align-items: stretch; /* 含义：flex 对齐方式（交叉轴）；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .swot-grid */
  .swot-grid .swot-cell {{ /* 含义：.swot-grid .swot-cell 样式区域；设置：在本块内调整相关属性 */
    break-inside: avoid; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: avoid; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .swot-grid .swot-cell */
  .swot-legend {{ /* 含义：.swot-legend 样式区域；设置：在本块内调整相关属性 */
    display: none !important; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .swot-legend */
  .swot-grid .swot-cell {{ /* 含义：.swot-grid .swot-cell 样式区域；设置：在本块内调整相关属性 */
    flex: 1 1 320px; /* 含义：flex 占位比例；设置：按需调整数值/颜色/变量 */
    min-width: 240px; /* 含义：最小宽度；设置：按需调整数值/颜色/变量 */
    height: auto; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .swot-grid .swot-cell */
  /* PEST 打印样式 */
  .pest-card,
  .pest-strip {{ /* 含义：PEST 条带；设置：在本块内调整相关属性 */
    break-inside: avoid; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: avoid; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .pest-strip */
  .pest-card {{ /* 含义：PEST 卡片容器；设置：在本块内调整相关属性 */
    color: var(--pest-text); /* 含义：文字颜色；设置：按需调整数值/颜色/变量 */
    break-inside: auto !important; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: auto !important; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .pest-card */
  .pest-card__head {{ /* 含义：.pest-card__head 样式区域；设置：在本块内调整相关属性 */
    break-after: avoid; /* 含义：break-after 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-after: avoid; /* 含义：page-break-after 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .pest-card__head */
  .pest-strips {{ /* 含义：PEST 条带容器；设置：在本块内调整相关属性 */
    break-before: avoid; /* 含义：break-before 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-before: avoid; /* 含义：page-break-before 样式属性；设置：按需调整数值/颜色/变量 */
    break-inside: auto; /* 含义：break-inside 样式属性；设置：按需调整数值/颜色/变量 */
    page-break-inside: auto; /* 含义：page-break-inside 样式属性；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .pest-strips */
  .pest-legend {{ /* 含义：.pest-legend 样式区域；设置：在本块内调整相关属性 */
    display: none !important; /* 含义：布局展示方式；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .pest-legend */
  .pest-strip {{ /* 含义：PEST 条带；设置：在本块内调整相关属性 */
    flex-direction: row; /* 含义：flex 主轴方向；设置：按需调整数值/颜色/变量 */
  }} /* 结束 .pest-strip */
.table-wrap {{ /* 含义：表格滚动容器；设置：在本块内调整相关属性 */
  overflow-x: auto; /* 含义：横向溢出处理；设置：按需调整数值/颜色/变量 */
  max-width: 100%; /* 含义：最大宽度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .table-wrap */
.table-wrap table {{ /* 含义：.table-wrap table 样式区域；设置：在本块内调整相关属性 */
  table-layout: fixed; /* 含义：表格布局算法；设置：按需调整数值/颜色/变量 */
  width: 100%; /* 含义：宽度设置；设置：按需调整数值/颜色/变量 */
  max-width: 100%; /* 含义：最大宽度；设置：按需调整数值/颜色/变量 */
}} /* 结束 .table-wrap table */
.table-wrap table th,
.table-wrap table td {{ /* 含义：.table-wrap table td 样式区域；设置：在本块内调整相关属性 */
  word-break: break-word; /* 含义：单词断行规则；设置：按需调整数值/颜色/变量 */
  overflow-wrap: break-word; /* 含义：长单词换行；设置：按需调整数值/颜色/变量 */
}} /* 结束 .table-wrap table td */
/* 防止图片和图表溢出 */
img, canvas, svg {{ /* 含义：媒体元素尺寸限制；设置：在本块内调整相关属性 */
  max-width: 100% !important; /* 含义：最大宽度；设置：按需调整数值/颜色/变量 */
  height: auto !important; /* 含义：高度设置；设置：按需调整数值/颜色/变量 */
}} /* 结束 img, canvas, svg */
/* 确保所有容器不超出页面宽度 */
* {{ /* 含义：* 样式区域；设置：在本块内调整相关属性 */
  box-sizing: border-box; /* 含义：尺寸计算方式；设置：按需调整数值/颜色/变量 */
  max-width: 100%; /* 含义：最大宽度；设置：按需调整数值/颜色/变量 */
}} /* 结束 * */
}} /* 结束 @media print */

"""

    def _hydration_script(self) -> str:
        """
        返回页面底部的JS，负责 Chart.js 注水、词云渲染及按钮交互。

        交互层级梳理：
        1) 主题切换（# theme-toggle): Listen to the change event of the custom component, the detail is 'light'/'dark',
           作用：切换 body.dark-mode、刷新 Chart.js 与词云颜色。
        2) 打印按钮（# print-btn): triggers window.print(), controlled by CSS @media print.
        3) 导出按钮（# export-btn): Call exportPdf(), internally use html2canvas + jsPDF,
           并显示 # export-overlay (mask, status copy, progress bar).
        4) 图表注水：扫描所有 data-config-id 的 canvas，解析相邻 JSON，实例化 Chart.js；
           失败时降级为表格/词云徽章展示，并在卡片上标记 data-chart-state。
        5) 窗口 resize：debounce 后重绘词云，确保响应式。
        """
        return """
<script>
document.documentElement.classList.remove('no-js');
document.documentElement.classList.add('js-ready');

/* ========== Theme Button Web Component (已注释，改用 action-btn 风格) ========== */
/*
(() => {
  const themeButtonFunc = (root, initTheme, changeTheme) => {
    const checkbox = root.querySelector('.theme-checkbox');
    // 初始化状态
    if (initTheme === 'dark') {
      checkbox.checked = true;
    }
    // 核心交互：勾选切换 dark/light，外部通过 changeTheme 回调同步主题
    checkbox.addEventListener('change', (e) => {
      const isDark = e.target.checked;
      changeTheme(isDark ? 'dark' : 'light');
    });
  };

  class ThemeButton extends HTMLElement {
    constructor() { super(); }
    connectedCallback() {
      const initTheme = this.getAttribute("value") || "light";
      const size = +this.getAttribute("size") || 1.5;
      
      const shadow = this.attachShadow({ mode: "closed" });
      const container = document.createElement("div");
      container.setAttribute("class", "container");
      container.style.fontSize = `${size * 10}px`;

      // 组件结构：checkbox + label，label 内含天空/星星/云层与月亮圆点，视觉上是主题切换拨钮
      container.innerHTML = [
        '<div class="toggle-wrapper">',
        '  <input type="checkbox" class="theme-checkbox" id="theme-toggle-input">',
        '  <label for="theme-toggle-input" class="toggle-label">',
        '    <div class="toggle-background">',
        '      <div class="stars">',
        '        <span class="star"></span>',
        '        <span class="star"></span>',
        '        <span class="star"></span>',
        '        <span class="star"></span>',
        '      </div>',
        '      <div class="clouds">',
        '        <span class="cloud"></span>',
        '        <span class="cloud"></span>',
        '      </div>',
        '    </div>',
        '    <div class="toggle-circle">',
        '      <div class="moon-crater"></div>',
        '      <div class="moon-crater"></div>',
        '      <div class="moon-crater"></div>',
        '    </div>',
        '  </label>',
        '</div>'
      ].join('');

      const style = document.createElement("style");
      style.textContent = [
        '* { box-sizing: border-box; margin: 0; padding: 0; }',
        '.container { display: inline-block; position: relative; width: 5.4em; height: 2.6em; vertical-align: middle; }',
        '.toggle-wrapper { width: 100%; height: 100%; }',
        '.theme-checkbox { display: none; }',
        '.toggle-label { display: block; width: 100%; height: 100%; border-radius: 2.6em; background-color: #87CEEB; cursor: pointer; position: relative; overflow: hidden; transition: background-color 0.5s ease; box-shadow: inset 0 0.1em 0.3em rgba(0,0,0,0.2); }',
        '.theme-checkbox:checked + .toggle-label { background-color: #1F2937; }',
        '.toggle-circle { position: absolute; top: 0.2em; left: 0.2em; width: 2.2em; height: 2.2em; border-radius: 50%; background-color: #FFD700; box-shadow: 0 0.1em 0.2em rgba(0,0,0,0.3); transition: transform 0.5s cubic-bezier(0.4, 0.0, 0.2, 1), background-color 0.5s ease; z-index: 2; }',
        '.theme-checkbox:checked + .toggle-label .toggle-circle { transform: translateX(2.8em); background-color: #F3F4F6; box-shadow: inset -0.2em -0.2em 0.2em rgba(0,0,0,0.1), 0 0.1em 0.2em rgba(255,255,255,0.2); }',
        '.moon-crater { position: absolute; background-color: rgba(200, 200, 200, 0.6); border-radius: 50%; opacity: 0; transition: opacity 0.3s ease; }',
        '.theme-checkbox:checked + .toggle-label .toggle-circle .moon-crater { opacity: 1; }',
        '.moon-crater:nth-child(1) { width: 0.6em; height: 0.6em; top: 0.4em; left: 0.8em; }',
        '.moon-crater:nth-child(2) { width: 0.4em; height: 0.4em; top: 1.2em; left: 0.4em; }',
        '.moon-crater:nth-child(3) { width: 0.3em; height: 0.3em; top: 1.4em; left: 1.2em; }',
        '.toggle-background { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }',
        '.clouds { position: absolute; width: 100%; height: 100%; transition: transform 0.5s ease, opacity 0.5s ease; opacity: 1; }',
        '.theme-checkbox:checked + .toggle-label .clouds { transform: translateY(100%); opacity: 0; }',
        '.cloud { position: absolute; background-color: #fff; border-radius: 2em; opacity: 0.9; }',
        '.cloud::before { content: ""; position: absolute; top: -40%; left: 15%; width: 50%; height: 100%; background-color: inherit; border-radius: 50%; }',
        '.cloud::after { content: ""; position: absolute; top: -55%; left: 45%; width: 50%; height: 120%; background-color: inherit; border-radius: 50%; }',
        '.cloud:nth-child(1) { width: 1.4em; height: 0.5em; top: 0.8em; right: 1.0em; }',
        '.cloud:nth-child(2) { width: 1.0em; height: 0.4em; top: 1.6em; right: 2.0em; opacity: 0.7; }',
        '.stars { position: absolute; width: 100%; height: 100%; transition: transform 0.5s ease, opacity 0.5s ease; transform: translateY(-100%); opacity: 0; }',
        '.theme-checkbox:checked + .toggle-label .stars { transform: translateY(0); opacity: 1; }',
        '.star { position: absolute; background-color: #FFF; border-radius: 50%; width: 0.15em; height: 0.15em; box-shadow: 0 0 0.2em #FFF; animation: twinkle 2s infinite ease-in-out; }',
        '.star:nth-child(1) { top: 0.6em; left: 1.0em; animation-delay: 0s; }',
        '.star:nth-child(2) { top: 1.6em; left: 1.8em; width: 0.1em; height: 0.1em; animation-delay: 0.5s; }',
        '.star:nth-child(3) { top: 0.8em; left: 2.4em; width: 0.12em; height: 0.12em; animation-delay: 1s; }',
        '.star:nth-child(4) { top: 1.8em; left: 0.8em; width: 0.08em; height: 0.08em; animation-delay: 1.5s; }',
        '@keyframes twinkle { 0%, 100% { opacity: 0.4; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1.2); } }'
      ].join(' ');

      const changeThemeWrapper = (detail) => {
        this.dispatchEvent(new CustomEvent("change", { detail }));
      };
      
      themeButtonFunc(container, initTheme, changeThemeWrapper);
      shadow.appendChild(style);
      shadow.appendChild(container);
    }
  }
  customElements.define("theme-button", ThemeButton);
})();
*/
/* ========== End Theme Button Web Component ========== */
 
 const chartRegistry = [];
const wordCloudRegistry = new Map();
const STABLE_CHART_TYPES = ['line', 'bar'];
const CHART_TYPE_LABELS = {
  line: '折线图',
  bar: '柱状图',
  doughnut: '圆环图',
  pie: '饼图',
  radar: '雷达图',
  polarArea: '极地区域图'
};

// 与PDF矢量渲染保持一致的颜色替换/提亮规则
const DEFAULT_CHART_COLORS = [
  '#4A90E2', '#E85D75', '#50C878', '#FFB347',
  '#9B59B6', '#3498DB', '#E67E22', '#16A085',
  '#F39C12', '#D35400', '#27AE60', '#8E44AD'
];
const CSS_VAR_COLOR_MAP = {
  'var(--chart-color-green)': '#4BC0C0',
  'var(--chart-color-red)': '#FF6384',
  'var(--chart-color-blue)': '#36A2EB',
  'var(--color-accent)': '#4A90E2',
  'var(--re-accent-color)': '#4A90E2',
  'var(--re-accent-color-translucent)': 'rgba(74, 144, 226, 0.08)',
  'var(--color-kpi-down)': '#E85D75',
  'var(--re-danger-color)': '#E85D75',
  'var(--re-danger-color-translucent)': 'rgba(232, 93, 117, 0.08)',
  'var(--color-warning)': '#FFB347',
  'var(--re-warning-color)': '#FFB347',
  'var(--re-warning-color-translucent)': 'rgba(255, 179, 71, 0.08)',
  'var(--color-success)': '#50C878',
  'var(--re-success-color)': '#50C878',
  'var(--re-success-color-translucent)': 'rgba(80, 200, 120, 0.08)',
  'var(--color-accent-positive)': '#50C878',
  'var(--color-accent-negative)': '#E85D75',
  'var(--color-text-secondary)': '#6B7280',
  'var(--accentPositive)': '#50C878',
  'var(--accentNegative)': '#E85D75',
  'var(--sentiment-positive, #28A745)': '#28A745',
  'var(--sentiment-negative, #E53E3E)': '#E53E3E',
  'var(--sentiment-neutral, #FFC107)': '#FFC107',
  'var(--sentiment-positive)': '#28A745',
  'var(--sentiment-negative)': '#E53E3E',
  'var(--sentiment-neutral)': '#FFC107',
  'var(--color-primary)': '#3498DB',
  'var(--color-secondary)': '#95A5A6'
};
const WORDCLOUD_CATEGORY_COLORS = {
  positive: '#10b981',
  negative: '#ef4444',
  neutral: '#6b7280',
  controversial: '#f59e0b'
};

function normalizeColorToken(color) {
  if (typeof color !== 'string') return color;
  const trimmed = color.trim();
  if (!trimmed) return null;
  // 支持 var(--token, fallback) 形式，优先解析fallback
  const varWithFallback = trimmed.match(/^var\(\s*--[^,)+]+,\s*([^)]+)\)/i);
  if (varWithFallback && varWithFallback[1]) {
    const fallback = varWithFallback[1].trim();
    const normalizedFallback = normalizeColorToken(fallback);
    if (normalizedFallback) return normalizedFallback;
  }
  if (CSS_VAR_COLOR_MAP[trimmed]) {
    return CSS_VAR_COLOR_MAP[trimmed];
  }
  if (trimmed.startsWith('var(')) {
    if (/accent|primary/i.test(trimmed)) return '#4A90E2';
    if (/danger|down|error/i.test(trimmed)) return '#E85D75';
    if (/warning/i.test(trimmed)) return '#FFB347';
    if (/success|up/i.test(trimmed)) return '#50C878';
    return '#3498DB';
  }
  return trimmed;
}

function hexToRgb(color) {
  if (typeof color !== 'string') return null;
  const normalized = color.replace('#', '');
  if (!(normalized.length === 3 || normalized.length === 6)) return null;
  const hex = normalized.length === 3 ? normalized.split('').map(c => c + c).join('') : normalized;
  const intVal = parseInt(hex, 16);
  if (Number.isNaN(intVal)) return null;
  return [(intVal >> 16) & 255, (intVal >> 8) & 255, intVal & 255];
}

function parseRgbString(color) {
  if (typeof color !== 'string') return null;
  const match = color.match(/rgba?\s*\(([^)]+)\)/i);
  if (!match) return null;
  const parts = match[1].split(',').map(p => parseFloat(p.trim())).filter(v => !Number.isNaN(v));
  if (parts.length < 3) return null;
  return [parts[0], parts[1], parts[2]].map(v => Math.max(0, Math.min(255, v)));
}

function alphaFromColor(color) {
  if (typeof color !== 'string') return null;
  const raw = color.trim();
  if (!raw) return null;
  if (raw.toLowerCase() === 'transparent') return 0;

  const extractAlpha = (source) => {
    const match = source.match(/rgba?\s*\(([^)]+)\)/i);
    if (!match) return null;
    const parts = match[1].split(',').map(p => p.trim());
    if (source.toLowerCase().startsWith('rgba') && parts.length >= 2) {
      const alphaToken = parts[parts.length - 1];
      const isPercent = /%$/.test(alphaToken);
      const alphaVal = parseFloat(alphaToken.replace('%', ''));
      if (!Number.isNaN(alphaVal)) {
        const normalizedAlpha = isPercent ? alphaVal / 100 : alphaVal;
        return Math.max(0, Math.min(1, normalizedAlpha));
      }
    }
    if (parts.length >= 3) return 1;
    return null;
  };

  const rawAlpha = extractAlpha(raw);
  if (rawAlpha !== null) return rawAlpha;

  const normalized = normalizeColorToken(raw);
  if (typeof normalized === 'string' && normalized !== raw) {
    const normalizedAlpha = extractAlpha(normalized);
    if (normalizedAlpha !== null) return normalizedAlpha;
  }

  return null;
}

function rgbFromColor(color) {
  const normalized = normalizeColorToken(color);
  return hexToRgb(normalized) || parseRgbString(normalized);
}

function colorLuminance(color) {
  const rgb = rgbFromColor(color);
  if (!rgb) return null;
  const [r, g, b] = rgb.map(v => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function lightenColor(color, ratio) {
  const rgb = rgbFromColor(color);
  if (!rgb) return color;
  const factor = Math.min(1, Math.max(0, ratio || 0.25));
  const mixed = rgb.map(v => Math.round(v + (255 - v) * factor));
  return `rgb(${mixed[0]}, ${mixed[1]}, ${mixed[2]})`;
}

function ensureAlpha(color, alpha) {
  const rgb = rgbFromColor(color);
  if (!rgb) return color;
  const clamped = Math.min(1, Math.max(0, alpha));
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${clamped})`;
}

function liftDarkColor(color) {
  const normalized = normalizeColorToken(color);
  const lum = colorLuminance(normalized);
  if (lum !== null && lum < 0.12) {
    return lightenColor(normalized, 0.35);
  }
  return normalized;
}

function mixColors(colorA, colorB, amount) {
  const rgbA = rgbFromColor(colorA);
  const rgbB = rgbFromColor(colorB);
  if (!rgbA && !rgbB) return colorA || colorB;
  if (!rgbA) return colorB;
  if (!rgbB) return colorA;
  const t = Math.min(1, Math.max(0, amount || 0));
  const mixed = rgbA.map((v, idx) => Math.round(v * (1 - t) + rgbB[idx] * t));
  return `rgb(${mixed[0]}, ${mixed[1]}, ${mixed[2]})`;
}

function pickComputedColor(keys, fallback, styles) {
  const styleRef = styles || getComputedStyle(document.body);
  for (const key of keys) {
    const val = styleRef.getPropertyValue(key);
    if (val && val.trim()) {
      const normalized = normalizeColorToken(val.trim());
      if (normalized) return normalized;
    }
  }
  return fallback;
}

function resolveWordcloudTheme() {
  const styles = getComputedStyle(document.body);
  const isDark = document.body.classList.contains('dark-mode');
  const text = pickComputedColor(['--text-color'], isDark ? '#e5e7eb' : '#111827', styles);
  const secondary = pickComputedColor(['--secondary-color', '--color-text-secondary'], isDark ? '#cbd5e1' : '#475569', styles);
  const accent = liftDarkColor(
    pickComputedColor(['--primary-color', '--color-accent', '--re-accent-color'], '#4A90E2', styles)
  );
  const cardBg = pickComputedColor(
    ['--card-bg', '--paper-bg', '--bg', '--bg-color', '--background', '--page-bg'],
    isDark ? '#0f172a' : '#ffffff',
    styles
  );
  return { text, secondary, accent, cardBg, isDark };
}

function normalizeDatasetColors(payload, chartType) {
  const changes = [];
  const data = payload && payload.data;
  if (!data || !Array.isArray(data.datasets)) {
    return changes;
  }
  const type = chartType || 'bar';
  const needsArrayColors = type === 'pie' || type === 'doughnut' || type === 'polarArea';
  const MIN_PIE_ALPHA = 0.6;
  const pickColor = (value, fallback) => {
    if (Array.isArray(value) && value.length) return value[0];
    return value || fallback;
  };

  data.datasets.forEach((dataset, idx) => {
    if (!isPlainObject(dataset)) return;
    if (type === 'line') {
      dataset.fill = true;  // 对折线图强制开启填充，便于区域对比
    }
    const paletteColor = normalizeColorToken(DEFAULT_CHART_COLORS[idx % DEFAULT_CHART_COLORS.length]);
    const borderInput = dataset.borderColor;
    const backgroundInput = dataset.backgroundColor;
    const borderIsArray = Array.isArray(borderInput);
    const bgIsArray = Array.isArray(backgroundInput);
    const baseCandidate = pickColor(borderInput, pickColor(backgroundInput, dataset.color || paletteColor));
    const liftedBase = liftDarkColor(baseCandidate || paletteColor);

    if (needsArrayColors) {
      const labelCount = Array.isArray(data.labels) ? data.labels.length : 0;
      const rawColors = bgIsArray ? backgroundInput : [];
      const dataLength = Array.isArray(dataset.data) ? dataset.data.length : 0;
      const total = Math.max(labelCount, rawColors.length, dataLength, 1);
      const normalizedColors = [];
      let fixedTransparentCount = 0;
      for (let i = 0; i < total; i++) {
        const fallbackColor = DEFAULT_CHART_COLORS[(idx + i) % DEFAULT_CHART_COLORS.length];
        const normalizedRaw = normalizeColorToken(rawColors[i]);
        const alpha = alphaFromColor(normalizedRaw);
        const isInvisible = typeof normalizedRaw === 'string' && normalizedRaw.toLowerCase() === 'transparent';
        if (alpha === 0 || isInvisible) {
          fixedTransparentCount += 1;
        }
        const baseColor = (!normalizedRaw || isInvisible) ? fallbackColor : normalizedRaw;
        const targetAlpha = alpha === null ? 1 : alpha;
        const normalizedColor = ensureAlpha(
          liftDarkColor(baseColor),
          Math.max(MIN_PIE_ALPHA, targetAlpha)
        );
        normalizedColors.push(normalizedColor);
      }
      dataset.backgroundColor = normalizedColors;
      dataset.borderColor = normalizedColors.map(col => ensureAlpha(liftDarkColor(col), 1));
      const changeLabel = fixedTransparentCount
        ? `dataset${idx}: 修正${fixedTransparentCount}个透明扇区`
        : `dataset${idx}: 标准化扇区颜色(${normalizedColors.length})`;
      changes.push(changeLabel);
      return;
    }

    if (!borderInput) {
      dataset.borderColor = liftedBase;
      changes.push(`dataset${idx}: 补全边框色`);
    } else if (borderIsArray) {
      dataset.borderColor = borderInput.map(col => liftDarkColor(col));
    } else {
      dataset.borderColor = liftDarkColor(borderInput);
    }

    const typeAlpha = type === 'line'
      ? (dataset.fill ? 0.25 : 0.18)
      : type === 'radar'
        ? 0.25
        : type === 'scatter' || type === 'bubble'
          ? 0.6
          : type === 'bar'
            ? 0.85
            : null;

    if (typeAlpha !== null) {
      if (bgIsArray && dataset.backgroundColor.length) {
        dataset.backgroundColor = backgroundInput.map(col => ensureAlpha(liftDarkColor(col), typeAlpha));
      } else {
        const bgSeed = pickColor(backgroundInput, pickColor(dataset.borderColor, paletteColor));
        dataset.backgroundColor = ensureAlpha(liftDarkColor(bgSeed), typeAlpha);
      }
      if (dataset.fill || type !== 'line') {
        changes.push(`dataset${idx}: 应用淡化填充以避免遮挡`);
      }
    } else if (!dataset.backgroundColor) {
      dataset.backgroundColor = ensureAlpha(liftedBase, 0.85);
    } else if (bgIsArray) {
      dataset.backgroundColor = backgroundInput.map(col => liftDarkColor(col));
    } else if (!bgIsArray) {
      dataset.backgroundColor = liftDarkColor(dataset.backgroundColor);
    }

    if (type === 'line' && !dataset.pointBackgroundColor) {
      dataset.pointBackgroundColor = Array.isArray(dataset.borderColor)
        ? dataset.borderColor[0]
        : dataset.borderColor;
    }
  });

  if (changes.length) {
    payload._colorAudit = changes;
  }
  return changes;
}

function getThemePalette() {
  const styles = getComputedStyle(document.body);
  return {
    text: styles.getPropertyValue('--text-color').trim(),
    grid: styles.getPropertyValue('--border-color').trim()
  };
}

function applyChartTheme(chart) {
  if (!chart) return;
  try {
    chart.update('none');
  } catch (err) {
    console.error('Chart refresh failed', err);
  }
}

function isPlainObject(value) {
  return Object.prototype.toString.call(value) === '[object Object]';
}

function cloneDeep(value) {
  if (Array.isArray(value)) {
    return value.map(cloneDeep);
  }
  if (isPlainObject(value)) {
    const obj = {};
    Object.keys(value).forEach(key => {
      obj[key] = cloneDeep(value[key]);
    });
    return obj;
  }
  return value;
}

function mergeOptions(base, override) {
  const result = isPlainObject(base) ? cloneDeep(base) : {};
  if (!isPlainObject(override)) {
    return result;
  }
  Object.keys(override).forEach(key => {
    const overrideValue = override[key];
    if (Array.isArray(overrideValue)) {
      result[key] = cloneDeep(overrideValue);
    } else if (isPlainObject(overrideValue)) {
      result[key] = mergeOptions(result[key], overrideValue);
    } else {
      result[key] = overrideValue;
    }
  });
  return result;
}

function resolveChartTypes(payload) {
  const explicit = payload && payload.props && payload.props.type;
  const widgetType = payload && payload.widgetType ? payload.widgetType : 'chart.js/bar';
  const derived = widgetType && widgetType.includes('/') ? widgetType.split('/').pop() : widgetType;
  const extra = Array.isArray(payload && payload.preferredTypes) ? payload.preferredTypes : [];
  const pipeline = [explicit, derived, ...extra, ...STABLE_CHART_TYPES].filter(Boolean);
  const result = [];
  pipeline.forEach(type => {
    if (type && !result.includes(type)) {
      result.push(type);
    }
  });
  return result.length ? result : ['bar'];
}

function describeChartType(type) {
  return CHART_TYPE_LABELS[type] || type || '图表';
}

function setChartDegradeNote(card, fromType, toType) {
  if (!card) return;
  card.setAttribute('data-chart-state', 'degraded');
  let note = card.querySelector('.chart-note');
  if (!note) {
    note = document.createElement('p');
    note.className = 'chart-note';
    card.appendChild(note);
  }
  note.textContent = `${describeChartType(fromType)}渲染失败，已自动切换为${describeChartType(toType)}以确保兼容。`;
}

function clearChartDegradeNote(card) {
  if (!card) return;
  card.removeAttribute('data-chart-state');
  const note = card.querySelector('.chart-note');
  if (note) {
    note.remove();
  }
}

function isWordCloudWidget(payload) {
  const type = payload && payload.widgetType;
  return typeof type === 'string' && type.toLowerCase().includes('wordcloud');
}

function hashString(str) {
  let h = 0;
  if (!str) return h;
  for (let i = 0; i < str.length; i++) {
    h = (h << 5) - h + str.charCodeAt(i);
    h |= 0;
  }
  return h;
}

function normalizeWordcloudItems(payload) {
  const sources = [];
  const props = payload && payload.props;
  const dataField = payload && payload.data;
  if (props) {
    ['data', 'items', 'words', 'sourceData'].forEach(key => {
      if (props[key]) sources.push(props[key]);
    });
  }
  if (dataField) {
    sources.push(dataField);
  }

  const seen = new Map();
  const pushItem = (word, weight, category) => {
    if (!word) return;
    let numeric = 1;
    if (typeof weight === 'number' && Number.isFinite(weight)) {
      numeric = weight;
    } else if (typeof weight === 'string') {
      const parsed = parseFloat(weight);
      numeric = Number.isFinite(parsed) ? parsed : 1;
    }
    if (!(numeric > 0)) numeric = 1;
    const cat = (category || '').toString().toLowerCase();
    const key = `${word}__${cat}`;
    const existing = seen.get(key);
    const payloadItem = { word: String(word), weight: numeric, category: cat };
    if (!existing || numeric > existing.weight) {
      seen.set(key, payloadItem);
    }
  };

  const consume = (raw) => {
    if (!raw) return;
    if (Array.isArray(raw)) {
      raw.forEach(item => {
        if (!item) return;
        if (Array.isArray(item)) {
          pushItem(item[0], item[1], item[2]);
        } else if (typeof item === 'object') {
          pushItem(item.word || item.text || item.label, item.weight, item.category);
        } else if (typeof item === 'string') {
          pushItem(item, 1, '');
        }
      });
    } else if (typeof raw === 'object') {
      Object.entries(raw).forEach(([word, weight]) => pushItem(word, weight, ''));
    }
  };

  sources.forEach(consume);

  const items = Array.from(seen.values());
  items.sort((a, b) => (b.weight || 0) - (a.weight || 0));
  return items.slice(0, 150);
}

function wordcloudColor(category) {
  const key = typeof category === 'string' ? category.toLowerCase() : '';
  const palette = resolveWordcloudTheme();
  const base = WORDCLOUD_CATEGORY_COLORS[key] || palette.accent || palette.secondary || '#334155';
  return liftDarkColor(base);
}

function renderWordCloudFallback(canvas, items, reason) {
  // 词云失败时的显示形式：隐藏 canvas，展示徽章列表（词+权重），保证“可见数据”而非空白
  const card = canvas.closest('.chart-card') || canvas.parentElement;
  if (!card) return;
  const wrapper = canvas.parentElement && canvas.parentElement.classList && canvas.parentElement.classList.contains('chart-container')
    ? canvas.parentElement
    : null;
  if (wrapper) {
    wrapper.style.display = 'none';
  } else {
    canvas.style.display = 'none';
  }
  let fallback = card.querySelector('.chart-fallback[data-dynamic="true"]');
  if (!fallback) {
    fallback = card.querySelector('.chart-fallback');
  }
  if (!fallback) {
    fallback = document.createElement('div');
    card.appendChild(fallback);
  }
  fallback.className = 'chart-fallback wordcloud-fallback';
  fallback.setAttribute('data-dynamic', 'true');
  fallback.style.display = 'block';
  fallback.innerHTML = '';
  card.setAttribute('data-chart-state', 'fallback');
  const buildBadge = (item, maxWeight) => {
    const badge = document.createElement('span');
    badge.className = 'wordcloud-badge';
    const clampedWeight = Math.max(0.5, (item.weight || 1));
    const normalized = Math.min(1, clampedWeight / (maxWeight || 1));
    const fontSize = 0.85 + normalized * 0.9;
    badge.style.fontSize = `${fontSize}rem`;
    badge.style.background = `linear-gradient(135deg, ${lightenColor(wordcloudColor(item.category), 0.05)} 0%, ${lightenColor(wordcloudColor(item.category), 0.15)} 100%)`;
    badge.style.borderColor = lightenColor(wordcloudColor(item.category), 0.25);
    badge.textContent = item.word;
    if (item.weight !== undefined && item.weight !== null) {
      const meta = document.createElement('small');
      meta.textContent = item.weight >= 0 && item.weight <= 1.5
        ? `${(item.weight * 100).toFixed(0)}%`
        : item.weight.toFixed(1).replace(/\.0+$/, '').replace(/0+$/, '').replace(/\.$/, '');
      badge.appendChild(meta);
    }
    return badge;
  };

  if (reason) {
    const notice = document.createElement('p');
    notice.className = 'chart-fallback__notice';
    notice.textContent = `词云未能渲染${reason ? `（${reason}）` : ''}，已展示关键词列表。`;
    fallback.appendChild(notice);
  }
  if (!items || !items.length) {
    const empty = document.createElement('p');
    empty.textContent = '暂无可用数据。';
    fallback.appendChild(empty);
    return;
  }
  const badges = document.createElement('div');
  badges.className = 'wordcloud-badges';
  const maxWeight = items.reduce((max, item) => Math.max(max, item.weight || 0), 1);
  items.forEach(item => {
    badges.appendChild(buildBadge(item, maxWeight));
  });
  fallback.appendChild(badges);
}

function renderWordCloud(canvas, payload, skipRegistry) {
  const items = normalizeWordcloudItems(payload);
  const card = canvas.closest('.chart-card') || canvas.parentElement;
  const container = canvas.parentElement && canvas.parentElement.classList && canvas.parentElement.classList.contains('chart-container')
    ? canvas.parentElement
    : null;
  if (!items.length) {
    renderWordCloudFallback(canvas, items, '无有效数据');
    return;
  }
  if (typeof WordCloud === 'undefined') {
    renderWordCloudFallback(canvas, items, '词云依赖未加载');
    return;
  }
  const theme = resolveWordcloudTheme();
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  const width = Math.max(260, (container ? container.clientWidth : canvas.clientWidth || canvas.width || 320));
  const height = Math.max(120, Math.round(width / 5)); // 5:1 宽高比
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  canvas.style.backgroundColor = 'transparent';

  const resolveBgColor = () => {
    const cardEl = card || container || document.body;
    const style = getComputedStyle(cardEl);
    const tokens = ['--card-bg', '--panel-bg', '--paper-bg', '--bg', '--background', '--page-bg'];
    for (const key of tokens) {
      const val = style.getPropertyValue(key);
      if (val && val.trim() && val.trim() !== 'transparent') return val.trim();
    }
    if (style.backgroundColor && style.backgroundColor !== 'rgba(0, 0, 0, 0)') return style.backgroundColor;
    const bodyStyle = getComputedStyle(document.body);
    for (const key of tokens) {
      const val = bodyStyle.getPropertyValue(key);
      if (val && val.trim() && val.trim() !== 'transparent') return val.trim();
    }
    if (bodyStyle.backgroundColor && bodyStyle.backgroundColor !== 'rgba(0, 0, 0, 0)') {
      return bodyStyle.backgroundColor;
    }
    return 'transparent';
  };
  const bgColor = resolveBgColor() || theme.cardBg || 'transparent';

  const maxWeight = items.reduce((max, item) => Math.max(max, item.weight || 0), 0) || 1;
  const weightLookup = new Map();
  const categoryLookup = new Map();
  items.forEach(it => {
    weightLookup.set(it.word, it.weight || 1);
    categoryLookup.set(it.word, it.category || '');
  });
  const list = items.map(item => [item.word, item.weight && item.weight > 0 ? item.weight : 1]);
  try {
    WordCloud(canvas, {
      list,
      gridSize: Math.max(3, Math.floor(Math.sqrt(canvas.width * canvas.height) / 170)),
      weightFactor: (val) => {
        const normalized = Math.max(0, val) / maxWeight;
        const cap = Math.min(width, height);
        const base = Math.max(9, cap / 5.5);
        const size = base * (0.8 + normalized * 1.3);
        return size * dpr;
      },
      color: (word) => {
        const w = weightLookup.get(word) || 1;
        const ratio = Math.max(0, Math.min(1, w / (maxWeight || 1)));
        const category = categoryLookup.get(word) || '';
        const base = wordcloudColor(category);
        const target = theme.isDark ? '#ffffff' : (theme.text || '#111827');
        const mixAmount = theme.isDark
          ? 0.28 + (1 - ratio) * 0.22
          : 0.12 + (1 - ratio) * 0.35;
        const mixed = mixColors(base, target, mixAmount);
        return ensureAlpha(mixed || base, theme.isDark ? 0.95 : 1);
      },
      rotateRatio: 0,
      rotationSteps: 0,
      shuffle: false,
      shrinkToFit: true,
      drawOutOfBound: false,
      shape: 'square',
      ellipticity: 0.45,
      clearCanvas: true,
      backgroundColor: bgColor
    });
    if (container) {
      container.style.display = '';
      container.style.minHeight = `${height}px`;
      container.style.background = 'transparent';
    }
    const fallback = card && card.querySelector('.chart-fallback');
    if (fallback) {
      fallback.style.display = 'none';
    }
    card && card.removeAttribute('data-chart-state');
    if (!skipRegistry) {
      wordCloudRegistry.set(canvas, () => renderWordCloud(canvas, payload, true));
    }
  } catch (err) {
    console.error('WordCloud 渲染失败', err);
    renderWordCloudFallback(canvas, items, err && err.message ? err.message : '');
  }
}

function createFallbackTable(labels, datasets) {
  if (!Array.isArray(datasets) || !datasets.length) {
    return null;
  }
  const primaryDataset = datasets.find(ds => Array.isArray(ds && ds.data));
  const resolvedLabels = Array.isArray(labels) && labels.length
    ? labels
    : (primaryDataset && primaryDataset.data ? primaryDataset.data.map((_, idx) => `数据点 ${idx + 1}`) : []);
  if (!resolvedLabels.length) {
    return null;
  }
  const table = document.createElement('table');
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  const categoryHeader = document.createElement('th');
  categoryHeader.textContent = '类别';
  headRow.appendChild(categoryHeader);
  datasets.forEach((dataset, index) => {
    const th = document.createElement('th');
    th.textContent = dataset && dataset.label ? dataset.label : `系列${index + 1}`;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  resolvedLabels.forEach((label, rowIdx) => {
    const row = document.createElement('tr');
    const labelCell = document.createElement('td');
    labelCell.textContent = label;
    row.appendChild(labelCell);
    datasets.forEach(dataset => {
      const cell = document.createElement('td');
      const series = dataset && Array.isArray(dataset.data) ? dataset.data[rowIdx] : undefined;
      if (typeof series === 'number') {
        cell.textContent = series.toLocaleString();
      } else if (series !== undefined && series !== null && series !== '') {
        cell.textContent = series;
      } else {
        cell.textContent = '—';
      }
      row.appendChild(cell);
    });
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  return table;
}

function renderChartFallback(canvas, payload, reason) {
  // 图表失败时的显示形式：切换到表格数据（categories x series），并在卡片上标记 fallback 状态
  const card = canvas.closest('.chart-card') || canvas.parentElement;
  if (!card) return;
  clearChartDegradeNote(card);
  const wrapper = canvas.parentElement && canvas.parentElement.classList && canvas.parentElement.classList.contains('chart-container')
    ? canvas.parentElement
    : null;
  if (wrapper) {
    wrapper.style.display = 'none';
  } else {
    canvas.style.display = 'none';
  }
  let fallback = card.querySelector('.chart-fallback[data-dynamic="true"]');
  let prebuilt = false;
  if (!fallback) {
    fallback = card.querySelector('.chart-fallback');
    if (fallback) {
      prebuilt = fallback.hasAttribute('data-prebuilt');
    }
  }
  if (!fallback) {
    fallback = document.createElement('div');
    fallback.className = 'chart-fallback';
    fallback.setAttribute('data-dynamic', 'true');
    card.appendChild(fallback);
  } else if (!prebuilt) {
    fallback.innerHTML = '';
  }
  const titleFromOptions = payload && payload.props && payload.props.options &&
    payload.props.options.plugins && payload.props.options.plugins.title &&
    payload.props.options.plugins.title.text;
  const fallbackTitle = titleFromOptions ||
    (payload && payload.props && payload.props.title) ||
    (payload && payload.widgetId) ||
    canvas.getAttribute('id') ||
    '图表';
  const existingNotice = fallback.querySelector('.chart-fallback__notice');
  if (existingNotice) {
    existingNotice.remove();
  }
  const notice = document.createElement('p');
  notice.className = 'chart-fallback__notice';
  notice.textContent = `${fallbackTitle}：图表未能渲染，已展示表格数据${reason ? `（${reason}）` : ''}`;
  fallback.insertBefore(notice, fallback.firstChild || null);
  if (!prebuilt) {
    const table = createFallbackTable(
      payload && payload.data && payload.data.labels,
      payload && payload.data && payload.data.datasets
    );
    if (table) {
      fallback.appendChild(table);
    }
  }
  fallback.style.display = 'block';
  card.setAttribute('data-chart-state', 'fallback');
}

function buildChartOptions(payload) {
  const rawLegend = payload && payload.props ? payload.props.legend : undefined;
  let legendConfig;
  if (isPlainObject(rawLegend)) {
    legendConfig = mergeOptions({
      display: rawLegend.display !== false,
      position: rawLegend.position || 'top'
    }, rawLegend);
  } else {
    legendConfig = {
      display: rawLegend === 'hidden' ? false : true,
      position: typeof rawLegend === 'string' ? rawLegend : 'top'
    };
  }
  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: legendConfig
    }
  };
  if (payload && payload.props && payload.props.title) {
    baseOptions.plugins.title = {
      display: true,
      text: payload.props.title
    };
  }
  const overrideOptions = payload && payload.props && payload.props.options;
  return mergeOptions(baseOptions, overrideOptions);
}

function validateChartData(payload, type) {
  /**
   * 前端验证图表数据
   * 返回: { valid: boolean, errors: string[] }
   */
  const errors = [];

  if (!payload || typeof payload !== 'object') {
    errors.push('无效的payload');
    return { valid: false, errors };
  }

  const data = payload.data;
  if (!data || typeof data !== 'object') {
    errors.push('缺少data字段');
    return { valid: false, errors };
  }

  // 特殊图表类型（scatter, bubble）
  const specialTypes = { 'scatter': true, 'bubble': true };
  if (specialTypes[type]) {
    // 这些类型需要特殊的数据格式 {x, y} 或 {x, y, r}
    // 跳过标准验证
    return { valid: true, errors };
  }

  // 标准图表类型验证
  const datasets = data.datasets;
  if (!Array.isArray(datasets)) {
    errors.push('datasets必须是数组');
    return { valid: false, errors };
  }

  if (datasets.length === 0) {
    errors.push('datasets数组为空');
    return { valid: false, errors };
  }

  // 验证每个dataset
  for (let i = 0; i < datasets.length; i++) {
    const dataset = datasets[i];
    if (!dataset || typeof dataset !== 'object') {
      errors.push(`datasets[${i}]不是对象`);
      continue;
    }

    if (!Array.isArray(dataset.data)) {
      errors.push(`datasets[${i}].data不是数组`);
    } else if (dataset.data.length === 0) {
      errors.push(`datasets[${i}].data为空`);
    }
  }

  // 需要labels的图表类型
  const labelRequiredTypes = {
    'line': true, 'bar': true, 'radar': true,
    'polarArea': true, 'pie': true, 'doughnut': true
  };

  if (labelRequiredTypes[type]) {
    const labels = data.labels;
    if (!Array.isArray(labels)) {
      errors.push('缺少labels数组');
    } else if (labels.length === 0) {
      errors.push('labels数组为空');
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

function instantiateChart(ctx, payload, optionsTemplate, type) {
  if (!ctx) {
    return null;
  }
  if (ctx.canvas && typeof Chart !== 'undefined' && typeof Chart.getChart === 'function') {
    const existing = Chart.getChart(ctx.canvas);
    if (existing) {
      existing.destroy();
    }
  }
  const data = cloneDeep(payload && payload.data ? payload.data : {});
  const config = {
    type,
    data,
    options: cloneDeep(optionsTemplate)
  };
  return new Chart(ctx, config);
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(null, args), wait || 200);
  };
}

function hydrateCharts() {
  document.querySelectorAll('canvas[data-config-id]').forEach(canvas => {
    const configScript = document.getElementById(canvas.dataset.configId);
    if (!configScript) return;
    let payload;
    try {
      payload = JSON.parse(configScript.textContent);
    } catch (err) {
      console.error('Widget JSON 解析失败', err);
      renderChartFallback(canvas, { widgetId: canvas.dataset.configId }, '配置解析失败');
      return;
    }
    if (isWordCloudWidget(payload)) {
      renderWordCloud(canvas, payload);
      return;
    }
    if (typeof Chart === 'undefined') {
      renderChartFallback(canvas, payload, 'Chart.js 未加载');
      return;
    }
    const chartTypes = resolveChartTypes(payload);
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      renderChartFallback(canvas, payload, 'Canvas 初始化失败');
      return;
    }

    // 前端数据验证
    const desiredType = chartTypes[0];
    const card = canvas.closest('.chart-card') || canvas.parentElement;
    const colorAdjustments = normalizeDatasetColors(payload, desiredType);
    if (colorAdjustments.length && card) {
      card.setAttribute('data-chart-color-fixes', colorAdjustments.join(' | '));
    }
    const validation = validateChartData(payload, desiredType);
    if (!validation.valid) {
      console.warn('图表数据验证失败:', validation.errors);
      // 验证失败但仍然尝试渲染，因为可能会降级成功
    }

    const optionsTemplate = buildChartOptions(payload);
    let chartInstance = null;
    let selectedType = null;
    let lastError;
    for (const type of chartTypes) {
      try {
        chartInstance = instantiateChart(ctx, payload, optionsTemplate, type);
        selectedType = type;
        break;
      } catch (err) {
        lastError = err;
        console.error('图表渲染失败', type, err);
      }
    }
    if (chartInstance) {
      chartRegistry.push(chartInstance);
      try {
        applyChartTheme(chartInstance);
      } catch (err) {
        console.error('主题同步失败', selectedType || desiredType || payload && payload.widgetType || 'chart', err);
      }
      if (selectedType && selectedType !== desiredType) {
        setChartDegradeNote(card, desiredType, selectedType);
      } else {
        clearChartDegradeNote(card);
      }
    } else {
      const reason = lastError && lastError.message ? lastError.message : '';
      renderChartFallback(canvas, payload, reason);
    }
  });
}

function getExportOverlayParts() {
  const overlay = document.getElementById('export-overlay');
  if (!overlay) {
    return null;
  }
  return {
    overlay,
    status: overlay.querySelector('.export-status')
  };
}

function showExportOverlay(message) {
  const parts = getExportOverlayParts();
  if (!parts) return;
  if (message && parts.status) {
    parts.status.textContent = message;
  }
  parts.overlay.classList.add('active');
  document.body.classList.add('exporting');
}

function updateExportOverlay(message) {
  if (!message) return;
  const parts = getExportOverlayParts();
  if (parts && parts.status) {
    parts.status.textContent = message;
  }
}

function hideExportOverlay(delay) {
  const parts = getExportOverlayParts();
  if (!parts) return;
  const close = () => {
    parts.overlay.classList.remove('active');
    document.body.classList.remove('exporting');
  };
  if (delay && delay > 0) {
    setTimeout(close, delay);
  } else {
    close();
  }
}

// exportPdf已移除
function exportPdf() {
  // 导出按钮交互：禁用按钮+打开遮罩，使用 html2canvas + jsPDF 渲染 main，再恢复按钮与遮罩
  const target = document.querySelector('main');
  if (!target || typeof jspdf === 'undefined' || typeof jspdf.jsPDF !== 'function') {
    alert('PDF导出依赖未就绪');
    return;
  }
  const exportBtn = document.getElementById('export-btn');
  if (exportBtn) {
    exportBtn.disabled = true;
  }
  showExportOverlay('正在导出PDF，请稍候...');
  document.body.classList.add('exporting');
  const pdf = new jspdf.jsPDF('p', 'mm', 'a4');
  try {
    if (window.pdfFontData) {
      pdf.addFileToVFS('SourceHanSerifSC-Medium.ttf', window.pdfFontData);
      pdf.addFont('SourceHanSerifSC-Medium.ttf', 'SourceHanSerif', 'normal');
      pdf.setFont('SourceHanSerif');
      console.log('PDF字体已成功加载');
    } else {
      console.warn('PDF字体数据未找到，将使用默认字体');
    }
  } catch (err) {
    console.warn('Custom PDF font setup failed, fallback to default', err);
  }
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pxWidth = Math.max(
    target.scrollWidth,
    document.documentElement.scrollWidth,
    Math.round(pageWidth * 3.78)
  );
  const restoreButton = () => {
    if (exportBtn) {
      exportBtn.disabled = false;
    }
    document.body.classList.remove('exporting');
  };
  let renderTask;
  try {
    // force charts to rerender at full width before capture
    chartRegistry.forEach(chart => {
      if (chart && typeof chart.resize === 'function') {
        chart.resize();
      }
    });
    wordCloudRegistry.forEach(fn => {
      if (typeof fn === 'function') {
        try {
          fn();
        } catch (err) {
          console.error('词云重新渲染失败', err);
        }
      }
    });
    renderTask = pdf.html(target, {
      x: 8,
      y: 12,
      width: pageWidth - 16,
      margin: [12, 12, 20, 12],
      autoPaging: 'text',
      windowWidth: pxWidth,
      html2canvas: {
        scale: Math.min(1.5, Math.max(1.0, pageWidth / (target.clientWidth || pageWidth))),
        useCORS: true,
        scrollX: 0,
        scrollY: -window.scrollY,
        logging: false,
        allowTaint: true,
        backgroundColor: '#ffffff'
      },
      pagebreak: {
        mode: ['css', 'legacy'],
        avoid: [
          '.chapter > *',
          '.callout',
          '.chart-card',
          '.table-wrap',
          '.kpi-grid',
          '.hero-section'
        ],
        before: '.chapter-divider'
      },
      callback: (doc) => doc.save('report.pdf')
    });
  } catch (err) {
    console.error('PDF 导出失败', err);
    updateExportOverlay('导出失败，请稍后重试');
    hideExportOverlay(1200);
    restoreButton();
    alert('PDF导出失败，请稍后重试');
    return;
  }
  if (renderTask && typeof renderTask.then === 'function') {
    renderTask.then(() => {
      updateExportOverlay('导出完成，正在保存...');
      hideExportOverlay(800);
      restoreButton();
    }).catch(err => {
      console.error('PDF 导出失败', err);
      updateExportOverlay('导出失败，请稍后重试');
      hideExportOverlay(1200);
      restoreButton();
      alert('PDF导出失败，请稍后重试');
    });
  } else {
    hideExportOverlay();
    restoreButton();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const rerenderWordclouds = debounce(() => {
    wordCloudRegistry.forEach(fn => {
      if (typeof fn === 'function') {
        fn();
      }
    });
  }, 260);
  // 旧版 Web Component 主题按钮（已注释）
  // const themeBtn = document.getElementById('theme-toggle');
  // if (themeBtn) {
  //   themeBtn.addEventListener('change', (e) => {
  //     if (e.detail === 'dark') {
  //       document.body.classList.add('dark-mode');
  //     } else {
  //       document.body.classList.remove('dark-mode');
  //     }
  //     chartRegistry.forEach(applyChartTheme);
  //     rerenderWordclouds();
  //   });
  // }

  // 新版 action-btn 风格主题按钮
  const themeBtnNew = document.getElementById('theme-toggle-btn');
  if (themeBtnNew) {
    const sunIcon = themeBtnNew.querySelector('.sun-icon');
    const moonIcon = themeBtnNew.querySelector('.moon-icon');
    let isDark = document.body.classList.contains('dark-mode');

    const updateThemeUI = () => {
      if (isDark) {
        sunIcon.style.display = 'none';
        moonIcon.style.display = 'block';
      } else {
        sunIcon.style.display = 'block';
        moonIcon.style.display = 'none';
      }
    };
    updateThemeUI();

    themeBtnNew.addEventListener('click', () => {
      isDark = !isDark;
      if (isDark) {
        document.body.classList.add('dark-mode');
      } else {
        document.body.classList.remove('dark-mode');
      }
      updateThemeUI();
      chartRegistry.forEach(applyChartTheme);
      rerenderWordclouds();
    });
  }
  const printBtn = document.getElementById('print-btn');
  if (printBtn) {
    // 打印按钮：直接调用浏览器打印，依赖 @media print 控制布局
    printBtn.addEventListener('click', () => window.print());
  }
  // 为所有 action-btn 添加鼠标追踪光晕效果
  document.querySelectorAll('.action-btn').forEach(btn => {
    btn.addEventListener('mousemove', (e) => {
      const rect = btn.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      btn.style.setProperty('--mouse-x', x + '%');
      btn.style.setProperty('--mouse-y', y + '%');
    });
    btn.addEventListener('mouseleave', () => {
      btn.style.setProperty('--mouse-x', '50%');
      btn.style.setProperty('--mouse-y', '50%');
    });
  });
  const exportBtn = document.getElementById('export-btn');
  if (exportBtn) {
    // 导出按钮：调用 exportPdf（html2canvas + jsPDF），并驱动遮罩/进度提示
    exportBtn.addEventListener('click', exportPdf);
  }
  window.addEventListener('resize', rerenderWordclouds);
  hydrateCharts();
});
</script>
""".strip()


__all__ = ["HTMLRenderer"]
