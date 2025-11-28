import base64

from .config import plugin_config

config = plugin_config.sub


def generate() -> str:
    u = config.u.read_text()
    inner = config.inner.format(u=u, d=config.d)
    inner = base64.b64encode(inner.encode()).decode()
    return config.outer.format(inner=inner, d=config.d)
