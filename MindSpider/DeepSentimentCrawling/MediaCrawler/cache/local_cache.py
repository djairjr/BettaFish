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
# @Time    : 2024/6/2 11:05
# @Desc: local cache

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from cache.abs_cache import AbstractCache


class ExpiringLocalCache(AbstractCache):

    def __init__(self, cron_interval: int = 10):
        """Initialize local cache
        :param cron_interval: time interval for clearing cache regularly
        :return:"""
        self._cron_interval = cron_interval
        self._cache_container: Dict[str, Tuple[Any, float]] = {}
        self._cron_task: Optional[asyncio.Task] = None
        # Start scheduled cleaning tasks
        self._schedule_clear()

    def __del__(self):
        """Destructor, clean up scheduled tasks
        :return:"""
        if self._cron_task is not None:
            self._cron_task.cancel()

    def get(self, key: str) -> Optional[Any]:
        """Get the value of key from cache
        :param key:
        :return:"""
        value, expire_time = self._cache_container.get(key, (None, 0))
        if value is None:
            return None

        # If the key has expired, delete the key and return None
        if expire_time < time.time():
            del self._cache_container[key]
            return None

        return value

    def set(self, key: str, value: Any, expire_time: int) -> None:
        """Set the value of the key into the cache
        :param key:
        :param value:
        :param expire_time:
        :return:"""
        self._cache_container[key] = (value, time.time() + expire_time)

    def keys(self, pattern: str) -> List[str]:
        """Get all keys matching pattern
        :param pattern: matching pattern
        :return:"""
        if pattern == '*':
            return list(self._cache_container.keys())

        # Local cache wildcard temporarily replaces * with empty
        if '*' in pattern:
            pattern = pattern.replace('*', '')

        return [key for key in self._cache_container.keys() if pattern in key]

    def _schedule_clear(self):
        """Start scheduled cleaning tasks,
        :return:"""

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        self._cron_task = loop.create_task(self._start_clear_cron())

    def _clear(self):
        """Clean cache based on expiration time
        :return:"""
        for key, (value, expire_time) in self._cache_container.items():
            if expire_time < time.time():
                del self._cache_container[key]

    async def _start_clear_cron(self):
        """Start scheduled cleaning tasks
        :return:"""
        while True:
            self._clear()
            await asyncio.sleep(self._cron_interval)


if __name__ == '__main__':
    cache = ExpiringLocalCache(cron_interval=2)
    cache.set('name', '程序员阿江-Relakkes', 3)
    print(cache.get('key'))
    print(cache.keys("*"))
    time.sleep(4)
    print(cache.get('key'))
    del cache
    time.sleep(1)
    print("done")
