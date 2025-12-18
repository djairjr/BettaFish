"""Report Engine's default OpenAI compatible LLM client package.

Provides unified non-streaming/streaming calls, optional retry, byte-safe splicing and model meta-information query."""

import os
import sys
from typing import Any, Dict, Optional, Generator
from loguru import logger

from openai import OpenAI

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
utils_dir = os.path.join(project_root, "utils")
if utils_dir not in sys.path:
    sys.path.append(utils_dir)

try:
    from retry_helper import with_retry, LLM_RETRY_CONFIG
except ImportError:
    def with_retry(config=None):
        """Simplified version of with_retry placeholder to achieve a call signature consistent with the real decorator"""
        def decorator(func):
            """Return the original function directly to ensure that the code can still run without retry dependencies"""
            return func
        return decorator

    LLM_RETRY_CONFIG = None


class LLMClient:
    """For lightweight encapsulation of OpenAI Chat Completion API, unified Report Engine call entry."""

    def __init__(self, api_key: str, model_name: str, base_url: Optional[str] = None):
        """Initialize the LLM client and save basic connection information.

        Args:
            api_key: API Token used for authentication
            model_name: specific model ID, used to locate supplier capabilities
            base_url: Custom compatible interface address, the default is OpenAI official"""
        if not api_key:
            raise ValueError("Report Engine LLM API key is required.")
        if not model_name:
            raise ValueError("Report Engine model name is required.")

        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.provider = model_name
        timeout_fallback = os.getenv("LLM_REQUEST_TIMEOUT") or os.getenv("REPORT_ENGINE_REQUEST_TIMEOUT") or "3000"
        try:
            self.timeout = float(timeout_fallback)
        except ValueError:
            self.timeout = 3000.0

        client_kwargs: Dict[str, Any] = {
            "api_key": api_key,
            "max_retries": 0,
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)

    @with_retry(LLM_RETRY_CONFIG)
    def invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """Calls LLM in a non-streaming manner and returns a complete response in one go.

        Args:
            system_prompt: system role prompt
            user_prompt: user high priority command
            **kwargs: allows transparent transmission of sampling parameters such as temperature/top_p

        Returns:
            LLM response text after removing leading and trailing whitespace"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        allowed_keys = {"temperature", "top_p", "presence_penalty", "frequency_penalty", "stream"}
        extra_params = {key: value for key, value in kwargs.items() if key in allowed_keys and value is not None}

        timeout = kwargs.pop("timeout", self.timeout)

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            timeout=timeout,
            **extra_params,
        )

        if response.choices and response.choices[0].message:
            return self.validate_response(response.choices[0].message.content)
        return ""

    def stream_invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> Generator[str, None, None]:
        """Call LLM in a streaming manner and gradually return the response content.
        
        Parameters:
            system_prompt: system prompt word.
            user_prompt: user prompt word.
            **kwargs: Sampling parameters (temperature, top_p, etc.).
            
        Output:
            str: Yield a piece of delta text each time to facilitate real-time rendering by the upper layer."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        allowed_keys = {"temperature", "top_p", "presence_penalty", "frequency_penalty"}
        extra_params = {key: value for key, value in kwargs.items() if key in allowed_keys and value is not None}
        # Force streaming
        extra_params["stream"] = True

        timeout = kwargs.pop("timeout", self.timeout)

        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                timeout=timeout,
                **extra_params,
            )
            
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
        except Exception as e:
            logger.error(f"Streaming request failed: {str(e)}")
            raise e
    
    @with_retry(LLM_RETRY_CONFIG)
    def stream_invoke_to_string(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """Streaming calls to LLM and safe concatenation into complete strings (avoiding UTF-8 multibyte character truncation).
        
        Parameters:
            system_prompt: system prompt word.
            user_prompt: user prompt word.
            **kwargs: Sampling or timeout configuration.
            
        Return:
            str: The complete response after concatenating all deltas."""
        # Collect all blocks in bytes
        byte_chunks = []
        for chunk in self.stream_invoke(system_prompt, user_prompt, **kwargs):
            byte_chunks.append(chunk.encode('utf-8'))
        
        # Concatenate all bytes and decode them in one go
        if byte_chunks:
            return b''.join(byte_chunks).decode('utf-8', errors='replace')
        return ""

    @staticmethod
    def validate_response(response: Optional[str]) -> str:
        """Handle None/blank strings to prevent upper-layer logic from collapsing"""
        if response is None:
            return ""
        return response.strip()

    def get_model_info(self) -> Dict[str, Any]:
        """Returns the current client's model/provider/base URL information in dictionary form"""
        return {
            "provider": self.provider,
            "model": self.model_name,
            "api_base": self.base_url or "default",
        }
