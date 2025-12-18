"""Streamlit web interface
Provide a friendly web interface for Media Agent"""

import os
import sys
import streamlit as st
from datetime import datetime
import json
import locale
from loguru import logger

# Set UTF-8 encoding environment
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

# Set system encoding
try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    except locale.Error:
        pass

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from MediaEngine import DeepSearchAgent, AnspireSearchAgent, Settings
from config import settings
from utils.github_issues import error_with_issue_link


def main():
    """main function"""
    st.set_page_config(
        page_title="Media Agent",
        page_icon="",
        layout="wide"
    )

    st.title("Media Agent")
    st.markdown("AI agent with powerful multi-modal capabilities")
    st.markdown("Break through the limitations of traditional text communication and extensively browse videos, pictures, texts, and live broadcasts on Douyin, Kuaishou, and Xiaohongshu")
    st.markdown("Further enhance capabilities with multi-modal structured information such as calendar cards, weather cards, stock cards and more provided by modern search engines")

    # Check URL parameters
    try:
        # Try using new version of query_params
        query_params = st.query_params
        auto_query = query_params.get('query', '')
        auto_search = query_params.get('auto_search', 'false').lower() == 'true'
    except AttributeError:
        # Compatible with older versions
        query_params = st.experimental_get_query_params()
        auto_query = query_params.get('query', [''])[0]
        auto_search = query_params.get('auto_search', ['false'])[0].lower() == 'true'

    # ----- Configuration is hardcoded -----
    # Force use of Gemini
    model_name = settings.MEDIA_ENGINE_MODEL_NAME or "gemini-2.5-pro"
    # Default advanced configuration
    max_reflections = 2
    max_content_length = 20000

    # Simplified research query display area

    # If there is an automatic query, use it as the default, otherwise show the placeholder
    display_query = auto_query if auto_query else "Waiting to receive analysis content from the main page..."

    # Read-only query display area
    st.text_area(
        "Current query",
        value=display_query,
        height=100,
        disabled=True,
        help="The query content is controlled by the search box on the main page",
        label_visibility="hidden"
    )

    # Automatic search logic
    start_research = False
    query = auto_query

    if auto_search and auto_query and 'auto_search_executed' not in st.session_state:
        st.session_state.auto_search_executed = True
        start_research = True
    elif auto_query and not auto_search:
        st.warning("Waiting for search start signal...")

    # Verify configuration
    if start_research:
        if not query.strip():
            st.error("Please enter a research query")
            logger.error("Please enter a research query")
            return

        # Since using Gemini is mandatory, check the relevant API keys
        if not settings.MEDIA_ENGINE_API_KEY:
            st.error("Please set MEDIA_ENGINE_API_KEY in your environment variables")
            logger.error("Please set MEDIA_ENGINE_API_KEY in your environment variables")
            return

        # Automatically use API keys from configuration files
        engine_key = settings.MEDIA_ENGINE_API_KEY
        bocha_key = settings.BOCHA_WEB_SEARCH_API_KEY
        ansire_key = settings.ANSPIRE_API_KEY

        # Build Settings (pydantic_settings style, uppercase environment variables first)
        if settings.SEARCH_TOOL_TYPE == "BochaAPI":
            if not bocha_key:
                st.error("Please set BOCHA_WEB_SEARCH_API_KEY in your environment variables")
                logger.error("Please set BOCHA_WEB_SEARCH_API_KEY in your environment variables")
                return
            logger.info("Search API keys using Bocha")
            config = Settings(
                MEDIA_ENGINE_API_KEY=engine_key,
                MEDIA_ENGINE_BASE_URL=settings.MEDIA_ENGINE_BASE_URL,
                MEDIA_ENGINE_MODEL_NAME=model_name,
                SEARCH_TOOL_TYPE="BochaAPI",
                BOCHA_WEB_SEARCH_API_KEY=bocha_key,
                MAX_REFLECTIONS=max_reflections,
                SEARCH_CONTENT_MAX_LENGTH=max_content_length,
                OUTPUT_DIR="media_engine_streamlit_reports",
            )
        elif settings.SEARCH_TOOL_TYPE == "AnspireAPI":
            if not ansire_key:
                st.error("Please set ANSPIRE_API_KEY in your environment variables")
                logger.error("Please set ANSPIRE_API_KEY in your environment variables")
                return
            logger.info("Search API keys using Anspire")
            config = Settings(
                MEDIA_ENGINE_API_KEY=engine_key,
                MEDIA_ENGINE_BASE_URL=settings.MEDIA_ENGINE_BASE_URL,
                MEDIA_ENGINE_MODEL_NAME=model_name,
                SEARCH_TOOL_TYPE="AnspireAPI",
                ANSPIRE_API_KEY=ansire_key,
                MAX_REFLECTIONS=max_reflections,
                SEARCH_CONTENT_MAX_LENGTH=max_content_length,
                OUTPUT_DIR="media_engine_streamlit_reports",
            )
        else:
            st.error(f"Unknown search tool type: {settings.SEARCH_TOOL_TYPE}")
            logger.error(f"Unknown search tool type: {settings.SEARCH_TOOL_TYPE}")
            return

        # Execute research
        execute_research(query, config)


def execute_research(query: str, config: Settings):
    """Execute research"""
    try:
        # Create a progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()

        # InitializeAgent
        status_text.text("Initializing Agent...")
        if config.SEARCH_TOOL_TYPE == "BochaAPI":
            agent = DeepSearchAgent(config)
        elif config.SEARCH_TOOL_TYPE == "AnspireAPI":
            agent = AnspireSearchAgent(config)
        else:
            raise ValueError(f"Unknown search tool type: {config.SEARCH_TOOL_TYPE}")
        st.session_state.agent = agent

        progress_bar.progress(10)

        # Generate report structure
        status_text.text("Generating report structure...")
        agent._generate_report_structure(query)
        progress_bar.progress(20)

        # Process paragraphs
        total_paragraphs = len(agent.state.paragraphs)
        for i in range(total_paragraphs):
            status_text.text(f"Processing paragraph {i + 1}/{total_paragraphs}: {agent.state.paragraphs[i].title}")

            # Initial search and summary
            agent._initial_search_and_summary(i)
            progress_value = 20 + (i + 0.5) / total_paragraphs * 60
            progress_bar.progress(int(progress_value))

            # reflective cycle
            agent._reflection_loop(i)
            agent.state.paragraphs[i].research.mark_completed()

            progress_value = 20 + (i + 1) / total_paragraphs * 60
            progress_bar.progress(int(progress_value))

        # Generate final report
        status_text.text("Generating final report...")
        logger.info("Generating final report...")
        final_report = agent._generate_final_report()
        progress_bar.progress(90)

        # save report
        status_text.text("Saving report...")
        logger.info("Saving report...")
        agent._save_report(final_report)
        progress_bar.progress(100)

        status_text.text("Research done!")
        logger.info("Research done!")
        # Show results
        display_results(agent, final_report)

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        error_display = error_with_issue_link(
            f"An error occurred during research: {str(e)}",
            error_traceback,
            app_name="Media Engine Streamlit App"
        )
        st.error(error_display)
        logger.exception(f"An error occurred during research: {str(e)}")


def display_results(agent: DeepSearchAgent, final_report: str):
    """Show research results"""
    st.header("Research results")

    # Results tab (download option removed)
    tab1, tab2 = st.tabs(["Research summary", "Citation information"])

    with tab1:
        st.markdown(final_report)

    with tab2:
        # Paragraph details
        st.subheader("Paragraph details")
        for i, paragraph in enumerate(agent.state.paragraphs):
            with st.expander(f"Paragraph {i + 1}: {paragraph.title}"):
                st.write("**Expected content:**", paragraph.content)
                st.write("**Final content:**", paragraph.research.latest_summary[:300] + "..."
                if len(paragraph.research.latest_summary) > 300
                else paragraph.research.latest_summary)
                st.write("**Number of searches:**", paragraph.research.get_search_count())
                st.write("**Number of reflections:**", paragraph.research.reflection_iteration)

        # Search history
        st.subheader("Search history")
        all_searches = []
        for paragraph in agent.state.paragraphs:
            all_searches.extend(paragraph.research.search_history)

        if all_searches:
            for i, search in enumerate(all_searches):
                query_label = search.query if search.query else "Unrecorded query"
                with st.expander(f"Search {i + 1}: {query_label}"):
                    paragraph_title = getattr(search, "paragraph_title", "") or "Unmarked paragraph"
                    search_tool = getattr(search, "search_tool", "") or "Unlabeled tools"
                    has_result = getattr(search, "has_result", True)
                    st.write("**paragraph:**", paragraph_title)
                    st.write("**Tools used:**", search_tool)
                    preview = search.content or ""
                    if not isinstance(preview, str):
                        preview = str(preview)
                    if len(preview) > 200:
                        preview = preview[:200] + "..."
                    st.write("**URL:**", search.url or "none")
                    st.write("**title:**", search.title or "none")
                    st.write("**Content Preview:**", preview if preview else "No content available")
                    if not has_result:
                        st.info("This search returned no results")
                    if search.score:
                        st.write("**Relevance Score:**", search.score)


if __name__ == "__main__":
    main()
