# AGENTS.md

## Scope and sources of truth

This file applies to the entire repository. Treat `pyproject.toml` and `uv.lock`
as dependency authority; `ruff.toml`, `ty.toml`, `prek.toml`, and
`.github/workflows/` define checks and CI. `README.md` is an overview only.

Do not copy Ruff, ty, or prek version numbers into documentation; use the
versions resolved by `uv.lock`.

## Project overview

Bot7685 is a Python 3.14 NoneBot2 application managed with `uv`.

```text
bot.py -> src.bootstrap.init_nonebot() -> config -> patches -> driver
       -> adapters -> plugins -> nonebot.run()
```

Keep generic plugin behavior adapter-neutral and isolate adapter-specific code.

## Repository layout

- `bot.py`: application and ORM CLI entrypoint.
- `src/bootstrap/`: configuration, logging, driver setup, dependency tracking,
  and lifespan ordering.
- `src/service/`: shared services (`llm`, `cache`, `kv`, and `task.py`).
- `src/plugins/`: application plugins.
- `src/dev/`: local development plugins; do not place production behavior here.
- `scripts/`: maintenance utilities.
- `config/`: base and environment-specific runtime configuration.
- `data/` and `logs/`: runtime state.
- `docker/`: Bot and Playwright server images.

Preserve each plugin's existing internal architecture; do not introduce a
second organizational convention.

## Setup and runtime commands

```bash
uv sync --locked --all-extras
uv run bot.py
uv run bot.py orm <args>
```

`uv run bot.py` starts the selected environment. Plugin smoke tests must set
`ENVIRONMENT` explicitly and follow the dedicated workflow below.

Configuration loading order:

1. Load `config/config.*`.
2. Select `ENVIRONMENT`, falling back to the root configuration.
3. Merge `config/<environment>/config.*`.
4. Merge the remaining files in that directory in lexicographic order.

Later files override earlier values; avoid duplicate settings unless the
precedence is intentional.

## New plugin runtime smoke testing

Use a dedicated `config/<plugin-name>-debug/` environment. `config/dev/` is
reserved for manually launched VS Code debugging.

Runtime smoke tests depend on the `milky-mock` MCP and the `milky-testing`
skill. If either is unavailable, ask the user to install the plugin from
https://github.com/wyf7685/cc-milky-mock and do not substitute a live service.

Explicitly load only the target plugin, with `plugin_dirs: []`; generated
dependencies may still load automatically. Add `~milky` and only the other
adapters required by the scenario.

```yaml
# config/<plugin-name>-debug/config.yaml
bootstrap:
  adapters:
    - "~milky"
  plugins:
    - "src.plugins.<plugin_name>"
  plugin_dirs: []
```

Use the existing adapter supplemental-file convention with test-only values:

```yaml
# config/<plugin-name>-debug/adapters.yaml
scope_compat: true
milky:
  clients:
    - host: "127.0.0.1"
      port: 4000
      access_token: "<test-token>"
```

Keep `bootstrap` out of files using `scope_compat`. Start from the repository
root:

```bash
ENVIRONMENT="<plugin-name>-debug" uv run bot.py
```

1. Start `milky-mock` with `init_test_env(start_server=true, ...)`, creating the
   test Bot, users, groups, members, and friends. Match its port and token to
   the dedicated environment.
2. Verify target-plugin loading and the Bot connection with
   `get_milky_server_status` and connection activities from `get_activity`.
   A listening port alone is insufficient.
3. Simulate one message or event, save its `activity_cursor`, and query
   `get_activity(after_cursor=...)` for the resulting `message` or `api_call`.
   Continue from `next_cursor`; use complete data only when needed and
   `clear_activity` between independent scenarios.
4. Restart the Bot after source or configuration changes. Stop the Bot and call
   `stop_milky_server` afterward. Never expose test credentials or dump merged
   configuration into logs or documentation.

## Plugin conventions

Package plugins declare metadata before registration imports:

```python
__plugin_meta__ = PluginMetadata(...)

from . import matchers as matchers
```

- Provide meaningful metadata, a config model, and supported adapters when
  applicable.
- Prefer `nonebot_plugin_alconna`, `UniMessage`, `nonebot_plugin_uninfo`, and
  `inherit_supported_adapters` for adapter-neutral behavior.
- Put adapter-specific event, API, and message conversion under `adapters/`.
- Use explicit permissions such as `SUPERUSER` for administrative commands and
  keep user-facing responses consistent with the surrounding Chinese UI.
- Use Pydantic models with `get_plugin_config`; use `SecretStr` for credentials
  and never log secret values.

## Shared services, async, and lifecycle

Cross-plugin behavior belongs in `src/service/`. Use public package exports;
import LLM contracts from `src.service.llm`, never private implementation
modules.

Reuse `src.service.cache`, `src.service.kv`, `src.service.task`, the driver task
group, `src.utils.ConfigFile`, and `src.utils.logger_wrapper` before adding new
infrastructure.

- Keep handlers and service I/O asynchronous. Use async clients and AnyIO;
  offload unavoidable synchronous work with `anyio.to_thread.run_sync`.
- Prefer managed task groups. Close clients and runtimes during shutdown, and
  register spanning resources through driver lifecycle hooks.
- Bootstrap dependency declarations determine startup and reverse shutdown
  order; keep them accurate.

## Generated plugin dependency map

Generate `src/bootstrap/patches/plugin_requires.json` with:

```bash
uv run python -m scripts.resolve_plugin_requires
```

Never edit it manually. Regenerate it after changing imports between
`src/plugins`, `src/service`, or `nonebot_plugin_*` packages.

## Code style

Follow `ruff.toml` and existing code.

- Target Python 3.14; use 4-space indentation, 88 columns, double quotes, and
  LF line endings.
- Use modern typing and type public parameters, returns, and data structures.
- Keep imports organized with `src` as first-party; prefer `pathlib.Path`.
- Do not use blanket `noqa`, `type: ignore`, or ty suppressions. Keep explicit
  exports where the package already uses `__all__`.
- Use NoneBot logging in runtime code; maintenance scripts may print concise
  status output.

## Verification

Run the applicable non-mutating checks:

```bash
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run ty check .
```

The repository has no unit-test suite. Do not add pytest, unittest, coverage,
test dependencies, test-only scaffolding, or a `tests/` directory; ignored
scripts under `.local/` are experiments, not a test convention.

Runtime behavior changes require a focused smoke test of the actual matcher,
adapter, configuration, lifecycle, ORM, rendering, or LLM surface. Static
checks do not replace that test.

## Runtime files, security, and change discipline

Do not hand-edit or commit `.env`, `.venv/`, `.local/`, `.ruff_cache/`,
`__pycache__/`, `data/`, or `logs/`; tooling may regenerate them.

Treat `config/` as deployment-sensitive. Never expose tokens, credentials,
webhook secrets, IDs, or private endpoints in output, logs, fixtures, or
documentation, and do not rewrite unrelated environment configuration.

- Fix the owning source and reuse established services and structures.
- Update every caller when changing a public contract; do not leave aliases or
  deprecated paths.
- Keep generated artifacts synchronized with their source.
- Avoid unrelated formatting or configuration churn, and run the smallest
  complete set of static checks and real smoke scenarios covering the change.
