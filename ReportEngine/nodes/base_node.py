"""Report Engine node base class.

All high-order inference nodes inherit this, unified log, input verification and status change interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from ..llms.base import LLMClient
from ..state.state import ReportState
from loguru import logger

class BaseNode(ABC):
    """Node base class.

    Unified implementation of logging tools, input/output hooks and LLM client dependency injection,
    It is convenient for all nodes to focus only on business logic."""
    
    def __init__(self, llm_client: LLMClient, node_name: str = ""):
        """Initialize node
        
        Args:
            llm_client: LLM client
            node_name: node name

        BaseNode will save the node name to uniformly output log prefixes."""
        self.llm_client = llm_client
        self.node_name = node_name or self.__class__.__name__
    
    @abstractmethod
    def run(self, input_data: Any, **kwargs) -> Any:
        """Execute node processing logic
        
        Args:
            input_data: input data
            **kwargs: additional parameters
            
        Returns:
            Processing results"""
        pass
    
    def validate_input(self, input_data: Any) -> bool:
        """Validate input data.
        By default, it is passed directly, and subclasses can override it as needed to implement field checking.
        
        Args:
            input_data: input data
            
        Returns:
            Verification passed"""
        return True
    
    def process_output(self, output: Any) -> Any:
        """Process the output data.
        Subclasses can override for structuring or validation.
        
        Args:
            output: raw output
            
        Returns:
            Processed output"""
        return output
    
    def log_info(self, message: str):
        """Record information logs and automatically prefix them with the node name."""
        formatted_message = f"[{self.node_name}] {message}"
        logger.info(formatted_message)
    
    def log_error(self, message: str):
        """Record error logs to facilitate troubleshooting."""
        formatted_message = f"[{self.node_name}] {message}"
        logger.error(formatted_message)


class StateMutationNode(BaseNode):
    """Node base class with status modification function.

    Suitable for scenarios where nodes need to write ReportState directly."""
    
    @abstractmethod
    def mutate_state(self, input_data: Any, state: ReportState, **kwargs) -> ReportState:
        """Modify status.

        The subclass needs to return a new status object or modify it in place and then return it for pipeline recording.
        
        Args:
            input_data: input data
            state: current state
            **kwargs: additional parameters
            
        Returns:
            modified status"""
        pass
