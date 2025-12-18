"""Template selection node.

Comprehensive user query, three-engine report, forum log and local template library,
Call LLM to select the most appropriate report skeleton."""

import os
import json
from typing import Dict, Any, List, Optional
from loguru import logger

from .base_node import BaseNode
from ..prompts import SYSTEM_PROMPT_TEMPLATE_SELECTION
from ..utils.json_parser import RobustJSONParser, JSONParseError


class TemplateSelectionNode(BaseNode):
    """Template selection processing node.

    Responsible for preparing template candidate lists, constructing prompt words, and parsing LLM return results.
    and fall back to built-in templates on failure."""
    
    def __init__(self, llm_client, template_dir: str = "ReportEngine/report_template"):
        """Initialize template selection node

        Args:
            llm_client: LLM client
            template_dir: template directory path"""
        super().__init__(llm_client, "TemplateSelectionNode")
        self.template_dir = template_dir
        # Initialize robust JSON parser, enable all repair strategies
        self.json_parser = RobustJSONParser(
            enable_json_repair=True,
            enable_llm_repair=False,
            max_repair_attempts=3,
        )
        
    def run(self, input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Perform template selection.
        
        Args:
            input_data: dictionary containing query and report content
                - query: original query
                - reports: report list of three sub-agents
                - forum_logs: Forum log content
                
        Returns:
            Selected template information, including name, content and reason for selection"""
        logger.info("Start template selection...")
        
        query = input_data.get('query', '')
        reports = input_data.get('reports', [])
        forum_logs = input_data.get('forum_logs', '')
        
        # Get available templates
        available_templates = self._get_available_templates()
        
        if not available_templates:
            logger.info("No preset template found, use built-in default template")
            return self._get_fallback_template()
        
        # Using LLM for template selection
        try:
            llm_result = self._llm_template_selection(query, reports, forum_logs, available_templates)
            if llm_result:
                return llm_result
        except Exception as e:
            logger.exception(f"LLM template selection failed: {str(e)}")
        
        # If LLM selection fails, use alternatives
        return self._get_fallback_template()
    

    
    def _llm_template_selection(self, query: str, reports: List[Any], forum_logs: str, 
                              available_templates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Use LLM for template selection.

        Construct template list and report summary → Call LLM → Parse JSON →
        Verify that the template exists and return the standard structure.

        Parameters:
            query: the keyword entered by the user.
            reports: Report content of multiple analysis engines.
            forum_logs: Forum logs, may be empty.
            available_templates: List of locally available templates.

        Return:
            dict | None: Contains template information if LLM successfully returns a legal result, otherwise None."""
        logger.info("Try using LLM for template selection...")
        
        # Build template list
        template_list = "\n".join([f"- {t['name']}: {t['description']}" for t in available_templates])
        
        # Build a report summary
        reports_summary = ""
        if reports:
            reports_summary = "\n\n=== Analysis engine report content ===\n"
            for i, report in enumerate(reports, 1):
                # Get report content and support different data formats
                if isinstance(report, dict):
                    content = report.get('content', str(report))
                elif hasattr(report, 'content'):
                    content = report.content
                else:
                    content = str(report)
                
                # Truncate overly long content and keep the first 1000 characters
                if len(content) > 1000:
                    content = content[:1000] + "...(Content has been truncated)"
                
                reports_summary += f"\nReport{i}content:\n{content}\n"
        
        # Build forum log summary
        forum_summary = ""
        if forum_logs and forum_logs.strip():
            forum_summary = "\n\n=== Discussion content of three engines ===\n"
            # Truncate overly long log content and retain the first 800 characters
            if len(forum_logs) > 800:
                forum_content = forum_logs[:800] + "...(discussion has been truncated)"
            else:
                forum_content = forum_logs
            forum_summary += forum_content
        
        user_message = f"""Query content: {query}

Number of reports: {len(reports)} analytics engine reports
Forum logs: {'yes' if forum_logs else 'no'}
{reports_summary}{forum_summary}

Available templates:
{template_list}

Please choose the most appropriate template based on the query content, report content, and forum logs."""
        
        # Call LLM
        response = self.llm_client.stream_invoke_to_string(SYSTEM_PROMPT_TEMPLATE_SELECTION, user_message)

        # Check if the response is empty
        if not response or not response.strip():
            logger.error("LLM returns empty response")
            return None

        logger.info(f"LLM original response: {response}")

        # Try parsing the JSON response, using a robust parser
        try:
            result = self.json_parser.parse(
                response,
                context_name="Template selection",
                expected_keys=["template_name", "selection_reason"],
            )

            # Verify that the selected template exists
            selected_template_name = result.get('template_name', '')
            for template in available_templates:
                if template['name'] == selected_template_name or selected_template_name in template['name']:
                    logger.info(f"LLM selection template: {selected_template_name}")
                    return {
                        'template_name': template['name'],
                        'template_content': template['content'],
                        'selection_reason': result.get('selection_reason', 'LLM智能选择')
                    }

            logger.error(f"The template selected by LLM does not exist: {selected_template_name}")
            return None

        except JSONParseError as e:
            logger.error(f"JSON parsing failed: {str(e)}")
            # Try to extract template information from text response
            return self._extract_template_from_text(response, available_templates)
    

    def _extract_template_from_text(self, response: str, available_templates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Extract template information from text responses.

        When LLM does not output valid JSON, it tries to downgrade by matching the template name keyword.

        Parameters:
            response: unstructured LLM text.
            available_templates: List of optional templates.

        Return:
            dict | None: Returns the template details if the match is successful, otherwise None."""
        logger.info("Try to extract template information from text response")
        
        # Find if the template name is included in the response
        for template in available_templates:
            template_name_variants = [
                template['name'],
                template['name'].replace('.md', ''),
                template['name'].replace('模板', ''),
            ]
            
            for variant in template_name_variants:
                if variant in response:
                    logger.info(f"Template found in response: {template['name']}")
                    return {
                        'template_name': template['name'],
                        'template_content': template['content'],
                        'selection_reason': '从文本响应中提取'
                    }
        
        return None
    
    def _get_available_templates(self) -> List[Dict[str, Any]]:
        """Get a list of available templates.

        Enumerate the `.md` files in the template directory and read the content and description fields.

        Return:
            list[dict]: Each item contains name/path/content/description."""
        templates = []
        
        if not os.path.exists(self.template_dir):
            logger.error(f"Template directory does not exist: {self.template_dir}")
            return templates
        
        # Find all markdown template files
        for filename in os.listdir(self.template_dir):
            if filename.endswith('.md'):
                template_path = os.path.join(self.template_dir, filename)
                try:
                    with open(template_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    template_name = filename.replace('.md', '')
                    description = self._extract_template_description(template_name)
                    
                    templates.append({
                        'name': template_name,
                        'path': template_path,
                        'content': content,
                        'description': description
                    })
                except Exception as e:
                    logger.exception(f"Failed to read template file {filename}: {str(e)}")
        
        return templates
    
    def _extract_template_description(self, template_name: str) -> str:
        """Generate a description based on the template name to facilitate LLM's understanding of template positioning."""
        if '企业品牌' in template_name:
            return "Suitable for corporate brand reputation and image analysis"
        elif '市场竞争' in template_name:
            return "Suitable for market competition landscape and opponent analysis"
        elif '日常' in template_name or '定期' in template_name:
            return "Suitable for daily monitoring and regular reporting"
        elif '政策' in template_name or '行业' in template_name:
            return "Suitable for policy impact and industry dynamics analysis"
        elif '热点' in template_name or '社会' in template_name:
            return "Suitable for analysis of social hot spots and public events"
        elif '突发' in template_name or '危机' in template_name:
            return "Suitable for emergencies and crisis public relations"
        
        return "Generic report template"
    

    
    def _get_fallback_template(self) -> Dict[str, Any]:
        """Get an alternate default template (empty template, let LLM do its thing).

        Return:
            dict: The structure field is consistent with the LLM return, making it easy to replace directly."""
        logger.info("No suitable template found, use empty template to let LLM play its role")
        
        return {
            'template_name': '自由发挥模板',
            'template_content': '',
            'selection_reason': '未找到合适的预设模板，让LLM根据内容自行设计报告结构'
        }
