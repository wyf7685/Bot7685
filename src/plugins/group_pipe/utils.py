import httpx


async def download_url(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.HTTPError):
            return b""
        else:
            return resp.read()


async def check_url_ok(url: str) -> bool:
    async with httpx.AsyncClient() as client, client.stream("GET", url) as resp:
        return resp.status_code == 200
