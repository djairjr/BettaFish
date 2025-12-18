#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BroadTopicExtraction module - topic extractor
Directly extract keywords and generate news summaries based on DeepSeek"""

import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Tuple
from openai import OpenAI

# Add project root directory to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

try:
    import config
    from config import settings
except ImportError:
    raise ImportError("Unable to import settings.py configuration file")

class TopicExtractor:
    """topic extractor"""

    def __init__(self):
        """Initialize topic extractor"""
        self.client = OpenAI(
            api_key=settings.MINDSPIDER_API_KEY,
            base_url=settings.MINDSPIDER_BASE_URL
        )
        self.model = settings.MINDSPIDER_MODEL_NAME
    
    def extract_keywords_and_summary(self, news_list: List[Dict], max_keywords: int = 100) -> Tuple[List[str], str]:
        """Extract keywords from news lists and generate summaries
        
        Args:
            news_list: news list
            max_keywords: maximum number of keywords
            
        Returns:
            (keyword list, news analysis summary)"""
        if not news_list:
            return [], "No hot news today"
        
        # Construct news summary text
        news_text = self._build_news_summary(news_list)
        
        # Build prompt words
        prompt = self._build_analysis_prompt(news_text, max_keywords)
        
        try:
            # Call DeepSeek API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional news analyst who is good at extracting keywords from hot news and writing analysis summaries."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.3
            )
            
            # Parse return results
            result_text = response.choices[0].message.content
            keywords, summary = self._parse_analysis_result(result_text)
            
            print(f"Successfully extracted {len(keywords)} keywords and generated news summary")
            return keywords[:max_keywords], summary
            
        except Exception as e:
            print(f"Topic extraction failed: {e}")
            # Return simple fallback results
            fallback_keywords = self._extract_simple_keywords(news_list)
            fallback_summary = f"A total of {len(news_list)} hot news items have been collected today, covering hot topics on multiple platforms."
            return fallback_keywords[:max_keywords], fallback_summary
    
    def _build_news_summary(self, news_list: List[Dict]) -> str:
        """Construct news summary text"""
        news_items = []
        
        for i, news in enumerate(news_list, 1):
            title = news.get('title', '无标题')
            source = news.get('source_platform', news.get('source', '未知'))
            
            # Clean special characters in title
            title = re.sub(r'[#@]', '', title).strip()
            
            news_items.append(f"{i}. 【{source}】{title}")
        
        return "\n".join(news_items)
    
    def _build_analysis_prompt(self, news_text: str, max_keywords: int) -> str:
        """Build analysis prompt words"""
        news_count = len(news_text.split('\n'))
        
        prompt = f"""Please analyze the following {news_count} hot news today and complete two tasks:

News list:
{news_text}

Task 1: Extract keywords (up to {max_keywords})
- Extract keywords that represent today’s hot topics
- Keywords should be suitable for searching on social media platforms
- Prioritize topics that are hot and have a lot of discussion
- Avoid words that are too broad or too specific

Task 2: Write a news analysis summary (150-300 words)
- Briefly summarize the main content of today’s hot news
- Point out the direction of key topics of current social concern
- Analyze the social phenomena or trends reflected in these hot spots
- The language is concise, clear, objective and neutral

Please strictly follow the following JSON format for output:
```json
{{"keywords": ["关键词1", "关键词2", "关键词3"],
  "summary": "今日新闻分析总结内容..."}}
```

Please directly output the results in JSON format without including other text descriptions."""
        return prompt
    
    def _parse_analysis_result(self, result_text: str) -> Tuple[List[str], str]:
        """Analyze analysis results"""
        try:
            # Try to extract the JSON part
            json_match = re.search(r'```json\s*(.*?)\s*```', result_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(1)
            else:
                # If there is no code block, try parsing directly
                json_text = result_text.strip()
            
            # Parse JSON
            data = json.loads(json_text)
            
            keywords = data.get('keywords', [])
            summary = data.get('summary', '')
            
            # Validate and clean keywords
            clean_keywords = []
            for keyword in keywords:
                keyword = str(keyword).strip()
                if keyword and len(keyword) > 1 and keyword not in clean_keywords:
                    clean_keywords.append(keyword)
            
            # Verification summary
            if not summary or len(summary.strip()) < 10:
                summary = "Today's hot news covers multiple fields and reflects the diverse concerns of current society."
            
            return clean_keywords, summary.strip()
            
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}")
            print(f"Original return: {result_text}")
            
            # Try parsing manually
            return self._manual_parse_result(result_text)
        
        except Exception as e:
            print(f"Failed to process analysis results: {e}")
            return [], "Analysis result processing failed, please try again later."
    
    def _manual_parse_result(self, text: str) -> Tuple[List[str], str]:
        """Manually parse results (fallback plan when JSON parsing fails)"""
        print("Try parsing the results manually...")
        
        keywords = []
        summary = ""
        
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Find keywords
            if '关键词' in line or 'keywords' in line.lower():
                # Extract keywords
                keyword_match = re.findall(r'[""](.*?)["""]', line)
                if keyword_match:
                    keywords.extend(keyword_match)
                else:
                    # Try other separators
                    parts = re.split(r'[,,,]', line)
                    for part in parts:
                        clean_part = re.sub(r'[Keywords: :keywords\[\]"keywords\[\]"]', '', part).strip()
                        if clean_part and len(clean_part) > 1:
                            keywords.append(clean_part)
            
            # looking for summary
            elif '总结' in line or '分析' in line or 'summary' in line.lower():
                if '：' in line or ':' in line:
                    summary = line.split('：')[-1].split(':')[-1].strip()
            
            # If this line looks like summarizing the content
            elif len(line) > 50 and ('今日' in line or '热点' in line or '新闻' in line):
                if not summary:
                    summary = line
        
        # Clean up keywords
        clean_keywords = []
        for keyword in keywords:
            keyword = keyword.strip()
            if keyword and len(keyword) > 1 and keyword not in clean_keywords:
                clean_keywords.append(keyword)
        
        # If no summary is found, generate a simple
        if not summary:
            summary = "Today's hot news is rich in content and covers concerns at all levels of society."
        
        return clean_keywords[:max_keywords], summary
    
    def _extract_simple_keywords(self, news_list: List[Dict]) -> List[str]:
        """Simple keyword extraction (fallback solution)"""
        keywords = []
        
        for news in news_list:
            title = news.get('title', '')
            
            # Simple keyword extraction
            # Remove common nonsense words
            title_clean = re.sub(r'[#@【】\[\]()（）]', ' ', title)
            words = title_clean.split()
            
            for word in words:
                word = word.strip()
                if (len(word) > 1 and 
                    word not in ['的', '了', '在', '和', '与', '或', '但', '是', '有', '被', '将', '已', '正在'] and
                    word not in keywords):
                    keywords.append(word)
        
        return keywords[:10]
    
    def get_search_keywords(self, keywords: List[str], limit: int = 10) -> List[str]:
        """Get keywords for search
        
        Args:
            keywords: keyword list
            limit: limit quantity
            
        Returns:
            List of keywords suitable for search"""
        # Filter and optimize keywords
        search_keywords = []
        
        for keyword in keywords:
            keyword = str(keyword).strip()
            
            # filter conditions
            if (len(keyword) > 1 and 
                len(keyword) < 20 and  # not too long
                keyword not in search_keywords and
                not keyword.isdigit() and  # not pure numbers
                not re.match(r'^[a-zA-Z]+$', keyword)):  # Not pure English (unless it is a proper noun)
                
                search_keywords.append(keyword)
        
        return search_keywords[:limit]

if __name__ == "__main__":
    # Test topic extractor
    extractor = TopicExtractor()
    
    # Simulated news data
    test_news = [
        {"title": "AI technology develops rapidly", "source_platform": "Technology News"},
        {"title": "Stock market analysis", "source_platform": "financial news"},
        {"title": "Latest celebrity news", "source_platform": "entertainment news"}
    ]
    
    keywords, summary = extractor.extract_keywords_and_summary(test_news)
    
    print(f"Extracted keywords: {keywords}")
    print(f"News summary: {summary}")
    
    search_keywords = extractor.get_search_keywords(keywords)
    print(f"Search keywords: {search_keywords}")
