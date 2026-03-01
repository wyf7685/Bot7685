"""Monkey-patch for nonebot_plugin_htmlrender — remote Playwright support.

When Playwright is deployed as a separate container, `file://` URLs cannot be
resolved by the remote browser (different filesystem).  This patch intercepts
every `file://` template_path / base_url passed through html_to_pic and
get_new_page, replacing them with virtual HTTP URLs that are served from the
*bot-side* filesystem via Playwright's route interception API.

Virtual URL format:
    http://{dir_hash}.htmlrender-local.bot/{abs_dir_path}/
where:
    dir_hash = format(hash(str(abs_dir)) & 0xFFFFFFFFFFFFFFFF, "x")
    abs_dir_path = POSIX absolute path of the template directory

Embedding the absolute directory path as the URL path component lets the
browser resolve relative references (including `../`) correctly:
    ../images/file.png
    → http://{hash}.bot/opt/.../resources/images/file.png
The handler then strips the URL path and serves it as an absolute FS path.

A catch-all proxy route (registered first, lowest priority) intercepts all
external HTTP/HTTPS requests, proxies them via httpx on the bot side, and
adds Access-Control-Allow-Origin: * to avoid CORS errors.

Patch points
------------
* `nonebot_plugin_htmlrender.browser.get_new_page`  — register routes on page
* `nonebot_plugin_htmlrender.data_source.get_new_page` — same (direct import)
* `nonebot_plugin_htmlrender.data_source.html_to_pic`  — full replacement to
  bypass the original `file:` check and inject the ContextVar before opening
  the page.
"""

import contextvars
import importlib.metadata
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from mimetypes import guess_type
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import unquote, urlparse

import anyio
import httpx
import nonebot
from nonebot.utils import escape_tag, logger_wrapper
from playwright.async_api import Page, Request, Route

type RouteHandler = Callable[[Route, Request], object]

log = logger_wrapper("pw")

if TYPE_CHECKING:
    import nonebot_plugin_htmlrender.browser as _browser_mod

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PATCH_HTMLRENDER_VERSION = "0.6.7"
_VIRTUAL_HOST_SUFFIX = "htmlrender-local.bot"

# ContextVar: list of (glob_pattern, async_handler) pairs to be registered
# on every page opened within the current async task's call to html_to_pic.
# Default is None; _patched_html_to_pic always sets a fresh list before use.
_ctx_routes: contextvars.ContextVar[list[tuple[str, RouteHandler]] | None] = (
    contextvars.ContextVar("_htmlrender_pw_routes", default=None)
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _path_hash(path: Path) -> str:
    """Unsigned hex hash of the resolved absolute path string.

    Python's built-in hash() can return negative values; masking with
    0xFFFF_FFFF_FFFF_FFFF guarantees a non-negative 64-bit integer.
    """
    return format(hash(str(path.resolve())) & 0xFFFF_FFFF_FFFF_FFFF, "x")


def _virtual_base(local_dir: Path) -> str:
    """Return the virtual HTTP base URL (no trailing slash) for local_dir."""
    return f"http://{_path_hash(local_dir)}.{_VIRTUAL_HOST_SUFFIX}"


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


def _make_file_handler() -> RouteHandler:
    """Return a Playwright route handler that interprets the URL path as an
    absolute filesystem path and serves the corresponding file.

    Because the absolute directory path is embedded in the virtual URL
    (see _register_dir), the browser correctly resolves `../` references
    before the request reaches this handler.  The URL path is therefore
    always a valid absolute FS path — no extra resolution is needed.
    """

    async def handler(route: Route, request: Request) -> None:
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
        target = (
            anyio.Path(stripped)  # Windows: "C:/..." is already absolute
            if len(stripped) >= 2 and stripped[1] == ":"
            else anyio.Path("/" + stripped)  # POSIX: restore leading "/"
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

    return handler


def _register_dir(
    routes: list[tuple[str, RouteHandler]],
    local_dir: Path,
) -> str:
    """Ensure a virtual HTTP route exists in *routes* for *local_dir*.

    Returns a virtual URL with the absolute directory path embedded as the
    URL path component, e.g.:
        http://{hash}.htmlrender-local.bot/opt/venv/.../templates/

    Using this as the page.goto() target and base_url lets the browser
    resolve `../` references to the correct absolute paths, which the
    handler then maps back to the local filesystem.
    """
    resolved = local_dir.resolve()
    virtual_host = _virtual_base(resolved)
    pattern = f"{virtual_host}/**"

    if not any(p == pattern for p, _ in routes):
        routes.append((pattern, _make_file_handler()))
        log("DEBUG", f"Virtual route: <y>{pattern}</>")

    # Encode the absolute directory path as the URL path component.
    # POSIX: /opt/venv/... → /opt/venv/...
    # Windows: C:\Users\... → /C:/Users/...
    path_str = str(resolved)
    url_path = (
        "/" + path_str.replace("\\", "/")  # Windows: prefix "/"
        if len(path_str) >= 2 and path_str[1] == ":"
        else path_str  # POSIX: already starts with "/"
    )
    return f"{virtual_host}{url_path}/"


def _virtualize(url: str, routes: list[tuple[str, RouteHandler]]) -> str:
    """If *url* is a file:// URL, register a route and return the virtual URL.

    Any other URL scheme is returned unchanged.
    """
    local_dir = _parse_file_url(url)
    if local_dir is None:
        return url
    return _register_dir(routes, local_dir)


@asynccontextmanager
async def _make_proxy_handler() -> AsyncIterator[RouteHandler]:
    """Yield a catch-all route handler that proxies external HTTP/HTTPS
    requests through the bot-side httpx client.

    This prevents CORS errors for external resources (CDN fonts, scripts, etc.)
    referenced by templates.  Every response gets Access-Control-Allow-Origin: *
    added so the browser accepts cross-origin subresources.

    Virtual-host requests that slip past the specific route registrations are
    passed through via route.fallback() rather than proxied.
    """

    async def handler(route: Route, request: Request) -> None:
        # Virtual-host URLs are handled by more specific routes registered
        # later (higher priority in Playwright LIFO).  If one reaches here
        # something went wrong — return 404 immediately instead of fallback(),
        # because fallback() on the lowest-priority handler sends the request
        # to the real network, causing a DNS timeout for our virtual hosts.
        if _VIRTUAL_HOST_SUFFIX in (urlparse(request.url).hostname or ""):
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
                f"Proxy failed for <y>{escape_tag(url)}</>: {escape_tag(str(exc))}",
            )
            await route.fallback()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        yield handler


# ---------------------------------------------------------------------------
# Patched get_new_page
# ---------------------------------------------------------------------------

if TYPE_CHECKING:
    _orig_get_new_page = _browser_mod.get_new_page
else:
    _orig_get_new_page = None


@asynccontextmanager
async def _patched_get_new_page(
    device_scale_factor: float = 2,
    **kwargs: object,
) -> AsyncIterator[Page]:
    routes = _ctx_routes.get() or []

    # Transform base_url when it is a file:// URL.
    # If called from _patched_html_to_pic, base_url was already virtualised
    # there; _virtualize() will return it unchanged (not a file:// URL).
    if isinstance(base_url := kwargs.get("base_url"), str):
        kwargs["base_url"] = _virtualize(base_url, routes)

    async with (
        _orig_get_new_page(device_scale_factor, **kwargs) as page,
        _make_proxy_handler() as proxy_handler,
    ):
        # Proxy catch-all registered first → lowest priority in Playwright LIFO.
        # Handles external CDN resources and adds CORS headers to all responses.
        await page.route("**/*", proxy_handler)
        # Virtual host routes registered last → highest priority.
        # These override the proxy for requests to our virtual hosts.
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
    routes: list[tuple[str, RouteHandler]] = []

    # Virtualise template_path.
    template_path = _virtualize(template_path, routes)

    # Virtualise base_url if present; otherwise fall back to template_path so
    # the browser context always has a virtual base_url set.
    if isinstance(base_url := kwargs.get("base_url"), str):
        kwargs["base_url"] = _virtualize(base_url, routes)
    else:
        kwargs["base_url"] = template_path

    # Publish routes to the ContextVar so _patched_get_new_page can pick them
    # up even if called indirectly through other wrappers.
    token = _ctx_routes.set(routes)
    try:
        async with _patched_get_new_page(device_scale_factor, **kwargs) as page:
            page.on("console", lambda msg: log("DEBUG", f"浏览器控制台: {msg.text}"))
            # Skip page.goto() to the virtual host URL.  In remote Playwright
            # setups the browser may attempt real DNS resolution for the virtual
            # host if the route pattern doesn't match the navigation request,
            # causing a 30-second timeout.
            #
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
    finally:
        _ctx_routes.reset(token)


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

    global _orig_get_new_page

    nonebot.require("nonebot_plugin_htmlrender")
    import nonebot_plugin_htmlrender as _htmlrender_mod
    import nonebot_plugin_htmlrender.browser as _browser_mod
    import nonebot_plugin_htmlrender.data_source as _ds_mod

    _orig_get_new_page = _browser_mod.get_new_page

    # browser module — affects every caller that imports get_new_page from there
    _browser_mod.get_new_page = _patched_get_new_page
    # data_source module — the `from ... import get_new_page` binding inside it
    _ds_mod.get_new_page = _patched_get_new_page
    # html_to_pic replacement (template_to_pic calls it by module-level name lookup,
    _ds_mod.html_to_pic = _patched_html_to_pic

    # also patch the re-exports
    _htmlrender_mod.get_new_page = _patched_get_new_page
    _htmlrender_mod.html_to_pic = _patched_html_to_pic

    log("SUCCESS", "Applied htmlrender patches for remote Playwright support")
