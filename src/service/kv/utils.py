import inspect

from nonebot.plugin import Plugin, get_plugin_by_module_name


def get_caller_plugin() -> Plugin | None:
    current_frame = inspect.currentframe()
    if current_frame is None:
        return None

    # find plugin
    frame = current_frame
    while frame := frame.f_back:
        module_name = (module := inspect.getmodule(frame)) and module.__name__
        if module_name is None:
            return None

        # skip nonebot_plugin_localstore it self
        if module_name.split(".", maxsplit=1)[0] == "nonebot_plugin_localstore":
            continue

        plugin = get_plugin_by_module_name(module_name)
        if plugin and plugin.id_ != "nonebot_plugin_localstore":
            return plugin

    return None


def try_get_caller_plugin() -> Plugin:
    if plugin := get_caller_plugin():
        return plugin
    raise RuntimeError("Cannot detect caller plugin")
