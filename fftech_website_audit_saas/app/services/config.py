
"""Central configuration & logging utilities."""
from __future__ import annotations
import logging
import os
import sys
from pathlib import Path
from typing import Tuple

APP_NAME = "audit-saas"
DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEFAULT_LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
DEFAULT_OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "artifacts"))


def resolve_path(p: str | Path) -> Path:
    return Path(p).expanduser().resolve()


def ensure_dirs(*dirs: Path) -> None:
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def setup_logging(level: str = DEFAULT_LOG_LEVEL, log_dir: Path = DEFAULT_LOG_DIR) -> Tuple[logging.Logger, Path]:
    lvl = getattr(logging, level.upper(), logging.INFO)
    log_dir = resolve_path(log_dir)
    ensure_dirs(log_dir)

    logger = logging.getLogger(APP_NAME)
    logger.setLevel(lvl)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(lvl)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    fh_path = log_dir / f"{APP_NAME}.log"
    fh = logging.FileHandler(fh_path, encoding="utf-8")
    fh.setLevel(lvl)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger, fh_path

