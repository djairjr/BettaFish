"""Deep Search Agent main class
Integrate all modules to achieve a complete in-depth search process"""

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans

from .llms import LLMClient
from .nodes import (
    FirstSearchNode,
    FirstSummaryNode,
    ReflectionNode,
    ReflectionSummaryNode,
    ReportFormattingNode,
    ReportStructureNode,
)
from .state import State
from .tools import (
    DBResponse,
    MediaCrawlerDB,
    keyword_optimizer,
    multilingual_sentiment_analyzer,
)
from .utils import format_search_results_for_prompt
from .utils.config import Settings, settings

ENABLE_CLUSTERING: bool = True  # Whether to enable cluster sampling
MAX_CLUSTERED_RESULTS: int = 50  # Maximum number of results returned after clustering
RESULTS_PER_CLUSTER: int = 5  # The number of results returned for each cluster


class DeepSearchAgent:
    """Deep Search Agent main class"""

    def __init__(self, config: Optional[Settings] = None):
        """Initialize Deep Search Agent

        Args:
            config: Optional configuration object (if left blank, use global settings)"""
        self.config = config or settings

        # Initialize LLM client
        self.llm_client = self._initialize_llm()

        # Initialize the search toolset
        self.search_agency = MediaCrawlerDB()

        # Initialize small clustering model (lazy loading)
        self._clustering_model = None

        # Initialize sentiment analyzer
        self.sentiment_analyzer = multilingual_sentiment_analyzer

        # Initialize node
        self._initialize_nodes()

        # state
        self.state = State()

        # Make sure the output directory exists
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)

        logger.info(f"Insight Agent has been initialized")
        logger.info(f"Using LLM: {self.llm_client.get_model_info()}")
        logger.info(f"Search toolset: MediaCrawlerDB (supports 5 local database query tools)")
        logger.info(f"Sentiment Analysis: WeiboMultilingualSentiment (supports sentiment analysis in 22 languages)")

    def _initialize_llm(self) -> LLMClient:
        """Initialize LLM client"""
        return LLMClient(
            api_key=self.config.INSIGHT_ENGINE_API_KEY,
            model_name=self.config.INSIGHT_ENGINE_MODEL_NAME,
            base_url=self.config.INSIGHT_ENGINE_BASE_URL,
        )

    def _initialize_nodes(self):
        """Initialize processing node"""
        self.first_search_node = FirstSearchNode(self.llm_client)
        self.reflection_node = ReflectionNode(self.llm_client)
        self.first_summary_node = FirstSummaryNode(self.llm_client)
        self.reflection_summary_node = ReflectionSummaryNode(self.llm_client)
        self.report_formatting_node = ReportFormattingNode(self.llm_client)

    def _get_clustering_model(self):
        """Lazy loading of clustering models"""
        if self._clustering_model is None:
            logger.info("Loading the clustering model (paraphrase-multilingual-MiniLM-L12-v2)...")
            self._clustering_model = SentenceTransformer(
                "paraphrase-multilingual-MiniLM-L12-v2"
            )
        return self._clustering_model

    def _validate_date_format(self, date_str: str) -> bool:
        """Verify that the date format is YYYY-MM-DD

        Args:
            date_str: date string

        Returns:
            Is it a valid format?"""
        if not date_str:
            return False

        # Check format
        pattern = r"^\d{4}-\d{2}-\d{2}$"
        if not re.match(pattern, date_str):
            return False

        # Check if the date is valid
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _cluster_and_sample_results(
        self,
        results: List,
        max_results: int = MAX_CLUSTERED_RESULTS,
        results_per_cluster: int = RESULTS_PER_CLUSTER,
    ) -> List:
        """Cluster and sample search results

        Args:
            results: search results list
            max_results: Maximum number of results returned
            results_per_cluster: Number of results returned per cluster

        Returns:
            Result list after sampling"""
        if len(results) <= max_results:
            return results

        try:
            # Extract text
            texts = [r.title_or_content[:500] for r in results]

            # Get the model and code
            model = self._get_clustering_model()
            embeddings = model.encode(texts, show_progress_bar=False)

            # Calculate the number of clusters
            n_clusters = min(max(2, max_results // results_per_cluster), len(results))

            # KMeans clustering
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = kmeans.fit_predict(embeddings)

            # Sample from each cluster
            sampled_results = []
            for cluster_id in range(n_clusters):
                cluster_indices = np.flatnonzero(labels == cluster_id)
                cluster_results = [(results[i], i) for i in cluster_indices]
                cluster_results.sort(
                    key=lambda x: x[0].hotness_score or 0, reverse=True
                )

                for result, _ in cluster_results[:results_per_cluster]:
                    sampled_results.append(result)
                    if len(sampled_results) >= max_results:
                        break

                if len(sampled_results) >= max_results:
                    break

            logger.info(
                f"Clustering completed: {len(results)} items -> {n_clusters} topics -> {len(sampled_results)} representative results"
            )
            return sampled_results

        except Exception as e:
            logger.warning(f"Clustering failed, return the first {max_results} items: {str(e)}")
            return results[:max_results]

    def execute_search_tool(self, tool_name: str, query: str, **kwargs) -> DBResponse:
        """Execute the specified database query tool (integrated keyword optimization middleware and sentiment analysis)

        Args:
            tool_name: tool name, optional value:
                -"search_hot_content": Find hot content
                -"search_topic_globally": Global topic search
                -"search_topic_by_date": Search topics by date
                -"get_comments_for_topic": Get topic comments
                -"search_topic_on_platform": Platform targeted search
                -"analyze_sentiment": Perform sentiment analysis on query results
            query: search keywords/topics
            **kwargs: additional parameters (such as start_date, end_date, platform, limit, enable_sentiment, etc.)
                     enable_sentiment: Whether to automatically perform sentiment analysis on search results (default True)

        Returns:
            DBResponse object (may contain sentiment analysis results)"""
        logger.info(f"→ Execute database query tool: {tool_name}")

        # For hot content searches, keyword optimization is not required (because no query parameters are required)
        if tool_name == "search_hot_content":
            time_period = kwargs.get("time_period", "week")
            limit = kwargs.get("limit", 100)
            response = self.search_agency.search_hot_content(
                time_period=time_period, limit=limit
            )

            # Check if sentiment analysis is required
            enable_sentiment = kwargs.get("enable_sentiment", True)
            if enable_sentiment and response.results and len(response.results) > 0:
                logger.info(f"🎭 Start sentiment analysis on hot content...")
                sentiment_analysis = self._perform_sentiment_analysis(response.results)
                if sentiment_analysis:
                    # Add sentiment analysis results to the parameters of the response
                    response.parameters["sentiment_analysis"] = sentiment_analysis
                    logger.info(f"✅ Sentiment analysis completed")

            return response

        # Standalone Sentiment Analysis Tool
        if tool_name == "analyze_sentiment":
            texts = kwargs.get("texts", query)  # Can be passed through the texts parameter, or using query
            sentiment_result = self.analyze_sentiment_only(texts)

            # Constructing a response in DBResponse format
            return DBResponse(
                tool_name="analyze_sentiment",
                parameters={
                    "texts": texts if isinstance(texts, list) else [texts],
                    **kwargs,
                },
                results=[],  # Sentiment analysis does not return search results
                results_count=0,
                metadata=sentiment_result,
            )

        # For tools that require search terms, use keyword optimization middleware
        optimized_response = keyword_optimizer.optimize_keywords(
            original_query=query, context=f"Use {tool_name} tool to query"
        )

        logger.info(f"🔍 Original query: '{query}'")
        logger.info(f"✨ Optimized keywords: {optimized_response.optimized_keywords}")

        # Use optimized keywords to conduct multiple queries and consolidate the results
        all_results = []
        total_count = 0

        for keyword in optimized_response.optimized_keywords:
            logger.info(f"Search keyword: '{keyword}'")

            try:
                if tool_name == "search_topic_globally":
                    # Use the default value in the configuration file and ignore the limit_per_table parameter provided by the agent
                    limit_per_table = (
                        self.config.DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE
                    )
                    response = self.search_agency.search_topic_globally(
                        topic=keyword, limit_per_table=limit_per_table
                    )
                elif tool_name == "search_topic_by_date":
                    start_date = kwargs.get("start_date")
                    end_date = kwargs.get("end_date")
                    # Use the default value in the configuration file and ignore the limit_per_table parameter provided by the agent
                    limit_per_table = (
                        self.config.DEFAULT_SEARCH_TOPIC_BY_DATE_LIMIT_PER_TABLE
                    )
                    if not start_date or not end_date:
                        raise ValueError(
                            "The search_topic_by_date tool requires start_date and end_date parameters"
                        )
                    response = self.search_agency.search_topic_by_date(
                        topic=keyword,
                        start_date=start_date,
                        end_date=end_date,
                        limit_per_table=limit_per_table,
                    )
                elif tool_name == "get_comments_for_topic":
                    # Use the default value in the configuration file, distribute according to the number of keywords, but ensure the minimum value
                    limit = self.config.DEFAULT_GET_COMMENTS_FOR_TOPIC_LIMIT // len(
                        optimized_response.optimized_keywords
                    )
                    limit = max(limit, 50)
                    response = self.search_agency.get_comments_for_topic(
                        topic=keyword, limit=limit
                    )
                elif tool_name == "search_topic_on_platform":
                    platform = kwargs.get("platform")
                    start_date = kwargs.get("start_date")
                    end_date = kwargs.get("end_date")
                    # Use the default value in the configuration file, distribute according to the number of keywords, but ensure the minimum value
                    limit = self.config.DEFAULT_SEARCH_TOPIC_ON_PLATFORM_LIMIT // len(
                        optimized_response.optimized_keywords
                    )
                    limit = max(limit, 30)
                    if not platform:
                        raise ValueError("The search_topic_on_platform tool requires the platform parameter")
                    response = self.search_agency.search_topic_on_platform(
                        platform=platform,
                        topic=keyword,
                        start_date=start_date,
                        end_date=end_date,
                        limit=limit,
                    )
                else:
                    logger.info(f"Unknown search tool: {tool_name}, using default global search")
                    response = self.search_agency.search_topic_globally(
                        topic=keyword,
                        limit_per_table=self.config.DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE,
                    )

                # Collect results
                if response.results:
                    logger.info(f"Found {len(response.results)} results")
                    all_results.extend(response.results)
                    total_count += len(response.results)
                else:
                    logger.info(f"No results found")

            except Exception as e:
                logger.error(f"Error while querying '{keyword}': {str(e)}")
                continue

        # Deduplication and consolidation of results
        unique_results = self._deduplicate_results(all_results)
        logger.info(f"A total of {total_count} results were found, and after deduplication, {len(unique_results)} results were found.")

        if ENABLE_CLUSTERING:
            unique_results = self._cluster_and_sample_results(
                unique_results,
                max_results=MAX_CLUSTERED_RESULTS,
                results_per_cluster=RESULTS_PER_CLUSTER,
            )

        # Build the integrated response
        integrated_response = DBResponse(
            tool_name=f"{tool_name}_optimized",
            parameters={
                "original_query": query,
                "optimized_keywords": optimized_response.optimized_keywords,
                "optimization_reasoning": optimized_response.reasoning,
                **kwargs,
            },
            results=unique_results,
            results_count=len(unique_results),
        )

        # Check if sentiment analysis is required
        enable_sentiment = kwargs.get("enable_sentiment", True)
        if enable_sentiment and unique_results and len(unique_results) > 0:
            logger.info(f"🎭 Start sentiment analysis of search results...")
            sentiment_analysis = self._perform_sentiment_analysis(unique_results)
            if sentiment_analysis:
                # Add sentiment analysis results to the parameters of the response
                integrated_response.parameters["sentiment_analysis"] = (
                    sentiment_analysis
                )
                logger.info(f"✅ Sentiment analysis completed")

        return integrated_response

    def _deduplicate_results(self, results: List) -> List:
        """Deduplication search results"""
        seen = set()
        unique_results = []

        for result in results:
            # Use URL or content as deduplication identifier
            identifier = result.url if result.url else result.title_or_content[:100]
            if identifier not in seen:
                seen.add(identifier)
                unique_results.append(result)

        return unique_results

    def _perform_sentiment_analysis(self, results: List) -> Optional[Dict[str, Any]]:
        """Perform sentiment analysis on search results

        Args:
            results: search results list

        Returns:
            A dictionary of sentiment analysis results, returning None if failed"""
        try:
            # Initialize the sentiment analyzer (if not already initialized and disabled)
            if (
                not self.sentiment_analyzer.is_initialized
                and not self.sentiment_analyzer.is_disabled
            ):
                logger.info("Initialize sentiment analysis model...")
                if not self.sentiment_analyzer.initialize():
                    logger.info("The sentiment analysis model initialization failed and the original text will be directly transmitted transparently.")
            elif self.sentiment_analyzer.is_disabled:
                logger.info("The sentiment analysis function is disabled and the original text is directly transmitted")

            # Convert query results to dictionary format
            results_dict = []
            for result in results:
                result_dict = {
                    "content": result.title_or_content,
                    "platform": result.platform,
                    "author": result.author_nickname,
                    "url": result.url,
                    "publish_time": str(result.publish_time)
                    if result.publish_time
                    else None,
                }
                results_dict.append(result_dict)

            # Perform sentiment analysis
            sentiment_analysis = self.sentiment_analyzer.analyze_query_results(
                query_results=results_dict, text_field="content", min_confidence=0.5
            )

            return sentiment_analysis.get("sentiment_analysis")

        except Exception as e:
            logger.exception(f"❌ An error occurred during sentiment analysis: {str(e)}")
            return None

    def analyze_sentiment_only(self, texts: Union[str, List[str]]) -> Dict[str, Any]:
        """Standalone sentiment analysis tool

        Args:
            texts: single text or text list

        Returns:
            Sentiment analysis results"""
        logger.info(f"→ Perform independent sentiment analysis")

        try:
            # Initialize the sentiment analyzer (if not already initialized and disabled)
            if (
                not self.sentiment_analyzer.is_initialized
                and not self.sentiment_analyzer.is_disabled
            ):
                logger.info("Initialize sentiment analysis model...")
                if not self.sentiment_analyzer.initialize():
                    logger.info("The sentiment analysis model initialization failed and the original text will be directly transmitted transparently.")
            elif self.sentiment_analyzer.is_disabled:
                logger.warning("The sentiment analysis function is disabled and the original text is directly transmitted")

            # Perform analysis
            if isinstance(texts, str):
                result = self.sentiment_analyzer.analyze_single_text(texts)
                result_dict = result.__dict__
                response = {
                    "success": result.success and result.analysis_performed,
                    "total_analyzed": 1
                    if result.analysis_performed and result.success
                    else 0,
                    "results": [result_dict],
                }
                if not result.analysis_performed:
                    response["success"] = False
                    response["warning"] = (
                        result.error_message or "The sentiment analysis function is not available and the original text has been returned directly."
                    )
                return response
            else:
                texts_list = list(texts)
                batch_result = self.sentiment_analyzer.analyze_batch(
                    texts_list, show_progress=True
                )
                response = {
                    "success": batch_result.analysis_performed
                    and batch_result.success_count > 0,
                    "total_analyzed": batch_result.total_processed
                    if batch_result.analysis_performed
                    else 0,
                    "success_count": batch_result.success_count,
                    "failed_count": batch_result.failed_count,
                    "average_confidence": batch_result.average_confidence
                    if batch_result.analysis_performed
                    else 0.0,
                    "results": [result.__dict__ for result in batch_result.results],
                }
                if not batch_result.analysis_performed:
                    warning = next(
                        (
                            r.error_message
                            for r in batch_result.results
                            if r.error_message
                        ),
                        "The sentiment analysis function is not available and the original text has been returned directly.",
                    )
                    response["success"] = False
                    response["warning"] = warning
                return response

        except Exception as e:
            logger.exception(f"❌ An error occurred during sentiment analysis: {str(e)}")
            return {"success": False, "error": str(e), "results": []}

    def research(self, query: str, save_report: bool = True) -> str:
        """Perform in-depth research

        Args:
            query: research query
            save_report: whether to save the report to a file

        Returns:
            Final report content"""
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Start in-depth research: {query}")
        logger.info(f"{'=' * 60}")

        try:
            # Step 1: Generate report structure
            self._generate_report_structure(query)

            # Step 2: Process each paragraph
            self._process_paragraphs()

            # Step 3: Generate final report
            final_report = self._generate_final_report()

            # Step 4: Save report
            if save_report:
                self._save_report(final_report)

            logger.info("In-depth research completed!")

            return final_report

        except Exception as e:
            logger.exception(f"An error occurred during research: {str(e)}")
            raise e

    def _generate_report_structure(self, query: str):
        """Generate report structure"""
        logger.info(f"\n[Step 1] Generate report structure...")

        # Create report structure node
        report_structure_node = ReportStructureNode(self.llm_client, query)

        # Generate structure and update status
        self.state = report_structure_node.mutate_state(state=self.state)

        _message = f"The report structure has been generated, with {len(self.state.paragraphs)} paragraphs in total:"
        for i, paragraph in enumerate(self.state.paragraphs, 1):
            _message += f"\n  {i}. {paragraph.title}"
        logger.info(_message)

    def _process_paragraphs(self):
        """process all paragraphs"""
        total_paragraphs = len(self.state.paragraphs)

        for i in range(total_paragraphs):
            logger.info(
                f"\n[Step 2.{i + 1}] Process paragraphs: {self.state.paragraphs[i].title}"
            )
            logger.info("-" * 50)

            # Initial search and summary
            self._initial_search_and_summary(i)

            # reflective cycle
            self._reflection_loop(i)

            # Mark paragraph complete
            self.state.paragraphs[i].research.mark_completed()

            progress = (i + 1) / total_paragraphs * 100
            logger.info(f"Paragraph processing completed ({progress:.1f}%)")

    def _initial_search_and_summary(self, paragraph_index: int):
        """Perform initial search and summary"""
        paragraph = self.state.paragraphs[paragraph_index]

        # Prepare search input
        search_input = {"title": paragraph.title, "content": paragraph.content}

        # Generate search queries and tool selections
        logger.info("- Generate search queries...")
        search_output = self.first_search_node.run(search_input)
        search_query = search_output["search_query"]
        search_tool = search_output.get(
            "search_tool", "search_topic_globally"
        )  # Default tool
        reasoning = search_output["reasoning"]

        logger.info(f"- Search query: {search_query}")
        logger.info(f"- Selected tool: {search_tool}")
        logger.info(f"- Reasoning: {reasoning}")

        # Perform a search
        logger.info("- Execute database queries...")

        # Handle special parameters
        search_kwargs = {}

        # Tools for handling required dates
        if search_tool in ["search_topic_by_date", "search_topic_on_platform"]:
            start_date = search_output.get("start_date")
            end_date = search_output.get("end_date")

            if start_date and end_date:
                # Validate date format
                if self._validate_date_format(
                    start_date
                ) and self._validate_date_format(end_date):
                    search_kwargs["start_date"] = start_date
                    search_kwargs["end_date"] = end_date
                    logger.info(f"- Time range: {start_date} to {end_date}")
                else:
                    logger.info(f"Wrong date format (should be YYYY-MM-DD), use global search instead")
                    logger.info(
                        f"Dates provided: start_date={start_date}, end_date={end_date}"
                    )
                    search_tool = "search_topic_globally"
            elif search_tool == "search_topic_by_date":
                logger.info(f"The search_topic_by_date tool lacks time parameters, use global search instead")
                search_tool = "search_topic_globally"

        # Handles tools that require platform parameters
        if search_tool == "search_topic_on_platform":
            platform = search_output.get("platform")
            if platform:
                search_kwargs["platform"] = platform
                logger.info(f"- Specify platform: {platform}")
            else:
                logger.warning(
                    f"The search_topic_on_platform tool lacks platform parameters, use global search instead"
                )
                search_tool = "search_topic_globally"

        # Handle constraint parameters, using default values ​​in the configuration file instead of parameters provided by the agent
        if search_tool == "search_hot_content":
            time_period = search_output.get("time_period", "week")
            limit = self.config.DEFAULT_SEARCH_HOT_CONTENT_LIMIT
            search_kwargs["time_period"] = time_period
            search_kwargs["limit"] = limit
        elif search_tool in ["search_topic_globally", "search_topic_by_date"]:
            if search_tool == "search_topic_globally":
                limit_per_table = (
                    self.config.DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE
                )
            else:  # search_topic_by_date
                limit_per_table = (
                    self.config.DEFAULT_SEARCH_TOPIC_BY_DATE_LIMIT_PER_TABLE
                )
            search_kwargs["limit_per_table"] = limit_per_table
        elif search_tool in ["get_comments_for_topic", "search_topic_on_platform"]:
            if search_tool == "get_comments_for_topic":
                limit = self.config.DEFAULT_GET_COMMENTS_FOR_TOPIC_LIMIT
            else:  # search_topic_on_platform
                limit = self.config.DEFAULT_SEARCH_TOPIC_ON_PLATFORM_LIMIT
            search_kwargs["limit"] = limit

        search_response = self.execute_search_tool(
            search_tool, search_query, **search_kwargs
        )

        # Convert to compatible format
        search_results = []
        if search_response and search_response.results:
            # Use the configuration file to control the number of results passed to LLM, 0 means no limit
            if self.config.MAX_SEARCH_RESULTS_FOR_LLM > 0:
                max_results = min(
                    len(search_response.results), self.config.MAX_SEARCH_RESULTS_FOR_LLM
                )
            else:
                max_results = len(search_response.results)  # No limit, pass all results
            for result in search_response.results[:max_results]:
                search_results.append(
                    {
                        "title": result.title_or_content,
                        "url": result.url or "",
                        "content": result.title_or_content,
                        "score": result.hotness_score,
                        "raw_content": result.title_or_content,
                        "published_date": result.publish_time.isoformat()
                        if result.publish_time
                        else None,
                        "platform": result.platform,
                        "content_type": result.content_type,
                        "author": result.author_nickname,
                        "engagement": result.engagement,
                    }
                )

        if search_results:
            _message = f"- {len(search_results)} search results found"
            for j, result in enumerate(search_results, 1):
                date_info = (
                    f"(Published in: {result.get('published_date', 'N/A')})"
                    if result.get("published_date")
                    else ""
                )
                _message += f"\n    {j}. {result['title'][:50]}...{date_info}"
            logger.info(_message)
        else:
            logger.info("- No search results found")

        # Update search history in status
        paragraph.research.add_search_results(search_query, search_results)

        # Generate initial summary
        logger.info("- Generate initial summary...")
        summary_input = {
            "title": paragraph.title,
            "content": paragraph.content,
            "search_query": search_query,
            "search_results": format_search_results_for_prompt(
                search_results, self.config.MAX_CONTENT_LENGTH
            ),
        }

        # update status
        self.state = self.first_summary_node.mutate_state(
            summary_input, self.state, paragraph_index
        )

        logger.info("- Initial summary completed")

    def _reflection_loop(self, paragraph_index: int):
        """Execute a reflective cycle"""
        paragraph = self.state.paragraphs[paragraph_index]

        for reflection_i in range(self.config.MAX_REFLECTIONS):
            logger.info(f"- reflection {reflection_i + 1}/{self.config.MAX_REFLECTIONS}...")

            # Prepare reflective input
            reflection_input = {
                "title": paragraph.title,
                "content": paragraph.content,
                "paragraph_latest_state": paragraph.research.latest_summary,
            }

            # Generate reflective search queries
            reflection_output = self.reflection_node.run(reflection_input)
            search_query = reflection_output["search_query"]
            search_tool = reflection_output.get(
                "search_tool", "search_topic_globally"
            )  # Default tool
            reasoning = reflection_output["reasoning"]

            logger.info(f"Reflection query: {search_query}")
            logger.info(f"Selected tool: {search_tool}")
            logger.info(f"reflective reasoning: {reasoning}")

            # Perform a reflective search
            # Handle special parameters
            search_kwargs = {}

            # Tools for handling required dates
            if search_tool in ["search_topic_by_date", "search_topic_on_platform"]:
                start_date = reflection_output.get("start_date")
                end_date = reflection_output.get("end_date")

                if start_date and end_date:
                    # Validate date format
                    if self._validate_date_format(
                        start_date
                    ) and self._validate_date_format(end_date):
                        search_kwargs["start_date"] = start_date
                        search_kwargs["end_date"] = end_date
                        logger.info(f"Time range: {start_date} to {end_date}")
                    else:
                        logger.info(
                            f"Wrong date format (should be YYYY-MM-DD), use global search instead"
                        )
                        logger.info(
                            f"Dates provided: start_date={start_date}, end_date={end_date}"
                        )
                        search_tool = "search_topic_globally"
                elif search_tool == "search_topic_by_date":
                    logger.warning(
                        f"The search_topic_by_date tool lacks time parameters, use global search instead"
                    )
                    search_tool = "search_topic_globally"

            # Handles tools that require platform parameters
            if search_tool == "search_topic_on_platform":
                platform = reflection_output.get("platform")
                if platform:
                    search_kwargs["platform"] = platform
                    logger.info(f"Specify platform: {platform}")
                else:
                    logger.warning(
                        f"The search_topic_on_platform tool lacks platform parameters, use global search instead"
                    )
                    search_tool = "search_topic_globally"

            # Processing restriction parameters
            if search_tool == "search_hot_content":
                time_period = reflection_output.get("time_period", "week")
                # Use the default value in the configuration file and do not allow the agent to control the limit parameter
                limit = self.config.DEFAULT_SEARCH_HOT_CONTENT_LIMIT
                search_kwargs["time_period"] = time_period
                search_kwargs["limit"] = limit
            elif search_tool in ["search_topic_globally", "search_topic_by_date"]:
                # Use the default value in the configuration file and do not allow the agent to control the limit_per_table parameter
                if search_tool == "search_topic_globally":
                    limit_per_table = (
                        self.config.DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE
                    )
                else:  # search_topic_by_date
                    limit_per_table = (
                        self.config.DEFAULT_SEARCH_TOPIC_BY_DATE_LIMIT_PER_TABLE
                    )
                search_kwargs["limit_per_table"] = limit_per_table
            elif search_tool in ["get_comments_for_topic", "search_topic_on_platform"]:
                # Use the default value in the configuration file and do not allow the agent to control the limit parameter
                if search_tool == "get_comments_for_topic":
                    limit = self.config.DEFAULT_GET_COMMENTS_FOR_TOPIC_LIMIT
                else:  # search_topic_on_platform
                    limit = self.config.DEFAULT_SEARCH_TOPIC_ON_PLATFORM_LIMIT
                search_kwargs["limit"] = limit

            search_response = self.execute_search_tool(
                search_tool, search_query, **search_kwargs
            )

            # Convert to compatible format
            search_results = []
            if search_response and search_response.results:
                # Use the configuration file to control the number of results passed to LLM, 0 means no limit
                if self.config.MAX_SEARCH_RESULTS_FOR_LLM > 0:
                    max_results = min(
                        len(search_response.results),
                        self.config.MAX_SEARCH_RESULTS_FOR_LLM,
                    )
                else:
                    max_results = len(search_response.results)  # No limit, pass all results
                for result in search_response.results[:max_results]:
                    search_results.append(
                        {
                            "title": result.title_or_content,
                            "url": result.url or "",
                            "content": result.title_or_content,
                            "score": result.hotness_score,
                            "raw_content": result.title_or_content,
                            "published_date": result.publish_time.isoformat()
                            if result.publish_time
                            else None,
                            "platform": result.platform,
                            "content_type": result.content_type,
                            "author": result.author_nickname,
                            "engagement": result.engagement,
                        }
                    )

            if search_results:
                _message = f"Found {len(search_results)} reflection search results"
                for j, result in enumerate(search_results, 1):
                    date_info = (
                        f"(Published in: {result.get('published_date', 'N/A')})"
                        if result.get("published_date")
                        else ""
                    )
                    _message += f"\n      {j}. {result['title'][:50]}...{date_info}"
                logger.info(_message)
            else:
                logger.info("No reflection search results found")

            # Update search history
            paragraph.research.add_search_results(search_query, search_results)

            # Generate reflection summaries
            reflection_summary_input = {
                "title": paragraph.title,
                "content": paragraph.content,
                "search_query": search_query,
                "search_results": format_search_results_for_prompt(
                    search_results, self.config.MAX_CONTENT_LENGTH
                ),
                "paragraph_latest_state": paragraph.research.latest_summary,
            }

            # update status
            self.state = self.reflection_summary_node.mutate_state(
                reflection_summary_input, self.state, paragraph_index
            )

            logger.info(f"Reflection {reflection_i + 1} completed")

    def _generate_final_report(self) -> str:
        """Generate final report"""
        logger.info(f"\n[Step 3] Generate final report...")

        # Prepare reporting data
        report_data = []
        for paragraph in self.state.paragraphs:
            report_data.append(
                {
                    "title": paragraph.title,
                    "paragraph_latest_state": paragraph.research.latest_summary,
                }
            )

        # Format reports
        try:
            final_report = self.report_formatting_node.run(report_data)
        except Exception as e:
            logger.exception(f"LLM format failed, use fallback method: {str(e)}")
            final_report = self.report_formatting_node.format_report_manually(
                report_data, self.state.report_title
            )

        # update status
        self.state.final_report = final_report
        self.state.mark_completed()

        logger.info("Final report generation completed")
        return final_report

    def _save_report(self, report_content: str):
        """Save report to file"""
        # Generate file name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_safe = "".join(
            c for c in self.state.query if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        query_safe = query_safe.replace(" ", "_")[:30]

        filename = f"deep_search_report_{query_safe}_{timestamp}.md"
        filepath = os.path.join(self.config.OUTPUT_DIR, filename)

        # save report
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info(f"Report saved to: {filepath}")

        # Save state (if configuration allows)
        if self.config.SAVE_INTERMEDIATE_STATES:
            state_filename = f"state_{query_safe}_{timestamp}.json"
            state_filepath = os.path.join(self.config.OUTPUT_DIR, state_filename)
            self.state.save_to_file(state_filepath)
            logger.info(f"State saved to: {state_filepath}")

    def get_progress_summary(self) -> Dict[str, Any]:
        """Get progress summary"""
        return self.state.get_progress_summary()

    def load_state(self, filepath: str):
        """Load status from file"""
        self.state = State.load_from_file(filepath)
        logger.info(f"Status loaded from {filepath}")

    def save_state(self, filepath: str):
        """Save state to file"""
        self.state.save_to_file(filepath)
        logger.info(f"Status saved to {filepath}")


def create_agent(config_file: Optional[str] = None) -> DeepSearchAgent:
    """Convenience functions for creating Deep Search Agent instances

    Args:
        config_file: configuration file path

    Returns:
        DeepSearchAgent instance"""
    config = Settings()  # Initialized with empty configuration and initialized from environment variables
    return DeepSearchAgent(config)
