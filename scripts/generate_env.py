import json
import pathlib
from typing import Any

import yaml

root = pathlib.Path(__file__).resolve().parent.parent
config_file = root / "config.yaml"
env_file = root / ".env"


def load_config() -> dict[str, Any]:
    if not config_file.exists():
        return {}
    config: dict[str, Any] = yaml.safe_load(config_file.open("r"))
    config |= config.pop(config.get("environment", "prod"), {})
    return config


def generate_env_file() -> None:
    env_file.write_text(
        "\n".join(f"{key}={json.dumps(value)}" for key, value in load_config().items())
    )


if __name__ == "__main__":
    generate_env_file()
