from pathlib import Path

async def upload_from_buffer(
    data: bytes,
    /,
    key: str,
    expired: int = ...,
) -> str: ...
async def upload_from_url(
    url: str,
    /,
    key: str,
    expired: int = ...,
) -> str: ...
async def upload_from_local(
    path: Path,
    /,
    key: str,
    expired: int = ...,
) -> str: ...
