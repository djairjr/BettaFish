"""node base class
Define the basic interface for all processing nodes"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from loguru import logger
from ..llms.base import LLMClient
from ..state.state import State


class BaseNode(ABC):
    """node base class"""

    def __init__(self, llm_client: LLMClient, node_name: str = ""):
        """Initialize node

        Args:
            llm_client: LLM client
            node_name: node name"""
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
        """Validate input data

        Args:
            input_data: input data

        Returns:
            Verification passed"""
        return True

    def process_output(self, output: Any) -> Any:
        """Process output data

        Args:
            output: raw output

        Returns:
            Processed output"""
        return output

    def log_info(self, message: str):
        """Record information log"""
        logger.info(f"[{self.node_name}] {message}")
    
    def log_warning(self, message: str):
        """Record warning log"""
        logger.warning(f"[{self.node_name}] warning: {message}")

    def log_error(self, message: str):
        """Record error log"""
        logger.error(f"[{self.node_name}] Error: {message}")


class StateMutationNode(BaseNode):
    """Node base class with status modification function"""
    
    @abstractmethod
    def mutate_state(self, input_data: Any, state: State, **kwargs) -> State:
        """Modify status
        
        Args:
            input_data: input data
            state: current state
            **kwargs: additional parameters
            
        Returns:
            modified status"""
        pass
