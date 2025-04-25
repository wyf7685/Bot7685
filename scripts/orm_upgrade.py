# /// script
# dependencies = ["msgspec[toml,yaml]>=0.19.0"]
# ///

import os

from generate_env import ensure_cli  # pyright: ignore[reportImplicitRelativeImport]

if __name__ == "__main__":
    with ensure_cli():
        os.system("nb orm upgrade")  # noqa: S605, S607
