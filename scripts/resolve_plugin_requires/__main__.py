# ruff: noqa: T201
import json

from . import resolve_plugin_requires
from .models import SRC


def main() -> None:
    plugin_requires = resolve_plugin_requires()
    deps_json = json.dumps(plugin_requires, ensure_ascii=False, separators=(",", ":"))
    deps_json_file = SRC / "bootstrap" / "patches" / "plugin_requires.json"

    if (
        not deps_json_file.exists()
        or deps_json_file.read_text(encoding="utf-8") != deps_json
    ):
        deps_json_file.write_text(deps_json, encoding="utf-8")
        print("Plugin dependencies updated.")


if __name__ == "__main__":
    main()
