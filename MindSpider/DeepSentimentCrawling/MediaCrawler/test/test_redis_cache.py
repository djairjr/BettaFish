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
# @Time    : 2024/6/2 19:54
# @Desc    :

import time
import unittest

from cache.redis_cache import RedisCache


class TestRedisCache(unittest.TestCase):

    def setUp(self):
        self.redis_cache = RedisCache()

    def test_set_and_get(self):
        self.redis_cache.set('key', 'value', 10)
        self.assertEqual(self.redis_cache.get('key'), 'value')

    def test_expired_key(self):
        self.redis_cache.set('key', 'value', 1)
        time.sleep(2)  # wait for the key to expire
        self.assertIsNone(self.redis_cache.get('key'))

    def test_keys(self):
        self.redis_cache.set('key1', 'value1', 10)
        self.redis_cache.set('key2', 'value2', 10)
        keys = self.redis_cache.keys('*')
        self.assertIn('key1', keys)
        self.assertIn('key2', keys)

    def tearDown(self):
        # self.redis_cache._redis_client.flushdb() # Clear the redis database
        pass


if __name__ == '__main__':
    unittest.main()
