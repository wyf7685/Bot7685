# ruff: noqa: T201, S603
import ast
import contextlib
import importlib
import importlib.metadata
import itertools
import json
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

SRC = Path(__file__).parent.parent.joinpath("src")


class ImportCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.add(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and not node.level:
            self.imports.add(node.module)

    @classmethod
    def collect(cls, path: Path) -> set[str]:
        try:
            module = ast.parse(path.read_text(encoding="utf-8"), str(path), mode="exec")
        except Exception:
            return set()
        collector = cls()
        collector.visit(module)
        return collector.imports


def resolve_requires(path: Path, *, seen: set[Path] | None = None) -> set[str]:
    if seen is None:
        seen = set()
    elif path in seen:
        return set()
    seen.add(path)
    if not path.exists():
        return set()
    if path.is_dir():
        return set(
            itertools.chain.from_iterable(
                resolve_requires(item, seen=seen) for item in path.iterdir()
            )
        )
    if path.suffix != ".py" or not path.is_file():
        return set()

    requires: set[str] = set()
    for name in ImportCollector.collect(path):
        if name.startswith("nonebot_plugin_"):
            requires.add(name.split(".")[0])
        elif name.startswith(("src.plugins.", "src.service.")):
            requires.add(".".join(name.split(".")[:3]))

    if path.stem == "__init__":
        requires.update(resolve_requires(path.parent, seen=seen))

    return requires


def iter_plugins() -> Iterable[Path]:
    for path in itertools.chain(
        SRC.joinpath("plugins").iterdir(),
        SRC.joinpath("service").iterdir(),
    ):
        if (path.is_dir() and (path / "__init__.py").is_file()) or (
            path.is_file() and path.suffix == ".py" and not path.stem.startswith("_")
        ):
            yield path


known_plugins: set[str] = set()


def filter_requires(requires: set[str]) -> Iterable[str]:
    for req in requires:
        if req in known_plugins or not req.startswith("nonebot_plugin_"):
            yield req
        else:
            with contextlib.suppress(importlib.metadata.PackageNotFoundError):
                importlib.metadata.distribution(req)
                yield req
                known_plugins.add(req)


def main():
    git = shutil.which("git")
    assert git is not None, "Git is required to run this script."

    plugin_requires = {
        path.stem if path.is_file() else path.name: sorted(
            filter_requires(resolve_requires(path))
        )
        for path in sorted(iter_plugins())
    }
    deps_json = json.dumps(plugin_requires, ensure_ascii=False, separators=(",", ":"))
    deps_json_file = SRC / "bootstrap" / "patches" / "plugin_requires.json"

    if (
        not deps_json_file.exists()
        or deps_json_file.read_text(encoding="utf-8") != deps_json
    ):
        deps_json_file.write_text(deps_json, encoding="utf-8")
        print("Plugin dependencies updated.")
        subprocess.run([git, "add", str(deps_json_file)], check=True)


if __name__ == "__main__":
    main()
