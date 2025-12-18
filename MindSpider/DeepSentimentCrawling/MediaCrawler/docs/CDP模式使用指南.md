# CDP mode usage guide

## Overview

CDP (Chrome DevTools Protocol) mode is an advanced anti-detection crawler technology that crawls web pages by controlling the user's existing Chrome/Edge browser. Compared with traditional Playwright automation, CDP mode has the following advantages:

### 🎯 Main advantages

1. **Real browser environment**: Use the browser actually installed by the user, including all extensions, plug-ins and personal settings
2. **Better anti-detection capabilities**: Browser fingerprints are more realistic and difficult to be detected by websites as automated tools
3. **Retain user status**: Automatically inherit the user's login status, cookies and browsing history
4. **Extended support**: You can take advantage of user-installed ad blockers, proxy extensions and other tools
5. **More natural behavior**: Browser behavior patterns are closer to real users

## Quick Start

### 1. Enable CDP mode

Set in `config/base_config.py`:

```python
# Enable CDP mode
ENABLE_CDP_MODE = True

# CDP debugging port (optional, default 9222)
CDP_DEBUG_PORT = 9222

# Whether to run in headless mode (it is recommended to set it to False for the best anti-detection effect)
CDP_HEADLESS = False

# Whether to automatically close the browser when the program ends
AUTO_CLOSE_BROWSER = True
```

### 2. Run the test

```bash
#Run CDP functional test
python examples/cdp_example.py

# Run Xiaohongshu crawler (CDP mode)
python main.py
```

## Detailed explanation of configuration options

### Basic configuration

| Configuration item | Type | Default value | Description |
|--------|------|--------|------|
| `ENABLE_CDP_MODE` | bool | False | Whether to enable CDP mode |
| `CDP_DEBUG_PORT` | int | 9222 | CDP debug port |
| `CDP_HEADLESS` | bool | False | Headless mode in CDP mode |
| `AUTO_CLOSE_BROWSER` | bool | True | Whether to close the browser when the program ends |

### Advanced configuration

| Configuration item | Type | Default value | Description |
|--------|------|--------|------|
| `CUSTOM_BROWSER_PATH` | str | "" | Custom browser path |
| `BROWSER_LAUNCH_TIMEOUT` | int | 30 | Browser startup timeout (seconds) |

### Custom browser path

If the system's automatic detection fails, you can manually specify the browser path:

```python
# Windows example
CUSTOM_BROWSER_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# macOS example
CUSTOM_BROWSER_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Linux example
CUSTOM_BROWSER_PATH = "/usr/bin/google-chrome"
```

## Supported browsers

### Windows
- Google Chrome (Stable, Beta, Dev, Canary)
- Microsoft Edge (Stable, Beta, Dev, Canary)

### macOS
- Google Chrome (Stable, Beta, Dev, Canary)
- Microsoft Edge (Stable, Beta, Dev, Canary)

### Linux
- Google Chrome / Chromium
- Microsoft Edge

## Usage example

### Basic usage

```python
import asyncio
from playwright.async_api import async_playwright
from tools.cdp_browser import CDPBrowserManager

async def main():
    cdp_manager = CDPBrowserManager()
    
    async with async_playwright() as playwright:
# Start CDP browser
        browser_context = await cdp_manager.launch_and_connect(
            playwright=playwright,
user_agent="Custom User-Agent",
            headless=False
        )
        
#Create a page and visit the website
        page = await browser_context.new_page()
        await page.goto("https://example.com")
        
# Execute crawling operation...
        
# Clean up resources
        await cdp_manager.cleanup()

asyncio.run(main())
```

### Used in crawlers

CDP mode is integrated into all platform crawlers, just enable the configuration:

```python
# In config/base_config.py
ENABLE_CDP_MODE = True

# Then run the crawler normally
python main.py
```

## troubleshooting

### FAQ

#### 1. Browser detection failed
**Error**: `No available browser found`

**Solution**:
- Make sure you have Chrome or Edge browser installed
- Check if the browser is under the standard path
- Use `CUSTOM_BROWSER_PATH` to specify the browser path

#### 2. The port is occupied
**ERROR**: `Unable to find available port`

**Solution**:
- Close other programs using the debug port
- Modify `CDP_DEBUG_PORT` to other ports
- The system will automatically try the next available port

#### 3. Browser startup timeout
**Error**: `The browser failed to start within 30 seconds`

**Solution**:
- Increase `BROWSER_LAUNCH_TIMEOUT` value
- Check whether system resources are sufficient
- Try closing other resource-hogging programs

#### 4. CDP connection failed
**ERROR**: `CDP connection failed`

**Solution**:
- Check firewall settings
- Make sure localhost access is normal
- Try restarting the browser

### Debugging Tips

#### 1. Enable detailed logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### 2. Manually test CDP connection
```bash
# Start Chrome manually
chrome --remote-debugging-port=9222

#Access debugging page
curl http://localhost:9222/json
```

#### 3. Check browser process
```bash
# Windows
tasklist | findstr chrome

# macOS/Linux  
ps aux | grep chrome
```

## Best Practices

### 1. Anti-detection optimization
- Keep `CDP_HEADLESS = False` for best anti-detection results
- Use real User-Agent string
- Avoid too frequent requests

### 2. Performance optimization
- Properly set `AUTO_CLOSE_BROWSER`
- Reuse browser instances instead of restarting frequently
- Monitor memory usage

### 3. Security considerations
- Do not save sensitive cookies in production environments
- Clean browser data regularly
- Pay attention to user privacy protection

### 4. Compatibility
- Test compatibility of different browser versions
- Prepare fallback scenarios (standard Playwright mode)
- Monitor changes in anti-crawling strategies of target websites

## Technical principles

How the CDP model works:

1. **Browser Detection**: Automatically scan the Chrome/Edge installation path in the system
2. **Process Start**: Use the `--remote-debugging-port` parameter to start the browser
3. **CDP connection**: Connect to the browser’s debugging interface through WebSocket
4. **Playwright Integration**: Use the `connectOverCDP` method to take over browser control
5. **Context Management**: Create or reuse browser context for operations

This method bypasses the traditional WebDriver detection mechanism and provides more covert automation capabilities.

## Update log

### v1.0.0
- Initial version release
- Supports Chrome/Edge detection for Windows and macOS
- Integrated into all platform crawlers
- Provides complete configuration options and error handling

## contribute

Welcome to submit Issues and Pull Requests to improve CDP mode functions.

## License

This feature is subject to the overall license terms of the project and is for learning and research use only.
