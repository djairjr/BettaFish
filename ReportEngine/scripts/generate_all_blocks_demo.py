#!/usr/bin/env python3
"""Generate demo IR covering all allowed block types for verifying HTML and PDF rendering.

After execution, a time-stamped IR will be written to `final_reports/ir`.
And output the corresponding rendering files in `final_reports/html` and `final_reports/pdf` respectively."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Allows running directly as a script
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ReportEngine.core import DocumentComposer
from ReportEngine.ir import IRValidator
from ReportEngine.ir.schema import ENGINE_AGENT_TITLES
from ReportEngine.renderers import HTMLRenderer, PDFRenderer
from ReportEngine.utils.config import settings


def build_inline_marks_demo() -> dict:
    """Generate a paragraph block covering all inline markup."""
    return {
        "type": "paragraph",
        "inlines": [
            {"text": "This section covers all inline markup:"},
            {"text": "Bold", "marks": [{"type": "bold"}]},
            {"text": "/italic", "marks": [{"type": "italic"}]},
            {"text": "/ underline", "marks": [{"type": "underline"}]},
            {"text": "/ strikethrough", "marks": [{"type": "strike"}]},
            {"text": "/code", "marks": [{"type": "code"}]},
            {
                "text": "/ Link",
                "marks": [
                    {
                        "type": "link",
                        "href": "https://example.com/demo",
                        "title": "Example link",
                    }
                ],
            },
            {"text": "/ color", "marks": [{"type": "color", "value": "#c0392b"}]},
            {
                "text": "/font",
                "marks": [
                    {
                        "type": "font",
                        "family": "Georgia, serif",
                        "size": "15px",
                        "weight": "600",
                    }
                ],
            },
            {"text": "/ highlight", "marks": [{"type": "highlight"}]},
            {"text": "/ subscript", "marks": [{"type": "subscript"}]},
            {"text": "/ superscript", "marks": [{"type": "superscript"}]},
            {"text": "/ inline formula", "marks": [{"type": "math", "value": "E=mc^2"}]},
            {"text": "。"},
        ],
    }


def build_widget_block() -> dict:
    """Construct a valid Chart.js widget block."""
    return {
        "type": "widget",
        "widgetId": "demo-volume-trend",
        "widgetType": "chart.js/line",
        "props": {
            "type": "line",
            "options": {
                "responsive": True,
                "plugins": {"legend": {"position": "bottom"}},
                "scales": {"y": {"title": {"display": True, "text": "Mentions"}}},
            },
        },
        "data": {
            "labels": ["T0", "T0+6h", "T0+12h", "T0+18h", "T0+24h"],
            "datasets": [
                {
                    "label": "mainstream media",
                    "data": [12, 18, 23, 30, 26],
                    "borderColor": "#2980b9",
                    "backgroundColor": "rgba(41,128,185,0.18)",
                    "tension": 0.25,
                    "fill": False,
                },
                {
                    "label": "social platform",
                    "data": [8, 10, 15, 28, 40],
                    "borderColor": "#c0392b",
                    "backgroundColor": "rgba(192,57,43,0.2)",
                    "tension": 0.35,
                    "fill": False,
                },
            ],
        },
    }


def build_chapters() -> list[dict]:
    """Constructs a list of chapters covering all block types."""
    inline_demo = build_inline_marks_demo()

    bullet_list = {
        "type": "list",
        "listType": "bullet",
        "items": [
            [
                {
                    "type": "paragraph",
                    "inlines": [{"text": "Social media popularity doubles in 48 hours"}],
                }
            ],
            [
                {
                    "type": "paragraph",
                    "inlines": [{"text": "Mainstream media coverage focuses on morning hours"}],
                },
                {
                    "type": "list",
                    "listType": "ordered",
                    "items": [
                        [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "07:00-09:00: First round of coverage"}],
                            }
                        ],
                        [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "10:00-12:00: Comments spread"}],
                            }
                        ],
                    ],
                },
            ],
            [
                {
                    "type": "paragraph",
                    "inlines": [{"text": "Local government affairs accounts began to respond and synchronize offline releases"}],
                }
            ],
        ],
    }

    task_list = {
        "type": "list",
        "listType": "task",
        "items": [
            [
                {
                    "type": "paragraph",
                    "inlines": [{"text": "Track whether authoritative rumor-refuting materials are online"}],
                }
            ],
            [
                {
                    "type": "paragraph",
                    "inlines": [{"text": "Monitor new related keywords and long-tail issues"}],
                }
            ],
            [
                {
                    "type": "paragraph",
                    "inlines": [{"text": "Prepare FAQ for customer service to answer uniformly"}],
                }
            ],
        ],
    }

    table_block = {
        "type": "table",
        "caption": "Core information sources and communication paths",
        "zebra": True,
        "colgroup": [{"width": "22%"}, {"width": "38%"}, {"width": "40%"}],
        "rows": [
            {
                "cells": [
                    {
                        "align": "center",
                        "blocks": [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "Time node", "marks": [{"type": "bold"}]}],
                            }
                        ],
                    },
                    {
                        "align": "center",
                        "blocks": [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "Event content", "marks": [{"type": "bold"}]}],
                            }
                        ],
                    },
                    {
                        "align": "center",
                        "blocks": [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "main channel", "marks": [{"type": "bold"}]}],
                            }
                        ],
                    },
                ]
            },
            {
                "cells": [
                    {"blocks": [{"type": "paragraph", "inlines": [{"text": "T0"}]}]},
                    {
                        "blocks": [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "Offline conflict video uploaded for the first time"}],
                            }
                        ]
                    },
                    {
                        "blocks": [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "Short video platform/private chat forwarding"}],
                            }
                        ]
                    },
                ]
            },
            {
                "cells": [
                    {"blocks": [{"type": "paragraph", "inlines": [{"text": "T0+6h"}]}]},
                    {
                        "blocks": [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "On the hot search, secondary editing appeared"}],
                            }
                        ]
                    },
                    {
                        "blocks": [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "Weibo/Moments"}],
                            }
                        ]
                    },
                ]
            },
            {
                "cells": [
                    {"blocks": [{"type": "paragraph", "inlines": [{"text": "T0+18h"}]}]},
                    {
                        "blocks": [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "Official response and issue clarification of facts"}],
                            }
                        ]
                    },
                    {
                        "blocks": [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "Government Account/News Client"}],
                            }
                        ]
                    },
                ]
            },
            {
                "cells": [
                    {"blocks": [{"type": "paragraph", "inlines": [{"text": "T0+24h"}]}]},
                    {
                        "blocks": [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "Experts interpret that the focus of public opinion turns to responsibility"}],
                            }
                        ]
                    },
                    {
                        "blocks": [
                            {
                                "type": "paragraph",
                                "inlines": [{"text": "Video account live broadcast/industry community"}],
                            }
                        ]
                    },
                ]
            },
        ],
    }

    blockquote_block = {
        "type": "blockquote",
        "variant": "accent",
        "blocks": [
            {
                "type": "paragraph",
                "inlines": [{"text": "“The message that the public cares most about is truth and boundaries of accountability.”"}],
            },
            {
                "type": "paragraph",
                "inlines": [{"text": "——Simulate quotation and verify quotation block style"}],
            },
        ],
    }

    engine_quote_block = {
        "type": "engineQuote",
        "engine": "insight",
        "title": ENGINE_AGENT_TITLES["insight"],
        "blocks": [
            {
                "type": "paragraph",
                "inlines": [
                    {
                        "text": "The model believes that maintaining response frequency within 24 hours can avoid an information vacuum.",
                        "marks": [{"type": "bold"}],
                    }
                ],
            },
            {
                "type": "paragraph",
                "inlines": [
                    {"text": "It is recommended to prepare a short FAQ at the same time to facilitate unified communication across multiple channels."}
                ],
            },
        ],
    }

    swot_block = {
        "type": "swotTable",
        "title": "Public opinion field SWOT quick overview",
        "summary": "Covers current sentiment distribution, potential risks and opportunities.",
        "strengths": [
            {"title": "Official quick response", "detail": "The first clarification video will be online within 3 hours"},
            {"title": "Cooperation with local media", "impact": "high", "score": 8},
        ],
        "weaknesses": [
            {"title": "There was a lot of early rumors", "detail": "Related forwarding still accounts for 30%"},
            "External experts have not yet unanimously agreed on the",
        ],
        "opportunities": [
            {
                "title": "Community co-construction discussion",
                "detail": "Spontaneously organized the topic of "Rumor Refuting Volunteers" and the mood was positive",
            },
            {"title": "Public welfare cooperation window", "impact": "middle"},
        ],
        "threats": [
            {"title": "Cross-platform editing continues to ferment", "impact": "high", "score": 9},
            {"title": "Individual self-media incites emotions", "evidence": "There is a tendency for regional labeling"},
        ],
    }

    pest_block = {
        "type": "pestTable",
        "title": "Macroenvironmental pulse scanning (PEST)",
        "summary": "Simulate external constraints and opportunities in four dimensions to verify the rendering style of pestTable.",
        "political": [
            {
                "title": "Solicitation of local ordinances",
                "detail": "Short video releases require real-name traceability, and the platform’s compliance communication window is open",
                "trend": "Positive",
                "impact": 7,
            },
            {
                "title": "Regulatory concerns over emotional incitement",
                "detail": "Focus on inspections of accounts that exaggerate contradictions, and lower the public opinion threshold",
                "trend": "Continuous observation",
                "impact": 6,
            },
        ],
        "economic": [
            {
                "title": "Surrounding merchants’ revenue fluctuates",
                "detail": "Customer flow fell by 12% in the short term, but live streaming orders increased",
                "trend": "neutral",
                "impact": 5,
            },
            {
                "title": "Be cautious about brand sponsorships",
                "detail": "Sponsorship extension to observe reputational risks, putting pressure on the pace of official announcements",
                "trend": "uncertain",
                "impact": 4,
            },
        ],
        "social": [
            {
                "title": "Emotional differentiation among core groups",
                "detail": "Local residents are concerned about safety, while foreign tourists are concerned about experience and refunds",
                "trend": "negative impact",
                "impact": 8,
            },
            {
                "title": "University communities spontaneously seek verification",
                "detail": "The school media and the student union organized a "search for pictures by pictures" popular science post, and the mood stabilized",
                "trend": "Positive",
                "impact": 6,
            },
        ],
        "technological": [
            {
                "title": "AI-generated content is mixed in",
                "detail": "Part of the picture is enlarged and then disseminated, and watermark traceability tools are needed to assist in detecting counterfeiting.",
                "trend": "negative impact",
                "impact": 7,
            },
            {
                "title": "Multimodal retrieval is online",
                "detail": "The platform piloted the "video anti-fraud" model and automatically prompted for traces of editing",
                "trend": "Positive",
                "impact": 5,
            },
        ],
    }

    callout_block = {
        "type": "callout",
        "tone": "warning",
        "title": "Typesetting boundary tips",
        "blocks": [
            {
                "type": "paragraph",
                "inlines": [
                    {"text": "Only light content is placed inside the callout, and the excess content will automatically overflow to the outer layer."}
                ],
            },
            {
                "type": "list",
                "listType": "bullet",
                "items": [
                    [
                        {
                            "type": "paragraph",
                            "inlines": [{"text": "Support nested lists/tables/mathematical formulas"}],
                        }
                    ],
                    [
                        {
                            "type": "paragraph",
                            "inlines": [{"text": "Reminders or action steps can be placed here"}],
                        }
                    ],
                ],
            },
        ],
    }

    code_block = {
        "type": "code",
        "lang": "json",
        "caption": "Demo code block",
        "content": '{\n  "event": "Hotspot example",\n  "topic": "public events",\n  "status": "monitoring"\n}',
    }

    math_block = {
        "type": "math",
        "latex": r"E = mc^2",
        "displayMode": True,
    }

    figure_block = {
        "type": "figure",
        "img": {
            "src": "https://dummyimage.com/600x320/eeeeee/333333&text=Placeholder",
            "alt": "Placeholder diagram",
            "width": 600,
            "height": 320,
        },
        "caption": "Image external links are replaced with friendly tips to verify the figure placeholder effect.",
        "responsive": True,
    }

    widget_block = build_widget_block()
    stacked_bar_chart_block = {
        "type": "widget",
        "widgetId": "demo-stacked-sentiment",
        "widgetType": "chart.js/bar",
        "props": {
            "type": "bar",
            "options": {
                "responsive": True,
                "plugins": {"legend": {"position": "bottom"}},
                "scales": {
                    "x": {"stacked": True},
                    "y": {"stacked": True, "title": {"display": True, "text": "amount of information"}},
                },
            },
        },
        "data": {
            "labels": ["on Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "datasets": [
                {"label": "forward", "data": [18, 22, 24, 19, 16], "backgroundColor": "#27ae60"},
                {"label": "neutral", "data": [22, 20, 18, 21, 23], "backgroundColor": "#f39c12"},
                {"label": "Negative", "data": [12, 14, 10, 9, 11], "backgroundColor": "#c0392b"},
            ],
        },
    }
    doughnut_chart_block = {
        "type": "widget",
        "widgetId": "demo-sentiment-share",
        "widgetType": "chart.js/doughnut",
        "props": {
            "type": "doughnut",
            "options": {"plugins": {"legend": {"position": "right"}, "tooltip": {"enabled": True}}},
        },
        "data": {
            "labels": ["policy", "economy", "society", "technology"],
            "datasets": [
                {
                    "label": "Attention ratio",
                    "data": [24, 30, 28, 18],
                    "backgroundColor": ["#8e44ad", "#16a085", "#e67e22", "#2980b9"],
                    "hoverOffset": 6,
                }
            ],
        },
    }
    radar_chart_block = {
        "type": "widget",
        "widgetId": "demo-response-radar",
        "widgetType": "chart.js/radar",
        "props": {
            "type": "radar",
            "options": {
                "plugins": {"legend": {"position": "top"}},
                "scales": {"r": {"beginAtZero": True, "max": 100}},
            },
        },
        "data": {
            "labels": ["transparency", "Response speed", "consistency", "Interaction", "amount of information"],
            "datasets": [
                {
                    "label": "official channels",
                    "data": [78, 88, 82, 66, 91],
                    "backgroundColor": "rgba(46,204,113,0.15)",
                    "borderColor": "#2ecc71",
                    "pointBackgroundColor": "#27ae60",
                },
                {
                    "label": "civil discussion",
                    "data": [64, 72, 58, 74, 63],
                    "backgroundColor": "rgba(52,152,219,0.12)",
                    "borderColor": "#3498db",
                    "pointBackgroundColor": "#2980b9",
                },
            ],
        },
    }
    polar_area_chart_block = {
        "type": "widget",
        "widgetId": "demo-channel-polar",
        "widgetType": "chart.js/polarArea",
        "props": {"type": "polarArea"},
        "data": {
            "labels": ["short video", "Weibo", "community forum", "news client", "Offline feedback"],
            "datasets": [
                {
                    "label": "channel penetration",
                    "data": [62, 54, 38, 45, 28],
                    "backgroundColor": [
                        "rgba(231,76,60,0.65)",
                        "rgba(142,68,173,0.6)",
                        "rgba(52,152,219,0.55)",
                        "rgba(46,204,113,0.55)",
                        "rgba(241,196,15,0.6)",
                    ],
                }
            ],
        },
    }
    scatter_chart_block = {
        "type": "widget",
        "widgetId": "demo-correlation-scatter",
        "widgetType": "chart.js/scatter",
        "props": {
            "type": "scatter",
            "options": {
                "plugins": {"legend": {"position": "bottom"}},
                "scales": {
                    "x": {"title": {"display": True, "text": "emotional polarity"}, "min": -1, "max": 1},
                    "y": {"title": {"display": True, "text": "Interaction volume"}, "beginAtZero": True},
                },
            },
        },
        "data": {
            "datasets": [
                {
                    "label": "Scattered posts",
                    "data": [
                        {"x": -0.65, "y": 120},
                        {"x": -0.25, "y": 190},
                        {"x": 0.05, "y": 260},
                        {"x": 0.42, "y": 340},
                        {"x": 0.78, "y": 410},
                    ],
                    "backgroundColor": "rgba(52,152,219,0.7)",
                }
            ],
        },
    }
    bubble_chart_block = {
        "type": "widget",
        "widgetId": "demo-impact-bubble",
        "widgetType": "chart.js/bubble",
        "props": {
            "type": "bubble",
            "options": {
                "plugins": {"legend": {"position": "bottom"}},
                "scales": {
                    "x": {"title": {"display": True, "text": "Exposure (10,000)"}, "beginAtZero": True},
                    "y": {"title": {"display": True, "text": "emotional intensity"}, "min": -100, "max": 100},
                },
            },
        },
        "data": {
            "datasets": [
                {
                    "label": "Channel distribution",
                    "data": [
                        {"x": 8, "y": 35, "r": 12},
                        {"x": 12, "y": -28, "r": 10},
                        {"x": 18, "y": 22, "r": 14},
                        {"x": 25, "y": 48, "r": 16},
                        {"x": 6, "y": -12, "r": 8},
                    ],
                    "backgroundColor": "rgba(192,57,43,0.55)",
                    "borderColor": "#c0392b",
                }
            ],
        },
    }

    chapter_1 = {
        "chapterId": "S1",
        "title": "Cover and Table of Contents",
        "anchor": "overview",
        "order": 10,
        "blocks": [
            {"type": "heading", "level": 2, "text": "1. Cover and Table of Contents", "anchor": "overview"},
            {
                "type": "paragraph",
                "inlines": [
                    {
                        "text": "Simulate abstracts of hot public events in society to facilitate quick confirmation of typesetting and font effects.",
                    }
                ],
            },
            inline_demo,
            {
                "type": "kpiGrid",
                "items": [
                    {"label": "24h mentions", "value": "98K", "delta": "+41%", "deltaTone": "up"},
                    {"label": "Positive proportion", "value": "32%", "delta": "+5pp", "deltaTone": "up"},
                    {"label": "Negative proportion", "value": "18%", "delta": "-3pp", "deltaTone": "down"},
                    {"label": "high frequency channel", "value": "Short video / Weibo"},
                ],
                "cols": 4,
            },
            {"type": "toc"},
            {"type": "hr"},
        ],
    }

    chapter_2 = {
        "chapterId": "S2",
        "title": "Block type demo",
        "anchor": "blocks-showcase",
        "order": 20,
        "blocks": [
            {
                "type": "heading",
                "level": 2,
                "text": "2. Block type demonstration",
                "anchor": "blocks-showcase",
            },
            {
                "type": "paragraph",
                "inlines": [
                    {
                        "text": "The following content covers all block types such as paragraph/list/table/swot/pest/widget one by one.",
                    }
                ],
            },
            {
                "type": "heading",
                "level": 3,
                "text": "2.1 Lists and tables",
                "anchor": "lists-and-tables",
            },
            bullet_list,
            task_list,
            table_block,
            {
                "type": "heading",
                "level": 3,
                "text": "2.2 Chart component demonstration",
                "anchor": "charts-demo",
            },
            {
                "type": "paragraph",
                "inlines": [
                    {
                        "text": "Multiple types of charts such as line/column/pie chart/radar/polar area/scatter/bubble are used to verify Chart.js compatibility.",
                    }
                ],
            },
            widget_block,
            stacked_bar_chart_block,
            doughnut_chart_block,
            radar_chart_block,
            polar_area_chart_block,
            scatter_chart_block,
            bubble_chart_block,
            {
                "type": "heading",
                "level": 3,
                "text": "2.3 Higher-order blocks and rich media",
                "anchor": "advanced-blocks",
            },
            blockquote_block,
            callout_block,
            engine_quote_block,
            swot_block,
            pest_block,
            code_block,
            math_block,
            figure_block,
            {
                "type": "hr",
                "variant": "dashed",
            },
            {
                "type": "paragraph",
                "align": "justify",
                "inlines": [
                    {
                        "text": "The inline math thorough verification of this chapter:",
                    },
                    {"text": "p(t)=p_0 e^{\\lambda t}", "marks": [{"type": "math"}]},
                    {"text": ";The above covers all allowed blocks and tags."},
                ],
            },
        ],
    }

    return [chapter_1, chapter_2]


def validate_chapters(chapters: list[dict]) -> None:
    """Use IRValidator to verify the chapter structure and throw an exception when errors are found."""
    validator = IRValidator()
    for chapter in chapters:
        ok, errors = validator.validate_chapter(chapter)
        if not ok:
            raise ValueError(f"{chapter.get('chapterId', 'unknown')} Verification failed: {errors}")


def render_and_save(document_ir: dict, timestamp: str) -> tuple[Path, Path, Path]:
    """Save IR as JSON and render HTML/PDF, returning three paths."""
    ir_dir = Path(settings.DOCUMENT_IR_OUTPUT_DIR)
    html_dir = Path(settings.OUTPUT_DIR) / "html"
    pdf_dir = Path(settings.OUTPUT_DIR) / "pdf"
    ir_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    ir_path = ir_dir / f"report_ir_all_blocks_demo_{timestamp}.json"
    ir_path.write_text(json.dumps(document_ir, ensure_ascii=False, indent=2), encoding="utf-8")

    html_renderer = HTMLRenderer()
    html_content = html_renderer.render(document_ir)
    html_path = html_dir / f"report_html_all_blocks_demo_{timestamp}.html"
    html_path.write_text(html_content, encoding="utf-8")

    pdf_renderer = PDFRenderer()
    pdf_path = pdf_dir / f"report_pdf_all_blocks_demo_{timestamp}.pdf"
    pdf_renderer.render_to_pdf(document_ir, pdf_path)

    return ir_path, html_path, pdf_path


def main() -> int:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_id = f"all-blocks-demo-{timestamp}"
    metadata = {
        "title": "Social public hot event rendering test",
        "subtitle": "Sample data covering all IR block types, including various charts and PEST demos",
        "query": "Public event rendering capability self-test / Chart & PEST",
        "toc": {"title": "Table of contents", "depth": 3},
        "hero": {
            "summary": "Used to verify Report Engine's compatibility with various blocks, Chart.js components and PEST modules when rendering HTML/PDF.",
            "kpis": [
                {"label": "Number of sample blocks", "value": "20+", "delta": "Contains PEST", "tone": "up"},
                {"label": "number of charts", "value": "7", "delta": "Add multiple types", "tone": "neutral"},
            ],
            "highlights": ["Cover all blocks", "Contains inline/block level formulas", "Chart.js multiple types", "PEST + SWOT"],
            "actions": ["Regenerate", "Export PDF"],
        },
    }

    chapters = build_chapters()
    validate_chapters(chapters)

    composer = DocumentComposer()
    document_ir = composer.build_document(report_id, metadata, chapters)

    ir_path, html_path, pdf_path = render_and_save(document_ir, timestamp)

    print("✅ Demo IR generation completed")
    print(f"IR:   {ir_path}")
    print(f"HTML: {html_path}")
    print(f"PDF:  {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
