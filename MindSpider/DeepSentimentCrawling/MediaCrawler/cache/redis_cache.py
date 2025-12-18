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
# @Time    : 2024/5/29 22:57
# @Desc: RedisCache implementation
import pickle
import time
from typing import Any, List

from redis import Redis

from cache.abs_cache import AbstractCache
from config import db_config


class RedisCache(AbstractCache):

    def __init__(self) -> None:
        # Connect to redis and return to redis client
        self._redis_client = self._connet_redis()

    @staticmethod
    def _connet_redis() -> Redis:
        """Connect to redis and return to the redis client. Here configure the redis connection information as needed.
        :return:"""
        return Redis(
            host=db_config.REDIS_DB_HOST,
            port=db_config.REDIS_DB_PORT,
            db=db_config.REDIS_DB_NUM,
            password=db_config.REDIS_DB_PWD,
        )

    def get(self, key: str) -> Any:
        """Get the value of the key from the cache and deserialize it
        :param key:
        :return:"""
        value = self._redis_client.get(key)
        if value is None:
            return None
        return pickle.loads(value)

    def set(self, key: str, value: Any, expire_time: int) -> None:
        """Set the value of the key to the cache and serialize it
        :param key:
        :param value:
        :param expire_time:
        :return:"""
        self._redis_client.set(key, pickle.dumps(value), ex=expire_time)

    def keys(self, pattern: str) -> List[str]:
        """Get all keys matching pattern"""
        return [key.decode() for key in self._redis_client.keys(pattern)]


if __name__ == '__main__':
    redis_cache = RedisCache()
    # basic usage
    redis_cache.set("name", "Programmer Ajiang-Relakkes", 1)
    print(redis_cache.get("name"))  # Relakkes
    print(redis_cache.keys("*"))  # ['name']
    time.sleep(2)
    print(redis_cache.get("name"))  # None

    # special python type usage
    # list
    redis_cache.set("list", [1, 2, 3], 10)
    _value = redis_cache.get("list")
    print(_value, f"value type:{type(_value)}")  # [1, 2, 3]
