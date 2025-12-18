# -*- coding: utf-8 -*-
# Disclaimer: This code is for learning and research purposes only. Users should abide by the following principles:
# 1. Not for any commercial purposes.
# 2. When using, you should comply with the terms of use and robots.txt rules of the target platform.
# 3. Do not conduct large-scale crawling or cause operational interference to the platform.
# 4. The request frequency should be reasonably controlled to avoid unnecessary burden on the target platform.
# 5. May not be used for any illegal or inappropriate purposes.
#
# For detailed license terms, please refer to the LICENSE file in the project root directory.
# By using this code, you agree to abide by the above principles and all terms in LICENSE.

import hashlib
import base64
import json
from typing import Any

def _build_c(e: Any, a: Any) -> str:
    c = str(e)
    if isinstance(a, (dict, list)):
        c += json.dumps(a, separators=(",", ":"), ensure_ascii=False)
    elif isinstance(a, str):
        c += a
    # Other types do not spell
    return c


# ---------------------------
# p.Pu = MD5(c) => hex lowercase
# ---------------------------
def _md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()



# ============================================================
# Playwright version (asynchronous): pass in page (Page object)
# Internally use page.evaluate('window.mnsv2(...)')
# ============================================================
async def seccore_signv2_playwright(
    page,  # Playwright Page
    e: Any,
    a: Any,
) -> str:
    """Use Playwright's page.evaluate call to window.mnsv2(c, d) to generate the signature.
    Make sure window.mnsv2 already exists in the page context (for example, the target site script has been injected).

    Usage:
      s = await page.evaluate("(c, d) => window.mnsv2(c, d)", c, d)
    """
    c = _build_c(e, a)
    d = _md5_hex(c)

    # Call window.mnsv2 in the browser context
    s = await page.evaluate("(c, d) => window.mnsv2(c, d)", [c, d])
    f = {
        "x0": "4.2.6",
        "x1": "xhs-pc-web",
        "x2": "Mac OS",
        "x3": s,
        "x4": a,
    }
    payload = json.dumps(f, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    token = "XYS_" + base64.b64encode(payload).decode("ascii")
    print(token)
    return token