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


class SearchChannelType(Enum):
    """search channel type"""
    GENERAL = "aweme_general"  # comprehensive
    VIDEO = "aweme_video_web"  # video
    USER = "aweme_user_web"  # user
    LIVE = "aweme_live"  # live streaming


class SearchSortType(Enum):
    """search sort type"""
    GENERAL = 0  # Comprehensive sorting
    MOST_LIKE = 1  # Most likes
    LATEST = 2  # Latest releases

class PublishTimeType(Enum):
    """publish time type"""
    UNLIMITED = 0  # No limit
    ONE_DAY = 1  # within one day
    ONE_WEEK = 7  # within a week
    SIX_MONTH = 180  # Within half a year
