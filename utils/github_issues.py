"""GitHub Issues tool module

Provides the ability to create GitHub Issues URLs and display linked error messages
Data model definition location:
- No data model"""

from datetime import datetime
from urllib.parse import quote

# GitHub repository information
GITHUB_REPO = "666ghj/BettaFish"
GITHUB_ISSUES_URL = f"https://github.com/{GITHUB_REPO}/issues/new"


def create_issue_url(title: str, body: str = "") -> str:
    """Create a GitHub Issues URL, pre-populated with title and content
    
    Args:
        title: Issue title
        body: Issue content (optional)
    
    Returns:
        Full GitHub Issues URL"""
    encoded_title = quote(title)
    encoded_body = quote(body) if body else ""
    
    if encoded_body:
        return f"{GITHUB_ISSUES_URL}?title={encoded_title}&body={encoded_body}"
    else:
        return f"{GITHUB_ISSUES_URL}?title={encoded_title}"


def error_with_issue_link(
    error_message: str,
    error_details: str = "",
    app_name: str = "Streamlit App"
) -> str:
    """Generate error message string with link to GitHub Issues
    
    Only used in general exception handling, not for user configuration errors
    
    Args:
        error_message: error message
        error_details: error details (optional, used to fill in the Issue body)
        app_name: application name, used to identify the source of the error
    
    Returns:
        Markdown format string containing error message and link to GitHub Issues"""
    issue_title = f"[{app_name}] {error_message[:50]}"
    issue_body = f"## Error message\n\n{error_message}\n\n"sage}\n\n"
    
    if error_details:
        issue_body += f"## Error details\n\n```\n{error_details}\n```\n\n"\n```\n\n"
    
    issue_body += f"## Environment information\n\n- Application: {app_name}\n- Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"strftime('%Y-%m-%d %H:%M:%S')}"
    
    issue_url = create_issue_url(issue_title, issue_body)
    
    # Add hyperlinks using markdown format
    error_display = f"{error_message}\n\n[📝 Submit error report]({issue_url})"
    
    if error_details:
        error_display = f"{error_message}\n\n```\n{error_details}\n``\n\n[📝 Submit error report]({issue_url})"
    
    return error_display


__all__ = [
    "create_issue_url",
    "error_with_issue_link",
    "GITHUB_REPO",
    "GITHUB_ISSUES_URL",
]

