"""
Configuration management module for the Media Engine (pydantic_settings style).
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, Literal


# Calculate .env priority: the current working directory first, followed by the project root directory
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
CWD_ENV: Path = Path.cwd() / ".env"
ENV_FILE: str = str(CWD_ENV if CWD_ENV.exists() else (PROJECT_ROOT / ".env"))

class Settings(BaseSettings):
    """Global configuration; supports automatic loading of .env and environment variables.
    The variable names are capitalized the same as the original config.py to facilitate smooth transition."""
    # ====================== Database configuration ======================
    DB_HOST: str = Field("your_db_host", description="Database host, such as localhost or 127.0.0.1. We also provide convenient configuration of cloud database resources, with an average of 100,000+ data per day. You can apply for free. Contact us: 670939375@qq.com NOTE: In order to conduct data compliance review and service upgrade, the cloud database will suspend accepting new usage applications from October 1, 2025.")
    DB_PORT: int = Field(3306, description="Database port number, default is 3306")
    DB_USER: str = Field("your_db_user", description="Database username")
    DB_PASSWORD: str = Field("your_db_password", description="Database password")
    DB_NAME: str = Field("your_db_name", description="Database name")
    DB_CHARSET: str = Field("utf8mb4", description="Database character set, utf8mb4 recommended, compatible with emoji")
    DB_DIALECT: str = Field("mysql", description="Database type, such as 'mysql' or 'postgresql'. Used to support multiple database backends (such as SQLAlchemy, please configure it together with the connection information)")

    # ======================= LLM related =======================
    INSIGHT_ENGINE_API_KEY: str = Field(None, description="Insight Agent (Kimi recommended, https://platform.moonshot.cn/) API key, used for the main LLM. You can change the API used by each part of LLM. As long as it is compatible with the OpenAI request format, it can be used normally after defining KEY, BASE_URL and MODEL_NAME. Important reminder: We strongly recommend that you use the recommended configuration to apply for the API and run through it before making your changes!")
    INSIGHT_ENGINE_BASE_URL: Optional[str] = Field("https://api.moonshot.cn/v1", description="Insight Agent LLM interface BaseUrl, customizable manufacturer API")
    INSIGHT_ENGINE_MODEL_NAME: str = Field("kimi-k2-0711-preview", description="Insight Agent LLM model name, such as kimi-k2-0711-preview")
    
    MEDIA_ENGINE_API_KEY: str = Field(None, description="Media Agent (Gemini is recommended, I used a transit vendor here, you can also replace it with your own, application address: https://www.chataiapi.com/) API key")
    MEDIA_ENGINE_BASE_URL: Optional[str] = Field("https://www.chataiapi.com/v1", description="Media Agent LLM interface BaseUrl")
    MEDIA_ENGINE_MODEL_NAME: str = Field("gemini-2.5-pro", description="Media Agent LLM model name, such as gemini-2.5-pro")
    
    BOCHA_WEB_SEARCH_API_KEY: Optional[str] = Field(None, description="Bocha Web Search API Key")
    BOCHA_API_KEY: Optional[str] = Field(None, description="Bocha compatible keys (aliases)")
    
    SEARCH_TIMEOUT: int = Field(240, description="Search timeout (seconds)")
    SEARCH_CONTENT_MAX_LENGTH: int = Field(20000, description="Maximum content length to use for prompts")
    MAX_REFLECTIONS: int = Field(2, description="Maximum number of reflection rounds")
    MAX_PARAGRAPHS: int = Field(5, description="Maximum number of paragraphs")
    
    MINDSPIDER_API_KEY: Optional[str] = Field(None, description="MindSpider API key")
    MINDSPIDER_BASE_URL: Optional[str] = Field("https://api.deepseek.com", description="MindSpider LLM interface BaseUrl")
    MINDSPIDER_MODEL_NAME: str = Field("deepseek-reasoner", description="MindSpider LLM model name, such as deepseek-reasoner")
    
    OUTPUT_DIR: str = Field("reports", description="output directory")
    SAVE_INTERMEDIATE_STATES: bool = Field(True, description="Whether to save the intermediate state")

    
    QUERY_ENGINE_API_KEY: str = Field(None, description="Query Agent (DeepSeek recommended, https://www.deepseek.com/) API key")
    QUERY_ENGINE_BASE_URL: Optional[str] = Field("https://api.deepseek.com", description="Query Agent LLM interface BaseUrl")
    QUERY_ENGINE_MODEL_NAME: str = Field("deepseek-reasoner", description="Query Agent LLM model, such as deepseek-reasoner")
    
    REPORT_ENGINE_API_KEY: str = Field(None, description="Report Agent (Gemini is recommended, I used a transit vendor here, you can also replace it with your own, application address: https://www.chataiapi.com/) API key")
    REPORT_ENGINE_BASE_URL: Optional[str] = Field("https://www.chataiapi.com/v1", description="Report Agent LLM interface BaseUrl")
    REPORT_ENGINE_MODEL_NAME: str = Field("gemini-2.5-pro", description="Report Agent LLM model, such as gemini-2.5-pro")
    
    FORUM_HOST_API_KEY: str = Field(None, description="Forum Host (Qwen3 latest model, here I use the Silicon Flow platform, application address: https://cloud.siliconflow.cn/) API key")
    FORUM_HOST_BASE_URL: Optional[str] = Field("https://api.siliconflow.cn/v1", description="Forum Host LLM BaseUrl")
    FORUM_HOST_MODEL_NAME: str = Field("Qwen/Qwen3-235B-A22B-Instruct-2507", description="Forum Host LLM model name, such as Qwen/Qwen3-235B-A22B-Instruct-2507")
    
    KEYWORD_OPTIMIZER_API_KEY: str = Field(None, description="SQL keyword Optimizer (small parameter Qwen3 model, here I use the Silicon Flow platform, application address: https://cloud.siliconflow.cn/) API key")
    KEYWORD_OPTIMIZER_BASE_URL: Optional[str] = Field("https://api.siliconflow.cn/v1", description="Keyword Optimizer BaseUrl")
    KEYWORD_OPTIMIZER_MODEL_NAME: str = Field("Qwen/Qwen3-30B-A3B-Instruct-2507", description="Keyword Optimizer LLM model name, such as Qwen/Qwen3-30B-A3B-Instruct-2507")

    # ================== Network tool configuration ====================
    TAVILY_API_KEY: str = Field(None, description="Tavily API (application address: https://www.tavily.com/) API key, used for Tavily web search")
    
    SEARCH_TOOL_TYPE: Literal["AnspireAPI", "BochaAPI"] = Field("AnspireAPI", description="Network search tool type, supports BochaAPI or AnspireAPI, the default is AnspireAPI")
    BOCHA_BASE_URL: Optional[str] = Field("https://api.bochaai.com/v1/ai-search", description="Bocha AI search BaseUrl or Bocha web page search BaseUrl")
    BOCHA_WEB_SEARCH_API_KEY: Optional[str] = Field(None, description="Bocha API (application address: https://open.bochaai.com/) API key for Bocha search")
    # Anspire AI Search API (application address: https://open.anspire.cn/)
    ANSPIRE_BASE_URL: Optional[str] = Field("https://plugin.anspire.cn/api/ntsearch/search", description="Anspire AI Search BaseUrl")
    ANSPIRE_API_KEY: Optional[str] = Field(None, description="Anspire AI Search API (application address: https://open.anspire.cn/) API key, used for Anspire search")

    class Config:
        env_file = ENV_FILE
        env_prefix = ""
        case_sensitive = False
        extra = "allow"


settings = Settings()
