"""Forum log reading tool
Used to read the latest HOST statements in forum.log"""

import re
from pathlib import Path
from typing import Optional, List, Dict
from loguru import logger

def get_latest_host_speech(log_dir: str = "logs") -> Optional[str]:
    """Get the latest HOST statement in forum.log
    
    Args:
        log_dir: log directory path
        
    Returns:
        The latest HOST speech content, if there is none, return None"""
    try:
        forum_log_path = Path(log_dir) / "forum.log"
        
        if not forum_log_path.exists():
            logger.debug("forum.log file does not exist")
            return None
            
        with open(forum_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        # Find the latest HOST statements from back to front
        host_speech = None
        for line in reversed(lines):
            # Match format: [time] [HOST] content
            match = re.match(r'\[(\d{2}:\d{2}:\d{2})\]\s*\[HOST\]\s*(.+)', line)
            if match:
                _, content = match.groups()
                # Handle escaped newlines, reverting to actual newlines
                host_speech = content.replace('\\n', '\n').strip()
                break
        
        if host_speech:
            logger.info(f"Find the latest HOST speech, length: {len(host_speech)} characters")
        else:
            logger.debug("HOST speech not found")
            
        return host_speech
        
    except Exception as e:
        logger.error(f"Failed to read forum.log: {str(e)}")
        return None


def get_all_host_speeches(log_dir: str = "logs") -> List[Dict[str, str]]:
    """Get all HOST comments in forum.log
    
    Args:
        log_dir: log directory path
        
    Returns:
        A list containing all HOST statements, each element is a dictionary containing timestamp and content"""
    try:
        forum_log_path = Path(log_dir) / "forum.log"
        
        if not forum_log_path.exists():
            logger.debug("forum.log file does not exist")
            return []
            
        with open(forum_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        host_speeches = []
        for line in lines:
            # Match format: [time] [HOST] content
            match = re.match(r'\[(\d{2}:\d{2}:\d{2})\]\s*\[HOST\]\s*(.+)', line)
            if match:
                timestamp, content = match.groups()
                # Handling escaped newlines
                content = content.replace('\\n', '\n').strip()
                host_speeches.append({
                    'timestamp': timestamp,
                    'content': content
                })
        
        logger.info(f"Found {len(host_speeches)} HOST speeches")
        return host_speeches
        
    except Exception as e:
        logger.error(f"Failed to read forum.log: {str(e)}")
        return []


def get_recent_agent_speeches(log_dir: str = "logs", limit: int = 5) -> List[Dict[str, str]]:
    """Get the latest Agent statement in forum.log (excluding HOST)
    
    Args:
        log_dir: log directory path
        limit: the maximum number of comments returned
        
    Returns:
        Contains a list of recent Agent statements"""
    try:
        forum_log_path = Path(log_dir) / "forum.log"
        
        if not forum_log_path.exists():
            return []
            
        with open(forum_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        agent_speeches = []
        for line in reversed(lines):  # Read from back to front
            # Match format: [time] [AGENT_NAME] content
            match = re.match(r'\[(\d{2}:\d{2}:\d{2})\]\s*\[(INSIGHT|MEDIA|QUERY)\]\s*(.+)', line)
            if match:
                timestamp, agent, content = match.groups()
                # Handling escaped newlines
                content = content.replace('\\n', '\n').strip()
                agent_speeches.append({
                    'timestamp': timestamp,
                    'agent': agent,
                    'content': content
                })
                if len(agent_speeches) >= limit:
                    break
        
        agent_speeches.reverse()  # Restoration time sequence
        return agent_speeches
        
    except Exception as e:
        logger.error(f"Failed to read forum.log: {str(e)}")
        return []


def format_host_speech_for_prompt(host_speech: str) -> str:
    """Format HOST speech for adding to prompt
    
    Args:
        host_speech: HOST speech content
        
    Returns:
        Formatted content"""
    if not host_speech:
        return ""
    
    return f"""### The latest summary of the forum moderator
The following is the forum moderator’s latest summary and guidance on various Agent discussions. Please refer to the views and suggestions:

{host_speech}

---"参考其中的观点和建议：

{host_speech}

---
"""
