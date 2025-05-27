import sys
from typing import NoReturn

from src.bootstrap import init_nonebot

app = init_nonebot()


def run_orm_upgrade() -> NoReturn:
    import asyncio

    from src.utils import orm_upgrade

    sys.exit(asyncio.run(orm_upgrade()))


def main() -> None:
    if "orm-upgrade" in sys.argv:
        run_orm_upgrade()

    import nonebot

    sys.exit(nonebot.run())


if __name__ == "__main__":
    main()
