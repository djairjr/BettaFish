"""Log Monitor - Real-time monitoring of SummaryNode output in three log files"""

import os
import time
import threading
from pathlib import Path
from datetime import datetime
import re
import json
from typing import Dict, Optional, List
from threading import Lock
from loguru import logger

# Import forum moderator module
try:
    from .llm_host import generate_host_speech
    HOST_AVAILABLE = True
except ImportError:
    logger.exception("ForumEngine: The forum moderator module was not found and will be run in pure monitoring mode.")
    HOST_AVAILABLE = False

class LogMonitor:
    """Intelligent log monitor based on file changes"""
   
    def __init__(self, log_dir: str = "logs"):
        """Initialize log monitor"""
        self.log_dir = Path(log_dir)
        self.forum_log_file = self.log_dir / "forum.log"
       
        # Log files to monitor
        self.monitored_logs = {
            'insight': self.log_dir / 'insight.log',
            'media': self.log_dir / 'media.log',
            'query': self.log_dir / 'query.log'
        }
       
        # Monitor status
        self.is_monitoring = False
        self.monitor_thread = None
        self.file_positions = {}  # Record the reading position of each file
        self.file_line_counts = {}  # Record the number of lines in each file
        self.is_searching = False  # Are you searching
        self.search_inactive_count = 0  # Search for inactive counters
        self.write_lock = Lock()  # Write lock to prevent concurrent write conflicts
        
        # Moderator related status
        self.agent_speeches_buffer = []  # agent speech buffer
        self.host_speech_threshold = 5  # Every 5 agent statements trigger a moderator statement.
        self.is_host_generating = False  # Whether the moderator is generating a speech
       
        # Target node identification mode
        # 1. Class name (old format may contain)
        # 2. Full module path (actual log format, including engine prefix)
        # 3. Partial module paths (compatibility)
        # 4. Key identification text
        self.target_node_patterns = [
            'FirstSummaryNode',  # Class name
            'ReflectionSummaryNode',  # Class name
            'InsightEngine.nodes.summary_node',  # InsightEngine full path
            'MediaEngine.nodes.summary_node',  # MediaEngine full path
            'QueryEngine.nodes.summary_node',  # QueryEngine full path
            'nodes.summary_node',  # module path (compatibility, for partial matching)
            '正在生成首次段落总结',  # Identity of FirstSummaryNode
            '正在生成反思总结',  # Identity of ReflectionSummaryNode
        ]
        
        # Multi-line content capture status
        self.capturing_json = {}  # JSON capture status for each app
        self.json_buffer = {}     # JSON buffer per app
        self.json_start_line = {} # JSON starting line for each app
        self.in_error_block = {}  # Whether each app is in the ERROR block
       
        # Make sure the logs directory exists
        self.log_dir.mkdir(exist_ok=True)
   
    def clear_forum_log(self):
        """Clear the forum.log file"""
        try:
            if self.forum_log_file.exists():
                self.forum_log_file.unlink()
           
            # Create a new forum.log file and write the start tag
            start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # Use the write_to_forum_log function to write the start tag to ensure a consistent format
            with open(self.forum_log_file, 'w', encoding='utf-8') as f:
                pass  # Create an empty file first
            self.write_to_forum_log(f"=== ForumEngine monitoring starts - {start_time} ===", "SYSTEM")
               
            logger.info(f"ForumEngine: forum.log has been cleared and initialized")
            
            # Reset JSON capture status
            self.capturing_json = {}
            self.json_buffer = {}
            self.json_start_line = {}
            self.in_error_block = {}
            
            # Reset host related status
            self.agent_speeches_buffer = []
            self.is_host_generating = False
           
        except Exception as e:
            logger.exception(f"ForumEngine: Failed to clear forum.log: {e}")
   
    def write_to_forum_log(self, content: str, source: str = None):
        """Write content to forum.log (thread safe)"""
        try:
            with self.write_lock:  # Use locks to ensure thread safety
                with open(self.forum_log_file, 'a', encoding='utf-8') as f:
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    # Convert actual newlines in the content to \n strings, ensuring the entire record is on one line
                    content_one_line = content.replace('\n', '\\n').replace('\r', '\\r')
                    # If source tag is provided, appended after timestamp
                    if source:
                        f.write(f"[{timestamp}] [{source}] {content_one_line}\n")
                    else:
                        f.write(f"[{timestamp}] {content_one_line}\n")
                    f.flush()
        except Exception as e:
            logger.exception(f"ForumEngine: Failed to write to forum.log: {e}")
    
    def get_log_level(self, line: str) -> Optional[str]:
        """Detect the level of log lines (INFO/ERROR/WARNING/DEBUG, etc.)
        
        Support loguru format: YYYY-MM-DD HH:mm:ss.SSS | LEVEL | ...
        
        Returns:
            'INFO', 'ERROR', 'WARNING', 'DEBUG' or None (unrecognized)"""
        # Check the loguru format: YYYY-MM-DD HH:mm:ss.SSS | LEVEL | ...
        # Match pattern: | LEVEL | or | LEVEL |
        match = re.search(r'\|\s*(INFO|ERROR|WARNING|DEBUG|TRACE|CRITICAL)\s*\|', line)
        if match:
            return match.group(1)
        return None
    
    def is_target_log_line(self, line: str) -> bool:
        """Check if it is the target log line (SummaryNode)
        
        Supports multiple identification methods:
        1. Class name: FirstSummaryNode, ReflectionSummaryNode
        2. Complete module path: InsightEngine.nodes.summary_node, MediaEngine.nodes.summary_node, QueryEngine.nodes.summary_node
        3. Partial module path: nodes.summary_node (compatibility)
        4. Key identification text: The first paragraph summary is being generated, the reflection summary is being generated
        
        Exclusion criteria:
        - ERROR level logs (error logs should not be recognized as target nodes)
        - Logs containing error keywords (JSON parsing failure, JSON repair failure, etc.)"""
        # Exclude ERROR level logs
        log_level = self.get_log_level(line)
        if log_level == 'ERROR':
            return False
        
        # Compatible with old checking methods
        if "| ERROR" in line or "| ERROR    |" in line:
            return False
        
        # Exclude logs containing incorrect keywords
        error_keywords = ["JSON parsing failed", "JSON repair failed", "Traceback", "File \""]
        for keyword in error_keywords:
            if keyword in line:
                return False
        
        # Check if target node pattern is included
        for pattern in self.target_node_patterns:
            if pattern in line:
                return True
        return False
    
    def is_valuable_content(self, line: str) -> bool:
        """Determine whether it is valuable content (exclude short prompts and error messages)"""
        # Considered valuable if "cleaned output" is included则认为是有价值的
        if "Cleaned output" in line:
            return True
        
        # Exclude common short prompts and error messages
        exclude_patterns = [
            "JSON parsing failed",
            "JSON repair failed",
            "Use the cleaned text directly",
            "JSON parsed successfully",
            "Successfully generated",
            "Paragraph updated",
            "Generating",
            "Start processing",
            "Processing completed",
            "HOST statement has been read",
            "Failed to read HOST statement",
            "HOST speech not found",
            "debug output",
            "information record"
        ]
        
        for pattern in exclude_patterns:
            if pattern in line:
                return False
        
        # If the line length is too short, it is not considered valuable content.
        # Remove timestamp: support old and new formats
        clean_line = re.sub(r'\[\d{2}:\d{2}:\d{2}\]', '', line)
        clean_line = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s*\|\s*[A-Z]+\s*\|\s*[^|]+?\s*-\s*', '', clean_line)
        clean_line = clean_line.strip()
        if len(clean_line) < 30:  # Threshold can be adjusted
            return False
            
        return True
    
    def is_json_start_line(self, line: str) -> bool:
        """Determine whether it is the beginning line of JSON"""
        return "Cleaned output: {" in line
    
    def is_json_end_line(self, line: str) -> bool:
        """Determine whether it is the end of JSON line
        
        Only pure end tag lines are evaluated, without any log format information (timestamp, etc.).
        If the row contains a timestamp, it should be cleaned before judging, but returning False here indicates that further processing is required."""
        stripped = line.strip()
        
        # If the line contains a timestamp (old or new format), it is not a pure end line
        # Old format: [HH:MM:SS]
        if re.match(r'^\[\d{2}:\d{2}:\d{2}\]', stripped):
            return False
        # New format: YYYY-MM-DD HH:mm:ss.SSS
        if re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}', stripped):
            return False
        
        # Lines that do not contain a timestamp, check if they are pure closing tags
        if stripped == "}" or stripped == "] }":
            return True
        return False
    
    def extract_json_content(self, json_lines: List[str]) -> Optional[str]:
        """Extract and parse JSON content from multiple lines"""
        try:
            # Find where JSON starts
            json_start_idx = -1
            for i, line in enumerate(json_lines):
                if "Cleaned output: {" in line:
                    json_start_idx = i
                    break
            
            if json_start_idx == -1:
                return None
            
            # Extract JSON part
            first_line = json_lines[json_start_idx]
            json_start_pos = first_line.find("Cleaned output: {")
            if json_start_pos == -1:
                return None
            
            json_part = first_line[json_start_pos + len("Cleaned output:"):]
            
            # If the first line contains complete JSON, process it directly
            if json_part.strip().endswith("}") and json_part.count("{") == json_part.count("}"):
                try:
                    json_obj = json.loads(json_part.strip())
                    return self.format_json_content(json_obj)
                except json.JSONDecodeError:
                    # Single line JSON parsing failed, try to fix it
                    fixed_json = self.fix_json_string(json_part.strip())
                    if fixed_json:
                        try:
                            json_obj = json.loads(fixed_json)
                            return self.format_json_content(json_obj)
                        except json.JSONDecodeError:
                            pass
                    return None
            
            # Processing multi-line JSON
            json_text = json_part
            for line in json_lines[json_start_idx + 1:]:
                # Remove timestamp: support old format [HH:MM:SS] and new format loguru (YYYY-MM-DD HH:mm:ss.SSS | LEVEL | ...)
                # Old format: [HH:MM:SS]
                clean_line = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', line)
                # New format: Remove loguru format timestamp and level information
                # Format: YYYY-MM-DD HH:mm:ss.SSS | LEVEL | module:function:line -
                clean_line = re.sub(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s*\|\s*[A-Z]+\s*\|\s*[^|]+?\s*-\s*', '', clean_line)
                json_text += clean_line
            
            # Try to parse JSON
            try:
                json_obj = json.loads(json_text.strip())
                return self.format_json_content(json_obj)
            except json.JSONDecodeError:
                # Multi-line JSON parsing failed, try to fix it
                fixed_json = self.fix_json_string(json_text.strip())
                if fixed_json:
                    try:
                        json_obj = json.loads(fixed_json)
                        return self.format_json_content(json_obj)
                    except json.JSONDecodeError:
                        pass
                return None
            
        except Exception as e:
            # For other exceptions, no error message is printed and None is returned directly.
            return None
    
    def format_json_content(self, json_obj: dict) -> str:
        """Format JSON content into readable form"""
        try:
            # Extract the main content, give priority to reflection and summary, followed by the first summary
            content = None
            
            if "updated_paragraph_latest_state" in json_obj:
                content = json_obj["updated_paragraph_latest_state"]
            elif "paragraph_latest_state" in json_obj:
                content = json_obj["paragraph_latest_state"]
            
            # If the content is found, return directly (keep the newline character as \n)
            if content:
                return content
            
            # If the expected field is not found, returns a string representation of the entire JSON
            return f"Cleaned output: {json.dumps(json_obj, ensure_ascii=False, indent=2)}"
            
        except Exception as e:
            logger.exception(f"ForumEngine: Error formatting JSON: {e}")
            return f"Cleaned output: {json.dumps(json_obj, ensure_ascii=False, indent=2)}"

    def extract_node_content(self, line: str) -> Optional[str]:
        """Extract node content and remove prefixes such as timestamps and node names."""
        content = line
        
        # Remove timestamp part: support old and new formats
        # Old format: [HH:MM:SS]
        match_old = re.search(r'\[\d{2}:\d{2}:\d{2}\]\s*(.+)', content)
        if match_old:
            content = match_old.group(1).strip()
        else:
            # New format: YYYY-MM-DD HH:mm:ss.SSS | LEVEL | module:function:line -
            match_new = re.search(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s*\|\s*[A-Z]+\s*\|\s*[^|]+?\s*-\s*(.+)', content)
            if match_new:
                content = match_new.group(1).strip()
        
        if not content:
            return line.strip()
        
        # Remove all square bracket labels (including node names and application names)
        content = re.sub(r'^\[.*?\]\s*', '', content)
        
        # Continue removing possible multiple consecutive tags
        while re.match(r'^\[.*?\]\s*', content):
            content = re.sub(r'^\[.*?\]\s*', '', content)
        
        # Remove common prefixes (such as "first summary: ", "reflection summary: ", etc.)eflection summary:"等）
        prefixes_to_remove = [
            "First summary:",
            "Reflection summary:",
            "Cleaned output:"
        ]
        
        for prefix in prefixes_to_remove:
            if content.startswith(prefix):
                content = content[len(prefix):]
                break
        
        # Remove possible application name tags (those not enclosed in square brackets)
        app_names = ['INSIGHT', 'MEDIA', 'QUERY']
        for app_name in app_names:
            # Remove APP_NAME alone (at the beginning of the line)
            content = re.sub(rf'^{app_name}\s+', '', content, flags=re.IGNORECASE)
        
        # Clean up extra spaces
        content = re.sub(r'\s+', ' ', content)
        
        return content.strip()
   
    def get_file_size(self, file_path: Path) -> int:
        """Get file size"""
        try:
            return file_path.stat().st_size if file_path.exists() else 0
        except:
            return 0
   
    def get_file_line_count(self, file_path: Path) -> int:
        """Get the number of file lines"""
        try:
            if not file_path.exists():
                return 0
            with open(file_path, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f)
        except:
            return 0
   
    def read_new_lines(self, file_path: Path, app_name: str) -> List[str]:
        """Read new lines in file"""
        new_lines = []
       
        try:
            if not file_path.exists():
                return new_lines
           
            current_size = self.get_file_size(file_path)
            last_position = self.file_positions.get(app_name, 0)
           
            # If the file becomes smaller, it means it has been cleared and needs to start again from the beginning.
            if current_size < last_position:
                last_position = 0
                # Reset JSON capture status
                self.capturing_json[app_name] = False
                self.json_buffer[app_name] = []
                self.in_error_block[app_name] = False
           
            if current_size > last_position:
                with open(file_path, 'r', encoding='utf-8') as f:
                    f.seek(last_position)
                    new_content = f.read()
                    new_lines = new_content.split('\n')
                   
                    # Update location
                    self.file_positions[app_name] = f.tell()
                   
                    # Filter empty lines
                    new_lines = [line.strip() for line in new_lines if line.strip()]
                   
        except Exception as e:
            logger.exception(f"ForumEngine: Failed to read {app_name} log: {e}")
       
        return new_lines
   
    def process_lines_for_json(self, lines: List[str], app_name: str) -> List[str]:
        """Process rows to capture multiple lines of JSON content
        
        Implement ERROR block filtering: if an ERROR level log is encountered, processing will be refused until the next INFO level log is encountered."""
        captured_contents = []
        
        # initialization state
        if app_name not in self.capturing_json:
            self.capturing_json[app_name] = False
            self.json_buffer[app_name] = []
        if app_name not in self.in_error_block:
            self.in_error_block[app_name] = False
        
        for line in lines:
            if not line.strip():
                continue
            
            # First check the log level and update the ERROR block status
            log_level = self.get_log_level(line)
            if log_level == 'ERROR':
                # When ERROR is encountered, enter the ERROR block state
                self.in_error_block[app_name] = True
                # If JSON is being captured, stop immediately and clear the buffer
                if self.capturing_json[app_name]:
                    self.capturing_json[app_name] = False
                    self.json_buffer[app_name] = []
                # Skip the current line and do not process it
                continue
            elif log_level == 'INFO':
                # When INFO is encountered, exit the ERROR block state
                self.in_error_block[app_name] = False
            # Other levels (WARNING, DEBUG, etc.) remain in their current state
            
            # If inside an ERROR block, refuse to process everything
            if self.in_error_block[app_name]:
                # If JSON is being captured, stop immediately and clear the buffer
                if self.capturing_json[app_name]:
                    self.capturing_json[app_name] = False
                    self.json_buffer[app_name] = []
                # Skip the current line and do not process it
                continue
                
            # Check if it is target node row and JSON start tag
            is_target = self.is_target_log_line(line)
            is_json_start = self.is_json_start_line(line)
            
            # Only the JSON output of the target node (SummaryNode) should be captured
            # Filter out the output of other nodes such as SearchNode (they are not target nodes and will not be captured even if there is JSON)
            if is_target and is_json_start:
                # Start capturing JSON (must be the target node and contain "sanitized output: {")put: {"）
                self.capturing_json[app_name] = True
                self.json_buffer[app_name] = [line]
                self.json_start_line[app_name] = line
                
                # Check if it is single line JSON
                if line.strip().endswith("}"):
                    # Single line of JSON, processed immediately
                    content = self.extract_json_content([line])
                    if content:  # Only successfully parsed content will be recorded
                        # Remove duplicate tags and formatting
                        clean_content = self._clean_content_tags(content, app_name)
                        captured_contents.append(f"{clean_content}")
                    self.capturing_json[app_name] = False
                    self.json_buffer[app_name] = []
                    
            elif is_target and self.is_valuable_content(line):
                # Other valuable SummaryNode content (must be the target node and valuable)
                clean_content = self._clean_content_tags(self.extract_node_content(line), app_name)
                captured_contents.append(f"{clean_content}")
                    
            elif self.capturing_json[app_name]:
                # Capturing subsequent lines of JSON
                self.json_buffer[app_name].append(line)
                
                # Check if it ends with JSON
                # First clean the timestamp, and then determine whether the cleaned line is an end mark
                cleaned_line = line.strip()
                # Clean up old format timestamps: [HH:MM:SS]
                cleaned_line = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', cleaned_line)
                # Clean new format timestamp: YYYY-MM-DD HH:mm:ss.SSS | LEVEL | module:function:line -
                cleaned_line = re.sub(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s*\|\s*[A-Z]+\s*\|\s*[^|]+?\s*-\s*', '', cleaned_line)
                cleaned_line = cleaned_line.strip()
                
                # Determine whether it is an end tag after cleaning
                if cleaned_line == "}" or cleaned_line == "] }":
                    # JSON end, process the complete JSON
                    content = self.extract_json_content(self.json_buffer[app_name])
                    if content:  # Only successfully parsed content will be recorded
                        # Remove duplicate tags and formatting
                        clean_content = self._clean_content_tags(content, app_name)
                        captured_contents.append(f"{clean_content}")
                    
                    # reset state
                    self.capturing_json[app_name] = False
                    self.json_buffer[app_name] = []
        
        return captured_contents
    
    def _trigger_host_speech(self):
        """Trigger the host to speak (executed synchronously)"""
        if not HOST_AVAILABLE or self.is_host_generating:
            return
        
        try:
            # Set build flags
            self.is_host_generating = True
            
            # Get the 5 comments in the buffer
            recent_speeches = self.agent_speeches_buffer[:5]
            if len(recent_speeches) < 5:
                self.is_host_generating = False
                return
            
            logger.info("ForumEngine: Generating moderator's speech...")
            
            # Call the moderator to generate speeches (pass in the latest 5 messages)
            host_speech = generate_host_speech(recent_speeches)
            
            if host_speech:
                # Write the moderator's remarks to forum.log
                self.write_to_forum_log(host_speech, "HOST")
                logger.info(f"ForumEngine: The moderator’s speech has been recorded")
                
                # Clear 5 processed comments
                self.agent_speeches_buffer = self.agent_speeches_buffer[5:]
            else:
                logger.error("ForumEngine: Moderator speech generation failed")
            
            # Reset build flags
            self.is_host_generating = False
                
        except Exception as e:
            logger.exception(f"ForumEngine: Error triggering moderator to speak: {e}")
            self.is_host_generating = False
    
    def _clean_content_tags(self, content: str, app_name: str) -> str:
        """Clean up duplicate tags and redundant prefixes in content"""
        if not content:
            return content
            
        # First remove all possible tag formats (including [INSIGHT], [MEDIA], [QUERY], etc.)
        # Use more powerful cleaning methods
        all_app_names = ['INSIGHT', 'MEDIA', 'QUERY']
        
        for name in all_app_names:
            # Remove [APP_NAME] format (case insensitive)
            content = re.sub(rf'\[{name}\]\s*', '', content, flags=re.IGNORECASE)
            # Remove separate APP_NAME format
            content = re.sub(rf'^{name}\s+', '', content, flags=re.IGNORECASE)
        
        # Remove any other square bracket tags
        content = re.sub(r'^\[.*?\]\s*', '', content)
        
        # Remove possible duplicate spaces
        content = re.sub(r'\s+', ' ', content)
        
        return content.strip()
   
    def monitor_logs(self):
        """Intelligent monitoring log files"""
        logger.info("ForumEngine: Forum is being created...")
       
        # Initialization file line number and position - record current status as baseline
        for app_name, log_file in self.monitored_logs.items():
            self.file_line_counts[app_name] = self.get_file_line_count(log_file)
            self.file_positions[app_name] = self.get_file_size(log_file)
            self.capturing_json[app_name] = False
            self.json_buffer[app_name] = []
            self.in_error_block[app_name] = False
            # logger.info(f"ForumEngine: {app_name} Baseline line count: {self.file_line_counts[app_name]}")ts[app_name]}")
       
        while self.is_monitoring:
            try:
                # Detect changes in three log files simultaneously
                any_growth = False
                any_shrink = False
                captured_any = False
               
                # Process each log file independently
                for app_name, log_file in self.monitored_logs.items():
                    current_lines = self.get_file_line_count(log_file)
                    previous_lines = self.file_line_counts.get(app_name, 0)
                   
                    if current_lines > previous_lines:
                        any_growth = True
                        # Read new content now
                        new_lines = self.read_new_lines(log_file, app_name)
                       
                        # First check whether the search needs to be triggered (only trigger once)
                        if not self.is_searching:
                            for line in new_lines:
                                # Check if target node pattern is included (multiple formats supported)
                                if line.strip() and self.is_target_log_line(line):
                                    # Further confirm that it is the first summary node (FirstSummaryNode or contains "The first paragraph summary is being generated")irst paragraph summary"）
                                    if 'FirstSummaryNode' in line or '正在生成首次段落总结' in line:
                                        logger.info(f"ForumEngine: Detected first forum post in {app_name}")
                                        self.is_searching = True
                                        self.search_inactive_count = 0
                                        # Clear forum.log to start a new session
                                        self.clear_forum_log()
                                        break  # Just find one and break out of the loop
                       
                        # Process all new additions (if searching state is in progress)
                        if self.is_searching:
                            # Use new processing logic
                            captured_contents = self.process_lines_for_json(new_lines, app_name)
                            
                            for content in captured_contents:
                                # Convert app_name to uppercase as label (such as insight -> INSIGHT)
                                source_tag = app_name.upper()
                                self.write_to_forum_log(content, source_tag)
                                # logger.info(f"ForumEngine: Capture - {content}")nt}")
                                captured_any = True
                                
                                # Add utterances to buffer (formatted as full log lines)
                                timestamp = datetime.now().strftime('%H:%M:%S')
                                log_line = f"[{timestamp}] [{source_tag}] {content}"
                                self.agent_speeches_buffer.append(log_line)
                                
                                # Check whether the host needs to be triggered to speak
                                if len(self.agent_speeches_buffer) >= self.host_speech_threshold and not self.is_host_generating:
                                    # Synchronously trigger the host to speak
                                    self._trigger_host_speech()
                   
                    elif current_lines < previous_lines:
                        any_shrink = True
                        # logger.info(f"ForumEngine: {app_name} log shortening detected, baseline will be reset")etected, baseline will be reset")
                        # Reset file position to new end of file
                        self.file_positions[app_name] = self.get_file_size(log_file)
                        # Reset JSON capture status
                        self.capturing_json[app_name] = False
                        self.json_buffer[app_name] = []
                        self.in_error_block[app_name] = False
                   
                    # Update row count record
                    self.file_line_counts[app_name] = current_lines
               
                # Checks whether the current search session should be ended
                if self.is_searching:
                    if any_shrink:
                        # The log becomes shorter, ends the current search session, and resets to the waiting state.
                        # logger.info("ForumEngine: Shorten the log, end the current search session, and return to the waiting state")he current search session, and return to the waiting state")
                        self.is_searching = False
                        self.search_inactive_count = 0
                        # Reset host related status
                        self.agent_speeches_buffer = []
                        self.is_host_generating = False
                        # write end tag
                        end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        self.write_to_forum_log(f"=== ForumEngine Forum ends - {end_time} ===", "SYSTEM")
                        # logger.info("ForumEngine: The baseline has been reset, waiting for the next FirstSummaryNode trigger")aiting for the next FirstSummaryNode trigger")
                    elif not any_growth and not captured_any:
                        # No growth and no content captured, increasing the inactive count
                        self.search_inactive_count += 1
                        if self.search_inactive_count >= 7200:  # Automatically ends if there is no activity after timeout
                            logger.info("ForumEngine: No activity for a long time, end the forum")
                            self.is_searching = False
                            self.search_inactive_count = 0
                            # Reset host related status
                            self.agent_speeches_buffer = []
                            self.is_host_generating = False
                            # write end tag
                            end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            self.write_to_forum_log(f"=== ForumEngine Forum ends - {end_time} ===", "SYSTEM")
                    else:
                        self.search_inactive_count = 0  # reset counter
               
                # short sleep
                time.sleep(1)
               
            except Exception as e:
                logger.exception(f"ForumEngine: Error in forum record: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(2)
       
        logger.info("ForumEngine: Stop forum log file")
   
    def start_monitoring(self):
        """Start smart monitoring"""
        if self.is_monitoring:
            logger.info("ForumEngine: The forum is already running")
            return False
       
        try:
            # Start monitoring
            self.is_monitoring = True
            self.monitor_thread = threading.Thread(target=self.monitor_logs, daemon=True)
            self.monitor_thread.start()
           
            logger.info("ForumEngine: The forum has been started")
            return True
           
        except Exception as e:
            logger.exception(f"ForumEngine: Failed to start forum: {e}")
            self.is_monitoring = False
            return False
   
    def stop_monitoring(self):
        """Stop monitoring"""
        if not self.is_monitoring:
            logger.info("ForumEngine: Forum is not running")
            return
       
        try:
            self.is_monitoring = False
           
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=2)
           
            # write end tag
            end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.write_to_forum_log(f"=== ForumEngine Forum ends - {end_time} ===", "SYSTEM")
           
            logger.info("ForumEngine: Forum has stopped")
           
        except Exception as e:
            logger.exception(f"ForumEngine: Failed to stop forum: {e}")
   
    def get_forum_log_content(self) -> List[str]:
        """Get the contents of forum.log"""
        try:
            if not self.forum_log_file.exists():
                return []
           
            with open(self.forum_log_file, 'r', encoding='utf-8') as f:
                return [line.rstrip('\n\r') for line in f.readlines()]
               
        except Exception as e:
            logger.exception(f"ForumEngine: Failed to read forum.log: {e}")
            return []

    def fix_json_string(self, json_text: str) -> str:
        """Fix common issues in JSON strings, specifically unescaped double quotes"""
        try:
            # Try to parse directly and return the original text if successful
            json.loads(json_text)
            return json_text
        except json.JSONDecodeError:
            pass
        
        # Fix unescaped double quotes issue
        # Here's a smarter fix that specifically handles double quotes in string values
        
        try:
            # Fix JSON using state machine approach
            # Iterate over characters, keeping track of whether they are inside a string value
            
            fixed_text = ""
            i = 0
            in_string = False
            escape_next = False
            
            while i < len(json_text):
                char = json_text[i]
                
                if escape_next:
                    # Handling escape characters
                    fixed_text += char
                    escape_next = False
                    i += 1
                    continue
                
                if char == '\\':
                    # escape character
                    fixed_text += char
                    escape_next = True
                    i += 1
                    continue
                
                if char == '"' and not escape_next:
                    # encountered double quotes
                    if in_string:
                        # Inside the string, check for the next character
                        # If the next character is a colon, comma or brace, it means that this is the end of the string
                        next_char_pos = i + 1
                        while next_char_pos < len(json_text) and json_text[next_char_pos].isspace():
                            next_char_pos += 1
                        
                        if next_char_pos < len(json_text):
                            next_char = json_text[next_char_pos]
                            if next_char in [':', ',', '}']:
                                # This is the end of the string, exit string status
                                in_string = False
                                fixed_text += char
                            else:
                                # This is a quote inside the string and needs to be escaped
                                fixed_text += '\\"t += char
                            else:
                                # These are quotes inside the string and need to be escaped
                                fixed_text += '\\"'
                        else:
                            # End of file, exit string status
                            in_string = False
                            fixed_text += char
                    else:
                        # string start
                        in_string = True
                        fixed_text += char
                else:
                    # other characters
                    fixed_text += char
                
                i += 1
            
            # Try parsing the repaired JSON
            try:
                json.loads(fixed_text)
                return fixed_text
            except json.JSONDecodeError:
                # Repair fails and returns None
                return None
                
        except Exception:
            return None

# Global monitor instance
_monitor_instance = None

def get_monitor() -> LogMonitor:
    """Get global monitor instance"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = LogMonitor()
    return _monitor_instance

def start_forum_monitoring():
    """Start ForumEngine intelligent monitoring"""
    return get_monitor().start_monitoring()

def stop_forum_monitoring():
    """Stop ForumEngine monitoring"""
    get_monitor().stop_monitoring()

def get_forum_log():
    """Get forum.log content"""
    return get_monitor().get_forum_log_content()