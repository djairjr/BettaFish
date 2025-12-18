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


class FeedType(Enum):
    # recommend
    RECOMMEND = "homefeed_recommend"
    # Outfit
    FASION = "homefeed.fashion_v3"
    # gourmet food
    FOOD = "homefeed.food_v3"
    # Makeup
    COSMETICS = "homefeed.cosmetics_v3"
    # Film and television
    MOVIE = "homefeed.movie_and_tv_v3"
    # workplace
    CAREER = "homefeed.career_v3"
    # emotion
    EMOTION = "homefeed.love_v3"
    # Home
    HOURSE = "homefeed.household_product_v3"
    # game
    GAME = "homefeed.gaming_v3"
    # travel
    TRAVEL = "homefeed.travel_v3"
    # fitness
    FITNESS = "homefeed.fitness_v3"


class NoteType(Enum):
    NORMAL = "normal"
    VIDEO = "video"


class SearchSortType(Enum):
    """search sort type"""
    # default
    GENERAL = "general"
    # most popular
    MOST_POPULAR = "popularity_descending"
    # Latest
    LATEST = "time_descending"


class SearchNoteType(Enum):
    """search note type
    """
    # default
    ALL = 0
    # only video
    VIDEO = 1
    # only image
    IMAGE = 2


class Note(NamedTuple):
    """note tuple"""
    note_id: str
    title: str
    desc: str
    type: str
    user: dict
    img_urls: list
    video_url: str
    tag_list: list
    at_user_list: list
    collected_count: str
    comment_count: str
    liked_count: str
    share_count: str
    time: int
    last_update_time: int
