"""Report Engine configuration module uniformly reads environment variables and provides type-safe access."""

import os
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

from loguru import logger

class Settings(BaseSettings):
    """Report Engine configuration, environment variables and fields are all capitalized with REPORT_ENGINE_ prefix."""
    REPORT_ENGINE_API_KEY: Optional[str] = Field(None, description="Report Engine LLM API Key")
    REPORT_ENGINE_BASE_URL: Optional[str] = Field(None, description="Report Engine LLM base URL")
    REPORT_ENGINE_MODEL_NAME: Optional[str] = Field(None, description="Report Engine LLM model name")
    REPORT_ENGINE_PROVIDER: Optional[str] = Field(None, description="Model service provider, only compatible and reserved")
    # Other engine APIs (for cross-engine fixes)
    FORUM_HOST_API_KEY: Optional[str] = Field(
        None, description="LLM API key of Forum Engine / Forum Host (used for chapter repair)"
    )
    FORUM_HOST_BASE_URL: Optional[str] = Field(
        None, description="Forum Engine API Base URL (if empty, use LLM default configuration)"
    )
    FORUM_HOST_MODEL_NAME: Optional[str] = Field(
        None, description="Forum Engine LLM model name"
    )
    INSIGHT_ENGINE_API_KEY: Optional[str] = Field(
        None, description="Insight Engine LLM API key for cross-engine chapter fixes"
    )
    INSIGHT_ENGINE_BASE_URL: Optional[str] = Field(
        None, description="Insight Engine API Base URL"
    )
    INSIGHT_ENGINE_MODEL_NAME: Optional[str] = Field(
        None, description="Insight Engine LLM model name"
    )
    MEDIA_ENGINE_API_KEY: Optional[str] = Field(
        None, description="Media Engine LLM API key for cross-engine chapter fixes"
    )
    MEDIA_ENGINE_BASE_URL: Optional[str] = Field(
        None, description="Media Engine API Base URL"
    )
    MEDIA_ENGINE_MODEL_NAME: Optional[str] = Field(
        None, description="Media Engine LLM model name"
    )
    MAX_CONTENT_LENGTH: int = Field(200000, description="maximum content length")
    OUTPUT_DIR: str = Field("final_reports", description="Main output directory")
    # Chapter chunked JSON will be stored in this directory to facilitate source tracing and breakpoint resuming.
    CHAPTER_OUTPUT_DIR: str = Field(
        "final_reports/chapters", description="Chapter JSON cache directory"
    )
    # The entire bound IR/manifest will also be persisted to facilitate debugging and auditing.
    DOCUMENT_IR_OUTPUT_DIR: str = Field(
        "final_reports/ir", description="Entire IR/Manifest output directory"
    )
    CHAPTER_JSON_MAX_ATTEMPTS: int = Field(
        2, description="Maximum number of attempts when chapter JSON parsing fails"
    )
    TEMPLATE_DIR: str = Field("ReportEngine/report_template", description="Multiple template directories")
    API_TIMEOUT: float = Field(900.0, description="Single API timeout (seconds)")
    MAX_RETRY_DELAY: float = Field(180.0, description="Maximum retry interval (seconds)")
    MAX_RETRIES: int = Field(8, description="Maximum number of retries")
    LOG_FILE: str = Field("logs/report.log", description="Log output file")
    ENABLE_PDF_EXPORT: bool = Field(True, description="Whether to allow PDF export")
    CHART_STYLE: str = Field("modern", description="Chart style: modern/classic/")
    JSON_ERROR_LOG_DIR: str = Field(
        "logs/json_repair_failures", description="Unrepairable JSON block drop directory"
    )

    class Config:
        """Pydantic configuration: allow reading from .env and be case compatible"""
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False
        extra = "allow"

settings = Settings()


def print_config(config: Settings):
    """Output the current configuration items to the log in human-readable format to facilitate troubleshooting.

    Parameters:
        config: Settings instance, usually global settings."""
    message = ""
    message += "\n=== Report Engine Configuration ===\n"
    message += f"LLM model: {config.REPORT_ENGINE_MODEL_NAME}\n"
    message += f"LLM Base URL: {config.REPORT_ENGINE_BASE_URL or '(default)'}\n"
    message += f"Maximum content length: {config.MAX_CONTENT_LENGTH}\n"
    message += f"Output directory: {config.OUTPUT_DIR}\n"
    message += f"Chapter JSON directory: {config.CHAPTER_OUTPUT_DIR}\n"
    message += f"Maximum number of chapter JSON attempts: {config.CHAPTER_JSON_MAX_ATTEMPTS}\n"
    message += f"Entire IR directory: {config.DOCUMENT_IR_OUTPUT_DIR}\n"
    message += f"Template directory: {config.TEMPLATE_DIR}\n"
    message += f"API timeout: {config.API_TIMEOUT} seconds\n"
    message += f"Maximum retry interval: {config.MAX_RETRY_DELAY} seconds\n"
    message += f"Maximum number of retries: {config.MAX_RETRIES}\n"
    message += f"Log file: {config.LOG_FILE}\n"
    message += f"PDF export: {config.ENABLE_PDF_EXPORT}\n"
    message += f"Chart style: {config.CHART_STYLE}\n"
    message += f"LLM API Key: {'configured' if config.REPORT_ENGINE_API_KEY else 'not configured'}\n"
    message += "=========================\n"
    logger.info(message)
