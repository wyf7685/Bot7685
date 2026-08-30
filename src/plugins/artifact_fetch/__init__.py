from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="Artifact Fetch",
    description="A plugin to fetch GitHub Actions artifacts.",
    usage=(
        "artifact fetch [-o owner] [-r repo] [-w workflow_id]\n"
        "artifact subscribe add -o owner -r repo [-w workflow_id] "
        "[--upload-artifact --filter-regex REGEX "
        "[--rename-template TEMPLATE]]\n"
        "artifact subscribe remove -o owner -r repo [-w workflow_id]\n"
        "artifact subscribe list"
    ),
    type="application",
    config=Config,
    supported_adapters={"~milky"},
)

from . import matchers as matchers
