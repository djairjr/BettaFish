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


class ZhihuContent(BaseModel):
    """Zhihu content (answers, articles, videos)"""
    content_id: str = Field(default="", description="Content ID")
    content_type: str = Field(default="", description="Content type (article | answer | zvideo)")
    content_text: str = Field(default="", description="Content text, if it is a video type, this is empty")
    content_url: str = Field(default="", description="Content landing link")
    question_id: str = Field(default="", description="Question ID, has value when type is answer")
    title: str = Field(default="", description="Content title")
    desc: str = Field(default="", description="Content description")
    created_time: int = Field(default=0, description="creation time")
    updated_time: int = Field(default=0, description="Update time")
    voteup_count: int = Field(default=0, description="Number of people who agree")
    comment_count: int = Field(default=0, description="Number of comments")
    source_keyword: str = Field(default="", description="Source keywords")

    user_id: str = Field(default="", description="User ID")
    user_link: str = Field(default="", description="User homepage link")
    user_nickname: str = Field(default="", description="User nickname")
    user_avatar: str = Field(default="", description="User avatar address")
    user_url_token: str = Field(default="", description="userurl_token")


class ZhihuComment(BaseModel):
    """Zhihu comments"""

    comment_id: str = Field(default="", description="Comment ID")
    parent_comment_id: str = Field(default="", description="Parent comment ID")
    content: str = Field(default="", description="Comment content")
    publish_time: int = Field(default=0, description="Release time")
    ip_location: Optional[str] = Field(default="", description="IP geographical location")
    sub_comment_count: int = Field(default=0, description="Number of sub-comments")
    like_count: int = Field(default=0, description="Number of likes")
    dislike_count: int = Field(default=0, description="Count down")
    content_id: str = Field(default="", description="Content ID")
    content_type: str = Field(default="", description="Content type (article | answer | zvideo)")

    user_id: str = Field(default="", description="User ID")
    user_link: str = Field(default="", description="User homepage link")
    user_nickname: str = Field(default="", description="User nickname")
    user_avatar: str = Field(default="", description="User avatar address")


class ZhihuCreator(BaseModel):
    """Zhihu creator"""
    user_id: str = Field(default="", description="User ID")
    user_link: str = Field(default="", description="User homepage link")
    user_nickname: str = Field(default="", description="User nickname")
    user_avatar: str = Field(default="", description="User avatar address")
    url_token: str = Field(default="", description="userurl_token")
    gender: str = Field(default="", description="User gender")
    ip_location: Optional[str] = Field(default="", description="IP geographical location")
    follows: int = Field(default=0, description="Number of followers")
    fans: int = Field(default=0, description="Number of fans")
    anwser_count: int = Field(default=0, description="Number of answers")
    video_count: int = Field(default=0, description="Number of videos")
    question_count: int = Field(default=0, description="Number of questions")
    article_count: int = Field(default=0, description="Number of articles")
    column_count: int = Field(default=0, description="Number of columns")
    get_voteup_count: int = Field(default=0, description="Number of approvals received")

