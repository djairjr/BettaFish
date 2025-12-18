#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MindSpider - the main program of the AI crawler project
Integrate two core modules: BroadTopicExtraction and DeepSentimentCrawling"""

import os
import sys
import argparse
from datetime import date, datetime
from pathlib import Path
import subprocess
import asyncio
import pymysql
from pymysql.cursors import DictCursor
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import inspect, text
from config import settings
from loguru import logger
from urllib.parse import quote_plus

# Add project root directory to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

try:
    import config
except ImportError:
    logger.error("Error: Unable to import config.py configuration file")
    logger.error("Please ensure that the config.py file exists in the project root directory and contains database and API configuration information")
    sys.exit(1)

class MindSpider:
    """MindSpider main program"""
    
    def __init__(self):
        """Initialize MindSpider"""
        self.project_root = project_root
        self.broad_topic_path = self.project_root / "BroadTopicExtraction"
        self.deep_sentiment_path = self.project_root / "DeepSentimentCrawling"
        self.schema_path = self.project_root / "schema"
        
        logger.info("MindSpider AI crawler project")
        logger.info(f"Project path: {self.project_root}")
    
    def check_config(self) -> bool:
        """Check basic configuration"""
        logger.info("Check basic configuration...")
        
        # Check settings configuration items
        required_configs = [
            'DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'DB_CHARSET',
            'MINDSPIDER_API_KEY', 'MINDSPIDER_BASE_URL', 'MINDSPIDER_MODEL_NAME'
        ]
        
        missing_configs = []
        for config_name in required_configs:
            if not hasattr(settings, config_name) or not getattr(settings, config_name):
                missing_configs.append(config_name)
        
        if missing_configs:
            logger.error(f"Missing configuration: {', '.join(missing_configs)}")
            logger.error("Please check the environment variable configuration information in the .env file")
            return False
        
        logger.info("Basic configuration check passed")
        return True
    
    def check_database_connection(self) -> bool:
        """Check database connection"""
        logger.info("Check database connection...")
        
        def build_async_url() -> str:
            dialect = (settings.DB_DIALECT or "mysql").lower()
            if dialect == "postgresql":
                return f"postgresql+asyncpg://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
            # By default, mysql asynchronous driver asyncmy is used
            return (
                f"mysql+asyncmy://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}"
                f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}?charset={settings.DB_CHARSET}"
            )

        async def _test_connection(db_url: str) -> None:
            engine: AsyncEngine = create_async_engine(db_url, pool_pre_ping=True)
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            finally:
                await engine.dispose()

        try:
            db_url: str = build_async_url()
            asyncio.run(_test_connection(db_url))
            logger.info("Database connection is normal")
            return True
        except Exception as e:
            logger.exception(f"Database connection failed: {e}")
            return False
    
    def check_database_tables(self) -> bool:
        """Check if database table exists"""
        logger.info("Check database table...")
        
        def build_async_url() -> str:
            dialect = (settings.DB_DIALECT or "mysql").lower()
            if dialect == "postgresql":
                return f"postgresql+asyncpg://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
            return (
                f"mysql+asyncmy://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}"
                f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}?charset={settings.DB_CHARSET}"
            )

        async def _check_tables(db_url: str) -> list[str]:
            engine: AsyncEngine = create_async_engine(db_url, pool_pre_ping=True)
            try:
                async with engine.connect() as conn:
                    def _get_tables(sync_conn):
                        return inspect(sync_conn).get_table_names()
                    tables = await conn.run_sync(_get_tables)
                    return tables
            finally:
                await engine.dispose()

        try:
            db_url: str = build_async_url()
            existing_tables = asyncio.run(_check_tables(db_url))
            required_tables = ['daily_news', 'daily_topics']
            missing_tables = [t for t in required_tables if t not in existing_tables]
            if missing_tables:
                logger.error(f"Missing database table: {', '.join(missing_tables)}")
                return False
            logger.info("Database table check passed")
            return True
        except Exception as e:
            logger.exception(f"Failed to check database table: {e}")
            return False
    
    def initialize_database(self) -> bool:
        """Initialize database"""
        logger.info("Initialize database...")
        
        try:
            # Run database initialization script
            init_script = self.schema_path / "init_database.py"
            if not init_script.exists():
                logger.error("Error: Database initialization script not found")
                return False
            
            result = subprocess.run(
                [sys.executable, str(init_script)],
                cwd=self.schema_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info("Database initialization successful")
                return True
            else:
                logger.error(f"Database initialization failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.exception(f"Database initialization exception: {e}")
            return False
    
    def check_dependencies(self) -> bool:
        """Check dependency environment"""
        logger.info("Check dependencies...")
        
        # Check Python package
        required_packages = ['pymysql', 'requests', 'playwright']
        missing_packages = []
        
        for package in required_packages:
            try:
                __import__(package)
            except ImportError:
                missing_packages.append(package)
        
        if missing_packages:
            logger.error(f"Missing Python packages: {', '.join(missing_packages)}")
            logger.info("Please run: pip install -r requirements.txt")
            return False
        
        # Check MediaCrawler dependencies
        mediacrawler_path = self.deep_sentiment_path / "MediaCrawler"
        if not mediacrawler_path.exists():
            logger.error("Error: MediaCrawler directory not found")
            return False
        
        logger.info("Dependency environment check passed")
        return True
    
    def run_broad_topic_extraction(self, extract_date: date = None, keywords_count: int = 100) -> bool:
        """Run the BroadTopicExtraction module"""
        logger.info("Run the BroadTopicExtraction module...")
        
        if not extract_date:
            extract_date = date.today()
        
        try:
            cmd = [
                sys.executable, "main.py",
                "--keywords", str(keywords_count)
            ]
            
            logger.info(f"Execute command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                cwd=self.broad_topic_path,
                timeout=1800  # 30 minutes timeout
            )
            
            if result.returncode == 0:
                logger.info("BroadTopicExtraction module was executed successfully")
                return True
            else:
                logger.error(f"BroadTopicExtraction module failed to execute, return code: {result.returncode}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("BroadTopicExtraction module execution timeout")
            return False
        except Exception as e:
            logger.exception(f"BroadTopicExtraction module execution exception: {e}")
            return False
    
    def run_deep_sentiment_crawling(self, target_date: date = None, platforms: list = None,
                                   max_keywords: int = 50, max_notes: int = 50,
                                   test_mode: bool = False) -> bool:
        """Run the DeepSentimentCrawling module"""
        logger.info("Run the DeepSentimentCrawling module...")
        
        if not target_date:
            target_date = date.today()
        
        try:
            cmd = [sys.executable, "main.py"]
            
            if target_date:
                cmd.extend(["--date", target_date.strftime("%Y-%m-%d")])
            
            if platforms:
                cmd.extend(["--platforms"] + platforms)
            
            cmd.extend([
                "--max-keywords", str(max_keywords),
                "--max-notes", str(max_notes)
            ])
            
            if test_mode:
                cmd.append("--test")
            
            logger.info(f"Execute command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                cwd=self.deep_sentiment_path,
                timeout=3600  # 60 minutes timeout
            )
            
            if result.returncode == 0:
                logger.info("DeepSentimentCrawling module was executed successfully")
                return True
            else:
                logger.error(f"DeepSentimentCrawling module execution failed, return code: {result.returncode}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("DeepSentimentCrawling module execution timeout")
            return False
        except Exception as e:
            logger.exception(f"DeepSentimentCrawling module execution exception: {e}")
            return False
    
    def run_complete_workflow(self, target_date: date = None, platforms: list = None,
                             keywords_count: int = 100, max_keywords: int = 50,
                             max_notes: int = 50, test_mode: bool = False) -> bool:
        """Run the complete workflow"""
        logger.info("Start the complete MindSpider workflow")
        
        if not target_date:
            target_date = date.today()
        
        logger.info(f"Target date: {target_date}")
        logger.info(f"Platform list: {platforms if platforms else 'All supported platforms'}")
        logger.info(f"Test mode: {'yes' if test_mode else 'no'}")
        
        # Step 1: Run topic extraction
        logger.info("=== Step One: Topic Extraction ===")
        if not self.run_broad_topic_extraction(target_date, keywords_count):
            logger.error("Topic extraction failed and the process was terminated.")
            return False
        
        # Step Two: Run Sentiment Crawl
        logger.info("=== Step 2: Emotional crawling ===")
        if not self.run_deep_sentiment_crawling(target_date, platforms, max_keywords, max_notes, test_mode):
            logger.error("Sentiment crawling failed, but topic extraction was completed")
            return False
        
        logger.info("The complete workflow was executed successfully!")
        return True
    
    def show_status(self):
        """Show project status"""
        logger.info("MindSpider project status:")
        logger.info(f"Project path: {self.project_root}")
        
        # configuration status
        config_ok = self.check_config()
        logger.info(f"Configuration status: {'normal' if config_ok else 'abnormal'}")
        
        # Database status
        if config_ok:
            db_conn_ok = self.check_database_connection()
            logger.info(f"Database connection: {'normal' if db_conn_ok else 'abnormal'}")
            
            if db_conn_ok:
                db_tables_ok = self.check_database_tables()
                logger.info(f"Database table: {'normal' if db_tables_ok else 'needs initialization'}")
        
        # dependency state
        deps_ok = self.check_dependencies()
        logger.info(f"Dependency environment: {'normal' if deps_ok else 'abnormal'}")
        
        # module status
        broad_topic_exists = self.broad_topic_path.exists()
        deep_sentiment_exists = self.deep_sentiment_path.exists()
        logger.info(f"BroadTopicExtraction module: {'exists' if broad_topic_exists else 'missing'}")
        logger.info(f"DeepSentimentCrawling module: {'exists' if deep_sentiment_exists else 'missing'}")
    
    def setup_project(self) -> bool:
        """Project initialization settings"""
        logger.info("Start MindSpider project initialization...")
        
        # 1. Check configuration
        if not self.check_config():
            return False
        
        # 2. Check dependencies
        if not self.check_dependencies():
            return False
        
        # 3. Check database connection
        if not self.check_database_connection():
            return False
        
        # 4. Check and initialize database tables
        if not self.check_database_tables():
            logger.info("Need to initialize database tables...")
            if not self.initialize_database():
                return False
        
        logger.info("MindSpider project initialization completed!")
        return True

def main():
    """Command line entry"""
    parser = argparse.ArgumentParser(description="MindSpider - the main program of the AI ​​crawler project")
    
    # Basic operations
    parser.add_argument("--setup", action="store_true", help="Initialize project settings")
    parser.add_argument("--status", action="store_true", help="Show project status")
    parser.add_argument("--init-db", action="store_true", help="Initialize database")
    
    # module run
    parser.add_argument("--broad-topic", action="store_true", help="Only run the topic extraction module")
    parser.add_argument("--deep-sentiment", action="store_true", help="Only run the sentiment crawler module")
    parser.add_argument("--complete", action="store_true", help="Run the complete workflow")
    
    # Parameter configuration
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--platforms", type=str, nargs='+', 
                       choices=['xhs', 'dy', 'ks', 'bili', 'wb', 'tieba', 'zhihu'],
                       help="Specify crawling platform")
    parser.add_argument("--keywords-count", type=int, default=100, help="The number of keywords extracted from the topic")
    parser.add_argument("--max-keywords", type=int, default=50, help="Maximum number of keywords per platform")
    parser.add_argument("--max-notes", type=int, default=50, help="Maximum number of crawled content per keyword")
    parser.add_argument("--test", action="store_true", help="Test mode (small amount of data)")
    
    args = parser.parse_args()
    
    # parse date
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Error: Date format is incorrect, please use YYYY-MM-DD format")
            return
    
    # Create MindSpider instance
    spider = MindSpider()
    
    try:
        # Show status
        if args.status:
            spider.show_status()
            return
        
        # Project settings
        if args.setup:
            if spider.setup_project():
                logger.info("The project setup is complete and you can start using MindSpider!")
            else:
                logger.error("Project setup failed, please check configuration and environment")
            return
        
        # Initialize database
        if args.init_db:
            if spider.initialize_database():
                logger.info("Database initialization successful")
            else:
                logger.error("Database initialization failed")
            return
        
        # Run module
        if args.broad_topic:
            spider.run_broad_topic_extraction(target_date, args.keywords_count)
        elif args.deep_sentiment:
            spider.run_deep_sentiment_crawling(
                target_date, args.platforms, args.max_keywords, args.max_notes, args.test
            )
        elif args.complete:
            spider.run_complete_workflow(
                target_date, args.platforms, args.keywords_count, 
                args.max_keywords, args.max_notes, args.test
            )
        else:
            # Run full workflow by default
            logger.info("Run the complete MindSpider workflow...")
            spider.run_complete_workflow(
                target_date, args.platforms, args.keywords_count,
                args.max_keywords, args.max_notes, args.test
            )
    
    except KeyboardInterrupt:
        logger.info("User interrupt operation")
    except Exception as e:
        logger.exception(f"Execution error: {e}")

if __name__ == "__main__":
    main()
