from src.bootstrap import init_nonebot

app = init_nonebot()


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1:
        import nonebot

        sys.exit(nonebot.run())
    elif sys.argv[1] == "orm":
        from nonebot_plugin_orm.__main__ import main

        sys.argv.pop(1)  # "orm"
        main(prog_name="bot.py orm")
