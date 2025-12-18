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
# @Time    : 2023/12/3 16:20
# @Desc    :

from enum import Enum


class SearchOrderType(Enum):
    # Comprehensive sorting
    DEFAULT = ""

    # Most clicks
    MOST_CLICK = "click"

    # Latest releases
    LAST_PUBLISH = "pubdate"

    # Most barrages
    MOST_DANMU = "dm"

    # Most favorites
    MOST_MARK = "stow"


class CommentOrderType(Enum):
    # Only by heat
    DEFAULT = 0

    # By heat + by time
    MIXED = 1

    # by time
    TIME = 2
