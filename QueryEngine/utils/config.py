"""Query Engine configuration management module

This module uses pydantic-settings to manage Query Engine configuration and supports automatic loading from environment variables and .env files.
Data model definition location:
- This document - Configuration model definition"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from loguru import logger


# Calculate .env priority: the current working directory first, followed by the project root directory
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
CWD_ENV: Path = Path.cwd() / ".env"
ENV_FILE: str = str(CWD_ENV if CWD_ENV.exists() else (PROJECT_ROOT / ".env"))


class Settings(BaseSettings):
    """Query Engine global configuration; supports automatic loading of .env and environment variables.
    The variable names are capitalized the same as the original config.py to facilitate smooth transition."""
    
    # ======================= LLM related =======================
    QUERY_ENGINE_API_KEY: str = Field(..., description="Query Engine LLM API key, used for the main LLM. You can change the API used by each part of LLM. As long as it is compatible with the OpenAI request format, it can be used normally after defining KEY, BASE_URL and MODEL_NAME.")
    QUERY_ENGINE_BASE_URL: Optional[str] = Field(None, description="Query Engine LLM interface BaseUrl, customizable manufacturer API")
    QUERY_ENGINE_MODEL_NAME: str = Field(..., description="Query Engine LLM model name")
    QUERY_ENGINE_PROVIDER: Optional[str] = Field(None, description="Query Engine LLM provider (compatible fields)")
    
    # ================== Network tool configuration ====================
    TAVILY_API_KEY: str = Field(..., description="Tavily API (application address: https://www.tavily.com/) API key, used for Tavily web search")
    
    # ================== Search parameter configuration ====================
    SEARCH_TIMEOUT: int = Field(240, description="Search timeout (seconds)")
    SEARCH_CONTENT_MAX_LENGTH: int = Field(20000, description="Maximum content length to use for prompts")
    MAX_REFLECTIONS: int = Field(2, description="Maximum number of reflection rounds")
    MAX_PARAGRAPHS: int = Field(5, description="Maximum number of paragraphs")
    MAX_SEARCH_RESULTS: int = Field(20, description="Maximum number of search results")
    
    # ================== Output configuration ====================
    OUTPUT_DIR: str = Field("reports", description="output directory")
    SAVE_INTERMEDIATE_STATES: bool = Field(True, description="Whether to save the intermediate state")
    
    class Config:
        env_file = ENV_FILE
        env_prefix = ""
        case_sensitive = False
        extra = "allow"


# Create a global configuration instance
settings = Settings()

def print_config(config: Settings):
    """打印配置信息
    
    Args:
        config: Settings配置对象"""
    message = ""
    message += "=== Query Engine Configuration ===\n"
    message += f"LLM model: {config.QUERY_ENGINE_MODEL_NAME}\n"
    message += f"LLM Base URL: {config.QUERY_ENGINE_BASE_URL or '(default)'}\n"
    message += f"Tavily API Key: {'configured' if config.TAVILY_API_KEY else 'not configured'}\n"
    message += f"Search timeout: {config.SEARCH_TIMEOUT} seconds\n"
    message += f"Maximum content length: {config.SEARCH_CONTENT_MAX_LENGTH}\n"
    message += f"Maximum number of reflections: {config.MAX_REFLECTIONS}\n"
    message += f"Maximum number of paragraphs: {config.MAX_PARAGRAPHS}\n"
    message += f"Maximum number of search results: {config.MAX_SEARCH_RESULTS}\n"
    message += f"Output directory: {config.OUTPUT_DIR}\n"
    message += f"Save intermediate states: {config.SAVE_INTERMEDIATE_STATES}\n"
    message += f"LLM API Key: {'configured' if config.QUERY_ENGINE_API_KEY else 'not configured'}\n"
    message += "========================\n"
    logger.info(message)
