## Wandou HTTP proxy usage documentation (only supports enterprise users)

## Prepare proxy IP information
Click <a href="https://h.wandouip.com?invite_code=rtnifi">Wandouip HTTP Proxy</a> to register on the official website and perform real-name authentication (real-name is required to use proxy IP in China, everyone knows it)

## Get the key information of the IP proxy appkey
Get a free trial from the <a href="https://h.wandouip.com?invite_code=rtnifi">Wandouip HTTP Proxy</a> official website, as shown below
![img.png](static/images/wd_http_img.png)

Choose the package you need
![img_4.png](static/images/wd_http_img_4.png)


An example of initializing a Wandou HTTP proxy, as shown in the following code, requires 1 parameter: app_key

```python
# File address: proxy/providers/wandou_http_proxy.py
# -*- coding: utf-8 -*-

def new_wandou_http_proxy() -> WanDouHttpProxy:
    """
Construct Wandou HTTP instance
    Returns:

    """
    return WanDouHttpProxy(
        app_key=os.getenv(
"wandou_app_key", "your pea HTTP app_key"
), # Get Wandou HTTP app_key through environment variables
    )

```

Find `app_key` in the `Open Interface` of the personal center, as shown in the figure below

![img_2.png](static/images/wd_http_img_2.png)


