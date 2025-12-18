# 🔥 MediaCrawler - self-media platform crawler 🕷️

<div align="center" markdown="1">
   <sup>Special thanks to:</sup>
   <br>
   <br>
   <a href="https://go.warp.dev/MediaCrawler">
      <img alt="Warp sponsorship" width="400" src="https://github.com/warpdotdev/brand-assets/blob/main/Github/Sponsor/Warp-Github-LG-02.png?raw=true">
   </a>

### [Warp is built for coding with multiple AI agents](https://go.warp.dev/MediaCrawler)


</div>
<hr>

<div align="center">

<a href="https://trendshift.io/repositories/8291" target="_blank">
  <img src="https://trendshift.io/api/badge/repositories/8291" alt="NanmiCoder%2FMediaCrawler | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/>
</a>

[![GitHub Stars](https://img.shields.io/github/stars/NanmiCoder/MediaCrawler?style=social)](https://github.com/NanmiCoder/MediaCrawler/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/NanmiCoder/MediaCrawler?style=social)](https://github.com/NanmiCoder/MediaCrawler/network/members)
[![GitHub Issues](https://img.shields.io/github/issues/NanmiCoder/MediaCrawler)](https://github.com/NanmiCoder/MediaCrawler/issues)
[![GitHub Pull Requests](https://img.shields.io/github/issues-pr/NanmiCoder/MediaCrawler)](https://github.com/NanmiCoder/MediaCrawler/pulls)
[![License](https://img.shields.io/github/license/NanmiCoder/MediaCrawler)](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE)
[![中文](https://img.shields.io/badge/🇨🇳_中文-current-blue)](README.md)
[![English](https://img.shields.io/badge/🇺🇸_English-Available-green)](README_en.md)
[![Español](https://img.shields.io/badge/🇪🇸_Español-Available-green)](README_es.md)
</div>



> **Disclaimer:**
> 
> Please use this repository for learning purposes ⚠️⚠️⚠️⚠️, [Crawler illegal cases](https://github.com/HiddenStrawberry/Crawler_Illegal_Cases_In_China) <br>
>
>All contents in this warehouse are for learning and reference only and are not allowed to be used for commercial purposes. No person or organization may use the contents of this warehouse for illegal purposes or infringe upon the legitimate rights and interests of others. The crawler technology involved in this warehouse is only used for learning and research, and may not be used to conduct large-scale crawling of other platforms or other illegal activities. This warehouse does not assume any responsibility for any legal liability arising from the use of the contents of this warehouse. By using the content of this repository, you agree to all terms and conditions of this disclaimer.
>
> Click for a more detailed disclaimer. [Click to jump](#disclaimer)




## 📖Project Introduction

A powerful **multi-platform self-media data collection tool** that supports the capture of public information from mainstream platforms such as Xiaohongshu, Douyin, Kuaishou, Bilibili, Weibo, Tieba, and Zhihu.

### 🔧 Technical principles

- **Core Technology**: Based on [Playwright](https://playwright.dev/) browser automation framework login to save login status
- **No need for JS reverse engineering**: Use the browser context that retains the login state to obtain signature parameters through JS expressions
- **Advantages**: No need to reverse complex encryption algorithms, greatly reducing the technical threshold

## ✨ Features
| Platform | Keyword search | Crawling of specified post ID | Secondary comments | Specified creator homepage | Login state cache | IP proxy pool | Generate comment word cloud |
| ------ | ---------- | -------------- | -------- | -------------- | ---------- | -------- | -------------- |
| Little Red Book | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Tik Tok | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Kuaishou | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Bilibili | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Weibo | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Tieba | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Zhihu | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |



### 🚀 MediaCrawlerPro is released!

> Focus on learning the architecture design of mature projects, not just crawler technology, the code design ideas of the Pro version are also worth learning in depth!

The core advantages of [MediaCrawlerPro](https://github.com/MediaCrawlerPro) compared to the open source version:

#### 🎯Core function upgrade
- ✅ **Breakpoint resume function** (key feature)
- ✅ **Multiple accounts + IP proxy pool support** (key features)
- ✅ **Remove Playwright dependency**, easier to use
- ✅ **Full Linux environment support**

#### 🏗️ Architecture design optimization
- ✅ **Code refactoring and optimization**, easier to read and maintain (decoupled JS signature logic)
- ✅ **Enterprise-level code quality**, suitable for building large-scale crawler projects
- ✅ **Perfect architecture design**, high scalability, greater source code learning value

#### 🎁 Extra features
- ✅ **Self-media video downloader desktop** (suitable for learning full-stack development)
- ✅ **Multi-platform homepage information flow recommendation** (HomeFeed)
- [ ] **AI Agent based on self-media platform is under development 🚀🚀**

Click to view: [MediaCrawlerPro project homepage](https://github.com/MediaCrawlerPro) More introduction


## 🚀 Quick Start

> 💡 **Open source is not easy. If this project is helpful to you, please give it a ⭐ Star to support it! **

## 📋 Prerequisites

### 🚀 uv installation (recommended)

Before proceeding to the next step, please make sure that uv is installed on your computer:

- **Installation address**: [uv official installation guide](https://docs.astral.sh/uv/getting-started/installation)
- **Verify installation**: Enter the command `uv --version` in the terminal. If the version number is displayed normally, it proves that the installation has been successful.
- **Reason for recommendation**: uv is currently the most powerful Python package management tool, with fast speed and accurate dependency analysis.

### 🟢 Node.js installation

The project depends on Node.js, please go to the official website to download and install:

- **Download address**: https://nodejs.org/en/download/
- **Version Requirements**: >= 16.0.0

### 📦 Python package installation

```shell
# Enter the project directory
cd MediaCrawler

# Use the uv sync command to ensure the consistency of the python version and related dependency packages
uv sync
```

### 🌐 Browser driver installation

```shell
#Install browser driver
uv run playwright install
```

> **💡 Tip**: MediaCrawler now supports using playwright to connect to your local Chrome browser, and some problems caused by Webdriver have been solved.
>
> Currently, `xhs` and `dy` are enabled to use CDP to connect to local browsers. If necessary, check the configuration items in `config/base_config.py`.

## 🚀 Run the crawler program

```shell
# The project does not enable comment crawling mode by default. If you need comments, please modify the ENABLE_GET_COMMENTS variable in config/base_config.py
# For some other support items, you can also view the functions in config/base_config.py, which are written with Chinese comments.

# Read keywords from the configuration file to search for related posts and crawl post information and comments
uv run main.py --platform xhs --lt qrcode --type search

# Read the specified post ID list from the configuration file to obtain the information and comment information of the specified post.
uv run main.py --platform xhs --lt qrcode --type detail

# Open the corresponding APP and scan the QR code to log in

# For other platform crawler usage examples, execute the following command to view
uv run main.py --help
```

<details>
<summary>🔗 <strong>Use Python native venv to manage the environment (not recommended)</strong></summary>

#### Create and activate Python virtual environment

> If you are crawling Douyin and Zhihu, you need to install the nodejs environment in advance. The version is greater than or equal to: `16`.

```shell
# Enter the project root directory
cd MediaCrawler

#Create virtual environment
# My python version is: 3.9.6, the library in requirements.txt is based on this version
# If it is another python version, the library in requirements.txt may be incompatible, and you need to solve it yourself.
python -m venv venv

# macOS & Linux Activate virtual environment
source venv/bin/activate

# Windows activate virtual environment
venv\Scripts\activate
```

#### Install dependent libraries

```shell
pip install -r requirements.txt
```

#### Install playwright browser driver

```shell
playwright install
```

#### Run the crawler program (native environment)

```shell
# The project does not enable comment crawling mode by default. If you need comments, please modify the ENABLE_GET_COMMENTS variable in config/base_config.py
# For some other support items, you can also view the functions in config/base_config.py, which are written with Chinese comments.

# Read keywords from the configuration file to search for related posts and crawl post information and comments
python main.py --platform xhs --lt qrcode --type search

# Read the specified post ID list from the configuration file to obtain the information and comment information of the specified post.
python main.py --platform xhs --lt qrcode --type detail

# Open the corresponding APP and scan the QR code to log in

# For other platform crawler usage examples, execute the following command to view
python main.py --help
```

</details>


## 💾 Data Saving

Supports multiple data storage methods:
- **CSV file**: supports saving to CSV (under the `data/` directory)
- **JSON file**: supports saving to JSON (under the `data/` directory)
- **Database Storage**
- Use parameter `--init_db` for database initialization (no need to carry other optionals when using `--init_db`)
- **SQLite database**: lightweight database, no server required, suitable for personal use (recommended)
1. Initialization: `--init_db sqlite`
2. Data storage: `--save_data_option sqlite`
- **MySQL database**: Supports saving in relational database MySQL (the database needs to be created in advance)
1. Initialization: `--init_db mysql`
2. Data storage: `--save_data_option db` (the db parameter is reserved for compatibility with historical updates)


### Usage example:
```shell
# Initialize the SQLite database (no need to carry other optionals when using '--init_db')
uv run main.py --init_db sqlite
# Use SQLite to store data (recommended for individual users)
uv run main.py --platform xhs --lt qrcode --type search --save_data_option sqlite
```
```shell
# Initialize MySQL database
uv run main.py --init_db mysql
# Use MySQL to store data (to adapt to historical updates, the db parameter will be used)
uv run main.py --platform xhs --lt qrcode --type search --save_data_option db
```


[🚀 MediaCrawlerPro big release 🚀! More functions, better architectural design! ](https://github.com/MediaCrawlerPro)


### 💬 Communication group
- **WeChat communication group**: [Click to join](https://nanmicoder.github.io/MediaCrawler/%E5%BE%AE%E4%BF%A1%E4%BA%A4%E6%B5%81%E7%BE%A4.html)

### 📚 Others
- **FAQ**: [MediaCrawler full documentation](https://nanmicoder.github.io/MediaCrawler/)
- **Introduction to crawler tutorial**: [CrawlerTutorial free tutorial](https://github.com/NanmiCoder/CrawlerTutorial)
- **News crawler open source project**: [NewsCrawlerCollection](https://github.com/NanmiCoder/NewsCrawlerCollection)
---

### 💰 Sponsor Showcase

<a href="https://h.wandouip.com">
<img src="docs/static/images/img_8.jpg">
<br>
Wandou HTTP operates a tens-of-million-level IP resource pool with an IP purity of ≥99.8%. It maintains high-frequency IP updates every day, provides fast response, and stable connections to meet a variety of business scenarios. It supports on-demand customization and registers to extract 10,000 IPs for free.
</a>

---

<p align="center">
  <a href="https://tikhub.io/?utm_source=github.com/NanmiCoder/MediaCrawler&utm_medium=marketing_social&utm_campaign=retargeting&utm_content=carousel_ad">
    <img style="border-radius:20px" width="500" alt="TikHub IO_Banner zh" src="docs/static/images/tikhub_banner_zh.png">
  </a>
</p>

[TikHub](https://tikhub.io/?utm_source=github.com/NanmiCoder/MediaCrawler&utm_medium=marketing_social&utm_campaign=retargeting&utm_content=carousel_ad) provides over **700 endpoints** for obtaining and analyzing data from **14+ social media platforms** —— Including videos, users, comments, stores, products and trends, etc., complete all data access and analysis in one stop.

By checking in every day, you can get free quota. You can use my registration link: [https://user.tikhub.io/users/signup?referral_code=cfzyejV9](https://user.tikhub.io/users/signup?referral_code=cfzye jV9&utm_source=github.com/NanmiCoder/MediaCrawler&utm_medium=marketing_social&utm_campaign=retargeting&utm_content=carousel_ad) Or use the invitation code: `cfzyejV9`, register and recharge to get **$2 free credit**.

[TikHub](https://tikhub.io/?utm_source=github.com/NanmiCoder/MediaCrawler&utm_medium=marketing_social&utm_campaign=retargeting&utm_content=carousel_ad) provides the following services:

- 🚀 Rich social media data interface (TikTok, Douyin, XHS, YouTube, Instagram, etc.)
- 💎 Sign in daily to receive free quota
- ⚡ High success rate and high concurrency support
- 🌐 Official website: [https://tikhub.io/](https://tikhub.io/?utm_source=github.com/NanmiCoder/MediaCrawler&utm_medium=marketing_social&utm_campaign=retargeting&utm_content=carousel_ad)
- 💻 GitHub address: [https://github.com/TikHubIO/](https://github.com/TikHubIO/)

---
<p align="center">
  <a href="https://app.nstbrowser.io/account/register?utm_source=official&utm_term=mediacrawler">
    <img style="border-radius:20px"  alt="NstBrowser Banner " src="docs/static/images/nstbrowser.jpg">
  </a>
</p>

Nstbrowser fingerprint browser - the best solution for multi-account operation & automated management
<br>
Multi-account security management and session isolation; fingerprint customization combined with anti-detection browser environment, taking into account authenticity and stability; covering business lines such as store management, e-commerce monitoring, social media marketing, ad verification, Web3, delivery monitoring and affiliate marketing; providing production-level concurrency and customized enterprise services; providing a cloud browser solution that can be deployed with one click, supporting a global high-quality IP pool, to build your long-term industry competitiveness
<br>
[Click here to start using it for free now](https://app.nstbrowser.io/account/register?utm_source=official&utm_term=mediacrawler)
<br>
Use NSTBROWSER to get 10% recharge gift



### 🤝 Become a sponsor

Become a patron and get your products featured here and get tons of exposure every day!

**Contact Information**:
- WeChat: `relakkes`
- Email: `relakkes@gmail.com`

---

## ⭐ Star Trend Chart

If this project is helpful to you, please give a ⭐ Star to support it and let more people see MediaCrawler!

[![Star History Chart](https://api.star-history.com/svg?repos=NanmiCoder/MediaCrawler&type=Date)](https://star-history.com/#NanmiCoder/MediaCrawler&Date)



## 📚 Reference

- **Xiaohongshu client**: [ReaJason’s xhs warehouse](https://github.com/ReaJason/xhs)
- **SMS forwarding**: [SmsForwarder reference warehouse](https://github.com/pppscn/SmsForwarder)
- **Intranet penetration tool**: [ngrok official document](https://ngrok.com/docs/)


# Disclaimer
<div id="disclaimer"> 

## 1. Project purpose and nature
This project (hereinafter referred to as "the project") was created as a technical research and learning tool to explore and learn network data collection technology. This project focuses on the research on data crawling technology of self-media platforms, aiming to provide it to learners and researchers for technical communication purposes.

## 2. Legal Compliance Statement
The developer of this project (hereinafter referred to as the "Developer") solemnly reminds users to strictly abide by the relevant laws and regulations of the People's Republic of China when downloading, installing and using this project, including but not limited to the "Cybersecurity Law of the People's Republic of China", the "Counterespionage Law of the People's Republic of China" and all applicable national laws and policies. The user shall bear all legal responsibilities that may arise from the use of this project.

## 3. Restrictions on purpose of use
This project is strictly prohibited from being used for any illegal purposes or commercial activities other than learning or research. This project may not be used for any form of illegal intrusion into other people's computer systems, or for any infringement of other people's intellectual property rights or other legitimate rights and interests. Users should ensure that their use of this project is purely for personal study and technical research and shall not be used for any form of illegal activities.

## 4. Disclaimer
The developer has tried its best to ensure the legitimacy and safety of this project, but is not responsible for any form of direct or indirect losses that may be caused by the user's use of this project. Including but not limited to any data loss, equipment damage, legal proceedings, etc. resulting from the use of this project.

## 5. Intellectual Property Statement
The intellectual property rights of this project belong to the developer. This project is protected by copyright law and international copyright treaties, as well as other intellectual property laws and treaties. Users may download and use this project on the premise of complying with this statement and relevant laws and regulations.

## 6. Final interpretation right
The final right of interpretation on this project belongs to the developer. The Developer reserves the right to change or update this disclaimer at any time without prior notice.
</div>
