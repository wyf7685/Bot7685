import sys
from pathlib import Path

from importlib_metadata import metadata

meta = metadata("nonebot-adapter-satori")
if meta.get("version") != "0.13.0rc3":
    sys.exit(0)

from nonebot.adapters.satori import models

file = Path(models.__file__)
lines = file.read_text().splitlines()
# lines.insert(303, "        return values")
lines[312:318] = []
lines[304:309] = []
file.write_text("\n".join(lines))
