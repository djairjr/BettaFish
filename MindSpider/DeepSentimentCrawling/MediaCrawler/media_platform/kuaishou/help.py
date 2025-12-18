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

import re
from model.m_kuaishou import VideoUrlInfo, CreatorUrlInfo


def parse_video_info_from_url(url: str) -> VideoUrlInfo:
    """Parse the video ID from the Kuaishou video URL
    The following formats are supported:
    1. Full video URL:"https://www.kuaishou.com/short-video/3x3zxz4mjrsc8ke?authorId=3x84qugg4ch9zhs&streamSource=search"2. Pure video ID:"3x3zxz4mjrsc8ke"Args:
        url: Kuaishou video link or video ID
    Returns:
        VideoUrlInfo: object containing the video ID"""
    # If it does not contain http and does not contain kuaishou.com, it is considered a pure ID.
    if not url.startswith("http") and "kuaishou.com" not in url:
        return VideoUrlInfo(video_id=url, url_type="normal")

    # Extract ID from standard video URL: /short-video/videoID
    video_pattern = r'/short-video/([a-zA-Z0-9_-]+)'
    match = re.search(video_pattern, url)
    if match:
        video_id = match.group(1)
        return VideoUrlInfo(video_id=video_id, url_type="normal")

    raise ValueError(f"Unable to parse video ID from URL: {url}")


def parse_creator_info_from_url(url: str) -> CreatorUrlInfo:
    """Parse the creator ID from the Kuaishou creator homepage URL
    The following formats are supported:
    1. Creator homepage:"https://www.kuaishou.com/profile/3x84qugg4ch9zhs"2. Pure ID:"3x4sm73aye7jq7i"Args:
        url: Kuaishou creator homepage link or user_id
    Returns:
        CreatorUrlInfo: object containing the creator ID"""
    # If it does not contain http and does not contain kuaishou.com, it is considered a pure ID.
    if not url.startswith("http") and "kuaishou.com" not in url:
        return CreatorUrlInfo(user_id=url)

    # Extract user_id from creator homepage URL: /profile/xxx
    user_pattern = r'/profile/([a-zA-Z0-9_-]+)'
    match = re.search(user_pattern, url)
    if match:
        user_id = match.group(1)
        return CreatorUrlInfo(user_id=user_id)

    raise ValueError(f"Unable to parse creator ID from URL: {url}")


if __name__ == '__main__':
    # Test video URL parsing
    print("=== Video URL parsing test ===")
    test_video_urls = [
        "https://www.kuaishou.com/short-video/3x3zxz4mjrsc8ke?authorId=3x84qugg4ch9zhs&streamSource=search&area=searchxxnull&searchKey=python",
        "3xf8enb8dbj6uig",
    ]
    for url in test_video_urls:
        try:
            result = parse_video_info_from_url(url)
            print(f"✓ URL: {url[:80]}...")
            print(f"Result: {result}\n")
        except Exception as e:
            print(f"✗ URL: {url}")
            print(f"Error: {e}\n")

    # Test creator URL parsing
    print("=== Creator URL parsing test ===")
    test_creator_urls = [
        "https://www.kuaishou.com/profile/3x84qugg4ch9zhs",
        "3x4sm73aye7jq7i",
    ]
    for url in test_creator_urls:
        try:
            result = parse_creator_info_from_url(url)
            print(f"✓ URL: {url[:80]}...")
            print(f"Result: {result}\n")
        except Exception as e:
            print(f"✗ URL: {url}")
            print(f"Error: {e}\n")
