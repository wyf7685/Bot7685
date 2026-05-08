from pathlib import Path


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


async def orm_revision(
    message: str | None = None,
    sql: bool | None = False,
    head: str | None = None,
    splice: bool = False,
    branch_label: str | None = None,
    version_path: str | Path | None = None,
    rev_id: str | None = None,
    depends_on: str | None = None,
) -> None:
    from argparse import Namespace

    from nonebot_plugin_orm import _init_orm, migrate
    from nonebot_plugin_orm.utils import StreamToLogger
    from sqlalchemy.util import greenlet_spawn

    _init_orm()

    cmd_opts = Namespace()
    with migrate.AlembicConfig(stdout=StreamToLogger(), cmd_opts=cmd_opts) as config:
        cmd_opts.cmd = (migrate.revision, [], [])
        scripts = await greenlet_spawn(
            migrate.revision,
            config,
            message=message,
            sql=sql,
            head=head,
            splice=splice,
            branch_label=branch_label,
            version_path=version_path,
            rev_id=rev_id,
            depends_on=depends_on,
        )
        for script in scripts:
            config.move_script(script)
