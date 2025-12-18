# -*- coding: utf-8 -*-
"""Weiyu configuration file

This module uses pydantic-settings to manage global configuration and supports automatic loading from environment variables and .env files.
Data model definition location:
- This document - Configuration model definition"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict
from typing import Optional, Literal
from loguru import logger


# Calculate .env priority: the current working directory first, followed by the project root directory
PROJECT_ROOT: Path = Path(__file__).resolve().parent
CWD_ENV: Path = Path.cwd() / ".env"
ENV_FILE: str = str(CWD_ENV if CWD_ENV.exists() else (PROJECT_ROOT / ".env"))


class Settings(BaseSettings):
    """Global configuration; supports automatic loading of .env and environment variables.
    The variable names are capitalized the same as the original config.py to facilitate smooth transition."""
    # ================== Flask server configuration ====================
    HOST: str = Field("0.0.0.0", description="BETTAFISH host address, such as 0.0.0.0 or 127.0.0.1")
    PORT: int = Field(5000, description="Flask server port number, default 5000")

    # ====================== Database configuration ======================
    DB_DIALECT: str = Field("postgresql", description="Database type, optional mysql or postgresql; please configure it together with other connection information")
    DB_HOST: str = Field("your_db_host", description="Database host, such as localhost or 127.0.0.1")
    DB_PORT: int = Field(3306, description="Database port number, default is 3306")
    DB_USER: str = Field("your_db_user", description="Database username")
    DB_PASSWORD: str = Field("your_db_password", description="Database password")
    DB_NAME: str = Field("your_db_name", description="Database name")
    DB_CHARSET: str = Field("utf8mb4", description="Database character set, utf8mb4 recommended, compatible with emoji")
    
    # ======================= LLM related =======================
    # Our LLM model API sponsors are: https://aihubmix.com/?aff=8Ds9, which provides a very comprehensive model API
    
    # Insight Agent (Kimi recommended, application address: https://platform.moonshot.cn/)
    INSIGHT_ENGINE_API_KEY: Optional[str] = Field(None, description="Insight Agent (recommended kimi-k2, official application address: https://platform.moonshot.cn/) API key, used for the main LLM. 🚩Please apply and run according to the recommended configuration first, and then adjust KEY, BASE_URL and MODEL_NAME as needed.")
    INSIGHT_ENGINE_BASE_URL: Optional[str] = Field("https://api.moonshot.cn/v1", description="Insight Agent LLM BaseUrl, can be customized according to the manufacturer")
    INSIGHT_ENGINE_MODEL_NAME: str = Field("kimi-k2-0711-preview", description="Insight Agent LLM model name, for example kimi-k2-0711-preview")
    
    # Media Agent (Gemini recommended, recommended transfer vendor: https://aihubmix.com/?aff=8Ds9)
    MEDIA_ENGINE_API_KEY: Optional[str] = Field(None, description="Media Agent (recommended gemini-2.5-pro, transfer vendor application address: https://aihubmix.com/?aff=8Ds9) API key")
    MEDIA_ENGINE_BASE_URL: Optional[str] = Field("https://aihubmix.com/v1", description="Media Agent LLM BaseUrl, adjustable according to the transfer service")
    MEDIA_ENGINE_MODEL_NAME: str = Field("gemini-2.5-pro", description="Media Agent LLM model name, such as gemini-2.5-pro")
    
    # Query Agent (DeepSeek is recommended, application address: https://www.deepseek.com/)
    QUERY_ENGINE_API_KEY: Optional[str] = Field(None, description="Query Agent (recommended deepseek, official application address: https://platform.deepseek.com/) API key")
    QUERY_ENGINE_BASE_URL: Optional[str] = Field("https://api.deepseek.com", description="Query Agent LLM BaseUrl")
    QUERY_ENGINE_MODEL_NAME: str = Field("deepseek-chat", description="Query Agent LLM model name, such as deepseek-reasoner")
    
    # Report Agent (Recommended Gemini, recommended transfer vendor: https://aihubmix.com/?aff=8Ds9)
    REPORT_ENGINE_API_KEY: Optional[str] = Field(None, description="Report Agent (recommended gemini-2.5-pro, transfer vendor application address: https://aihubmix.com/?aff=8Ds9) API key")
    REPORT_ENGINE_BASE_URL: Optional[str] = Field("https://aihubmix.com/v1", description="Report Agent LLM BaseUrl, which can be adjusted according to the transfer service")
    REPORT_ENGINE_MODEL_NAME: str = Field("gemini-2.5-pro", description="Report Agent LLM model name, such as gemini-2.5-pro")

    # MindSpider Agent (Deepseek recommended, official application address: https://platform.deepseek.com/)
    MINDSPIDER_API_KEY: Optional[str] = Field(None, description="MindSpider Agent (recommended deepseek, official application address: https://platform.deepseek.com/) API key")
    MINDSPIDER_BASE_URL: Optional[str] = Field(None, description="MindSpider Agent BaseUrl, configurable per selected service")
    MINDSPIDER_MODEL_NAME: Optional[str] = Field(None, description="MindSpider Agent model name, such as deepseek-reasoner")
    
    # Forum Host (the latest model of Qwen3, here I use the Silicon Flow platform, application address: https://cloud.siliconflow.cn/)
    FORUM_HOST_API_KEY: Optional[str] = Field(None, description="Forum Host (qwen-plus recommended, official application address: https://www.aliyun.com/product/bailian) API key")
    FORUM_HOST_BASE_URL: Optional[str] = Field(None, description="Forum Host LLM BaseUrl, configurable per selected service")
    FORUM_HOST_MODEL_NAME: Optional[str] = Field(None, description="Forum Host LLM model name, for example qwen-plus")
    
    # SQL keyword Optimizer (small parameter Qwen3 model, here I use the Silicon Flow platform, application address: https://cloud.siliconflow.cn/)
    KEYWORD_OPTIMIZER_API_KEY: Optional[str] = Field(None, description="SQL Keyword Optimizer (qwen-plus recommended, official application address: https://www.aliyun.com/product/bailian) API key")
    KEYWORD_OPTIMIZER_BASE_URL: Optional[str] = Field(None, description="Keyword Optimizer BaseUrl, configurable per selected service")
    KEYWORD_OPTIMIZER_MODEL_NAME: Optional[str] = Field(None, description="Keyword Optimizer LLM model name, such as qwen-plus")
    
    # ================== Network tool configuration ====================
    # Tavily API (application address: https://www.tavily.com/)
    TAVILY_API_KEY: Optional[str] = Field(None, description="Tavily API (application address: https://www.tavily.com/) API key, used for Tavily web search")

    SEARCH_TOOL_TYPE: Literal["AnspireAPI", "BochaAPI"] = Field("AnspireAPI", description="Network search tool type, supports BochaAPI or AnspireAPI, the default is AnspireAPI")
    # Bocha API (application address: https://open.bochaai.com/)
    BOCHA_BASE_URL: Optional[str] = Field("https://api.bocha.cn/v1/ai-search", description="Bocha AI search BaseUrl or Bocha web page search BaseUrl")
    BOCHA_WEB_SEARCH_API_KEY: Optional[str] = Field(None, description="Bocha API (application address: https://open.bochaai.com/) API key for Bocha search")

    # Anspire AI Search API (application address: https://open.anspire.cn/)
    ANSPIRE_BASE_URL: Optional[str] = Field("https://plugin.anspire.cn/api/ntsearch/search", description="Anspire AI Search BaseUrl")
    ANSPIRE_API_KEY: Optional[str] = Field(None, description="Anspire AI Search API (application address: https://open.anspire.cn/) API key, used for Anspire search")

    
    # ================== Insight Engine Search Configuration ====================
    DEFAULT_SEARCH_HOT_CONTENT_LIMIT: int = Field(100, description="Default maximum number of hot list contents")
    DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE: int = Field(50, description="Maximum number of global topics by table")
    DEFAULT_SEARCH_TOPIC_BY_DATE_LIMIT_PER_TABLE: int = Field(100, description="Maximum number of topics by date")
    DEFAULT_GET_COMMENTS_FOR_TOPIC_LIMIT: int = Field(500, description="Maximum number of comments on a single topic")
    DEFAULT_SEARCH_TOPIC_ON_PLATFORM_LIMIT: int = Field(200, description="Maximum number of platform search topics")
    MAX_SEARCH_RESULTS_FOR_LLM: int = Field(0, description="Maximum number of search results for LLM")
    MAX_HIGH_CONFIDENCE_SENTIMENT_RESULTS: int = Field(0, description="High Confidence Sentiment Analysis Maximum Number")
    MAX_REFLECTIONS: int = Field(3, description="Maximum number of reflections")
    MAX_PARAGRAPHS: int = Field(6, description="Maximum number of paragraphs")
    SEARCH_TIMEOUT: int = Field(240, description="Single search request timeout")
    MAX_CONTENT_LENGTH: int = Field(500000, description="Search maximum content length")
    
    model_config = ConfigDict(
        env_file=ENV_FILE,
        env_prefix="",
        case_sensitive=False,
        extra="allow"
    )


# Create a global configuration instance
settings = Settings()


def reload_settings() -> Settings:
    """Reload configuration
    
    Reload configuration from .env files and environment variables, updating the global settings instance.
    Used to dynamically update configuration at runtime.
    
    Returns:
        Settings: newly created configuration instance"""
    
    global settings
    settings = Settings()
    return settings
