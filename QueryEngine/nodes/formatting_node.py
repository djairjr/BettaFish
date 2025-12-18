"""report formatting node
Responsible for formatting final research results into beautiful Markdown reports"""

import json
from typing import List, Dict, Any

from .base_node import BaseNode
from loguru import logger
from ..prompts import SYSTEM_PROMPT_REPORT_FORMATTING
from ..utils.text_processing import (
    remove_reasoning_from_output,
    clean_markdown_tags
)


class ReportFormattingNode(BaseNode):
    """Node for formatting final report"""
    
    def __init__(self, llm_client):
        """Initialize report formatting node
        
        Args:
            llm_client: LLM client"""
        super().__init__(llm_client, "ReportFormattingNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                return isinstance(data, list) and all(
                    isinstance(item, dict) and "title" in item and "paragraph_latest_state" in item
                    for item in data
                )
            except:
                return False
        elif isinstance(input_data, list):
            return all(
                isinstance(item, dict) and "title" in item and "paragraph_latest_state" in item
                for item in input_data
            )
        return False
    
    def run(self, input_data: Any, **kwargs) -> str:
        """Call LLM to generate a Markdown format report
        
        Args:
            input_data: list containing all paragraph information
            **kwargs: additional parameters
            
        Returns:
            Formatted Markdown report"""
        try:
            if not self.validate_input(input_data):
                raise ValueError("The input data format is incorrect and a list containing title and paragraph_latest_state is required.")
            
            # Prepare to enter data
            if isinstance(input_data, str):
                message = input_data
            else:
                message = json.dumps(input_data, ensure_ascii=False)
            
            logger.info("Formatting final report")
            
            # Call LLM to generate Markdown format (streaming, safe splicing UTF-8)
            response = self.llm_client.stream_invoke_to_string(
                SYSTEM_PROMPT_REPORT_FORMATTING,
                message,
            )
            
            # Handle response
            processed_response = self.process_output(response)
            
            logger.info("Successfully generated formatted report")
            return processed_response
            
        except Exception as e:
            logger.exception(f"Report formatting failure: {str(e)}")
            raise e
    
    def process_output(self, output: str) -> str:
        """Process LLM output and clean up Markdown format
        
        Args:
            output: LLM raw output
            
        Returns:
            Cleaned Markdown report"""
        try:
            # Clean response text
            cleaned_output = remove_reasoning_from_output(output)
            cleaned_output = clean_markdown_tags(cleaned_output)
            
            # Make sure the report has a basic structure
            if not cleaned_output.strip():
                return "# Report generation failed\n\nValid report content cannot be generated."d\n\nValid report content could not be generated. "
            
            # If there is no title, add a default title
            if not cleaned_output.strip().startswith('#'):
                cleaned_output = "#In-depth research report\n\n"search report\n\n" + cleaned_output
            
            return cleaned_output.strip()
            
        except Exception as e:
            logger.exception(f"Failed to process output: {str(e)}")
            return "# Report processing failed\n\nAn error occurred during report formatting."\n\nAn error occurred during report formatting. "
    
    def format_report_manually(self, paragraphs_data: List[Dict[str, str]], 
                             report_title: str = "In-depth research report") -> str:
        """Format reports manually (alternative method)
        
        Args:
            paragraphs_data: paragraph data list
            report_title: report title
            
        Returns:
            Formatted Markdown report"""
        try:
            logger.info("Use manual formatting method")
            
            # Build report
            report_lines = [
                f"# {report_title}",
                "",
                "---",
                ""
            ]
            
            # Add individual paragraphs
            for i, paragraph in enumerate(paragraphs_data, 1):
                title = paragraph.get("title", f"Paragraph {i}")
                content = paragraph.get("paragraph_latest_state", "")
                
                if content:
                    report_lines.extend([
                        f"## {title}",
                        "",
                        content,
                        "",
                        "---",
                        ""
                    ])
            
            # Add conclusion
            if len(paragraphs_data) > 1:
                report_lines.extend([
                    "## in conclusion" conclusion",
                    "",
                    "This report provides a comprehensive analysis of relevant topics through in-depth search and research."
                    "The above aspects provide an important reference for understanding this topic.",
                    ""
                ])
            
            return "\n".join(report_lines)
            
        except Exception as e:
            logger.exception(f"Manual formatting failed: {str(e)}")
            return "# Report generation failed\n\nUnable to complete report formatting."led\n\nUnable to complete report formatting. "
