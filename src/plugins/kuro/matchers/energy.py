from .alc import root_matcher
from .depends import HandlerFromKey

matcher_energy = root_matcher.dispatch("energy")


@matcher_energy.assign("~")
async def assign_energy(handler: HandlerFromKey) -> None:
    await handler.check_energy(do_refresh=True)
    await handler.push_msg()
