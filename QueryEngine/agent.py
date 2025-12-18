"""Deep Search Agent main class
Integrate all modules to achieve a complete in-depth search process"""

import json
import os
import re
from datetime import datetime
from typing import Optional, Dict, Any, List

from .llms import LLMClient
from .nodes import (
    ReportStructureNode,
    FirstSearchNode, 
    ReflectionNode,
    FirstSummaryNode,
    ReflectionSummaryNode,
    ReportFormattingNode
)
from .state import State
from .tools import TavilyNewsAgency, TavilyResponse
from .utils import Settings, format_search_results_for_prompt
from loguru import logger

class DeepSearchAgent:
    """Deep Search Agent main class"""
    
    def __init__(self, config: Optional[Settings] = None):
        """Initialize Deep Search Agent
        
        Args:
            config: configuration object, automatically loaded if not provided"""
        # Load configuration
        from .utils.config import settings
        self.config = config or settings
        
        # Initialize LLM client
        self.llm_client = self._initialize_llm()
        
        # Initialize the search toolset
        self.search_agency = TavilyNewsAgency(api_key=self.config.TAVILY_API_KEY)
        
        # Initialize node
        self._initialize_nodes()
        
        # state
        self.state = State()
        
        # Make sure the output directory exists
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        
        logger.info(f"Query Agent has been initialized")
        logger.info(f"Using LLM: {self.llm_client.get_model_info()}")
        logger.info(f"Search toolset: TavilyNewsAgency (supports 6 search tools)")
    
    def _initialize_llm(self) -> LLMClient:
        """Initialize LLM client"""
        return LLMClient(
            api_key=self.config.QUERY_ENGINE_API_KEY,
            model_name=self.config.QUERY_ENGINE_MODEL_NAME,
            base_url=self.config.QUERY_ENGINE_BASE_URL,
        )
    
    def _initialize_nodes(self):
        """Initialize processing node"""
        self.first_search_node = FirstSearchNode(self.llm_client)
        self.reflection_node = ReflectionNode(self.llm_client)
        self.first_summary_node = FirstSummaryNode(self.llm_client)
        self.reflection_summary_node = ReflectionSummaryNode(self.llm_client)
        self.report_formatting_node = ReportFormattingNode(self.llm_client)
    
    def _validate_date_format(self, date_str: str) -> bool:
        """Verify that the date format is YYYY-MM-DD
        
        Args:
            date_str: date string
            
        Returns:
            Is it a valid format?"""
        if not date_str:
            return False
        
        # Check format
        pattern = r'^\d{4}-\d{2}-\d{2}$'
        if not re.match(pattern, date_str):
            return False
        
        # Check if the date is valid
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False
    
    def execute_search_tool(self, tool_name: str, query: str, **kwargs) -> TavilyResponse:
        """Execute the specified search tool
        
        Args:
            tool_name: tool name, optional value:
                -"basic_search_news": Basic news search (fast, universal)
                -"deep_search_news": In-depth news analysis
                -"search_news_last_24_hours": Latest news within 24 hours
                -"search_news_last_week": News of the week
                -"search_images_for_news": News photo search
                -"search_news_by_date": Search news by date range
            query: search query
            **kwargs: additional parameters (such as start_date, end_date, max_results)
            
        Returns:
            TavilyResponse object"""
        logger.info(f"→ Execute search tool: {tool_name}")
        
        if tool_name == "basic_search_news":
            max_results = kwargs.get("max_results", 7)
            return self.search_agency.basic_search_news(query, max_results)
        elif tool_name == "deep_search_news":
            return self.search_agency.deep_search_news(query)
        elif tool_name == "search_news_last_24_hours":
            return self.search_agency.search_news_last_24_hours(query)
        elif tool_name == "search_news_last_week":
            return self.search_agency.search_news_last_week(query)
        elif tool_name == "search_images_for_news":
            return self.search_agency.search_images_for_news(query)
        elif tool_name == "search_news_by_date":
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")
            if not start_date or not end_date:
                raise ValueError("The search_news_by_date tool requires start_date and end_date parameters")
            return self.search_agency.search_news_by_date(query, start_date, end_date)
        else:
            logger.warning(f"⚠️ Unknown search tool: {tool_name}, using default basic search")
            return self.search_agency.basic_search_news(query)
    
    def research(self, query: str, save_report: bool = True) -> str:
        """Perform in-depth research
        
        Args:
            query: research query
            save_report: whether to save the report to a file
            
        Returns:
            Final report content"""
        logger.info(f"\n{'='*60}")
        logger.info(f"Start in-depth research: {query}")
        logger.info(f"{'='*60}")
        
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
            
            logger.info(f"\n{'='*60}")
            logger.info("In-depth research completed!")
            logger.info(f"{'='*60}")
            
            return final_report
            
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"An error occurred during research: {str(e)} \nError stack: {error_traceback}")
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
            logger.info(f"\n[Step 2.{i+1}] Process paragraphs: {self.state.paragraphs[i].title}")
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
        search_input = {
            "title": paragraph.title,
            "content": paragraph.content
        }
        
        # Generate search queries and tool selections
        logger.info("- Generate search queries...")
        search_output = self.first_search_node.run(search_input)
        search_query = search_output["search_query"]
        search_tool = search_output.get("search_tool", "basic_search_news")  # Default tool
        reasoning = search_output["reasoning"]
        
        logger.info(f"- Search query: {search_query}")
        logger.info(f"- Selected tool: {search_tool}")
        logger.info(f"- Reasoning: {reasoning}")
        
        # Perform a search
        logger.info("- Perform a web search...")
        
        # Special parameters for handling search_news_by_date
        search_kwargs = {}
        if search_tool == "search_news_by_date":
            start_date = search_output.get("start_date")
            end_date = search_output.get("end_date")
            
            if start_date and end_date:
                # Validate date format
                if self._validate_date_format(start_date) and self._validate_date_format(end_date):
                    search_kwargs["start_date"] = start_date
                    search_kwargs["end_date"] = end_date
                    logger.info(f"- Time range: {start_date} to {end_date}")
                else:
                    logger.info(f"⚠️ The date format is wrong (should be YYYY-MM-DD), use basic search instead")
                    logger.info(f"Dates provided: start_date={start_date}, end_date={end_date}")
                    search_tool = "basic_search_news"
            else:
                logger.info(f"⚠️ The search_news_by_date tool lacks time parameters, use basic search instead")
                search_tool = "basic_search_news"
        
        search_response = self.execute_search_tool(search_tool, search_query, **search_kwargs)
        
        # Convert to compatible format
        search_results = []
        if search_response and search_response.results:
            # Each search tool has its specific number of results, here we take the top 10 as the upper limit
            max_results = min(len(search_response.results), 10)
            for result in search_response.results[:max_results]:
                search_results.append({
                    'title': result.title,
                    'url': result.url,
                    'content': result.content,
                    'score': result.score,
                    'raw_content': result.raw_content,
                    'published_date': result.published_date  # Add new field
                })
        
        if search_results:
            _message = f"- {len(search_results)} search results found"
            for j, result in enumerate(search_results, 1):
                date_info = f"(Published in: {result.get('published_date', 'N/A')})" if result.get('published_date') else ""
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
                search_results, self.config.SEARCH_CONTENT_MAX_LENGTH
            )
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
                "paragraph_latest_state": paragraph.research.latest_summary
            }
            
            # Generate reflective search queries
            reflection_output = self.reflection_node.run(reflection_input)
            search_query = reflection_output["search_query"]
            search_tool = reflection_output.get("search_tool", "basic_search_news")  # Default tool
            reasoning = reflection_output["reasoning"]
            
            logger.info(f"Reflection query: {search_query}")
            logger.info(f"Selected tool: {search_tool}")
            logger.info(f"reflective reasoning: {reasoning}")
            
            # Perform a reflective search
            # Special parameters for handling search_news_by_date
            search_kwargs = {}
            if search_tool == "search_news_by_date":
                start_date = reflection_output.get("start_date")
                end_date = reflection_output.get("end_date")
                
                if start_date and end_date:
                    # Validate date format
                    if self._validate_date_format(start_date) and self._validate_date_format(end_date):
                        search_kwargs["start_date"] = start_date
                        search_kwargs["end_date"] = end_date
                        logger.info(f"Time range: {start_date} to {end_date}")
                    else:
                        logger.info(f"⚠️ The date format is wrong (should be YYYY-MM-DD), use basic search instead")
                        logger.info(f"Dates provided: start_date={start_date}, end_date={end_date}")
                        search_tool = "basic_search_news"
                else:
                    logger.info(f"⚠️ The search_news_by_date tool lacks time parameters, use basic search instead")
                    search_tool = "basic_search_news"
            
            search_response = self.execute_search_tool(search_tool, search_query, **search_kwargs)
            
            # Convert to compatible format
            search_results = []
            if search_response and search_response.results:
                # Each search tool has its specific number of results, here we take the top 10 as the upper limit
                max_results = min(len(search_response.results), 10)
                for result in search_response.results[:max_results]:
                    search_results.append({
                        'title': result.title,
                        'url': result.url,
                        'content': result.content,
                        'score': result.score,
                        'raw_content': result.raw_content,
                        'published_date': result.published_date
                    })
            
            if search_results:
                logger.info(f"Found {len(search_results)} reflection search results")
                for j, result in enumerate(search_results, 1):
                    date_info = f"(Published in: {result.get('published_date', 'N/A')})" if result.get('published_date') else ""
                    logger.info(f"      {j}. {result['title'][:50]}...{date_info}")
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
                    search_results, self.config.SEARCH_CONTENT_MAX_LENGTH
                ),
                "paragraph_latest_state": paragraph.research.latest_summary
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
            report_data.append({
                "title": paragraph.title,
                "paragraph_latest_state": paragraph.research.latest_summary
            })
        
        # Format reports
        try:
            final_report = self.report_formatting_node.run(report_data)
        except Exception as e:
            logger.error(f"LLM format failed, use fallback method: {str(e)}")
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
        query_safe = "".join(c for c in self.state.query if c.isalnum() or c in (' ', '-', '_')).rstrip()
        query_safe = query_safe.replace(' ', '_')[:30]
        
        filename = f"deep_search_report_{query_safe}_{timestamp}.md"
        filepath = os.path.join(self.config.OUTPUT_DIR, filename)
        
        # save report
        with open(filepath, 'w', encoding='utf-8') as f:
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


def create_agent() -> DeepSearchAgent:
    """Convenience functions for creating Deep Search Agent instances
    
    Returns:
        DeepSearchAgent instance"""
    from .utils.config import Settings
    config = Settings()
    return DeepSearchAgent(config)
