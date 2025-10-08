# /// script
# dependencies = ["msgspec[toml,yaml]>=0.19.0"]
# ///

import contextlib
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from msgspec import toml as msgtoml
from msgspec import yaml as msgyaml

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

root = Path(__file__).resolve().parent.parent
env_file = root / ".env"
toml_file = root / "pyproject.toml"


def _load_yaml(file_path: Path) -> dict[str, Any]:
    data = msgyaml.decode(file_path.read_bytes()) or {}

    if data.pop("scope_compat", None):
        for key, value in list(data.items()):
            if isinstance(value, dict):
                del data[key]
                for k, v in value.items():
                    data[f"{key}_{k}"] = v

    return data


def deep_update(
    mapping: dict[str, Any],
    *updating_mappings: dict[str, Any],
) -> dict[str, Any]:
    """深度更新合并字典"""
    updated_mapping = mapping.copy()
    for updating_mapping in updating_mappings:
        for k, v in updating_mapping.items():
            if (
                k in updated_mapping
                and isinstance(updated_mapping[k], dict)
                and isinstance(v, dict)
            ):
                updated_mapping[k] = deep_update(updated_mapping[k], v)
            else:
                updated_mapping[k] = v
    return updated_mapping


def _find_config_file(fp: Path) -> Path | None:
    for suffix in ".toml", ".yaml", ".yml", ".json":
        if (file := fp.with_suffix(suffix)).exists():
            return file
    return None


_decoders: dict[str, Callable[[bytes], dict[str, Any]]] = {}


def _get_decoder(suffix: str) -> Callable[[bytes], dict[str, Any]] | None:
    if suffix not in _decoders:
        match suffix:
            case ".toml":
                from msgspec import toml as module
            case ".yaml" | ".yml":
                from msgspec import yaml as module
            case ".json":
                from msgspec import json as module
            case _:
                return None
        _decoders[suffix] = module.decode

    return _decoders[suffix]


def _load_file(fp: Path) -> dict[str, Any]:
    if (decoder := _get_decoder(fp.suffix)) is None:
        return {}

    data = decoder(fp.read_bytes()) or {}

    if data.pop("scope_compat", None):
        for key, value in list(data.items()):
            if isinstance(value, dict):
                del data[key]
                for k, v in value.items():
                    data[f"{key}_{k}"] = v

    return data


def load_config() -> dict[str, Any]:
    config_dir = Path("config")
    if (root_config := _find_config_file(config_dir / "config")) is None:
        return {}

    config = _load_file(root_config)

    env = str(config.get("environment", "prod"))
    if (env_config := _find_config_file(config_dir / env)) is None:
        return config

    config = deep_update(config, _load_file(env_config))

    if (env_dir := config_dir / env).exists():
        for p in filter(Path.is_file, env_dir.iterdir()):
            config = deep_update(config, _load_file(p))

    return config


def generate_env_file(config: dict[str, Any]) -> None:
    env = "\n".join(f"{key}={json.dumps(value)}" for key, value in config.items())
    env_file.write_text(env)


def generate_cli_toml(bs_cfg: dict[str, Any]) -> None:
    adapters = [
        {
            "name": adapter.replace(".", " ").replace("~", ""),
            "module_name": adapter.replace("~", "nonebot.adapters."),
        }
        for adapter in cast("list[str]", bs_cfg["adapters"])
    ]
    plugins = cast("list[str]", bs_cfg["plugins"])

    toml: dict[str, dict[str, object]] = msgtoml.decode(toml_file.read_text())
    toml.setdefault("tool", {})
    toml["tool"]["nonebot"] = {
        "adapters": adapters,
        "plugins": plugins,
        "plugin_dirs": bs_cfg["plugin_dirs"],
        "builtin_plugins": [],
    }
    toml_file.write_bytes(msgtoml.encode(toml))


@contextlib.contextmanager
def ensure_cli() -> Generator[None]:
    u = str(uuid.uuid4()).partition("-")[0]
    toml_backup = root / f"pyproject.{u}.toml"
    toml_backup.write_bytes(toml_file.read_bytes())
    config = load_config()

    try:
        generate_env_file(config)
        generate_cli_toml(config["bootstrap"])
        yield
    finally:
        env_file.unlink(missing_ok=True)
        toml_file.unlink(missing_ok=True)
        toml_backup.rename(toml_file)


if __name__ == "__main__":
    import sys

    if sys.argv[-1] == "cli":
        with ensure_cli():
            input("Press Enter to exit...")
    else:
        generate_env_file(load_config())
