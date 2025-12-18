# Disclaimer: This code is for learning and research purposes only. Users should abide by the following principles:
# 1. Not for any commercial purposes.
# 2. When using, you should comply with the terms of use and robots.txt rules of the target platform.
# 3. Do not conduct large-scale crawling or cause operational interference to the platform.
# 4. The request frequency should be reasonably controlled to avoid unnecessary burden on the target platform.
# 5. May not be used for any illegal or inappropriate purposes.
#   
# For detailed license terms, please refer to the LICENSE file in the project root directory.
# By using this code, you agree to abide by the above principles and all terms in LICENSE.


# -*- coding: utf-8 -*-
# @Author  : relakkes@gmail.com
# @Name: Programmer Ajiang-Relakkes
# @Time    : 2024/6/2 11:06
# @Desc: abstract class

from abc import ABC, abstractmethod
from typing import Any, List, Optional


class AbstractCache(ABC):

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get the value of the key from the cache.
        This is an abstract method. Subclasses must implement this method.
        :param key: key
        :return:"""
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: Any, expire_time: int) -> None:
        """Sets the key's value into the cache.
        This is an abstract method. Subclasses must implement this method.
        :param key: key
        :param value: value
        :param expire_time: expiration time
        :return:"""
        raise NotImplementedError

    @abstractmethod
    def keys(self, pattern: str) -> List[str]:
        """Get all keys matching pattern
        :param pattern: matching pattern
        :return:"""
        raise NotImplementedError
