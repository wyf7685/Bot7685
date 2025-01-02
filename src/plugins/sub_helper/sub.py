import base64

from .config import plugin_config

config = plugin_config.sub


def generate() -> str:
    inner = config.fmt_inner.format(data=config.data)
    inner = base64.b64encode(inner.encode()).decode()
    return config.fmt_outer.format(inner=inner, data=config.data)
