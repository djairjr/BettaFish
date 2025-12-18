"""Multimodal search toolset designed for AI agents (Bocha)

Version: 1.1
Last updated: 2025-08-22

This script breaks down the complex Bocha AI Search functionality into a series of independent tools with clear goals and few parameters.
Designed specifically for AI Agent invocation. The agent only needs to perform tasks according to the purpose (such as general search, finding structured data or time-sensitive news).
Choose the right tool without having to understand complex parameter combinations.

Core features:
- Powerful multi-modal capabilities: can return web pages, pictures, AI summaries, follow-up suggestions, and rich "modal card" structured data at the same time.
- Modal card support: For specific queries such as weather, stocks, exchange rates, encyclopedias, and medical care, structured data cards can be directly returned to facilitate direct analysis and use by the Agent.

Main tools:
- comprehensive_search: Perform a comprehensive search, returning web pages, pictures, AI summaries and possible modal cards.
- search_for_structured_data: Specifically used to query structured information such as weather, stocks, exchange rates, etc. that can trigger "modal cards".
- web_search_only: Perform pure web search without requesting AI summary, which is faster.
- search_last_24_hours: Get the latest information in the past 24 hours.
- search_last_week: Get the main stories from the past week."""

import os
import json
import sys
import datetime
from typing import List, Dict, Any, Optional, Literal

from loguru import logger
from config import settings

# Please make sure the requests library is installed before running: pip install requests
try:
    import requests
except ImportError:
    raise ImportError("The requests library is not installed, please run `pip install requests` to install it.")

# Add utils directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
utils_dir = os.path.join(root_dir, 'utils')
if utils_dir not in sys.path:
    sys.path.append(utils_dir)

from retry_helper import with_graceful_retry, SEARCH_API_RETRY_CONFIG

# --- 1. Data structure definition ---
from dataclasses import dataclass, field

@dataclass
class WebpageResult:
    """Web search results"""
    name: str
    url: str
    snippet: str
    display_url: Optional[str] = None
    date_last_crawled: Optional[str] = None

@dataclass
class ImageResult:
    """Image search results"""
    name: str
    content_url: str
    host_page_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None

@dataclass
class ModalCardResult:
    """Modal card structured data results
    This is a core feature of Bocha search and is used to return specific types of structured information."""
    card_type: str  # For example: weather_china, stock, baike_pro, medical_common
    content: Dict[str, Any]  # Parsed JSON content

@dataclass
class BochaResponse:
    """Encapsulate the complete return results of the Bocha API so that they can be passed between tools"""
    query: str
    conversation_id: Optional[str] = None
    answer: Optional[str] = None  # AI generated summary answer
    follow_ups: List[str] = field(default_factory=list) # AI generated questioning
    webpages: List[WebpageResult] = field(default_factory=list)
    images: List[ImageResult] = field(default_factory=list)
    modal_cards: List[ModalCardResult] = field(default_factory=list)

@dataclass
class AnspireResponse:
    """Encapsulate the complete return results of the Anspire API so that they can be passed between tools"""
    query: str
    conversation_id: Optional[str] = None
    score: Optional[float] = None
    webpages: List[WebpageResult] = field(default_factory=list)


# --- 2. Core client and dedicated toolset ---

class BochaMultimodalSearch:
    """A client that includes a variety of specialized multimodal search tools.
    Each public method is designed as a tool to be called independently by the AI ​​Agent."""

    BOCHA_BASE_URL = settings.BOCHA_BASE_URL or "https://api.bocha.cn/v1/ai-search"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the client.
        Args:
            api_key: Bocha API key, if not provided, it will be read from the environment variable BOCHA_API_KEY."""
        if api_key is None:
            api_key = settings.BOCHA_WEB_SEARCH_API_KEY
            if not api_key:
                raise ValueError("Bocha API Key not found! Please set the BOCHA_API_KEY environment variable or provide it during initialization")

        self._headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': '*/*'
        }

    def _parse_search_response(self, response_dict: Dict[str, Any], query: str) -> BochaResponse:
        """Parse a structured BochaResponse object from the API's raw dictionary response"""

        final_response = BochaResponse(query=query)
        final_response.conversation_id = response_dict.get('conversation_id')

        messages = response_dict.get('messages', [])
        for msg in messages:
            role = msg.get('role')
            if role != 'assistant':
                continue

            msg_type = msg.get('type')
            content_type = msg.get('content_type')
            content_str = msg.get('content', '{}')

            try:
                content_data = json.loads(content_str)
            except json.JSONDecodeError:
                # If the content is not a legal JSON string (such as a plain text answer), use it directly
                content_data = content_str

            if msg_type == 'answer' and content_type == 'text':
                final_response.answer = content_data

            elif msg_type == 'follow_up' and content_type == 'text':
                final_response.follow_ups.append(content_data)

            elif msg_type == 'source':
                if content_type == 'webpage':
                    web_results = content_data.get('value', [])
                    for item in web_results:
                        final_response.webpages.append(WebpageResult(
                            name=item.get('name'),
                            url=item.get('url'),
                            snippet=item.get('snippet'),
                            display_url=item.get('displayUrl'),
                            date_last_crawled=item.get('dateLastCrawled')
                        ))
                elif content_type == 'image':
                    final_response.images.append(ImageResult(
                        name=content_data.get('name'),
                        content_url=content_data.get('contentUrl'),
                        host_page_url=content_data.get('hostPageUrl'),
                        thumbnail_url=content_data.get('thumbnailUrl'),
                        width=content_data.get('width'),
                        height=content_data.get('height')
                    ))
                # All other content_types are considered modal cards
                else:
                    final_response.modal_cards.append(ModalCardResult(
                        card_type=content_type,
                        content=content_data
                    ))

        return final_response


    @with_graceful_retry(SEARCH_API_RETRY_CONFIG, default_return=BochaResponse(query="Search failed"))
    def _search_internal(self, **kwargs) -> BochaResponse:
        """Internally common search executor, all tools ultimately call this method"""
        query = kwargs.get("query", "Unknown Query")
        payload = {
            "stream": False,  # Agent tools usually use non-streaming to get complete results
        }
        payload.update(kwargs)

        try:

            response = requests.post(self.BOCHA_BASE_URL, headers=self._headers, json=payload, timeout=30)
            response.raise_for_status()  # Throws an exception if the HTTP status code is 4xx or 5xx

            response_dict = response.json()
            if response_dict.get("code") != 200:
                logger.error(f"API return error: {response_dict.get('msg', 'Unknown error')}")
                return BochaResponse(query=query)

            return self._parse_search_response(response_dict, query)

        except requests.exceptions.RequestException as e:
            logger.exception(f"A network error occurred while searching: {str(e)}")
            raise e  # Let the retry mechanism capture and handle
        except Exception as e:
            logger.exception(f"An unknown error occurred while processing the response: {str(e)}")
            raise e  # Let the retry mechanism capture and handle

    # ---Available tools and methods for Agent ---

    def comprehensive_search(self, query: str, max_results: int = 10) -> BochaResponse:
        """[Tools] Comprehensive comprehensive search: Perform a standard comprehensive search that includes all information types.
        Return web pages, pictures, AI summaries, follow-up suggestions and possible modal cards. This is the most commonly used general search tool.
        Agent can provide search query (query) and optional maximum number of results (max_results)."""
        logger.info(f"--- TOOL: Comprehensive comprehensive search (query: {query}) ---")
        return self._search_internal(
            query=query,
            count=max_results,
            answer=True  # Turn on AI summary
        )

    def web_search_only(self, query: str, max_results: int = 15) -> BochaResponse:
        """[Tool] Pure web search: Only obtain web links and abstracts, and do not request AI to generate answers.
        It is suitable for scenarios where original web page information needs to be quickly obtained without additional analysis by AI. Faster and cheaper."""
        logger.info(f"--- TOOL: Pure web search (query: {query}) ---")
        return self._search_internal(
            query=query,
            count=max_results,
            answer=False # Close AI summary
        )

    def search_for_structured_data(self, query: str) -> BochaResponse:
        """[Tool] Structured data query: specifically used for queries that may trigger "modal cards".
        This tool should be used first when the agent intends to query structured information such as weather, stocks, exchange rates, encyclopedia definitions, train tickets, car parameters, etc.
        It returns all information, but the agent should focus on the `modal_cards` part of the results."""
        logger.info(f"--- TOOL: Structured data query (query: {query}) ---")
        # The implementation is the same as comprehensive_search, but the intent of the agent is guided through naming and documentation.
        return self._search_internal(
            query=query,
            count=5, # Structured queries usually don’t require many web results
            answer=True
        )

    def search_last_24_hours(self, query: str) -> BochaResponse:
        """[Tools] Search information within 24 hours: Get the latest updates on a certain topic.
        This tool specifically looks for content published in the past 24 hours. Suitable for tracking emergencies or latest developments."""
        logger.info(f"--- TOOL: Search for information within 24 hours (query: {query}) ---")
        return self._search_internal(query=query, freshness='oneDay', answer=True)

    def search_last_week(self, query: str) -> BochaResponse:
        """[Tool] Search this week's information: Get the main reports on a certain topic in the past week.
        Suitable for weekly public opinion summary or review."""
        logger.info(f"--- TOOL: Search this week's information (query: {query}) ---")
        return self._search_internal(query=query, freshness='oneWeek', answer=True)

class AnspireAISearch:
    """Anspire AI Search Client"""
    ANSPIRE_BASE_URL = settings.ANSPIRE_BASE_URL or "https://plugin.anspire.cn/api/ntsearch/search"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the client.
        Args:
            api_key: Anspire API key, if not provided, it will be read from the environment variable ANSPIRE_API_KEY."""
        if api_key is None:
            api_key = settings.ANSPIRE_API_KEY
            if not api_key:
                raise ValueError("Anspire API Key not found! Please set the ANSPIRE_API_KEY environment variable or provide it during initialization")

        self._headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Connection': 'keep-alive',
            'Accept': '*/*'
        }

    def _parse_search_response(self, response_dict: Dict[str, Any], query: str) -> AnspireResponse:
        final_response = AnspireResponse(query=query)
        final_response.conversation_id = response_dict.get('Uuid')

        messages = response_dict.get("results", [])
        for msg in messages:
            final_response.score = msg.get("score")
            final_response.webpages.append(WebpageResult(
                name = msg.get("title", ""),
                url = msg.get("url", ""),
                snippet = msg.get("content", ""),
                date_last_crawled = msg.get("date", None)
            ))

        return final_response
    
    @with_graceful_retry(SEARCH_API_RETRY_CONFIG, default_return=AnspireResponse(query="Search failed"))
    def _search_internal(self, **kwargs) -> AnspireResponse:
        """Internally common search executor, all tools ultimately call this method"""
        query = kwargs.get("query", "Unknown Query")
        payload = {
            "query": query,
            "top_k": kwargs.get("top_k", 10),
            "Insite": kwargs.get("Insite", ""),
            "FromTime": kwargs.get("FromTime", ""),
            "ToTime": kwargs.get("ToTime", "")
        }
        
        try:
            response = requests.get(self.ANSPIRE_BASE_URL, headers=self._headers, params=payload, timeout=30)
            response.raise_for_status()  # Throws an exception if the HTTP status code is 4xx or 5xx

            response_dict = response.json()
            return self._parse_search_response(response_dict, query)
        except requests.exceptions.RequestException as e:
            logger.exception(f"A network error occurred while searching: {str(e)}")
            raise e  # Let the retry mechanism capture and handle
        except Exception as e:
            logger.exception(f"An unknown error occurred while processing the response: {str(e)}")
            raise e  # Let the retry mechanism capture and handle
    
    def comprehensive_search(self, query: str, max_results: int = 10) -> AnspireResponse:
        """[Tools] Comprehensive search: Get comprehensive information on a topic, including web pages.
        Suitable for scenarios that require multiple sources of information."""
        logger.info(f"--- TOOL: Comprehensive search (query: {query}) ---")
        return self._search_internal(
            query=query,
            top_k=max_results
        )

    def search_last_24_hours(self, query: str, max_results: int = 10) -> AnspireResponse:
        """[Tools] Search information within 24 hours: Get the latest updates on a certain topic.
        This tool specifically looks for content published in the past 24 hours. Suitable for tracking emergencies or latest developments."""
        logger.info(f"--- TOOL: Search for information within 24 hours (query: {query}) ---")
        to_time = datetime.datetime.now()
        from_time = to_time - datetime.timedelta(days=1)
        return self._search_internal(query=query,
                                     top_k=max_results,
                                     FromTime=from_time.strftime("%Y-%m-%d %H:%M:%S"), 
                                     ToTime=to_time.strftime("%Y-%m-%d %H:%M:%S"))

    def search_last_week(self, query: str, max_results: int = 10) -> AnspireResponse:
        """[Tool] Search this week's information: Get the main reports on a certain topic in the past week.
        Suitable for weekly public opinion summary or review."""
        logger.info(f"--- TOOL: Search this week's information (query: {query}) ---")
        to_time = datetime.datetime.now()
        from_time = to_time - datetime.timedelta(weeks=1)
        return self._search_internal(query=query,
                                     top_k=max_results,
                                     FromTime=from_time.strftime("%Y-%m-%d %H:%M:%S"),
                                     ToTime=to_time.strftime("%Y-%m-%d %H:%M:%S"))


# --- 3. Testing and usage examples ---
def load_agent_from_config():
    """Select and load the search agent based on the configuration file"""
    if settings.BOCHA_WEB_SEARCH_API_KEY:
        logger.info("Load BochaMultimodalSearch Agent")
        return BochaMultimodalSearch()
    elif settings.ANSPIRE_API_KEY:
        logger.info("Load AnspireAISearch Agent")
        return AnspireAISearch()
    else:
        raise ValueError("No valid search agent is configured")

def print_response_summary(response):
    """Simplified printing function for displaying test results"""
    if not response or not response.query:
        logger.error("Failed to get valid response.")
        return

    logger.info(f"\nQuery: '{response.query}' | Session ID: {response.conversation_id}")
    if hasattr(response, 'answer') and response.answer:
        logger.info(f"AI summary: {response.answer[:150]}...")

    logger.info(f"{len(response.webpages)} web pages found")
    if hasattr(response, 'images'):
        logger.info(f"Found {len(response.images)} images")
    if hasattr(response, 'modal_cards'):
        logger.info(f"Found {len(response.modal_cards)} modal cards")

    if hasattr(response, 'modal_cards') and response.modal_cards:
        first_card = response.modal_cards[0]
        logger.info(f"First modal card type: {first_card.card_type}")

    if response.webpages:
        first_result = response.webpages[0]
        logger.info(f"The first web result: {first_result.name}")

    if hasattr(response, 'follow_ups') and response.follow_ups:
        logger.info(f"Suggested follow-up questions: {response.follow_ups}")

    logger.info("-" * 60)


if __name__ == "__main__":
    # Before running, make sure you have set the BOCHA_API_KEY environment variable

    try:
        # Initialize the multimodal search client, which contains all the tools internally
        search_client = load_agent_from_config()

        # Scenario 1: Agent conducts a regular comprehensive search that requires AI summary
        response1 = search_client.comprehensive_search(query="The impact of artificial intelligence on future education")
        print_response_summary(response1)

        # Scenario 2: Agent needs to query specific structured information - weather
        if isinstance(search_client, BochaMultimodalSearch):
            response2 = search_client.search_for_structured_data(query="What will the weather be like tomorrow in Shanghai?")
            print_response_summary(response2)
            # In-depth analysis of the first modal card
            if response2.modal_cards and response2.modal_cards[0].card_type == 'weather_china':
                logger.info("Weather modal card details:", json.dumps(response2.modal_cards[0].content, indent=2, ensure_ascii=False))


        # Scenario 3: Agent needs to query specific structured information - stocks
        if isinstance(search_client, BochaMultimodalSearch):
            response3 = search_client.search_for_structured_data(query="Oriental Fortune Stock")
            print_response_summary(response3)

        # Scenario 4: Agent needs to track the latest progress of an event
        response4 = search_client.search_last_24_hours(query="Latest news on C929 large aircraft")
        print_response_summary(response4)

        # Scenario 5: Agent only needs to quickly obtain web page information and does not need AI summary
        if isinstance(search_client, BochaMultimodalSearch):
            response5 = search_client.web_search_only(query="Python dataclasses usage")
            print_response_summary(response5)

        # Scenario 6: Agent needs to review news about a certain technology within a week
        response6 = search_client.search_last_week(query="Quantum computing commercialization")
        print_response_summary(response6)

        '''下面是测试程序的输出：
        --- TOOL: 全面综合搜索 (query: 人工智能对未来教育的影响) ---

查询: '人工智能对未来教育的影响' | 会话ID: bf43bfe4c7bb4f7b8a3945515d8ab69e
AI摘要: 人工智能对未来教育有着多方面的影响。

从积极影响来看：
- 在教学资源方面，人工智能有助于教育资源的均衡分配[引用:4]。例如通过人工智能云平台，可以实现优质资源的共享，这对于偏远地区来说意义重大，能让那里的学生也接触到优质的教育内 容，一定程度上缓解师资短缺的问题，因为AI驱动的智能教学助手或虚拟...
找到 10 个网页, 1 张图片, 1 个模态卡。
第一个模态卡类型: video
第一条网页结果: 人工智能如何影响教育变革
建议追问: [['人工智能将如何改变未来的教育模式？', '在未来教育中，人工智能会给教师带来哪些挑战？', '未来教育中，学生如何利用人工智能提升学习效果？']]
------------------------------------------------------------
--- TOOL: 结构化数据查询 (query: 上海明天天气怎么样) ---

查询: '上海明天天气怎么样' | 会话ID: e412aa1548cd43a295430e47a62adda2
AI摘要: 根据所给信息，无法确定上海明天的天气情况。

首先，所提供的信息都是关于2025年8月22日的天气状况，包括当天的气温、降水、风力、湿度以及高温预警等信息[引用:1][引用:2][引用:3][引用:5]。然而，这些信息没有涉及到明天（8月23 日）天气的预测内容。虽然提到了副热带高压一直到8月底高温都...
找到 5 个网页, 1 张图片, 2 个模态卡。
第一个模态卡类型: video
第一条网页结果: 今日冲击38!上海八月高温天数和夏季持续高温天数有望双双破纪录_天气_低压_气象站
建议追问: [['能告诉我上海明天的气温范围吗？', '上海明天会有降雨吗？', '上海明天的天气是晴天还是阴天呢？']]
------------------------------------------------------------
--- TOOL: 结构化数据查询 (query: 东方财富股票) ---

查询: '东方财富股票' | 会话ID: 584d62ed97834473b967127852e1eaa0
AI摘要: 仅根据提供的上下文，无法确切获取东方财富股票的相关信息。

从给出的这些数据来看，并没有直接表明与东方财富股票相关的特定数据。例如，没有东方财富股票的涨跌幅情况、成交量、市值等具体数据[引用:1][引用:3]。也没有涉及东方财富股票在研报 、评级方面的信息[引用:2]。同时，上下文里关于股票价格、成交...
找到 5 个网页, 1 张图片, 2 个模态卡。
第一个模态卡类型: video
第一条网页结果: 股票价格_分时成交_行情_走势图—东方财富网
建议追问: [['东方财富股票近期的走势如何？', '东方财富股票有哪些主要的投资亮点？', '东方财富股票的历史最高和最低股价是多少？']]
------------------------------------------------------------
--- TOOL: 搜索24小时内信息 (query: C929大飞机最新消息) ---

查询: 'C929大飞机最新消息' | 会话ID: 5904021dc29d497e938e04db18d7f2e2
AI摘要: 根据提供的上下文，没有关于C929大飞机的直接消息，无法确切给出C929大飞机的最新消息。

目前提供的上下文涵盖了众多航空领域相关事件，但多是围绕波音787、空客A380相关专家的人事变动、国产飞机“C909云端之旅”、科德数控的营收情况、俄制航空发动机供应相关以及其他非C929大飞机相关的内容。...
找到 10 个网页, 1 张图片, 1 个模态卡。
第一个模态卡类型: video
第一条网页结果: 放弃美国千万年薪,波音787顶尖专家回国,或可协助破解C929
建议追问: [['C929大飞机目前的研发进度如何？', '有没有关于C929大飞机预计首飞时间的消息？', 'C929大飞机在技术创新方面有哪些新进展？']]
------------------------------------------------------------
--- TOOL: 纯网页搜索 (query: Python dataclasses用法) ---

查询: 'Python dataclasses用法' | 会话ID: 74c742759d2e4b17b52d8b735ce24537
找到 15 个网页, 1 张图片, 1 个模态卡。
第一个模态卡类型: video
第一条网页结果: 不可不知的dataclasses  python小知识_python dataclasses-CSDN博客
------------------------------------------------------------
--- TOOL: 搜索本周信息 (query: 量子计算商业化) ---

AI摘要: 量子计算商业化正在逐步推进。

量子计算商业化有着多方面的体现和推动因素。从国际上看，美国能源部橡树岭国家实验室选择IQM Radiance作为其首台本地部署的量子计算机，计划于2025年第三季度交付并集成至高性能计算系统中[引用:4]；英国量子计算公司Oxford Ionics的全栈离子阱量子计算...
找到 10 个网页, 1 张图片, 1 个模态卡。
第一个模态卡类型: video
第一条网页结果: 量子计算商业潜力释放正酣,微美全息(WIMI.US)创新科技卡位“生态高地”
建议追问: [['量子计算商业化目前有哪些成功的案例？', '哪些公司在推动量子计算商业化进程？', '量子计算商业化面临的主要挑战是什么？']]
------------------------------------------------------------'''

    except ValueError as e:
        logger.exception(f"Initialization failed: {e}")
        logger.error("Please make sure the BOCHA_API_KEY environment variable is set correctly.")
    except Exception as e:
        logger.exception(f"An unknown error occurred during testing: {e}")