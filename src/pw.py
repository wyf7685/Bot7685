"""Monkey-patch for nonebot_plugin_htmlrender — remote Playwright support.

When Playwright is deployed as a separate container, `file://` URLs cannot be
resolved by the remote browser (different filesystem).  This patch intercepts
every `file://` template_path / base_url passed through html_to_pic and
get_new_page, replacing them with virtual HTTP URLs that are served from the
*bot-side* filesystem via Playwright's route interception API.

Virtual URL format:
    http://{dir_hash}.htmlrender-local.bot/<relative-path>
where:
    dir_hash = format(hash(str(abs_dir)) & 0xFFFFFFFFFFFFFFFF, "x")

The hash is computed over the resolved absolute directory path, so the same
physical directory always maps to the same virtual host within a single
process run.

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
from contextlib import asynccontextmanager
from mimetypes import guess_type
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import unquote, urlparse

import anyio
import nonebot
from nonebot.utils import logger_wrapper

log = logger_wrapper("pw")

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    import nonebot_plugin_htmlrender.browser as _browser_mod
    from playwright.async_api import Page, Request, Route

    type RouteHandler = Callable[[Route, Request], object]

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
    return format(hash(str(path.resolve())) & 0xFFFFFFFFFFFFFFFF, "x")


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


def _make_file_handler(local_dir: Path) -> RouteHandler:
    """Return a Playwright route handler that serves files from local_dir."""

    resolved_dir = local_dir.resolve()

    async def handler(route: Route, request: Request) -> None:
        rel = unquote(urlparse(request.url).path).lstrip("/")

        if not rel:
            # page.goto(virtual_base + "/") triggers this; return an empty
            # placeholder page so Playwright considers the navigation done.
            await route.fulfill(content_type="text/html", body=b"")
            return

        target = await anyio.Path(resolved_dir / rel).resolve()

        # Path-traversal guard
        try:
            target.relative_to(resolved_dir)
        except ValueError:
            log("WARNING", f"Path traversal blocked: {target}")
            await route.fulfill(status=403)
            return

        if not await target.is_file():
            log("DEBUG", f"404: {target}")
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

    Returns the virtual base URL with a trailing slash, suitable for use as
    the target of page.goto() or as a base_url for Browser.new_page().
    """
    resolved = local_dir.resolve()
    virtual_base = _virtual_base(resolved)
    pattern = f"{virtual_base}/**"

    if not any(p == pattern for p, _ in routes):
        routes.append((pattern, _make_file_handler(resolved)))
        log("DEBUG", f"Virtual route: {pattern} → {resolved}")

    return virtual_base + "/"


def _virtualize(url: str, routes: list[tuple[str, RouteHandler]]) -> str:
    """If *url* is a file:// URL, register a route and return the virtual URL.

    Any other URL scheme is returned unchanged.
    """
    local_dir = _parse_file_url(url)
    if local_dir is None:
        return url
    return _register_dir(routes, local_dir)


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

    async with _orig_get_new_page(device_scale_factor, **kwargs) as page:
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

    # Virtualise template_path (used as the goto() target).
    template_path = _virtualize(template_path, routes)

    # Virtualise base_url if present in page kwargs
    # (passed as **pages from template_to_pic → html_to_pic).
    if isinstance(base_url := kwargs.get("base_url"), str):
        kwargs["base_url"] = _virtualize(base_url, routes)

    # Publish routes to the ContextVar so _patched_get_new_page can pick them
    # up even if called indirectly through other wrappers.
    token = _ctx_routes.set(routes)
    try:
        async with _patched_get_new_page(device_scale_factor, **kwargs) as page:
            page.on("console", lambda msg: log("DEBUG", f"浏览器控制台: {msg.text}"))
            await page.goto(template_path)
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
