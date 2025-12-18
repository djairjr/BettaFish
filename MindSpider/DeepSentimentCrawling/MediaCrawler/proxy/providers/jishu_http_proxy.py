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
# @Time    : 2024/4/5 09:32
# @Desc: Deprecated! ! ! ! ! Closed! ! ! Extremely fast HTTP proxy IP implementation. Please use fast proxy implementation (proxy/providers/kuaidl_proxy.py)
import os
from typing import Dict, List
from urllib.parse import urlencode

import httpx

from proxy import IpCache, IpGetError, ProxyProvider
from proxy.types import IpInfoModel
from tools import utils


class JiSuHttpProxy(ProxyProvider):

    def __init__(self, key: str, crypto: str, time_validity_period: int):
        """Extremely fast HTTP proxy IP implementation
        :param key: Extract key value (obtained after registering on the official website)
        :param crypto: encrypted signature (obtained after registering on the official website)"""
        self.proxy_brand_name = "JISUHTTP"
        self.api_path = "https://api.jisuhttp.com"
        self.params = {
            "key": key,
            "crypto": crypto,
            "time": time_validity_period,  # IP usage time, supports 3, 5, 10, 15, and 30 minutes.
            "type": "json",  # The data result is json
            "port": "2",  # IP protocol: 1: HTTP, 2: HTTPS, 3: SOCKS5
            "pw": "1",  # Whether to use account and password verification, 1: yes, 0: no, no means whitelist verification; the default is 0
            "se": "1",  # Whether to display the IP expiration time when returning JSON format, 1: display, 0: not display; the default is 0
        }
        self.ip_cache = IpCache()

    async def get_proxy(self, num: int) -> List[IpInfoModel]:
        """
        :param num:
        :return:
        """

        # Get IP from cache first
        ip_cache_list = self.ip_cache.load_all_ip(proxy_brand_name=self.proxy_brand_name)
        if len(ip_cache_list) >= num:
            return ip_cache_list[:num]

        # If the number in the cache is not enough, get it from the IP agent and store it in the cache.
        need_get_count = num - len(ip_cache_list)
        self.params.update({"num": need_get_count})
        ip_infos = []
        async with httpx.AsyncClient() as client:
            url = self.api_path + "/fetchips" + '?' + urlencode(self.params)
            utils.logger.info(f"[JiSuHttpProxy.get_proxy] get ip proxy url:{url}")
            response = await client.get(url, headers={
                "User-Agent": "MediaCrawler https://github.com/NanmiCoder/MediaCrawler",
            })
            res_dict: Dict = response.json()
            if res_dict.get("code") == 0:
                data: List[Dict] = res_dict.get("data")
                current_ts = utils.get_unix_timestamp()
                for ip_item in data:
                    ip_info_model = IpInfoModel(
                        ip=ip_item.get("ip"),
                        port=ip_item.get("port"),
                        user=ip_item.get("user"),
                        password=ip_item.get("pass"),
                        expired_time_ts=utils.get_unix_time_from_time_str(ip_item.get("expire")),
                    )
                    ip_key = f"JISUHTTP_{ip_info_model.ip}_{ip_info_model.port}_{ip_info_model.user}_{ip_info_model.password}"
                    ip_value = ip_info_model.json()
                    ip_infos.append(ip_info_model)
                    self.ip_cache.set_ip(ip_key, ip_value, ex=ip_info_model.expired_time_ts - current_ts)
            else:
                raise IpGetError(res_dict.get("msg", "unkown err"))
        return ip_cache_list + ip_infos


def new_jisu_http_proxy() -> JiSuHttpProxy:
    """Construct extremely fast HTTP instance
    Returns:"""
    return JiSuHttpProxy(
        key=os.getenv("jisu_key", ""),  # Obtain the extremely fast HTTPIP extraction key value through environment variables
        crypto=os.getenv("jisu_crypto", ""),  # Obtain extremely fast HTTP IP extraction encryption signature through environment variables
        time_validity_period=30  # 30 minutes (maximum time limit)
    )
