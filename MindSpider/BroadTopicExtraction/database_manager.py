#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BroadTopicExtraction module - database manager
Only responsible for the storage and query of news data and topic analysis"""

import sys
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from loguru import logger

# Add project root directory to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

try:
    import config
except ImportError:
    raise ImportError("Unable to import config.py configuration file")

from config import settings


class DatabaseManager:
    """Database manager"""

    def __init__(self):
        """Initialize the database manager"""
        self.engine: Engine = None
        self.connect()

    def connect(self):
        """Connect to database"""
        try:
            dialect = (settings.DB_DIALECT or "mysql").lower()
            if dialect in ("postgresql", "postgres"):
                url = f"postgresql+psycopg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
            else:
                url = f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}?charset={settings.DB_CHARSET}"
            self.engine = create_engine(url, future=True)
            logger.info(f"Successfully connected to database: {settings.DB_NAME}")
        except ModuleNotFoundError as e:
            missing: str = str(e)
            if "psycopg" in missing:
                logger.error(
                    "Database connection failed: PostgreSQL driver psycopg is not installed. Please install: psycopg[binary]. Reference instructions: uv pip install psycopg[binary]")
            elif "pymysql" in missing:
                logger.error("Database connection failed: MySQL driver pymysql is not installed. Please install: pymysql. Reference instructions: uv pip install pymysql")
            else:
                logger.error(f"Database connection failed (missing driver): {e}")
            raise
        except Exception as e:
            logger.exception(f"Database connection failed: {e}")
            raise

    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ==================== News data operations ====================

    def save_daily_news(self, news_data: List[Dict], crawl_date: date = None) -> int:
        """Save daily news data, overwriting if there is data for that day

        Args:
            news_data: news data list
            crawl_date: crawl date, default is today

        Returns:
            Number of saved news"""
        if not crawl_date:
            crawl_date = date.today()

        current_timestamp = int(datetime.now().timestamp())

        try:
            saved_count = 0
            # Perform the deletion in an independent transaction first to prevent subsequent insertion failures from causing inability to clean up.
            with self.engine.begin() as conn:
                deleted = conn.execute(text("DELETE FROM daily_news WHERE crawl_date = :d"), {"d": crawl_date}).rowcount
                if deleted and deleted > 0:
                    logger.info(f"Overwrite mode: {deleted} existing news records for the day were deleted")

            # Insert items one by one, failure of a single item will not affect subsequent transactions (each independent transaction)
            for news_item in news_data:
                try:
                    # news_item.get('id') is already the complete news_id (format: source_item_id)
                    # In order to support the same news appearing on different dates, add crawl_date to news_id
                    base_news_id = news_item.get(
                        'id') or f"{news_item.get('source', 'unknown')}_rank_{news_item.get('rank', 0)}"
                    # Format the date into a string and add it to news_id to ensure global uniqueness
                    news_id = f"{base_news_id}_{crawl_date.strftime('%Y%m%d')}"

                    title_val = (news_item.get("title", "") or "")
                    if len(title_val) > 500:
                        title_val = title_val[:500]
                    with self.engine.begin() as conn:
                        conn.execute(
                            text(
                                """
                                INSERT INTO daily_news (
                                    news_id, source_platform, title, url, crawl_date,
                                    rank_position, add_ts, last_modify_ts
                                ) VALUES (:news_id, :source_platform, :title, :url, :crawl_date, :rank_position, :add_ts, :last_modify_ts)
                                """
                            ),
                            {
                                "news_id": news_id,
                                "source_platform": news_item.get("source", "unknown"),
                                "title": title_val,
                                "url": news_item.get("url", ""),
                                "crawl_date": crawl_date,
                                "rank_position": news_item.get("rank", None),
                                "add_ts": current_timestamp,
                                "last_modify_ts": current_timestamp,
                            },
                        )
                    saved_count += 1
                except Exception as e:
                    logger.exception(f"Failed to save single news: {e}")
                    continue
            logger.info(f"{saved_count} news records successfully saved")
            return saved_count
        except Exception as e:
            logger.exception(f"Failed to save news data: {e}")
            return 0

    def get_daily_news(self, crawl_date: date = None) -> List[Dict]:
        """Get daily news data

        Args:
            crawl_date: crawl date, default is today

        Returns:
            News list"""
        if not crawl_date:
            crawl_date = date.today()

        query = (
            "SELECT * FROM daily_news WHERE crawl_date = :d ORDER BY rank_position ASC"
        )
        with self.engine.connect() as conn:
            result = conn.execute(text(query), {"d": crawl_date})
            rows = result.mappings().all()
        return rows

    # ==================== Topic data operations ====================

    def save_daily_topics(self, keywords: List[str], summary: str, extract_date: date = None) -> bool:
        """Save daily topic analysis

        Args:
            keywords: topic keyword list
            summary: summary of news analysis
            extract_date: extraction date, default is today

        Returns:
            Is the save successful?"""
        if not extract_date:
            extract_date = date.today()

        current_timestamp = int(datetime.now().timestamp())

        try:
            keywords_json = json.dumps(keywords, ensure_ascii=False)
            # In order to support foreign key references, topic_id needs to be globally unique, so the date is added to topic_id
            topic_id = f"summary_{extract_date.strftime('%Y%m%d')}"

            with self.engine.begin() as conn:
                check = conn.execute(
                    text("SELECT id FROM daily_topics WHERE extract_date = :d AND topic_id = :tid"),
                    {"d": extract_date, "tid": topic_id},
                ).first()
                if check:
                    conn.execute(
                        text(
                            "UPDATE daily_topics SET keywords = :k, topic_description = :s, add_ts = :ts, last_modify_ts = :lmt, topic_name = :tn WHERE extract_date = :d AND topic_id = :tid"
                        ),
                        {"k": keywords_json, "s": summary, "ts": current_timestamp, "lmt": current_timestamp,
                         "d": extract_date, "tid": topic_id, "tn": "Daily news analysis"},
                    )
                    logger.info(f"Updated topic analysis for {extract_date}")
                else:
                    conn.execute(
                        text(
                            "INSERT INTO daily_topics (extract_date, topic_id, topic_name, keywords, topic_description, add_ts, last_modify_ts) VALUES (:d, :tid, :tn, :k, :s, :ts, :lmt)"
                        ),
                        {"d": extract_date, "tid": topic_id, "tn": "Daily news analysis", "k": keywords_json, "s": summary,
                         "ts": current_timestamp, "lmt": current_timestamp},
                    )
                    logger.info(f"Topic analysis saved for {extract_date}")
            return True
        except Exception as e:
            logger.exception(f"Failed to save topic analysis: {e}")
            return False

    def get_daily_topics(self, extract_date: date = None) -> Optional[Dict]:
        """Get daily topic analysis

        Args:
            extract_date: extraction date, default is today

        Returns:
            Topic analysis data, if it does not exist, return None"""
        if not extract_date:
            extract_date = date.today()

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT * FROM daily_topics WHERE extract_date = :d"),
                                      {"d": extract_date}).mappings().first()
                if result:
                    result = dict(result)  # Convert to variable dict to support item assignment
                    result["keywords"] = json.loads(result["keywords"]) if result.get("keywords") else []
                    return result
                return None
        except Exception as e:
            logger.exception(f"Failed to get topic analysis: {e}")
            return None

    def get_recent_topics(self, days: int = 7) -> List[Dict]:
        """Get topic analysis in recent days

        Args:
            days: number of days

        Returns:
            Topic analysis list"""
        try:
            start_date = date.today() - timedelta(days=days)
            with self.engine.connect() as conn:
                results = conn.execute(
                    text(
                        """
                        SELECT * FROM daily_topics 
                        WHERE extract_date >= :start_date
                        ORDER BY extract_date DESC
                        """
                    ),
                    {"start_date": start_date},
                ).mappings().all()
                for r in results:
                    r["keywords"] = json.loads(r["keywords"]) if r.get("keywords") else []
                return results
        except Exception as e:
            logger.exception(f"Failed to get recent topic analysis: {e}")
            return []

    # ==================== Statistical query ====================

    def get_summary_stats(self, days: int = 7) -> Dict:
        """Get statistical summary"""
        try:
            start_date = date.today() - timedelta(days=days)
            with self.engine.connect() as conn:
                news_stats = conn.execute(
                    text(
                        """
                        SELECT crawl_date, COUNT(*) as news_count, COUNT(DISTINCT source_platform) as platforms_count
                        FROM daily_news 
                        WHERE crawl_date >= :start_date
                        GROUP BY crawl_date
                        ORDER BY crawl_date DESC
                        """
                    ),
                    {"start_date": start_date},
                ).all()
                topics_stats = conn.execute(
                    text(
                        """
                        SELECT extract_date, keywords, CHAR_LENGTH(topic_description) as summary_length
                        FROM daily_topics 
                        WHERE extract_date >= :start_date
                        ORDER BY extract_date DESC
                        """
                    ),
                    {"start_date": start_date},
                ).all()
                return {"news_stats": news_stats, "topics_stats": topics_stats}
        except Exception as e:
            logger.exception(f"Failed to get statistics summary: {e}")
            return {"news_stats": [], "topics_stats": []}


if __name__ == "__main__":
    # Test database manager
    with DatabaseManager() as db:
        # Test getting news
        news = db.get_daily_news()
        logger.info(f"Today’s news quantity: {len(news)}")

        # Test getting topics
        topics = db.get_daily_topics()
        if topics:
            logger.info(f"Today’s topic keywords: {topics['keywords']}")
        else:
            logger.info("There is no topic analysis today")

        logger.info("Simplified database manager testing completed!")
