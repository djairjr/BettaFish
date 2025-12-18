"""Report Engine status management
Define simplified status data structures during report generation"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import json
from datetime import datetime


@dataclass
class ReportMetadata:
    """Simplified reporting metadata"""
    query: str = ""                      # original query
    template_used: str = ""              # Template name to use
    generation_time: float = 0.0         # Generation time (seconds)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            "query": self.query,
            "template_used": self.template_used,
            "generation_time": self.generation_time,
            "timestamp": self.timestamp
        }


@dataclass 
class ReportState:
    """Simplified report status management.

    Store basic task information, input, output and metadata for sharing between Agent and Flask layer."""
    # Basic information
    task_id: str = ""                    # Task ID
    query: str = ""                      # original query
    status: str = "pending"              # Status: pending, processing, completed, failed
    
    # Enter data
    query_engine_report: str = ""        # QueryEngineReport
    media_engine_report: str = ""        # MediaEngineReport
    insight_engine_report: str = ""      # InsightEngineReport
    forum_logs: str = ""                 # Forum log
    
    # Processing results
    selected_template: str = ""          # Selected template
    html_content: str = ""               # final HTML content
    
    # metadata
    metadata: ReportMetadata = field(default_factory=ReportMetadata)
    
    def __post_init__(self):
        """Post-initialization processing"""
        if not self.task_id:
            self.task_id = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.metadata.query = self.query
    
    def mark_processing(self):
        """Marked as processing, the background thread starts scheduling the generation process."""
        self.status = "processing"
    
    def mark_completed(self):
        """Marked as complete, also means that `html_content` is available."""
        self.status = "completed"
    
    def mark_failed(self, error_message: str = ""):
        """Mark as failed and log the last error message."""
        self.status = "failed"
        self.error_message = error_message
    
    def is_completed(self) -> bool:
        """Checks for completion, including status as completed and presence of HTML content."""
        return self.status == "completed" and bool(self.html_content)
    
    def get_progress(self) -> float:
        """Get the progress percentage and make a rough estimate based on the two stages of template/content."""
        if self.status == "completed":
            return 100.0
        elif self.status == "processing":
            # Simple progress calculation
            progress = 0.0
            if self.selected_template:
                progress += 30.0
            if self.html_content:
                progress += 70.0
            return progress
        else:
            return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format to facilitate serialization to the front end."""
        return {
            "task_id": self.task_id,
            "query": self.query,
            "status": self.status,
            "progress": self.get_progress(),
            "selected_template": self.selected_template,
            "has_html_content": bool(self.html_content),
            "html_content_length": len(self.html_content) if self.html_content else 0,
            "metadata": self.metadata.to_dict()
        }
    
    def save_to_file(self, file_path: str):
        """Save state to file, excluding HTML body to control size."""
        try:
            state_data = self.to_dict()
            # Not saving full HTML content to state file (too large)
            state_data.pop("html_content", None)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to save state file: {str(e)}")
    
    @classmethod
    def load_from_file(cls, file_path: str) -> Optional["ReportState"]:
        """Load state from file, restoring only key fields for easy debugging."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Create ReportState object
            state = cls(
                task_id=data.get("task_id", ""),
                query=data.get("query", ""),
                status=data.get("status", "pending"),
                selected_template=data.get("selected_template", "")
            )
            
            # Set metadata
            metadata_data = data.get("metadata", {})
            state.metadata.template_used = metadata_data.get("template_used", "")
            state.metadata.generation_time = metadata_data.get("generation_time", 0.0)
            
            return state
            
        except Exception as e:
            print(f"Failed to load status file: {str(e)}")
            return None
