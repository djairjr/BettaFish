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
# bilili platform configuration

# Control the number of videos/posts crawled per day
MAX_NOTES_PER_DAY = 1

# Specify Bilibili video URL list (supports complete URL or BV number)
# Example:
# - Full URL: "https://www.bilibili.com/video/BV1dwuKzmE26/?spm_id_from=333.1387.homepage.video_card.click"
# - BV number: "BV1d54y1g7db"
BILI_SPECIFIED_ID_LIST = [
    "https://www.bilibili.com/video/BV1dwuKzmE26/?spm_id_from=333.1387.homepage.video_card.click",
    "BV1Sz4y1U77N",
    "BV14Q4y1n7jz",
    # ........................
]

# Specify the URL list of Bilibili creators (supports full URL or UID)
# Example:
# - Full URL: "https://space.bilibili.com/434377496?spm_id_from=333.1007.0.0"
# - UID: "20813884"
BILI_CREATOR_ID_LIST = [
    "https://space.bilibili.com/434377496?spm_id_from=333.1007.0.0",
    "20813884",
    # ........................
]

# Specify time range
START_DAY = "2024-01-01"
END_DAY = "2024-01-01"

# Search mode
BILI_SEARCH_MODE = "normal"

# Video definition (qn) configuration, common values:
# 16=360p, 32=480p, 64=720p, 80=1080p, 112=1080p high bit rate, 116=1080p60, 120=4K
# Note: Higher definition requires support from the account/video itself
BILI_QN = 80

# Whether to crawl user information
CREATOR_MODE = True

# Start crawling user information page number
START_CONTACTS_PAGE = 1

# Maximum number of crawled comments for a single video/post
CRAWLER_MAX_CONTACTS_COUNT_SINGLENOTES = 100

# Maximum number of crawled dynamics for a single video/post
CRAWLER_MAX_DYNAMICS_COUNT_SINGLENOTES = 50
