
#!/usr/bin/env python3
"""
engine.py — Updated asynchronous engine with plugin lifecycle, structured logging,
config management, graceful shutdown, and resilient task scheduling.

Usage:
  python engine.py run --config config.json --log-level INFO
  python engine.py list-plugins --plugin-package app_plugins
  python engine.py dry-run --config config.json

Config (JSON example):
{
  "plugin_package": "app_plugins",
  "tick_interval_seconds": 5,
  "max_concurrency": 4,
  "retry": {
    "max_attempts": 5,
    "base_delay_seconds": 0.5,
    "max_delay_seconds": 5.0,
    "jitter_fraction": 0.25
  },
  "plugins": {
    "MyPlugin": {
      "enabled": true,
      "tick_interval_seconds": 3
    }
  }
}

Place your plugins in a package (folder with __init__.py), e.g. app_plugins/,
and implement subclasses of EnginePlugin (see skeleton at bottom).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib
import json
import logging
import pkgutil
import random
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

# ----------------------------
# Version / metadata
# ----------------------------
ENGINE_NAME = "AsyncEngine"
ENGINE_VERSION = "1.3.0"  # bump as needed
ENGINE_BUILD_TIME = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ----------------------------
# Config models
# ----------------------------
@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 5.0
    jitter_fraction: float = 0.20  # 20% jitter


@dataclass
class PluginSpecificConfig:
    enabled: bool = True
    tick_interval_seconds: Optional[float] = None  # override global interval if set
    # Add plugin-specific keys as needed, e.g. credentials, endpoints, etc.


@dataclass
class EngineConfig:
    plugin_package: str = "app_plugins"
    tick_interval_seconds: float = 5.0
    max_concurrency: int = 4
    retry: RetryConfig = field(default_factory=RetryConfig)
    plugins: Dict[str, PluginSpecificConfig] = field(default_factory=dict)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "EngineConfig":
        # Defensive merge for nested structures
        retry = d.get("retry", {})
        plugins_dict = d.get("plugins", {})

        # Normalize plugin configs
        normalized_plugins: Dict[str, PluginSpecificConfig] = {}
        for name, cfg in plugins_dict.items():
            if not isinstance(cfg, dict):
                cfg = {}
            normalized_plugins[name] = PluginSpecificConfig(
                enabled=cfg.get("enabled", True),
                tick_interval_seconds=cfg.get("tick_interval_seconds"),
            )

        return EngineConfig(
            plugin_package=d.get("plugin_package", "app_plugins"),
            tick_interval_seconds=float(d.get("tick_interval_seconds", 5.0)),
            max_concurrency=int(d.get("max_concurrency", 4)),
            retry=RetryConfig(
                max_attempts=int(retry.get("max_attempts", 3)),
                base_delay_seconds=float(retry.get("base_delay_seconds", 0.5)),
                max_delay_seconds=float(retry.get("max_delay_seconds", 5.0)),
                jitter_fraction=float(retry.get("jitter_fraction", 0.20)),
            ),
            plugins=normalized_plugins,
        )

    @staticmethod
    def load(path: Path) -> "EngineConfig":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return EngineConfig.from_dict(data)


# ----------------------------
# Logging setup
# ----------------------------
def setup_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)sZ | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logging.getLogger("asyncio").setLevel(logging.WARNING)


logger = logging.getLogger(ENGINE_NAME)


# ----------------------------
# Plugin interface & discovery
# ----------------------------
class EnginePlugin:
    """
    Base class for engine plugins.

    Required lifecycle methods:
      - async setup(engine): prepare resources, validate config
      - async tick(): perform a unit of work (periodic)
      - async shutdown(): cleanup resources

    Optional:
      - name (str): human-readable name
      - suggested_interval_seconds (float): plugin-specific default interval
    """
    name: str = "UnnamedPlugin"
    suggested_interval_seconds: Optional[float] = None

    def __init__(self, config: PluginSpecificConfig | None = None) -> None:
        self.config = config or PluginSpecificConfig()

    async def setup(self, engine: "Engine") -> None:  # noqa: D401
        raise NotImplementedError

    async def tick(self) -> None:
        raise NotImplementedError

    async def shutdown(self) -> None:
        pass


def iter_plugin_classes(package_name: str) -> List[Type[EnginePlugin]]:
    """
    Discover EnginePlugin subclasses within the given package.
    """
    classes: List[Type[EnginePlugin]] = []
    try:
        pkg = importlib.import_module(package_name)
    except Exception as e:
        logger.error("Failed to import plugin package '%s': %s", package_name, e)
        return classes

    for modinfo in pkgutil.iter_modules(pkg.__path__, package_name + "."):
        try:
            module = importlib.import_module(modinfo.name)
        except Exception as e:
            logger.exception("Failed to import module '%s': %s", modinfo.name, e)
            continue

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, EnginePlugin)
                and attr is not EnginePlugin
            ):
                classes.append(attr)
    return classes


# ----------------------------
# Backoff/jitter helpers
# ----------------------------
def compute_backoff(
    attempt: int,
    base: float,
    max_delay: float,
    jitter_fraction: float,
) -> float:
    delay = min(max_delay, base * (2 ** (attempt - 1)))
    jitter = delay * jitter_fraction * (random.random() * 2 - 1)  # ±fraction
    return max(0.0, delay + jitter)


# ----------------------------
# Engine runtime
# ----------------------------
class Engine:
    def __init__(self, config: EngineConfig):
        self.config = config
        self.plugins: List[EnginePlugin] = []
        self._stopping = asyncio.Event()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrency)
        self._tasks: List[asyncio.Task] = []
        self._loop = asyncio.get_event_loop()

    def load_plugins(self) -> None:
        classes = iter_plugin_classes(self.config.plugin_package)
        if not classes:
            logger.warning("No plugins discovered in package '%s'.", self.config.plugin_package)

        for cls in classes:
            plugin_name = getattr(cls, "name", cls.__name__)
            p_cfg = self.config.plugins.get(plugin_name, PluginSpecificConfig())
            if not p_cfg.enabled:
                logger.info("Plugin '%s' disabled via config.", plugin_name)
                continue
            try:
                plugin = cls(p_cfg)
                self.plugins.append(plugin)
                logger.info("Loaded plugin: %s", plugin_name)
            except Exception:
                logger.exception("Failed to instantiate plugin class '%s'.", plugin_name)

    async def _setup_all(self) -> None:
        for plugin in self.plugins:
            try:
                await plugin.setup(self)
                logger.info("Plugin setup complete: %s", plugin.name)
            except Exception:
                logger.exception("Plugin setup failed: %s", plugin.name)

    async def _shutdown_all(self) -> None:
        for plugin in self.plugins:
            with contextlib.suppress(Exception):
                await plugin.shutdown()
                logger.info("Plugin shutdown complete: %s", plugin.name)

    def _register_signal_handlers(self) -> None:
        def _signal_handler(signame: str):
            logger.warning("Received signal %s — initiating graceful shutdown.", signame)
            self.stop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                self._loop.add_signal_handler(sig, _signal_handler, sig.name)

    def stop(self) -> None:
        self._stopping.set()

    async def run(self) -> None:
        self._register_signal_handlers()
        await self._setup_all()

        try:
            # Schedule plugin tickers
            for plugin in self.plugins:
                interval = (
                    plugin.config.tick_interval_seconds
                    if plugin.config.tick_interval_seconds is not None
                    else (plugin.suggested_interval_seconds or self.config.tick_interval_seconds)
                )
                task = self._loop.create_task(self._run_plugin_loop(plugin, interval))
                self._tasks.append(task)

            logger.info(
                "%s v%s started with %d plugin(s).",
                ENGINE_NAME,
                ENGINE_VERSION,
                len(self.plugins),
            )
            # Wait for stop signal
            await self._stopping.wait()

        finally:
            # Cancel tasks and shutdown
            for t in self._tasks:
                t.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            await self._shutdown_all()
            logger.info("%s stopped.", ENGINE_NAME)

    async def _run_plugin_loop(self, plugin: EnginePlugin, interval: float) -> None:
        """
        Continuously run plugin.tick() with retries and backoff.
        """
        name = plugin.name
        attempt = 0
        retry_cfg = self.config.retry

        while not self._stopping.is_set():
            # Respect concurrency limits
            async with self._semaphore:
                try:
                    await plugin.tick()
                    attempt = 0  # reset on success
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    attempt += 1
                    logger.exception("Plugin '%s' tick failed (attempt %d): %s", name, attempt, e)
                    if attempt >= retry_cfg.max_attempts:
                        logger.error(
                            "Plugin '%s' exceeded max attempts (%d). Will continue after interval.",
                            name,
                            retry_cfg.max_attempts,
                        )
                        attempt = 0  # reset for future ticks
                    else:
                        # Backoff before retrying immediately (not waiting for normal interval)
                        delay = compute_backoff(
                            attempt,
                            retry_cfg.base_delay_seconds,
                            retry_cfg.max_delay_seconds,
                            retry_cfg.jitter_fraction,
                        )
                        await asyncio.sleep(delay)
                        # Retry once without waiting the full interval
                        with contextlib.suppress(Exception):
                            await plugin.tick()
                            attempt = 0

            # Normal interval sleep with small jitter to reduce thundering herd
            jitter = interval * 0.05  # 5% jitter
            await asyncio.sleep(max(0.0, interval + random.uniform(-jitter, jitter)))


# ----------------------------
# CLI
# ----------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=f"{ENGINE_NAME} v{ENGINE_VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(subp: argparse.ArgumentParser) -> None:
        subp.add_argument("--config", type=Path, help="Path to JSON config.", required=False)
        subp.add_argument("--log-level", type=str, default="INFO", help="Logging level (INFO/DEBUG/WARN/ERROR).")

    run_p = sub.add_parser("run", help="Run engine.")
    add_common(run_p)

    list_p = sub.add_parser("list-plugins", help="List discoverable plugins in a package.")
    list_p.add_argument("--plugin-package", type=str, default="app_plugins")
    list_p.add_argument("--log-level", type=str, default="INFO")

    dry_p = sub.add_parser("dry-run", help="Load config and plugins, run setup/shutdown only.")
    add_common(dry_p)

    return p


def load_config_from_args(args: argparse.Namespace) -> EngineConfig:
    if args.command in ("run", "dry-run"):
        if args.config and args.config.exists():
            return EngineConfig.load(args.config)
        else:
            logger.warning("No config provided or path missing; using defaults.")
            return EngineConfig()
    elif args.command == "list-plugins":
        # Minimal config with given package
        return EngineConfig(plugin_package=getattr(args, "plugin_package", "app_plugins"))
    else:
        return EngineConfig()


async def main_async(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)
    logger.info("%s v%s (build %s)", ENGINE_NAME, ENGINE_VERSION, ENGINE_BUILD_TIME)

    if args.command == "list-plugins":
        classes = iter_plugin_classes(args.plugin_package)
        if not classes:
            logger.info("No plugins found in package '%s'.", args.plugin_package)
        else:
            logger.info("Found %d plugin class(es) in '%s':", len(classes), args.plugin_package)
            for cls in classes:
                name = getattr(cls, "name", cls.__name__)
                interval = getattr(cls, "suggested_interval_seconds", None)
                logger.info("  - %s (suggested_interval=%s)", name, interval)
        return 0

    config = load_config_from_args(args)
    engine = Engine(config)
    engine.load_plugins()

    if args.command == "dry-run":
        await engine._setup_all()
        await engine._shutdown_all()
        logger.info("Dry-run completed successfully.")
        return 0

    if args.command == "run":
        await engine.run()
        return 0

    logger.error("Unknown command: %s", args.command)
    return 1


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        exit_code = asyncio.run(main_async(args))
    except KeyboardInterrupt:
        exit_code = 130
    sys.exit(exit_code)


if __name__ == "__main__":
    main()


# ----------------------------
# Plugin skeleton (example)
# ----------------------------
# Save this in app_plugins/my_plugin.py (ensure app_plugins/__init__.py exists).
#
# from typing import Optional
# import asyncio
# import logging
# from engine import EnginePlugin, Engine, PluginSpecificConfig
#
# log = logging.getLogger("MyPlugin")
#
# class MyPlugin(EnginePlugin):
#     name = "MyPlugin"
#     suggested_interval_seconds: Optional[float] = 2.0
#
#     def __init__(self, config: PluginSpecificConfig | None = None):
#         super().__init__(config)
#
#     async def setup(self, engine: Engine) -> None:
#         log.info("MyPlugin setup with config: %s", self.config)
#
#     async def tick(self) -> None:
#         # Do work here
#         await asyncio.sleep(0.1)
#         log.info("MyPlugin tick executed.")
#
#     async def shutdown(self) -> None:
#         log.info("MyPlugin shutdown complete.")
``
