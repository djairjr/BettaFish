#MindSpider - an AI crawler specially designed for public opinion analysis

> Disclaimer:
> All contents in this warehouse are for learning and reference only and are not allowed to be used for commercial purposes. No person or organization may use the contents of this warehouse for illegal purposes or infringe upon the legitimate rights and interests of others. The crawler technology involved in this warehouse is only used for learning and research, and may not be used to conduct large-scale crawling of other platforms or other illegal activities. This warehouse does not assume any responsibility for any legal liability arising from the use of the contents of this warehouse. By using the content of this repository, you agree to all terms and conditions of this disclaimer.

## Project Overview

MindSpider is an intelligent public opinion crawler system based on Agent technology. It uses AI to automatically identify hot topics and accurately crawl content on multiple social media platforms. The system adopts a modular design and can realize a fully automated process from topic discovery to content collection.

This part learns from the well-known github crawler project [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)

Two-step crawling:

- Module 1: Search Agent identifies hot news from **13** social media platforms and technology forums including Weibo, Zhihu, GitHub, Kuan, etc., and maintains a daily topic analysis table.
- Module 2: Full-platform crawlers deeply crawl the fine-grained public opinion feedback of each topic.

<div align="center">
<img src="img\example.png" alt="banner" width="700">

MindSpider running example
</div>

### Technical architecture

- **Programming Language**: Python 3.9+
- **AI Framework**: Default is Deepseek, which can access multiple APIs (topic extraction and analysis)
- **Crawler Framework**: Playwright (browser automation)
- **Database**: MySQL (data persistence storage)
- **Concurrency processing**: AsyncIO (asynchronous concurrent crawling)

## Project structure

```
MindSpider/
├── BroadTopicExtraction/ # Topic extraction module
│ ├── database_manager.py # Database manager
│ ├── get_today_news.py # News collector
│ ├── main.py # Module main entrance
│ └── topic_extractor.py # AI topic extractor
│
├── DeepSentimentCrawling/ # Deep crawling module
│ ├── keyword_manager.py # Keyword manager
│ ├── main.py # Module main entrance
│ ├── platform_crawler.py # Platform crawler manager
│ └── MediaCrawler/ # Multi-platform crawler core
│ ├── base/ # base class
│ ├── cache/ # cache system
│ ├── config/ # Configuration file
│ ├── media_platform/ # Implementation of each platform
│ │ ├── bilibili/ # Bilibili Crawler
│ │ ├── douyin/ # Douyin crawler
│ │ ├── kuaishou/ # kuaishou crawler
│ │ ├── tieba/ # tieba crawler
│ │ ├── weibo/ # 微博 crawler
│ │ ├── xhs/ #小红书 crawler
│ │ └── zhihu/ # Zhihu Reptile
│ ├── model/ # Data model
│ ├── proxy/ # proxy management
│ ├── store/ # Storage layer
│ └── tools/ # toolset
│
├── schema/ # Database schema
│ ├── db_manager.py # Database management
│ ├── init_database.py # Initialization script
│ └── mindspider_tables.sql # Table structure definition
│
├── config.py # Global configuration file
├── main.py # System main entrance
├── requirements.txt # dependency list
└── README.md # Project documentation
```

## System workflow

### Overall architecture flow chart

```mermaid
flowchart TB
Start[Start] --> CheckConfig{Check configuration}
CheckConfig -->|Invalid configuration| ConfigError[Configuration error<br/>Please check the environment variables in env]
CheckConfig -->|Configuration is valid|InitDB[Initialize database]
    
InitDB --> BroadTopic[BroadTopicExtraction<br/>Topic extraction module]
    
BroadTopic --> CollectNews[Collect hot news]
CollectNews --> |Multi-platform collection| NewsSource{news source}
NewsSource --> Weibo[Weibo hot search]
NewsSource --> Zhihu[Zhihu Hot List]
NewsSource --> Bilibili[Bilibili Popular]
NewsSource --> Toutiao[Today's headlines]
NewsSource --> Other[Other platforms...]
    
Weibo --> SaveNews[Save news to database]
    Zhihu --> SaveNews
    Bilibili --> SaveNews
    Toutiao --> SaveNews
    Other --> SaveNews
    
SaveNews --> ExtractTopic[AI topic extraction]
ExtractTopic --> |DeepSeek API| GenerateKeywords[Generate keyword list]
GenerateKeywords --> GenerateSummary[Generate news summary]
GenerateSummary --> SaveTopics[save topic data]
    
SaveTopics --> DeepCrawl[DeepSentimentCrawling<br/>deep crawling module]
    
DeepCrawl --> LoadKeywords[Load keywords]
LoadKeywords --> PlatformSelect{Select crawling platform}
    
PlatformSelect --> XHS [Little Red Book Crawler]
PlatformSelect --> DY[Douyin crawler]
PlatformSelect --> KS[Kuaishou crawler]
PlatformSelect --> BILI [Bilibili Crawler]
PlatformSelect --> WB[Weibo crawler]
PlatformSelect --> TB [Tieba crawler]
PlatformSelect --> ZH[Zhihu crawler]
    
XHS --> Login{Need to log in?}
    DY --> Login
    KS --> Login
    BILI --> Login
    WB --> Login
    TB --> Login
    ZH --> Login
    
Login -->|Yes| QRCode[Scan code to log in]
Login -->|No| Search[keyword search]
    QRCode --> Search
    
Search --> CrawlContent[crawl content]
CrawlContent --> ParseData[parse data]
ParseData --> SaveContent[save to database]
    
SaveContent --> MoreKeywords{Are there more keywords?}
MoreKeywords -->|Yes| LoadKeywords
MoreKeywords -->|No| GenerateReport[Generate crawling report]
    
GenerateReport --> End[End]
    
    style Start fill:#90EE90
    style End fill:#FFB6C1
    style BroadTopic fill:#87CEEB,stroke:#000,stroke-width:3px
    style DeepCrawl fill:#DDA0DD,stroke:#000,stroke-width:3px
    style ExtractTopic fill:#FFD700
    style ConfigError fill:#FF6347
```

### Workflow description

#### 1. BroadTopicExtraction (topic extraction module)

This module is responsible for the automatic discovery and extraction of daily hot topics:

1. **News Collection**: Automatically collect hot news from multiple mainstream platforms (Weibo, Zhihu, Bilibili, etc.)
2. **AI Analysis**: Use DeepSeek API to conduct intelligent analysis of news
3. **Topic Extraction**: Automatically identify hot topics and generate related keywords
4. **Data Storage**: Save topics and keywords to the MySQL database

#### 2. DeepSentimentCrawling (deep crawling module)

Based on the extracted topic keywords, in-depth content crawling is performed on major social platforms:

1. **Keyword loading**: Read the keywords extracted on the day from the database
2. **Platform crawling**: Use Playwright to automate crawling on 7 major platforms
3. **Content Analysis**: Extract posts, comments, interaction data, etc.
4. **Emotional Analysis**: Analyze the emotional tendency of crawled content
5. **Data persistence**: Store all data in a structured manner in the database

## database schema

### Core data table

1. **daily_news** - Daily news table
- Store hot news collected from various platforms
- Contains title, link, description, ranking and other information

2. **daily_topics** - daily topic list
- Store topics and keywords extracted by AI
- Contains topic name, description, keyword list, etc.

3. **topic_news_relation** - Topic news correlation table
- Record the relationship between topics and news
- Contains relevance score

4. **crawling_tasks** - Crawling task list
- Manage crawling tasks for each platform
- Record task status, progress, results, etc.

5. **Platform content table** (inherited from MediaCrawler)
- xhs_note - Xiaohongshu notes (temporarily abandoned, see details: https://github.com/NanmiCoder/MediaCrawler/issues/754)
- douyin_aweme - Douyin video
- kuaishou_video - Kuaishou video
- bilibili_video - B station video
- weibo_note - Weibo post
- tieba_note - Tieba post
- zhihu_content - Zhihu content

## Installation and deployment

### Environmental requirements

- Python 3.9 or higher
- MySQL 5.7 or higher, or PostgreSQL
- Conda environment: pytorch_python11 (recommended)
- Operating system: Windows/Linux/macOS


### 1. Clone project

```bash
git clone https://github.com/yourusername/MindSpider.git
cd MindSpider
```

### 2. Create and activate the environment

#### Conda configuration method

#### Conda configuration method

```bash
# Create a conda environment named pytorch_python11 and specify the Python version
conda create -n pytorch_python11 python=3.11
# Activate the environment
conda activate pytorch_python11
```

#### UV configuration method

> [UV is a fast and lightweight Python package environment management tool, suitable for low dependency and convenient management needs. Please refer to: https://github.com/astral-sh/uv]

- Install uv (if not installed)
```bash
pip install uv
```
- Create virtual environment and activate it
```bash
uv venv --python 3.11 # Create a 3.11 environment
source .venv/bin/activate   # Linux/macOS
# or
.venv\Scripts\activate      # Windows
```


### 3. Install dependencies

```bash
#Install Python dependencies
pip install -r requirements.txt

or
#uv version is faster
uv pip install -r requirements.txt


# Install Playwright browser driver
playwright install
```

### 4. Configure the system

Copy the .env.example file to a .env file and place it in the project root directory. Edit the `.env` file and set the database and API configuration:

```python
# MySQL database configuration
DB_HOST = "your_database_host"
DB_PORT = 3306
DB_USER = "your_username"
DB_PASSWORD = "your_password"
DB_NAME = "mindspider"
DB_CHARSET = "utf8mb4"

#MINDSPIDER API key
MINDSPIDER_BASE_URL=your_api_base_url
MINDSPIDER_API_KEY=sk-your-key
MINDSPIDER_MODEL_NAME=deepseek-chat
```

### 5. Initialize the system

```bash
# Check system status
python main.py --status
```

## User Guide

### Complete process

```bash
# 1. Run topic extraction (get hot news and keywords)
python main.py --broad-topic

# 2. Run the crawler (crawl content from each platform based on keywords)
python main.py --deep-sentiment --test

# Or run the entire process at once
python main.py --complete --test
```

### Using modules alone

```bash
# Get only today’s hot topics and keywords
python main.py --broad-topic

# Only crawl specific platforms
python main.py --deep-sentiment --platforms xhs dy --test

#Specify date
python main.py --broad-topic --date 2024-01-15
```

## Crawler configuration (important)

### Platform login configuration

**Every first time you use each platform you need to log in, this is the most critical step:**

1. **Xiaohongshu Login** (temporarily abandoned, see details: https://github.com/NanmiCoder/MediaCrawler/issues/754)
```bash
# Test Xiaohongshu crawling (QR code will pop up)
python main.py --deep-sentiment --platforms xhs --test
# Use Xiaohongshu APP to scan the QR code to log in. The status will be automatically saved after successful login.
```

2. **Douyin login**
```bash
# Test Douyin crawling
python main.py --deep-sentiment --platforms dy --test
# Use Douyin APP to scan the code to log in
```

3. **Similar to other platforms**
```bash
# Kuaishou
python main.py --deep-sentiment --platforms ks --test

# Bilibili
python main.py --deep-sentiment --platforms bili --test

#微博
python main.py --deep-sentiment --platforms wb --test

# Tieba
python main.py --deep-sentiment --platforms tieba --test

# Zhihu
python main.py --deep-sentiment --platforms zhihu --test
```

### Troubleshooting login issues

**If login fails or gets stuck:**

1. **Check the network**: Make sure you can access the corresponding platform normally
2. **Turn off headless mode**: Edit `DeepSentimentCrawling/MediaCrawler/config/base_config.py`
   ```python
HEADLESS = False # Change to False to see the browser interface
   ```
3. **Manual processing of verification**: Some platforms may require manual sliding verification code
4. **Re-login**: Delete the `DeepSentimentCrawling/MediaCrawler/browser_data/` directory and log in again

### Other questions

https://github.com/666ghj/BettaFish/issues/185

### Crawling parameter adjustment

It is recommended to adjust the crawling parameters before actual use:

```bash
# Small-scale testing (recommended to test like this first)
python main.py --complete --test

#Adjust the number of crawls
python main.py --complete --max-keywords 20 --max-notes 30
```

### Advanced features

#### 1. Specify date operation
```bash
# Extract topics on the specified date
python main.py --broad-topic --date 2024-01-15

# Crawl the content of the specified date
python main.py --deep-sentiment --date 2024-01-15
```

#### 2. Specify platform crawling
```bash
# Only crawl Bilibili and Douyin
python main.py --deep-sentiment --platforms bili dy --test

# Crawl a specific amount of content across all platforms
python main.py --deep-sentiment --max-keywords 30 --max-notes 20
```

## Common parameters

```bash
--status # Check project status
--setup #Initialize project (obsolete, automatically initialized)
--broad-topic # Topic extraction
--deep-sentiment #crawler module
--complete # complete process
--test #Test mode (small amount of data)
--platforms xhs dy #Specify platform
--date 2024-01-15 #Specify date
```

## Supported platforms

| code | platform | code | platform |
|-----|-----|-----|-----|
| xhs | Xiaohongshu | wb | Weibo |
| dy | Douyin | tieba | Tieba |
| ks | Kuaishou | zhihu | Zhihu |
| bili | Bilibili | | |

## FAQ

### 1. Crawler login failed
```bash
# Problem: QR code does not display or login fails
# Solution: Turn off headless mode and log in manually
# Edit: DeepSentimentCrawling/MediaCrawler/config/base_config.py
HEADLESS = False

# Rerun login
python main.py --deep-sentiment --platforms xhs --test
```

### 2. Database connection failed
```bash
# Check configuration
python main.py --status

# Check whether the database configuration in config.py is correct
```

### 3. playwright installation failed
```bash
# Reinstall
pip install playwright

or

uv pip install playwright

playwright install
```

### 4. The crawled data is empty
- Make sure you have logged in successfully to the platform
- Check if the keyword exists (run topic extraction first)
- Verify using test mode: `--test`

### 5. API call failed
- Check if the DeepSeek API key is correct
- Confirm whether the API quota is sufficient

## Notes

1. **You must log in to each platform before using it for the first time**
2. **It is recommended to verify using test mode first**
3. **Abide by the platform usage rules**
4. **For study and research purposes only**

## Project Development Guide

### Expand new news sources

Add new news source in `BroadTopicExtraction/get_today_news.py`:

```python
async def get_new_platform_news(self) -> List[Dict]:
"""Get the hot news on the new platform"""
# Implement news collection logic
    pass
```

### Expand new crawler platform

1. Create a new platform directory under `DeepSentimentCrawling/MediaCrawler/media_platform/`
2. Implement the core functional modules of the platform:
- `client.py`: API client
- `core.py`: crawler core logic
- `login.py`: login logic
- `field.py`: data field definition

### Database extension

To add new data tables or fields, update `schema/mindspider_tables.sql` and run:

```bash
python schema/init_database.py
```

## Performance optimization suggestions

1. **Database Optimization**
- Regularly clean historical data
- Create indexes for frequently queried fields
- Consider using partitioned tables to manage large amounts of data

2. **Crawling Optimization**
- Set crawling intervals reasonably to avoid being restricted
- Use proxy pool to improve stability
- Control the number of concurrencies to avoid resource exhaustion

3. **System Optimization**
- Use Redis to cache hotspot data
- Asynchronous task queue processing time-consuming operations
- Regularly monitor system resource usage

## API interface description

The system provides Python API for secondary development:

```python
from BroadTopicExtraction import BroadTopicExtraction
from DeepSentimentCrawling import DeepSentimentCrawling

# Topic extraction
async def extract_topics():
    extractor = BroadTopicExtraction()
    result = await extractor.run_daily_extraction()
    return result

# Content crawling
def crawl_content():
    crawler = DeepSentimentCrawling()
    result = crawler.run_daily_crawling(
        platforms=['xhs', 'dy'],
        max_keywords=50,
        max_notes=30
    )
    return result
```

## License

This project is for study and research only, please do not use it for commercial purposes. Please abide by relevant laws, regulations and platform service terms when using this project.

---

**MindSpider** - Let AI help public opinion insights and be a powerful assistant for intelligent content analysis
