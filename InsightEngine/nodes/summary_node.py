"""Summary node implementation
Responsible for generating and updating paragraph content based on search results"""

import json
from typing import Dict, Any, List
from json.decoder import JSONDecodeError
from loguru import logger

from .base_node import StateMutationNode
from ..state.state import State
from ..prompts import SYSTEM_PROMPT_FIRST_SUMMARY, SYSTEM_PROMPT_REFLECTION_SUMMARY
from ..utils.text_processing import (
    remove_reasoning_from_output,
    clean_json_tags,
    extract_clean_response,
    fix_incomplete_json,
    format_search_results_for_prompt
)

# Import forum reading tool
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from utils.forum_reader import get_latest_host_speech, format_host_speech_for_prompt
    FORUM_READER_AVAILABLE = True
except ImportError:
    FORUM_READER_AVAILABLE = False
    logger.warning("The forum_reader module cannot be imported and the HOST forum reading function will be skipped.")


class FirstSummaryNode(StateMutationNode):
    """Generate the node for the first summary of the paragraph based on the search results."""
    
    def __init__(self, llm_client):
        """Initialize the first summary node
        
        Args:
            llm_client: LLM client"""
        super().__init__(llm_client, "FirstSummaryNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                required_fields = ["title", "content", "search_query", "search_results"]
                return all(field in data for field in required_fields)
            except JSONDecodeError:
                return False
        elif isinstance(input_data, dict):
            required_fields = ["title", "content", "search_query", "search_results"]
            return all(field in input_data for field in required_fields)
        return False
    
    def run(self, input_data: Any, **kwargs) -> str:
        """Call LLM to generate paragraph summary
        
        Args:
            input_data: data containing title, content, search_query and search_results
            **kwargs: additional parameters
            
        Returns:
            Paragraph summary content"""
        try:
            if not self.validate_input(input_data):
                raise ValueError("Input data format error")
            
            # Prepare to enter data
            if isinstance(input_data, str):
                data = json.loads(input_data)
            else:
                data = input_data.copy() if isinstance(input_data, dict) else input_data
            
            # Read the latest HOST statement (if available)
            if FORUM_READER_AVAILABLE:
                try:
                    host_speech = get_latest_host_speech()
                    if host_speech:
                        # Add HOST speech to input data
                        data['host_speech'] = host_speech
                        logger.info(f"HOST speech has been read, length: {len(host_speech)} characters")
                except Exception as e:
                    logger.exception(f"Failed to read HOST statement: {str(e)}")
            
            # Convert to JSON string
            message = json.dumps(data, ensure_ascii=False)
            
            # If there is a HOST speaking, add it to the front of the message as a reference.
            if FORUM_READER_AVAILABLE and 'host_speech' in data and data['host_speech']:
                formatted_host = format_host_speech_for_prompt(data['host_speech'])
                message = formatted_host + "\n" + message
            
            logger.info("Generating first paragraph summary")
            
            # Call LLM (streaming, safe splicing of UTF-8)
            response = self.llm_client.stream_invoke_to_string(SYSTEM_PROMPT_FIRST_SUMMARY, message)
            
            # Handle response
            processed_response = self.process_output(response)
            
            logger.info("Successfully generated the first paragraph summary")
            return processed_response
            
        except Exception as e:
            logger.exception(f"Failed to generate first summary: {str(e)}")
            raise e
    
    def process_output(self, output: str) -> str:
        """Process LLM output and extract paragraph content
        
        Args:
            output: LLM raw output
            
        Returns:
            Paragraph content"""
        try:
            # Clean response text
            cleaned_output = remove_reasoning_from_output(output)
            cleaned_output = clean_json_tags(cleaned_output)
            
            # Logging cleaned output for debugging
            logger.info(f"Cleaned output: {cleaned_output}")
            
            # Parse JSON
            try:
                result = json.loads(cleaned_output)
                logger.info("JSON parsed successfully")
            except JSONDecodeError as e:
                logger.error(f"JSON parsing failed: {str(e)}")
                # Try to fix JSON
                fixed_json = fix_incomplete_json(cleaned_output)
                if fixed_json:
                    try:
                        result = json.loads(fixed_json)
                        logger.info("JSON repair successful")
                    except JSONDecodeError:
                        logger.exception("JSON repair failed, use the cleaned text directly")
                        # If it is not in JSON format, return the cleaned text directly.
                        return cleaned_output
                else:
                    logger.exception("Unable to repair JSON, use cleaned text directly")
                    # If it is not in JSON format, return the cleaned text directly.
                    return cleaned_output
            
            # Extract paragraph content
            if isinstance(result, dict):
                paragraph_content = result.get("paragraph_latest_state", "")
                if paragraph_content:
                    return paragraph_content
            
            # If extraction fails, return the original cleaned text
            return cleaned_output
            
        except Exception as e:
            logger.exception(f"Failed to process output: {str(e)}")
            return "Paragraph summary generation failed"
    
    def mutate_state(self, input_data: Any, state: State, paragraph_index: int, **kwargs) -> State:
        """Update the latest summary of the paragraph to the status
        
        Args:
            input_data: input data
            state: current state
            paragraph_index: paragraph index
            **kwargs: additional parameters
            
        Returns:
            Updated status"""
        try:
            # Generate summary
            summary = self.run(input_data, **kwargs)
            
            # update status
            if 0 <= paragraph_index < len(state.paragraphs):
                state.paragraphs[paragraph_index].research.latest_summary = summary
                logger.info(f"First summary of paragraph {paragraph_index} updated")
            else:
                raise ValueError(f"Paragraph index {paragraph_index} is out of range")
            
            state.update_timestamp()
            return state
            
        except Exception as e:
            logger.exception(f"Status update failed: {str(e)}")
            raise e


class ReflectionSummaryNode(StateMutationNode):
    """Update paragraph summary nodes based on reflection search results"""
    
    def __init__(self, llm_client):
        """Initialize reflection summary node
        
        Args:
            llm_client: LLM client"""
        super().__init__(llm_client, "ReflectionSummaryNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                required_fields = ["title", "content", "search_query", "search_results", "paragraph_latest_state"]
                return all(field in data for field in required_fields)
            except JSONDecodeError:
                return False
        elif isinstance(input_data, dict):
            required_fields = ["title", "content", "search_query", "search_results", "paragraph_latest_state"]
            return all(field in input_data for field in required_fields)
        return False
    
    def run(self, input_data: Any, **kwargs) -> str:
        """Call LLM to update paragraph content
        
        Args:
            input_data: data containing complete reflection information
            **kwargs: additional parameters
            
        Returns:
            Updated paragraph content"""
        try:
            if not self.validate_input(input_data):
                raise ValueError("Input data format error")
            
            # Prepare to enter data
            if isinstance(input_data, str):
                data = json.loads(input_data)
            else:
                data = input_data.copy() if isinstance(input_data, dict) else input_data
            
            # Read the latest HOST statement (if available)
            if FORUM_READER_AVAILABLE:
                try:
                    host_speech = get_latest_host_speech()
                    if host_speech:
                        # Add HOST speech to input data
                        data['host_speech'] = host_speech
                        logger.info(f"HOST speech has been read, length: {len(host_speech)} characters")
                except Exception as e:
                    logger.exception(f"Failed to read HOST statement: {str(e)}")
            
            # Convert to JSON string
            message = json.dumps(data, ensure_ascii=False)
            
            # If there is a HOST speaking, add it to the front of the message as a reference.
            if FORUM_READER_AVAILABLE and 'host_speech' in data and data['host_speech']:
                formatted_host = format_host_speech_for_prompt(data['host_speech'])
                message = formatted_host + "\n" + message
            
            logger.info("Generating reflection summary")
            
            # Call LLM (streaming, safe splicing of UTF-8)
            response = self.llm_client.stream_invoke_to_string(SYSTEM_PROMPT_REFLECTION_SUMMARY, message)
            
            # Handle response
            processed_response = self.process_output(response)
            
            logger.info("Successfully generated reflection summary")
            return processed_response
            
        except Exception as e:
            logger.exception(f"Failed to generate reflection summary: {str(e)}")
            raise e
    
    def process_output(self, output: str) -> str:
        """Process LLM output and extract updated paragraph content
        
        Args:
            output: LLM raw output
            
        Returns:
            Updated paragraph content"""
        try:
            # Clean response text
            cleaned_output = remove_reasoning_from_output(output)
            cleaned_output = clean_json_tags(cleaned_output)
            
            # Logging cleaned output for debugging
            logger.info(f"Cleaned output: {cleaned_output}")
            
            # Parse JSON
            try:
                result = json.loads(cleaned_output)
                logger.info("JSON parsed successfully")
            except JSONDecodeError as e:
                logger.error(f"JSON parsing failed: {str(e)}")
                # Try to fix JSON
                fixed_json = fix_incomplete_json(cleaned_output)
                if fixed_json:
                    try:
                        result = json.loads(fixed_json)
                        logger.info("JSON repair successful")
                    except JSONDecodeError:
                        logger.error("JSON repair failed, use the cleaned text directly")
                        # If it is not in JSON format, return the cleaned text directly.
                        return cleaned_output
                else:
                    logger.error("Unable to repair JSON, use cleaned text directly")
                    # If it is not in JSON format, return the cleaned text directly.
                    return cleaned_output
            
            # Extract updated paragraph content
            if isinstance(result, dict):
                updated_content = result.get("updated_paragraph_latest_state", "")
                if updated_content:
                    return updated_content
            
            # If extraction fails, return the original cleaned text
            return cleaned_output
            
        except Exception as e:
            logger.exception(f"Failed to process output: {str(e)}")
            return "Reflection summary generation failed"
    
    def mutate_state(self, input_data: Any, state: State, paragraph_index: int, **kwargs) -> State:
        """Write updated summary to status
        
        Args:
            input_data: input data
            state: current state
            paragraph_index: paragraph index
            **kwargs: additional parameters
            
        Returns:
            Updated status"""
        try:
            # Generate updated summary
            updated_summary = self.run(input_data, **kwargs)
            
            # update status
            if 0 <= paragraph_index < len(state.paragraphs):
                state.paragraphs[paragraph_index].research.latest_summary = updated_summary
                state.paragraphs[paragraph_index].research.increment_reflection()
                logger.info(f"Reflective summary of updated paragraph {paragraph_index}")
            else:
                raise ValueError(f"Paragraph index {paragraph_index} is out of range")
            
            state.update_timestamp()
            return state
            
        except Exception as e:
            logger.exception(f"Status update failed: {str(e)}")
            raise e
