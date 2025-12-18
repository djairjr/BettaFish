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
# @Time    : 2025/7/31
# @Desc: Wandou HTTP proxy IP implementation
import os
from typing import Dict, List
from urllib.parse import urlencode

import httpx

from proxy import IpCache, IpGetError, ProxyProvider
from proxy.types import IpInfoModel
from tools import utils


class WanDouHttpProxy(ProxyProvider):

    def __init__(self, app_key: str, num: int = 100):
        """Wandou HTTP proxy IP implementation
        :param app_key: open app_key, which can be obtained through the user center
        :param num: The number of IPs extracted at a time, the maximum is 100"""
        self.proxy_brand_name = "WANDOUHTTP"
        self.api_path = "https://api.wandouapp.com/"
        self.params = {
            "app_key": app_key,
            "num": num,
        }
        self.ip_cache = IpCache()

    async def get_proxy(self, num: int) -> List[IpInfoModel]:
        """
        :param num:
        :return:
        """

        # Get IP from cache first
        ip_cache_list = self.ip_cache.load_all_ip(
            proxy_brand_name=self.proxy_brand_name
        )
        if len(ip_cache_list) >= num:
            return ip_cache_list[:num]

        # If the number in the cache is not enough, get it from the IP agent and store it in the cache.
        need_get_count = num - len(ip_cache_list)
        self.params.update({"num": min(need_get_count, 100)})  # Max 100
        ip_infos = []
        async with httpx.AsyncClient() as client:
            url = self.api_path + "?" + urlencode(self.params)
            utils.logger.info(f"[WanDouHttpProxy.get_proxy] get ip proxy url:{url}")
            response = await client.get(
                url,
                headers={
                    "User-Agent": "MediaCrawler https://github.com/NanmiCoder/MediaCrawler",
                },
            )
            res_dict: Dict = response.json()
            if res_dict.get("code") == 200:
                data: List[Dict] = res_dict.get("data", [])
                current_ts = utils.get_unix_timestamp()
                for ip_item in data:
                    ip_info_model = IpInfoModel(
                        ip=ip_item.get("ip"),
                        port=ip_item.get("port"),
                        user="",  # Wandou HTTP does not require username and password authentication
                        password="",
                        expired_time_ts=utils.get_unix_time_from_time_str(
                            ip_item.get("expire_time")
                        ),
                    )
                    ip_key = f"WANDOUHTTP_{ip_info_model.ip}_{ip_info_model.port}"
                    ip_value = ip_info_model.model_dump_json()
                    ip_infos.append(ip_info_model)
                    self.ip_cache.set_ip(
                        ip_key, ip_value, ex=ip_info_model.expired_time_ts - current_ts
                    )
            else:
                error_msg = res_dict.get("msg", "unknown error")
                # Handle specific error codes
                error_code = res_dict.get("code")
                if error_code == 10001:
                    error_msg = "General error, please check msg content for specific error information"
                elif error_code == 10048:
                    error_msg = "No packages available"
                raise IpGetError(f"{error_msg} (code: {error_code})")
        return ip_cache_list + ip_infos


def new_wandou_http_proxy() -> WanDouHttpProxy:
    """Construct Wandou HTTP instance
    Returns:"""
    return WanDouHttpProxy(
        app_key=os.getenv(
            "wandou_app_key", "Your pea HTTP app_key"
        ),  # Obtain Wandou HTTP app_key through environment variables
    )
