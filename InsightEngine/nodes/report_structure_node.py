"""Report structure generation node
Responsible for the overall structure of generating reports based on queries"""

import json
from typing import Dict, Any, List
from json.decoder import JSONDecodeError
from loguru import logger

from .base_node import StateMutationNode
from ..state.state import State
from ..prompts import SYSTEM_PROMPT_REPORT_STRUCTURE
from ..utils.text_processing import (
    remove_reasoning_from_output,
    clean_json_tags,
    extract_clean_response,
    fix_incomplete_json
)


class ReportStructureNode(StateMutationNode):
    """The node that generates the report structure"""
    
    def __init__(self, llm_client, query: str):
        """Initialize report structure node
        
        Args:
            llm_client: LLM client
            query: user query"""
        super().__init__(llm_client, "ReportStructureNode")
        self.query = query
    
    def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""
        return isinstance(self.query, str) and len(self.query.strip()) > 0
    
    def run(self, input_data: Any = None, **kwargs) -> List[Dict[str, str]]:
        """Call LLM to generate report structure
        
        Args:
            input_data: input data (not used here, use the query during initialization)
            **kwargs: additional parameters
            
        Returns:
            Report structure list"""
        try:
            logger.info(f"Generating report structure for query: {self.query}")
            
            # Call LLM (streaming, safe splicing of UTF-8)
            response = self.llm_client.stream_invoke_to_string(SYSTEM_PROMPT_REPORT_STRUCTURE, self.query)
            
            # Handle response
            processed_response = self.process_output(response)
            
            logger.info(f"Successfully generated {len(processed_response)} paragraph structures")
            return processed_response
            
        except Exception as e:
            logger.exception(f"Failed to generate report structure: {str(e)}")
            raise e
    
    def process_output(self, output: str) -> List[Dict[str, str]]:
        """Process LLM output and extract report structure
        
        Args:
            output: LLM raw output
            
        Returns:
            Processed report structure list"""
        try:
            # Clean response text
            cleaned_output = remove_reasoning_from_output(output)
            cleaned_output = clean_json_tags(cleaned_output)
            
            # Logging cleaned output for debugging
            logger.info(f"Cleaned output: {cleaned_output}")
            
            # Parse JSON
            try:
                report_structure = json.loads(cleaned_output)
                logger.info("JSON parsed successfully")
            except JSONDecodeError as e:
                logger.error(f"JSON parsing failed: {str(e)}")
                # Use more powerful extraction methods
                report_structure = extract_clean_response(cleaned_output)
                if "error" in report_structure:
                    logger.error("JSON parsing failed, trying to fix...")
                    # Try to fix JSON
                    fixed_json = fix_incomplete_json(cleaned_output)
                    if fixed_json:
                        try:
                            report_structure = json.loads(fixed_json)
                            logger.info("JSON repair successful")
                        except JSONDecodeError:
                            logger.error("JSON repair failed")
                            # return default structure
                            return self._generate_default_structure()
                    else:
                        logger.error("Unable to fix JSON, using default structure")
                        return self._generate_default_structure()
            
            # Verify structure
            if not isinstance(report_structure, list):
                logger.info("Report structure is not a list, try converting...")
                if isinstance(report_structure, dict):
                    # If it is a single object, wrap it into a list
                    report_structure = [report_structure]
                else:
                    logger.exception("Invalid report structure format, using default structure")
                    return self._generate_default_structure()
            
            # Validate each paragraph
            validated_structure = []
            for i, paragraph in enumerate(report_structure):
                if not isinstance(paragraph, dict):
                    logger.warning(f"Paragraph {i+1} is not in dictionary format, skip")
                    continue
                
                title = paragraph.get("title", f"Paragraph {i+1}")
                content = paragraph.get("content", "")
                
                if not title or not content:
                    logger.warning(f"Paragraph {i+1} is missing title or content, skip")
                    continue
                
                validated_structure.append({
                    "title": title,
                    "content": content
                })
            
            if not validated_structure:
                logger.warning("No valid paragraph structure, use default structure")
                return self._generate_default_structure()
            
            logger.info(f"Successfully validated {len(validated_structure)} paragraph structures")
            return validated_structure
            
        except Exception as e:
            logger.exception(f"Failed to process output: {str(e)}")
            return self._generate_default_structure()
    
    def _generate_default_structure(self) -> List[Dict[str, str]]:
        """Generate default report structure
        
        Returns:
            Default report structure list"""
        logger.info("Generate default report structure")
        return [
            {
                "title": "Research overview",
                "content": "Provide a general overview and analysis of the query topic"
            },
            {
                "title": "In-depth analysis",
                "content": "In-depth analysis of all aspects of the query subject"
            }
        ]
    
    def mutate_state(self, input_data: Any = None, state: State = None, **kwargs) -> State:
        """Write report structure to status
        
        Args:
            input_data: input data
            state: current state, if None, create a new state
            **kwargs: additional parameters
            
        Returns:
            Updated status"""
        if state is None:
            state = State()
        
        try:
            # Generate report structure
            report_structure = self.run(input_data, **kwargs)
            
            # Set query and report titles
            state.query = self.query
            if not state.report_title:
                state.report_title = f"In-depth research report on '{self.query}'"
            
            # Add paragraph to status
            for paragraph_data in report_structure:
                state.add_paragraph(
                    title=paragraph_data["title"],
                    content=paragraph_data["content"]
                )
            
            logger.info(f"{len(report_structure)} paragraphs have been added to status")
            return state
            
        except Exception as e:
            logger.exception(f"Status update failed: {str(e)}")
            raise e
