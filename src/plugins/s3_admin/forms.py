from collections.abc import Callable

from src.service.interaction import (
    MISSING,
    ask_bool,
    ask_choice,
    ask_float,
    ask_int,
    ask_secret,
    ask_text,
    ask_value,
)
from src.service.s3 import S3Config

_EMPTY_WORDS = {"空", "none", "null", "-"}


def _optional_text(value: str) -> str | None:
    value = value.strip()
    if value.casefold() in _EMPTY_WORDS:
        return None
    if not value:
        raise ValueError
    return value


def _endpoint(value: str) -> str | None:
    endpoint = _optional_text(value)
    if endpoint is None:
        return None
    if "://" in endpoint or "@" in endpoint:
        raise ValueError
    if any(char in endpoint for char in "/?#"):
        raise ValueError
    return endpoint


async def _ask_optional(
    prompt: str,
    *,
    default: str | None,
    editing: bool,
    parser: Callable[[str], str | None] = _optional_text,
) -> str | None:
    return await ask_value(
        f"{prompt}；回复“空”清空",
        parser,
        default=default if editing else MISSING,
    )


async def ask_s3_config(existing: S3Config | None = None) -> S3Config:
    editing = existing is not None
    access_key = await ask_secret(
        "请输入 Access Key ID",
        default=existing.access_key_id if existing else MISSING,
    )
    secret_key = await ask_secret(
        "请输入 Secret Access Key",
        default=existing.secret_access_key if existing else MISSING,
    )
    region = await ask_text(
        "请输入 Region",
        default=existing.region if existing else MISSING,
    )
    bucket = await ask_text(
        "请输入 Bucket",
        default=existing.bucket if existing else MISSING,
    )
    endpoint = await _ask_optional(
        "请输入请求 Endpoint host，不含协议；AWS S3 可留空",
        default=existing.endpoint_url if existing else None,
        editing=editing,
        parser=_endpoint,
    )
    presign_endpoint = await _ask_optional(
        "请输入对外预签名 Endpoint host；与请求 Endpoint 相同可留空",
        default=existing.presign_endpoint_url if existing else None,
        editing=editing,
        parser=_endpoint,
    )
    scheme = await ask_choice(
        "请选择协议",
        (("https", "https"), ("http", "http")),
        default=existing.scheme if existing else MISSING,
    )
    path_style = await ask_bool(
        "是否使用 path-style addressing",
        default=existing.path_style if existing else MISSING,
    )
    max_concurrency = await ask_int(
        "请输入最大并发数",
        minimum=1,
        default=int(existing.max_concurrency) if existing else MISSING,
    )
    timeout = await ask_float(
        "请输入请求超时秒数",
        minimum_exclusive=0,
        default=float(existing.timeout_seconds) if existing else MISSING,
    )
    prefix = await _ask_optional(
        "请输入对象 Key 前缀",
        default=existing.key_prefix if existing else "qbot/upload",
        editing=editing,
    )
    session_token = await ask_secret(
        "请输入临时 Session Token",
        default=(
            existing.session_token
            if existing is not None and existing.session_token is not None
            else MISSING
        ),
        optional=True,
    )
    return S3Config(
        access_key_id=access_key,
        secret_access_key=secret_key,
        region=region,
        bucket=bucket,
        endpoint_url=endpoint,
        presign_endpoint_url=presign_endpoint,
        path_style=path_style,
        max_concurrency=max_concurrency,
        session_token=session_token,
        scheme=scheme,
        timeout_seconds=timeout,
        key_prefix=prefix or "",
    )


__all__ = ["ask_s3_config"]
