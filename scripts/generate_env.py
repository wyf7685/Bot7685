import contextlib
import json
import pathlib
from collections.abc import Generator
from typing import Any, cast

from msgspec import toml as msgtoml
from msgspec import yaml as msgyaml

root = pathlib.Path(__file__).resolve().parent.parent
env_file = root / ".env"
toml_file = root / "pyproject.toml"


def _load_yaml(file_path: pathlib.Path) -> dict[str, Any]:
    return msgyaml.decode(file_path.read_bytes()) or {}


def load_config() -> dict[str, Any]:
    config_dir = pathlib.Path("config")
    root_config = config_dir / "config.yaml"
    if not root_config.exists():
        return {}

    config: dict[str, Any] = _load_yaml(root_config)

    env = str(config.get("environment", "prod"))
    env_config = config_dir / f"{env}.yaml"
    if not env_config.exists():
        return config

    config |= _load_yaml(env_config)

    env_dir = config_dir / env
    if not env_dir.exists():
        return config

    for p in env_dir.iterdir():
        if p.suffix == ".yaml":
            config |= _load_yaml(p)

    return config


def generate_env_file(config: dict[str, object]) -> None:
    env = "\n".join(f"{key}={json.dumps(value)}" for key, value in config.items())
    env_file.write_text(env)


def generate_cli_toml(config: dict[str, object]) -> None:
    adapters = [
        {
            "name": adapter.replace(".", " "),
            "module_name": f"nonebot.adapters.{adapter}",
        }
        for adapter in cast(list[str], config["adapters"])
    ]
    plugins = cast(list[str], config["plugins"])
    plugin_dirs = [
        config["plugin_dir"],
        config["dev_plugin_dir"],
    ]
    for path in pathlib.Path(str(config["dev_plugin_dir"])).iterdir():
        if path.is_dir() and path.name in plugins:
            plugins.remove(path.name)

    toml = msgtoml.decode(toml_file.read_text())
    if "tool" not in toml:
        toml["tool"] = {}
    toml["tool"]["nonebot"] = {
        "adapters": adapters,
        "plugins": plugins,
        "plugin_dirs": plugin_dirs,
        "builtin_plugins": [],
    }
    toml_file.write_bytes(msgtoml.encode(toml))


def generate() -> None:
    config = load_config()
    generate_env_file(config)
    generate_cli_toml(config)


@contextlib.contextmanager
def ensure_cli() -> Generator[None]:
    toml = toml_file.read_text()
    generate()
    try:
        yield
    finally:
        env_file.unlink()
        toml_file.write_text(toml)


if __name__ == "__main__":
    generate()
