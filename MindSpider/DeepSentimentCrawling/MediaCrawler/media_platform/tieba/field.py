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


class SearchSortType(Enum):
    """search sort type"""
    # in reverse chronological order
    TIME_DESC = "1"
    # in chronological order
    TIME_ASC = "0"
    # in order of relevance
    RELEVANCE_ORDER = "2"


class SearchNoteType(Enum):
    # Only view topic posts
    MAIN_THREAD = "1"
    # Mixed mode (post + reply)
    FIXED_THREAD = "0"
