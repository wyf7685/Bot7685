from src.bootstrap import init_nonebot

app = init_nonebot()


if __name__ == "__main__":
    import sys

    if "orm-upgrade" not in sys.argv:
        import nonebot

        nonebot.run()
    else:
        import asyncio

        from src.utils import orm_upgrade

        asyncio.run(orm_upgrade())
