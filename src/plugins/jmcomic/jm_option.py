from nonebot_plugin_localstore import get_plugin_cache_dir

from jmcomic import JmOption


def patch_log() -> None:
    from jmcomic import JmModuleConfig

    def log(_: object, topic: str, msg: str) -> None:
        from nonebot import logger
        from nonebot.utils import escape_tag

        logger.opt(colors=True).info(f"[<m>{topic}</m>] {escape_tag(msg)}")

    JmModuleConfig.jm_log.__func__.__code__ = log.__code__  # pyright:ignore[reportFunctionMemberAccess]


CACHE_DIR = get_plugin_cache_dir()
DOWNLOAD_DIR = CACHE_DIR / "download"
PDF_DIR = CACHE_DIR / "pdf"
option_dict = {
    "version": "2.1",
    "dir_rule": {
        "base_dir": str(DOWNLOAD_DIR),
    },
    "download": {"threading": {"image": 4, "photo": 4}},
    "plugins": {
        "after_album": [
            {
                "plugin": "img2pdf",
                "kwargs": {
                    "pdf_dir": str(PDF_DIR),
                    "filename_rule": "Aalbum_id",
                },
            }
        ],
    },
}

patch_log()
option = JmOption.construct(option_dict)
