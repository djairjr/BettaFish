"""Report Engine.

An AI agent implementation for intelligent report generation, aggregating the three sub-engines of Query/Media/Insight
Markdown was discussed with the forum, and finally the structured HTML report was implemented."""

from .agent import ReportAgent, create_agent

__version__ = "1.0.0"
__author__ = "Report Engine Team"

__all__ = ["ReportAgent", "create_agent"]
