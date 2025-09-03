from nonebot.adapters import Adapter
from nonebot.drivers import HTTPClientMixin, HTTPClientSession, Request, Response

_ATTR_NAME = "_bot7685_adapter_session"


async def request(self: Adapter, setup: Request) -> Response:
    if not isinstance(self.driver, HTTPClientMixin):
        raise TypeError("Current driver does not support http client")

    session: HTTPClientSession
    if hasattr(self, _ATTR_NAME):
        session = getattr(self, _ATTR_NAME)
    else:
        session = self.driver.get_session()
        await session.setup()
        setattr(self, _ATTR_NAME, session)

    return await session.request(setup)


for adapter in Adapter.__subclasses__():
    adapter.request = request
