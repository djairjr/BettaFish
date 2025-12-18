"""Test the log parsing function in ForumEngine/monitor.py

Test the parsing capabilities in various log formats, including:
1. Old format: [HH:MM:SS]
2. New format: loguru default format (YYYY-MM-DD HH:mm:ss.SSS | LEVEL | ...)
3. Only the output of SummaryNode such as FirstSummaryNode and ReflectionSummaryNode should be received, and the output of SearchNode should not be received."""

import sys
from pathlib import Path

# Add project root directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ForumEngine.monitor import LogMonitor
from tests import forum_log_test_data as test_data


class TestLogMonitor:
    """Test the log parsing function of LogMonitor"""
    
    def setup_method(self):
        """Initialization before each test method"""
        self.monitor = LogMonitor(log_dir="tests/test_logs")
    
    def test_is_target_log_line_old_format(self):
        """Test target node recognition for old format"""
        # The line containing FirstSummaryNode should be recognized
        assert self.monitor.is_target_log_line(test_data.OLD_FORMAT_FIRST_SUMMARY) == True
        # The line containing ReflectionSummaryNode should be recognized
        assert self.monitor.is_target_log_line(test_data.OLD_FORMAT_REFLECTION_SUMMARY) == True
        # Non-target nodes should not be identified
        assert self.monitor.is_target_log_line(test_data.OLD_FORMAT_NON_TARGET) == False
    
    def test_is_target_log_line_new_format(self):
        """Test target node recognition for new format"""
        # The line containing FirstSummaryNode should be recognized
        assert self.monitor.is_target_log_line(test_data.NEW_FORMAT_FIRST_SUMMARY) == True
        # The line containing ReflectionSummaryNode should be recognized
        assert self.monitor.is_target_log_line(test_data.NEW_FORMAT_REFLECTION_SUMMARY) == True
        # Non-target nodes should not be identified
        assert self.monitor.is_target_log_line(test_data.NEW_FORMAT_NON_TARGET) == False
    
    def test_is_json_start_line_old_format(self):
        """Testing old format JSON start line recognition"""
        assert self.monitor.is_json_start_line(test_data.OLD_FORMAT_SINGLE_LINE_JSON) == True
        assert self.monitor.is_json_start_line(test_data.OLD_FORMAT_MULTILINE_JSON[0]) == True
        assert self.monitor.is_json_start_line(test_data.OLD_FORMAT_NON_TARGET) == False
    
    def test_is_json_start_line_new_format(self):
        """Testing JSON start line recognition for new format"""
        assert self.monitor.is_json_start_line(test_data.NEW_FORMAT_SINGLE_LINE_JSON) == True
        assert self.monitor.is_json_start_line(test_data.NEW_FORMAT_MULTILINE_JSON[0]) == True
        assert self.monitor.is_json_start_line(test_data.NEW_FORMAT_NON_TARGET) == False
    
    def test_is_json_end_line(self):
        """Test JSON end line recognition"""
        assert self.monitor.is_json_end_line("}") == True
        assert self.monitor.is_json_end_line("] }") == True
        assert self.monitor.is_json_end_line("[17:42:31] }") == False  # Need to clean timestamp first
        assert self.monitor.is_json_end_line("2025-11-05 17:42:31.289 | INFO | module:function:133 - }") == False  # Need to clean timestamp first
    
    def test_extract_json_content_old_format_single_line(self):
        """Testing old format single line JSON extraction"""
        lines = [test_data.OLD_FORMAT_SINGLE_LINE_JSON]
        result = self.monitor.extract_json_content(lines)
        assert result is not None
        assert "This is the first summary of the content" in result
    
    def test_extract_json_content_new_format_single_line(self):
        """Test new format single line JSON extraction"""
        lines = [test_data.NEW_FORMAT_SINGLE_LINE_JSON]
        result = self.monitor.extract_json_content(lines)
        assert result is not None
        assert "This is the first summary of the content" in result
    
    def test_extract_json_content_old_format_multiline(self):
        """Testing old format multi-line JSON extraction"""
        result = self.monitor.extract_json_content(test_data.OLD_FORMAT_MULTILINE_JSON)
        assert result is not None
        assert "multiple lines" in result
        assert "JSON content" in result
    
    def test_extract_json_content_new_format_multiline(self):
        """Test new format multi-line JSON extraction (support timestamp removal in loguru format)"""
        result = self.monitor.extract_json_content(test_data.NEW_FORMAT_MULTILINE_JSON)
        assert result is not None
        assert "multiple lines" in result
        assert "JSON content" in result
    
    def test_extract_json_content_updated_priority(self):
        """Test updated_paragraph_latest_state is extracted first"""
        result = self.monitor.extract_json_content(test_data.COMPLEX_JSON_WITH_UPDATED)
        assert result is not None
        assert "Updated version" in result
        assert "Core findings" in result
    
    def test_extract_json_content_paragraph_only(self):
        """Test the situation with only paragraph_latest_state"""
        result = self.monitor.extract_json_content(test_data.COMPLEX_JSON_WITH_PARAGRAPH)
        assert result is not None
        assert "First summary" in result or "Core findings" in result
    
    def test_format_json_content(self):
        """Test JSON content formatting"""
        # Test updated_paragraph_latest_state first
        json_obj = {
            "updated_paragraph_latest_state": "Updated content",
            "paragraph_latest_state": "First time content"
        }
        result = self.monitor.format_json_content(json_obj)
        assert result == "Updated content"
        
        # Test only paragraph_latest_state
        json_obj = {
            "paragraph_latest_state": "First time content"
        }
        result = self.monitor.format_json_content(json_obj)
        assert result == "First time content"
        
        # There are no tests
        json_obj = {"other_field": "Other content"}
        result = self.monitor.format_json_content(json_obj)
        assert "Cleaned output" in result
    
    def test_extract_node_content_old_format(self):
        """Test node content extraction for old format"""
        line = "[17:42:31] [INSIGHT] [FirstSummaryNode] Cleaned output: This is the test content"
        result = self.monitor.extract_node_content(line)
        assert result is not None
        assert "Test content" in result
    
    def test_extract_node_content_new_format(self):
        """Testing new format for node content extraction"""
        line = "2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - FirstSummaryNode cleaned output: This is the test content"
        result = self.monitor.extract_node_content(line)
        assert result is not None
        assert "Test content" in result
    
    def test_process_lines_for_json_old_format(self):
        """Test the complete processing flow of the old format"""
        lines = [
            test_data.OLD_FORMAT_NON_TARGET,  # should be ignored
            test_data.OLD_FORMAT_MULTILINE_JSON[0],
            test_data.OLD_FORMAT_MULTILINE_JSON[1],
            test_data.OLD_FORMAT_MULTILINE_JSON[2],
        ]
        result = self.monitor.process_lines_for_json(lines, "insight")
        assert len(result) > 0
        assert any("multiple lines" in content for content in result)
    
    def test_process_lines_for_json_new_format(self):
        """Complete processing flow for testing new formats"""
        lines = [
            test_data.NEW_FORMAT_NON_TARGET,  # should be ignored
            test_data.NEW_FORMAT_MULTILINE_JSON[0],
            test_data.NEW_FORMAT_MULTILINE_JSON[1],
            test_data.NEW_FORMAT_MULTILINE_JSON[2],
        ]
        result = self.monitor.process_lines_for_json(lines, "insight")
        assert len(result) > 0
        assert any("multiple lines" in content for content in result)
        assert any("JSON content" in content for content in result)
    
    def test_process_lines_for_json_mixed_format(self):
        """Test handling of mixed formats"""
        result = self.monitor.process_lines_for_json(test_data.MIXED_FORMAT_LINES, "insight")
        assert len(result) > 0
        assert any("Mixed format content" in content for content in result)
    
    def test_is_valuable_content(self):
        """Test judgments about valuable content"""
        # It should be valuable to include "cleaned output""应该是有价值的
        assert self.monitor.is_valuable_content(test_data.OLD_FORMAT_SINGLE_LINE_JSON) == True
        
        # Exclude short reminder messages
        assert self.monitor.is_valuable_content("JSON parsed successfully") == False
        assert self.monitor.is_valuable_content("Successfully generated") == False
        
        # Empty lines should be filtered
        assert self.monitor.is_valuable_content("") == False
    
    def test_extract_json_content_real_query_engine(self):
        """Test QueryEngine actual production environment log extraction"""
        result = self.monitor.extract_json_content(test_data.REAL_QUERY_ENGINE_REFLECTION)
        assert result is not None
        assert "Luoyang Luanchuan Molybdenum Group" in result
        assert "CMOC" in result
        assert "updated_paragraph_latest_state" not in result  # The content should have been extracted, excluding field names
    
    def test_extract_json_content_real_insight_engine(self):
        """Test InsightEngine actual production environment log extraction (including identification lines)"""
        # First test whether the identification line can be recognized
        assert self.monitor.is_target_log_line(test_data.REAL_INSIGHT_ENGINE_REFLECTION[0]) == True  # Contains "Generating reflection summary"g reflection summary"
        assert self.monitor.is_target_log_line(test_data.REAL_INSIGHT_ENGINE_REFLECTION[1]) == True  # Contains nodes.summary_node
        
        # Test JSON extraction (start with the second line since the first is the identification line)
        json_lines = test_data.REAL_INSIGHT_ENGINE_REFLECTION[1:]  # Skip identification line
        result = self.monitor.extract_json_content(json_lines)
        assert result is not None
        assert "Core findings" in result
        assert "Updated version" in result
        assert "CMOC third quarter 2025" in result
    
    def test_extract_json_content_real_media_engine(self):
        """Test MediaEngine actual production environment log extraction (single line JSON)"""
        # MediaEngine is a single-line JSON format and needs to be split into lines first.
        lines = test_data.REAL_MEDIA_ENGINE_REFLECTION.split('\n')
        
        # Test whether the identification line can be recognized
        assert self.monitor.is_target_log_line(lines[0]) == True  # Contains "Generating reflection summary"g reflection summary"
        assert self.monitor.is_target_log_line(lines[1]) == True  # Contains nodes.summary_node and "cleaned output" output"
        
        # Test JSON extraction (start with the line containing JSON)
        json_line = lines[1]  # The second line contains the complete single line JSON
        result = self.monitor.extract_json_content([json_line])
        assert result is not None
        assert "Comprehensive information overview" in result
        assert "CMOC" in result
        assert "updated_paragraph_latest_state" not in result  # The content should have been extracted
    
    def test_process_lines_for_json_real_query_engine(self):
        """Test the complete processing flow of QueryEngine’s actual logs"""
        result = self.monitor.process_lines_for_json(test_data.REAL_QUERY_ENGINE_REFLECTION, "query")
        assert len(result) > 0
        assert any("Luoyang Luanchuan Molybdenum Group" in content for content in result)
    
    def test_process_lines_for_json_real_insight_engine(self):
        """Test the complete processing flow of InsightEngine's actual logs (including identification lines)"""
        result = self.monitor.process_lines_for_json(test_data.REAL_INSIGHT_ENGINE_REFLECTION, "insight")
        assert len(result) > 0
        assert any("Core findings" in content for content in result)
        assert any("Updated version" in content for content in result)
    
    def test_process_lines_for_json_real_media_engine(self):
        """Test the complete processing flow of MediaEngine’s actual logs (single line JSON)"""
        # Split a single line string into multiple lines
        lines = test_data.REAL_MEDIA_ENGINE_REFLECTION.split('\n')
        result = self.monitor.process_lines_for_json(lines, "media")
        assert len(result) > 0
        assert any("Comprehensive information overview" in content for content in result)
        assert any("CMOC" in content for content in result)
    
    def test_filter_search_node_output(self):
        """Test filtering the output of SearchNode (Important: SearchNode should not enter the forum)"""
        # SearchNode's output contains "Cleaned output: {" but not the target node pattern包含目标节点模式
        search_lines = test_data.SEARCH_NODE_FIRST_SEARCH
        result = self.monitor.process_lines_for_json(search_lines, "insight")
        # The output of SearchNode should be filtered and should not be captured
        assert len(result) == 0
    
    def test_filter_search_node_output_single_line(self):
        """Test filtering single line JSON output of SearchNode"""
        # Single line JSON format for SearchNode
        search_line = test_data.SEARCH_NODE_REFLECTION_SEARCH
        result = self.monitor.process_lines_for_json([search_line], "insight")
        # The output of SearchNode should be filtered
        assert len(result) == 0
    
    def test_search_node_vs_summary_node_mixed(self):
        """Test mixed scenario: SearchNode and SummaryNode exist at the same time, only SummaryNode is captured"""
        lines = [
            # SearchNode output (should be filtered)
            "[11:16:35] 2025-11-06 11:16:35.567 | INFO | InsightEngine.nodes.search_node:process_output:97 - Cleaned output: {",
            "[11:16:35] \"search_query\": \"Test query\"",
            "[11:16:35] }",
            # SummaryNode output (should be captured)
            "[11:17:05] 2025-11-06 11:17:05.547 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
            "[11:17:05] \"paragraph_latest_state\": \"This is the summary\"",
            "[11:17:05] }",
        ]
        result = self.monitor.process_lines_for_json(lines, "insight")
        # Only the output of SummaryNode should be captured, not the output of SearchNode
        assert len(result) > 0
        assert any("Summary content" in content for content in result)
        # Make sure you don't include search queries
        assert not any("search_query" in content for content in result)
        assert not any("Test query" in content for content in result)
    
    def test_filter_error_logs_from_summary_node(self):
        """Test filtering the error log of SummaryNode (Important: error logs should not enter the forum)"""
        # JSON parsing failure error log
        assert self.monitor.is_target_log_line(test_data.SUMMARY_NODE_JSON_ERROR) == False
        
        # JSON repair failure error log
        assert self.monitor.is_target_log_line(test_data.SUMMARY_NODE_JSON_FIX_ERROR) == False
        
        # ERROR level log
        assert self.monitor.is_target_log_line(test_data.SUMMARY_NODE_ERROR_LOG) == False
        
        # Traceback error log
        for line in test_data.SUMMARY_NODE_TRACEBACK.split('\n'):
            assert self.monitor.is_target_log_line(line) == False
    
    def test_error_logs_not_captured(self):
        """Test error logs are not captured to the forum"""
        error_lines = [
            test_data.SUMMARY_NODE_JSON_ERROR,
            test_data.SUMMARY_NODE_JSON_FIX_ERROR,
            test_data.SUMMARY_NODE_ERROR_LOG,
        ]
        
        for line in error_lines:
            result = self.monitor.process_lines_for_json([line], "media")
            # Error logs should not be captured
            assert len(result) == 0
    
    def test_mixed_valid_and_error_logs(self):
        """Test mixed scenario: valid logs and error logs exist at the same time, only valid logs are captured"""
        lines = [
            # Error log (should be filtered)
            test_data.SUMMARY_NODE_JSON_ERROR,
            test_data.SUMMARY_NODE_JSON_FIX_ERROR,
            # Valid SummaryNode output (should be captured)
            "[11:55:31] 2025-11-06 11:55:31.762 | INFO | MediaEngine.nodes.summary_node:process_output:134 - Cleaned output: {",
            "[11:55:31] \"paragraph_latest_state\": \"This is a valid summary\"",
            "[11:55:31] }",
        ]
        result = self.monitor.process_lines_for_json(lines, "media")
        # Only valid logs should be captured, not error logs
        assert len(result) > 0
        assert any("Effective summary content" in content for content in result)
        # Make sure there are no error messages
        assert not any("JSON parsing failed" in content for content in result)
        assert not any("JSON repair failed" in content for content in result)


def run_tests():
    """Run all tests"""
    import pytest
    
    # Run tests
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    run_tests()

