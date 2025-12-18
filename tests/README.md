# ForumEngine log parsing test

This test suite is used to test the log parsing function in `ForumEngine/monitor.py` and verify its correctness under different log formats.

## Test data

`forum_log_test_data.py` contains minimal examples of various log formats (forum log test data):

### Old format ([HH:MM:SS])
- `OLD_FORMAT_SINGLE_LINE_JSON`: Single line JSON
- `OLD_FORMAT_MULTILINE_JSON`: multi-line JSON
- `OLD_FORMAT_FIRST_SUMMARY`: Contains the log of FirstSummaryNode
- `OLD_FORMAT_REFLECTION_SUMMARY`: Contains the log of ReflectionSummaryNode

### New format (loguru default format)
- `NEW_FORMAT_SINGLE_LINE_JSON`: single line JSON
- `NEW_FORMAT_MULTILINE_JSON`: multi-line JSON
- `NEW_FORMAT_FIRST_SUMMARY`: contains the log of FirstSummaryNode
- `NEW_FORMAT_REFLECTION_SUMMARY`: Contains the log of ReflectionSummaryNode

### Complex example
- `COMPLEX_JSON_WITH_UPDATED`: JSON containing updated_paragraph_latest_state
- `COMPLEX_JSON_WITH_PARAGRAPH`: only the JSON of paragraph_latest_state
- `MIXED_FORMAT_LINES`: mixed format log lines

## Run the test

### Use pytest (recommended)

```bash
# Install pytest (if not installed yet)
pip install pytest

#Run all tests
pytest tests/test_monitor.py -v

#Run specific tests
pytest tests/test_monitor.py::TestLogMonitor::test_extract_json_content_new_format_multiline -v
```

### Run directly

```bash
python tests/test_monitor.py
```

## Test coverage

The tests cover the following functions:

1. **is_target_log_line**: Identify the target node log line
2. **is_json_start_line**: Identify JSON start line
3. **is_json_end_line**: Identify JSON end line
4. **extract_json_content**: Extract JSON content (single line and multi-line)
5. **format_json_content**: Format JSON content (extract updated_paragraph_latest_state first)
6. **extract_node_content**: Extract node content
7. **process_lines_for_json**: complete processing flow
8. **is_valuable_content**: Determine whether the content is valuable

## Anticipated issues

The current code may not handle the new loguru format correctly. The main problems are:

1. **Timestamp removal**: The regular `r'^\[\d{2}:\d{2}:\d{2}\]\s*'` in `extract_json_content()` can only match the `[HH:MM:SS]` format and cannot match loguru's `YYYY-MM-DD HH:mm:ss.SSS` format.

2. **Timestamp matching**: The regular `r'\[\d{2}:\d{2}:\d{2}\]\s*(.+)'` in `extract_node_content()` can also only match the old format

These tests will help identify these issues and guide subsequent code fixes.

