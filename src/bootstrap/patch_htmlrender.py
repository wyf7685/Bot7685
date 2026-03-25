"""Monkey-patch for nonebot_plugin_htmlrender — remote Playwright support.

When Playwright is deployed as a separate container, `file://` URLs cannot be
resolved by the remote browser (different filesystem).  This patch intercepts
every `file://` template_path / base_url passed through html_to_pic and
get_new_page, replacing them with virtual HTTP URLs that are served from the
*bot-side* filesystem via Playwright's route interception API.

Virtual URL format:
    http://htmlrender-local.bot/{abs_dir_path}/
where:
    abs_dir_path = POSIX absolute path of the template directory

Embedding the absolute directory path as the URL path component lets the
browser resolve relative references (including `../`) correctly:
    ../images/file.png
    → http://htmlrender-local.bot/opt/.../resources/images/file.png
The handler strips the URL path and serves it as an absolute FS path.
All directories share the same virtual host; the absolute path in the URL
path component provides unambiguous file identity without any hashing.

A catch-all proxy route (registered first, lowest priority) intercepts all
external HTTP/HTTPS requests, proxies them via httpx on the bot side, and
adds Access-Control-Allow-Origin: * to avoid CORS errors.

Patch points
------------
* `nonebot_plugin_htmlrender.browser.get_new_page`  — register routes on page
* `nonebot_plugin_htmlrender.data_source.html_to_pic`  — full replacement to
  bypass the original `file:` check and inject the ContextVar before opening
  the page.
"""

import contextlib
import contextvars
import functools
import importlib.metadata
import re
from collections.abc import AsyncIterator, Callable
from mimetypes import guess_type
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import unquote, urlparse

import anyio
import httpx
from nonebot.utils import escape_tag, logger_wrapper
from playwright.async_api import Page, Request, Route

type RouteHandler = Callable[[Route, Request], object]
type Routes = list[tuple[str, RouteHandler]]

log = logger_wrapper("Patch HTMLRender")

if TYPE_CHECKING:
    from nonebot_plugin_htmlrender.browser import get_new_page as _orig_get_new_page
else:
    _orig_get_new_page = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PATCH_HTMLRENDER_VERSION = "0.6.7"
_VIRTUAL_HOST = "htmlrender-local.bot"
_VIRTUAL_BASE = f"http://{_VIRTUAL_HOST}"
_VIRTUAL_PATTERN = f"{_VIRTUAL_BASE}/**"

# ContextVar: list of (glob_pattern, async_handler) pairs to be registered
# on every page opened within the current async task's call to html_to_pic.
# Default is None; _patched_html_to_pic always sets a fresh list before use.
_ctx_routes: contextvars.ContextVar[Routes | None] = contextvars.ContextVar(
    "_htmlrender_pw_routes", default=None
)


@contextlib.asynccontextmanager
async def _set_routes(routes: Routes) -> AsyncIterator[None]:
    """Context manager to set the ContextVar for route registrations."""
    token = _ctx_routes.set(routes)
    try:
        yield
    finally:
        _ctx_routes.reset(token)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _abs_path_to_url_path(path: Path) -> str:
    """Convert a resolved absolute Path to a URL path component string.

    POSIX: /opt/venv/lib/...  → /opt/venv/lib/...
    Windows: C:\\Users\\...  → /C:/Users/...
    """
    path_str = str(path)
    if len(path_str) >= 2 and path_str[1] == ":":  # Windows drive letter
        return "/" + path_str.replace("\\", "/")
    return path_str  # POSIX: already starts with "/"


def _parse_file_url(url: str) -> Path | None:
    """Convert a file:// URL to a local Path; return None for any other scheme.

    Handles both POSIX paths (file:///app/...) and the Windows form that
    data_source.py produces on Windows (file://C:/...).
    """
    if not url.startswith("file://"):
        return None
    parsed = urlparse(url)
    path_str = unquote(parsed.path)
    # Windows: urlparse("file:///C:/foo").path == "/C:/foo"
    # Strip the leading "/" when the second char is a drive-letter colon.
    if len(path_str) >= 3 and path_str[0] == "/" and path_str[2] == ":":
        path_str = path_str[1:]
    return Path(path_str)


async def _file_handler(route: Route, request: Request) -> None:
    """
    Playwright route handler that serves files from the bot-side filesystem
    based on the URL path component.

    The URL path is interpreted as an absolute filesystem path.  This works
    because the virtual URL format embeds the absolute directory path, and
    the browser resolves relative references before the request reaches this
    handler.

    For example, a request to http://htmlrender-local.bot/opt/file.css
    corresponds to the bot-side file at /opt/file.css.
    """
    url_path = unquote(urlparse(request.url).path)

    if not url_path or url_path == "/":
        # page.goto() root navigation — return an empty placeholder so
        # Playwright considers the navigation successful.
        await route.fulfill(content_type="text/html", body=b"")
        return

    # Convert URL path component back to an absolute filesystem path.
    # POSIX: "/opt/venv/.../file.css" → anyio.Path("/opt/venv/.../file.css")
    # Windows: "/C:/Users/.../file.css" → anyio.Path("C:/Users/.../file.css")
    stripped = url_path.lstrip("/")
    target = anyio.Path(
        stripped  # Windows: "C:/..." is already absolute
        if len(stripped) >= 2 and stripped[1] == ":"
        else "/" + stripped  # POSIX: restore leading "/"
    )

    if not await target.is_file():
        log("DEBUG", f"404: <y>{escape_tag(str(target))}</>")
        await route.fulfill(status=404)
        return

    mime, _ = guess_type(target.name)
    await route.fulfill(
        body=await target.read_bytes(),
        content_type=mime or "application/octet-stream",
    )


def _file_url_to_virtual(url: str, routes: Routes) -> str:
    """Convert a file:// URL to a virtual HTTP URL and ensure the shared file
    route is registered in *routes* (idempotent).

    Returns the URL unchanged if it is not a file:// URL.
    """
    local_dir = _parse_file_url(url)
    if local_dir is None:
        return url

    resolved = local_dir.resolve()

    # Register the single shared file handler once per page session.
    if not any(p == _VIRTUAL_PATTERN for p, _ in routes):
        routes.append((_VIRTUAL_PATTERN, _file_handler))
        log("DEBUG", f"Virtual route registered: <y>{_VIRTUAL_PATTERN}</>")

    return f"{_VIRTUAL_BASE}{_abs_path_to_url_path(resolved)}/"


async def _proxy_handler(
    client: httpx.AsyncClient,
    route: Route,
    request: Request,
) -> None:
    # Virtual-host URLs are handled by more specific routes registered
    # later (higher priority in Playwright LIFO).  If one reaches here
    # something went wrong — return 404 immediately instead of fallback(),
    # because fallback() on the lowest-priority handler sends the request
    # to the real network, causing a DNS timeout for our virtual hosts.
    if _VIRTUAL_HOST in (urlparse(request.url).hostname or ""):
        log(
            "WARNING",
            "Request for virtual host reached proxy handler (route miss?): "
            f"<y>{escape_tag(request.url)}</>",
        )
        await route.fulfill(status=404)
        return

    url = request.url
    try:
        resp = await client.request(
            method=request.method,
            url=url,
            # Strip headers that don't make sense when relayed
            headers={
                k: v
                for k, v in request.headers.items()
                if k.lower() not in {"host", "origin", "referer"}
            },
            content=request.post_data_buffer,
        )
        # Drop transfer/encoding headers; Playwright handles them itself
        resp_headers = {
            k: v
            for k, v in resp.headers.multi_items()
            if k.lower() not in {"content-encoding", "transfer-encoding"}
        }
        resp_headers["access-control-allow-origin"] = "*"
        resp_headers["access-control-allow-credentials"] = "true"
        await route.fulfill(
            status=resp.status_code,
            headers=resp_headers,
            body=resp.content,
        )
    except Exception as exc:
        log(
            "WARNING",
            f"Proxy failed for <y>{escape_tag(url)}</>",
            exc,
        )
        await route.fallback()


@contextlib.asynccontextmanager
async def _make_proxy_handler() -> AsyncIterator[RouteHandler]:
    """Yield a catch-all route handler that proxies external HTTP/HTTPS
    requests through the bot-side httpx client.

    This prevents CORS errors for external resources (CDN fonts, scripts, etc.)
    referenced by templates.  Every response gets Access-Control-Allow-Origin: *
    added so the browser accepts cross-origin subresources.

    Virtual-host requests that slip past the specific route registrations are
    passed through via route.fallback() rather than proxied.
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        yield functools.partial(_proxy_handler, client)


# ---------------------------------------------------------------------------
# Patched get_new_page
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def _patched_get_new_page(
    device_scale_factor: float = 2,
    **kwargs: object,
) -> AsyncIterator[Page]:
    routes = _ctx_routes.get() or []

    # Transform base_url when it is a file:// URL.
    # If called from _patched_html_to_pic, base_url was already virtualised
    # there; _file_url_to_virtual() will return it unchanged (not file://).
    if isinstance(base_url := kwargs.get("base_url"), str):
        kwargs["base_url"] = _file_url_to_virtual(base_url, routes)

    async with (
        _orig_get_new_page(device_scale_factor, **kwargs) as page,
        _make_proxy_handler() as proxy_handler,
    ):
        # Proxy catch-all registered first → lowest priority in Playwright LIFO.
        await page.route("**/*", proxy_handler)
        # Virtual host route registered last → highest priority.
        for pattern, handler in routes:
            await page.route(pattern, handler)
        yield page


# ---------------------------------------------------------------------------
# Patched html_to_pic
# ---------------------------------------------------------------------------
# The original raises if "file:" is not in template_path, which would reject
# our virtualised "http://" URLs.  We replicate the rendering logic in full
# (it is intentionally minimal) and add the file-route injection.


async def _patched_html_to_pic(
    html: str,
    wait: int = 0,
    template_path: str = f"file://{Path.cwd()}",
    type: Literal["jpeg", "png"] = "png",  # noqa: A002
    quality: int | None = None,
    device_scale_factor: float = 2,
    screenshot_timeout: float | None = 30_000,
    full_page: bool | None = True,
    **kwargs: object,
) -> bytes:
    routes: Routes = []

    # Virtualise template_path.
    template_path = _file_url_to_virtual(template_path, routes)

    # Virtualise base_url if present; otherwise fall back to template_path so
    # the browser context always has a virtual base_url set.
    if isinstance(base_url := kwargs.get("base_url"), str):
        kwargs["base_url"] = _file_url_to_virtual(base_url, routes)
    else:
        kwargs["base_url"] = template_path

    # Publish routes to the ContextVar so _patched_get_new_page can pick them
    # up even if called indirectly through other wrappers.
    async with (
        _set_routes(routes),
        _patched_get_new_page(device_scale_factor, **kwargs) as page,
    ):
        page.on("console", lambda msg: log("DEBUG", f"浏览器控制台: {msg.text}"))
        # Skip page.goto() to the virtual host URL.
        # Instead inject a <base href> tag so the browser resolves all
        # relative resource references against the virtual template URL.
        # The routes registered above intercept those requests and serve
        # files from the bot-side filesystem.
        base_tag = f'<base href="{template_path}">'
        if m := re.search(r"<head(?:\s[^>]*)?>", html, re.IGNORECASE):
            insert_at = m.end()
            html = html[:insert_at] + base_tag + html[insert_at:]
        else:
            html = base_tag + html
        await page.set_content(html, wait_until="networkidle")
        await page.wait_for_timeout(wait)
        return await page.screenshot(
            full_page=full_page,
            type=type,
            quality=quality,
            timeout=screenshot_timeout,
        )


# ---------------------------------------------------------------------------
# Patching API
# ---------------------------------------------------------------------------


def patch_htmlrender() -> None:
    htmlrender_version = importlib.metadata.version("nonebot_plugin_htmlrender")
    log("DEBUG", f"nonebot_plugin_htmlrender version: {htmlrender_version}")

    if htmlrender_version != _PATCH_HTMLRENDER_VERSION:
        log(
            "WARNING",
            f"Expected nonebot_plugin_htmlrender version {_PATCH_HTMLRENDER_VERSION} "
            f"for Playwright patching, but found {htmlrender_version}. "
            "Patching skipped to avoid potential breakage",
        )
        return

    import nonebot_plugin_htmlrender as _htmlrender_mod
    import nonebot_plugin_htmlrender.browser as _browser_mod
    import nonebot_plugin_htmlrender.data_source as _ds_mod

    global _orig_get_new_page
    _orig_get_new_page = _browser_mod.get_new_page

    # browser module — affects every caller that imports get_new_page from there
    _browser_mod.get_new_page = _patched_get_new_page
    # data_source module — the `from ... import get_new_page` binding inside it
    _ds_mod.get_new_page = _patched_get_new_page
    # html_to_pic replacement (template_to_pic calls it by module-level name lookup)
    _ds_mod.html_to_pic = _patched_html_to_pic
    # also patch the re-exports
    _htmlrender_mod.get_new_page = _patched_get_new_page
    _htmlrender_mod.html_to_pic = _patched_html_to_pic

    log("SUCCESS", "Applied htmlrender patches for remote Playwright support")


def register_patch() -> None:
    from nonebot.plugin import Plugin

    from .plugin_loader_hook import after_plugin_load

    @after_plugin_load
    def apply_htmlrender_patch(plugin: Plugin, exception: Exception | None) -> None:
        if exception is None and plugin.id_ == "nonebot_plugin_htmlrender":
            patch_htmlrender()
