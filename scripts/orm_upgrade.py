# ruff: noqa: S605, S607
import os

from generate_env import env_file, generate_env_file


def orm_upgrade() -> None:
    generate_env_file()
    os.system("nb orm upgrade")
    env_file.unlink(missing_ok=True)


if __name__ == "__main__":
    orm_upgrade()
