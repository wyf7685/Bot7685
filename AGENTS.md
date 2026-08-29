# AGENTS.md

## Scope and sources of truth

This file applies to the entire repository.

Use repository configuration as the authority:

- `pyproject.toml` defines Python and dependency requirements.
- `uv.lock` defines resolved dependencies.
- `ruff.toml`, `ty.toml`, and `prek.toml` define code-quality checks.
- `.github/workflows/` defines CI behavior.
- `README.md` is an overview, not the canonical development specification.

Do not copy Ruff, ty, or prek version numbers into documentation. Use the versions resolved by `uv.lock`.

## Project overview

Bot7685 is a Python 3.14 NoneBot2 application managed with `uv`.

Runtime entrypoint:

```text
bot.py
  -> src.bootstrap.init_nonebot()
  -> load and merge environment configuration
  -> install bootstrap patches
  -> create the combined NoneBot driver
  -> register adapters
  -> load external and local plugins
  -> nonebot.run()
```

The application supports multiple adapters. Keep generic plugin behavior adapter-neutral; isolate adapter-specific behavior in dedicated modules.

## Repository layout

- `bot.py`: application and ORM CLI entrypoint.
- `src/bootstrap/`: configuration loading, logging, driver setup, plugin dependency tracking, and lifespan ordering.
- `src/service/`: shared library plugins and cross-plugin services.
  - `llm/`: stable LLM service contracts and runtime.
  - `cache/`: shared cache abstraction.
  - `kv/`: persistent key-value storage.
  - `task.py`: background task helpers backed by the driver task group.
- `src/plugins/`: application plugins.
- `src/dev/`: local development plugins; do not place production behavior here.
- `scripts/`: repository maintenance utilities.
- `config/`: base and environment-specific runtime configuration.
- `data/`: runtime data and ORM state.
- `logs/`: runtime logs.
- `docker/`: Bot and Playwright server images.

Complex plugins should preserve their existing internal architecture. Examples:

- `src/plugins/zssm/`: contracts, orchestration, input collection, tools, and web sources.
- `src/plugins/group_daily_analysis/`: domain, analyzers, services, persistence, rendering, and matchers.
- `src/plugins/group_pipe/`: common conversion logic, adapter implementations, database, and matchers.
- `src/plugins/llm_admin/`: matcher, interaction, forms, status, and configuration endpoints.

Do not introduce a second organizational convention beside an existing one.

## Setup and runtime commands

Install the locked project environment:

```bash
uv sync --locked --all-extras
```

Start the Bot:

```bash
uv run bot.py
```

Run the NoneBot ORM CLI:

```bash
uv run bot.py orm <args>
```

`config/config.*` supplies the default environment. The `ENVIRONMENT` variable overrides it and selects `config/<environment>/`.

Configuration loading order:

1. Load `config/config.*`.
2. Select the environment.
3. Merge `config/<environment>/config.*`.
4. Merge the remaining files in that environment directory.

Supplemental environment files are merged in lexicographic path order. Later files override earlier values; avoid duplicate settings unless that precedence is intentional.

## Plugin conventions

Package plugins normally declare metadata in `__init__.py` before importing registration modules:

```python
__plugin_meta__ = PluginMetadata(...)

from . import matchers as matchers
```

Follow these rules:

- Declare `PluginMetadata` with meaningful name, description, usage, and type.
- Declare the plugin config model and supported adapters when applicable.
- Import matcher or hook modules after metadata declaration so registration occurs during plugin loading.
- Prefer `nonebot_plugin_alconna`, `UniMessage`, `nonebot_plugin_uninfo`, and `inherit_supported_adapters` for adapter-neutral behavior.
- Put adapter-specific event, API, or message conversion code under an `adapters/` module.
- Use explicit permissions such as `SUPERUSER` for administrative commands.
- Keep user-facing responses consistent with the surrounding plugin, which is generally Chinese.
- Use Pydantic models with `get_plugin_config` for configuration.
- Use `SecretStr` for credentials and never log secret values.

The plugin manager applies runtime enable/disable state through a message preprocessor. Do not duplicate plugin-switch checks in individual matchers unless the behavior occurs outside matcher preprocessing.

## Shared services and public APIs

Cross-plugin behavior belongs in `src/service/` when an existing service is the correct owner.

Use public package exports rather than internal implementation modules. In particular, import LLM contracts from:

```python
from src.service.llm import ...
```

Do not import private LLM adapter or runtime implementation modules from consumers.

Reuse existing helpers before adding new infrastructure:

- `src.service.cache` for caching.
- `src.service.kv` for persistent typed values.
- `src.service.task` or the driver task group for managed background work.
- `src.utils.ConfigFile` and related types for local JSON-backed data where already appropriate.
- `src.utils.logger_wrapper` for named bootstrap/component logging.

## Async and lifecycle behavior

NoneBot handlers and service I/O should remain asynchronous.

- Do not block the event loop with synchronous network, file, rendering, or CPU-heavy work.
- Use async clients and AnyIO primitives where available.
- Offload unavoidable synchronous work with `anyio.to_thread.run_sync`.
- Prefer managed task groups over detached background tasks.
- Close async clients and service runtimes during plugin or driver shutdown.
- Register setup and disposal through driver lifecycle hooks where resources span multiple events.

Bootstrap patches track plugin dependencies and use them to order startup and reverse shutdown. Incorrect dependency declarations can break lifecycle ordering.

## Generated plugin dependency map

`src/bootstrap/patches/plugin_requires.json` is generated by:

```bash
uv run --script scripts/resolve_plugin_requires.py
```

Rules:

- Never edit `plugin_requires.json` manually.
- Run the generator after changing imports between `src/plugins`, `src/service`, or `nonebot_plugin_*` packages.

The generator is also invoked by the prek hook.

## Code style

Follow `ruff.toml` and existing code.

- Target Python 3.14.
- Use 4-space indentation and a line length of 88.
- Use double-quoted strings and LF line endings.
- Use modern Python typing, including PEP 695 syntax where it improves clarity.
- Type function parameters, return values, and public data structures.
- Keep imports organized by Ruff/isort; `src` is first-party.
- Prefer `pathlib.Path` over string-based path manipulation.
- Prefer immutable, slotted dataclasses for small runtime value objects where appropriate.
- Do not add blanket `noqa`, `type: ignore`, or ty suppression to avoid fixing a real issue.
- Keep public exports explicit with `__all__` where the package already uses it.
- Avoid `print` in runtime code; use NoneBot logging. Maintenance scripts may print concise status output.

## Validation commands

Non-mutating validation:

```bash
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run ty check .
```

Explicit formatting and automatic fixes:

```bash
uv run ruff check --fix .
uv run ruff format .
```

The prek Ruff hooks intentionally apply fixes, and the dependency hook may update `plugin_requires.json`. Review resulting changes.

## No unit tests

This project does not use or plan to add a unit-test suite.

- Do not add pytest, unittest-based suites, test dependencies, coverage tooling, or test-only scaffolding.
- Do not create a `tests/` directory.
- Ignored scripts under `.local/` are local experiments, not a test convention.
- Verify behavioral changes with a focused runtime smoke test of the actual changed surface.

Required behavioral verification examples:

- Matcher or command changes: start the Bot and exercise the affected command or event path.
- Adapter changes: use the affected adapter or an appropriate event simulator.
- Configuration changes: initialize the Bot with the affected environment and observe successful loading.
- Lifecycle changes: exercise startup and shutdown.
- ORM changes: run the relevant ORM command or migration scenario.
- Rendering changes: generate the actual image or HTML output.
- LLM changes: exercise the affected completion, structured-output, or tool-call path with controlled configuration.

Static checks do not replace a behavioral smoke test when runtime behavior changed.

## Runtime and sensitive files

Do not hand-edit or commit generated runtime artifacts. Tooling and runtime commands may regenerate them during setup and smoke testing:

- `.env`
- `.venv/`
- `.local/`
- `.ruff_cache/`
- `__pycache__/`
- `data/`
- `logs/`

Treat files under `config/` as deployment-sensitive. Do not expose tokens, credentials, webhook secrets, IDs, or private endpoint values in output, logs, fixtures, or documentation.

Do not normalize or rewrite environment configuration unrelated to the requested change.

## Change discipline

- Fix the owning source instead of suppressing symptoms.
- Reuse established services, plugin structure, and utilities.
- Update every caller when changing a public contract; never leave compatibility aliases.
- Keep generated artifacts synchronized with their source.
- Avoid unrelated formatting or configuration churn.
- Run the smallest complete set of static checks and real smoke scenarios that covers the change.
