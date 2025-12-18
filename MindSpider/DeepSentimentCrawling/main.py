#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSentimentCrawling module - main workflow
Full-platform keyword crawling based on topics extracted by BroadTopicExtraction"""

import sys
import argparse
from datetime import date, datetime
from pathlib import Path
from typing import List, Dict

# Add project root directory to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from keyword_manager import KeywordManager
from platform_crawler import PlatformCrawler

class DeepSentimentCrawling:
    """Main workflow of deep emotion crawling"""
    
    def __init__(self):
        """Initialize deep emotion crawling"""
        self.keyword_manager = KeywordManager()
        self.platform_crawler = PlatformCrawler()
        self.supported_platforms = ['xhs', 'dy', 'ks', 'bili', 'wb', 'tieba', 'zhihu']
    
    def run_daily_crawling(self, target_date: date = None, platforms: List[str] = None, 
                          max_keywords_per_platform: int = 50, 
                          max_notes_per_platform: int = 50,
                          login_type: str = "qrcode") -> Dict:
        """Perform daily crawling tasks
        
        Args:
            target_date: target date, default is today
            platforms: list of platforms to crawl, defaults to all supported platforms
            max_keywords_per_platform: Maximum number of keywords per platform
            max_notes_per_platform: Maximum number of crawled content per platform
            login_type: login method
        
        Returns:
            Crawling result statistics"""
        if not target_date:
            target_date = date.today()
        
        if not platforms:
            platforms = self.supported_platforms
        
        print(f"🚀 Start executing the deep sentiment crawling task of {target_date}")
        print(f"Target platforms: {platforms}")
        
        # 1. Get keyword summary
        summary = self.keyword_manager.get_crawling_summary(target_date)
        print(f"📊 Keyword summary: {summary}")
        
        if not summary['has_data']:
            print("⚠️ No topic data found and cannot be crawled")
            return {"success": False, "error": "No topic data"}
        
        # 2. Obtain keywords (not assigned, all platforms use the same keywords)
        print(f"\n📝 Get keywords...")
        keywords = self.keyword_manager.get_latest_keywords(target_date, max_keywords_per_platform)
        
        if not keywords:
            print("⚠️ No keyword found, unable to crawl")
            return {"success": False, "error": "no keywords"}
        
        print(f"Obtained {len(keywords)} keywords")
        print(f"Each keyword will be crawled on {len(platforms)} platforms")
        print(f"Total crawling tasks: {len(keywords)} × {len(platforms)} = {len(keywords) * len(platforms)}")
        
        # 3. Execute full-platform keyword crawling
        print(f"\n🔄 Start crawling keywords across all platforms...")
        crawl_results = self.platform_crawler.run_multi_platform_crawl_by_keywords(
            keywords, platforms, login_type, max_notes_per_platform
        )
        
        # 4. Generate final report
        final_report = {
            "date": target_date.isoformat(),
            "summary": summary,
            "crawl_results": crawl_results,
            "success": crawl_results["successful_tasks"] > 0
        }
        
        print(f"\n✅ Deep emotion crawling task completed!")
        print(f"Date: {target_date}")
        print(f"Successful tasks: {crawl_results['successful_tasks']}/{crawl_results['total_tasks']}")
        print(f"Total keywords: {crawl_results['total_keywords']}")
        print(f"Total platforms: {crawl_results['total_platforms']}")
        print(f"Total content: {crawl_results['total_notes']} items")
        
        return final_report
    
    def run_platform_crawling(self, platform: str, target_date: date = None,
                             max_keywords: int = 50, max_notes: int = 50,
                             login_type: str = "qrcode") -> Dict:
        """Execute crawling tasks for a single platform
        
        Args:
            platform: platform name
            target_date: target date
            max_keywords: maximum number of keywords
            max_notes: Maximum number of crawled content
            login_type: login method
        
        Returns:
            Crawl results"""
        if platform not in self.supported_platforms:
            raise ValueError(f"Unsupported platforms: {platform}")
        
        if not target_date:
            target_date = date.today()
        
        print(f"🎯 Start executing the crawling task of {platform} platform ({target_date})")
        
        # Get keywords
        keywords = self.keyword_manager.get_keywords_for_platform(
            platform, target_date, max_keywords
        )
        
        if not keywords:
            print(f"⚠️ No keywords found for {platform} platform")
            return {"success": False, "error": "no keywords"}
        
        print(f"📝 Prepare to crawl {len(keywords)} keywords")
        
        # Execute crawling
        result = self.platform_crawler.run_crawler(
            platform, keywords, login_type, max_notes
        )
        
        return result
    
    def list_available_topics(self, days: int = 7):
        """List recently available topics"""
        print(f"📋 Topic data for the last {days} days:")
        
        recent_topics = self.keyword_manager.db_manager.get_recent_topics(days)
        
        if not recent_topics:
            print("No topic data yet")
            return
        
        for topic in recent_topics:
            extract_date = topic['extract_date']
            keywords_count = len(topic.get('keywords', []))
            summary_preview = topic.get('summary', '')[:100] + "..." if len(topic.get('summary', '')) > 100 else topic.get('summary', '')
            
            print(f"📅 {extract_date}: {keywords_count} keywords")
            print(f"Summary: {summary_preview}")
            print()
    
    def show_platform_guide(self):
        """Show platform usage guide"""
        print("🔧 Platform crawling guide:")
        print()
        
        platform_info = {
            'xhs': '小红书 - 美妆、生活、时尚内容为主',
            'dy': '抖音 - 短视频、娱乐、生活内容',
            'ks': '快手 - 生活、娱乐、农村题材内容',
            'bili': 'B站 - 科技、学习、游戏、动漫内容',
            'wb': '微博 - 热点新闻、明星、社会话题',
            'tieba': '百度贴吧 - 兴趣讨论、游戏、学习',
            'zhihu': '知乎 - 知识问答、深度讨论'
        }
        
        for platform, desc in platform_info.items():
            print(f"   {platform}: {desc}")
        
        print()
        print("💡 Usage suggestions:")
        print("1. For first-time use, you need to scan the QR code to log in to each platform.")
        print("2. It is recommended to test a single platform first to confirm that the login is normal.")
        print("3. The number of crawls should not be too large to avoid being restricted.")
        print("4. You can use the --test mode for small-scale testing")
    
    def close(self):
        """Close resource"""
        if self.keyword_manager:
            self.keyword_manager.close()

def main():
    """Command line entry"""
    parser = argparse.ArgumentParser(description="DeepSentimentCrawling - topic-based deep sentiment crawling")
    
    # Basic parameters
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--platform", type=str, choices=['xhs', 'dy', 'ks', 'bili', 'wb', 'tieba', 'zhihu'], 
                       help="Specify a single platform for crawling")
    parser.add_argument("--platforms", type=str, nargs='+', 
                       choices=['xhs', 'dy', 'ks', 'bili', 'wb', 'tieba', 'zhihu'],
                       help="Specify multiple platforms for crawling")
    
    # Crawl parameters
    parser.add_argument("--max-keywords", type=int, default=50, 
                       help="Maximum number of keywords per platform (default: 50)")
    parser.add_argument("--max-notes", type=int, default=50,
                       help="Maximum number of crawled content per platform (default: 50)")
    parser.add_argument("--login-type", type=str, choices=['qrcode', 'phone', 'cookie'], 
                       default='qrcode', help="Login method (default: qrcode)")
    
    # Function parameters
    parser.add_argument("--list-topics", action="store_true", help="List recent topic data")
    parser.add_argument("--days", type=int, default=7, help="View topics from the last few days (default: 7)")
    parser.add_argument("--guide", action="store_true", help="Show platform usage guide")
    parser.add_argument("--test", action="store_true", help="Test mode (small amount of data)")
    
    args = parser.parse_args()
    
    # parse date
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print("❌ The date format is incorrect, please use YYYY-MM-DD format")
            return
    
    # Create crawling instance
    crawler = DeepSentimentCrawling()
    
    try:
        # show guide
        if args.guide:
            crawler.show_platform_guide()
            return
        
        # list topics
        if args.list_topics:
            crawler.list_available_topics(args.days)
            return
        
        # Test mode adjustment parameters
        if args.test:
            args.max_keywords = min(args.max_keywords, 10)
            args.max_notes = min(args.max_notes, 10)
            print("Test mode: limit the number of keywords and content")
        
        # Single platform crawling
        if args.platform:
            result = crawler.run_platform_crawling(
                args.platform, target_date, args.max_keywords, 
                args.max_notes, args.login_type
            )
            
            if result['success']:
                print(f"\n{args.platform} Crawled successfully!")
            else:
                print(f"\n{args.platform} Failed to crawl: {result.get('error', 'Unknown error')}")
            
            return
        
        # Multi-platform crawling
        platforms = args.platforms if args.platforms else None
        result = crawler.run_daily_crawling(
            target_date, platforms, args.max_keywords, 
            args.max_notes, args.login_type
        )
        
        if result['success']:
            print(f"\nMulti-platform crawling task completed!")
        else:
            print(f"\nMulti-platform crawling failed: {result.get('error', 'Unknown error')}")
    
    except KeyboardInterrupt:
        print("\nUser interrupt operation")
    except Exception as e:
        print(f"\nExecution error: {e}")
    finally:
        crawler.close()

if __name__ == "__main__":
    main()
