# How to use MediaCrawler

## Create and activate python virtual environment
> If you are crawling Douyin and Zhihu, you need to install the nodejs environment in advance. The version is greater than or equal to: `16` <br>
   ```shell   
# Enter the project root directory
   cd MediaCrawler
   
#Create virtual environment
# My python version is: 3.9.6. The library in requirements.txt is based on this version. If it is other python versions, the library in requirements.txt may not be compatible. Please solve it yourself.
   python -m venv venv
   
# macos & linux activate virtual environment
   source venv/bin/activate

# windows activate virtual environment
   venv\Scripts\activate

   ```

## Install dependent libraries

   ```shell
   pip install -r requirements.txt
   ```

## Install playwright browser driver

   ```shell
   playwright install
   ```

## Run the crawler program

   ```shell
### By default, the comment crawling mode is not enabled for the project. If you need to comment, please modify the ENABLE_GET_COMMENTS variable in config/base_config.py
### For some other support items, you can also view the functions in config/base_config.py, which are written with Chinese comments.
   
# Read keywords from the configuration file to search for related posts and crawl post information and comments
   python main.py --platform xhs --lt qrcode --type search
   
# Read the specified post ID list from the configuration file to obtain the information and comment information of the specified post.
   python main.py --platform xhs --lt qrcode --type detail
   
# Use SQLite database to store data (recommended for individual users)
   python main.py --platform xhs --lt qrcode --type search --save_data_option sqlite
   
# Use MySQL database to store data
   python main.py --platform xhs --lt qrcode --type search --save_data_option db
  
# Open the corresponding APP and scan the QR code to log in
     
# For other platform crawler usage examples, execute the following command to view
   python main.py --help    
   ```

## 💾 Data storage

Supports multiple data storage methods:
- **CSV file**: supports saving to CSV (located in the `data/` directory)
- **JSON file**: supports saving to JSON (located in the `data/` directory)
- **Database Storage**
- Use the `--init_db` parameter for database initialization (no other optional parameters are required when using `--init_db`)
- **SQLite database**: lightweight database, no server required, suitable for personal use (recommended)
1. Initialization: `--init_db sqlite`
2. Data storage: `--save_data_option sqlite`
- **MySQL database**: Supports saving to relational database MySQL (database needs to be created in advance)
1. Initialization: `--init_db mysql`
2. Data storage: `--save_data_option db` (the db parameter is reserved for compatibility with historical updates)

## Disclaimer
> **Disclaimer:**
> 
> Please use this repository for the purpose of learning. Cases of illegal crawlers: https://github.com/HiddenStrawberry/Crawler_Illegal_Cases_In_China <br>
>
>All contents of this project are for learning and reference only and are not allowed to be used for commercial purposes. No person or organization may use the contents of this warehouse for illegal purposes or infringe upon the legitimate rights and interests of others. The crawler technology involved in this warehouse is only used for learning and research, and may not be used to conduct large-scale crawling of other platforms or other illegal activities. This warehouse does not assume any responsibility for any legal liability arising from the use of the contents of this warehouse. By using the content of this repository, you agree to all terms and conditions of this disclaimer.

