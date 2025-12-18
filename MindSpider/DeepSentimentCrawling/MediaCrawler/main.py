# Disclaimer: This code is for learning and research purposes only. Users should abide by the following principles:
# 1. Not for any commercial purposes.
# 2. When using, you should comply with the terms of use and robots.txt rules of the target platform.
# 3. Do not conduct large-scale crawling or cause operational interference to the platform.
# 4. The request frequency should be reasonably controlled to avoid unnecessary burden on the target platform.
# 5. May not be used for any illegal or inappropriate purposes.
#
# For detailed license terms, please refer to the LICENSE file in the project root directory.
# By using this code, you agree to abide by the above principles and all terms in LICENSE.


import asyncio
import sys
from typing import Optional

import cmd_arg
import config
from database import db
from base.base_crawler import AbstractCrawler
from media_platform.bilibili import BilibiliCrawler
from media_platform.douyin import DouYinCrawler
from media_platform.kuaishou import KuaishouCrawler
from media_platform.tieba import TieBaCrawler
from media_platform.weibo import WeiboCrawler
from media_platform.xhs import XiaoHongShuCrawler
from media_platform.zhihu import ZhihuCrawler
from tools.async_file_writer import AsyncFileWriter
from var import crawler_type_var


class CrawlerFactory:
    CRAWLERS = {
        "xhs": XiaoHongShuCrawler,
        "dy": DouYinCrawler,
        "ks": KuaishouCrawler,
        "bili": BilibiliCrawler,
        "wb": WeiboCrawler,
        "tieba": TieBaCrawler,
        "zhihu": ZhihuCrawler,
    }

    @staticmethod
    def create_crawler(platform: str) -> AbstractCrawler:
        crawler_class = CrawlerFactory.CRAWLERS.get(platform)
        if not crawler_class:
            raise ValueError(
                "Invalid Media Platform Currently only supported xhs or dy or ks or bili ..."
            )
        return crawler_class()


crawler: Optional[AbstractCrawler] = None


# persist-1<persist1@126.com>
# Reason: Added --init_db function for database initialization.
# Side effects: None
# Rollback strategy: Restore this file.
async def main():
    # Init crawler
    global crawler

    # parse cmd
    args = await cmd_arg.parse_cmd()

    # init db
    if args.init_db:
        await db.init_db(args.init_db)
        print(f"Database {args.init_db} initialized successfully.")
        return  # Exit the main function cleanly



    crawler = CrawlerFactory.create_crawler(platform=config.PLATFORM)
    await crawler.start()

    # Generate wordcloud after crawling is complete
    # Only for JSON save mode
    if config.SAVE_DATA_OPTION == "json" and config.ENABLE_GET_WORDCLOUD:
        try:
            file_writer = AsyncFileWriter(
                platform=config.PLATFORM,
                crawler_type=crawler_type_var.get()
            )
            await file_writer.generate_wordcloud_from_comments()
        except Exception as e:
            print(f"Error generating wordcloud: {e}")


def cleanup():
    if crawler:
        # asyncio.run(crawler.close())
        pass
    if config.SAVE_DATA_OPTION in ["db", "sqlite"]:
        asyncio.run(db.close())


if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(main())
    finally:
        cleanup()
