# -*- coding: utf-8 -*-
# Disclaimer: This code is for learning and research purposes only. Users should abide by the following principles:
# 1. Not for any commercial purposes.
# 2. When using, you should comply with the terms of use and robots.txt rules of the target platform.
# 3. Do not conduct large-scale crawling or cause operational interference to the platform.
# 4. The request frequency should be reasonably controlled to avoid unnecessary burden on the target platform.
# 5. May not be used for any illegal or inappropriate purposes.
#
# For detailed license terms, please refer to the LICENSE file in the project root directory.
# By using this code, you agree to abide by the above principles and all terms in LICENSE.


# Xiaohongshu platform configuration

# Sorting method, the specific enumeration value is in media_platform/xhs/field.py
SORT_TYPE = "popularity_descending"

# Specify the note URL list, which must carry the xsec_token parameter
XHS_SPECIFIED_NOTE_URL_LIST = [
    "https://www.xiaohongshu.com/explore/68f99f6d0000000007033fcf?xsec_token=ABZEzjuN2fPjKF9EcMsCCxfbt3IBRsFZldGFoCJbdDmXI=&xsec_source=pc_feed"
    # ........................
]

# Specify creator URL list (supports full URL or pure ID)
# Supported formats:
# 1. Complete creator homepage URL (with xsec_token and xsec_source parameters): "https://www.xiaohongshu.com/user/profile/5eb8e1d400000000010075ae?xsec_token=AB1nWBKCo1vE2HEkfoJUOi5B6BE5n7wVrbdpHoWIj5xHw=&xsec_source=pc_feed"
# 2. Pure user_id: "63e36c9a000000002703502b"
XHS_CREATOR_ID_LIST = [
    "https://www.xiaohongshu.com/user/profile/5eb8e1d400000000010075ae?xsec_token=AB1nWBKCo1vE2HEkfoJUOi5B6BE5n7wVrbdpHoWIj5xHw=&xsec_source=pc_feed",
    "63e36c9a000000002703502b",    
    # ........................
]
