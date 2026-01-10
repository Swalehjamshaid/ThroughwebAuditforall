
"""Example grader producing synthetic metrics from input files."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict


def grade_all(input_path: str | None, config: Dict[str, Any], logger):
    if not input_path:
        return {"status": "no-input"}
    p = Path(input_path).expanduser().resolve()
    total = 0
    files = []
    if p.is_dir():
        for f in p.rglob('*'):
            if f.is_file():
                files.append(f)
                total += f.stat().st_size
    elif p.is_file():
        files = [p]; total = p.stat().st_size
    metrics = {
        "files": len(files),
        "bytes": total,
        "input": str(p)
    }
    logger.info('Graded input: %s', metrics)
    return metrics

