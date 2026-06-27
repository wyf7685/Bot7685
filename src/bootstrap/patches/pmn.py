from bot7685_ext.nonebot import on_plugin_load
from nonebot.plugin import Plugin, get_loaded_plugins


def get_filtered_plugins() -> set[Plugin]:
    return {
        plugin
        for plugin in get_loaded_plugins()
        if plugin.id_.startswith("nonebot_plugin_") or plugin.metadata is not None
    }


@on_plugin_load("after", plugin_id="nonebot_plugin_picmenu_next", skip_on_exc=True)
def _patch_pmn(_: Plugin) -> None:
    from nonebot_plugin_picmenu_next import data_source as ds_mod

    ds_mod._get_loaded_plugins = get_filtered_plugins  # noqa: SLF001  # ty:ignore[invalid-assignment]
