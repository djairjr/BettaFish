# Disclaimer: This code is for learning and research purposes only. Users should abide by the following principles:
# 1. Not for any commercial purposes.
# 2. When using, you should comply with the terms of use and robots.txt rules of the target platform.
# 3. Do not conduct large-scale crawling or cause operational interference to the platform.
# 4. The request frequency should be reasonably controlled to avoid unnecessary burden on the target platform.
# 5. May not be used for any illegal or inappropriate purposes.
#
# For detailed license terms, please refer to the LICENSE file in the project root directory.
# By using this code, you agree to abide by the above principles and all terms in LICENSE.


import os
import asyncio
import socket
import httpx
from typing import Optional, Dict, Any
from playwright.async_api import Browser, BrowserContext, Playwright

import config
from tools.browser_launcher import BrowserLauncher
from tools import utils


class CDPBrowserManager:
    """CDP Browser Manager, responsible for launching and managing browsers connected through CDP"""

    def __init__(self):
        self.launcher = BrowserLauncher()
        self.browser: Optional[Browser] = None
        self.browser_context: Optional[BrowserContext] = None
        self.debug_port: Optional[int] = None

    async def launch_and_connect(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict] = None,
        user_agent: Optional[str] = None,
        headless: bool = False,
    ) -> BrowserContext:
        """Launch a browser and connect via CDP"""
        try:
            # 1. Detect browser path
            browser_path = await self._get_browser_path()

            # 2. Get available ports
            self.debug_port = self.launcher.find_available_port(config.CDP_DEBUG_PORT)

            # 3. Start the browser
            await self._launch_browser(browser_path, headless)

            # 4. Connect via CDP
            await self._connect_via_cdp(playwright)

            # 5. Create browser context
            browser_context = await self._create_browser_context(
                playwright_proxy, user_agent
            )

            self.browser_context = browser_context
            return browser_context

        except Exception as e:
            utils.logger.error(f"[CDPBrowserManager] CDP browser failed to start: {e}")
            await self.cleanup()
            raise

    async def _get_browser_path(self) -> str:
        """Get browser path"""
        # Give priority to user-defined paths
        if config.CUSTOM_BROWSER_PATH and os.path.isfile(config.CUSTOM_BROWSER_PATH):
            utils.logger.info(
                f"[CDPBrowserManager] Use custom browser path: {config.CUSTOM_BROWSER_PATH}"
            )
            return config.CUSTOM_BROWSER_PATH

        # Automatically detect browser paths
        browser_paths = self.launcher.detect_browser_paths()

        if not browser_paths:
            raise RuntimeError(
                "No available browser found. Please make sure you have Chrome or Edge browser installed,"
                "Or set CUSTOM_BROWSER_PATH in the configuration file to specify the browser path."
            )

        browser_path = browser_paths[0]  # Use the first browser found
        browser_name, browser_version = self.launcher.get_browser_info(browser_path)

        utils.logger.info(
            f"[CDPBrowserManager] Detected browser: {browser_name} ({browser_version})"
        )
        utils.logger.info(f"[CDPBrowserManager] Browser path: {browser_path}")

        return browser_path

    async def _test_cdp_connection(self, debug_port: int) -> bool:
        """Test whether the CDP connection is available"""
        try:
            # Simple socket connection test
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                result = s.connect_ex(("localhost", debug_port))
                if result == 0:
                    utils.logger.info(
                        f"[CDPBrowserManager] CDP port {debug_port} is accessible"
                    )
                    return True
                else:
                    utils.logger.warning(
                        f"[CDPBrowserManager] CDP port {debug_port} is not accessible"
                    )
                    return False
        except Exception as e:
            utils.logger.warning(f"[CDPBrowserManager] CDP connection test failed: {e}")
            return False

    async def _launch_browser(self, browser_path: str, headless: bool):
        """Start browser process"""
        # Set the user data directory (if saving login status is enabled)
        user_data_dir = None
        if config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(
                os.getcwd(),
                "browser_data",
                f"cdp_{config.USER_DATA_DIR % config.PLATFORM}",
            )
            os.makedirs(user_data_dir, exist_ok=True)
            utils.logger.info(f"[CDPBrowserManager] User data directory: {user_data_dir}")

        # Start browser
        self.launcher.browser_process = self.launcher.launch_browser(
            browser_path=browser_path,
            debug_port=self.debug_port,
            headless=headless,
            user_data_dir=user_data_dir,
        )

        # Wait for the browser to be ready
        if not self.launcher.wait_for_browser_ready(
            self.debug_port, config.BROWSER_LAUNCH_TIMEOUT
        ):
            raise RuntimeError(f"Browser failed to launch in {config.BROWSER_LAUNCH_TIMEOUT} seconds")

        # Wait an extra second for the CDP service to fully start
        await asyncio.sleep(1)

        # Test CDP connection
        if not await self._test_cdp_connection(self.debug_port):
            utils.logger.warning(
                "[CDPBrowserManager] CDP connection test failed but will continue to try to connect"
            )

    async def _get_browser_websocket_url(self, debug_port: int) -> str:
        """Get the browser's WebSocket connection URL"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://localhost:{debug_port}/json/version", timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    ws_url = data.get("webSocketDebuggerUrl")
                    if ws_url:
                        utils.logger.info(
                            f"[CDPBrowserManager] Obtain the browser WebSocket URL: {ws_url}"
                        )
                        return ws_url
                    else:
                        raise RuntimeError("webSocketDebuggerUrl not found")
                else:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            utils.logger.error(f"[CDPBrowserManager] Failed to obtain WebSocket URL: {e}")
            raise

    async def _connect_via_cdp(self, playwright: Playwright):
        """Connect to browser via CDP"""
        try:
            # Get the correct WebSocket URL
            ws_url = await self._get_browser_websocket_url(self.debug_port)
            utils.logger.info(f"[CDPBrowserManager] Connecting to browser via CDP: {ws_url}")

            # Connect using Playwright's connectOverCDP method
            self.browser = await playwright.chromium.connect_over_cdp(ws_url)

            if self.browser.is_connected():
                utils.logger.info("[CDPBrowserManager] successfully connected to the browser")
                utils.logger.info(
                    f"[CDPBrowserManager] Number of browser contexts: {len(self.browser.contexts)}"
                )
            else:
                raise RuntimeError("CDP connection failed")

        except Exception as e:
            utils.logger.error(f"[CDPBrowserManager] CDP connection failed: {e}")
            raise

    async def _create_browser_context(
        self, playwright_proxy: Optional[Dict] = None, user_agent: Optional[str] = None
    ) -> BrowserContext:
        """Create or get browser context"""
        if not self.browser:
            raise RuntimeError("Browser not connected")

        # Get an existing context or create a new context
        contexts = self.browser.contexts

        if contexts:
            # Use the existing first context
            browser_context = contexts[0]
            utils.logger.info("[CDPBrowserManager] Use existing browser context")
        else:
            # Create new context
            context_options = {
                "viewport": {"width": 1920, "height": 1080},
                "accept_downloads": True,
            }

            # Set user agent
            if user_agent:
                context_options["user_agent"] = user_agent
                utils.logger.info(f"[CDPBrowserManager] Set user agent: {user_agent}")

            # Note: The proxy settings may not take effect in CDP mode because the browser has already been started.
            if playwright_proxy:
                utils.logger.warning(
                    "[CDPBrowserManager] Warning: Proxy settings may not take effect in CDP mode."
                    "It is recommended to configure the system proxy or browser proxy extension before starting the browser"
                )

            browser_context = await self.browser.new_context(**context_options)
            utils.logger.info("[CDPBrowserManager] Create a new browser context")

        return browser_context

    async def add_stealth_script(self, script_path: str = "libs/stealth.min.js"):
        """Add anti-detection script"""
        if self.browser_context and os.path.exists(script_path):
            try:
                await self.browser_context.add_init_script(path=script_path)
                utils.logger.info(
                    f"[CDPBrowserManager] Added anti-detection script: {script_path}"
                )
            except Exception as e:
                utils.logger.warning(f"[CDPBrowserManager] Failed to add anti-detection script: {e}")

    async def add_cookies(self, cookies: list):
        """Add cookies"""
        if self.browser_context:
            try:
                await self.browser_context.add_cookies(cookies)
                utils.logger.info(f"[CDPBrowserManager] Added {len(cookies)} Cookies")
            except Exception as e:
                utils.logger.warning(f"[CDPBrowserManager] Failed to add cookie: {e}")

    async def get_cookies(self) -> list:
        """Get the current cookie"""
        if self.browser_context:
            try:
                cookies = await self.browser_context.cookies()
                return cookies
            except Exception as e:
                utils.logger.warning(f"[CDPBrowserManager] Failed to obtain Cookie: {e}")
                return []
        return []

    async def cleanup(self):
        """Clean up resources"""
        try:
            # Close browser context
            if self.browser_context:
                try:
                    await self.browser_context.close()
                    utils.logger.info("[CDPBrowserManager] Browser context closed")
                except Exception as context_error:
                    utils.logger.warning(
                        f"[CDPBrowserManager] Failed to close browser context: {context_error}"
                    )
                finally:
                    self.browser_context = None

            # Disconnect browser
            if self.browser:
                try:
                    await self.browser.close()
                    utils.logger.info("[CDPBrowserManager] Browser connection disconnected")
                except Exception as browser_error:
                    utils.logger.warning(
                        f"[CDPBrowserManager] Failed to close browser connection: {browser_error}"
                    )
                finally:
                    self.browser = None

            # Close the browser process (if configured to close automatically)
            if config.AUTO_CLOSE_BROWSER:
                self.launcher.cleanup()
            else:
                utils.logger.info(
                    "[CDPBrowserManager] Browser process keeps running (AUTO_CLOSE_BROWSER=False)"
                )

        except Exception as e:
            utils.logger.error(f"[CDPBrowserManager] Error cleaning resources: {e}")

    def is_connected(self) -> bool:
        """Check if connected to browser"""
        return self.browser is not None and self.browser.is_connected()

    async def get_browser_info(self) -> Dict[str, Any]:
        """Get browser information"""
        if not self.browser:
            return {}

        try:
            version = self.browser.version
            contexts_count = len(self.browser.contexts)

            return {
                "version": version,
                "contexts_count": contexts_count,
                "debug_port": self.debug_port,
                "is_connected": self.is_connected(),
            }
        except Exception as e:
            utils.logger.warning(f"[CDPBrowserManager] Failed to obtain browser information: {e}")
            return {}
