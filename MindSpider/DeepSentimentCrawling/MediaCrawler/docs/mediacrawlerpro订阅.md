# Subscribe to MediaCrawlerPro version source code access rights

## Get access to Pro version
> MediaCrawler has been open source for more than a year. I believe this warehouse has helped many friends learn and understand crawlers at a low threshold. Maintenance really consumes a lot of energy and manpower <br>
> 
> So the Pro version will not be open source. Being able to subscribe to the Pro version makes me more motivated to update. <br>
> 
> If you are interested, you can add me on WeChat and subscribe to the Pro version for access. There is a threshold💰. <br>
> 
> Only for users who want to learn the source code implementation of the Pro version. If you are a company or commercial profit-making company, please do not add me. Thank you🙏
> 
> The code design is highly scalable. You can expand more crawler platforms and more data storage methods by yourself. I believe it will be helpful to you in building this kind of crawler code.
> 
> 
> **MediaCrawlerPro project homepage address**
> [MediaCrawlerPro Github homepage address](https://github.com/MediaCrawlerPro)



Scan my personal WeChat ID below, note: pro version (if the picture cannot be displayed, you can directly add my WeChat ID: relakkes)

![relakkes_weichat.JPG](static/images/relakkes_weichat.jpg)


## Background of the birth of Pro version
[MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) This open source project has received a lot of attention so far, and has also exposed a series of problems, such as:
- Can it support multiple accounts?
- Can it be deployed on linux?
- Can I remove the dependency on playwright?
- Is there an easier way to deploy?
- Is there any way to lower the entry barrier for novices?

If you want to solve problems like the above on the original project, it will undoubtedly increase the complexity and may make subsequent maintenance more difficult.
MediaCrawler is completely restructured for the purpose of sustainable maintenance, ease of use, and simple deployment.

## Project introduction
### Pro version python implementation of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)
**Xiaohongshu crawler**, **Douyin crawler**, **Kuaishou crawler**, **B station crawler**, **Weibo crawler**, **Baidu Tieba**, **Zhihu crawler**....

It supports crawlers on multiple platforms, supports crawling of multiple data, and supports storage of multiple data. The most important thing is that it perfectly supports multiple accounts + IP proxy pools to make your crawlers more stable**.
Compared with MediaCrawler, the biggest changes in the Pro version are:
- Removed the dependency on playwright and no longer integrates Playwright into the crawler trunk. The dependency is too heavy.
- Added Docker and Docker-compose deployment methods to make deployment easier.
- Support for multiple accounts + IP proxy pool makes the crawler more stable.
- Added a new signature service to decouple the signature logic and make the crawler more flexible.
