
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
import json

def grade_all(input_path: str | None, config: Dict[str, Any], logger):
    if not input_path:
        return []
    p = Path(input_path)
    if not p.exists():
        logger.warning('grade_all: input_path not found: %s', p)
        return []
    # Simple behavior: if a JSON file, return its data; else list files
    if p.is_file() and p.suffix.lower() == '.json':
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info('grade_all: loaded %d items from %s', (len(data) if isinstance(data, list) else 1), p)
            return data
        except Exception as e:
            logger.error('grade_all: failed to read JSON: %s', e, exc_info=True)
            return []
    if p.is_dir():
        files = [str(fp) for fp in p.rglob('*') if fp.is_file()]
        logger.info('grade_all: found %d files in %s', len(files), p)
        return [{'file': f} for f in files[:100]]
    return []
