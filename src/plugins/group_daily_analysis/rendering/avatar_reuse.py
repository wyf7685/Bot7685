"""头像 CSS 复用系统 — 相同 Data URI 仅通过 CSS 注入一次。"""

import hashlib
import html
import re

TRANSPARENT_IMAGE_DATA_URI = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxIiBoZWlnaHQ9IjEiPjwvc3ZnPg=="
)


def _build_avatar_ref(avatar_key: str | None, avatar_url: str) -> str:
    if avatar_key:
        digest = hashlib.sha256(avatar_key.encode()).hexdigest()[:24]
        return f"avatar-{digest}"
    digest = hashlib.sha256(avatar_url.encode()).hexdigest()[:24]
    return f"avatar-{digest}"


def _replace_inline_img_srcs(
    html_content: str,
    aliases: dict[str, str] | None = None,
) -> str:
    """将最终 HTML 中的 Data URI img src 替换为短引用。"""
    if not html_content:
        return html_content

    img_src_pattern = re.compile(
        r'(<img\b[^>]*?\bsrc\s*=\s*)(["\'])(data:image/[^"\']+)(\2)([^>]*>)',
        re.IGNORECASE | re.DOTALL,
    )

    def replace(m: re.Match[str]) -> str:
        prefix, quote_char, data_uri, _, suffix = m.groups()
        if data_uri == TRANSPARENT_IMAGE_DATA_URI:
            return m.group(0)

        avatar_ref = aliases.get(data_uri) if aliases else None
        if not avatar_ref:
            return m.group(0)

        escaped_ref = html.escape(avatar_ref, quote=True)
        return (
            f"{prefix}{quote_char}{TRANSPARENT_IMAGE_DATA_URI}{quote_char}"
            f' data-avatar-ref="{escaped_ref}"{suffix}'
        )

    return img_src_pattern.sub(replace, html_content)


def _inject_styles(html_content: str, reuse_styles: str) -> str:
    if not html_content or not reuse_styles:
        return html_content

    head_close = re.search(r"</head\s*>", html_content, re.IGNORECASE)
    if head_close:
        return (
            html_content[: head_close.start()]
            + reuse_styles
            + "\n"
            + html_content[head_close.start() :]
        )
    return reuse_styles + "\n" + html_content


class ReusableAvatarManager:
    """头像复用管理器，维护注册表和别名映射。"""

    def __init__(self) -> None:
        self.registry: dict[str, str] = {}
        self.aliases: dict[str, str] = {}

    def register(
        self,
        avatar_url: str | None,
        avatar_key: str | None = None,
    ) -> str | None:
        """将 Data URI 登记为可复用资源，返回缩短的引用 ID。"""
        if not avatar_url:
            return None
        if not avatar_url.startswith("data:image/"):
            return None

        if avatar_url in self.aliases:
            return self.aliases[avatar_url]

        ref = _build_avatar_ref(avatar_key, avatar_url)
        self.registry.setdefault(ref, avatar_url)
        self.aliases[avatar_url] = ref
        return ref

    def _build_avatar_reuse_styles(self) -> str:
        if not self.registry:
            return ""

        rules = [
            '<style id="avatar-reuse-styles">',
            (
                ".user-capsule-avatar,img[data-avatar-ref]{"
                "background-color:#ddd;background-size:cover;"
                "background-position:center;background-repeat:no-repeat;}"
            ),
        ]
        for ref, data_uri in self.registry.items():
            escaped_ref = html.escape(ref, quote=True)
            escaped_uri = data_uri.replace("\\", "\\\\").replace('"', '\\"')
            rules.append(
                f'[data-avatar-ref="{escaped_ref}"]'
                f'{{background-image:url("{escaped_uri}");}}'
            )
        rules.append("</style>")
        return "\n".join(rules)

    def apply(self, html_content: str) -> str:
        """复用最终 HTML 中所有内联头像，注入 CSS 样式块。"""
        if not html_content:
            return html_content

        html_content = _replace_inline_img_srcs(html_content, self.aliases)
        return _inject_styles(html_content, self._build_avatar_reuse_styles())
