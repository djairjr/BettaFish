"""Retry mechanism tool module
Provides a general network request retry function to enhance system robustness"""

import time
from functools import wraps
from typing import Callable, Any
import requests
from loguru import logger

# Configuration log
class RetryConfig:
    """Retry configuration class"""
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 60.0,
        retry_on_exceptions: tuple = None
    ):
        """Initialize retry configuration
        
        Args:
            max_retries: Maximum number of retries
            initial_delay: initial delay in seconds
            backoff_factor: backoff factor (double the delay for each retry)
            max_delay: maximum delay seconds
            retry_on_exceptions: Tuple of exception types that need to be retried"""
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        
        # Default exception type that requires retry
        if retry_on_exceptions is None:
            self.retry_on_exceptions = (
                requests.exceptions.RequestException,
                requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError,
                requests.exceptions.Timeout,
                requests.exceptions.TooManyRedirects,
                ConnectionError,
                TimeoutError,
                Exception  # General exceptions that may be thrown by OpenAI and other APIs
            )
        else:
            self.retry_on_exceptions = retry_on_exceptions

# Default configuration
DEFAULT_RETRY_CONFIG = RetryConfig()

def with_retry(config: RetryConfig = None):
    """Retry decorator
    
    Args:
        config: Retry configuration, use default configuration if not provided
    
    Returns:
        Decorator function"""
    if config is None:
        config = DEFAULT_RETRY_CONFIG
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(config.max_retries + 1):  # +1 because the first time does not count as a retry
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(f"Function {func.__name__} succeeds after {attempt + 1}th attempt")
                    return result
                    
                except config.retry_on_exceptions as e:
                    last_exception = e
                    
                    if attempt == config.max_retries:
                        # The last attempt also failed
                        logger.error(f"Function {func.__name__} still fails after {config.max_retries + 1} attempts")
                        logger.error(f"Final error: {str(e)}")
                        raise e
                    
                    # Calculate delay time
                    delay = min(
                        config.initial_delay * (config.backoff_factor ** attempt),
                        config.max_delay
                    )
                    
                    logger.warning(f"Function {func.__name__} failed at {attempt + 1}th attempt: {str(e)}")
                    logger.info(f"The {attempt + 2}th attempt will be made in {delay:.1f} seconds...")
                    
                    time.sleep(delay)
                
                except Exception as e:
                    # Exceptions not in the retry list are thrown directly
                    logger.error(f"Function {func.__name__} encountered a non-retryable exception: {str(e)}")
                    raise e
            
            # This should not be reached but serves as a safety net
            if last_exception:
                raise last_exception
            
        return wrapper
    return decorator

def retry_on_network_error(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0
):
    """Retry decorator specifically for network errors (simplified version)
    
    Args:
        max_retries: Maximum number of retries
        initial_delay: initial delay in seconds
        backoff_factor: backoff factor
    
    Returns:
        Decorator function"""
    config = RetryConfig(
        max_retries=max_retries,
        initial_delay=initial_delay,
        backoff_factor=backoff_factor
    )
    return with_retry(config)

class RetryableError(Exception):
    """Custom retryable exceptions"""
    pass

def with_graceful_retry(config: RetryConfig = None, default_return=None):
    """Graceful retry decorator - for non-critical API calls
    No exception will be thrown after failure, but the default value will be returned to ensure that the system continues to run.
    
    Args:
        config: Retry configuration, use default configuration if not provided
        default_return: The default value returned after all failed retries
    
    Returns:
        Decorator function"""
    if config is None:
        config = SEARCH_API_RETRY_CONFIG
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(config.max_retries + 1):  # +1 because the first time does not count as a retry
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(f"Non-critical API {func.__name__} succeeded after {attempt + 1} attempts")
                    return result
                    
                except config.retry_on_exceptions as e:
                    last_exception = e
                    
                    if attempt == config.max_retries:
                        # The last attempt also failed, returning the default value without throwing an exception
                        logger.warning(f"Non-critical API {func.__name__} still fails after {config.max_retries + 1} attempts")
                        logger.warning(f"Final error: {str(e)}")
                        logger.info(f"Return to default value to ensure the system continues to operate: {default_return}")
                        return default_return
                    
                    # Calculate delay time
                    delay = min(
                        config.initial_delay * (config.backoff_factor ** attempt),
                        config.max_delay
                    )
                    
                    logger.warning(f"Non-critical API {func.__name__} {attempt + 1} failed: {str(e)}")
                    logger.info(f"The {attempt + 2}th attempt will be made in {delay:.1f} seconds...")
                    
                    time.sleep(delay)
                
                except Exception as e:
                    # For exceptions not in the retry list, return the default value
                    logger.warning(f"Non-critical API {func.__name__} encountered a non-retryable exception: {str(e)}")
                    logger.info(f"Return to default value to ensure the system continues to operate: {default_return}")
                    return default_return
            
            # This should not be reached but serves as a safety net
            return default_return
            
        return wrapper
    return decorator

def make_retryable_request(
    request_func: Callable,
    *args,
    max_retries: int = 5,
    **kwargs
) -> Any:
    """Execute retryable requests directly (without using decorators)
    
    Args:
        request_func: the request function to be executed
        *args: Positional parameters passed to the request function
        max_retries: Maximum number of retries
        **kwargs: keyword arguments passed to the request function
    
    Returns:
        The return value of the request function"""
    config = RetryConfig(max_retries=max_retries)
    
    @with_retry(config)
    def _execute():
        return request_func(*args, **kwargs)
    
    return _execute()

# Predefine some commonly used retry configurations
LLM_RETRY_CONFIG = RetryConfig(
    max_retries=6,        # Keep extra retries
    initial_delay=60.0,   # Wait at least 1 minute for the first time
    backoff_factor=2.0,   # Continue to use exponential backoff
    max_delay=600.0       # Wait up to 10 minutes at a time
)

SEARCH_API_RETRY_CONFIG = RetryConfig(
    max_retries=5,        # Increase to 5 retries
    initial_delay=2.0,    # Add initial delay
    backoff_factor=1.6,   # Adjust backoff factor
    max_delay=25.0        # Increase maximum delay
)

DB_RETRY_CONFIG = RetryConfig(
    max_retries=5,        # Increase to 5 retries
    initial_delay=1.0,    # Keep database retry delays short
    backoff_factor=1.5,
    max_delay=10.0
)
