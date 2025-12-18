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
from typing import Optional

from pydantic import BaseModel, Field


class TiebaNote(BaseModel):
    """Baidu Tieba posts"""
    note_id: str = Field(..., description="Post ID")
    title: str = Field(..., description="Post title")
    desc: str = Field(default="", description="Post description")
    note_url: str = Field(..., description="Post link")
    publish_time: str = Field(default="", description="Release time")
    user_link: str = Field(default="", description="User homepage link")
    user_nickname: str = Field(default="", description="User nickname")
    user_avatar: str = Field(default="", description="User avatar address")
    tieba_name: str = Field(..., description="Tieba name")
    tieba_link: str = Field(..., description="Tieba link")
    total_replay_num: int = Field(default=0, description="Total number of replies")
    total_replay_page: int = Field(default=0, description="Total number of pages replied")
    ip_location: Optional[str] = Field(default="", description="IP geographical location")
    source_keyword: str = Field(default="", description="Source keywords")


class TiebaComment(BaseModel):
    """Baidu Tieba comments"""

    comment_id: str = Field(..., description="Comment ID")
    parent_comment_id: str = Field(default="", description="Parent comment ID")
    content: str = Field(..., description="Comment content")
    user_link: str = Field(default="", description="User homepage link")
    user_nickname: str = Field(default="", description="User nickname")
    user_avatar: str = Field(default="", description="User avatar address")
    publish_time: str = Field(default="", description="Release time")
    ip_location: Optional[str] = Field(default="", description="IP geographical location")
    sub_comment_count: int = Field(default=0, description="Number of sub-comments")
    note_id: str = Field(..., description="Post ID")
    note_url: str = Field(..., description="Post link")
    tieba_id: str = Field(..., description="The Tieba ID it belongs to")
    tieba_name: str = Field(..., description="The name of the post bar it belongs to")
    tieba_link: str = Field(..., description="Tieba link")


class TiebaCreator(BaseModel):
    """Baidu Tieba creator"""
    user_id: str = Field(..., description="User ID")
    user_name: str = Field(..., description="username")
    nickname: str = Field(..., description="User nickname")
    gender: str = Field(default="", description="User gender")
    avatar: str = Field(..., description="User avatar address")
    ip_location: Optional[str] = Field(default="", description="IP geographical location")
    follows: int = Field(default=0, description="Number of followers")
    fans: int = Field(default=0, description="Number of fans")
    registration_duration: str = Field(default="", description="Registration duration")
