import json
from typing import Any

import anyio
from nonebot import logger
from nonebot_plugin_htmlrender import get_new_page

from .config import TEMPLATE_DIR

PAWTECT_HTML = TEMPLATE_DIR / "pawtect" / "index.html"


async def get_pawtect_token(user_id: int, request_body: dict[str, Any]) -> str | None:
    if not PAWTECT_HTML.exists():
        return None

    html = (
        PAWTECT_HTML.read_text(encoding="utf-8")
        .replace("{{user_id}}", str(user_id))
        .replace("{{request_body}}", json.dumps(request_body, separators=(",", ":")))
    )

    async with get_new_page() as page:
        await page.set_content(html)
        await anyio.sleep(1)
        with anyio.move_on_after(10):
            while not (element := await page.query_selector("#pawtect-result")):  # noqa: ASYNC110
                await anyio.sleep(0.1)
            data: dict[str, str] = json.loads(await element.text_content() or "{}")
            if token := data.get("token"):
                return token
            if error := data.get("error"):
                logger.warning(f"Pawtect error: {error}")
            else:
                logger.warning("Pawtect returned no token and no error message.")

    return None
