async def orm_upgrade() -> None:
    from argparse import Namespace

    from nonebot_plugin_orm import _init_orm, migrate
    from nonebot_plugin_orm.utils import StreamToLogger
    from sqlalchemy.util import greenlet_spawn

    _init_orm()

    cmd_opts = Namespace()
    with migrate.AlembicConfig(stdout=StreamToLogger(), cmd_opts=cmd_opts) as config:
        cmd_opts.cmd = (migrate.upgrade, [], [])
        await greenlet_spawn(migrate.upgrade, config)
