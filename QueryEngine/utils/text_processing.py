"""Text processing tool functions
Used to clean LLM output, parse JSON, etc."""

import re
import json
from typing import Dict, Any, List
from json.decoder import JSONDecodeError


def clean_json_tags(text: str) -> str:
    """Clean JSON tags in text
    
    Args:
        text: original text
        
    Returns:
        Cleaned text"""
    # Remove ```json and ``` tags
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*$', '', text)
    text = re.sub(r'```', '', text)
    
    return text.strip()


def clean_markdown_tags(text: str) -> str:
    """Clean Markdown tags in text
    
    Args:
        text: original text
        
    Returns:
        Cleaned text"""
    # Remove ```markdown and ``` tags
    text = re.sub(r'```markdown\s*', '', text)
    text = re.sub(r'```\s*$', '', text)
    text = re.sub(r'```', '', text)
    
    return text.strip()


def remove_reasoning_from_output(text: str) -> str:
    """Remove inference process text from output
    
    Args:
        text: original text
        
    Returns:
        Cleaned text"""
    # Find where JSON starts
    json_start = -1
    
    # Try to find the first { or [
    for i, char in enumerate(text):
        if char in '{[':
            json_start = i
            break
    
    if json_start != -1:
        # Intercept from the beginning of JSON
        return text[json_start:].strip()
    
    # If no JSON tag is found, try other methods
    # Remove common inference flags
    patterns = [
        r'(?:reasoning|推理|思考|分析)[:：]\s*.*?(?=\{|\[)',  # Remove reasoning part
        r'(?:explanation|解释|说明)[:：]\s*.*?(?=\{|\[)',   # Remove explanation section
        r'^.*?(?=\{|\[)',  # Remove all text before JSON
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    
    return text.strip()


def extract_clean_response(text: str) -> Dict[str, Any]:
    """Extract and clean the JSON content in the response
    
    Args:
        text: original response text
        
    Returns:
        Parsed JSON dictionary"""
    # Clean text
    cleaned_text = clean_json_tags(text)
    cleaned_text = remove_reasoning_from_output(cleaned_text)
    
    # Try to parse directly
    try:
        return json.loads(cleaned_text)
    except JSONDecodeError:
        pass
    
    # Try to fix incomplete JSON
    fixed_text = fix_incomplete_json(cleaned_text)
    if fixed_text:
        try:
            return json.loads(fixed_text)
        except JSONDecodeError:
            pass
    
    # Try to find JSON object
    json_pattern = r'\{.*\}'
    match = re.search(json_pattern, cleaned_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except JSONDecodeError:
            pass
    
    # Trying to find a JSON array
    array_pattern = r'\[.*\]'
    match = re.search(array_pattern, cleaned_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except JSONDecodeError:
            pass
    
    # If all methods fail, return an error message
    print(f"Unable to parse JSON response: {cleaned_text[:200]}...")
    return {"error": "JSON parsing failed", "raw_text": cleaned_text}


def fix_incomplete_json(text: str) -> str:
    """Fix incomplete JSON response
    
    Args:
        text: original text
        
    Returns:
        The repaired JSON text, or an empty string if it cannot be repaired"""
    # Remove extra commas and whitespace
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)
    
    # Check if it is already valid JSON
    try:
        json.loads(text)
        return text
    except JSONDecodeError:
        pass
    
    # Check if starting array symbol is missing
    if text.strip().startswith('{') and not text.strip().startswith('['):
        # If starting with an object, try wrapping into an array
        if text.count('{') > 1:
            # Multiple objects, packed into arrays
            text = '[' + text + ']'
        else:
            # Single object, wrapped into an array
            text = '[' + text + ']'
    
    # Check if trailing array symbol is missing
    if text.strip().endswith('}') and not text.strip().endswith(']'):
        # If it ends with an object, try wrapping into an array
        if text.count('}') > 1:
            # Multiple objects, packed into arrays
            text = '[' + text + ']'
        else:
            # Single object, wrapped into an array
            text = '[' + text + ']'
    
    # Check if brackets match
    open_braces = text.count('{')
    close_braces = text.count('}')
    open_brackets = text.count('[')
    close_brackets = text.count(']')
    
    # Fix mismatched brackets
    if open_braces > close_braces:
        text += '}' * (open_braces - close_braces)
    if open_brackets > close_brackets:
        text += ']' * (open_brackets - close_brackets)
    
    # Verify that the repaired JSON is valid
    try:
        json.loads(text)
        return text
    except JSONDecodeError:
        # If that still doesn't work, try a more radical fix
        return fix_aggressive_json(text)


def fix_aggressive_json(text: str) -> str:
    """More radical JSON repair methods
    
    Args:
        text: original text
        
    Returns:
        Repaired JSON text"""
    # Find all possible JSON objects
    objects = re.findall(r'\{[^{}]*\}', text)
    
    if len(objects) >= 2:
        # If there are multiple objects, wrap them into arrays
        return '[' + ','.join(objects) + ']'
    elif len(objects) == 1:
        # If there is only one object, wrap it into an array
        return '[' + objects[0] + ']'
    else:
        # If no object is found, returns an empty array
        return '[]'


def update_state_with_search_results(search_results: List[Dict[str, Any]], 
                                   paragraph_index: int, state: Any) -> Any:
    """Update search results to status
    
    Args:
        search_results: search results list
        paragraph_index: paragraph index
        state: state object
        
    Returns:
        updated state object"""
    if 0 <= paragraph_index < len(state.paragraphs):
        # Get the last searched query (assuming it is the current query)
        current_query = ""
        if search_results:
            # Inferring queries from search results (needs improvement here to get actual queries)
            current_query = "search query"
        
        # Add search results to status
        state.paragraphs[paragraph_index].research.add_search_results(
            current_query, search_results
        )
    
    return state


def validate_json_schema(data: Dict[str, Any], required_fields: List[str]) -> bool:
    """Verify that JSON data contains required fields
    
    Args:
        data: data to be verified
        required_fields: list of required fields
        
    Returns:
        Verification passed"""
    return all(field in data for field in required_fields)


def truncate_content(content: str, max_length: int = 20000) -> str:
    """Truncate content to specified length
    
    Args:
        content: original content
        max_length: maximum length
        
    Returns:
        Truncated content"""
    if len(content) <= max_length:
        return content
    
    # Try truncation at word boundaries
    truncated = content[:max_length]
    last_space = truncated.rfind(' ')
    
    if last_space > max_length * 0.8:  # If the last space is in a reasonable position
        return truncated[:last_space] + "..."
    else:
        return truncated + "..."


def format_search_results_for_prompt(search_results: List[Dict[str, Any]], 
                                   max_length: int = 20000) -> List[str]:
    """Format search results for prompt words
    
    Args:
        search_results: search results list
        max_length: the maximum length of each result
        
    Returns:
        Formatted content list"""
    formatted_results = []
    
    for result in search_results:
        content = result.get('content', '')
        if content:
            truncated_content = truncate_content(content, max_length)
            formatted_results.append(truncated_content)
    
    return formatted_results
