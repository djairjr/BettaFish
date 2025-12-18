#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MindSpider AI crawler project - database management tool
Provides database status viewing, data statistics, cleaning and other functions"""

import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
from urllib.parse import quote_plus

# Add project root directory to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

try:
    import config
except ImportError:
    logger.error("Error: Unable to import config.py configuration file")
    sys.exit(1)

from config import settings

class DatabaseManager:
    def __init__(self):
        self.engine: Engine = None
        self.connect()
    
    def connect(self):
        """Connect to database"""
        try:
            dialect = (settings.DB_DIALECT or "mysql").lower()
            if dialect in ("postgresql", "postgres"):
                url = f"postgresql+psycopg://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
            else:
                url = f"mysql+pymysql://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}?charset={settings.DB_CHARSET}"
            self.engine = create_engine(url, future=True)
            logger.info(f"Successfully connected to database: {settings.DB_NAME}")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            sys.exit(1)
    
    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()
    
    def show_tables(self):
        """show all tables"""
        data_list_message = ""
        data_list_message += "\n" + "=" * 60
        data_list_message += "Database table list"
        data_list_message += "=" * 60
        logger.info(data_list_message)
        
        inspector = inspect(self.engine)
        tables = inspector.get_table_names()
        
        if not tables:
            logger.info("There is no table in the database")
            return
        
        # Classification display table
        mindspider_tables = []
        mediacrawler_tables = []
        
        for table_name in tables:
            if table_name in ['daily_news', 'daily_topics', 'topic_news_relation', 'crawling_tasks']:
                mindspider_tables.append(table_name)
            else:
                mediacrawler_tables.append(table_name)
        
        data_list_message += "MindSpider core table:"
        data_list_message += "\n"
        for table in mindspider_tables:
            with self.engine.connect() as conn:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            data_list_message += f"- {table:<25} ({count:>6} records)"
            data_list_message += "\n"
        
        data_list_message += "\nMediaCrawler platform table:"
        data_list_message += "\n"
        for table in mediacrawler_tables:
            try:
                with self.engine.connect() as conn:
                    count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                data_list_message += f"- {table:<25} ({count:>6} records)"
                data_list_message += "\n"
            except:
                data_list_message += f"- {table:<25} (query failed)"
                data_list_message += "\n"
        logger.info(data_list_message)
    
    def show_statistics(self):
        """Show statistics"""
        data_statistics_message = ""
        data_statistics_message += "\n" + "=" * 60
        data_statistics_message += "Statistics"
        data_statistics_message += "=" * 60
        data_statistics_message += "\n"
        
        try:
            # News statistics
            with self.engine.connect() as conn:
                news_count = conn.execute(text("SELECT COUNT(*) FROM daily_news")).scalar_one()
                news_days = conn.execute(text("SELECT COUNT(DISTINCT crawl_date) FROM daily_news")).scalar_one()
                platforms = conn.execute(text("SELECT COUNT(DISTINCT source_platform) FROM daily_news")).scalar_one()
            
            data_statistics_message += "News data:"
            data_statistics_message += "\n"
            data_statistics_message += f"- Total news count: {news_count}"
            data_statistics_message += "\n"
            data_statistics_message += f"- Number of days covered: {news_days}"
            data_statistics_message += "\n"
            data_statistics_message += f"- News platform: {platforms}"
            data_statistics_message += "\n"
            # Topic statistics
            with self.engine.connect() as conn:
                topic_count = conn.execute(text("SELECT COUNT(*) FROM daily_topics")).scalar_one()
                topic_days = conn.execute(text("SELECT COUNT(DISTINCT extract_date) FROM daily_topics")).scalar_one()
            
            data_statistics_message += "Topic data:"
            data_statistics_message += "\n"
            data_statistics_message += f"- Total number of topics: {topic_count}"
            data_statistics_message += "\n"
            data_statistics_message += f"- Extract days: {topic_days}"
            data_statistics_message += "\n"
            
            # Crawling task statistics
            with self.engine.connect() as conn:
                task_count = conn.execute(text("SELECT COUNT(*) FROM crawling_tasks")).scalar_one()
                task_status = conn.execute(text("SELECT task_status, COUNT(*) FROM crawling_tasks GROUP BY task_status")).all()
            
            data_statistics_message += "Crawling tasks:"
            data_statistics_message += "\n"
            data_statistics_message += f"- Total number of tasks: {task_count}"
            data_statistics_message += "\n"
            for status, count in task_status:
                data_statistics_message += f"  - {status}: {count}"
                data_statistics_message += "\n"
            
            # Crawl content statistics
            data_statistics_message += "Platform content statistics:"
            data_statistics_message += "\n"
            platform_tables = {
                'xhs_note': '小红书',
                'douyin_aweme': '抖音',
                'kuaishou_video': '快手',
                'bilibili_video': 'B站',
                'weibo_note': '微博',
                'tieba_note': '贴吧',
                'zhihu_content': '知乎'
            }
            
            for table, platform in platform_tables.items():
                try:
                    with self.engine.connect() as conn:
                        count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                    data_statistics_message += f"  - {platform}: {count}"
                    data_statistics_message += "\n"
                except:
                    data_statistics_message += f"- {platform}: table does not exist"
                    data_statistics_message += "\n"
            logger.info(data_statistics_message)
        except Exception as e:
            data_statistics_message += f"Statistics query failed: {e}"
            data_statistics_message += "\n"
            logger.error(data_statistics_message)
    
    def show_recent_data(self, days=7):
        """Show data for the last few days"""
        data_recent_message = ""
        data_recent_message += "\n" + "=" * 60
        data_recent_message += "recent" + str(days) + "days of data"
        data_recent_message += "=" * 60
        
        from datetime import date, timedelta
        start_date = date.today() - timedelta(days=days)
        # latest news
        with self.engine.connect() as conn:
            news_data = conn.execute(
                text(
                    """
                    SELECT crawl_date, COUNT(*) as news_count, COUNT(DISTINCT source_platform) as platforms
                    FROM daily_news 
                    WHERE crawl_date >= :start_date
                    GROUP BY crawl_date 
                    ORDER BY crawl_date DESC
                    """
                ),
                {"start_date": start_date},
            ).all()
        if news_data:
            data_recent_message += "Daily news statistics:"
            data_recent_message += "\n"
            for date, count, platforms in news_data:
                data_recent_message += f"{date}: {count} news, {platforms} platforms"
                data_recent_message += "\n"
        
        # recent topics
        with self.engine.connect() as conn:
            topic_data = conn.execute(
                text(
                    """
                    SELECT extract_date, COUNT(*) as topic_count
                    FROM daily_topics 
                    WHERE extract_date >= :start_date
                    GROUP BY extract_date 
                    ORDER BY extract_date DESC
                    """
                ),
                {"start_date": start_date},
            ).all()
        if topic_data:
            data_recent_message += "Daily topic statistics:"
            data_recent_message += "\n"
            for date, count in topic_data:
                data_recent_message += f"{date}: {count} topics"
                data_recent_message += "\n"
        logger.info(data_recent_message)
    
    def cleanup_old_data(self, days=90, dry_run=True):
        """Clean old data"""
        cleanup_message = ""
        cleanup_message += "\n" + "=" * 60
        cleanup_message += f"Clean data from {days} days ago ({'preview mode' if dry_run else 'execution mode'})"
        cleanup_message += "=" * 60
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Check the data to be deleted
        cleanup_queries = [
            ("daily_news", f"SELECT COUNT(*) FROM daily_news WHERE crawl_date < '{cutoff_date.date()}'"),
            ("daily_topics", f"SELECT COUNT(*) FROM daily_topics WHERE extract_date < '{cutoff_date.date()}'"),
            ("crawling_tasks", f"SELECT COUNT(*) FROM crawling_tasks WHERE scheduled_date < '{cutoff_date.date()}'")
        ]
        
        with self.engine.begin() as conn:
            for table, query in cleanup_queries:
                count = conn.execute(text(query)).scalar_one()
                if count > 0:
                    cleanup_message += f"{table}: {count} records will be deleted"
                    cleanup_message += "\n"
                    if not dry_run:
                        delete_query = query.replace("SELECT COUNT(*)", "DELETE")
                        conn.execute(text(delete_query))
                        cleanup_message += f"{count} records deleted"
                        cleanup_message += "\n"
                else:
                    cleanup_message += f"{table}: No cleaning required"
                    cleanup_message += "\n"
        
        if dry_run:
            cleanup_message += "\nThis is preview mode, no data is actually deleted. Use the --execute parameter to perform the actual cleanup."
            cleanup_message += "\n"
        logger.info(cleanup_message)

def main():
    parser = argparse.ArgumentParser(description="MindSpider database management tool")
    parser.add_argument("--tables", action="store_true", help="show all tables")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--recent", type=int, default=7, help="Display data for the last N days (default 7 days)")
    parser.add_argument("--cleanup", type=int, help="Clean data from N days ago")
    parser.add_argument("--execute", action="store_true", help="Perform actual cleanup operations")
    
    args = parser.parse_args()
    
    # If there are no parameters, display all information
    if not any([args.tables, args.stats, args.recent != 7, args.cleanup]):
        args.tables = True
        args.stats = True
    
    db_manager = DatabaseManager()
    
    try:
        if args.tables:
            db_manager.show_tables()
        
        if args.stats:
            db_manager.show_statistics()
        
        if args.recent != 7 or not any([args.tables, args.stats, args.cleanup]):
            db_manager.show_recent_data(args.recent)
        
        if args.cleanup:
            db_manager.cleanup_old_data(args.cleanup, dry_run=not args.execute)
    
    finally:
        db_manager.close()

if __name__ == "__main__":
    main()
