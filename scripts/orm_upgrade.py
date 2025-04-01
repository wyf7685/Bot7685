# ruff: noqa: S605, S607
import os

from generate_env import ensure_cli  # pyright: ignore[reportImplicitRelativeImport]


def orm_upgrade() -> None:
    with ensure_cli():
        os.system("nb orm upgrade")


if __name__ == "__main__":
    orm_upgrade()
