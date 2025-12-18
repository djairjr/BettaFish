# Disclaimer: This code is for learning and research purposes only. Users should abide by the following principles:
# 1. Not for any commercial purposes.
# 2. When using, you should comply with the terms of use and robots.txt rules of the target platform.
# 3. Do not conduct large-scale crawling or cause operational interference to the platform.
# 4. The request frequency should be reasonably controlled to avoid unnecessary burden on the target platform.
# 5. May not be used for any illegal or inappropriate purposes.
#   
# For detailed license terms, please refer to the LICENSE file in the project root directory.
# By using this code, you agree to abide by the above principles and all terms in LICENSE.


from enum import Enum
from typing import NamedTuple

from constant import zhihu as zhihu_constant


class SearchTime(Enum):
    """Search time range"""
    DEFAULT = ""  # No time limit
    ONE_DAY = "a_day"  # within one day
    ONE_WEEK = "a_week"  # within a week
    ONE_MONTH = "a_month"  # within a month
    THREE_MONTH = "three_months"  # within three months
    HALF_YEAR = "half_a_year"  # Within half a year
    ONE_YEAR = "a_year"  # within one year


class SearchType(Enum):
    """Search result type"""
    DEFAULT = ""  # Any type
    ANSWER = zhihu_constant.ANSWER_NAME  # Only look at answers
    ARTICLE = zhihu_constant.ARTICLE_NAME  # Just read the article
    VIDEO = zhihu_constant.VIDEO_NAME  # Just watch the video


class SearchSort(Enum):
    """Search results sorting"""
    DEFAULT = ""  # Comprehensive sorting
    UPVOTED_COUNT = "upvoted_count"  # Most agree
    CREATE_TIME = "created_time"  # Latest releases
