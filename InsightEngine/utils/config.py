"""
Configuration management module for the Insight Engine.
Handles environment variables and config file parameters.
"""

import os
from dataclasses import dataclass
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field
from loguru import logger

class Settings(BaseSettings):
    INSIGHT_ENGINE_API_KEY: Optional[str] = Field(None, description="Insight Engine LLM API Key")
    INSIGHT_ENGINE_BASE_URL: Optional[str] = Field(None, description="Insight Engine LLM base url, optional")
    INSIGHT_ENGINE_MODEL_NAME: Optional[str] = Field(None, description="Insight Engine LLM model name")
    INSIGHT_ENGINE_PROVIDER: Optional[str] = Field(None, description="Insight Engine model provider, no longer recommended")
    DB_HOST: Optional[str] = Field(None, description="Database host")
    DB_USER: Optional[str] = Field(None, description="Database username")
    DB_PASSWORD: Optional[str] = Field(None, description="Database password")
    DB_NAME: Optional[str] = Field(None, description="Database name")
    DB_PORT: int = Field(3306, description="Database port")
    DB_CHARSET: str = Field("utf8mb4", description="Database character set")
    DB_DIALECT: Optional[str] = Field("mysql", description="Database dialect, such as mysql, postgresql, etc., SQLAlchemy backend selection")
    MAX_REFLECTIONS: int = Field(3, description="Maximum number of reflections")
    MAX_PARAGRAPHS: int = Field(6, description="Maximum number of paragraphs")
    SEARCH_TIMEOUT: int = Field(240, description="Single search request timeout")
    MAX_CONTENT_LENGTH: int = Field(500000, description="Search maximum content length")
    DEFAULT_SEARCH_HOT_CONTENT_LIMIT: int = Field(100, description="Default maximum number of hot list contents")
    DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE: int = Field(50, description="Maximum number of global topics by table")
    DEFAULT_SEARCH_TOPIC_BY_DATE_LIMIT_PER_TABLE: int = Field(100, description="Maximum number of topics by date")
    DEFAULT_GET_COMMENTS_FOR_TOPIC_LIMIT: int = Field(500, description="Maximum number of comments on a single topic")
    DEFAULT_SEARCH_TOPIC_ON_PLATFORM_LIMIT: int = Field(200, description="Maximum number of platform search topics")
    MAX_SEARCH_RESULTS_FOR_LLM: int = Field(0, description="Maximum number of search results for LLM")
    MAX_HIGH_CONFIDENCE_SENTIMENT_RESULTS: int = Field(0, description="High Confidence Sentiment Analysis Maximum Number")
    OUTPUT_DIR: str = Field("reports", description="Output path")
    SAVE_INTERMEDIATE_STATES: bool = Field(True, description="Whether to save the intermediate state")

    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False
        extra = "allow"

settings = Settings()