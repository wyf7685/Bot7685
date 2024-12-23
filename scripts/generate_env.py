import json
import pathlib
from typing import Any

import yaml

env_file = pathlib.Path(__file__).resolve().parent.parent / ".env"


def _load_yaml(file_path: pathlib.Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


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


def generate_env_file() -> None:
    (pathlib.Path(__file__).resolve().parent.parent / ".env").write_text(
        "\n".join(f"{key}={json.dumps(value)}" for key, value in load_config().items())
    )


if __name__ == "__main__":
    generate_env_file()
