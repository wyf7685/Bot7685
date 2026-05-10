"""Mention 渲染 — 将 [uid] 替换为胶囊样式的 HTML。"""

import asyncio
import contextlib
import html
import re

from .avatar import AvatarManager, get_default_avatar_base64


def _escape_text(text: str) -> str:
    return html.escape(text, quote=False).replace("\n", "<br>")


async def render_mentions(text: str, avatar_manager: AvatarManager) -> str:
    """将 [123456] 格式的用户引用替换为胶囊样式的 HTML。"""
    if not text:
        return _escape_text(text) if text else ""

    uids = set(re.findall(r"\[(\d+)\]", text))
    if not uids:
        return _escape_text(text)

    async def prepare(uid: str) -> tuple[str, str, str | None]:
        avatar, _ = await avatar_manager.get_avatar(uid)
        nickname = None
        with contextlib.suppress(Exception):
            nickname = await avatar_manager.get_nickname(uid)
        return uid, avatar, nickname

    results = await asyncio.gather(*(prepare(uid) for uid in uids))
    avatar_map: dict[str, str] = {}
    nickname_map: dict[str, str] = {}
    for uid, avatar, nick in results:
        if avatar:
            avatar_map[uid] = avatar
        if nick:
            nickname_map[uid] = nick

    capsule_style = (
        "display:inline-flex;align-items:center;background:rgba(0,0,0,0.05);"
        "padding:2px 6px 2px 2px;border-radius:12px;margin:0 2px;"
        "vertical-align:middle;border:1px solid rgba(0,0,0,0.1);text-decoration:none;"
    )
    img_style = (
        "width:18px;height:18px;border-radius:50%;margin-right:4px;display:block;"
    )
    name_style = "font-size:0.85em;color:inherit;font-weight:500;line-height:1;"

    def _replace(m: re.Match[str]) -> str:
        uid = m.group(1)
        avatar = avatar_map.get(uid, "")
        if not avatar:
            avatar = get_default_avatar_base64()
        name = nickname_map.get(uid) or uid

        ref = avatar_manager.reuse.register(avatar, uid)
        if ref:
            avatar_html = (
                '<span class="user-capsule-avatar" '
                f'data-avatar-ref="{html.escape(ref, quote=True)}" '
                f'style="{img_style}background-size:cover;background-position:center;'
                'background-repeat:no-repeat;flex-shrink:0;"></span>'
            )
        else:
            avatar_html = (
                f'<img src="{html.escape(avatar, quote=True)}" style="{img_style}">'
            )

        return (
            f'<span class="user-capsule" style="{capsule_style}">'
            f"{avatar_html}"
            f'<span style="{name_style}">{html.escape(name)}</span>'
            "</span>"
        )

    result_parts: list[str] = []
    last_end = 0
    for match in re.finditer(r"\[(\d+)\]", text):
        result_parts.append(_escape_text(text[last_end : match.start()]))
        result_parts.append(_replace(match))
        last_end = match.end()
    result_parts.append(_escape_text(text[last_end:]))
    return "".join(result_parts)
