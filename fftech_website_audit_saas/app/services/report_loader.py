
from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from .config import resolve_path


def discover_report_path(report_arg: str | None, output_dir: Path, logger) -> Path | None:
    if report_arg:
        p = resolve_path(report_arg)
        if p.exists():
            return p
        logger.warning('--report path not found: %s', p)
    for c in [output_dir / 'report.json', output_dir / 'report.csv', output_dir / 'report.xlsx', output_dir / 'report.xls']:
        if c.exists():
            return c
    logger.info('No report file discovered in %s.', output_dir)
    return None


def read_csv_dicts(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def read_json(path: Path) -> Any:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def read_xlsx(path: Path, logger) -> List[Dict[str, Any]]:
    try:
        import pandas as pd
        if path.suffix.lower() == '.xlsx':
            df = pd.read_excel(path, engine='openpyxl')
        else:
            df = pd.read_excel(path, engine='xlrd')
        return df.to_dict(orient='records')
    except Exception as e:
        logger.error('Failed to read Excel file: %s', e, exc_info=True)
        raise


def load_report_data(report_path: Path, logger) -> List[Dict[str, Any]]:
    ext = report_path.suffix.lower()
    if ext == '.json':
        payload = read_json(report_path)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ('rows','data','results'):
                if key in payload and isinstance(payload[key], list):
                    return payload[key]
            return [payload]
        raise ValueError('Unsupported JSON structure for report.')
    elif ext == '.csv':
        return read_csv_dicts(report_path)
    elif ext in ('.xlsx','.xls'):
        return read_xlsx(report_path, logger)
    else:
        raise ValueError(f'Unsupported report extension: {ext}')
